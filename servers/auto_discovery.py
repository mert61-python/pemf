# Author: mertaygn, cglrgrkn
"""
PEMF Auto-Discovery Service
============================
mDNS (Bonjour/Zeroconf): Aynı Wi-Fi ağındaki telefonlar LattePanda'yı otomatik
bulur, hiçbir konfigürasyon gerekmez. (Farklı ağdan erişim: Cloudflare tüneli +
Supabase cihaz-kaydı; QR kod KALDIRILDI — React arayüzü kullanılıyor.)

Kullanım:
    from servers.auto_discovery import start_mdns, stop_mdns
    start_mdns(port=8000)
"""

from __future__ import annotations

import logging
import os
import socket

logger = logging.getLogger(__name__)

# ── mDNS (Zeroconf) Servisi ────────────────────────────────────────────────────
_zeroconf_instance = None
_mdns_service_info = None
_mdns_port = 8000
_mdns_device_name = "PEMF-Vet"
#: `start_mdns` çağrıldı mı (`stop_mdns` sonrası False).
#
# ⚠️ NEDEN AYRI BİR BAYRAK (denetim 2026-08-17): `_reregister` eskiden `_mdns_service_info is None`
# ise erken dönüyordu. O koşul İKİ ayrı durumu birbirine karıştırıyordu:
#   (a) `start_mdns` hiç çağrılmadı / `stop_mdns` çağrıldı  → re-register YAPILMAMALI
#   (b) `start_mdns` çağrıldı ama LAN IP yoktu, İLK kayıt ATLANDI → re-register TAM DA BURADA GEREKLİ
# (b) durumunda `_pemfvet` süreç ömrü boyunca HİÇ yayınlanmıyordu; log ise "arayüz gelince
# kaydolacak" diyordu (ölçüldü: `get_shared_zeroconf` hiç çağrılmadı). Kardeş yayıncı doğru
# yapıyor: `services/mdns_service.py:219-236` ServiceInfo'yu SIFIRDAN kuruyor.
#
# ⚠️ Guard'ı TAMAMEN SİLMEK YANLIŞ OLURDU: `stop_mdns()` `_reregister_cbs`'ten callback'i SİLMİYOR
# (`utils/zeroconf_singleton` kaldırma API'si sunmuyor), dolayısıyla guard kalkarsa bir arayüz
# değişimi KASITLI OLARAK KALDIRILMIŞ servisi DİRİLTİR — kardeş dosya bunu açıkça yasaklıyor
# (`mdns_service.py:222-223`, "Audit P3: stop() sonrası callback re-publish etmesin").
_mdns_started = False


def get_api_port(default: int = 8000) -> int:
    """Backend'in GERÇEKTEN dinlediği API portu.

    ⚠️ DENETİM 2026-08-17: keşif kanallarının üçü de portu `8000` olarak SABİT yayınlıyordu, oysa
    gerçek port dinamik. 8000 meşgulken telefon yanlış porta bağlanıyor ve `checkHealth` onu
    eleyince keşif merdiveni bir sonraki basamağa düşüyor (ilk bağlanma saniyelerden ~70 sn'ye).
    Tek gerçek kaynak `PEMF_API_PORT`: `backend_service.publish_bind_port` yazar, launcher da
    kurulum env'inde verir.
    ⚠️ FONKSİYON, modül SABİTİ DEĞİL: sabit olsa import anında donardı ve env sonradan yazıldığı
    için 8000'de kalırdı.
    ⚠️ Bilinmiyor/bozuksa `8000` döner — launcher `DEFAULT_PORT` ve Supabase RPC'sinin
    `coalesce(p_api_port, 8000)` sözleşmesi KORUNUR."""
    try:
        p = int(str(os.environ.get("PEMF_API_PORT", "")).strip())
    except Exception:
        return default
    return p if 1 <= p <= 65535 else default


