# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Y200 (sahip · S-D3I.1 + S-D3I.6) — ESKİ KÖK GÖÇÜ BİR DB'Yİ ATLARSA HASTA DB'si AÇILMAZ, BOŞ DB KURULMAZ ("göç bekliyor" kısıtlı kip,
ACİL DURDUR + STOP çalışır, her açılışta yeniden denenir, operatöre çıkış yolu TR + EN) · KALICI "eski kök göçü tamamlandı" İŞARETİ.

ÖLÇÜLEN KUSUR (HEAD `ebf1c3fe`, GERÇEK `backend_service.main()` alt süreçte, sahte yalnız EN ALT katta): `_dosyalari_gocur`
`_tasinabilir_mi` False dalında (hedefte FARKLI at-rest / alan anahtarı; kaynak o an OKUNAMIYOR → `_sifreli_mi` onu "şifreli" sayar →
anahtarsız kurulumda taşınamaz) yalnız ERROR yazıp geçiyordu: `_GOC_ENGELI` boş → hasta DB kurucusu hedefte BOŞ `patients.db` KURUYOR
(`dbReady` true, hasta listesi `[]` — veteriner için veri kaybından ayırt edilemez "boş klinik") ve sonraki açılışlarda göç HİÇ
denenmiyordu (hedefte dosya var → atla); kilit kalksa da klinik kalıcı olarak boş görüyordu. Okunamayan düz-metin kaynak için günlük
YANLIŞ neden yazıyordu ("ŞİFRELİ ve … anahtarı FARKLI"). Kalıcı işaret yoktu: göç yalnız süreç başına bir kez (`_GOC_YAPILDI`).

SÖZLEŞME: atlanan DB için engel yazılır (neden günlükte ayrı) → kurucu `EskiKokGocuBekliyorHatasi` (`GocBekliyorHatasi` türevi) ile
AÇMAZ → DB'siz kısıtlı kip (Y9), `/api/health` `dbSebep` eski kök göçünün çıkış yolunu söyler (istek dilinde); arka planda (Y43 / Y61) ve
her yeni açılışta yeniden denenir; kaynak bayt bayt AYNI. Göç ATLAMASIZ bitince hedefe `.eski_kok_gocu_tamam` (yalnız kök ÖZETİ + zaman —
yol / sır YOK) yazılır; işaret o kökü listeledikçe eski kökten bir daha ne DB ne anahtar getirilir (hedefteki DB sonradan yok olsa da);
başka eski kök (Y182 ikinci hesap) kendi tek seferlik göçünü yapar. Atlama / engel varken işaret YAZILMAZ; yazılamazsa göç başarılı kalır.
"""

from __future__ import annotations

import builtins
import hashlib
import json
import logging
import re
import sys
from pathlib import Path

# Ürün modülleri (headless_core, database.*) MODÜL düzeyinde — fikstür `APPDATA`'yı sahte eski köke çevirmeden ÖNCE — içe aktarılır:
# içe aktarma sırasında veri kökü çözülürse göç hiçbir yere koşmaz (conftest: APPDATA = PEMF_DATA_DIR → aynı dizin → göç yok).
import headless_core
import pytest
from betik_alt_sureci import kostur, yalitik_ortam
from database import patient_database as pdb_mod
from database import sqlcipher_util as su
from database import treatment_history_db as thdb_mod

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="göç yalnız Windows'ta koşar (path_utils)")

KOK = Path(__file__).resolve().parents[1]
TESTLER = Path(__file__).resolve().parent
BACKEND = KOK / "apps" / "backend"
ISARET = ".eski_kok_gocu_tamam"
DUZ_DB = b"SQLite format 3\x00" + b"ESKI-KOK" * 8
SIFRELI_DB = b"\x00\x01SIFRELI-SEANS-SAYFASI" * 4

#: Operatör iletisi — TR BAYT BAYT (Y200 ile eklendi), EN karşılığı. `{{ad}}` = "Hasta veritabanı" / "Patient database".
TR_ESKI_KOK = (
    "{ad} açılmadı: eski veri klasöründeki kayıtlar yeni klasöre taşınamadı (dosya kilitli, disk dolu ya da anahtarı farklı "
    "olabilir). Boş veritabanı kurulmadı, eski dosya korunuyor; taşıma arka planda ve her açılışta yeniden deneniyor. Eski dosyayı "
    "SİLMEYİN: dosyayı açık tutan programı (virüs tarayıcı, yedekleme) kapatın, disk alanını denetleyin ve cihazı yeniden başlatın; "
    "sürerse teknik desteğe başvurun (eski dosyanın yeri günlükteki VERİ GÖÇÜ satırında)."
)
EN_ESKI_KOK = (
    "{ad} was not opened: the records in the old data folder could not be moved to the new folder (the file may be locked, the disk "
    "may be full or its key may be different). No empty database was created and the old file is preserved; the move is being "
    "retried in the background and at every start. Do NOT delete the old file: close any program keeping it open (antivirus, "
    "backup), check the free disk space and restart the device; if it persists, contact technical support (the data migration line "
    "in the log shows where the old file is)."
)


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _goruntu(d: Path) -> dict:
    return {p.name: _sha(p) for p in d.iterdir() if p.is_file()}


# ─────────────────────────── uçtan uca: ayrı açılışlar (alt süreç, GERÇEK main(), sahte yalnız kaynağın open'ı) ───────────────────────────

_SURUCU = r"""
import sys
sys.path.insert(0, {testler!r})
import alt_surec_ag_bekcisi as _ag
sys.path.remove({testler!r})
import builtins, json, logging, os, time
sys.path[:0] = [{kok!r}, {backend!r}]
KIP, KILITLI = {kip!r}, {kilitli!r}
sonuc = {{"kip": KIP}}
GUNLUK = []
import utils.path_utils as _pu

