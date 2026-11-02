# Author: mertaygn, cglrgrkn
"""KP-1 · apps/backend/servers/sync_worker.py · sözleşmeler: bulut senkron işçisi — sürüm alanları (api_server yüklenemezse
`app_version` / `at_rest_encrypted` YOK, launcher alanları ortamdan), cihaz kimliği okunamazsa "unknown-device", Supabase
istemcisi (paket yok → ERROR + False; kurulum hatası İLK seferde tür adıyla UYARI, sonra DEBUG), bulut kayıt sırrı kasası
okunamazsa "" ve sonraki çağrı yeniden dener, `publish_now` istemcisizken durum "istemci_yok", `start` (yapılandırma yoksa iş
parçacığı YOK; tünel geri çağrısı `publish_now`a bağlanır, bağlanamasa da işçi başlar; `stop` iş parçacığını bitirir), döngü
geri çekilmesi (istemci kurulamazsa / kayıt yayını düşerse bekleme ×2, başarıda aralık), hasta / seans PUSH-PULL DB hatası
yutulur ve günlüğe yazılır, PULL'da çözülemeyen (başka kliniğin) kayıt yerele YAZILMAZ ve sayısı uyarılır, tünel URL'si
TTL içinde son bilinenle korunur ve TTL aşılınca NULL yayınlanır, sürüm alanlı `upsert_device` reddedilirse BİR KEZ uyarı +
eski imzayla yeniden deneme, yayınlanan eşleştirme kodu veri kökünde KALICI olandır, RPC hiç yoksa `pairing_code`suz tablo
yedeği + "rpc_missing", veri kökü oluşturulamazsa `publish_now` istisna sızdırmaz / RPC yapmaz / iz bırakır (ve KP1-IA.4 —
KP-2 A3 / Y240 ile düzeldi: `_publish_device_registry` ilk yayında False + "error" + UYARI), `init_cloud_sync` tek örnek.

Sahte EN ALT katta: Supabase istemcisi (kayıtçı `rpc(...).execute()` / `table(...).upsert(...)`), `supabase` paketi
(`sys.modules` girdisi: None ya da `create_client`i düşen modül — monkeypatch geri koyar), kasa
(`utils.secrets_manager.get_secret`), ağ (`auto_discovery._get_local_ip`, `tunnel_manager.get_tunnel_url` /
`register_url_callback`), DB bağlantısı (`_get_connection` → OperationalError), bekleme (`stop_event` kayıtçısı: `wait` süreyi
kaydeder ve döngüyü bitirir). Cihaz kimliği / eşleştirme kodu GERÇEK `utils.path_utils` (KP1-IA.6): veri kökü tmp, mevcut
kurulumun `device_id.txt`si tohumlanır, eşleştirme kodunu gerçek üreteç tmp'ye yazar; veri kökü arızası GERÇEK `mkdir` arızası
(PEMF_DATA_DIR bir DOSYANIN altı). Tek istisna `test_CIHAZ_KIMLIGI_okunamazsa_unknown_device`: gerçek `get_unique_device_id`
dosya G/Ç'sini kendi içinde yakalar ve fırlatmaz → `__init__`in savunma kolu yalnız üst kat sahtesiyle ulaşılır (rapor GÖZLEM).
Hasta DB'si PULL testinde GERÇEK (tmp).
"""

from __future__ import annotations

import logging
import sqlite3
import sys
import threading
import time
import types
from types import SimpleNamespace

import pytest


def _log(caplog):
    return [r.getMessage() for r in caplog.records]


class _Sorgu:
    def __init__(self, fn):
        self._fn = fn

    def execute(self):
        return self._fn()


class _Istemci:
    """Supabase istemcisi yerine: `davranis(ad, params)` → data ya da istisna; tüm çağrılar kaydedilir."""

    def __init__(self, davranis=None):
        self.davranis = davranis or (lambda ad, params: [])
        self.rpc_cagri: list = []
        self.tablo_cagri: list = []

    def rpc(self, ad, params):
        self.rpc_cagri.append((ad, dict(params)))
        return _Sorgu(lambda: SimpleNamespace(data=self.davranis(ad, params)))

    def table(self, ad):
        istemci = self

        class _Tablo:
            def upsert(self, satir, on_conflict=None):
                istemci.tablo_cagri.append((ad, dict(satir), on_conflict))
                return _Sorgu(lambda: SimpleNamespace(data=[satir]))

        return _Tablo()


