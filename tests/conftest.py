# Author: mertaygn, cglrgrkn
"""pytest ortak ayarı — guii kökünü import yoluna ekler ve izole temp app_data sağlar."""

import os
import sys
import tempfile
import threading
from pathlib import Path

import pytest

_GUII_ROOT = Path(__file__).resolve().parent.parent
if str(_GUII_ROOT) not in sys.path:
    sys.path.insert(0, str(_GUII_ROOT))

# ⚠️ URUN PAKETLERI `apps/backend/` ALTINDA (2026-09-18, klasor duzeni F4).
# Import adlari degismedi (`from utils.x import y`) ama o dizin yola EKLENMELI.
# Buraya konmasi 202 test dosyasinin hepsini kapsar: onlarin kendi
# `sys.path.insert(kok)` satirlari ARTIK YETMEZ, kok paketleri tasimiyor.
_BACKEND_KOKU = _GUII_ROOT / "apps" / "backend"
if str(_BACKEND_KOKU) not in sys.path:
    sys.path.insert(0, str(_BACKEND_KOKU))


# ─────────────────────────────────────────────────────────────────────────────
# TOPLAMA-ZAMANI KORUMASI (fixture'lardan ÖNCE — MODÜL SEVİYESİNDE ÇALIŞIR)
# ─────────────────────────────────────────────────────────────────────────────
# ⚠️ DENETİM 2026-08-15: aşağıdaki `_gercek_kurulumu_koru` fixture'ı YETMİYOR, çünkü pytest
# test modüllerini TOPLAMA sırasında import eder ve bu, hiçbir fixture çalışmadan ÖNCE olur.
# Bazı test modülleri modül seviyesinde üretim modülü import ediyor; zincir şuraya varıyor:
#     tests/test_patient_encryption.py (import)   [2026-08-15 ölçümü; D0Ö.01'den beri bu dosya
#       toplamada import ETMİYOR — aynı zincir ör. tests/test_esp_ack_roundtrip.py'nin modül düzeyi
#       `servers.api_server` import'u → `database.patient_database` üzerinden sürer]
#       → apps/backend/database/patient_database.py  (modül seviyesi)
#         → pemf_gui/config.py:346      (modül seviyesi SINGLETON)
#           → Config.__init__ → _get_or_create_key → secrets_manager.get_secret
# Yani PUAN: sadece `import` etmek bile GERÇEK `%APPDATA%\PEMF_GUI` içinde bir şifreleme
# anahtarı (`pemf_secrets.json`) ÜRETİP DİSKE YAZIYORDU. Anahtar orada belirince canlı
# (düz-metin) klinik veritabanı bir sonraki açılışta göçe girer, `.plain.bak` artığı bırakır
# ve "file is not a database" ile açılamaz hale gelir — yani süit, kurulu bir makinede HASTA
# VERİSİNE dokunuyordu. Ölçüldü: fixture düzeltmesinden SONRA bile 7 test sızdırıyordu.
#
# ÇÖZÜM: izolasyonu süreç başına, conftest IMPORT EDİLİRKEN kur. conftest her zaman test
# modüllerinden ÖNCE import edilir → import yan etkileri de yakalanır. Test başına izolasyon
# (aşağıdaki fixture) bunun ÜSTÜNE biner; bu yalnızca taban güvenliktir.
# (Regresyonu `test_veri_dizini_izolasyonu.py` kilitliyor.)
_OTURUM_IZOLE = Path(tempfile.mkdtemp(prefix="pemf_test_veri_"))
(_OTURUM_IZOLE / "PEMF_GUI").mkdir(parents=True, exist_ok=True)
# ⚠️ D0Ö.05 (B-10.51): ezilmeden ÖNCEKİ gerçek değer saklanır — `test_veri_dizini_izolasyonu.py`
# "gerçek kök" sentinelini BURADAN türetir. Test modülü toplanırken APPDATA ZATEN ezilmiştir;
# oradan okunan değer oturum temp kökünü gösterir ve sentinel gerçek hasta dizinini GÖRMEZ.
_ORIJINAL_APPDATA = os.environ.get("APPDATA")
os.environ["PEMF_DATA_DIR"] = str(_OTURUM_IZOLE)
os.environ["APPDATA"] = str(_OTURUM_IZOLE)
# ⚠️ DENETİM 2026-08-28 #02: `device_registry_secret` artık VERİ KÖKÜNÜN DIŞINDA, makine
# kapsamlı bir dosyada tutuluyor (`apps/backend/utils/secrets_manager._cihaz_kimlik_deposu`). O yol
# `PEMF_DATA_DIR`e BAKMAZ → yukarıdaki izolasyon onu KAPSAMAZ. ÖLÇÜLDÜ: süit, gerçek
# `C:\ProgramData\PEMF_System\device_identity.json` dosyasına TEST SIRRI yazdı ve
# oradaki değer klinik cihazınkinden FARKLIYDI. Sonucu sinsi: veri kökü bir gün
# yenilendiğinde o yanlış sır kullanılır ve düzeltilen `secret_mismatch` arızası GERİ GELİR.
# (Aynı sınıf: `test_veri_dizini_izolasyonu.py`nin kilitlediği eski sızıntı.)
os.environ["PEMF_DEVICE_IDENTITY_DIR"] = str(_OTURUM_IZOLE / "makine_kimligi")
# Scratch CPN warmup thread'i testte ASLA başlamasın (CI ölçümü 2026-08-26, exit 134:
# daemon thread + interpreter kapanışı yarışı — app.py'de find_spec ön-kontrolü de var,
# bu satır çift emniyet + testlerin startup davranışını deterministik kılar).
os.environ.setdefault("PEMF_SCRATCH_WARMUP", "0")
# ⚠️ D0Ö.10 (B-10.105) — aynı sınıf: `ai-warmup` daemon'ı (ses hattı + torch importu) test bitince
# yaşayıp SONRAKİ testlerle yarışıyordu (A9). Isıtmayı sınayan testler bayrağı kendileri siler/verir.
# ZORLA (setdefault DEĞİL): dış kabuk/CI `PEMF_AI_WARMUP=1` verse de süit ısıtmasız koşar (D0Ö.11 deseni).
os.environ["PEMF_AI_WARMUP"] = "0"

