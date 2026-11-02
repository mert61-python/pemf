# -*- coding: utf-8 -*-
"""KP-1 · apps/backend/servers/system_router.py · sözleşmeler: sistem / sağlık uçları yardımcı OKUNAMAZSA düşmez (cihaz kimliği
"PEMF-001", eşleştirme kodu / tünel / sensör kaydı / oto-firmware None, bulut registry "unknown", aktif-tedavi BİLİNEMEZSE "aktif"
(fail-safe), açılış nedeni üretilemezse genel "DB hazır değil" metni) · sağlık DB sorgusu ve veri-kökü-ağda sorgusu kendi iş
parçacığında (anahtar üretilemezse None anahtarla; sorgu BaseException ile düşse de bekleyen ASILMAZ) · favicon (kaynak ağacı /
donmuş: _MEIPASS → EXE dizini; erişilemeyen aday atlanır; hiçbiri yoksa 204) · KPI (DB yok → sıfır sonuç; bobin kullanımı yalnız
1..8; koşu tablosu yoksa sayımlar yine döner; seans tablosu yoksa sıfır sonuç + günlük) · istemci hata günlüğü (2 MB'ta `.1`'e
döner; döndürülemezse kesilir; yazılamazsa da 200) · kurtarma kodu okunamazsa 500 · kurtarma onayı (işaret yazılamazsa onay YİNE
geçerli; DB açılamazsa 500) · saklama / denetim izi / destek paketi 500 iletileri · destek paketinde denetim izi modülü yoksa paket
yine döner · anonimleştirme bekleyeni sayılamazsa None · son anonimleştirme turu okunamazsa None · jeton bakiyesi.

Sahte EN ALT katta: veri kökü (`PEMF_DATA_DIR` bir DOSYA → `mkdir` düşer), MAC okuma (`uuid.getnode`), DB açılış kilidi (ürünün kendi
`_acilis_kilidi` kaydı = "açılışta açılamadı" durumu), içe aktarma engeli (paketlenmiş derlemede EKSİK MODÜL biçimi: `sys.modules`
girdisi None + üst paket özniteliği kaldırılır, ikisi de monkeypatch ile geri), dosya sistemi (salt-okunur dosya, dizin olan hedef,
geçersiz UTF-8), `sys.frozen/_MEIPASS/executable`, `Path.exists` (yalnız tek aday için EACCES). `_api` parametresi alan iç yardımcılar
(`_saglik_db_durumu*`, `_veri_koku_agda*`) parametreyle verilen saplamayla sınanır. Yerel IP sorgusu (UDP connect) sabit dizgeyle
sahtelenir (ağ YOK). Sunucu yalnız süreç içi (`TestClient`, loopback istemci adresi; dinleyici YOK).
"""

from __future__ import annotations

import asyncio
import base64
import importlib
import io
import json
import logging
import os
import pathlib
import stat
import sys
import threading
import types
import zipfile

import pytest
from fastapi.testclient import TestClient
from servers import system_router as sr
from utils import ceviri

# ── Aparat ───────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def api():
    from servers import api_server

    return api_server


@pytest.fixture
def yerel(api):
    c = TestClient(api.app, client=("127.0.0.1", 51234))
    try:
        yield c
    finally:
        c.close()


@pytest.fixture(autouse=True)
def _ucuslar(monkeypatch):
    """Tek-uçuş tekilleri her testte boş başlar; test sonunda süren sorgu beklenir (canlı iş parçacığı kalmaz) ve eski hâle döner."""
    monkeypatch.setattr(sr, "_saglik_db_ucusta", None)
    monkeypatch.setattr(sr, "_veri_agda_ucusta", None)
    yield
    for ad in ("_saglik_db_ucusta", "_veri_agda_ucusta"):
        u = getattr(sr, ad)
        if u is not None:
            u[1].result(timeout=10)
    for t in threading.enumerate():
        if t.name in ("pemf-saglik-db", "pemf-veri-koku-ag"):
            t.join(10)