class _Olay:
    """`stop_event` yerine: `wait(t)` süreyi kaydeder ve döngüyü bitirir."""

    def __init__(self):
        self.bekle: list = []
        self._set = False

    def is_set(self):
        return self._set

    def wait(self, t=None):
        self.bekle.append(t)
        self._set = True
        return True

    def set(self):
        self._set = True


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    from servers import auto_discovery, tunnel_manager
    from utils import secrets_manager

    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path / "veri"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("PEMF_API_PORT", "8131")
    monkeypatch.delenv("PEMF_CLOUD_PATIENT_SYNC", raising=False)
    monkeypatch.delenv("PEMF_RESET_PAIRING_CODE", raising=False)
    # KP1-IA.6: kimlik / eşleştirme kodu GERÇEK path_utils'ten; yalnız mevcut kurulumun kalıcı cihaz kimliği dosyası tohumlanır.
    kok = tmp_path / "veri" / "PEMF_GUI"
    kok.mkdir(parents=True)
    (kok / "device_id.txt").write_text("kp-cihaz", encoding="utf-8")
    gercek_kasa = secrets_manager.get_secret
    monkeypatch.setattr(
        secrets_manager,
        "get_secret",
        lambda ad, *a, **k: "kp-sir" if ad == "device_registry_secret" else gercek_kasa(ad, *a, **k),
    )
    monkeypatch.setattr(auto_discovery, "_get_local_ip", lambda *a, **k: "192.168.1.10")
    url = {"deger": ""}
    monkeypatch.setattr(tunnel_manager, "get_tunnel_url", lambda: url["deger"])
    return SimpleNamespace(url=url, tmp=tmp_path, kok=kok)


def _veri_koku_bozulur(ortam, monkeypatch):
    """Veri kökü artık oluşturulamıyor: PEMF_DATA_DIR bir DOSYANIN altını gösterir → `get_app_data_directory` içinde GERÇEK
    `mkdir` arızası (eşleştirme kodu okunamaz / yazılamaz)."""
    engel = ortam.tmp / "veri_koku_dosya"
    engel.write_text("burası dizin değil", encoding="utf-8")
    monkeypatch.setenv("PEMF_DATA_DIR", str(engel / "alt"))


def _isci(istemci=None, interval=60):
    from servers.sync_worker import CloudSyncWorker

    w = CloudSyncWorker("", "", interval_sec=interval)
    w.supabase_url, w.supabase_key = "https://ornek.supabase.co", "anon-anahtar"
    w.client = istemci
    return w


def _api_server_yuklenemez(monkeypatch):
    import servers
    from servers import api_server as _api  # noqa: F401 — geri koyma için yüklü olsun

    monkeypatch.delattr(servers, "api_server")
    monkeypatch.setitem(sys.modules, "servers.api_server", None)


# ── sürüm alanları · kimlik · istemci · sır ───────────────────────────────────────────────────────────────────────────────────


def test_SURUM_ALANLARI_api_server_YUKLENEMEZSE_yalniz_launcher_alanlari(ortam, monkeypatch):
    """api_server içe aktarılamıyor + `PEMF_LAUNCHER_VERSION` / `PEMF_BASE_SHA` → {launcher_version, base_sha}; `app_version` ve
    `at_rest_encrypted` YOK (uydurulmaz), istisna sızmaz."""
    from servers import sync_worker as sw

    monkeypatch.setenv("PEMF_LAUNCHER_VERSION", "1.9.51")
    monkeypatch.setenv("PEMF_BASE_SHA", "cfb481ee")
    _api_server_yuklenemez(monkeypatch)
    assert sw._surum_alanlari() == {"launcher_version": "1.9.51", "base_sha": "cfb481ee"}


def test_CIHAZ_KIMLIGI_okunamazsa_unknown_device(ortam, monkeypatch):
    """`get_unique_device_id` OSError → `device_id` "unknown-device" (işçi yine kurulur). Not: gerçek `get_unique_device_id` dosya
    G/Ç'sini kendi içinde yakalar ve bugün fırlatmaz → bu savunma kolu yalnız üst kat sahtesiyle ulaşılır (çağıranın dayanıklılık
    sözleşmesi; KP1-IA.6 GÖZLEM)."""
    from servers.sync_worker import CloudSyncWorker
    from utils import path_utils

    def _patla(*a, **k):
        raise OSError(5, "makine kimliği okunamadı")

    monkeypatch.setattr(path_utils, "get_unique_device_id", _patla)
    assert CloudSyncWorker("", "").device_id == "unknown-device"