# ⚠️ D0Ö.11 (B-10.222 = DENETIM-12 P1) — `PEMF_SIMULATE` TEST MODÜLLERİNDE DEĞİL, BURADA TEK YERDE.
# 72 test modülü modül gövdesinde yazıyordu (16 `setdefault('1')` + 56 `pop`); değeri TOPLAMA SIRASI
# belirliyordu: tam süitte toplama sonunda YOK, tek dosya koşumunda '1' → aynı test iki ayrı ortamda
# koşuyordu (ürün lifespan'de okuyup hw-sim thread'ini başlatır; o thread `stm='online'` yazar).
# Artık süreç başında TEK normalizasyon: YOK (tam süitin fiilî değeri; dış kabuk/CI '1' ya da ''
# verse de — silinen dolu değer rapor başlığında söylenir). ⚠️ Sanal donanımı ENV İLE İSTEME: lifespan
# hw-sim'i süreç başına BİR KEZ başlatırdı ve o daemon durdurulamaz (D0Ö.10'dan beri conftest arka plan
# başlatıcısını engelliyor). Sim davranışı gereken test döngüyü doğrudan ve sınırlı turla koşturur
# (test_sim_GERCEGI_ASMAZ.py deseni) ya da canlı durumu elle kurar. Toplama sonundaki değer kaydedilir;
# her testten sonra env'de PEMF_SIMULATE ya da canlı `hw-sim` kalırsa o test KIRMIZI (çalışma-anı
# sızıntısı — modül düzeyi taramanın görmediği fixture/test gövdesi yazımları).
# Kapı: tests/test_pemf_simulate_tek_kaynak.py
_PEMF_SIMULATE_DISARIDAN = os.environ.pop("PEMF_SIMULATE", None)
_PEMF_SIMULATE_TOPLAMA_SONU: list = []
_HW_SIM_BILDIRILDI: list = []


def pytest_collection_finish(session):
    _PEMF_SIMULATE_TOPLAMA_SONU.append(os.environ.get("PEMF_SIMULATE"))


def pytest_report_header(config):
    if _PEMF_SIMULATE_DISARIDAN:
        return f"UYARI: dis ortamdan PEMF_SIMULATE={_PEMF_SIMULATE_DISARIDAN!r} geldi; conftest SILDI (D0O.11)"
    return None


def pytest_configure(config):
    # Başlık `-q`/`--no-header` altında basılmaz → silme uyarı özetinde de görünsün (her kipte).
    if _PEMF_SIMULATE_DISARIDAN:
        config.issue_config_time_warning(
            pytest.PytestConfigWarning(
                f"dis ortamdan PEMF_SIMULATE={_PEMF_SIMULATE_DISARIDAN!r} geldi; conftest SILDI (D0O.11)"
            ),
            stacklevel=2,
        )


def _canli_hw_sim() -> list:
    """Adı `hw-sim` olan YA DA hedefi ürünün sanal donanım döngüsü olan canlı thread'ler (çıpa ada değil
    GERÇEK çağrıya: döngü başka adla başlatılsa da görünür)."""
    hedef = getattr(sys.modules.get("servers.api_server"), "_hardware_simulation_loop", None)
    return [
        t.name
        for t in threading.enumerate()
        if t.name == "hw-sim" or (hedef is not None and getattr(t, "_target", None) is hedef)
    ]


@pytest.fixture(autouse=True)
def _pemf_simulate_sizmaz():
    # Kurulumda zaten varsa suç BU testin değil: toplama (modül düzeyi yazım) ya da önceki bir kapsamlı
    # fixture bıraktı — ayrı iletiyle bildir (teşhis ilgisiz testin üstüne kalmasın).
    once = os.environ.pop("PEMF_SIMULATE", None)
    if once is not None:
        pytest.fail(f"PEMF_SIMULATE={once!r} bu test BAŞLAMADAN vardı — toplama/önceki bir fixture bıraktı (D0Ö.11)")
    yield
    kalan = os.environ.pop("PEMF_SIMULATE", None)  # sonraki testlere SIZMASIN
    sim = _canli_hw_sim() if not _HW_SIM_BILDIRILDI else []
    if sim:
        _HW_SIM_BILDIRILDI.append(sim)  # daemon durdurulamaz: bir kez bildir, zincirleme kırmızı üretme
    if kalan is not None or sim:
        pytest.fail(f"bu test PEMF_SIMULATE={kalan!r} bıraktı / canlı hw-sim: {sim} — çalışma-anı sızıntısı (D0Ö.11)")


# ⚠️ D0Ö.02 (B-3.6) — GERÇEK KİMLİK KASASI SÜİTTE python-keyring ÜZERİNDEN OKUNMAZ/YAZILMAZ.
# ÖLÇÜLDÜ: tam süit gerçek Windows kasasına 1603 okuma yapıyordu ve sahibin kasasında
# `PEMF_GUI/sqlcipher_key` VAR → gerçek at-rest anahtarı test DB'lerine göçüyor, kopyaları
# %TEMP%'te birikiyor, sonuçlar makinenin kasa durumuna bağlı kalıyordu (B-3.84 bunun kurbanıydı).
# (1) Süreç-geneli arka uç null: env + `set_keyring` birlikte — env TEK BAŞINA YETMEZ, keyring daha
#     önce import edilip arka ucunu seçtiyse env'e bir daha bakmaz. ⚠️ ENV SATIRI TAŞIYICIDIR:
#     conftest YÜKLEMEYEN alt süreçler (ör. test_recovery_reachable'ın `backend_service` koşumu)
#     arka ucu YALNIZ miras aldıkları env'den seçer.
# (2) Gerçek Windows arka ucu SAYAN bir engelle sarılır: bir test kendi arka ucunu kurup kasaya
#     uzanırsa çağrı düşer, `_GERCEK_KASA_CAGRILARI`'na yazılır ve o test kırmızı olur.
# ⚠️ KAPSAM: yalnız python-keyring kanalı. Kasaya `cmdkey` ALT SÜRECİYLE dokunan teardown testleri
#    (test_teardown_kimlik_dogrulama.py, test_teardown_system_kasasi.py — yalnız geçici PEMF_GATE_*
#    kayıtları yazıp siler, kasayı listeler) bu bloğun DIŞINDADIR; açık bulgu (DUZELTME-D0O.md).
# Kapı: tests/test_kasa_yalitimi.py
os.environ["PYTHON_KEYRING_BACKEND"] = "keyring.backends.null.Keyring"
_GERCEK_KASA_CAGRILARI: list = []
try:
    import keyring as _keyring
    from keyring.backends import null as _keyring_null

    _keyring.set_keyring(_keyring_null.Keyring())
except Exception:  # keyring kurulu değilse ürün de kasaya ulaşamaz
    pass
