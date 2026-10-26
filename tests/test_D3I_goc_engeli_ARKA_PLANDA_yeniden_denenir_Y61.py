# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D3I-A2.3 (i) (D3.37 · Y10 × Y43 / Y61) — GEÇİCİ GÖÇ ENGELİ ARKA PLAN YENİDEN AÇMASINDA KALKAR (yeniden başlatmadan `dbReady` true).

ÖLÇÜLEN KUSUR: kopya GEÇİCİ bir nedenle doğrulanamazsa (AV / yedekleyici kilidi, anlık disk dolu, salt-okur) `_GOC_ENGELI[db]` süreç ömrü
boyunca kalıyordu; Y43 / Y61 arka plan yeniden açması (`acilista_acilamayani_yeniden_ac`) aynı kurucuyu çağırıp her denemede aynı
`GocBekliyorHatasi`yı alıyordu — göç süreç başına bir kez koştuğu için neden kalksa da DB açılmıyordu (Y61 "kalıcı göç kilidinde de SÜRER"
kararına aykırı: deneme sürüyor ama hiçbir zaman başaramıyordu). Çıkış yalnız yeniden başlatmaydı.

SÖZLEŞME: arka plan yeniden açması kurucudan ÖNCE `goc_engelini_yeniden_dene` ile YALNIZ engelli dosyanın göçünü (KOPYALA → SHA-256
DOĞRULA → kaynak SİLİNMEZ) yeniden dener; başarılıysa engel düşer, DB açılır, `dbReady` yeniden başlatmadan true olur. Deneme olay döngüsü
DIŞINDA koşar (sağlık ucu / ACİL DURDUR yavaşlamaz). Anahtar göçü ve öteki dosyalar YENİDEN koşmaz (`_GOC_YAPILDI`); kaynak yoksa engel
KALIR (boş DB kurulmaz). KARŞIT kalıcı engel: her denemede kaynak ve sır dosyası değişmez, hedefte DB / karantina oluşmaz, ACİL DURDUR 200.
Uçtan uca kol GERÇEK `backend_service.main()` + GERÇEK Y43 döngüsü (aralıklar kısaltılır); geçici neden = hedefte kopya geçici adının
(`patients.db.goc.part`) DİZİN olarak tutulması (gerçek dosya sistemi hatası, sahte yok).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest
from betik_alt_sureci import kostur, yalitik_ortam

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="göç yalnız Windows'ta koşar (path_utils)")

KOK = Path(__file__).resolve().parents[1]
TESTLER = Path(__file__).resolve().parent
BACKEND = KOK / "apps" / "backend"
DUZ_DB = b"SQLite format 3\x00" + b"ESKI-KOK" * 8