class _Topla(logging.Handler):
    def emit(self, r):
        m = r.getMessage()
        if "GÖÇ" in m:
            GUNLUK.append(r.levelname + " " + m[:200])
logging.getLogger("utils.path_utils").addHandler(_Topla())
if KILITLI:
    # Sahte EN ALT katta: YALNIZ eski kökteki hasta DB'sinin `open`'ı paylaşım ihlali (AV / yedekleyici kilidi). Gerisi gerçek.
    _kaynak = os.path.normcase(os.path.join(os.environ["APPDATA"], "PEMF_GUI", "patients.db"))
    _o_open = builtins.open
    def _open(dosya, *a, **k):
        if isinstance(dosya, (str, os.PathLike)) and os.path.normcase(os.path.abspath(str(dosya))) == _kaynak:
            raise PermissionError(13, "sahte: dosya baska bir islem tarafindan kullaniliyor", str(dosya))
        return _o_open(dosya, *a, **k)
    builtins.open = _open

if KIP in ("eski", "hedef_anahtar"):
    from database.patient_database import get_patient_database
    from utils.path_utils import get_app_data_directory
    app = get_app_data_directory()
    pdb = get_patient_database()
    if KIP == "eski":
        for i in range(2):
            pdb.add_patient({{"name": "EskiHasta%d" % i, "species": "kedi"}})
        with pdb._get_connection() as cn:
            cn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    c = getattr(pdb._local, "conn", None)
    if c is not None:
        c.close()
    sonuc["kok"] = str(app)
    if KIP == "hedef_anahtar":
        # Hedef KENDİ alan anahtarını üretti (gerçek ürün yolu); hasta DB'si sonra yok (kullanılmış kök, DB'si kaldırılmış / hiç yerleşmemiş).
        for ek in ("", "-wal", "-shm"):
            p = os.path.join(str(app), "patients.db" + ek)
            if os.path.exists(p):
                os.remove(p)
