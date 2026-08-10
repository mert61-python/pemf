# Author: mertaygn, cglrgrkn
"""Process-genelinde TEK paylaşılan Zeroconf örneği.

python-zeroconf host başına TEK instance önerir. Bu backend'de İKİ ayrı yayıncı vardı:
  - MosquittoSupervisor → MDNSService  (_mqtt._tcp, 1883)
  - api_server startup   → auto_discovery (_pemfvet._tcp, 8000)
Her biri kendi `Zeroconf()`'unu açıyordu → UDP 5353'te iki ayrı multicast soket/responder;
birinin `close()`'u diğerinin soketini bozabiliyor, kayıt (record) flapping'i / aralıklı
"cihaz bulunamadı" oluşturabiliyordu. Artık ikisi de bu paylaşılan örnek üzerinde KENDİ
ServiceInfo'sunu register/unregister eder; ortak Zeroconf yalnızca process kapanışında kapatılır.
"""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_zc = None
_bound_ips: list = []  # _zc'nin şu an bağlı olduğu gerçek-LAN IP'leri (arayüz-seti izlemek için)
_reregister_cbs: list = []  # Zeroconf yeniden-yaratıldığında servislerini re-register eden yayıncı callback'leri


def add_reregister_callback(cb) -> None:
    """Bir yayıncı (mdns_service / auto_discovery), Zeroconf arayüz-değişimiyle YENİDEN yaratıldığında
    kendi ServiceInfo'sunu yeni instance'a re-register eden bir callback kaydeder. `ensure_interfaces_current`
    recreate sonrası bu callback'leri çağırır → servisler yeni arayüz-soketlerine geri konur."""
    with _lock:
        if cb not in _reregister_cbs:
            _reregister_cbs.append(cb)


def _real_lan_ipv4s() -> list:
    """GERÇEK LAN IPv4 adreslerini döndürür (WiFi + hotspot + Ethernet); loopback (127.*) ve
    APIPA/link-local (169.254.*) HARİÇ.

    NEDEN (çok-homed Windows mDNS bug'ı): Zeroconf'un varsayılanı `InterfaceChoice.All`. Cihazda
    Wi-Fi (ör. 192.168.1.43, metrik 40) + AKTİF hotspot (192.168.137.1, metrik 25) + ölü Ethernet
    (169.254.*, metrik 5) aynı anda varken, Windows istenmeyen mDNS multicast'ini EN DÜŞÜK-metrikli
    (çoğu zaman hotspot ya da ölü arayüz) üzerinden yolluyordu → ev-WiFi'sindeki telefon cihazın
    duyurusunu ALMIYOR ("aynı WiFi'de otomatik keşif" bozuluyor). Ölü 169.254 arayüzleri de
    InterfaceChoice.All enumerasyonunu bozabiliyor. Çözüm: yalnız GERÇEK arayüz IP'lerine AÇIKÇA
    bağla → Zeroconf her birine ayrı soket açıp mDNS'i hepsine yollar; OS-metriğine güvenmez →
    hem ev-WiFi hem hotspot'ta AYNI ANDA keşif garanti.
    """
    ips: list = []
    try:
        import ifaddr  # python-zeroconf ile birlikte gelen bağımlılık (ekstra dep yok)

        for adapter in ifaddr.get_adapters():
            for ip in adapter.ips:
                if getattr(ip, "is_IPv4", False):
                    addr = ip.ip
                    if (
                        isinstance(addr, str)
                        and addr != "0.0.0.0"
                        and not addr.startswith(("127.", "169.254."))
                        and addr not in ips
                    ):
                        ips.append(addr)
    except Exception as e:
        logger.debug("ifaddr ile arayüz IP'leri sayılamadı (%s) → InterfaceChoice.All'a düşülecek", e)
    return ips


def get_shared_zeroconf():
    """Paylaşılan Zeroconf örneğini döndürür (lazy, thread-safe). Yayıncılar bunun üzerinde
    kendi register_service/unregister_service'lerini yapar; close ETMEZ.

    Gerçek LAN arayüzlerine AÇIK bağlanır (çok-homed Windows mDNS düzeltmesi; bkz. _real_lan_ipv4s).
    Herhangi bir hata / IP bulunamazsa GÜVENLİ varsayılana (InterfaceChoice.All) düşer — regresyon yok.
    """
    global _zc, _bound_ips
    with _lock:
        if _zc is None:
            from zeroconf import Zeroconf

            ips = _real_lan_ipv4s()
            if ips:
                try:
                    _zc = Zeroconf(interfaces=ips)
                    _bound_ips = ips
                    logger.info("Zeroconf gerçek LAN arayüzlerine açık bağlandı: %s", ips)
                except Exception as e:
                    logger.warning("Zeroconf açık-arayüz bağlama başarısız (%s) → varsayılan (All)", e)
                    _zc = Zeroconf()
                    _bound_ips = []
            else:
                _zc = Zeroconf()
                _bound_ips = []
                logger.info("Zeroconf varsayılan (InterfaceChoice.All) ile başlatıldı (gerçek IP bulunamadı)")
        return _zc


def ensure_interfaces_current() -> bool:
    """Gerçek-LAN arayüz seti (WiFi/hotspot/Ethernet IP'leri) değiştiyse paylaşılan Zeroconf'u YENİDEN
    yaratıp yeni arayüzlere bağlar ve kayıtlı yayıncıların re-register callback'lerini çağırır.

    NEDEN recreate: python-zeroconf 0.149'da `update_interfaces()` YOK. Açık `interfaces=[ip,...]` ile
    bağlı Zeroconf, WiFi IP'si DHCP ile değişirse eski-IP'ye bağlı ölü sokete sahip olur → yeni-IP'de
    keşif bozulur. Arayüz-seti değişimini (birincil-IP değişimini de KAPSAR) yakalayıp yeniden-bağlarız.
    30sn'lik mDNS IP-monitör döngüsünden çağrılır. Değişiklik yoksa no-op. Döndürür: rebind oldu mu."""
    global _zc, _bound_ips
    ips = _real_lan_ipv4s()
    with _lock:
        if _zc is None or not ips or set(ips) == set(_bound_ips):
            return False
        from zeroconf import Zeroconf

        old_ips = list(_bound_ips)
        try:
            _zc.close()
        except Exception:
            pass
        try:
            _zc = Zeroconf(interfaces=ips)
            _bound_ips = ips
        except Exception as e:
            logger.warning("Zeroconf yeniden-yaratma (interfaces=%s) başarısız (%s) → varsayılan (All)", ips, e)
            _zc = Zeroconf()
            _bound_ips = []
        cbs = list(_reregister_cbs)
    # Callback'ler get_shared_zeroconf() çağırır → KİLİT DIŞINDA çalıştır (yeniden-giriş/deadlock önle).
    logger.info(
        "LAN arayüz seti değişti %s → %s; Zeroconf yeniden bağlandı, %d servis re-register ediliyor",
        old_ips,
        _bound_ips,
        len(cbs),
    )
    for cb in cbs:
        try:
            cb()
        except Exception:
            logger.warning("Zeroconf re-register callback hatası", exc_info=True)
    return True


def close_shared_zeroconf() -> None:
    """Yalnızca process/servis kapanışında çağrılır — paylaşılan Zeroconf soketlerini kapatır."""
    global _zc, _bound_ips
    with _lock:
        if _zc is not None:
            try:
                _zc.close()
            except Exception:
                pass
            _zc = None
            _bound_ips = []