try:
    from keyring.backends import Windows as _keyring_windows
    from keyring.errors import KeyringError as _KeyringError

    def _gercek_kasa_engeli(ad):
        def _engel(self, *args, **kwargs):
            _GERCEK_KASA_CAGRILARI.append((ad, args[:2]))
            raise _KeyringError(f"TEST SÜİTİ GERÇEK KİMLİK KASASINA UZANDI (engellendi): {ad}{args[:2]!r}")

        return _engel

    for _ad in ("get_password", "set_password", "delete_password", "get_credential"):
        if hasattr(_keyring_windows.WinVaultKeyring, _ad):
            setattr(_keyring_windows.WinVaultKeyring, _ad, _gercek_kasa_engeli(_ad))
except Exception:  # Windows arka ucu yüklenemiyorsa (Windows dışı) sarılacak bir şey yok
    pass


@pytest.fixture(autouse=True)
def _gercek_kasa_kaydedici():
    """D0Ö.02: bu testte gerçek kasaya uzanan (engellenen) çağrı varsa test KIRMIZI olur."""
    once = len(_GERCEK_KASA_CAGRILARI)
    yield
    yeni = _GERCEK_KASA_CAGRILARI[once:]
    if yeni:
        pytest.fail(f"Bu test GERÇEK kimlik kasasına uzandı (engellendi, D0Ö.02): {yeni}")


@pytest.fixture(autouse=True)
def _estop_mandali_sizmaz():
    """D1.81 · Y4: acil durdurma MANDALI süreç-geneldir (ürün böyle olmalı: sıfırlanana dek hiçbir START geçmez).
    Testler arası SIZMASIN — E-stop yapan bir testten sonra ilgisiz bir testin START'ı reddedilmesin. Her testin
    başında ve sonunda operatörün 'Sıfırla'sıyla AYNI işlev çağrılır (nesil artmaya devam eder; bayat niyetler
    bayat kalır)."""
    try:
        from utils import estop_mandali
    except ImportError:
        yield
        return
    estop_mandali.sifirla("pytest-izolasyon")
    yield
    estop_mandali.sifirla("pytest-izolasyon")


# ⚠️ D0Ö.07 (B-10.9) — SÜİT AĞA ÇIKMAZ (TCP connect, UDP sendto, DNS). ÖLÇÜLDÜ:
# `data/cloud_mqtt_provision.json` (git'e girmez) bu makinede VAR; aynayı stub'lamayan E-stop testleri
# `_estop_cloud_mirror` üzerinden GERÇEK (üretim) bulut broker'ına gerçek kimlikle TLS + STOP yayını
# DENİYORDU (4+4 TLS ClientHello). E-stop aynasının ÜRÜN kodu DEĞİŞMEZ (Ö.4-Y8); yalnız test aparatı:
# (1) Provizyon var olmayan bir tmp yola yönlenir ve `PEMF_MQTT_CLOUD_*` env'leri (provizyondan ÖNCE
#     okunur) silinir → ayna süitte sessizce devre dışı. ⚠️ Aynı değişken `make_cloud_provision.py`'nin
#     ÇIKTI yoludur: o yolda dosya belirirse `_bulut_provizyonu_yok_kalir` o testi KIRMIZI yapar.
# (2) Ağ bekçisi: loopback dışı connect/connect_ex/sendto ve DNS (getaddrinfo; gethostbyname* — yerel
#     makine adı serbest) ENGELLENİR. Loopback'te yalnız bu süreçte bir kez bind edilmiş port
#     NUMARALARINA izin (süreç boyunca tutulur, budanmaz); sahibin servis portları (8000 backend,
#     1883 broker, …) ne bağlanılır ne bind edilir — sahip makinesinde 127.0.0.1:8000'de gerçek
#     backend, 1883'te gerçek broker koşabilir; bind etmek canlı istekleri ELE GEÇİRİR (ölçülmüş tuzak).
#     Engellenen her deneme `_AG_ENGELLENEN`'e yazılır. Katlar: Python sarmalayıcıları + audit hook
#     (C düzeyi `_socket`) + asyncio IocpProactor.connect/sendto (Windows'ta ConnectEx/WSASendTo
#     `socket.*`'a uğramaz, audit olayı da üretmez — bu yama kurulamazsa conftest DÜŞER).
# ⚠️ KAPSAM: yalnız bu pytest süreci; alt süreçler bekçiyi MİRAS ALMAZ (yalnız env'i alır).
# Kapı: tests/test_ag_yalitimi.py
os.environ["PEMF_CLOUD_PROVISION_PATH"] = str(_OTURUM_IZOLE / "YOK_cloud_mqtt_provision.json")
for _ad in ("PEMF_MQTT_CLOUD_HOST", "PEMF_MQTT_CLOUD_PORT", "PEMF_MQTT_CLOUD_USER", "PEMF_MQTT_CLOUD_PASS"):
    os.environ.pop(_ad, None)

import ipaddress as _ipaddress
import socket as _socket

_AG_ENGELLENEN: list = []
_AG_ACILAN_PORTLAR: set = set()
_AG_SAHIP_PORTLARI = frozenset({8000, 8100, 1883, 5173, 8177, 8200})
_AG_AILELER = (_socket.AF_INET, _socket.AF_INET6)
_AG_KANCA_YOKLAMA: list = []  # audit hook'un KAYITLI olduğunun kanıtı (sys.audit ile yoklanır)
try:
    _AG_YEREL_AD = _socket.gethostname().lower()
except Exception:
    _AG_YEREL_AD = ""