else:
    import headless_core as _hc
    _hc.HeadlessCore.DB_YENIDEN_DENEME_ARALIKLARI_SN = (0.1, 0.2, 0.3)
    DENEME = []
    _o_dene = _pu.goc_engelini_yeniden_dene
    def _dene(db):
        r = _o_dene(db)
        # engel, denemeyi yapan iş parçacığında deneme BİTİNCE okunur (deneme sürerken `pop` penceresi var — yarış yok)
        DENEME.append([os.path.basename(str(db)), r, _pu.goc_engeli(db)])
        return r
    _pu.goc_engelini_yeniden_dene = _dene
    import backend_service as bs
    bs._start_cloud_sync = lambda logger: None
    bs._start_update_checker_safe = lambda logger: None
    bs._donanim_guncellemesi_kur = lambda core, logger, event_bus=None: None
    bs._donanim_guncellemesi_safe = lambda core, logger: None
    bs._start_db_maintenance = lambda core, logger: None
    bs._harden_secret_file_acls = lambda d, logger: None
    import utils.agir_import as _ai
    _ai.torch_isit = lambda *a, **k: None
    import servers.auto_discovery as _ad
    _ad._get_local_ip = lambda: "127.0.0.1"
    HEDEF = os.path.join(os.environ["PEMF_DATA_DIR"], "PEMF_GUI")

    class _Casus:
        should_exit = False
        force_exit = False

        def run(self):
            from fastapi.testclient import TestClient
            from servers import api_server as api
            c = TestClient(api.app, client=("127.0.0.1", 50077), raise_server_exceptions=False)
            def saglik(dil=None):
                r = c.get("/api/health", headers={{"X-PEMF-Dil": dil}} if dil else None)
                g = r.json() if r.status_code == 200 else {{}}
                return {{"kod": r.status_code, "dbReady": g.get("dbReady"), "dbSebep": g.get("dbSebep")}}
            sonuc["saglik"] = saglik()
            sonuc["saglik_en"] = saglik("en")
            son = time.monotonic() + 20
            while len([d for d in DENEME if d[0] == "patients.db"]) < 2 and sonuc["saglik"]["dbReady"] is False and time.monotonic() < son:
                time.sleep(0.05)
            sonuc["deneme"] = list(DENEME)
            sonuc["saglik_sonra"] = saglik()
            sonuc["estop"] = c.post("/api/hardware/emergency_stop").status_code
            sonuc["stop"] = c.post("/api/session/stop", json={{}}).status_code
            # Arka plan denemesi engeli `pop` edip yeniden koyar — ölçüm o pencereye denk gelmesin diye kısa örnekleme (ilk dolu değer)
            sonuc["engel"] = None
            son = time.monotonic() + 1.0
            while sonuc["engel"] is None and time.monotonic() < son:
                sonuc["engel"] = _pu.goc_engeli(os.path.join(HEDEF, "patients.db"))
                if sonuc["engel"] is None:
                    time.sleep(0.02)
            try:
                from database.patient_database import get_patient_database
                sonuc["hastalar"] = sorted(str(h.get("name")) for h in get_patient_database().get_all_patients())
            except Exception as e:
                sonuc["hastalar"] = "HATA " + type(e).__name__
            sonuc["hedef"] = sorted(os.listdir(HEDEF))

    bs._build_server = lambda app, args: _Casus()
    try:
        sonuc["rc"] = bs.main(["--host", "127.0.0.1", "--port", "51995", "--no-headless-services"])
    except BaseException as e:
        import traceback
        sonuc["kacan"] = type(e).__name__ + ": " + str(e)[:300]
        sonuc["iz"] = traceback.format_exc()[-1500:]