@pytest.fixture
def kok(api, tmp_path, monkeypatch):
    """Veri kökü tmp; tedavi DB tekili test boyunca BOŞ başlar (gerçek örnek açılırsa test sonunda kapatılır) ve eski hâline döner."""
    from database import treatment_history_db as thdb

    k = tmp_path / "veri"
    k.mkdir()
    monkeypatch.setattr(api, "_app_data_dir", lambda: k)
    monkeypatch.setattr(thdb, "_treatment_db_instance", None)
    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path / "pd"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "ad"))
    yield k
    yeni = thdb._treatment_db_instance
    if yeni is not None:
        yeni.close()


def _tedavi_db_acilamadi(monkeypatch, k):
    """Ürünün kendi "açılışta açılamadı" kaydı: `get_treatment_db(k)` istek yolunda RuntimeError atar (DB kurulmaz)."""
    from database import treatment_history_db as thdb

    monkeypatch.setattr(thdb, "_treatment_db_instance", None)
    monkeypatch.setitem(thdb._acilis_kilidi, thdb._kilit_anahtari(k / "pemf_treatment_history.db"), "OperationalError")


@pytest.fixture
def kilitli_kok(kok, monkeypatch):
    _tedavi_db_acilamadi(monkeypatch, kok)
    return kok


@pytest.fixture
def lan_ip_sabit(monkeypatch):
    """`_get_local_ip` UDP connect ile rota sorar — ağ YOK: sabit LAN adresi (dönüş sözleşmesi: dizge)."""
    from servers import auto_discovery

    monkeypatch.setattr(auto_discovery, "_get_local_ip", lambda: "192.168.1.50")


def _modul_yok(monkeypatch, ad):
    """`ad` bu test boyunca İÇE AKTARILAMAZ (eksik modül): `sys.modules[ad] = None` + üst paket özniteliği kaldırılır — monkeypatch
    ikisini de geri koyar (önce girdi, sonra öznitelik)."""
    paket_adi, _, alt = ad.rpartition(".")
    paket = importlib.import_module(paket_adi)
    monkeypatch.delattr(paket, alt, raising=False)
    monkeypatch.setitem(sys.modules, ad, None)


def _kos(coro):
    dongu = asyncio.SelectorEventLoop()
    try:
        return dongu.run_until_complete(coro)
    finally:
        dongu.close()


def _veri_koku_bozuk(monkeypatch, tmp_path):
    """`PEMF_DATA_DIR` bir DOSYA → `get_app_data_directory` mkdir'de düşer; MAC da okunamaz (`uuid.getnode` OSError)."""
    import uuid

    dosya = tmp_path / "kok_dosya"
    dosya.write_text("dizin degil", encoding="utf-8")
    monkeypatch.setenv("PEMF_DATA_DIR", str(dosya))

    def _mac_yok():
        raise OSError("MAC okunamadi (aparat)")

    monkeypatch.setattr(uuid, "getnode", _mac_yok)


class _Kesinti(BaseException):
    """İş parçacığında `Exception` dışı kesinti (ör. SystemExit benzeri)."""


def _kayitlar(caplog, parca):
    return [r for r in caplog.records if parca in r.getMessage()]


# ── /api/system/info ─────────────────────────────────────────────────────────


def test_sistem_bilgisi_KIMLIK_ESLESTIRME_TUNEL_okunamazsa_varsayilanlar_doner(yerel, api, kok, monkeypatch, tmp_path):
    """veri kökü kurulamaz + MAC okunamaz + tünel modülü yok → 200; deviceId "PEMF-001", pairingCode None, tunnelUrl None."""
    _veri_koku_bozuk(monkeypatch, tmp_path)
    _modul_yok(monkeypatch, "servers.tunnel_manager")
    r = yerel.get("/api/system/info")
    assert r.status_code == 200, r.text[:300]
    g = r.json()
    assert g["deviceId"] == "PEMF-001"
    assert g["pairingCode"] is None
    assert g["tunnelUrl"] is None
    assert g["softwareVersion"] == api._APP_VERSION


def test_sistem_bilgisi_SENSOR_KAYDI_modulu_yoksa_None_ve_debug(yerel, kok, monkeypatch, caplog):
    """sensör kaydedici içe aktarılamaz → `sensorKaydi` None (uç düşmez) + 'sensor kaydi durumu okunamadi' debug kaydı."""
    _modul_yok(monkeypatch, "servers.sensor_kaydedici")
    with caplog.at_level(logging.DEBUG, logger="system_router"):
        r = yerel.get("/api/system/info")
    assert r.status_code == 200, r.text[:300]
    assert r.json()["sensorKaydi"] is None
    assert _kayitlar(caplog, "sensor kaydi durumu okunamadi")


