"""
PEMF mDNS Servis Yayıncısı — LattePanda Gateway

LattePanda'nın IP adresini ağa otomatik olarak duyurur:
  pemf-gateway.local → MQTT broker (port 1883)

Bu sayede ESP32 ve Android uygulaması, IP adresi değişse bile
cihazı otomatik bulabilir.

Bağımlılık:
    pip install zeroconf

Kullanım:
    # Bağımsız mod
    python -m services.mdns_service

    # GUI entegrasyonu
    svc = MDNSService(mqtt_port=1883)
    svc.start()
    ...
    svc.stop()
"""

import logging
import socket
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

# mDNS servis adı — tüm cihazlar bu adı arar
MDNS_SERVICE_NAME = "PEMF-Gateway"
MDNS_SERVICE_TYPE = "_mqtt._tcp.local."
MDNS_HOST_NAME = "pemf-gateway"  # pemf-gateway.local olarak çözünür


def _get_local_ip() -> str:
    """Aktif ağ arayüzünün IP adresini döndürür.

    ⚠️ İKİ AŞAMALI (denetim 2026-08-17; kardeşi `servers/auto_discovery._get_local_ip`). UDP
    `connect` DEFAULT ROUTE ister. Offline klinikte ya da hotspot-only kurulumda (bkz.
    `scripts/start_hotspot.ps1`: *"özellikle offline klinikte GetInternetConnectionProfile null"*)
    default route YOKTUR → burada kalıcı olarak `127.0.0.1` dönülüyordu ve çağıranların 127.*
    guard'ı yüzünden `_mqtt` (`pemf-gateway.local`) SÜREÇ ÖMRÜ BOYUNCA hiç yayınlanmıyordu.
    Log ise "arayüz gelince kaydolacak" diyordu; o söz TUTULAMIYORDU çünkü tek kurtarma yolu
    `ensure_interfaces_current` ve o da arayüz KÜMESİ değişmediği için callback'leri hiç çağırmıyor
    (hotspot IP'si zaten baştan var). `_pemfvet` tarafı b30d7bd ile toparlandı, bu taraf kalmıştı.

    Aynı fonksiyonun dört satır ötesinde `get_shared_zeroconf()` AYNI süreçte `ifaddr` ile doğru
    IP'yi bulup Zeroconf'u ona bağlıyordu — yani doğru adres zaten eldeydi, yalnız ServiceInfo'ya
    konmuyordu. İkinci aşama o yolu kullanır.

    ⚠️ Loopback YAYINLAMAMA kararı (Audit P3 / #32) KORUNUR: aday bulunamazsa yine `127.0.0.1`
    dönülür ve çağıranların 127.* guard'ı kaydı atlar.

    ⚠️ Sonda MODÜL-YEREL `socket` adıyla yapılır (ortak bir yardımcıya TAŞINMAZ): testler rota
    yokluğunu bu adı gölgeleyerek taklit ediyor."""
    ip = ""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
    except Exception:
        ip = ""
    if ip and not ip.startswith("127."):
        return ip
    try:
        from utils.zeroconf_singleton import _real_lan_ipv4s

        adaylar = _real_lan_ipv4s()
        if adaylar:
            return adaylar[0]
    except Exception:
        pass
    return "127.0.0.1"


