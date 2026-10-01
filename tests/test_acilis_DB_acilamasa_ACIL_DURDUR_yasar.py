# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.37 · B-3.8 — AÇILIŞTA DB AÇILAMASA DA BACKEND AÇILIR (ACİL DURDUR dahil); DB'siz kısıtlı kip görünür.

ÖLÇÜLEN KUSUR: `HeadlessCore.__init__` hasta DB'sini (`get_patient_database`) ve tedavi DB'sini
(`get_session_manager` → `get_treatment_db`) SARMASIZ açıyordu. At-rest göçü dosya kilidine takılınca
(`.enc.tmp → db` taşıması kalıcı WinError 32) düz-metin DB `karantinaya_al`da `GocBekliyorHatasi`
verir (sahip kararı 3903ea9: düz-metin karantinaya ALINMAZ); istisna `backend_service.main()`'den
kaçıyor ve HİÇBİR uç açılmıyordu — ACİL DURDUR dahil. Aynı yol Karar-6 fail-closed `RuntimeError`'ları
için de geçerli (plan C1-7: düzeltme GENEL olmalı).

SÖZLEŞME (bu dosya ölçer, her senaryo AYRI çocuk süreçte, GERÇEK `main()`):
  1. `server.run()`'a ULAŞILIR; ACİL DURDUR rotası kayıtlı, `POST` 200 ve GERÇEK HardwareController'a
     STOP verilir.
  2. `/api/health` 200, `dbReady` **false** ve `dbSebep` nedeni söyler ("göç bekliyor"). HASTA DB'si
     tek başına göç beklese de `dbReady` false olur — launcher (`main.rs` `db_hazir_mi`) güncellemeyi
     ancak böyle GERİ ALIR; aksi hâlde onaylayıp `runtime.old`'u siler (plan D1.37 orkestratör notu).
  3. Sağlık yanıtı **launcher'ın 3 sn zaman aşımının çok altında** (< 2 sn): açılışta açılamayan DB
     süreç ömrü boyunca YENİDEN DENENMEZ. Denenseydi kalıcı kilitte her `/api/health` (async — olay
     döngüsünde) göçü ≥6 sn tekrar dener; launcher `None` ("bilinmiyor") alıp güncellemeyi ONAYLAR ve
     olay döngüsü bloklandığı için ACİL DURDUR isteği de gecikir.
  4. STM seansı **503** (kayıtsız tedavi başlamaz) ve donanıma `update_coil` GİTMEZ.
  5. Düz-metin DB **yerinde ve düz-metin** kalır; `.acilamadi-*` karantina kopyası YOK.
  6. Karşıt: sağlam kurulumda aynı aparatla `dbReady` TRUE (aparat ve kilit yanlış alarm vermez).