# ── /api/health ──────────────────────────────────────────────────────────────


def test_saglik_KIMLIK_ve_ESLESTIRME_okunamazsa_PEMF_001_ve_None(
    yerel, kilitli_kok, lan_ip_sabit, monkeypatch, tmp_path
):
    """veri kökü kurulamaz + MAC okunamaz → sağlık 200 "online"; deviceId "PEMF-001", pairingCode None (yerel istemci)."""
    _veri_koku_bozuk(monkeypatch, tmp_path)
    r = yerel.get("/api/health")
    assert r.status_code == 200, r.text[:300]
    g = r.json()
    assert g["status"] == "online"
    assert g["deviceId"] == "PEMF-001"
    assert g["pairingCode"] is None
    assert g["localIp"] == "192.168.1.50"


def test_saglik_SYNC_WORKER_yuklenemezse_cloudRegistry_unknown(yerel, kilitli_kok, lan_ip_sabit, monkeypatch):
    """registry durumu "ok" iken sağlık "ok" der; sync_worker içe aktarılamazsa → sağlık yine 200, `cloudRegistry` "unknown"."""
    from servers import sync_worker

    monkeypatch.setattr(sync_worker, "_sync_worker", types.SimpleNamespace(_registry_status="ok"))
    assert yerel.get("/api/health").json()["cloudRegistry"] == "ok"
    _modul_yok(monkeypatch, "servers.sync_worker")
    r = yerel.get("/api/health")
    assert r.status_code == 200, r.text[:300]
    assert r.json()["cloudRegistry"] == "unknown"


def test_saglik_AKTIF_TEDAVI_bilinemezse_sessionActive_TRUE_failsafe(yerel, kilitli_kok, lan_ip_sabit, monkeypatch):
    """loopback'te seans yokken `sessionActive` False; aktif-tedavi denetimi (update_manager) yüklenemezse → True (launcher ertelesin)."""
    assert yerel.get("/api/health").json()["sessionActive"] is False
    _modul_yok(monkeypatch, "servers.update_manager")
    r = yerel.get("/api/health")
    assert r.status_code == 200, r.text[:300]
    assert r.json()["sessionActive"] is True


def test_saglik_FIRMWARE_durumu_okunamazsa_None(yerel, kilitli_kok, lan_ip_sabit, monkeypatch):
    """oto-firmware durumu normalde sözlük; firmware_manager yüklenemezse → `firmwareGuncelleme` None, sağlık 200."""
    assert isinstance(yerel.get("/api/health").json()["firmwareGuncelleme"], dict)
    _modul_yok(monkeypatch, "servers.firmware_manager")
    r = yerel.get("/api/health")
    assert r.status_code == 200, r.text[:300]
    assert r.json()["firmwareGuncelleme"] is None


def test_saglik_ACILIS_NEDENI_uretilemezse_genel_DB_HAZIR_DEGIL_metni(
    yerel, api, kilitli_kok, lan_ip_sabit, monkeypatch
):
    """çekirdeğin açılış ayrıntısı bozuk (tek öğeli demet → nedeni üretmek IndexError) → dbReady False, dbSebep = katalogdaki
    'sistem.hata.dbHazirDegil' (yol / istisna metni SIZMAZ)."""
    cekirdek = types.SimpleNamespace(
        db_acilis_hatalari={"tedavi": "acilamadi"},
        db_acilis_ayrintilari={"tedavi": ("acilamadi",)},
        stm_is_connected=False,
    )
    monkeypatch.setattr(api.state, "core", cekirdek)
    r = yerel.get("/api/health")
    assert r.status_code == 200, r.text[:300]
    g = r.json()
    assert g["dbReady"] is False
    assert g["dbSebep"] == ceviri.t("sistem.hata.dbHazirDegil")
    assert "index" not in (g["dbSebep"] or "").lower()


# ── Sağlık DB / veri-kökü sorgusu (iş parçacığında) ──────────────────────────