def test_ISTEMCI_supabase_paketi_YOKSA_False_ve_ERROR(ortam, monkeypatch, caplog):
    """`supabase` içe aktarılamıyor → `_ensure_client` False, istemci None, ERROR "Supabase paketi kurulu degil (pip install supabase)."."""
    w = _isci()
    monkeypatch.setitem(sys.modules, "supabase", None)
    caplog.set_level(logging.ERROR)
    assert w._ensure_client() is False and w.client is None
    assert "Supabase paketi kurulu degil (pip install supabase)." in _log(caplog)


def test_ISTEMCI_kurulum_hatasi_ILK_kez_UYARI_sonra_DEBUG(ortam, monkeypatch, caplog):
    """`create_client` ValueError → iki çağrı da False; ilki UYARI (tür adı "ValueError", "BULUT SENKRONU KAPALI"), ikincisi
    yalnız DEBUG "Supabase client kurulamadi (tekrar): …" (UYARI tekrar etmez)."""
    sahte = types.ModuleType("supabase")

    def _create_client(url, key):
        raise ValueError("Invalid URL")

    sahte.create_client = _create_client
    monkeypatch.setitem(sys.modules, "supabase", sahte)
    w = _isci()
    caplog.set_level(logging.DEBUG)
    assert w._ensure_client() is False
    assert w._ensure_client() is False
    uyari = [
        r.getMessage()
        for r in caplog.records
        if r.levelno == logging.WARNING and r.getMessage().startswith("Supabase istemcisi kurulamadı")
    ]
    assert len(uyari) == 1 and "Supabase istemcisi kurulamadı (ValueError) — BULUT SENKRONU KAPALI" in uyari[0]
    assert "Supabase client kurulamadi (tekrar): Invalid URL" in _log(caplog)


def test_KAYIT_SIRRI_kasa_okunamazsa_bos_SONRAKI_cagri_yeniden_dener(ortam, monkeypatch):
    """Kasa ilk okumada hata → `_registry_secret` ""; kasa düzelince sonraki çağrı sırrı okur ("" önbelleğe takılmaz)."""
    from utils import secrets_manager

    durum = {"bozuk": True}

    def _kasa(ad, *a, **k):
        if durum["bozuk"]:
            raise RuntimeError("keyring arka ucu yok")
        return "kp-sir"

    monkeypatch.setattr(secrets_manager, "get_secret", _kasa)
    w = _isci()
    assert w._registry_secret() == ""
    durum["bozuk"] = False
    assert w._registry_secret() == "kp-sir"


def test_PUBLISH_NOW_istemcisiz_durum_istemci_yok(ortam):
    """İstemci yok → `publish_now` istisnasız, `_registry_status` "istemci_yok"."""
    w = _isci(None)
    w.publish_now("https://yeni.trycloudflare.com")
    assert w._registry_status == "istemci_yok"


# ── start · stop · döngü ──────────────────────────────────────────────────────────────────────────────────────────────────────


def test_START_yapilandirma_YOKSA_is_parcacigi_baslamaz(ortam):
    """URL / anahtar boş → `start` iş parçacığı açmaz (`thread` None)."""
    from servers.sync_worker import CloudSyncWorker

    w = CloudSyncWorker("", "")
    w.start()
    assert w.thread is None


@pytest.mark.parametrize("geri_cagri_bozuk", [False, True])
def test_START_tunel_geri_cagrisi_publish_now_isci_baslar_STOP_bitirir(ortam, monkeypatch, geri_cagri_bozuk):
    """Yapılandırılmış işçi: tünel geri çağrısı `publish_now`a bağlanır (bağlanamasa da işçi başlar); "CloudSyncWorker" iş
    parçacığı açılır, `stop` sonrası yaşamaz."""
    from servers import tunnel_manager

    kayit: list = []

    def _kaydet(cb):
        if geri_cagri_bozuk:
            raise RuntimeError("geri çağrı listesi kilitli")
        kayit.append(cb)

    monkeypatch.setattr(tunnel_manager, "register_url_callback", _kaydet)
    w = _isci(_Istemci())
    w.stop_event.set()  # döngü ilk denetimde çıkar — ağ turu yok
    w.start()
    try:
        assert w.thread is not None and w.thread.name == "CloudSyncWorker"
        assert kayit == ([] if geri_cagri_bozuk else [w.publish_now])
    finally:
        w.stop()
    assert not w.thread.is_alive()