def _ag_loopback_mu(host) -> bool:
    h = str(host).strip().strip("[]").split("%")[0]
    if h.lower() in ("localhost", ""):
        return True
    try:
        ip = _ipaddress.ip_address(h)
    except ValueError:
        return False
    if isinstance(ip, _ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_loopback or ip.is_unspecified


def _ag_denetle(adres, tur) -> None:
    if not (isinstance(adres, tuple) and len(adres) >= 2):
        return
    try:
        port = int(adres[1])
    except (TypeError, ValueError):
        port = -1
    if not _ag_loopback_mu(adres[0]):
        neden = "loopback dışı"
    elif port in _AG_SAHIP_PORTLARI:
        neden = "sahibin servis portu"
    elif port not in _AG_ACILAN_PORTLAR:
        neden = "bu süreçte açılmamış loopback portu"
    else:
        return
    _AG_ENGELLENEN.append((tur, str(adres[0]), port))
    raise ConnectionRefusedError(f"TEST SÜİTİ AĞ BEKÇİSİ (D0Ö.07): {tur} {adres[0]}:{port} engellendi — {neden}")


def _ag_ad_denetle(ad, tur) -> None:
    """gethostbyname*/gethostbyaddr: loopback ve YEREL makine adı serbest; diğer her ad ENGEL."""
    ad = ad.decode() if isinstance(ad, bytes) else str(ad)
    if _ag_loopback_mu(ad) or (_AG_YEREL_AD and ad.lower() == _AG_YEREL_AD):
        return
    _AG_ENGELLENEN.append((tur, ad, -1))
    raise _socket.gaierror(11001, f"TEST SÜİTİ AĞ BEKÇİSİ (D0Ö.07): {tur} {ad} engellendi")


_ag_orj_connect = _socket.socket.connect
_ag_orj_connect_ex = _socket.socket.connect_ex
_ag_orj_sendto = _socket.socket.sendto
_ag_orj_bind = _socket.socket.bind
_ag_orj_getaddrinfo = _socket.getaddrinfo
_ag_orj_gethostbyname = _socket.gethostbyname
_ag_orj_gethostbyname_ex = _socket.gethostbyname_ex
_ag_orj_gethostbyaddr = _socket.gethostbyaddr


def _ag_connect(self, adres):
    if self.family in _AG_AILELER:
        _ag_denetle(adres, "connect")
    return _ag_orj_connect(self, adres)


def _ag_connect_ex(self, adres):
    if self.family in _AG_AILELER:
        try:
            _ag_denetle(adres, "connect_ex")
        except ConnectionRefusedError:
            return 10061  # WSAECONNREFUSED
    return _ag_orj_connect_ex(self, adres)


def _ag_sendto(self, veri, *args):
    if self.family in _AG_AILELER and args:
        _ag_denetle(args[-1], "sendto")
    return _ag_orj_sendto(self, veri, *args)


def _ag_bind(self, adres):
    if self.family in _AG_AILELER and isinstance(adres, tuple) and len(adres) >= 2:
        try:
            port = int(adres[1])
        except (TypeError, ValueError):
            port = -1
        if port in _AG_SAHIP_PORTLARI:
            _AG_ENGELLENEN.append(("bind", str(adres[0]), port))
            raise PermissionError(f"TEST SÜİTİ AĞ BEKÇİSİ (D0Ö.07): bind {adres[0]}:{port} — sahibin servis portu")
    sonuc = _ag_orj_bind(self, adres)
    try:
        _AG_ACILAN_PORTLAR.add(int(self.getsockname()[1]))
    except Exception:
        pass
    return sonuc


def _ag_getaddrinfo(host, *args, **kwargs):
    if host is not None:
        ad = host.decode() if isinstance(host, bytes) else str(host)
        if not _ag_loopback_mu(ad):
            _AG_ENGELLENEN.append(("dns", ad, -1))
            raise _socket.gaierror(11001, f"TEST SÜİTİ AĞ BEKÇİSİ (D0Ö.07): dns {ad} engellendi")
    return _ag_orj_getaddrinfo(host, *args, **kwargs)


def _ag_gethostbyname(ad):
    _ag_ad_denetle(ad, "gethostbyname")
    return _ag_orj_gethostbyname(ad)


def _ag_gethostbyname_ex(ad):
    _ag_ad_denetle(ad, "gethostbyname_ex")
    return _ag_orj_gethostbyname_ex(ad)


def _ag_gethostbyaddr(ad):
    _ag_ad_denetle(ad, "gethostbyaddr")
    return _ag_orj_gethostbyaddr(ad)


def _ag_denetim_kancasi(olay, arg):
    if olay == "socket.connect":
        if getattr(arg[0], "family", None) in _AG_AILELER:
            _ag_denetle(arg[1], "audit:connect")
    elif olay == "socket.sendto":
        if getattr(arg[0], "family", None) in _AG_AILELER:
            _ag_denetle(arg[1], "audit:sendto")
    elif olay == "socket.getaddrinfo":
        if arg[0] is not None:
            ad = arg[0].decode() if isinstance(arg[0], bytes) else str(arg[0])
            if not _ag_loopback_mu(ad):
                _AG_ENGELLENEN.append(("audit:dns", ad, -1))
                raise _socket.gaierror(11001, f"TEST SÜİTİ AĞ BEKÇİSİ (D0Ö.07): dns {ad} engellendi")
    elif olay in ("socket.gethostbyname", "socket.gethostbyaddr"):
        _ag_ad_denetle(arg[0], "audit:" + olay.split(".", 1)[1])
    elif olay == "pemf.ag_bekcisi.yoklama":
        _AG_KANCA_YOKLAMA.append(arg)


_socket.socket.connect = _ag_connect
_socket.socket.connect_ex = _ag_connect_ex
_socket.socket.sendto = _ag_sendto
_socket.socket.bind = _ag_bind
_socket.getaddrinfo = _ag_getaddrinfo
_socket.gethostbyname = _ag_gethostbyname
_socket.gethostbyname_ex = _ag_gethostbyname_ex
_socket.gethostbyaddr = _ag_gethostbyaddr
sys.addaudithook(_ag_denetim_kancasi)
if os.name == "nt":
    # Windows Proactor'ı ConnectEx/WSASendTo ile `socket.*`'ı ve audit olaylarını ATLAR: bu yama tek
    # kat. Kurulamazsa SESSİZCE geçilmez — içe aktarma hatası conftest'i (dolayısıyla süiti) düşürür.
    import asyncio.windows_events as _ag_we

    _ag_orj_iocp_connect = _ag_we.IocpProactor.connect
    _ag_orj_iocp_sendto = _ag_we.IocpProactor.sendto

    def _ag_iocp_connect(self, conn, address):
        if getattr(conn, "family", None) in _AG_AILELER:
            _ag_denetle(address, "iocp.connect")
        return _ag_orj_iocp_connect(self, conn, address)

    def _ag_iocp_sendto(self, conn, buf, flags=0, addr=None):
        if addr is not None and getattr(conn, "family", None) in _AG_AILELER:
            _ag_denetle(addr, "iocp.sendto")
        return _ag_orj_iocp_sendto(self, conn, buf, flags, addr)

    _ag_we.IocpProactor.connect = _ag_iocp_connect
    _ag_we.IocpProactor.sendto = _ag_iocp_sendto


@pytest.fixture(autouse=True)
def _bulut_provizyonu_yok_kalir():
    """D0Ö.07: yönlendirilen provizyon yolu ASLA var olmamalı — aynı değişken `make_cloud_provision.py`'nin
    ÇIKTI yolu; orada dosya belirirse ayna sonraki testlerde (üretici gerçek `Secrets.h`'ı okuduysa)
    GERÇEK kimliği okurdu. Dosya kaldırılır ve onu üreten test KIRMIZI olur."""
    yield
    hedef = _OTURUM_IZOLE / "YOK_cloud_mqtt_provision.json"
    if hedef.exists():
        try:
            hedef.unlink()
        except OSError:
            pass
        pytest.fail(f"bu test yönlendirilmiş bulut provizyon yolunda DOSYA oluşturdu ({hedef}) — D0Ö.07")


# ⚠️ D0Ö.10 (B-10.104) — LIFESPAN GERÇEK mDNS KAYDI YAPMAZ, SÜRE SONUNA KALAN DAEMON BAŞLATMAZ.
# ÖLÇÜLDÜ: `with TestClient(api_server.app)` lifespan'ı (1) `_start_mdns_service` thread'ini başlatıyor
# → `register_service('PEMF-Vet-…._pemfvet._tcp')` → süit LAN'a ilan yapıyordu (aynı Wi-Fi'deki telefonlar
# TEST SÜRECİNİ cihaz sanıp keşfeder; UDP rota hilesi engellense de `ifaddr` gerçek LAN IP'sini bulur);
# (2) `_start_background_threads` ile SONSUZ daemon'lar başlatıyordu (session-watchdog, sensor-persist,
# daily-maintenance, esp-telemetry-watchdog, efield-live; PEMF_SIMULATE ile hw-sim). Bunlar süreç sonuna
# dek yaşıyor: watchdog her 1 sn SONRAKİ testlerin seansını durdurabiliyor, daily-maintenance 60 sn sonra
# o an yamalı DB'de retention/yedek koşuyordu. "Beklenemezler" (çıkışsız döngü) → ENGELLENİR.
# Ürün kodu DEĞİŞMEZ; ikisi de kaydeden bir boş-işlemle değiştirilir. OTURUM kapsamlı: modül/oturum
# kapsamlı bir `with TestClient` fixture'ı da korunur (fonksiyon kapsamlı yama ondan SONRA kurulurdu).
# mDNS'i SINAYAN testler `start_mdns`/`get_shared_zeroconf`'u, watchdog'u sınayanlar döngüyü doğrudan
# (sınırlı turla) çağırır. Ad değişirse `setattr` YÜKSEK SESLE düşer (korumasız süit sessizce koşmasın).
# Kapılar: tests/test_lifespan_mdns_kaydi.py, tests/test_session_watchdog.py (kablolama)
_MDNS_ENGELLENEN: list = []
_ARKA_PLAN_ENGELLENEN: list = []
_GERCEK_ARKA_PLAN_BASLATICI = None  # kablolama testi gerçek başlatıcıyı Thread kaydediciyle çağırır


def _mdns_baslatici_yerine() -> None:
    """Lifespan'ın `_start_mdns_service` yerine: kayıt YOK, yalnız çağrı sayılır."""
    _MDNS_ENGELLENEN.append(threading.current_thread().name)


def _arka_plan_baslatici_yerine() -> None:
    """Lifespan'ın `_start_background_threads` yerine: daemon YOK, yalnız çağrı sayılır."""
    _ARKA_PLAN_ENGELLENEN.append(threading.current_thread().name)


@pytest.fixture(autouse=True, scope="session")
def _lifespan_yan_etkilerini_engelle():
    global _GERCEK_ARKA_PLAN_BASLATICI
    try:
        from servers import api_server as _api
    except ImportError:  # api_server içe aktarılamıyorsa lifespan da koşamaz
        yield
        return
    mp = pytest.MonkeyPatch()
    _GERCEK_ARKA_PLAN_BASLATICI = _api._start_background_threads
    mp.setattr(_api, "_start_mdns_service", _mdns_baslatici_yerine)
    mp.setattr(_api, "_start_background_threads", _arka_plan_baslatici_yerine)
    yield
    mp.undo()


@pytest.fixture(autouse=True)
def _gercek_kurulumu_koru(tmp_path):
    """⚠️ HİÇBİR TEST GERÇEK KURULUMA DOKUNAMAZ — 2026-08-08 denetiminde bulundu.

    ARIZA: `TestClient(api_server.app)` kullanan test dosyaları (test_auth, test_api_design,
    test_ai_review…) izole bir veri dizini AYARLAMIYORDU. `apps/backend/utils/secrets_manager` yolunu global
    `get_app_data_directory()`'den aldığı için bu testler GERÇEK `%APPDATA%\\PEMF_GUI` dizinine
    yazıyordu: orada SQLCipher anahtarı üretildi → gerçek (düz-metin) klinik veritabanı bir
    sonraki açılışta GÖÇE girdi, `.plain.bak` / `.enc.tmp` artıkları bıraktı ve testler
    "file is not a database" ile düşmeye başladı.

    Yani test süiti, canlı kurulumu olan bir geliştirici/klinik makinesinde HASTA
    VERİTABANINI değiştirebiliyordu. Bu fixture zinciri kökten keser: her test kendi temp
    dizinini kullanır. Gerçek dizine yazmak İSTEYEN bir test olursa bunu AÇIKÇA ezmelidir.

    ⚠️ DENETİM 2026-08-15 — KORUMA GERİ ALINABİLİYORDU (sızıntı ÖLÇÜLDÜ, 13 test).
    Bu fixture testin `monkeypatch` fixture'ını kullanıyordu. pytest test başına TEK
    `MonkeyPatch` örneği verir ve `undo()` o örnekteki TÜM işlemleri geri alır — yani bir
    testin kendi amacı için yazdığı `monkeypatch.undo()`, farkında olmadan BU KORUMAYI da
    siliyordu. Sonrasında `get_app_data_directory()` gerçek `%APPDATA%`ya çözümlenip
    `pemf_secrets.json`i (SQLCipher anahtarı) GERÇEK dizine yazıyordu — docstring'in
    yukarıda anlattığı hasarın aynısı, farklı bir kapıdan.
    ÇÖZÜM: koruma artık KENDİ `MonkeyPatch` örneğini kullanır. Testin `undo()`su ona
    erişemez; koruma yalnız bu fixture'ın teardown'ında kalkar.
    (Tekrarını `test_veri_dizini_izolasyonu.py` kilitliyor.)
    """
    izole = tmp_path / "_izole_appdata"
    (izole / "PEMF_GUI").mkdir(parents=True, exist_ok=True)
    mp = pytest.MonkeyPatch()
    mp.setenv("PEMF_DATA_DIR", str(izole))
    mp.setenv("APPDATA", str(izole))
    # Denetim #02: makine kapsamlı bulut-kimlik deposu da izole edilmeli (veri kökünün dışında).
    mp.setenv("PEMF_DEVICE_IDENTITY_DIR", str(izole / "makine_kimligi"))
    try:
        import utils.secrets_manager as sm

        sm._cache = None
    except Exception:
        pass
    yield
    mp.undo()
    try:
        import utils.secrets_manager as sm

        sm._cache = None
    except Exception:
        pass


@pytest.fixture()
def temp_app_data(tmp_path):
    """Her test için izole app_data dizini (gerçek %APPDATA%/PEMF_GUI'ye dokunma).

    ⚠️ DENETİM 2026-08-08 — GERÇEK KURULUMU BOZAN SIZINTI KAPATILDI.
    Eskiden yalnız `APPDATA` ayarlanıyordu. Ama `apps/backend/utils/secrets_manager` yolunu kendisine geçilen
    `app_data_dir` argümanından DEĞİL, global `utils.path_utils.get_app_data_directory()`'den
    alır ve o da önce `PEMF_DATA_DIR`'e bakar. Sonuç: temp dizinle kurulan bir test DB'si,
    SQLCipher anahtarını GERÇEK `%APPDATA%\\PEMF_GUI\\pemf_secrets.json` dosyasına yazıyordu.
    Anahtar orada belirince gerçek (düz-metin) klinik veritabanı bir sonraki açılışta GÖÇE
    giriyor; `.plain.bak` / `.enc.tmp` artıkları bırakıyor ve testler "file is not a database"
    ile patlıyordu. Yani test süiti, canlı kurulumu olan bir makinede HASTA VERİTABANINA
    dokunabiliyordu. `PEMF_DATA_DIR` de izole edilerek zincir kesildi.

    Ayrıca süreç-geneli sır önbelleği temizlenir: bir testte üretilen anahtar sonraki testin
    BAŞKA dizinine taşınırsa, onun düz-metin DB'si şifreli sanılır ve testler birbirini düşürür.

    ⚠️ DENETİM 2026-08-15: bu fixture de testin PAYLAŞILAN `monkeypatch`ini kullanıyordu →
    testin kendi amacı için yazdığı `monkeypatch.undo()` izolasyonu da siliyordu
    (ayrıntı: `_gercek_kurulumu_koru`). Kendi `MonkeyPatch` örneğine geçirildi.
    """
    d = tmp_path / "PEMF_GUI"
    d.mkdir(parents=True, exist_ok=True)
    mp = pytest.MonkeyPatch()
    mp.setenv("APPDATA", str(tmp_path))
    mp.setenv("PEMF_DATA_DIR", str(tmp_path))
    # Denetim #02: bkz. yukarıdaki not — bu yol PEMF_DATA_DIR'e bakmaz, ayrıca izole edilir.
    mp.setenv("PEMF_DEVICE_IDENTITY_DIR", str(tmp_path / "makine_kimligi"))

    def _onbellegi_temizle():
        try:
            import utils.secrets_manager as sm

            sm._cache = None
        except Exception:
            pass

    _onbellegi_temizle()
    yield d
    mp.undo()
    _onbellegi_temizle()


@pytest.fixture(autouse=True)
def _masaustunu_koru(tmp_path):
    """⚠️ HİÇBİR TEST SAHİBİN MASAÜSTÜNE DOSYA BIRAKAMAZ — 2026-09-11'de ölçüldü.

    ===========================================================================
    ARIZA
    ===========================================================================
    Sahip "uygulama açık bile değil, masaüstüne sürekli yeni CSV geliyor" dedi.
    Masaüstünde 18 adet `PEMF_alan_*.csv` birikmişti; içerikleri
    `operator_name,op` / `patient_name,Boncuk` — yani TEST FIXTURE verisi. Zaman
    damgaları süit koşularıyla birebir örtüşüyordu.

    `/session/start` yolundan geçen her test `api_server._seans_alan` SINGLETON'ını
    tetikliyor, o da `masaustu_dizini()` → `~/Desktop` çözüp oraya GERÇEKTEN dosya
    yazıyordu. Kendi fixture'ında yolu yamalayan iki test (`test_seans_alan_kaydi`,
    `test_seans_yogunluk_uctan_uca`) temizdi; DİĞER HEPSİ sızdırıyordu.

    ===========================================================================
    ⚠️ NEDEN `_gercek_kurulumu_koru` BUNU YAKALAMADI
    ===========================================================================
    O fixture VERİ KÖKÜNÜ izole eder (`APPDATA`, `PEMF_DATA_DIR`, cihaz kimliği).
    Masaüstü veri kökü DEĞİLDİR ve `~` üzerinden çözülür. 2026-09-11'de masaüstüne
    yazan yeni bir özellik eklendiğinde izolasyon onunla birlikte genişletilmedi —
    bu deponun tekrar eden "koruma yazıldı ama YENİ yola uygulanmadı" sınıfı.

    ===========================================================================
    ⚠️ NEDEN `HOME`/`USERPROFILE` EZİLMEDİ (denendi, REDDEDİLDİ)
    ===========================================================================
    Tek satırda her `~` kullanıcısını (CSV + PDF + gelecekteki her yazıcı) kapatırdı
    ama İKİ ZARARI ölçüldü:
      1. `test_veri_dizini_izolasyonu.py` GERÇEK `~/.pemf_gui`ye bakarak sızıntı arar.
         `~` sahteye çevrilseydi o kapı izole dizini ölçer ve SESSİZCE sahte-yeşile
         dönerdi — var olan bir korumayı hadım etmek, yeni bir koruma eklemekten
         daha pahalıdır.
      2. `test_gitleaks_config_derlenir.py` gitleaks ikilisini `Path.home()/.cache`
         altında arar; bulamazsa kapı işlevsizleşir.
    Bu yüzden `~` DOKUNULMADAN kalır; yalnız masaüstüne YAZAN uçlar yönlendirilir.

    ===========================================================================
    NEDEN MODÜL NİTELİĞİ YAMANIYOR (import edilmiş ada DEĞİL)
    ===========================================================================
    `seans_basladi()` her çağrıda modül globalinden `masaustu_dizini()` okur → yama
    etkilidir. Buna karşılık `test_seans_alan_kaydi.py` fonksiyonu `from ... import`
    ile ALMIŞTIR; o bağ import anında kurulduğu için ORİJİNALİ gösterir ve
    `systemprofile` davranışını sınayan kapı BOZULMADAN çalışmaya devam eder.
    (İkisi de ölçüldü.)

    Kapı: `tests/test_masaustu_sizintisi.py` — bu fixture kaldırılırsa KIRMIZI.
    """
    hedef = tmp_path / "sahte_masaustu"
    hedef.mkdir(parents=True, exist_ok=True)
    mp = pytest.MonkeyPatch()

    try:
        import servers.seans_alan_kaydi as _sak

        # ⚠️ ORİJİNAL SAKLANIR: üretim mantığını (systemprofile reddi, aday sırası)
        # SINAYAN testler buna ihtiyaç duyar. Yamalı sürümle sınamak, kapının
        # KENDİ SAHTESİNİ doğrulaması olurdu.
        # ⚠️ Fonksiyon GÖVDESİNDE `from ... import masaustu_dizini` yapmak YETMEZ:
        # o satır test sırasında koşar ve YAMALI niteliği alır (ölçüldü). Yalnız
        # MODÜL SEVİYESİNDE import eden dosyalar (test_seans_alan_kaydi.py)
        # orijinale bağlı kalır — çünkü o bağ toplama anında kurulur.
        mp.setattr(_sak, "_orijinal_masaustu_dizini", _sak.masaustu_dizini, raising=False)
        mp.setattr(_sak, "masaustu_dizini", lambda: (hedef, "test izolasyonu"), raising=False)
    except Exception:
        pass

    # PDF raporları da masaüstüne yazar (`apps/backend/utils/pdf_report_generator._default_output_path`).
    # ⚠️ Bugün süitte sızıntı ÜRETMİYOR (masaüstünde test PDF'i yok) ama AYNI SINIF:
    # yolu burada da kapatmak, yarın bir testin rapor üretmesiyle sızıntının geri
    # gelmesini engeller. Sınıfı kapatmak, örneği kapatmaktan daha ucuzdur.
    try:
        from utils.pdf_report_generator import PDFReportGenerator as _PDF

        _orijinal = _PDF._default_output_path

        def _izole_yol(self, prefix: str, name_hint: str = "") -> str:
            ham = _orijinal(self, prefix, name_hint)
            return str(hedef / Path(ham).name)

        mp.setattr(_PDF, "_default_output_path", _izole_yol, raising=False)
    except Exception:
        pass

    yield hedef
    mp.undo()


# ⚠️ `tests/` dizinini de yola ekle: `capraz.py` ve `topoloji.py` YARDIMCI modüllerdir
# (adları `test_*` olmadığı için pytest onları toplamaz) ve test dosyaları bunları
# `import topoloji` ile alır. Eskiden her dosya kendi `sys.path.insert`ini yapıyordu;
# tek yerde olması, yeni bir test dosyasının import'u unutup ImportError almasını önler.
if str(_TESTS_DIR := Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))