def _saplama(app_data_dir, kayit_db_hazir):
    return types.SimpleNamespace(_app_data_dir=app_data_dir, _kayit_db_hazir=kayit_db_hazir)


def _oserr():
    raise OSError("veri koku yok (aparat)")


def test_saglik_db_durumu_YARDIMCILAR_istisna_atarsa_None_False_bos(kok):
    """`_app_data_dir` OSError + `_kayit_db_hazir` RuntimeError → (None, False, "") — istisna sızmaz."""

    def _hazir():
        raise RuntimeError("hazirlik denetimi coktu")

    assert sr._saglik_db_durumu(_saplama(_oserr, _hazir)) == (None, False, "")


def test_saglik_db_durumu_dongu_disi_ANAHTARSIZ_ve_BaseException_ile_dusen_sorgu_ASILMAZ(kok):
    """anahtar üretilemez (veri kökü OSError) ve sorgu iş parçacığında BaseException ile düşer → bekleyen asılmaz, (None, False, "");
    uçuş None anahtarla kaydedilir."""

    def _hazir():
        raise _Kesinti()

    sonuc = _kos(sr._saglik_db_durumu_dongu_disi(_saplama(_oserr, _hazir), sinir_sn=5.0))
    assert sonuc == (None, False, "")
    assert sr._saglik_db_ucusta[0] is None
    assert sr._saglik_db_ucusta[1].done()


def test_veri_koku_agda_dongu_disi_ANAHTARSIZ_ve_kok_okunamazsa_None(kok):
    """veri kökü her çağrıda OSError → anahtar None, sonuç None (bilinmiyor; arayüz susar)."""
    sonuc = _kos(sr._veri_koku_agda_dongu_disi(_saplama(_oserr, None), sinir_sn=5.0))
    assert sonuc is None
    assert sr._veri_agda_ucusta[0] is None


def test_veri_koku_agda_dongu_disi_SORGU_BaseException_ile_duserse_None_karsit_yerel_disk_False(kok, tmp_path):
    """karşıt: tmp (yerel disk) → False. Anahtar üretildikten sonra sorgu iş parçacığında BaseException → bekleyen asılmaz, None:
    iş parçacığı geleceği KENDİSİ None ile ÇÖZER (done, sonucu None) — zaman aşımı yolundan (sınır 5 sn; gelecek çözülmeden kalır)
    dönen None ile karışmaz."""
    from utils import path_utils as _pu

    assert _kos(sr._veri_koku_agda_dongu_disi(_saplama(lambda: tmp_path, None), sinir_sn=5.0)) is False
    sr._veri_agda_ucusta[1].result(timeout=5)
    sayac = {"n": 0}

    def _kok():
        sayac["n"] += 1
        if sayac["n"] == 1:
            return tmp_path / "ikinci"
        raise _Kesinti()

    sonuc = _kos(sr._veri_koku_agda_dongu_disi(_saplama(_kok, None), sinir_sn=5.0))
    assert sonuc is None
    assert sr._veri_agda_ucusta[0] == (str(tmp_path / "ikinci"), id(_pu._surucu_turu))
    assert sayac["n"] == 2
    gelecek = sr._veri_agda_ucusta[1]
    assert gelecek.done(), (
        "gelecek çözülmedi — bekleyen zaman aşımı yolundan döndü (BaseException iş parçacığından kaçtı)"
    )
    assert gelecek.result(timeout=0) is None


# ── /favicon.ico ─────────────────────────────────────────────────────────────


def test_favicon_KAYNAK_AGACINDAKI_tek_ikon_dosyasini_doner(yerel):
    """kaynak ağacı → 200, `image/x-icon`, gövde = pemf_gui/resources/icons/pemf_heart_emf_icon.ico baytları."""
    from utils.path_utils import kaynak_kokunu_bul

    ico = kaynak_kokunu_bul(sr.__file__) / "pemf_gui" / "resources" / "icons" / "pemf_heart_emf_icon.ico"
    r = yerel.get("/favicon.ico")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/x-icon")
    assert r.content == ico.read_bytes()


def _donmus(monkeypatch, meipass, exe_dizini):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dizini / "PEMF_Backend.exe"))


def _ikon(kok_dizin, veri):
    p = kok_dizin / "pemf_gui" / "resources" / "icons"
    p.mkdir(parents=True)
    (p / "pemf_heart_emf_icon.ico").write_bytes(veri)