_SURUCU = r"""
import sys
sys.path.insert(0, {testler!r})
import alt_surec_ag_bekcisi as _ag
sys.path.remove({testler!r})
import hashlib, json, os, shutil, threading, time
sys.path[:0] = [{kok!r}, {backend!r}]
KIP = {kip!r}
sonuc = {{"kip": KIP}}
if KIP == "eski":
    from database.patient_database import get_patient_database
    from database.treatment_history_db import TreatmentHistoryDB
    from utils.path_utils import get_app_data_directory
    pdb = get_patient_database()
    for i in range(2):
        pdb.add_patient({{"name": "EngelHasta%d" % i, "species": "kedi"}})
    with pdb._get_connection() as cn:
        cn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    TreatmentHistoryDB(get_app_data_directory()).close_connections()
else:
    import utils.path_utils as _pu
    YAVAS = {{"suruyor": False, "deneme": 0}}
    _o_kopya = _pu._kopyala_dogrula
    def _kopya(kaynak, varis):
        # Arka plan denemesi YAVAŞ (büyük DB / yavaş disk) — ölçümler deneme SÜRERKEN alınır. Açılıştaki ilk kopya ana iş parçacığında.
        if threading.current_thread() is not threading.main_thread() and str(varis).endswith("patients.db"):
            YAVAS["deneme"] += 1
            YAVAS["suruyor"] = True
            try:
                time.sleep(1.5)
                return _o_kopya(kaynak, varis)
            finally:
                YAVAS["suruyor"] = False
        return _o_kopya(kaynak, varis)
    _pu._kopyala_dogrula = _kopya
    import headless_core as _hc
    _hc.HeadlessCore.DB_YENIDEN_DENEME_ARALIKLARI_SN = (0.1, 0.2, 0.3)
    import backend_service as bs
    bs._start_cloud_sync = lambda logger: None
    bs._start_update_checker_safe = lambda logger: None
    bs._donanim_guncellemesi_kur = lambda core, logger, event_bus=None: None
    bs._start_db_maintenance = lambda core, logger: None
    bs._harden_secret_file_acls = lambda d, logger: None
    import utils.agir_import as _ai
    _ai.torch_isit = lambda *a, **k: None
    import servers.auto_discovery as _ad
    _ad._get_local_ip = lambda: "127.0.0.1"
    HEDEF = os.path.join(os.environ["PEMF_DATA_DIR"], "PEMF_GUI")

    def _sha(p):
        try:
            return hashlib.sha256(open(p, "rb").read()).hexdigest()
        except OSError:
            return None

    class _Casus:
        should_exit = False
        force_exit = False

        def run(self):
            from fastapi.testclient import TestClient
            from servers import api_server as api
            c = TestClient(api.app, client=("127.0.0.1", 50077))

            def saglik():
                t0 = time.perf_counter()
                r = c.get("/api/health")
                g = r.json() if r.status_code == 200 else {{}}
                return {{"kod": r.status_code, "sure": round(time.perf_counter() - t0, 3), "dbReady": g.get("dbReady"),
                         "dbSebep": g.get("dbSebep")}}

            sonuc["ilk"] = saglik()
            sonuc["sir_ilk"] = _sha(os.path.join(HEDEF, "pemf_secrets.json"))
            if KIP == "gecici":
                shutil.rmtree(os.path.join(HEDEF, "patients.db.goc.part"))  # geçici neden KALKTI (yeniden başlatma YOK)
            son = time.monotonic() + 20
            while not YAVAS["suruyor"] and time.monotonic() < son:
                time.sleep(0.02)
            sonuc["deneme_surerken"] = YAVAS["suruyor"]
            sonuc["saglik_surerken"] = saglik()
            t0 = time.perf_counter()
            r = c.post("/api/hardware/emergency_stop")
            sonuc["estop_surerken"] = {{"kod": r.status_code, "sure": round(time.perf_counter() - t0, 3)}}
            son = time.monotonic() + (25 if KIP == "gecici" else 0)
            sonuc["sonra"] = saglik()
            while sonuc["sonra"]["dbReady"] is not True and time.monotonic() < son:
                time.sleep(0.2)
                sonuc["sonra"] = saglik()
            if KIP == "kalici":
                son = time.monotonic() + 25
                while YAVAS["deneme"] < 3 and time.monotonic() < son:
                    time.sleep(0.1)
                while YAVAS["suruyor"]:
                    time.sleep(0.05)
                sonuc["sonra"] = saglik()
            sonuc["deneme"] = YAVAS["deneme"]
            sonuc["sir_son"] = _sha(os.path.join(HEDEF, "pemf_secrets.json"))
            try:
                from database.patient_database import get_patient_database
                sonuc["hastalar"] = sorted(str(h.get("name")) for h in get_patient_database().get_all_patients())
            except Exception as e:
                sonuc["hastalar"] = "HATA " + type(e).__name__
            sonuc["hedef"] = sorted(os.listdir(HEDEF))

    bs._build_server = lambda app, args: _Casus()
    try:
        sonuc["rc"] = bs.main(["--host", "127.0.0.1", "--port", "51997", "--no-headless-services"])
    except BaseException as e:
        import traceback
        sonuc["kacan"] = type(e).__name__ + ": " + str(e)[:300]
        sonuc["iz"] = traceback.format_exc()[-1500:]
sonuc["ag"] = _ag.ENGELLENEN
print("SONUC " + json.dumps(sonuc, ensure_ascii=False, default=str))
sys.stdout.flush()
os._exit(0)
"""