@pytest.fixture(autouse=True)
def _ack_bekcilerini_bosalt():
    """⚠️ ACK BEKÇİSİ SONRAKİ TESTE SIZAR — 2026-09-15'te CI'da ölçüldü (koşu 35005619586).

    ===========================================================================
    ARIZA
    ===========================================================================
    `windows-latest` matrisinde `test_KARSIT_KANIT_timeout_metni_DEGISMEDI` düştü.
    Kendi `uyarilar` listesinde BEŞ kayıt vardı ve kendi uyarısı ÜÇÜNCÜ sıradaydı:

        [('⚠️ Bobin 8: start onayı gelmedi …', 'warning'),      <- YABANCI
         ('⚠️ Bobin 8: start onayı gelmedi …', 'warning'),      <- YABANCI
         ('⚠️ Bobin 8: acil durdurma ESP onayı GELMEDİ …', 'error'),   <- kendi
         …]

    KÖK NEDEN: `_start_ack_izle_arka_planda` **daemon thread** açıyor
    (`start-ack-{coil}`) ve o thread `_START_ACK_TIMEOUT = 2.0` sn bekleyip
    `_push_notification` çağırıyor. Testler 2 sn'den KISA sürüyor → thread SONRAKİ
    testin içinde ateşliyor ve o an `_push_notification`'a takılı olan BAŞKA testin
    monkeypatch'ine yazıyor. E-stop bekçisi (`estop-ack-{coil}`) aynı desende.

    ⚠️ NEDEN YERELDE GEÇİYOR, CI'DA DÜŞÜYOR: tamamen ZAMANLAMA. Tam süit bu makinede
    iki kez yeşil geçti; CI runner'ının farklı hızında sıra kaydı. "Kararsız test"
    denip geçilecek sınıf DEĞİL — bu bir test-izolasyon arızası ve hangi testi
    vuracağı rastgele.

    ===========================================================================
    ⚠️ NEDEN TEARDOWN'DA (setup'ta değil)
    ===========================================================================
    Sızıntıyı ÜRETEN test kendi teardown'ında temizlemeli; sonraki testin setup'ına
    bırakmak, araya giren her fixture sırasında pencereyi açık bırakır. Ayrıca
    autouse conftest fixture'ı testin kendi `monkeypatch`inden ÖNCE kurulur, yani
    SONRA yıkılır → burada `_push_notification` artık GERÇEK fonksiyondur ve
    boşaltma kimsenin listesine yazmaz.

    ⚠️ THREAD ÖLDÜRÜLEMEZ (Python). Bu yüzden bekleyen `Event`'ler SET edilir →
    `_wait_ack` hemen döner → thread kendi akışını tamamlayıp biter; sonra `join`.
    Kayıt sözlüğü de temizlenir.
    """
    yield
    try:
        from servers import api_server as _api
    except Exception:
        return
    try:
        with _api._pending_acks_lock:
            for _giris in list(_api._pending_acks.values()):
                try:
                    _giris["event"].set()
                except Exception:
                    pass
            _api._pending_acks.clear()
    except Exception:
        pass
    for _t in list(threading.enumerate()):
        _ad = getattr(_t, "name", "") or ""
        if _ad.startswith(("start-ack-", "estop-ack-")) and _t.is_alive():
            try:
                _t.join(timeout=2.5)
            except Exception:
                pass