def test_favicon_DONMUS_meipass_bossa_EXE_dizinindeki_ikonu_doner(tmp_path, monkeypatch):
    """donmuş: _MEIPASS'ta ikon yok, EXE dizininde var → 200 + EXE dizinindeki baytlar."""
    mei, exe = tmp_path / "mei", tmp_path / "exe"
    mei.mkdir()
    exe.mkdir()
    _ikon(exe, b"EXE-IKON")
    _donmus(monkeypatch, mei, exe)
    y = _kos(sr.favicon())
    assert y.status_code == 200
    assert y.media_type == "image/x-icon"
    assert y.body == b"EXE-IKON"


def test_favicon_ERISILEMEYEN_aday_atlanir_hicbiri_yoksa_204(tmp_path, monkeypatch):
    """donmuş: _MEIPASS adayının varlık denetimi EACCES (PermissionError) → aday atlanır; EXE dizininde de yok → 204, gövde boş."""
    mei, exe = tmp_path / "mei", tmp_path / "exe"
    mei.mkdir()
    exe.mkdir()
    _ikon(mei, b"MEI-IKON")
    _donmus(monkeypatch, mei, exe)
    hedef = mei / "pemf_gui" / "resources" / "icons" / "pemf_heart_emf_icon.ico"
    orj = pathlib.Path.exists
    denenen = []

    def _exists(self):
        if str(self) == str(hedef):
            denenen.append(str(self))
            raise PermissionError(13, "Erisim engellendi", str(self))
        return orj(self)

    monkeypatch.setattr(pathlib.Path, "exists", _exists)
    y = _kos(sr.favicon())
    assert y.status_code == 204
    assert y.body == b""
    assert len(denenen) == 2  # _MEIPASS iki kez aday (kaynak kökü = _MEIPASS + açık _MEIPASS)


# ── /api/kpi/summary ─────────────────────────────────────────────────────────


@pytest.fixture
def tdb(api, tmp_path, monkeypatch):
    """Gerçek TreatmentHistoryDB (tmp); `_get_treatment_db` onu döndürür (sözleşme: DB ya da None). Test sonunda kapatılır."""
    from database.treatment_history_db import TreatmentHistoryDB

    d = tmp_path / "tdb"
    d.mkdir()
    db = TreatmentHistoryDB(d)
    monkeypatch.setattr(api, "_get_treatment_db", lambda: db)
    yield db
    db.close()


def _seans(db, n=1):
    ids = []
    for _ in range(n):
        sid = db.start_session(treatment_mode="Manuel", target_condition="kp", patient_name="Pamuk")
        db.end_session(sid, duration_minutes=10)
        ids.append(sid)
    return ids


VARSAYILAN_KPI = {
    "totalSessions": 0,
    "completedSessions": 0,
    "stoppedSessions": 0,
    "avgDurationMin": 0.0,
    "coilUsage": {str(i): 0 for i in range(1, 9)},
    "modeDistribution": {},
    "last7Days": [],
}


def test_kpi_DB_YOKSA_sifir_sonuc(api, monkeypatch, caplog):
    """`_get_treatment_db()` None (DB erişilemez) → varsayılan sıfır sonuç (anahtarlar tam, last7Days boş) SESSİZCE döner:
    DB'nin olmaması arıza değildir → 'KPI ozeti hesaplanamadi' istisna kaydı (yığın izli ERROR) YAZILMAZ; aksi her panel
    yoklamasında günlüğe yığın izi basılır. (Aynı kaydın caplog'a düştüğü test_kpi_SEANS_TABLOSU_yoksa… ile kanıtlı.)"""
    monkeypatch.setattr(api, "_get_treatment_db", lambda: None)
    with caplog.at_level(logging.ERROR):
        assert sr.get_kpi_summary() == VARSAYILAN_KPI
    assert _kayitlar(caplog, "KPI ozeti hesaplanamadi") == []
    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []


def test_kpi_BOBIN_KULLANIMI_yalniz_1_8_sayilir(tdb, yerel):
    """bobin 2'de 3 koşu + bobin 9'da 1 koşu → coilUsage["2"] == 3, "9" anahtarı YOK, diğerleri 0; toplam seans 2."""
    sids = _seans(tdb, 2)
    with tdb._get_connection() as c:
        for coil in (2, 2, 2, 9):
            c.execute(
                "INSERT INTO session_coil_runs (session_id, coil_id, started_epoch, created_at) VALUES (?, ?, 1.0, 1.0)",
                (sids[0], coil),
            )
        c.commit()
    g = yerel.get("/api/kpi/summary").json()
    assert g["totalSessions"] == 2 and g["completedSessions"] == 2
    assert g["coilUsage"] == {**{str(i): 0 for i in range(1, 9)}, "2": 3}
    assert "9" not in g["coilUsage"]


def test_kpi_KOSU_TABLOSU_yoksa_bobin_0_ama_seans_sayimlari_DONER(tdb):
    """session_coil_runs tablosu yok → coilUsage hepsi 0; seans sayımları ve son 7 gün yine dolu."""
    _seans(tdb, 3)
    with tdb._get_connection() as c:
        c.execute("DROP TABLE session_coil_runs")
        c.commit()
    g = sr.get_kpi_summary()
    assert g["coilUsage"] == {str(i): 0 for i in range(1, 9)}
    assert g["totalSessions"] == 3 and g["completedSessions"] == 3
    assert len(g["last7Days"]) == 7 and sum(d["count"] for d in g["last7Days"]) == 3


def test_kpi_SEANS_TABLOSU_yoksa_sifir_sonuc_ve_istisna_GUNLUKTE(tdb, caplog):
    """treatment_sessions tablosu yok → varsayılan sıfır sonuç (yarım güncelleme YOK) + 'KPI ozeti hesaplanamadi' istisna kaydı."""
    with tdb._get_connection() as c:
        c.execute("DROP TABLE treatment_sessions")
        c.commit()
    with caplog.at_level(logging.ERROR):
        g = sr.get_kpi_summary()
    assert g == VARSAYILAN_KPI
    k = _kayitlar(caplog, "KPI ozeti hesaplanamadi")
    assert k and k[0].exc_info is not None


# ── /api/client/error ────────────────────────────────────────────────────────


BUYUK = 2_000_001


def test_istemci_hatasi_2MB_asinca_DONDURULUR_eski_yedek_EZILIR(yerel, kok):
    """günlük > 2 MB ve `.1` var → eski `.1` silinir, günlük `.1` olur (içerik aynen), yeni günlükte YALNIZ bu kayıt."""
    gun = kok / "client_errors.jsonl"
    gun.write_bytes(b"E" * BUYUK)
    (kok / "client_errors.jsonl.1").write_text("ONCEKI", encoding="utf-8")
    r = yerel.post("/api/client/error", json={"message": "cokme", "stack": "s", "route": "/r"})
    assert r.status_code == 200 and r.json() == {"status": "ok"}
    assert (kok / "client_errors.jsonl.1").read_bytes() == b"E" * BUYUK
    satirlar = gun.read_text(encoding="utf-8").splitlines()
    assert len(satirlar) == 1
    rec = json.loads(satirlar[0])
    assert (rec["message"], rec["stack"], rec["route"]) == ("cokme", "s", "/r")


def test_istemci_hatasi_DONDURME_duserse_gunluk_KESILIR_kayit_yazilir(yerel, kok):
    """`.1` bir DİZİN (silinemez) → döndürme düşer; günlük boşaltılır ve yalnız yeni kayıt yazılır; dizin yerinde."""
    gun = kok / "client_errors.jsonl"
    gun.write_bytes(b"E" * BUYUK)
    (kok / "client_errors.jsonl.1").mkdir()
    r = yerel.post("/api/client/error", json={"message": "m2"})
    assert r.status_code == 200 and r.json() == {"status": "ok"}
    satirlar = gun.read_text(encoding="utf-8").splitlines()
    assert len(satirlar) == 1 and json.loads(satirlar[0])["message"] == "m2"
    assert (kok / "client_errors.jsonl.1").is_dir()


