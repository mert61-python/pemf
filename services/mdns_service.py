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

import socket
import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

# mDNS servis adı — tüm cihazlar bu adı arar
MDNS_SERVICE_NAME = "PEMF-Gateway"
MDNS_SERVICE_TYPE = "_mqtt._tcp.local."
MDNS_HOST_NAME = "pemf-gateway"   # pemf-gateway.local olarak çözünür


def _get_local_ip() -> str:
    """Aktif ağ arayüzünün IP adresini döndürür."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
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
            from zeroconf import Zeroconf, ServiceInfo  # noqa: F401 — availability check (asıl kayıt _ip_monitor_loop'ta)
        except ImportError:
            logger.error(
                "zeroconf kütüphanesi bulunamadı. "
                "Kurulum: pip install zeroconf"
            )
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
                self._zeroconf.unregister_service(self._service_info)  # ortak Zeroconf'u CLOSE ETME (auto_discovery da kullanir)
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

    def _ip_monitor_loop(self):
        """IP adresi değişirse mDNS kaydını günceller. İlk kaydı da burada yapar."""
        try:
            try:
                from zeroconf._exceptions import NonUniqueNameException
            except ImportError:
                class NonUniqueNameException(Exception): pass

            local_ip = self._ip_override or _get_local_ip()
            self._last_ip = local_ip
            from utils.zeroconf_singleton import get_shared_zeroconf
            self._zeroconf = get_shared_zeroconf()  # paylasilan TEK Zeroconf (cift-instance 5353 cakismasi yok)
            self._service_info = self._build_service_info(local_ip)
            
            try:
                self._zeroconf.register_service(self._service_info)
            except Exception as e:
                if 'NonUniqueNameException' in str(type(e)):
                    logger.warning("mDNS adı çakıştı, random suffix ekleniyor...")
                    import random, string
                    suffix = ''.join(random.choices(string.ascii_letters + string.digits, k=4))
                    self._service_name = f"{self._service_name}-{suffix}"
                    self._service_info = self._build_service_info(local_ip)
                    self._zeroconf.register_service(self._service_info)
                else:
                    raise e
                    
            logger.info(
                f"✓ mDNS yayını başlatıldı: {MDNS_HOST_NAME}.local "
                f"→ {local_ip}:{self._mqtt_port}"
            )
        except Exception:
            logger.exception("mDNS arka plan başlatma hatası detayı:")
            self._running = False
            return

        while self._running:
            try:
                time.sleep(30)  # 30 saniyede bir kontrol
                if not self._running:
                    break

                current_ip = _get_local_ip()
                if current_ip != self._last_ip:
                    logger.info(
                        f"IP değişti: {self._last_ip} → {current_ip}. "
                        "mDNS kaydı güncelleniyor..."
                    )
                    # Yeniden kaydet
                    try:
                        if self._zeroconf and self._service_info:
                            self._zeroconf.unregister_service(self._service_info)
                        self._service_info = self._build_service_info(current_ip)
                        self._zeroconf.register_service(self._service_info)
                        self._last_ip = current_ip
                        logger.info(f"✓ mDNS güncellendi: pemf-gateway.local → {current_ip}")
                    except Exception as e:
                        logger.error(f"mDNS güncelleme hatası: {e}")

            except Exception as e:
                if self._running:
                    logger.error(f"IP monitor hatası: {e}")


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