sonuc["gunluk"] = GUNLUK
sonuc["ag"] = _ag.ENGELLENEN
print("SONUC " + json.dumps(sonuc, ensure_ascii=False, default=str))
sys.stdout.flush()
os._exit(0)
"""


def _kos(tmp_path: Path, ad: str, kip: str, ev: str, makine: str | None, kilitli: bool = False) -> dict:
    env = yalitik_ortam(tmp_path / ev)
    env.update(
        {
            "PEMF_DEVICE_IDENTITY_DIR": str(tmp_path / "kimlik"),
            "PEMF_CLOUD_PROVISION_PATH": str(tmp_path / "yok" / "p.json"),
            "PEMF_CLOUD_PATIENT_SYNC": "0",
            "SUPABASE_URL": "http://127.0.0.1:9",
            "PEMF_LOG_DIR": str(tmp_path / f"log_{ad}"),
            "PEMF_ESP_ENABLED": "0",
            "PEMF_FW_AUTO_UPDATE": "0",
            "PEMF_HOTSPOT": "0",
            "PEMF_AI_WARMUP": "0",
            "PEMF_ENABLE_TUNNEL": "0",
            "PEMF_ENCRYPT_AT_REST": "0",
        }
    )
    if makine:
        env["PEMF_DATA_DIR"] = str(tmp_path / makine)
    betik = tmp_path / f"surucu_{ad}.py"
    betik.write_text(
        _SURUCU.format(testler=str(TESTLER), kok=str(KOK), backend=str(BACKEND), kip=kip, kilitli=kilitli),
        encoding="utf-8",
    )
    p = kostur([str(betik)], cwd=tmp_path, env=env, sure=420)
    satir = [s for s in p.stdout.splitlines() if s.startswith("SONUC ")]
    assert p.returncode == 0 and satir, f"{ad} çocuğu düştü rc={p.returncode}: {p.stderr[-1500:]}"
    s = json.loads(satir[-1][len("SONUC ") :])
    assert "kacan" not in s and s["ag"] == [], f"{ad}: {s}"
    return s


def _atlandi(s: dict) -> list[str]:
    return [g for g in s["gunluk"] if g.startswith("ERROR VERİ GÖÇÜ ATLANDI: patients.db")]


@pytest.mark.parametrize("kol", ["alan_anahtari_farkli", "kaynak_okunamiyor"])
def test_KRITIK_Y200_atlanan_hasta_DBsi_ACILMAZ_bos_DB_KURULMAZ_ACIL_DURDUR_STOP_calisir_her_acilista_YENIDEN_denenir(
    tmp_path, kol
):
    """MUTASYON: atlama dalında engel yazılmaz (= HEAD) → KIRMIZI (boş DB kurulur, `dbReady` true, hastalar [])."""
    eski = tmp_path / "ev" / "appdata" / "PEMF_GUI"
    hedef = tmp_path / "makine" / "PEMF_GUI"
    e = _kos(tmp_path, "eski", "eski", "ev", None)
    assert Path(e["kok"]) == eski, e
    if kol == "alan_anahtari_farkli":
        h = _kos(tmp_path, "hedef_anahtar", "hedef_anahtar", "ev2", "makine")
        assert Path(h["kok"]) == hedef and not (hedef / "patients.db").exists(), h
        assert json.loads((hedef / "pemf_secrets.json").read_text(encoding="utf-8"))["auto"].get("patient_fernet_key")
    once = _goruntu(eski)

    a1 = _kos(tmp_path, "acilis1", "main", "ev", "makine", kilitli=(kol == "kaynak_okunamiyor"))
    print(
        "OLCUM acilis1",
        {k: a1.get(k) for k in ("saglik", "saglik_sonra", "deneme", "estop", "stop", "engel", "hastalar")},
    )
    assert a1["saglik"]["kod"] == 200 and a1["saglik"]["dbReady"] is False, (
        f"atlanan hasta DB'si yerine BOŞ DB kuruldu / açıldı (boş klinik): {a1['saglik']} hastalar={a1['hastalar']}"
    )
    assert a1["saglik"]["dbSebep"] == TR_ESKI_KOK.format(ad="Hasta veritabanı"), a1["saglik"]["dbSebep"]
    assert a1["saglik_en"]["dbSebep"] == EN_ESKI_KOK.format(ad="Patient database"), a1["saglik_en"]["dbSebep"]
    assert "patients.db" not in a1["hedef"], f"hedefte BOŞ hasta DB'si kuruldu: {a1['hedef']}"
    # Y43 / Y61: arka plan yeniden açması göçü yeniden dener — atlama sürdükçe engel KALIR, boş DB yine kurulmaz
    denemeler = [d for d in a1["deneme"] if d[0] == "patients.db"]
    assert len(denemeler) >= 2, f"arka plan yeniden açması göçü yeniden DENEMEDİ: {a1['deneme']}"
    assert not any(d[1] or not d[2] for d in denemeler), f"arka plan denemesi engeli düşürdü: {a1['deneme']}"
    assert a1["saglik_sonra"]["dbReady"] is False, a1["saglik_sonra"]
    assert str(a1["hastalar"]).startswith("HATA"), f"hasta DB'si kısıtlı kipte açıldı: {a1['hastalar']}"
    assert a1["estop"] == 200 and a1["stop"] == 200, f"kısıtlı kipte ACİL DURDUR / STOP: {a1['estop']} / {a1['stop']}"
    neden = "kaynak okunamadi" if kol == "kaynak_okunamiyor" else "at-rest / alan anahtari hedefte FARKLI"
    assert a1["engel"] and neden in a1["engel"], f"engel nedeni: {a1['engel']}"
    assert any(f"({neden})" in g for g in _atlandi(a1)), f"günlük atlama nedenini söylemiyor: {a1['gunluk']}"
    assert ISARET not in a1["hedef"], (
        "atlama varken kalıcı 'göç tamam' işareti YAZILDI → sonraki açılış yeniden denemez"
    )
    assert _goruntu(eski) == once, "KAYNAK değişti / silindi"

    a2 = _kos(tmp_path, "acilis2", "main", "ev", "makine")  # YENİ süreç, kilit yok
    print("OLCUM acilis2", {k: a2.get(k) for k in ("saglik", "engel", "hastalar", "hedef")})
    assert _atlandi(a2) or kol == "kaynak_okunamiyor", f"ikinci açılışta göç yeniden DENENMEDİ: {a2['gunluk']}"
    if kol == "kaynak_okunamiyor":
        assert a2["saglik"]["dbReady"] is True and a2["hastalar"] == ["EskiHasta0", "EskiHasta1"], (
            f"kilit kalktı ama sonraki açılış göçü yeniden denemedi / taşımadı: {a2['saglik']} hastalar={a2['hastalar']}"
        )
        assert ISARET in a2["hedef"], "atlamasız göçten sonra kalıcı işaret yazılmadı"
    else:
        assert a2["saglik"]["dbReady"] is False and "patients.db" not in a2["hedef"], (
            f"ikinci açılışta BOŞ hasta DB'si kuruldu: {a2['saglik']} {a2['hedef']}"
        )
        assert a2["estop"] == 200 and a2["stop"] == 200 and ISARET not in a2["hedef"], a2
    assert _goruntu(eski) == once, "KAYNAK değişti / silindi (ikinci açılış)"


def test_KARSIT_Y200_temiz_goc_ve_goc_GEREKMEYEN_kurulum_DByi_ACAR_isaret_YALNIZ_temiz_gocte(tmp_path):
    """Aparat ve düzeltme yanlış alarm vermez: eski kök YOK → DB açılır, işaret yok; temiz göç → hastalar taşınır, DB açılır, işaret var."""
    g = _kos(tmp_path, "gocsuz", "main", "ev3", "makine3")
    assert g["saglik"]["dbReady"] is True and g["hastalar"] == [] and g["engel"] is None, g
    assert ISARET not in g["hedef"], "eski kök yokken 'göç tamam' işareti yazıldı"
    assert g["estop"] == 200 and g["stop"] == 200

    _kos(tmp_path, "eski", "eski", "ev", None)
    t = _kos(tmp_path, "temiz", "main", "ev", "makine")
    assert t["saglik"]["dbReady"] is True and t["hastalar"] == ["EskiHasta0", "EskiHasta1"] and t["engel"] is None, t
    assert ISARET in t["hedef"] and not _atlandi(t), t


# ─────────────────────────── süreç içi: göç kuralları (sahte eski / yeni kök, gerçek dosya sistemi, gerçek kurucular) ───────────────────────────


@pytest.fixture
def kokler(tmp_path, monkeypatch):
    from utils import path_utils as pu

    eski_appdata = tmp_path / "kullanici" / "AppData" / "Roaming"
    eski = eski_appdata / "PEMF_GUI"
    eski.mkdir(parents=True)
    yeni = tmp_path / "ProgramData" / "PEMF_System" / "PEMF_GUI"
    yeni.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(eski_appdata))
    monkeypatch.setattr(pu, "_GOC_YAPILDI", set())
    monkeypatch.setattr(pu, "_GOC_ENGELI", {})
    return pu, eski, yeni


def _sir_yaz(kok: Path, auto: dict) -> None:
    (kok / "pemf_secrets.json").write_text(json.dumps({"_version": 1, "auto": auto}), encoding="utf-8")


def _kilitle(monkeypatch, dosya: Path):
    """Sahte EN ALT katta: yalnız `dosya`nın `open`'ı PermissionError (paylaşım kilidi). Döner: kilidi kaldıran işlev."""
    gercek_open = builtins.open

    def _kilitli(d, *a, **k):
        if isinstance(d, (str, Path)) and str(d) == str(dosya):
            raise PermissionError(13, "sahte: dosya baska bir islem tarafindan kullaniliyor", str(d))
        return gercek_open(d, *a, **k)

    monkeypatch.setattr(builtins, "open", _kilitli)
    return lambda: monkeypatch.setattr(builtins, "open", gercek_open)