⚠️ AĞ: çocukta `tests/alt_surec_ag_bekcisi.py` ürün importundan ÖNCE yüklenir; her koşuda engellenen ağ
denemesi = [] ölçülür. Ağa çıkan yan alt sistemler (bulut senkronu, güncelleme denetleyicisi, donanım
güncellemesi denetimi — `PEMF_FW_AUTO_UPDATE=0`'da da manifesti GitHub'dan ölçer) ve
torch ısıtması çocukta KAYITÇI ile değiştirilir; yerel IP sondası (8.8.8.8 hilesi) loopback döner;
ACL sertleştirmesi (`.plain.bak`/anahtar dosyalarını SYSTEM'e kilitler → tmp silinemez) kaydedilir
ama uygulanmaz. Ölçülen zincir (HeadlessCore → api_server → sağlık/E-stop/seans) DEĞİŞTİRİLMEZ.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import pytest
from betik_alt_sureci import kostur, yalitik_ortam

KOK = Path(__file__).resolve().parents[1]
TESTLER = Path(__file__).resolve().parent
_SQLITE_BASLIK = b"SQLite format 3\x00"
#: launcher `backend::db_hazir_mi` zaman aşımı 3 sn (launcher/core/src/backend.rs) — pay bırakılır.
#: Ölçülen (2026-10-01): kilitliyken 4–140 ms; 20+ koşuda BİR kez 2,0 sn (kaynağı ölçülemedi). Kilit yokken
#: (açılışta açılamayan DB her çağrıda yeniden denenince) ≥6 sn — eşik ikisini ayırır.
SAGLIK_SURE_SINIRI_SN = 2.5

_SURUCU = r"""
import sys
sys.path.insert(0, {testler!r})
import alt_surec_ag_bekcisi as _ag
sys.path.remove({testler!r})
import json, os, shutil, time, traceback
sys.path[:0] = [{kok!r}, {backend!r}]
SENARYO = {senaryo!r}
sonuc = {{"run": False, "senaryo": SENARYO}}

gercek_move = shutil.move
if SENARYO.startswith("goc"):
    def _kalici_kilit(src, dst, *a, **k):
        # .enc.tmp -> db tasimasi HER denemede duser (Windows gecici kilit sinifinin KALICI hali)
        if str(src).endswith(".enc.tmp"):
            raise PermissionError(32, "The process cannot access the file because it is being used by another process")
        return gercek_move(src, dst, *a, **k)
    shutil.move = _kalici_kilit

import backend_service as bs
yan = []
bs._start_cloud_sync = lambda logger: yan.append("cloud_sync")
bs._start_update_checker_safe = lambda logger: yan.append("update_checker")
# FW_AUTO_UPDATE=0'da da manifesti GitHub'dan ÖLÇER (ağ) — Y1/Ö.4-Y2: testte koşturulmaz
bs._donanim_guncellemesi_safe = lambda core, logger: yan.append("donanim_guncellemesi")
bs._harden_secret_file_acls = lambda d, logger: yan.append("acl")
import utils.agir_import as _ai
_ai.torch_isit = lambda *a, **k: yan.append("torch")
import servers.auto_discovery as _ad
_ad._get_local_ip = lambda: "127.0.0.1"


class _Casus:
    should_exit = False
    force_exit = False

    def run(self):
        sonuc["run"] = True
        from fastapi.testclient import TestClient
        from servers import api_server as api
        c = TestClient(api.app, client=("127.0.0.1", 50077))
        sonuc["estop_rota"] = any(getattr(r, "path", "") == "/api/hardware/emergency_stop" for r in api.app.routes)
        hw = api.state.hardware
        sonuc["hc"] = type(hw).__name__
        sayac = {{"stop": 0, "update": 0}}
        _o_stop, _o_upd = hw.stop_all_coils, hw.update_coil
        def _stop():
            sayac["stop"] += 1
            return _o_stop()
        def _upd(*a, **k):
            sayac["update"] += 1
            return _o_upd(*a, **k)
        hw.stop_all_coils, hw.update_coil = _stop, _upd
        sonuc["saglik"] = []
        for _ in range(3):
            t0 = time.perf_counter()
            r = c.get("/api/health")
            g = r.json() if r.status_code == 200 else {{}}
            sonuc["saglik"].append({{"kod": r.status_code, "sure": time.perf_counter() - t0,
                                     "dbReady": g.get("dbReady"), "dbSebep": g.get("dbSebep")}})
        # Hasta listesi ucu (eşzamanlı uç, iş parçacığı havuzu): açılışta açılamayan hasta DB'si her istekte
        # yeniden denenmemeli. raise_server_exceptions=False: 5xx yanıt olarak ölçülür.
        t0 = time.perf_counter()
        r = TestClient(api.app, client=("127.0.0.1", 50078), raise_server_exceptions=False).get("/api/patients")
        sonuc["hastalar"] = {{"kod": r.status_code, "sure": time.perf_counter() - t0}}
        t0 = time.perf_counter()
        r = c.post("/api/hardware/emergency_stop")
        sonuc["estop"] = {{"kod": r.status_code, "sure": time.perf_counter() - t0}}
        if SENARYO != "saglam":
            r = c.post("/api/session/start", json={{"mode": "Manuel", "frequency": 100, "duty": 40, "phase": 0,
                       "intensity": 0, "duration_minutes": 5, "coil_ids": [1], "patient_name": "D137"}})
            sonuc["seans"] = {{"kod": r.status_code, "detail": (r.json() or {{}}).get("detail", "")}}
            c.post("/api/session/stop", json={{}})
        sonuc["sayac"] = dict(sayac)


bs._build_server = lambda app, args: _Casus()
try:
    sonuc["rc"] = bs.main({argv!r})
except BaseException as e:
    sonuc["kacan"] = type(e).__name__ + ": " + str(e)[:300]
    sonuc["iz"] = traceback.format_exc()[-1500:]
sonuc["yan"] = yan
sonuc["ag"] = _ag.ENGELLENEN
sonuc["alt"] = _ag.ALT_SURECLER
print("SONUC " + json.dumps(sonuc, default=str))
sys.stdout.flush()
os._exit(0)
"""


def _duz_db(yol: Path, tablo: str = "kayit") -> None:
    yol.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(yol))
    c.execute(f"CREATE TABLE {tablo} (ad TEXT)")
    c.execute(f"INSERT INTO {tablo} VALUES ('GocBekleyenHasta')")
    c.commit()
    c.close()