def test_istemci_hatasi_GUNLUK_YAZILAMAZSA_da_200_ve_istisna_GUNLUKTE(yerel, kok, caplog):
    """günlük salt-okunur + `.1` dizin → kesme de ekleme de düşer; yanıt yine 200 {"status":"ok"}, dosya AYNEN, istisna günlükte."""
    gun = kok / "client_errors.jsonl"
    gun.write_bytes(b"E" * BUYUK)
    (kok / "client_errors.jsonl.1").mkdir()
    os.chmod(gun, stat.S_IREAD)
    try:
        with caplog.at_level(logging.ERROR, logger="system_router"):
            r = yerel.post("/api/client/error", json={"message": "m3"})
        assert r.status_code == 200 and r.json() == {"status": "ok"}
        assert gun.stat().st_size == BUYUK
        k = _kayitlar(caplog, "client error log yaz")
        assert k and k[0].exc_info is not None
    finally:
        os.chmod(gun, stat.S_IREAD | stat.S_IWRITE)


# ── Kurtarma kodu / onay ─────────────────────────────────────────────────────


def test_kurtarma_kodu_OKUNAMAZSA_500_ve_katalog_iletisi(yerel, kok, caplog):
    """kod dosyası geçersiz UTF-8 → 500, detail = 'sistem.hata.kurtarmaOkunamadi'; içerik dönmez; istisna günlükte."""
    from utils.backup_recovery import CODE_FILE_NAME

    (kok / CODE_FILE_NAME).write_bytes(b"\xff\xfeKOD\xff")
    with caplog.at_level(logging.ERROR, logger="system_router"):
        r = yerel.get("/api/system/recovery-code")
    assert r.status_code == 500
    assert r.json()["detail"] == ceviri.t("sistem.hata.kurtarmaOkunamadi")
    assert "content" not in r.json()
    assert _kayitlar(caplog, "kurtarma kodu okunamadi")


def test_kurtarma_onayi_ISARET_yazilamazsa_onay_YINE_gecerli_ve_uyari(yerel, kok, caplog):
    """onay işareti yolu bir DİZİN → işaret yazılamaz (uyarı günlükte) ama onay 200 ve durum ucunda acknowledged=True, warn=False."""
    from utils.backup_recovery import CODE_FILE_NAME, ONAY_ISARETI_ADI

    (kok / CODE_FILE_NAME).write_text("KOD: ABCDE-FGHIJ-KLMNO-PQRST-UVWXY-Z2345\n", encoding="utf-8")
    (kok / ONAY_ISARETI_ADI).mkdir()
    with caplog.at_level(logging.WARNING, logger="system_router"):
        r = yerel.post("/api/system/recovery-ack", json={})
    assert r.status_code == 200 and r.json() == {"status": "success"}
    assert _kayitlar(caplog, "kurtarma onay isareti yazilamadi")
    assert (kok / ONAY_ISARETI_ADI).is_dir()
    g = yerel.get("/api/system/recovery-status").json()
    assert g["acknowledged"] is True and g["warn"] is False


def test_kurtarma_onayi_DB_ACILAMAZSA_500_ve_katalog_iletisi(yerel, kilitli_kok, caplog):
    """tedavi DB'si açılışta açılamamış → onay yazılamaz: 500, detail = 'sistem.hata.onayKaydedilemedi'; istisna günlükte."""
    with caplog.at_level(logging.ERROR, logger="system_router"):
        r = yerel.post("/api/system/recovery-ack", json={})
    assert r.status_code == 500
    assert r.json()["detail"] == ceviri.t("sistem.hata.onayKaydedilemedi")
    assert _kayitlar(caplog, "kurtarma onayi yazilamadi")


# ── Saklama / denetim izi / destek paketi ────────────────────────────────────


def test_saklama_durumu_DB_ACILAMAZSA_500_ayarOkunamadi(yerel, kilitli_kok):
    """GET /api/settings/retention, tedavi DB'si açılamaz → 500, detail = 'sistem.hata.ayarOkunamadi'."""
    r = yerel.get("/api/settings/retention")
    assert r.status_code == 500
    assert r.json()["detail"] == ceviri.t("sistem.hata.ayarOkunamadi")


def test_denetim_izi_DB_ACILAMAZSA_500_denetimOkunamadi(yerel, kilitli_kok):
    """GET /api/audit/events, tedavi DB'si açılamaz → 500, detail = 'sistem.hata.denetimOkunamadi'."""
    r = yerel.get("/api/audit/events")
    assert r.status_code == 500
    assert r.json()["detail"] == ceviri.t("sistem.hata.denetimOkunamadi")