def _kur(kol: str, eski: Path, yeni: Path, monkeypatch) -> tuple[str, object]:
    """Atlama senaryosu: döner (atlanan DB adı, kilit kaldırıcı | None)."""
    (eski / "auth_users.db").write_bytes(DUZ_DB)
    if kol == "alan_anahtari":
        _sir_yaz(eski, {"patient_fernet_key": "KAYNAK-ALAN"})
        _sir_yaz(yeni, {"patient_fernet_key": "HEDEFIN-KENDI-ALAN"})
        (eski / "patients.db").write_bytes(DUZ_DB)
        return "patients.db", None
    if kol == "sqlcipher_anahtari":
        _sir_yaz(eski, {"sqlcipher_key": "KAYNAK-SQLCIPHER"})
        _sir_yaz(yeni, {"sqlcipher_key": "HEDEFIN-KENDI-SQLCIPHER"})
        (eski / "pemf_treatment_history.db").write_bytes(SIFRELI_DB)
        return "pemf_treatment_history.db", None
    (eski / "patients.db").write_bytes(DUZ_DB)  # anahtarsız kurulum, kaynak o an kilitli
    return "patients.db", _kilitle(monkeypatch, eski / "patients.db")


@pytest.mark.parametrize("kol", ["alan_anahtari", "sqlcipher_anahtari", "kaynak_okunamiyor"])
def test_KRITIK_Y200_atlanan_DB_ENGEL_alir_GERCEK_kurucu_ACMAZ_bos_DB_KURULMAZ(kokler, monkeypatch, caplog, kol):
    """İkiz atlama dalları (anahtar uyuşmazlığı ↔ okunamayan kaynak) — biri engel yazıp öteki yazmazsa KIRMIZI."""
    pu, eski, yeni = kokler
    ad, kilit_kaldir = _kur(kol, eski, yeni, monkeypatch)
    once = {p.name: p.read_bytes() for p in eski.iterdir()}
    with caplog.at_level(logging.WARNING):
        pu._kullanicidan_makineye_gocur(yeni)
    if kilit_kaldir:
        kilit_kaldir()
    engel = pu.goc_engeli(yeni / ad)
    assert engel, f"{ad} ATLANDI ama engel YAZILMADI → kurucu hedefte BOŞ DB kurar (boş klinik)"
    assert ("okunamadi" in engel) is (kol == "kaynak_okunamiyor"), f"engel nedeni yanlış: {engel}"
    with pytest.raises(su.EskiKokGocuBekliyorHatasi) as e:
        if ad == "patients.db":
            pdb_mod.PatientDatabase(str(yeni / ad))
        else:
            thdb_mod.TreatmentHistoryDB(yeni)
    assert isinstance(e.value, su.GocBekliyorHatasi), (
        "kısıtlı kip yakalayıcıları (GocBekliyorHatasi) bu istisnayı tanımaz"
    )
    assert not (yeni / ad).exists(), f"göçü atlanan yolda BOŞ {ad} kuruldu"
    assert (yeni / "auth_users.db").read_bytes() == DUZ_DB, "atlama öteki DB'lerin göçünü de durdurdu"
    assert {p.name: p.read_bytes() for p in eski.iterdir()} == once, "KAYNAK değişti / silindi"
    assert not (yeni / ISARET).exists(), "atlama varken 'göç tamam' işareti yazıldı"
    satir = [
        r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR and "VERİ GÖÇÜ ATLANDI" in r.getMessage()
    ]
    assert satir and ad in satir[0] and "SİLMEYİN" in satir[0], f"günlük atlamayı / çıkış yolunu söylemiyor: {satir}"