def _kos(tmp_path: Path, kip: str, makine: bool, at_rest: str) -> dict:
    env = yalitik_ortam(tmp_path / "ev")
    env.update(
        {
            "PEMF_DEVICE_IDENTITY_DIR": str(tmp_path / "kimlik"),
            "PEMF_CLOUD_PROVISION_PATH": str(tmp_path / "yok" / "p.json"),
            "PEMF_CLOUD_PATIENT_SYNC": "0",
            "SUPABASE_URL": "http://127.0.0.1:9",
            "PEMF_LOG_DIR": str(tmp_path / f"log_{kip}"),
            "PEMF_ESP_ENABLED": "0",
            "PEMF_FW_AUTO_UPDATE": "0",
            "PEMF_HOTSPOT": "0",
            "PEMF_AI_WARMUP": "0",
            "PEMF_ENABLE_TUNNEL": "0",
            "PEMF_ENCRYPT_AT_REST": at_rest,
        }
    )
    if makine:
        env["PEMF_DATA_DIR"] = str(tmp_path / "makine")
    betik = tmp_path / f"surucu_{kip}.py"
    betik.write_text(
        _SURUCU.format(testler=str(TESTLER), kok=str(KOK), backend=str(BACKEND), kip=kip), encoding="utf-8"
    )
    p = kostur([str(betik)], cwd=tmp_path, env=env, sure=420)
    satir = [s for s in p.stdout.splitlines() if s.startswith("SONUC ")]
    assert p.returncode == 0 and satir, f"{kip} çocuğu düştü rc={p.returncode}: {p.stderr[-1500:]}"
    return json.loads(satir[-1][len("SONUC ") :])


def _goruntu(d: Path) -> dict:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in d.iterdir() if p.is_file()}


@pytest.mark.parametrize("kip", ["gecici", "kalici"])
def test_KRITIK_D3I_A2_3_gecici_goc_engeli_ARKA_PLANDA_kalkar_kalici_engel_hicbir_seye_DOKUNMAZ(tmp_path, kip):
    """MUTASYON: arka plan yeniden açması göçü yeniden DENEMEZ (= HEAD) → `gecici` KIRMIZI."""
    eski = tmp_path / "ev" / "appdata" / "PEMF_GUI"
    hedef = tmp_path / "makine" / "PEMF_GUI"
    e = _kos(tmp_path, "eski", makine=False, at_rest="0")
    assert e["ag"] == [], e
    (hedef / "patients.db.goc.part").mkdir(parents=True)  # kopya hedefi geçici olarak YAZILAMAZ (AV kilidi sınıfı)
    once = _goruntu(eski)

    s = _kos(tmp_path, kip, makine=True, at_rest="1")
    assert "kacan" not in s and s["ag"] == [], s
    print("OLCUM", kip, {k: s.get(k) for k in ("ilk", "saglik_surerken", "estop_surerken", "sonra", "deneme")})
    assert s["ilk"]["kod"] == 200 and s["ilk"]["dbReady"] is False and s["ilk"]["dbSebep"], (
        f"ön koşul (göç engeli): {s['ilk']}"
    )
    # Y43: deneme olay döngüsü DIŞINDA — deneme SÜRERKEN sağlık ve ACİL DURDUR hızlı
    assert s["deneme_surerken"] is True, f"arka plan göç denemesi HİÇ başlamadı (engel kalıcı): {s}"
    assert s["saglik_surerken"]["kod"] == 200 and s["saglik_surerken"]["sure"] < 1.0, s["saglik_surerken"]
    assert s["estop_surerken"]["kod"] == 200 and s["estop_surerken"]["sure"] < 1.0, s["estop_surerken"]
    assert _goruntu(eski) == once, "eski kök değişti (Y10)"
    assert s["sir_son"] == s["sir_ilk"], "yeniden denemeler sır dosyasını değiştirdi (yeni anahtar?)"
    if kip == "gecici":
        assert s["sonra"]["dbReady"] is True, (
            f"geçici neden kalktı ama DB yeniden başlatmadan AÇILMADI: {s['sonra']} (deneme {s['deneme']})"
        )
        assert s["hastalar"] == ["EngelHasta0", "EngelHasta1"], s["hastalar"]
    else:
        assert s["deneme"] >= 3 and s["sonra"]["dbReady"] is False, s
        assert "patients.db" not in s["hedef"] and not [a for a in s["hedef"] if "acilamadi" in a], (
            f"kalıcı engelde hedefte BOŞ DB / karantina oluştu: {s['hedef']}"
        )