# ── D1.41 · B-10.243 · B-10.257: SEANS ve WATCHDOG NÖBETİ (ack bekçisi deseni) ─────────────────────────
#
# ÖLÇÜLEN (2026-10-01, tam süit + tanı eklentisi): 16 test `_active_session["is_active"]=True` bırakıyordu
# (test_session_lifecycle 6 · test_session_stop_dogrulama 9 · test_live_state 1) — sonraki dosyanın ilk
# seans testi 409 alır ve "kararsız test" sanılır; süre-watchdog'u (bobini süre dolunca durduran TEK yazılım
# mekanizması) çalışıyorsa ARTIK BAŞKA bir testin seansını durdurur. Süreç geneli `time.sleep` yaması
# (test_sim_GERCEGI_ASMAZ, B-10.257) ise o an uyuyan `session-watchdog`u KeyboardInterrupt ile öldürüyordu.
# Arka plan iş parçacıkları bugün süitte BAŞLAMIYOR (ölçüldü: `_bg_threads_started` hiçbir testte True
# değil) — ikinci kol bugün uykuda ama başlatan bir test eklendiğinde geçerlidir.
_WATCHDOG_OLUMU_BILDIRILDI = {"evet": False}


def uyku_nobetcisi_dongusu(uyku=None) -> None:
    """Sonsuza dek `time.sleep` ile uyur. Süreç geneli, FIRLATAN bir sleep yaması bu iş parçacığını öldürür —
    1-B bağımsız inceleme (i4): nöbetin watchdog kolu `_bg_threads_started` False iken (süitte HEP) uykudaydı;
    üç dosyadaki süreç geneli yama ölçülen biçimde uyuyan iş parçacığını öldürüyor ama nöbet susuyordu. Fırlatmayan
    yama (anında dönen sahte sleep) döngüyü döndürmesin diye kısa dönüşte olaya göre beklenir."""
    import time as _t

    bekle = threading.Event()
    while True:
        t0 = _t.monotonic()
        (uyku or _t.sleep)(0.005)  # kısa: testin kısa süreli yama penceresine denk gelsin
        if _t.monotonic() - t0 < 0.001:
            bekle.wait(0.005)