@pytest.mark.parametrize("kol", ["alan_anahtari", "kaynak_okunamiyor"])
def test_KRITIK_Y200_arka_plan_yeniden_denemesi_atlamada_ENGELI_korur_idempotent(kokler, monkeypatch, kol):
    """Y43 / Y61 yeniden açması (`goc_engelini_yeniden_dene`) atlama SÜRDÜKÇE engeli bırakmaz — iki tur üst üste."""
    pu, eski, yeni = kokler
    ad, kilit_kaldir = _kur(kol, eski, yeni, monkeypatch)
    pu._kullanicidan_makineye_gocur(yeni)
    for tur in (1, 2):
        assert pu.goc_engelini_yeniden_dene(yeni / ad) is False, f"tur {tur}: yeniden deneme engeli düşürdü"
        assert pu.goc_engeli(yeni / ad) and not (yeni / ad).exists(), f"tur {tur}: engel / hedef"
    if kilit_kaldir:
        kilit_kaldir()
        assert pu.goc_engelini_yeniden_dene(yeni / ad) is True and (yeni / ad).read_bytes() == DUZ_DB, (
            "kilit kalktı ama arka plan denemesi taşımadı"
        )


def test_KRITIK_Y200_YENI_surecte_yeniden_denenir_kilit_kalkinca_TASINIR_isaret_YAZILIR(kokler, monkeypatch):
    pu, eski, yeni = kokler
    ad, kilit_kaldir = _kur("kaynak_okunamiyor", eski, yeni, monkeypatch)
    pu._kullanicidan_makineye_gocur(yeni)
    kilit_kaldir()
    assert pu.goc_engeli(yeni / ad), "kaynak okunamadı ama engel YAZILMADI → kurucu BOŞ DB kurar"
    assert not (yeni / ISARET).exists(), "atlama varken kalıcı işaret yazıldı"
    pu._GOC_YAPILDI.clear()  # YENİ süreç (engel de süreç içidir)
    pu._GOC_ENGELI.clear()
    pu._kullanicidan_makineye_gocur(yeni)
    assert (yeni / ad).read_bytes() == DUZ_DB, "ikinci açılış göçü yeniden denemedi"
    assert pu.goc_engeli(yeni / ad) is None
    assert (yeni / ISARET).is_file(), "atlamasız göçten sonra kalıcı işaret yazılmadı"