# ─────────────────────────── süreç içi: `goc_engelini_yeniden_dene` sözleşmesi ───────────────────────────


@pytest.fixture
def kokler(tmp_path, monkeypatch):
    from utils import path_utils as pu

    eski_appdata = tmp_path / "kullanici" / "AppData" / "Roaming"
    eski = eski_appdata / "PEMF_GUI"
    eski.mkdir(parents=True)
    yeni = tmp_path / "ProgramData" / "PEMF_System" / "PEMF_GUI"
    yeni.mkdir(parents=True)
    for ad in ("patients.db", "auth_users.db"):
        (eski / ad).write_bytes(DUZ_DB)
    monkeypatch.setenv("APPDATA", str(eski_appdata))
    monkeypatch.setattr(pu, "_GOC_YAPILDI", set())
    monkeypatch.setattr(pu, "_GOC_ENGELI", {pu._goc_anahtari(yeni / "patients.db"): "OSError: disk dolu (test)"})
    return pu, eski, yeni


def test_KRITIK_D3I_A2_3_yeniden_deneme_YALNIZ_engelli_dosya_anahtar_gocu_KOSMAZ(kokler, monkeypatch):
    pu, eski, yeni = kokler

    def _patlat(*a, **k):
        raise AssertionError("yeniden deneme anahtar göçünü / sır katmanını koşturdu")

    monkeypatch.setattr(pu, "_sqlcipher_anahtarini_gocur", _patlat)
    once = _goruntu(eski)
    assert pu.goc_engelini_yeniden_dene(yeni / "patients.db") is True
    assert pu.goc_engeli(yeni / "patients.db") is None
    assert (yeni / "patients.db").read_bytes() == DUZ_DB
    assert not (yeni / "auth_users.db").exists(), (
        "yeniden deneme engelsiz dosyaları da taşıdı (`_GOC_YAPILDI` sözleşmesi)"
    )
    assert _goruntu(eski) == once


def test_KARSIT_D3I_A2_3_neden_SURERSE_engel_KALIR_hedefte_iz_yok(kokler):
    pu, eski, yeni = kokler
    (yeni / "patients.db.goc.part").mkdir()
    assert pu.goc_engelini_yeniden_dene(yeni / "patients.db") is False
    assert pu.goc_engeli(yeni / "patients.db"), "kalıcı nedende engel düştü → kurucu BOŞ DB kurar"
    assert not (yeni / "patients.db").exists()


def test_KARSIT_D3I_A2_3_kaynak_YOKSA_engel_KALIR_bos_DB_kurulmaz(kokler):
    pu, eski, yeni = kokler
    (eski / "patients.db").unlink()
    assert pu.goc_engelini_yeniden_dene(yeni / "patients.db") is False
    assert pu.goc_engeli(yeni / "patients.db"), "kaynak kaybolunca engel düştü → kurucu BOŞ DB kurar (boş klinik)"


def test_KARSIT_D3I_A2_3_deneme_ISTISNASINDA_engel_GERI_konur(kokler, monkeypatch):
    pu, eski, yeni = kokler

    def _dus(*a, **k):
        raise OSError(5, "erisim reddedildi (test)")

    monkeypatch.setattr(pu, "_dosyalari_gocur", _dus)
    assert pu.goc_engelini_yeniden_dene(yeni / "patients.db") is False
    assert pu.goc_engeli(yeni / "patients.db"), "deneme istisnasında engel kayboldu"


# ─────────────────────────── D3I orkestratör: ilk turda YAŞAYAN iki mutantın kolları ───────────────────────────


class _Kurucu(Exception):
    """Sahte kurucuya ulaşıldı (yeniden açmayı orada durdurur)."""