def test_destek_paketi_URETICI_yuklenemezse_500_destekPaketi(yerel, kilitli_kok, monkeypatch):
    """destek paketi modülü içe aktarılamaz → 500, detail = 'sistem.hata.destekPaketi' (veri dönmez)."""
    _modul_yok(monkeypatch, "utils.support_bundle")
    r = yerel.post("/api/support/bundle", json={})
    assert r.status_code == 500
    assert r.json()["detail"] == ceviri.t("sistem.hata.destekPaketi")
    assert "data_b64" not in r.json()


def test_destek_paketi_DENETIM_IZI_modulu_yoksa_paket_YINE_doner(yerel, kilitli_kok, monkeypatch, tmp_path):
    """denetim izi modülü içe aktarılamaz → paket yine 200: zip'te OZET.json + logs/backend.log, özet 'alinan_dosyalar' = [backend.log]."""
    loglar = tmp_path / "loglar"
    loglar.mkdir()
    (loglar / "backend.log").write_text("satir-1\n", encoding="utf-8")
    monkeypatch.setenv("PEMF_LOG_DIR", str(loglar))
    _modul_yok(monkeypatch, "servers.audit_log")
    r = yerel.post("/api/support/bundle", json={})
    assert r.status_code == 200, r.text[:300]
    g = r.json()
    assert g["status"] == "success"
    assert g["summary"]["alinan_dosyalar"] == ["backend.log"]
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(g["data_b64"]))) as z:
        adlar = set(z.namelist())
        assert {"OZET.json", "logs/backend.log"} <= adlar
        assert "satir-1" in z.read("logs/backend.log").decode("utf-8")


def test_saklama_durumu_HASTA_DB_acilamazsa_anonim_bekleyen_None_ve_uyari(yerel, kok, monkeypatch, caplog):
    """hasta DB'si açılışta açılamamış → GET retention 200; anonymization.pending None ("0 bekleyen" yalanı YOK) + uyarı günlükte."""
    from database import patient_database as pdbm
    from utils.path_utils import get_app_data_directory

    monkeypatch.setattr(pdbm, "_patient_db", None)
    monkeypatch.setitem(
        pdbm._acilis_kilidi, pdbm._kilit_anahtari(get_app_data_directory() / "patients.db"), "OperationalError"
    )
    with caplog.at_level(logging.WARNING, logger="system_router"):
        r = yerel.get("/api/settings/retention")
    assert r.status_code == 200, r.text[:300]
    an = r.json()["anonymization"]
    assert an["pending"] is None
    assert an["acknowledged"] is False
    assert _kayitlar(caplog, "KVKK anonimlestirme bekleyen sayisi okunamadi")


def test_son_anonim_turu_IZ_OKUNAMAZSA_None_ve_uyari(caplog):
    """denetim izi okuması OperationalError → None (tur bilgisi uydurulmaz) + uyarı günlükte."""
    import sqlite3

    def _oku(*a, **k):
        raise sqlite3.OperationalError("database is locked")

    with caplog.at_level(logging.WARNING, logger="system_router"):
        assert sr._son_anonim_turu(types.SimpleNamespace(denetim_oku=_oku)) is None
    assert _kayitlar(caplog, "son anonimlestirme turu okunamadi")


# ── /api/jeton/bakiye ────────────────────────────────────────────────────────


def test_jeton_bakiye_KAPALIYKEN_etkin_false_ACIKKEN_kimliksiz_bilinmiyor(yerel, monkeypatch):
    """ücretlendirme kapalı → {"etkin": False}; açık + Bearer yok → {"etkin": True, "bilinmiyor": True, "sebep": "kimlik_yok"}."""
    from servers import jeton

    monkeypatch.setattr(jeton, "JETON_ENFORCED", False)
    assert yerel.get("/api/jeton/bakiye").json() == {"etkin": False}
    monkeypatch.setattr(jeton, "JETON_ENFORCED", True)
    r = yerel.get("/api/jeton/bakiye")
    assert r.status_code == 200
    assert r.json() == {"etkin": True, "bilinmiyor": True, "sebep": "kimlik_yok"}