def _kur(tmp_path: Path, senaryo: str) -> tuple[dict, Path]:
    veri = tmp_path / "veri"
    app = veri / "PEMF_GUI"
    app.mkdir(parents=True, exist_ok=True)
    env = yalitik_ortam(tmp_path / "ev")
    env.update(
        {
            "PEMF_DATA_DIR": str(veri),
            "PEMF_DEVICE_IDENTITY_DIR": str(tmp_path / "kimlik"),
            "PEMF_CLOUD_PROVISION_PATH": str(tmp_path / "yok" / "provizyon.json"),
            "PEMF_CLOUD_PATIENT_SYNC": "0",
            "SUPABASE_URL": "http://127.0.0.1:9",
            "PEMF_LOG_DIR": str(tmp_path / "log"),
            "PEMF_ESP_ENABLED": "0",
            "PEMF_FW_AUTO_UPDATE": "0",
            "PEMF_HOTSPOT": "0",
            "PEMF_AI_WARMUP": "0",
            "PEMF_ENABLE_TUNNEL": "0",
            "PEMF_ENCRYPT_AT_REST": "1" if senaryo.startswith("goc") or senaryo == "saglam" else "0",
        }
    )
    if senaryo == "goc_hasta":
        _duz_db(app / "patients.db")
    elif senaryo == "goc_tedavi":
        _duz_db(app / "pemf_treatment_history.db")
    elif senaryo == "bozuk_ikisi":
        for ad in ("patients.db", "pemf_treatment_history.db"):
            (app / ad).write_bytes(b"BU BIR SQLITE DOSYASI DEGIL " * 64)
    elif senaryo == "bozuk_port":
        # 1-A açık madde 6 (kol D1.14 kapısında): launcher `--port` verir; ortamdaki bozuk port açılışı öldürmemeli.
        env["PEMF_API_PORT"] = "80O0"
    return env, app


#: Launcher biçimi (`launcher/core/src/backend.rs`: `--port` HER ZAMAN verilir).
ARGV_LAUNCHER = ["--host", "127.0.0.1", "--port", "51999", "--no-headless-services"]