@pytest.mark.parametrize(
    "modul, dosya", [("patient_database", "patients.db"), ("treatment_history_db", "pemf_treatment_history.db")]
)
def test_KRITIK_D3I_A2_3_arka_plan_yeniden_acma_KURUCUDAN_ONCE_kendi_dosyasini_yeniden_dener(
    tmp_path, monkeypatch, modul, dosya
):
    """Hasta VE tedavi DB'sinin Y43 / Y61 arka plan yeniden açması kurucudan ÖNCE kendi dosyasının göçünü yeniden dener. Uçtan uca kol
    yalnız hasta DB'sini ölçüyordu — tedavi tarafındaki çağrı silinince kapı YEŞİL kalıyordu (ölçüldü). MUTASYON: tedavi yeniden
    denemesi yok → KIRMIZI."""
    import importlib

    from utils import path_utils as pu

    m = importlib.import_module(f"database.{modul}")
    sira = []
    monkeypatch.setattr(pu, "goc_engelini_yeniden_dene", lambda db: sira.append(("dene", Path(db).name)) or True)

    def _kurucu(*a, **k):
        sira.append(("kurucu", None))
        raise _Kurucu()

    if modul == "patient_database":
        monkeypatch.setattr(m, "_patient_db", None)
        monkeypatch.setattr(m, "PatientDatabase", _kurucu)
    else:
        monkeypatch.setattr(m, "_treatment_db_instance", None)
        monkeypatch.setattr(m, "TreatmentHistoryDB", _kurucu)
    with pytest.raises(_Kurucu):
        m.acilista_acilamayani_yeniden_ac(tmp_path)
    assert sira == [("dene", dosya), ("kurucu", None)], f"{modul}: göç yeniden denemesi kurucudan önce koşmadı: {sira}"


def test_KARSIT_D3I_A2_3_hedefte_dosya_BELIRDIYSE_engel_KALIR_uzerine_yazilmaz(kokler):
    """Engel sürerken hedefte aynı adlı dosya belirdiyse (0 bayt) engel KALIR ve dosyaya dokunulmaz (D3.37: hedefteki dosya ezilmez).
    MUTASYON: hedef-var denetimi yok → göç dosyayı atlar ama engel düşer → kurucu belirmiş (boş) dosyayı DB diye açar → KIRMIZI."""
    pu, eski, yeni = kokler
    (yeni / "patients.db").write_bytes(b"")
    assert pu.goc_engelini_yeniden_dene(yeni / "patients.db") is False
    assert pu.goc_engeli(yeni / "patients.db"), "hedefte dosya belirince engel düştü → kurucu onu (boş) DB diye açar"
    assert (yeni / "patients.db").read_bytes() == b""


def test_KARSIT_D3I_A2_3_yeniden_denemede_kaynak_KILITLI_dosya_ATLANIRSA_engel_KALIR(kokler, monkeypatch):
    """D3I çapraz (C1, doğrulayıcı D ölçtü): yeniden deneme anında kaynak okunamıyorsa (AV / paylaşım kilidi) `_sifreli_mi` onu ŞİFRELİ
    sayar, anahtarsız kurulumda `_tasinabilir_mi` False → göç dosyayı ATLAR. Engel GERİ konmalı (hedefte DB yok) — eskiden True dönüp
    kurucunun BOŞ DB kurmasına izin veriyordu (sonraki açılışlarda göç bir daha hiç denenmezdi). Sahte EN ALT katta: yalnız kaynak
    dosyanın `open`'ı PermissionError. Kilit kalkınca sonraki deneme taşır. MUTASYON: atlamada engel geri konmaz → KIRMIZI."""
    import builtins

    pu, eski, yeni = kokler
    kaynak = eski / "patients.db"
    gercek_open = builtins.open

    def _kilitli(dosya, *a, **k):
        if str(dosya) == str(kaynak):
            raise PermissionError(13, "sahte: dosya baska bir islem tarafindan kullaniliyor", str(dosya))
        return gercek_open(dosya, *a, **k)

    monkeypatch.setattr(builtins, "open", _kilitli)
    sonuc = pu.goc_engelini_yeniden_dene(yeni / "patients.db")
    monkeypatch.setattr(builtins, "open", gercek_open)
    assert sonuc is False and pu.goc_engeli(yeni / "patients.db"), (
        "kopya yerleşmedi ama engel düştü → kurucu BOŞ DB kurar"
    )
    assert not (yeni / "patients.db").exists()
    assert pu.goc_engelini_yeniden_dene(yeni / "patients.db") is True, "kilit kalktı ama göç yeniden denenmedi"
    assert (yeni / "patients.db").read_bytes() == DUZ_DB