class MDNSService:
    """
    Zeroconf (mDNS) MQTT servis yayıncısı.

    LattePanda'nın MQTT broker adresini `pemf-gateway.local` olarak
    yerel ağa duyurur. IP adresi değiştiğinde otomatik günceller.
    """

    def __init__(
        self,
        mqtt_port: int = 1883,
        service_name: Optional[str] = None,
        ip_override: Optional[str] = None,
    ):
        self._mqtt_port = mqtt_port
        self._service_name = service_name or MDNS_SERVICE_NAME
        self._ip_override = ip_override
        self._zeroconf = None
        self._service_info = None
        self._running = False
        self._ip_monitor_thread: Optional[threading.Thread] = None
        self._last_ip: Optional[str] = None

    # ── Public ──────────────────────────────────────────────────────────

    def start(self) -> bool:
        """mDNS yayınını başlat."""
        try:
            from zeroconf import (  # noqa: F401 — availability check (asıl kayıt _ip_monitor_loop'ta)
                ServiceInfo,
                Zeroconf,
            )
        except ImportError:
            logger.error("zeroconf kütüphanesi bulunamadı. Kurulum: pip install zeroconf")
            return False

        if self._running:
            logger.warning("mDNS servisi zaten çalışıyor.")
            return True

        try:
            self._mqtt_port = int(self._mqtt_port) if self._mqtt_port else 1883
            self._running = True

            # Başlatma ve IP değişikliği izleyicisi (Background Thread)
            self._ip_monitor_thread = threading.Thread(
                target=self._ip_monitor_loop,
                name="MDNSService-IPMonitor",
                daemon=True,
            )
            self._ip_monitor_thread.start()
            return True

        except Exception:
            logger.exception("mDNS başlatma hatası detayı:")
            self._running = False
            return False

    def stop(self):
        """mDNS yayınını durdur."""
        if not self._running:
            return
        self._running = False
        try:
            if self._zeroconf and self._service_info:
                self._zeroconf.unregister_service(
                    self._service_info
                )  # ortak Zeroconf'u CLOSE ETME (auto_discovery da kullanir)
                logger.info("mDNS servisi durduruldu.")
        except Exception as e:
            logger.warning(f"mDNS durdurma hatası: {e}")
        finally:
            self._zeroconf = None
            self._service_info = None

    def is_running(self) -> bool:
        return self._running

    def get_current_ip(self) -> Optional[str]:
        return self._last_ip

    # ── Özel ────────────────────────────────────────────────────────────

    def _build_service_info(self, ip: str):
        """Zeroconf ServiceInfo nesnesi oluşturur."""
        from zeroconf import ServiceInfo

        full_name = f"{self._service_name}.{MDNS_SERVICE_TYPE}"
        return ServiceInfo(
            MDNS_SERVICE_TYPE,
            full_name,
            addresses=[socket.inet_aton(ip)],
            port=self._mqtt_port,
            properties={
                "version": "1",
                "type": "pemf-gateway",
                "mqtt_port": str(self._mqtt_port),
                "tls": "0",
            },
            server=f"{MDNS_HOST_NAME}.local.",
        )

    def _ip_monitor_kurulum(self) -> None:
        """Zeroconf'u al, `_mqtt` ilk kaydını yap, re-register callback'ini kaydet.

        ⚠️ AYRI METOT (denetim 2026-08-17): eskiden bu gövde `_ip_monitor_loop`un içindeydi ve
        patladığında `self._running = False; return` ile döngüyü ÖLDÜRÜYORDU. Bu İKİ yayıncıyı
        birden bitiriyordu:
          · `utils/zeroconf_singleton.ensure_interfaces_current`ın TEK çağrıcısı o döngüdür
            (depo geneli ölçüldü) → arayüz izleme tamamen durur;
          · `servers/auto_discovery._reregister` YALNIZCA o callback listesinden çağrılıyor,
            yani `_pemfvet`in toparlanma yolu da SESSİZCE ölüyordu — üstelik o yol bu denetimin
            kendi eklediği düzeltmeydi. İki yayıncı arasında belgelenmemiş bağımlılık.
        Kurulum gerçek bir yarışta patlıyor: `Zeroconf(interfaces=ips)` adaptörleri YENİDEN
        sayıyor (arada Wi-Fi düşerse/hotspot kapanırsa fırlar) ve `register_service`
        `NotRunningException`/`EventLoopBlocked`/`ServiceNameAlreadyRegistered` atabiliyor —
        buradaki eleme yalnız `NonUniqueNameException`ı tanıyor.
        Artık istisna ÇAĞIRANA gider; döngü 30 sn'lik turda yeniden dener."""
        try:
            from zeroconf._exceptions import NonUniqueNameException
        except ImportError:

            class NonUniqueNameException(Exception):
                pass

        local_ip = self._ip_override or _get_local_ip()
        self._last_ip = local_ip
        from utils.zeroconf_singleton import get_shared_zeroconf

        self._zeroconf = get_shared_zeroconf()  # paylasilan TEK Zeroconf (cift-instance 5353 cakismasi yok)

        # #32: loopback (127.*) IP'yi mDNS'e YAYINLAMA — ESP/telefon pemf-gateway.local'i 127.0.0.1'e
        # çözüp KENDİ loopback'ine gider (broker'a bağlanamaz). Gerçek LAN IP yoksa İLK kaydı ATLA;
        # arayüz gelince ensure_interfaces_current → _reregister_mqtt (aynı guard'lı) kaydeder.
        if local_ip and not str(local_ip).startswith("127."):
            self._service_info = self._build_service_info(local_ip)
            try:
                self._zeroconf.register_service(self._service_info)
            except Exception as e:
                if 'NonUniqueNameException' in str(type(e)):
                    logger.warning("mDNS adı çakıştı, random suffix ekleniyor...")
                    import random
                    import string

                    suffix = ''.join(random.choices(string.ascii_letters + string.digits, k=4))
                    self._service_name = f"{self._service_name}-{suffix}"
                    self._service_info = self._build_service_info(local_ip)
                    self._zeroconf.register_service(self._service_info)
                else:
                    raise e
            logger.info(f"✓ mDNS yayını başlatıldı: {MDNS_HOST_NAME}.local → {local_ip}:{self._mqtt_port}")
        else:
            logger.info(
                "mDNS (_mqtt) ilk-kayıt atlandı: geçerli LAN IP yok (ip=%r) — arayüz gelince kaydolacak.", local_ip
            )
        # Arayüz/IP değişiminde bu servisi yeni Zeroconf instance'ına re-register et
        # (0.149'da update_interfaces yok → recreate; bkz. zeroconf_singleton.ensure_interfaces_current).
        from utils.zeroconf_singleton import add_reregister_callback

        add_reregister_callback(self._reregister_mqtt)

    def _ip_monitor_loop(self):
        """IP adresi değişirse mDNS kaydını günceller. İlk kaydı da burada yapar.

        ⚠️ Kurulum hatası bu döngüyü ÖLDÜRMEZ (bkz. `_ip_monitor_kurulum` gerekçesi).
        ⚠️ BACKOFF LOG'A uygulanır, UYKUYA değil: retry zaten mevcut 30 sn'lik tura biniyor,
        yani sıkı döngü/CPU yakma imkânsız; ama 30 sn × 24 saat = 2880 traceback riski var.
        ⚠️ `stop()` sonrası re-publish ETMEME kararı (Audit P3) korunuyor: döngü `_running`e
        bakıyor ve `_reregister_mqtt` kendi guard'ını sürdürüyor."""
        kurulum_ok = False
        hata_sayisi = 0

        while self._running:
            if not kurulum_ok:
                try:
                    self._ip_monitor_kurulum()
                    kurulum_ok = True
                    hata_sayisi = 0
                except Exception:
                    hata_sayisi += 1
                    if hata_sayisi == 1:
                        logger.exception("mDNS arka plan kurulum hatasi (30 sn'de bir yeniden denenecek):")
                    elif hata_sayisi % 10 == 0:
                        logger.warning(
                            "mDNS kurulumu hala basarisiz (%d. deneme) - arayuz monitoru CALISIYOR.",
                            hata_sayisi,
                        )

            try:
                time.sleep(30)  # 30 saniyede bir kontrol
                if not self._running:
                    break
                # ⚠️ KENDİ KURULUMUMUZ BAŞARISIZ OLSA DA DEVAM EDİYORUZ. Bu, bulgunun kalbi:
                # `ensure_interfaces_current` yalnız `_mqtt`i değil, KAYITLI TÜM yayıncıları
                # (özellikle `servers/auto_discovery`nin `_pemfvet` callback'ini) yeni Zeroconf
                # instance'ına re-register ediyor. `continue` ile atlamak, `_mqtt` kurulumu
                # patladığında `_pemfvet`in de toparlanamamasına yol açardı — yani düzeltmek
                # istediğimiz belgelenmemiş bağımlılığı AYNEN korurdu.
                # Zeroconf hâlâ erişilemezse aşağıdaki çağrı da patlar ve döngünün kendi
                # `except`i onu yakalar (döngü ölmez).

                # Gerçek-LAN arayüz seti (WiFi/hotspot/Ethernet IP'leri) değiştiyse paylaşılan Zeroconf'u
                # yeni arayüzlere YENİDEN bağla + tüm yayıncıları (mqtt + pemfvet) yeni instance'a re-register et.
                # Birincil-IP (DHCP) değişimini de KAPSAR: gerçek-IP değişince arayüz-seti değişir → ayrı IP-takibi gereksiz.
                from utils.zeroconf_singleton import ensure_interfaces_current

                ensure_interfaces_current()

            except Exception as e:
                if self._running:
                    logger.error(f"mDNS arayüz-monitör hatası: {e}")

    def _reregister_mqtt(self) -> None:
        """Zeroconf arayüz/IP değişimiyle YENİDEN yaratıldığında _mqtt servisini yeni instance'a
        GÜNCEL IP ile re-register eder (ensure_interfaces_current recreate sonrası çağırır)."""
        if not self._running:
            return  # Audit P3: stop() sonrası callback re-publish etmesin (kasıtlı-kaldırılan servisi canlandırma)
        try:
            from utils.zeroconf_singleton import get_shared_zeroconf

            ip = self._ip_override or _get_local_ip()
            # #32: loopback IP'yi re-register'da da YAYINLAMA (guard tutarlılığı).
            if not ip or str(ip).startswith("127."):
                logger.debug("mDNS (_mqtt) re-register atlandı: geçerli LAN IP yok (ip=%r).", ip)
                return
            self._zeroconf = get_shared_zeroconf()
            self._service_info = self._build_service_info(ip)
            self._zeroconf.register_service(self._service_info)
            self._last_ip = ip
            logger.info("✓ mDNS (_mqtt) yeni arayüzlere re-register: %s.local → %s", MDNS_HOST_NAME, ip)
        except Exception as e:
            logger.error("_mqtt re-register hatası: %s", e)


# ── Standalone çalıştırma ────────────────────────────────────────────────────


def main():
    import signal
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )

    svc = MDNSService(mqtt_port=1883)
    if not svc.start():
        logger.error("mDNS başlatılamadı. Çıkılıyor.")
        sys.exit(1)

    def _shutdown(signum, frame):
        logger.info("Kapatma sinyali alındı...")
        svc.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    logger.info("mDNS servisi çalışıyor. Durdurmak için Ctrl+C.")
    local_ip = svc.get_current_ip()
    logger.info(f"  pemf-gateway.local → {local_ip}:1883")
    logger.info("  ESP32 ve Android bu adresle otomatik bağlanacak.")

    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        svc.stop()


if __name__ == "__main__":
    main()