def _kos(tmp_path: Path, senaryo: str, argv: list[str] | None = None) -> tuple[dict, Path]:
    env, app = _kur(tmp_path, senaryo)
    kod = _SURUCU.format(
        testler=str(TESTLER),
        kok=str(KOK),
        backend=str(KOK / "apps" / "backend"),
        senaryo=senaryo,
        argv=list(ARGV_LAUNCHER if argv is None else argv),
    )
    (tmp_path / "surucu.py").write_text(kod, encoding="utf-8")
    p = kostur([str(tmp_path / "surucu.py")], cwd=tmp_path, env=env, sure=420)
    for satir in p.stdout.splitlines():
        if satir.startswith("SONUC "):
            return json.loads(satir[len("SONUC ") :]), app
    raise AssertionError(f"çocuk sonuç basmadı (rc={p.returncode}); stderr sonu: {p.stderr[-1500:]}")


#: Çocuğun başlatmasına izin verilen alt süreçler (D1.14 ile aynı: `platform` sürüm sorgusu).
_IZINLI_ALT_SUREC = re.compile(r'cmd\.exe /c "?ver"?$', re.IGNORECASE)


def _sqlcipher_var() -> bool:
    from database.sqlcipher_util import import_sqlcipher

    return import_sqlcipher() is not None


def _ortak_iddialar(s: dict) -> None:
    assert "kacan" not in s, (
        f"main()'den istisna KAÇTI — backend açılmadı, ACİL DURDUR ucu YOK: {s.get('kacan')}\n{s.get('iz', '')}"
    )
    assert s["run"] is True, f"server.run()'a ulaşılmadı: {s}"
    assert s["estop_rota"] is True and s["hc"] == "HardwareController", s
    assert s["estop"]["kod"] == 200 and s["sayac"]["stop"] >= 1, (
        f"ACİL DURDUR donanıma STOP vermedi: {s['estop']} {s['sayac']}"
    )
    assert all(h["kod"] == 200 for h in s["saglik"]), f"sağlık ucu düştü: {s['saglik']}"
    yavas = [round(h["sure"], 2) for h in s["saglik"] if h["sure"] >= SAGLIK_SURE_SINIRI_SN]
    assert not yavas, (
        f"/api/health {yavas} sn — launcher 3 sn'de vazgeçip dbReady'yi 'bilinmiyor' sayar ve güncellemeyi "
        "ONAYLAR; olay döngüsü bloklandığı için ACİL DURDUR da gecikir (açılışta açılamayan DB yeniden deneniyor)"
    )
    assert s["ag"] == [], f"çocuk AĞA çıkmayı denedi (bekçi engelledi): {s['ag']}"
    assert all(_IZINLI_ALT_SUREC.search(a) for a in s["alt"]), f"izin listesi dışı alt süreç: {s['alt']}"
    assert s.get("rc") == 0, f"main() dönüş kodu {s.get('rc')}"


def _db_yok_iddialari(s: dict, sebep_kalibi: str) -> None:
    for h in s["saglik"]:
        assert h["dbReady"] is False, (
            f"DB açılamadı ama dbReady={h['dbReady']} — launcher güncellemeyi ONAYLAR: {s['saglik']}"
        )
        assert h["dbSebep"] and re.search(sebep_kalibi, h["dbSebep"], re.IGNORECASE), (
            f"dbSebep nedeni söylemiyor ({sebep_kalibi!r}): {h['dbSebep']!r}"
        )
    assert s["seans"]["kod"] == 503 and "kayıt" in s["seans"]["detail"].lower(), f"DB'siz seans: {s['seans']}"
    assert re.search(sebep_kalibi, s["seans"]["detail"], re.IGNORECASE), f"seans reddi NEDENİ söylemiyor: {s['seans']}"
    assert s["sayac"]["update"] == 0, f"DB'siz kipte STM bobini sürülmeye çalışıldı ({s['sayac']['update']})"
    assert s["hastalar"]["sure"] < SAGLIK_SURE_SINIRI_SN, (
        f"/api/patients {s['hastalar']['sure']:.1f} sn — açılışta açılamayan hasta DB'si her istekte yeniden deneniyor"
    )