def test_DONGU_istemci_KURULAMAZSA_bekleme_IKI_KATI_yayin_YOK(ortam, monkeypatch):
    """İstemci yok ve `supabase` içe aktarılamıyor → tur `interval × 2` bekler (120 sn), kayıt yayını denenmez."""
    monkeypatch.setitem(sys.modules, "supabase", None)
    w = _isci(None, interval=60)
    w.stop_event = _Olay()
    yayin: list = []
    monkeypatch.setattr(w, "_publish_device_registry", lambda: yayin.append(1) or True)
    w._sync_loop()
    assert (w.stop_event.bekle, yayin) == ([120], [])


@pytest.mark.parametrize(("rpc_bozuk", "bekleme"), [(True, 120), (False, 60)])
def test_DONGU_kayit_yayini_DUSERSE_bekleme_IKI_KATI_basarida_aralik(ortam, rpc_bozuk, bekleme):
    """Kayıt yayını RPC'si "connection reset" → durum "error", bekleme 120 sn; RPC başarılı → durum "ok", bekleme 60 sn."""

    def _davranis(ad, params):
        if rpc_bozuk:
            raise RuntimeError("connection reset by peer")
        return []

    w = _isci(_Istemci(_davranis), interval=60)
    w.stop_event = _Olay()
    w._sync_loop()
    assert w.stop_event.bekle == [bekleme]
    assert w._registry_status == ("error" if rpc_bozuk else "ok")


# ── hasta / seans senkronu ─────────────────────────────────────────────────────────────────────────────────────────────────────


class _KilitliDb:
    """DB bağlantısı açılamıyor (SQLite kilitli)."""

    def __init__(self):
        self.lock = threading.Lock()

    def _get_connection(self):
        raise sqlite3.OperationalError("database is locked")


def test_HASTA_senkronu_DB_KILITLIYSE_PUSH_ve_PULL_hatasi_yutulur(ortam, caplog):
    """Bağlantı OperationalError → `_sync_patients` istisnasız; "Patient PUSH hatasi: database is locked" ve "Patient PULL hatasi:
    database is locked" yazılır; PULL RPC'si yapılmış ama yerele yazılmamış."""
    ist = _Istemci()
    w = _isci(ist)
    caplog.set_level(logging.ERROR)
    w._sync_patients(_KilitliDb())
    log = _log(caplog)
    assert "Patient PUSH hatasi: database is locked" in log and "Patient PULL hatasi: database is locked" in log
    assert [a for a, _ in ist.rpc_cagri] == ["resolve_patients"]


def test_SEANS_senkronu_DB_KILITLIYSE_PUSH_ve_PULL_hatasi_yutulur(ortam, caplog):
    """Bağlantı OperationalError → `_sync_sessions` istisnasız; "Session PUSH hatasi" ve "Session PULL hatasi" yazılır; bağlantı
    olmadan RPC yapılmaz."""
    ist = _Istemci()
    w = _isci(ist)
    caplog.set_level(logging.ERROR)
    w._sync_sessions(_KilitliDb())
    log = _log(caplog)
    assert "Session PUSH hatasi: database is locked" in log and "Session PULL hatasi: database is locked" in log
    assert ist.rpc_cagri == []


def test_HASTA_PULL_cozulemeyen_BASKA_klinik_kayitlari_YAZILMAZ_sayisi_uyarilir(ortam, monkeypatch, caplog):
    """Buluttan bu cihazın anahtarıyla çözülemeyen 2 kayıt (`enc:` başka anahtar) → yerel hasta DB'sine HİÇBİRİ yazılmaz, uyarı
    "Patient PULL: 2 yabanci/cozulemeyen kayit atlandi (cross-tenant korumasi)."."""
    import veri_tasima_aparati as vta

    tdb, hdb = vta.cihaz_kur(monkeypatch, ortam.tmp / "A")
    try:
        satirlar = [{"id": f"yabanci-{i}", "name": f"enc:gAAAAAB-baska-klinik-{i}", "species": "Kedi"} for i in (1, 2)]
        ist = _Istemci(lambda ad, params: satirlar if ad == "resolve_patients" else [])
        w = _isci(ist)
        caplog.set_level(logging.WARNING)
        w._sync_patients(hdb)
        assert hdb.get_all_patients() == []
        assert "Patient PULL: 2 yabanci/cozulemeyen kayit atlandi (cross-tenant korumasi)." in _log(caplog)
    finally:
        vta.kapat(tdb, hdb)