_UYKU_NOBETCISI = threading.Thread(target=uyku_nobetcisi_dongusu, daemon=True, name="nobetci-uyku")
_UYKU_NOBETCISI.start()
_UYKU_OLUMU_BILDIRILDI = {"evet": False}


@pytest.fixture(scope="session", autouse=True)
def _uyku_nobetcisi_OTURUM_SONU():
    """Ölüm SON testin teardown denetiminden sonra olursa da görünür olsun (oturum sonunda bir tur beklenir)."""
    yield
    _UYKU_NOBETCISI.join(0.05)
    if not _UYKU_NOBETCISI.is_alive() and not _UYKU_OLUMU_BILDIRILDI["evet"]:
        _UYKU_OLUMU_BILDIRILDI["evet"] = True
        pytest.fail(
            "D1.41 nöbeti (oturum sonu): süreç geneli `time.sleep` yaması nobetci-uyku'yu öldürdü", pytrace=False
        )


def seans_watchdog_nobet_sorunlari(api, is_parcaciklari) -> list[str]:
    """Nöbetin denetimi (test edilebilir saf işlev). `api`: servers.api_server benzeri; sızan aktif seans
    KAPATILIR (sonraki teste taşınmasın) ve raporlanır; watchdog ölümü süreçte YALNIZ BİR KEZ raporlanır."""
    sorunlar: list[str] = []
    try:
        with api._session_lock:
            if api._active_session.get("is_active") is True:
                api._active_session["is_active"] = False
                sorunlar.append(
                    f"aktif seans SIZDI (session_id={api._active_session.get('session_id')!r}) — test kendi seansını kapatmalı"
                )
    except Exception as e:  # noqa: BLE001
        sorunlar.append(f"seans durumu okunamadı: {e!r}")
    if getattr(api, "_bg_threads_started", False) and not _WATCHDOG_OLUMU_BILDIRILDI["evet"]:
        if not any(getattr(t, "name", "") == "session-watchdog" and t.is_alive() for t in is_parcaciklari):
            _WATCHDOG_OLUMU_BILDIRILDI["evet"] = True
            sorunlar.append("session-watchdog ÖLDÜ — bu testten sonra süre dolunca bobini durduran mekanizma YOK")
    return sorunlar