def _duz_metin_yerinde(app: Path, ad: str) -> None:
    db = app / ad
    assert db.exists(), f"{ad} YERİNDE DEĞİL — düz-metin DB taşındı (sahip kararı: karantina YOK)"
    assert db.read_bytes()[:16] == _SQLITE_BASLIK, f"{ad} artık düz-metin değil (dokunuldu)"
    c = sqlite3.connect(str(db))
    try:
        assert c.execute("SELECT ad FROM kayit").fetchone()[0] == "GocBekleyenHasta"
    finally:
        c.close()
    karantina = sorted(p.name for p in app.glob("*.acilamadi-*"))
    assert karantina == [], f"karantina kopyası oluştu: {karantina}"


@pytest.mark.parametrize("senaryo", ["goc_hasta", "goc_tedavi"])
def test_KRITIK_goc_bekleyen_DB_backendi_OLDURMEZ_dbReady_FALSE_karantina_YOK(tmp_path, senaryo):
    if not _sqlcipher_var():
        pytest.skip("sqlcipher3 yok — göç senaryosu kurulamaz (GENEL kol bozuk_ikisi'nde koşar)")
    s, app = _kos(tmp_path, senaryo)
    _ortak_iddialar(s)
    _db_yok_iddialari(s, r"g[öo]ç")
    _duz_metin_yerinde(app, "patients.db" if senaryo == "goc_hasta" else "pemf_treatment_history.db")


def test_KRITIK_GENEL_bozuk_DB_RuntimeError_de_backendi_OLDURMEZ(tmp_path):
    """C1-7: yalnız `GocBekliyorHatasi`'nı yakalayan dar düzeltme Karar-6 / bozuk dosya `RuntimeError`larında
    backend'i (ve E-stop'u) öldürmeye devam ederdi."""
    s, app = _kos(tmp_path, "bozuk_ikisi")
    _ortak_iddialar(s)
    _db_yok_iddialari(s, r"a[çc][ıi]lamad[ıi]")
    for ad in ("patients.db", "pemf_treatment_history.db"):
        assert (app / ad).read_bytes().startswith(b"BU BIR SQLITE"), f"{ad}: bozuk dosyaya DOKUNULDU"


def test_KARSIT_cekirdek_yok_ya_da_SAHTE_cekirdekte_acilis_hatasi_YOK(monkeypatch):
    """`_db_acilis_hatasi` yalnız gerçek sözlüğü okur: çekirdek yokken ya da sahte (MagicMock) çekirdekte
    açılış hatası UYDURMAZ — aksi hâlde testlerde/araçlarda dbReady sessizce false olur ve seans 503 alır."""
    from unittest.mock import MagicMock

    from servers import api_server as api

    for cekirdek in (None, MagicMock(), object()):
        monkeypatch.setattr(api.state, "core", cekirdek, raising=False)
        assert api._db_acilis_hatasi() == "", f"{type(cekirdek).__name__}: sahte açılış hatası"

    class _C:
        db_acilis_hatalari = {"hasta": "Hasta veritabanı göç bekliyor: …", "tedavi": None}

    monkeypatch.setattr(api.state, "core", _C(), raising=False)
    assert api._db_acilis_hatasi() == "Hasta veritabanı göç bekliyor: …"
    assert api._kayit_db_hazir() == (False, "Hasta veritabanı göç bekliyor: …")


def test_KARSIT_saglam_kurulumda_dbReady_TRUE(tmp_path):
    """Aparat ve 'yeniden deneme yok' kilidi sağlam kurulumda yanlış alarm vermez."""
    if not _sqlcipher_var():
        pytest.skip("sqlcipher3 yok")
    s, _app = _kos(tmp_path, "saglam")
    _ortak_iddialar(s)
    assert all(h["dbReady"] is True for h in s["saglik"]), f"sağlam kurulumda dbReady: {s['saglik']}"
    assert not any(h["dbSebep"] for h in s["saglik"]), s["saglik"]