@pytest.mark.parametrize("kol", ["artik", "kopya_dogrulanamadi"])
def test_KRITIK_Y200_ATLAMA_ya_da_ENGEL_varken_ISARET_YAZILMAZ(kokler, monkeypatch, kol):
    """İşaret yalnız ATLAMASIZ göçte. A2.6 artığı (güncel veri toparlanır) ve D3.37 doğrulanamayan kopya da atlama sayılır."""
    pu, eski, yeni = kokler
    (eski / "patients.db").write_bytes(DUZ_DB)
    (eski / "auth_users.db").write_bytes(DUZ_DB)
    if kol == "artik":
        (yeni / "patients.db.plain.bak").write_bytes(b"GUNCEL")
    else:
        gercek = pu.shutil.copy2

        def _dus(k, v, *a, **kw):
            if str(v).endswith("patients.db.goc.part"):
                raise OSError(28, "disk dolu (test)")
            return gercek(k, v, *a, **kw)

        monkeypatch.setattr(pu.shutil, "copy2", _dus)
    pu._kullanicidan_makineye_gocur(yeni)
    assert (yeni / "auth_users.db").exists(), "senaryo: öteki DB taşınmalı"
    assert not (yeni / ISARET).exists(), f"{kol}: atlama / engel varken kalıcı işaret yazıldı"


def test_KRITIK_Y200_isaret_varken_BAYAT_eski_kok_GETIRILMEZ_anahtar_da_TASINMAZ(kokler, monkeypatch):
    """Hedefteki DB sonradan yok olsa da (artık bırakmayan pencere / elle silme) eski kökün bayat kopyası GELMEZ; işaret ikinci turda
    değişmez (idempotens). MUTASYON: işaret OKUNMAZ → bayat kopya gelir → KIRMIZI."""
    pu, eski, yeni = kokler
    (eski / "patients.db").write_bytes(DUZ_DB)
    _sir_yaz(eski, {"patient_fernet_key": "ESKI-ALAN"})
    pu._kullanicidan_makineye_gocur(yeni)
    assert (yeni / "patients.db").read_bytes() == DUZ_DB, "senaryo: temiz göç taşımalı"
    assert (yeni / ISARET).is_file(), "atlamasız göçten sonra kalıcı işaret yazılmadı"
    isaret_once = (yeni / ISARET).read_bytes()

    (yeni / "patients.db").unlink()  # hedef DB'si yok oldu — A2.6 artığı YOK
    (yeni / "pemf_secrets.json").unlink()
    cagri = []
    monkeypatch.setattr(pu, "_kopyala_dogrula", lambda k, v: cagri.append(("kopya", Path(v).name)) or None)
    monkeypatch.setattr(
        pu, "_sqlcipher_anahtarini_gocur", lambda e, h, a="sqlcipher_key": cagri.append(("anahtar", a)) or False
    )
    pu._GOC_YAPILDI.clear()  # YENİ süreç
    pu._kullanicidan_makineye_gocur(yeni)
    assert not (yeni / "patients.db").exists() and cagri == [], f"işaret varken eski kök yeniden okundu: {cagri}"
    assert (yeni / ISARET).read_bytes() == isaret_once, "ikinci turda işaret değişti"


def test_KRITIK_Y200_isaret_KOKE_ozgu_YOL_ve_SIR_icermez_ikinci_hesap_kendi_gocunu_yapar(kokler, monkeypatch, tmp_path):
    pu, eski, yeni = kokler
    # Sahte sır değerleri ÇALIŞMA ANINDA kurulur (gitleaks `generic-api-key` dize sabitini sır sanar — D5 A-69 deseni).
    sahte_alan, sahte_sqlcipher = ("-".join(("GIZLI", ad, "Y200")) for ad in ("ALAN-DEGERI", "SQLCIPHER"))
    _sir_yaz(eski, {"patient_fernet_key": sahte_alan, "sqlcipher_key": sahte_sqlcipher})
    (eski / "patients.db").write_bytes(DUZ_DB)
    pu._kullanicidan_makineye_gocur(yeni)
    assert (yeni / ISARET).is_file(), "atlamasız göçten sonra kalıcı işaret yazılmadı"
    metin = (yeni / ISARET).read_text(encoding="utf-8")
    veri = json.loads(metin)
    assert set(veri) == {"surum", "kaynaklar"} and len(veri["kaynaklar"]) == 1, veri
    assert all(re.fullmatch(r"[0-9a-f]{64}", k) for k in veri["kaynaklar"]), "kök özeti SHA-256 değil"
    yasak = ("GIZLI-", "kullanici", "AppData", str(tmp_path).split("\\")[-1])
    assert not [y for y in yasak if y.lower() in metin.lower()], "işarette yol / kullanıcı / sır değeri var"

    # Y182: ikinci Windows hesabının kendi eski kökü (kendi %APPDATA%) — hedefte olmayan DB'sini bir kez taşır
    eski2_appdata = tmp_path / "ikinci" / "AppData" / "Roaming"
    (eski2_appdata / "PEMF_GUI").mkdir(parents=True)
    (eski2_appdata / "PEMF_GUI" / "auth_users.db").write_bytes(DUZ_DB)
    monkeypatch.setenv("APPDATA", str(eski2_appdata))
    pu._GOC_YAPILDI.clear()
    pu._kullanicidan_makineye_gocur(yeni)
    assert (yeni / "auth_users.db").is_file(), "ikinci hesabın eski kökü (başka kök) işaret yüzünden hiç taşınmadı"
    assert (yeni / "auth_users.db").read_bytes() == DUZ_DB
    assert len(json.loads((yeni / ISARET).read_text(encoding="utf-8"))["kaynaklar"]) == 2