def _mdns_ad(taban: str = "PEMF-Vet") -> str:
    """mDNS servis adı: taban ad + cihaz kimliğinden türetilmiş KARARLI benzersiz sonek.

    ⚠️ DENETİM 2026-08-28 #08 — SABİT AD ÇAKIŞIYOR. Aynı ağdaki iki cihaz `PEMF-Vet` adını
    birden iddia edince `register_service` `NonUniqueNameException` atıyor (gerçek LAN'da
    ölçüldü). Kardeş modül `services/mdns_service.py` bu çakışmayı zaten sonekle çözüyordu;
    bu yol çözmüyordu — asimetri belgelenmemişti.

    ⚠️ `allow_name_change=True` YETERSİZ (ölçüldü): zeroconf yalnız `info.name`i değiştirir
    (`_core.py:559-563`), `server=` hostname'i (A kaydı) HÂLÂ çakışır.

    ⚠️ HAM device_id YAYINLANMAZ: `get_unique_device_id()` MAC'in ondalık hâlidir ve
    `system_router` onu uzak isteklere BİLEREK vermez (tenant anahtarı). mDNS LAN'a multicast
    ettiği için kimliğin kendisi değil, SHA1 özetinin 6 hanesi yayınlanır (geri döndürülemez).

    ⚠️ KARARLI olmak zorunda: her açılışta değişen ad ağda çöp kayıt biriktirir. device_id
    dosyada kalıcı olduğu için aynı makinede hep aynı ad üretilir.

    ⚠️ HİÇBİR KOŞULDA PATLAMAZ: sonek türetilemezse taban ada düşer (bugünkü davranış).
    """
    import hashlib

    taban = (os.environ.get("PEMF_DEVICE_NAME") or taban).strip() or "PEMF-Vet"
    try:
        from utils.path_utils import get_unique_device_id

        cekirdek = str(get_unique_device_id() or "")
        if cekirdek:
            sonek = hashlib.sha1(cekirdek.encode("utf-8")).hexdigest()[:6]
            return f"{taban}-{sonek}"
    except Exception:
        pass
    try:
        return f"{taban}-{hashlib.sha1(socket.gethostname().encode('utf-8')).hexdigest()[:6]}"
    except Exception:
        return taban


def _hata_metni(e: BaseException) -> str:
    """İstisnayı OKUNABİLİR biçimde anlat.

    ⚠️ DENETİM #08: zeroconf 0.148'de `NonUniqueNameException` dâhil tüm `Error` alt
    sınıflarının `str(e)` değeri BOŞ. Canlı logda `mDNS başlatılamadı:` satırı 12 kez geçiyor
    ve 12'sinin de mesajı boştu — destek, ad çakışması mı `EventLoopBlocked` mi ayırt
    edemiyordu. Tip adı her zaman yazılır."""
    metin = str(e).strip()
    return f"{type(e).__name__}: {metin}" if metin else type(e).__name__


def _build_info(local_ip: str, port: int, device_name: str):
    """_pemfvet ServiceInfo'yu güncel IP ile kurar (start_mdns + re-register ortak kullanır)."""
    import socket as _socket

    from zeroconf import ServiceInfo

    return ServiceInfo(
        type_="_pemfvet._tcp.local.",
        name=f"{device_name}._pemfvet._tcp.local.",
        addresses=[_socket.inet_aton(local_ip)],
        port=port,
        properties={b"version": b"1.5", b"api": b"/api", b"ws": b"/ws"},
        server=f"{device_name}.local.",
    )


def _reregister() -> None:
    """Zeroconf arayüz/IP değişimiyle YENİDEN yaratıldığında _pemfvet servisini yeni instance'a
    GÜNCEL IP ile re-register eder (zeroconf_singleton.ensure_interfaces_current çağırır). Bu ayrıca
    auto_discovery'nin eskiden HİÇ olmayan IP-değişim yeniden-kaydını da kapatır. start_mdns
    çağrılmadıysa no-op."""
    global _zeroconf_instance, _mdns_service_info
    if not _mdns_started:
        # `start_mdns` çağrılmadı ya da `stop_mdns` sonrası: kasıtlı-kaldırılan servisi CANLANDIRMA.
        return
    try:
        from utils.zeroconf_singleton import get_shared_zeroconf

        ip = _get_local_ip()
        # Audit P3: loopback (127.*) ServiceInfo YAYINLAMA — telefon/ESP 127.0.0.1'i çözüp kendi
        # loopback'ine gider (sessiz başarısız). Gerçek LAN IP yoksa kaydı ATLA (sonraki tur tekrar dener).
        if not ip or ip.startswith("127."):
            logger.debug("mDNS re-register atlandı: geçerli LAN IP yok (ip=%r).", ip)
            return
        info = _build_info(ip, _mdns_port, _mdns_device_name)
        zc = get_shared_zeroconf()
        zc.register_service(info)
        _zeroconf_instance = zc
        _mdns_service_info = info
        logger.info("mDNS (_pemfvet) yeni arayüzlere re-register edildi: %s", ip)
    except Exception as e:
        logger.warning("_pemfvet re-register hatası: %s", _hata_metni(e))


def _get_local_ip() -> str:
    """Makinenin yerel ağ IP adresini tespit eder.

    ⚠️ İKİ AŞAMALI (denetim 2026-08-17): UDP `connect` DEFAULT ROUTE gerektirir. Offline klinikte
    ya da hotspot-only kurulumda (bkz. `scripts/start_hotspot.ps1`, `HOTSPOT_SUBNET`) default route
    YOKTUR; eskiden burada kalıcı olarak `127.0.0.1` dönülüyor ve `_pemfvet` HİÇ yayınlanmıyordu.
    Üstelik `zeroconf_singleton.ensure_interfaces_current` arayüz KÜMESİ değişmediği için
    callback'leri hiç çağırmıyordu → re-register de kurtarmıyordu.
    İkinci aşama, alt sistemin ZATEN kullandığı yolu kullanır: `ifaddr` gerçek arayüz adresini
    ROTA OLMADAN da görür (`_bound_ips` böyle kuruluyor). Loopback'i YAYINLAMAMA kararı korunur —
    aday bulunamazsa yine `127.0.0.1` dönülür ve çağıranların 127.* guard'ı kaydı atlar."""
    ip = ""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
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