# ── cihaz kayıt yayını ─────────────────────────────────────────────────────────────────────────────────────────────────────────


def _upsert(ist):
    return [p for ad, p in ist.rpc_cagri if ad == "upsert_device"]


def test_KAYIT_tunel_URL_TTL_icinde_KORUNUR_asilinca_NULL(ortam, caplog):
    """1) tünel URL'si var → `p_tunnel_url` o; 2) URL anlık boş, TTL içinde → son bilinen korunur; 3) son doğrulama TTL'den eski →
    UYARI + `p_tunnel_url` None (ulaşılamayan adres yayınlanmaz)."""
    from servers import sync_worker as sw

    ist = _Istemci()
    w = _isci(ist)
    ortam.url["deger"] = "https://kp.trycloudflare.com"
    assert w._publish_device_registry() is True
    ortam.url["deger"] = ""
    assert w._publish_device_registry() is True
    w._last_tunnel_seen = time.monotonic() - sw._TUNNEL_URL_TTL_S - 5
    caplog.set_level(logging.WARNING)
    assert w._publish_device_registry() is True
    assert [p["p_tunnel_url"] for p in _upsert(ist)] == [
        "https://kp.trycloudflare.com",
        "https://kp.trycloudflare.com",
        None,
    ]
    assert any("dogrulanmadi → registry'de NULL" in m for m in _log(caplog))
    assert w._last_tunnel_url is None


def test_KAYIT_surum_alanlari_REDDEDILIRSE_BIR_kez_uyari_eski_imza(ortam, caplog):
    """`upsert_device` sürüm alanlı imzayı PGRST202 ile reddediyor, eski imzayı kabul ediyor → iki yayın da True, durum "ok";
    her yayında önce `p_app_version`lı sonra onsuz çağrı; "Filo envanteri" uyarısı YALNIZ bir kez; dört çağrının hepsinde
    `p_pairing_code` veri kökündeki KALICI `pairing_code.txt` (6 karakter, ürün alfabesi; iki yayın arasında değişmez)."""
    from utils import path_utils

    def _davranis(ad, params):
        if "p_app_version" in params:
            raise RuntimeError("PGRST202: Could not find the function public.upsert_device(p_app_version, …)")
        return []

    ist = _Istemci(_davranis)
    w = _isci(ist)
    caplog.set_level(logging.WARNING)
    assert w._publish_device_registry() is True and w._publish_device_registry() is True
    assert w._registry_status == "ok"
    assert ["p_app_version" in p for p in _upsert(ist)] == [True, False, True, False]
    kod = (ortam.kok / "pairing_code.txt").read_text(encoding="utf-8")
    assert len(kod) == 6 and all(ch in path_utils._PAIRING_CODE_ALPHABET for ch in kod)
    assert [p["p_pairing_code"] for p in _upsert(ist)] == [kod] * 4
    assert _upsert(ist)[1]["p_secret"] == "kp-sir" and _upsert(ist)[1]["p_device_id"] == "kp-cihaz"
    assert sum("Filo envanteri: upsert_device SÜRÜM ALANLARINI kabul etmiyor" in m for m in _log(caplog)) == 1


def test_KAYIT_RPC_HIC_YOKSA_pairing_codesuz_tablo_yedegi_rpc_missing(ortam):
    """`upsert_device` hiç yok (her çağrı PGRST202) → eski imza da düşer → `devices` tablosuna `device_id` çakışmasıyla upsert,
    satırda `pairing_code` YOK (geniş okunur tabloya sır yazılmaz); durum "rpc_missing", dönüş True."""

    def _davranis(ad, params):
        raise RuntimeError("PGRST202: Could not find the function public.upsert_device")

    ist = _Istemci(_davranis)
    w = _isci(ist)
    assert w._publish_device_registry() is True
    assert w._registry_status == "rpc_missing"
    assert len(ist.tablo_cagri) == 1
    tablo, satir, cakisma = ist.tablo_cagri[0]
    assert (tablo, cakisma, satir["device_id"], satir["local_ip"], satir["api_port"]) == (
        "devices",
        "device_id",
        "kp-cihaz",
        "192.168.1.10",
        8131,
    )
    assert "pairing_code" not in satir