@pytest.mark.parametrize("kol", ["yazilamaz", "bozuk"])
def test_KARSIT_Y200_isaret_yazilamaz_ya_da_BOZUKSA_goc_BASARILI_uyari_yazilir(kokler, caplog, kol):
    pu, eski, yeni = kokler
    (eski / "patients.db").write_bytes(DUZ_DB)
    if kol == "yazilamaz":
        (yeni / ISARET).mkdir()  # işaret yolu dizin: okunamaz + üzerine yazılamaz
    else:
        (yeni / ISARET).write_text("{bozuk", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        pu._kullanicidan_makineye_gocur(yeni)
    assert (yeni / "patients.db").is_file(), f"{kol} işaret göçü DURDURDU (işaret 'tamam' sayıldı)"
    assert (yeni / "patients.db").read_bytes() == DUZ_DB, f"{kol} işaret göçü bozdu"
    assert pu.goc_engeli(yeni / "patients.db") is None
    beklenen = "işareti yazılamadı" if kol == "yazilamaz" else "işareti okunamadı"
    uyari = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING and beklenen in r.getMessage()]
    assert uyari, f"işaret sorunu günlüğe yazılmadı ({beklenen})"
    if kol == "bozuk":
        assert json.loads((yeni / ISARET).read_text(encoding="utf-8"))["kaynaklar"], "bozuk işaret yeniden kurulmadı"


# ─────────────────────────── operatör iletisi: TR bayt bayt + EN + tür ayrımı ───────────────────────────


def test_KRITIK_Y200_operator_iletisi_EYLEM_soyler_TR_EN_ve_tur_ayrimi(monkeypatch):
    db_acilis_metni = headless_core.db_acilis_metni
    assert db_acilis_metni("eskiKok", "hasta", "", "tr") == TR_ESKI_KOK.format(ad="Hasta veritabanı")
    assert db_acilis_metni("eskiKok", "tedavi", "", "tr") == TR_ESKI_KOK.format(ad="Tedavi kaydı veritabanı")
    assert db_acilis_metni("eskiKok", "hasta", "", "en") == EN_ESKI_KOK.format(ad="Patient database")

    monkeypatch.setattr(pdb_mod, "acilis_hatasini_kilitle", lambda *a, **k: None)
    sahte = type("Sahte", (), {})()
    sahte.db_acilis_hatalari, sahte.db_acilis_ayrintilari = {}, {}
    sahte.app_data_dir, sahte.logger = Path("."), logging.getLogger("test_Y200")
    beklenen = {
        su.EskiKokGocuBekliyorHatasi: ("eskiKok", TR_ESKI_KOK.format(ad="Hasta veritabanı")),
        su.GocBekliyorHatasi: (
            "goc",
            db_acilis_metni("goc", "hasta", "", "tr"),
        ),  # KARŞIT: at-rest göçü kendi iletisinde kalır
        RuntimeError: ("acilamadi", db_acilis_metni("acilamadi", "hasta", "RuntimeError", "tr")),
    }
    for sinif, (tur, metin) in beklenen.items():

        def _ac(s=sinif):
            raise s("test")

        assert headless_core.HeadlessCore._db_ac(sahte, "hasta", _ac) is None
        assert sahte.db_acilis_ayrintilari["hasta"][0] == tur, (
            f"{sinif.__name__} → {sahte.db_acilis_ayrintilari['hasta']}"
        )
        assert sahte.db_acilis_hatalari["hasta"] == metin