def start_mdns(port: int = 8000, device_name: str = "PEMF-Vet") -> bool:
    """
    mDNS servisi başlatır. Aynı ağdaki telefonlar bu servis üzerinden
    LattePanda'yı otomatik keşfedebilir.
    Servis tipi: _pemfvet._tcp.local.
    """
    global _zeroconf_instance, _mdns_service_info, _mdns_port, _mdns_device_name, _mdns_started
    try:
        from utils.zeroconf_singleton import add_reregister_callback, get_shared_zeroconf

        # Denetim #08: sabit ad yerine cihaza özgü KARARLI ad — aynı ağdaki ikinci cihaz
        # artık çakışmıyor. Çağıran hâlâ "PEMF-Vet" geçiyor; benzersizleştirme burada yapılır
        # ki tüm çağrı yolları (api_server + testler) aynı davranışı alsın.
        device_name = _mdns_ad(device_name)
        _mdns_port, _mdns_device_name = port, device_name
        local_ip = _get_local_ip()

        zc = get_shared_zeroconf()  # paylasilan TEK Zeroconf (MDNSService ile ayni instance → 5343 cakismasi yok)
        # #32: loopback (127.*) IP'yi mDNS'e YAYINLAMA (telefon/ESP 127.0.0.1'i çözüp kendi loopback'ine
        # gider → sessiz başarısız). Gerçek LAN IP yoksa İLK kaydı ATLA; add_reregister_callback ile
        # arayüz/IP gelince otomatik kaydolur (_reregister aynı 127.* guard'ına sahip).
        if local_ip and not local_ip.startswith("127."):
            info = _build_info(local_ip, port, device_name)
            # ⚠️ DENETİM #08 — SIRA KRİTİK. Eskiden `register_service` burada patlarsa
            # (`NonUniqueNameException`) fonksiyon TEK dıştaki except'e düşüyor, dolayısıyla
            # `_mdns_started = True` ve `add_reregister_callback` ATLANIYORDU. Sonuç:
            # `_reregister` süreç ömrü boyunca guard'a takılıp no-op oluyor VE callback zaten
            # hiç kaydedilmemiş oluyordu → arayüz/IP değişiminde de toparlanma YOK.
            # Artık kayıt hatası YUTULMAZ ama akışı kesmez: bayrak + callback kurulur, böylece
            # sonraki arayüz olayında yeniden denenir.
            try:
                zc.register_service(info)
                _zeroconf_instance = zc
                _mdns_service_info = info
            except Exception as _kayit_hatasi:
                _zeroconf_instance = zc
                logger.warning(
                    "mDNS ilk kaydı başarısız (%s) — ad=%r. Arayüz değişiminde yeniden denenecek.",
                    _hata_metni(_kayit_hatasi),
                    device_name,
                )
        else:
            _zeroconf_instance = zc
            logger.info("mDNS ilk-kayıt atlandı: geçerli LAN IP yok (ip=%r) — arayüz gelince kaydolacak.", local_ip)
        _mdns_started = True  # ⚠️ callback KAYDINDAN ÖNCE: kayıt anında tetiklenirse guard geçmeli
        add_reregister_callback(_reregister)  # arayüz/IP değişiminde yeni instance'a otomatik re-register

        logger.info("mDNS servisi başlatıldı: %s:%d (%s)", local_ip, port, device_name)
        return True
    except Exception as e:
        # Denetim #08: zeroconf istisnalarinin str() degeri BOS — tip adi olmadan
        # destek hangi hatayi aldigini ayirt edemiyordu (canli logda 12/12 bos satir).
        logger.warning("mDNS başlatılamadı: %s", _hata_metni(e))
        return False


def stop_mdns() -> None:
    """mDNS servisini durdurur."""
    global _zeroconf_instance, _mdns_service_info, _mdns_started
    _mdns_started = False  # bundan sonra bir arayüz değişimi servisi DİRİLTMEZ
    if _zeroconf_instance and _mdns_service_info:
        try:
            _zeroconf_instance.unregister_service(
                _mdns_service_info
            )  # ortak Zeroconf'u CLOSE ETME (MDNSService da kullanir)
        except Exception:
            pass
    _zeroconf_instance = None
    _mdns_service_info = None
    logger.info("mDNS servisi durduruldu.")