@pytest.fixture(autouse=True)
def _seans_ve_watchdog_nobeti():
    """Teardown'da (testin kendi fikstürleri yıkıldıktan SONRA): sızan aktif seans ya da ölü watchdog → KIRMIZI."""
    yield
    sorunlar: list[str] = []
    if not _UYKU_NOBETCISI.is_alive() and not _UYKU_OLUMU_BILDIRILDI["evet"]:
        _UYKU_OLUMU_BILDIRILDI["evet"] = True
        sorunlar.append(
            "süreç geneli `time.sleep` yaması UYUYAN iş parçacığını öldürdü (nobetci-uyku) — yamayı iş parçacığına "
            "yerel yap (`dongu_tek_tur.bir_tur_kos`)"
        )
    api = sys.modules.get("servers.api_server")
    if api is not None:
        sorunlar += seans_watchdog_nobet_sorunlari(api, threading.enumerate())
    if sorunlar:
        pytest.fail("D1.41 nöbeti: " + " · ".join(sorunlar), pytrace=False)


# ── 1-B (iii) · 1-A açık madde 13: ACL-KİLİTLİ düz-metin yedek ARTIĞI testin tmp'sinde KALMAZ ──────────────
#
# ÖLÇÜLEN (2026-10-01): emanet açıkken ürün `.plain.bak`'ı yalnız SYSTEM + Administrators'a kilitler; kullanıcı
# dosyayı OKUYAMAZ ve PowerShell `Remove-Item` onu SİLEMEZ (1-A temizliği bu yüzden `icacls /reset` istedi). Üst dizin
# kullanıcıya tam yetki verdiği için `os.unlink` / pytest `rm_rf` SİLER — "tmp rotasyonu kilitlenir" öncülü ölçümde
# DOĞRULANMADI; bu temizlik hijyendir (TEMP'te açılamayan düz-metin-biçimli yedek kalmasın). Teardown'da testin KENDİ
# tmp_path'i altındaki `*.plain.bak*` dosyaları silinir; silinemeyen kalırsa test KIRMIZI (sessiz artık yok).
# Yalnız tmp_path İSTEYEN testlerde çalışır.
@pytest.fixture(autouse=True)
def _acl_kilitli_duz_metin_yedek_ARTIGI_kalmaz(request):
    tmp = request.getfixturevalue("tmp_path") if "tmp_path" in request.fixturenames else None
    yield
    if tmp is None:
        return
    from acl_artik_temizligi import acl_kilitli_artiklari_temizle

    kalan = acl_kilitli_artiklari_temizle(tmp)
    if kalan:
        pytest.fail(f"1-B (iii): testin tmp'sinde SİLİNEMEYEN düz-metin yedek artığı: {kalan}", pytrace=False)