def test_PUBLISH_NOW_veri_koku_OLUSTURULAMAZSA_istisna_sizmaz_RPC_yok_ariza_IZ_birakir(ortam, monkeypatch, caplog):
    """Yeni işçi (henüz hiç kayıt yayını yok) + veri kökü oluşturulamıyor (gerçek `mkdir` arızası) → tünel geri çağrısı
    `publish_now` istisnasız döner (tünel yöneticisinin geri çağrı döngüsü kırılmaz), eksik yükle RPC / tablo yazımı YAPILMAZ ve
    arıza günlükte UYARI izi bırakır: `_publish_device_registry`nin "Device registry publish BASARISIZ: …" kolu. (KP1-IA.4 öncesi iz
    `publish_now`ın DEBUG "publish_now hatasi: …" koluydu — `AttributeError` orada yutuluyordu; KP-2 A3 / Y240 ile düzeldi.)"""
    from servers import sync_worker as sw

    ist = _Istemci()
    w = _isci(ist)
    monkeypatch.setattr(sw, "_sync_worker", w)
    _veri_koku_bozulur(ortam, monkeypatch)
    caplog.set_level(logging.DEBUG)
    w.publish_now("https://yeni.trycloudflare.com")
    assert (ist.rpc_cagri, ist.tablo_cagri) == ([], [])
    assert any(m.startswith("Device registry publish BASARISIZ: ") for m in _log(caplog))
    assert not any(m.startswith("publish_now hatasi: ") for m in _log(caplog))
    assert sw.get_registry_status() == "error"


def test_YENI_isci_kayit_durumu_UNKNOWN_ile_baslar(ortam, monkeypatch):
    """KP-2 A3 / Y240: yeni işçi (henüz kayıt yayını yok) → öznitelik `_registry_status` VAR ve "unknown"; `/api/health` alanı
    (`get_registry_status`) "unknown" der (öznitelik yokluğunun `getattr` varsayılanına değil kurucunun değerine dayanır)."""
    from servers import sync_worker as sw

    w = _isci(_Istemci())
    monkeypatch.setattr(sw, "_sync_worker", w)
    assert w.__dict__["_registry_status"] == "unknown"
    assert sw.get_registry_status() == "unknown"


def test_KAYIT_ilk_yayin_RPC_ONCESI_duserse_False_durum_ERROR_ve_UYARI(ortam, monkeypatch, caplog):
    """Yeni işçi + veri kökü oluşturulamıyor → `_publish_device_registry` FIRLATMAZ, False döner; `get_registry_status()`
    (/api/health alanı) "error"; UYARI "Device registry publish BASARISIZ: …"; RPC yok (DENETIM 2026-08-28 #02 görünürlük
    sözleşmesi). KP1-IA.4 GERÇEK ÜRÜN HATASIYDI (`__init__` `_registry_status`'u kurmuyordu → except dalı `AttributeError`
    yükseltiyordu, durum "unknown" kalıyordu); KP-2 A3 (Y240) ile düzeldi."""
    from servers import sync_worker as sw

    ist = _Istemci()
    w = _isci(ist)
    monkeypatch.setattr(sw, "_sync_worker", w)
    _veri_koku_bozulur(ortam, monkeypatch)
    caplog.set_level(logging.WARNING)
    assert w._publish_device_registry() is False
    assert sw.get_registry_status() == "error"
    assert ist.rpc_cagri == []
    assert any(m.startswith("Device registry publish BASARISIZ: ") for m in _log(caplog))


# ── modül tekili ───────────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_INIT_CLOUD_SYNC_tek_ornek_get_cloud_sync_onu_doner(ortam, monkeypatch):
    """Tekil boşken `init_cloud_sync` işçi kurar (yapılandırmasız → iş parçacığı yok) ve `get_cloud_sync` onu döner; ikinci çağrı
    örneği DEĞİŞTİRMEZ."""
    from servers import sync_worker as sw

    monkeypatch.setattr(sw, "_sync_worker", None)
    assert sw.get_cloud_sync() is None
    sw.init_cloud_sync("", "")
    ilk = sw.get_cloud_sync()
    assert isinstance(ilk, sw.CloudSyncWorker) and ilk.thread is None
    sw.init_cloud_sync("https://baska.supabase.co", "baska")
    assert sw.get_cloud_sync() is ilk and ilk.supabase_url == ""
