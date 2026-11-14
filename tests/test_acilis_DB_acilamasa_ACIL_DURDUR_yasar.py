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
  3. Sağlık yanıtı **launcher'ın 3 sn zaman aşımının çok altında** (< 2,5 sn): açılışta açılamayan DB
     İSTEK YOLUNDA yeniden denenmez. Denenseydi kalıcı kilitte her `/api/health` (async — olay
     döngüsünde) göçü ≥6 sn tekrar dener; launcher `None` ("bilinmiyor") alıp güncellemeyi ONAYLAR ve
     olay döngüsü bloklandığı için ACİL DURDUR isteği de gecikir.
     ⚠️ Y43 (sahip, D1.37 devamı): DB ARKA PLANDA (olay döngüsü dışı iş parçacığı) artan aralıklarla yeniden
     açılmaya çalışılır; bu dosyada aralıklar kısaltılır (çocukta sınıf özniteliği) → kalıcı kilit
     senaryolarında sağlık/E-stop ölçümleri arka plan denemeleri SÜRERKEN alınır. Geçici kilit senaryosu
     (`goc_gecici_*`): kilit kalkınca `dbReady` YENİDEN BAŞLATMADAN true olur, seans başlar, veri aynı
     anahtarla okunur, yeni anahtar üretilmez, karantina yok.
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

import base64
import hashlib
import json
import os
import re
import sqlite3
import subprocess
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
# D2.46 (B-3.48) "binding_yok": sqlcipher3 binding YOK (paket eksik/bozuk) — urun importundan ONCE engellenir.
if SENARYO == "binding_yok":
    for _ad in ("sqlcipher3", "sqlcipher3.dbapi2", "pysqlcipher3", "pysqlcipher3.dbapi2"):
        sys.modules[_ad] = None

# 2-A inceleme A2-1.4 "ikinci_hesap": veri koku BASKA bir SID'e kilitli (ebeveyn icacls ile kurar). Bu surec dosyalarin
# SAHIBI oldugundan ortuk WRITE_DAC tasir (gercek ikinci hesapta YOK) -> ACL degistiren cagrilar sahip-olmayan hesaptaki gibi
# DUSER (kaydedilir). Kimlik kasasina yazim (servis, ad) KAYDEDILIR, deger tutulmaz — yeni anahtar uretimi gorunsun.
ACL = []
KASA = []
if SENARYO == "ikinci_hesap":
    import utils.file_acl as _fa

    def _acl_dusur(ad):
        def _f(*a, **k):
            ACL.append(ad)
            return False
        return _f
    _fa.lock_down_dir = _acl_dusur("dir")
    _fa.lock_down_file = _acl_dusur("file")
    import keyring as _kr
    _o_kr_set = _kr.set_password

    def _kr_set(s, n, v):
        KASA.append([s, n])
        return _o_kr_set(s, n, v)
    _kr.set_password = _kr_set

# Y118 "ag_kok": veri koku AG SURUCUSUNDE — surucu turu sorgusu (GetDriveTypeW sarmalayicisi, urunun EN ALT kati) DRIVE_REMOTE
# doner; geri kalan her sey gercek (main(), gunluk, /api/health).
if SENARYO == "ag_kok":
    import utils.path_utils as _pu
    _pu._surucu_turu = lambda kok: 4

# 2-A inceleme A2-1.1: urun zincirinin ILK ice aktarimi (headless_core -> patient_database -> pemf_gui.config) ICE
# AKTARMADA olurse de SONUC basilir — "cocuk sonuc basmadi" diye gizlenmesin (ACIL DURDUR ucu hic kurulmamistir).
try:
    import headless_core as _hc_ilk  # noqa: F401
except BaseException as _e:
    sonuc["kacan"] = "ICE AKTARMADA: " + type(_e).__name__ + ": " + str(_e)[:300]
    sonuc["iz"] = traceback.format_exc()[-1500:]
    print("SONUC " + json.dumps(sonuc, default=str))
    sys.stdout.flush()
    os._exit(0)

gercek_move = shutil.move
KILIT = {{"aktif": True}}
if SENARYO.startswith("goc"):
    def _kalici_kilit(src, dst, *a, **k):
        # .enc.tmp -> db tasimasi HER denemede duser (Windows gecici kilit sinifinin KALICI hali);
        # goc_gecici_*: kilidi tutan (AV / yedekleme) KILIT["aktif"]=False olunca birakir.
        if str(src).endswith(".enc.tmp") and KILIT["aktif"]:
            raise PermissionError(32, "The process cannot access the file because it is being used by another process")
        return gercek_move(src, dst, *a, **k)
    shutil.move = _kalici_kilit

# Y43: goc girisimleri sayilir — bir girisim = `.enc.tmp -> db` tasimasi (girisimde 3 tasima var: db->.plain.bak,
# .enc.tmp->db, geri alma). sqlcipher_util ici GLOBAL arama -> modul ozniteligi yamasi tutar.
import database.sqlcipher_util as _su
GOC = {{"deneme": 0, "suruyor": False}}
_o_tasi = _su._tasi_yeniden_dene
def _sayan_tasi(*a, **k):
    if not str(a[0] if a else k.get("kaynak", "")).endswith(".enc.tmp"):
        return _o_tasi(*a, **k)
    GOC["deneme"] += 1
    GOC["suruyor"] = True
    try:
        return _o_tasi(*a, **k)
    finally:
        GOC["suruyor"] = False
_su._tasi_yeniden_dene = _sayan_tasi
# Y43: arka plan yeniden deneme araliklari kisaltilir (urunde 5 sn -> 30 sn -> 2 dk) — kalici kilit
# senaryolarinda saglik/E-stop olcumleri denemeler SURERKEN alinir.
import headless_core as _hc
_hc.HeadlessCore.DB_YENIDEN_DENEME_ARALIKLARI_SN = (0.1, 0.2, 0.3)

# 2-A (Y9): ACILIS STOP MUTABAKATI DB'siz kipte de kosmali — `startup-reconcile` is parcaciginin GERCEK
# HardwareController.stop_all_coils cagrisi SINIF duzeyinde sayilir (cekirdek kurulmadan once yamanir).
import threading as _th
from controllers.hardware_controller import HardwareController as _HC
MUTABAKAT = {{"stop": 0}}
_o_hc_stop = _HC.stop_all_coils
def _hc_stop(self, *a, **k):
    if _th.current_thread().name == "startup-reconcile":
        MUTABAKAT["stop"] += 1
    return _o_hc_stop(self, *a, **k)
_HC.stop_all_coils = _hc_stop

# D2.24 (B-3.81 · Y9) "alter_kilitli": baska bir baglanti tedavi DB'sinin YAZMA kilidini tutar (yedekleyici / ikinci
# surec); eski semadaki eksik kolonun ALTER'i busy_timeout sonra `database is locked` verir. GERCEK kilit, sahte yok.
import sqlite3 as _sq
TUTUCU = {{"baglanti": None}}
TEDAVI_DB = os.path.join(os.environ["PEMF_DATA_DIR"], "PEMF_GUI", "pemf_treatment_history.db")
if SENARYO == "alter_kilitli":
    TUTUCU["baglanti"] = _sq.connect(TEDAVI_DB, isolation_level=None)
    TUTUCU["baglanti"].execute("BEGIN IMMEDIATE")

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
        if SENARYO.startswith("goc"):
            _getter_olc(api)
        sonuc["saglik"] = []
        for _ in range(3):
            t0 = time.perf_counter()
            r = c.get("/api/health")
            g = r.json() if r.status_code == 200 else {{}}
            sonuc["saglik"].append({{"kod": r.status_code, "sure": time.perf_counter() - t0,
                                     "dbReady": g.get("dbReady"), "dbSebep": g.get("dbSebep"),
                                     "veriKokuAgda": g.get("veriKokuAgda")}})
        # Hasta listesi ucu (eşzamanlı uç, iş parçacığı havuzu): açılışta açılamayan hasta DB'si her istekte
        # yeniden denenmemeli. raise_server_exceptions=False: 5xx yanıt olarak ölçülür.
        t0 = time.perf_counter()
        r = TestClient(api.app, client=("127.0.0.1", 50078), raise_server_exceptions=False).get("/api/patients")
        sonuc["hastalar"] = {{"kod": r.status_code, "sure": time.perf_counter() - t0}}
        # KP-5 · 17: listenin 503 gerekçesi (ikinci hesapta "bağlantı" değil ERİŞİM iletisi beklenir)
        try:
            sonuc["hastalar"]["detail"] = (r.json() or {{}}).get("detail", "")
        except ValueError:
            sonuc["hastalar"]["detail"] = r.text[:200]
        t0 = time.perf_counter()
        r = c.post("/api/hardware/emergency_stop")
        sonuc["estop"] = {{"kod": r.status_code, "sure": time.perf_counter() - t0}}
        # D1.81 · Y4: acil durdurma MANDALLAR — yeni START'tan önce operatörün "Sıfırla"sı gerekir; DB'siz kipte de
        # çalışmalı (denetim izi yazılamaz, sıfırlama yine olur).
        r = c.post("/api/hardware/estop_mandali/sifirla", json={{"onay": True}})  # 1-C i3-F-6: bilinçli JSON (şablon: {{}} kaçış)
        sonuc["sifirla"] = {{"kod": r.status_code}}
        if SENARYO != "saglam":
            r = c.post("/api/session/start", json={{"mode": "Manuel", "frequency": 100, "duty": 40, "phase": 0,
                       "intensity": 0, "duration_minutes": 5, "coil_ids": [1], "patient_name": "D137"}})
            sonuc["seans"] = {{"kod": r.status_code, "detail": (r.json() or {{}}).get("detail", "")}}
            c.post("/api/session/stop", json={{}})
        sonuc["sayac"] = dict(sayac)
        # Y9: acilis STOP mutabakati (3 sn sonra `startup-reconcile`) DB'siz kipte de STM'e STOP verir.
        son = time.monotonic() + 10
        while MUTABAKAT["stop"] < 1 and time.monotonic() < son:
            time.sleep(0.05)
        sonuc["mutabakat_stop"] = MUTABAKAT["stop"]
        if SENARYO.startswith("goc_gecici"):
            _y43(c, api, sayac)
        if SENARYO == "alter_kilitli":
            _alter_iyilesme(c, api, sayac)


def _sema_kolonlari():
    k = _sq.connect(TEDAVI_DB)
    try:
        return [r[1] for r in k.execute("PRAGMA table_info(ai_analyses)")]
    finally:
        k.close()


def _alter_iyilesme(c, api, sayac):
    # D2.24: kilit SURERKEN kolon eklenmedi ve dosya yerinde; kilidi tutan BIRAKINCA (backend YENIDEN BASLATILMAZ)
    # arka plan yeniden acmasi kolonu ekler, dbReady true olur, eski seans okunur, seans KAYIT kapisini gecer.
    a = sonuc["alter"] = {{"sonra": []}}
    a["kolon_kilitliyken"] = "reviewed_at" in _sema_kolonlari()
    a["dosya_kilitliyken"] = os.path.exists(TEDAVI_DB)
    TUTUCU["baglanti"].execute("ROLLBACK")
    TUTUCU["baglanti"].close()
    son = time.monotonic() + 40
    while time.monotonic() < son:
        a["sonra"].append(_saglik_olc(c))
        if a["sonra"][-1]["dbReady"] is True:
            break
        time.sleep(0.2)
    a["kolon_sonra"] = "reviewed_at" in _sema_kolonlari()
    try:
        a["seanslar"] = [s.get("treatment_mode") for s in api._get_treatment_db().get_session_history(limit=10)]
    except Exception as e:
        a["seanslar"] = "HATA " + type(e).__name__ + ": " + str(e)[:200]
    r = c.post("/api/session/start", json={{"mode": "Manuel", "frequency": 100, "duty": 40, "phase": 0,
               "intensity": 0, "duration_minutes": 5, "coil_ids": [1], "patient_name": "D224"}})
    a["seans"] = {{"kod": r.status_code, "detail": str((r.json() or {{}}).get("detail", ""))[:200]}}
    a["update"] = sayac["update"]
    c.post("/api/session/stop", json={{}})


def _getter_olc(api):
    # Y43: arka plan goc denemesi SURERKEN (kilitli tasima beklemesinde) DB alicilari BEKLEMEMELI — kurucu modul
    # kilidi altinda kossaydi her get_* (olay dongusundeki cagiranlar dahil) ~6 sn bloklanirdi.
    son = time.monotonic() + 20
    while not GOC["suruyor"] and time.monotonic() < son:
        time.sleep(0.02)
    sonuc["deneme_surerken"] = GOC["suruyor"]
    from database.patient_database import get_patient_database
    t0 = time.perf_counter()
    try:
        get_patient_database()
    except Exception:
        pass
    sonuc["pdb_sure"] = round(time.perf_counter() - t0, 3)
    t0 = time.perf_counter()
    api._get_treatment_db()
    sonuc["tdb_sure"] = round(time.perf_counter() - t0, 3)
    sonuc["deneme_sonra_hala"] = GOC["suruyor"]


def _saglik_olc(c):
    t0 = time.perf_counter()
    r = c.get("/api/health")
    g = r.json() if r.status_code == 200 else {{}}
    return {{"kod": r.status_code, "sure": round(time.perf_counter() - t0, 3), "dbReady": g.get("dbReady")}}


def _y43(c, api, sayac):
    y = sonuc["y43"] = {{"once": [], "sonra": []}}
    # Kilit SURERKEN: arka plan en az 2 kez yeniden denesin (acilis + 2). Saglik her an hizli, dbReady false.
    son = time.monotonic() + 30
    while GOC["deneme"] < 3 and time.monotonic() < son:
        y["once"].append(_saglik_olc(c))
        time.sleep(0.2)
    y["deneme_once"] = GOC["deneme"]
    KILIT["aktif"] = False  # kilidi tutan birakti — backend YENIDEN BASLATILMAZ
    son = time.monotonic() + 30
    while time.monotonic() < son:
        y["sonra"].append(_saglik_olc(c))
        if y["sonra"][-1]["dbReady"] is True:
            break
        time.sleep(0.2)
    y["deneme_sonra"] = GOC["deneme"]
    r = c.post("/api/session/start", json={{"mode": "Manuel", "frequency": 100, "duty": 40, "phase": 0,
               "intensity": 0, "duration_minutes": 5, "coil_ids": [1], "patient_name": "Y43"}})
    y["seans"] = {{"kod": r.status_code, "detail": str((r.json() or {{}}).get("detail", ""))[:200]}}
    y["update"] = sayac["update"]
    c.post("/api/session/stop", json={{}})
    # Goc edilen veri AYNI anahtarla okunur (yeni anahtar uretilmedi, dosya kaybolmadi)
    try:
        if SENARYO.endswith("hasta"):
            from database.patient_database import get_patient_database
            db = get_patient_database()
        else:
            db = api._get_treatment_db()
        with db._get_connection() as cn:
            y["veri"] = cn.execute("SELECT ad FROM kayit").fetchone()[0]
    except Exception as e:
        y["veri"] = "HATA " + type(e).__name__ + ": " + str(e)[:200]


def _sunucu_casusu(app, args):
    # 1-B inceleme (i1/B2): GERÇEKTEN dinlenecek port ve keşfe yayınlanan port kaydedilir (launcher `--port`
    # önceliği main() düzeyinde ölçülür — yalnız parser değil).
    sonuc["dinlenen_port"] = args.port
    sonuc["yayinlanan_port"] = os.environ.get("PEMF_API_PORT")
    return _Casus()


bs._build_server = _sunucu_casusu
try:
    sonuc["rc"] = bs.main({argv!r})
except BaseException as e:
    sonuc["kacan"] = type(e).__name__ + ": " + str(e)[:300]
    sonuc["iz"] = traceback.format_exc()[-1500:]
sonuc["yan"] = yan
sonuc["acl"] = ACL
sonuc["kasa"] = KASA
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


def _eski_semali_tedavi_db(app: Path) -> None:
    """D2.24: GERÇEK tedavi şeması + 1 seans; ardından yeni bir kolon (`ai_analyses.reviewed_at`) DÜŞÜRÜLÜR → sonraki açılış
    o kolonu ALTER ile eklemeye çalışır. Ebeveynde, anahtarsız (düz-metin) kurulur; çocukta bayrak 0."""
    from database import treatment_history_db as thdb

    db = thdb.TreatmentHistoryDB(app)
    sid = db.start_session("AlterKilitliSeans")
    db.end_session(sid)
    db.close_connections()
    del db
    c = sqlite3.connect(str(app / "pemf_treatment_history.db"))
    try:
        c.execute("ALTER TABLE ai_analyses DROP COLUMN reviewed_at")
        c.commit()
    finally:
        c.close()


#: D2.45: DB'leri şifreleyen DOĞRU anahtar ve legacy kaynaktaki BAYAT anahtar (sentetik).
_K_DOGRU, _K_BAYAT = "D245-e2e-dogru-anahtar", "D245-e2e-bayat-anahtar"


def _sifreli_iki_db(app: Path, anahtar: str) -> None:
    """Hasta + tedavi DB'si ebeveynde GERÇEK sqlcipher3 ile `anahtar`la şifrelenir (`kayit` tablosunda 1 satır)."""
    from database.sqlcipher_util import import_sqlcipher

    mod = import_sqlcipher()
    for ad in ("patients.db", "pemf_treatment_history.db"):
        kaynak = app / (ad + ".kaynak")
        _duz_db(kaynak)
        k = mod.connect(str(kaynak))
        try:
            hedef = str(app / ad).replace("'", "''")
            k.execute(f"ATTACH DATABASE '{hedef}' AS enc KEY '{anahtar}'")
            k.execute("SELECT sqlcipher_export('enc')")
            k.execute("DETACH DATABASE enc")
        finally:
            k.close()
        kaynak.unlink()
        assert (app / ad).read_bytes()[:16] != _SQLITE_BASLIK, f"ön koşul: {ad} şifreli kurulmalı"


def _sir_cozulemez_kur(app: Path, tmp_path: Path) -> None:
    """D2.45 (B-3.14 · Karar 6): iki DB DOĞRU anahtarla şifreli; sır dosyasındaki `sqlcipher_key` bu makinede
    ÇÖZÜLEMEZ (makine değişimi / Windows yeniden kurulumu); legacy `.sqlcipher_key` BAYAT. Dosya özetleri sonradan
    karşılaştırılmak üzere `d245_once.json`a yazılır."""
    _sifreli_iki_db(app, _K_DOGRU)
    (app / ".sqlcipher_key").write_text(_K_BAYAT, encoding="utf-8")
    onek = "DPAPI:" if os.name == "nt" else "MKEY:"
    blob = onek + base64.b64encode(b"D245 baska makinenin blobu " * 4).decode("ascii")
    (app / "pemf_secrets.json").write_text(
        json.dumps({"_version": 1, "auto": {"sqlcipher_key": blob}, "operator": {}, "embedded": {}}), encoding="utf-8"
    )
    ozet = {ad: hashlib.sha256((app / ad).read_bytes()).hexdigest() for ad in _D245_DOSYALAR}
    ozet["blob"] = blob
    (tmp_path / "d245_once.json").write_text(json.dumps(ozet), encoding="utf-8")


_D245_DOSYALAR = ("patients.db", "pemf_treatment_history.db", ".sqlcipher_key")
_D246_DOSYALAR = ("patients.db", "pemf_treatment_history.db")
_A21_DOSYALAR = ("patients.db", "pemf_treatment_history.db")


def _a21_kur(app: Path, tmp_path: Path, senaryo: str) -> None:
    """2-A inceleme A2-1.1 (D2.45 · Y9): iki DB DOĞRU anahtarla gerçekten şifreli; sır dosyası GERÇEKÇİ biçimde
    okunamaz — `sir_bozuk`: JSON yarıda kesilmiş (güç kesintisi / elle düzenleme); `sir_cozulemez_ikisi`: İKİ kritik
    anahtar da (`sqlcipher_key` + `patient_fernet_key`) bu makinede ÇÖZÜLEMEYEN DPAPI/MKEY blobu (makine değişimi /
    Windows yeniden kurulumu — ikisi aynı mekanizmayla sarıldığı için birlikte düşer). D2.45 kolu (`sir_cozulemez`)
    yalnız `sqlcipher_key`i çözülemez yapıyor, `patient_fernet_key` YOKTU → içe aktarmadaki ölüm görünmüyordu."""
    _sifreli_iki_db(app, _K_DOGRU)
    sir = app / "pemf_secrets.json"
    if senaryo == "sir_bozuk":
        sir.write_text('{"_version": 1, "auto": {"sqlcipher_key": "DPAPI:QUJD', encoding="utf-8")
    else:
        onek = "DPAPI:" if os.name == "nt" else "MKEY:"
        doc = {
            "_version": 1,
            "auto": {
                "sqlcipher_key": onek + base64.b64encode(b"A21 baska makinenin sqlcipher blobu " * 4).decode("ascii"),
                "patient_fernet_key": onek + base64.b64encode(b"A21 baska makinenin fernet blobu " * 4).decode("ascii"),
            },
            "operator": {},
            "embedded": {},
        }
        sir.write_text(json.dumps(doc), encoding="utf-8")
    ozet = {ad: hashlib.sha256((app / ad).read_bytes()).hexdigest() for ad in (*_A21_DOSYALAR, "pemf_secrets.json")}
    (tmp_path / "a21_once.json").write_text(json.dumps(ozet), encoding="utf-8")


_IKINCI_DOSYALAR = ("patients.db", "pemf_treatment_history.db", "pemf_secrets.json", "logs/backend_service.log")


def _ikinci_hesap_kur(app: Path, tmp_path: Path) -> None:
    """2-A inceleme A2-1.4 (B-3.51 · A-2A.1 · Y9): İLK hesabın kurulumu — iki DB doğru anahtarla gerçekten şifreli, sır
    dosyasında iki kritik anahtar bu makinenin GERÇEK DPAPI/MKEY'iyle sarılı, ilk hesabın günlüğü. Test bunu sonra BAŞKA bir
    SID'e kilitler (ikinci Windows hesabı OLUŞTURULMAZ)."""
    from utils import secrets_manager as sm

    _sifreli_iki_db(app, _K_DOGRU)
    alan = base64.urlsafe_b64encode(bytes(range(32, 64))).decode("ascii")
    doc = {
        "_version": 1,
        "auto": {"sqlcipher_key": sm._enc(_K_DOGRU, critical=True), "patient_fernet_key": sm._enc(alan, critical=True)},
        "operator": {},
        "embedded": {},
    }
    (app / "pemf_secrets.json").write_text(json.dumps(doc), encoding="utf-8")
    (app / "logs").mkdir()
    (app / "logs" / "backend_service.log").write_text("ilk hesabin gunlugu\n", encoding="utf-8")
    ozet = {ad: hashlib.sha256((app / ad).read_bytes()).hexdigest() for ad in _IKINCI_DOSYALAR}
    (tmp_path / "ikinci_once.json").write_text(json.dumps(ozet), encoding="utf-8")


def _binding_yok_kur(app: Path, tmp_path: Path) -> None:
    """D2.46 (B-3.48): iki DB at-rest anahtarıyla GERÇEKTEN şifreli, anahtar sır dosyasında OKUNUR; çocukta sqlcipher3
    YOK, bayrak 0 (B-3.45 yolu: bayrak servise ulaşmamış). Özetler `d246_once.json`a yazılır."""
    _sifreli_iki_db(app, _K_DOGRU)
    (app / "pemf_secrets.json").write_text(
        json.dumps({"_version": 1, "auto": {"sqlcipher_key": _K_DOGRU}, "operator": {}, "embedded": {}}),
        encoding="utf-8",
    )
    ozet = {ad: hashlib.sha256((app / ad).read_bytes()).hexdigest() for ad in _D246_DOSYALAR}
    (tmp_path / "d246_once.json").write_text(json.dumps(ozet), encoding="utf-8")


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
            "PEMF_ENCRYPT_AT_REST": "1"
            if senaryo.startswith("goc")
            or senaryo in ("saglam", "sir_cozulemez", "sir_bozuk", "sir_cozulemez_ikisi", "ikinci_hesap")
            else "0",
        }
    )
    if senaryo in ("goc_hasta", "goc_gecici_hasta"):
        _duz_db(app / "patients.db")
    elif senaryo in ("goc_tedavi", "goc_gecici_tedavi"):
        _duz_db(app / "pemf_treatment_history.db")
    elif senaryo == "bozuk_ikisi":
        for ad in ("patients.db", "pemf_treatment_history.db"):
            (app / ad).write_bytes(b"BU BIR SQLITE DOSYASI DEGIL " * 64)
    elif senaryo == "bozuk_port":
        # 1-A açık madde 6 (kol D1.14 kapısında): launcher `--port` verir; ortamdaki bozuk port açılışı öldürmemeli.
        env["PEMF_API_PORT"] = "80O0"
    elif senaryo == "alter_kilitli":
        _eski_semali_tedavi_db(app)
    elif senaryo == "sir_cozulemez":
        _sir_cozulemez_kur(app, tmp_path)
    elif senaryo == "binding_yok":
        _binding_yok_kur(app, tmp_path)
    elif senaryo in ("sir_bozuk", "sir_cozulemez_ikisi"):
        _a21_kur(app, tmp_path, senaryo)
    elif senaryo == "ikinci_hesap":
        _ikinci_hesap_kur(app, tmp_path)
        env.pop("PEMF_LOG_DIR")  # gerçek günlük dizini türetimi (veri kökü) + %TEMP% düşüşü sınansın
    return env, app


#: Launcher biçimi (`launcher/core/src/backend.rs`: `--port` HER ZAMAN verilir).
ARGV_LAUNCHER = ["--host", "127.0.0.1", "--port", "51999", "--no-headless-services"]


def _kos(tmp_path: Path, senaryo: str, argv: list[str] | None = None) -> tuple[dict, Path]:
    env, app = _kur(tmp_path, senaryo)
    return _cocuk(tmp_path, env, senaryo, argv), app


def _cocuk(tmp_path: Path, env: dict, senaryo: str, argv: list[str] | None = None) -> dict:
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
            return json.loads(satir[len("SONUC ") :])
    raise AssertionError(f"çocuk sonuç basmadı (rc={p.returncode}); stderr sonu: {p.stderr[-1500:]}")


#: Çocuğun başlatmasına izin verilen alt süreçler (D1.14 ile aynı: `platform` sürüm sorgusu) + D2.79: `utils.file_acl`ın veri kökü
#: kilidi — YALNIZ onun tam komut biçimi (Users / Authenticated Users kaldırılır; SYSTEM, Administrators ve süreç SID'i verilir).
#: ⚠️ D2.79 öncesi bu kilit çocukta HİÇ koşmuyordu: yalıtık ortamda `USERNAME` yok → `getpass.getuser()` istisna → her
#: `keep_current_user=True` kilidi SESSİZCE düşüyordu (D-3.1'in ortam biçimi). SID ile kilit artık gerçekten uygulanıyor.
#: Yol BOŞLUKSUZ (`\S+`): eskiden `.+` idi — yol ile `/inheritance:r` arasına ek seçenek (`/T`, `/grant …`) sızabiliyordu.
#: Bozuk-bayrak aparatıyla AYNI desen (tests/test_bozuk_sayisal_bayrak_ESTOP_OLDURMEZ.py) — biri değişirse öteki de.
_IZINLI_ALT_SUREC = re.compile(
    r"subprocess\.Popen:(?:"
    r'(?:[A-Za-z]:\\(?:[^"\\]+\\)*)?cmd\.exe /c "?ver"?'
    r"|icacls [A-Za-z]:\\\S+ /inheritance:r /remove:g \*S-1-5-32-545 /remove:g \*S-1-5-11"
    r"(?: /remove:g \*S-1-(?:1-0|5-4|2-0|2-1|5-32-546|5-7|5-2))*"  # E2-1.3: öbür geniş grupların açık ACE'leri de kaldırılır
    r" /grant:r \*S-1-5-18:(?:\(OI\)\(CI\))?F /grant:r \*S-1-5-32-544:(?:\(OI\)\(CI\))?F"
    r"(?: /grant:r \*S-1-5-(?:18|21-[0-9-]+):(?:\(OI\)\(CI\))?F)*"
    r")",
    re.IGNORECASE,
)


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
    assert s["estop"]["sure"] < SAGLIK_SURE_SINIRI_SN, f"ACİL DURDUR yanıtı {s['estop']['sure']:.2f} sn (bloklandı)"
    assert s["sifirla"]["kod"] == 200, f"mandal 'Sıfırla' bu kipte çalışmadı (D1.81 · Y4): {s['sifirla']}"
    # 2-A (Y9): açılış STOP mutabakatı (`startup-reconcile`, GERÇEK HardwareController) DB'siz kipte de koşar.
    assert s.get("mutabakat_stop", 0) >= 1, (
        f"açılış STOP mutabakatı STM'e STOP vermedi (10 sn içinde): {s.get('mutabakat_stop')} — önceki süreçten kalan "
        "bobin durumu temizlenmedi"
    )
    assert all(h["kod"] == 200 for h in s["saglik"]), f"sağlık ucu düştü: {s['saglik']}"
    yavas = [round(h["sure"], 2) for h in s["saglik"] if h["sure"] >= SAGLIK_SURE_SINIRI_SN]
    assert not yavas, (
        f"/api/health {yavas} sn — launcher 3 sn'de vazgeçip dbReady'yi 'bilinmiyor' sayar ve güncellemeyi "
        "ONAYLAR; olay döngüsü bloklandığı için ACİL DURDUR da gecikir (açılışta açılamayan DB yeniden deneniyor)"
    )
    assert s["ag"] == [], f"çocuk AĞA çıkmayı denedi (bekçi engelledi): {s['ag']}"
    assert all(_IZINLI_ALT_SUREC.fullmatch(a) for a in s["alt"]), f"izin listesi dışı alt süreç: {s['alt']}"
    assert s.get("rc") == 0, f"main() dönüş kodu {s.get('rc')}"


#: Kimliksiz uçlara (auth-muaf `/api/health`, seans 503 detayı) ÇIKMAMASI gerekenler: dosya yolu ve ham istisna metni.
_SIZINTI = (
    "\\",
    "/",
    ".db",
    "WinError",
    "PermissionError",
    "initialization failed",
    "file is not a database",
    "Traceback",
)


def _deneme_surerken_iddialari(s: dict) -> None:
    """Y43: ölçüm, arka plan göç denemesi kilitli taşımada BEKLERKEN alındı ve DB alıcıları beklemedi."""
    assert s["deneme_surerken"], "arka planda yeniden deneme BAŞLAMADI (20 sn içinde göç girişimi yok)"
    sureler = {k: s[k] for k in ("pdb_sure", "tdb_sure")}
    assert s["deneme_sonra_hala"], (
        f"DB alıcısı arka plan göç denemesi BİTENE KADAR BEKLEDİ {sureler} — kurucu modül kilidi altında koşuyor "
        "(olay döngüsündeki her `get_*` çağıranı ~6 sn bloklanır)"
    )
    yavas = {k: s[k] for k in ("pdb_sure", "tdb_sure") if s[k] >= SAGLIK_SURE_SINIRI_SN}
    assert not yavas, (
        f"arka plan göç denemesi sürerken DB alıcısı BEKLEDİ {yavas} — kurucu modül kilidi altında koşuyor"
    )


def _db_yok_iddialari(s: dict, sebep_kalibi: str, kok: Path) -> None:
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
    # 1-B bağımsız inceleme (i2): metin operatör içindir — YOL ve istisna ayrıntısı kimliksiz uca SIZMAZ (ölçüldü:
    # `{exc}` / `@ {app_data_dir}` eklenince kapı yeşildi) …
    for metin in [h["dbSebep"] for h in s["saglik"]] + [s["seans"]["detail"]]:
        sizan = [p for p in _SIZINTI if p in metin] + ([str(kok)] if str(kok) in metin else [])
        assert not sizan, f"dbSebep/seans detayı ayrıntı SIZDIRIYOR {sizan}: {metin!r}"
    # … ve kök neden zinciri YALNIZ günlüktedir: o satır silinirse saha teşhisi kaybolur (ölçüldü: kapı yeşildi).
    gunluk = (kok / "log" / "backend_service.log").read_text(encoding="utf-8", errors="replace")
    assert "DB'SİZ (kısıtlı) açılıyor" in gunluk and "Traceback" in gunluk, (
        "açılış DB hatası günlüğe izle (Traceback) YAZILMADI — sebep metni bilinçli ayrıntısız, teşhis yalnız günlükte"
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
    _db_yok_iddialari(s, r"g[öo]ç", tmp_path)
    _deneme_surerken_iddialari(s)
    _duz_metin_yerinde(app, "patients.db" if senaryo == "goc_hasta" else "pemf_treatment_history.db")


def test_KRITIK_GENEL_bozuk_DB_RuntimeError_de_backendi_OLDURMEZ(tmp_path):
    """C1-7: yalnız `GocBekliyorHatasi`'nı yakalayan dar düzeltme Karar-6 / bozuk dosya `RuntimeError`larında
    backend'i (ve E-stop'u) öldürmeye devam ederdi."""
    s, app = _kos(tmp_path, "bozuk_ikisi")
    _ortak_iddialar(s)
    _db_yok_iddialari(s, r"a[çc][ıi]lamad[ıi]", tmp_path)
    for ad in ("patients.db", "pemf_treatment_history.db"):
        assert (app / ad).read_bytes().startswith(b"BU BIR SQLITE"), f"{ad}: bozuk dosyaya DOKUNULDU"


def test_KRITIK_D224_ALTER_KILITLIYKEN_backend_DBSIZ_acilir_kilit_kalkinca_KOLON_eklenir(tmp_path):
    """D2.24 (B-3.81 · Y9) UÇTAN UCA: yeni kolonun ilk açılışında tedavi DB'sinin yazma kilidi başka bir bağlantıda
    (gerçek `BEGIN IMMEDIATE`). Eskiden `_safe_add_column` `database is locked`ı YUTUYORDU → DB KOLONSUZ açılıyor,
    `dbReady` TRUE, seans başlıyor, kolonu yazan kayıt "no such column" ile düşüyordu (ölçüldü). Artık açılış görünür
    biçimde durur: backend DB'siz KISITLI kipte (ACİL DURDUR + açılış STOP mutabakatı + hızlı sağlık ucu, seans 503,
    yeni anahtar ÜRETİLMEZ, dosya yerinde, karantina YOK); kilit kalkınca YENİDEN BAŞLATMADAN arka planda açılır, kolon
    eklenir, eski seans okunur, yeni seans başlar."""
    s, app = _kos(tmp_path, "alter_kilitli")
    _ortak_iddialar(s)
    _db_yok_iddialari(s, r"a[çc][ıi]lamad[ıi]", tmp_path)
    a = s["alter"]
    assert a["kolon_kilitliyken"] is False and a["dosya_kilitliyken"] is True, f"kurgu/dosya: {a}"
    assert any(h["dbReady"] is True for h in a["sonra"]), (
        f"kilit kalkınca dbReady true OLMADI (40 sn): {a['sonra'][-3:]}"
    )
    assert a["kolon_sonra"] is True, "kilit kalkınca kolon EKLENMEDİ"
    assert a["seanslar"] == ["AlterKilitliSeans"], f"eski seans kaydı okunamadı: {a['seanslar']}"
    # Kayıt kapısı GEÇİLDİ: bobin sürülmeye çalışıldı (çocukta STM kartı yok → ürün "hiçbir bobin komutu kabul etmedi"
    # 503'ünü verir — Y43 kolundaki ölçütün aynısı; kayıt/DB nedeni OLMAMALI).
    assert a["update"] >= 1, f"DB iyileşti ama seans kayıt kapısında kaldı (bobin sürülmedi): {a['seans']}"
    assert not re.search(r"kay[ıi]t|veritaban|a[çc][ıi]lamad", a["seans"]["detail"], re.IGNORECASE), (
        f"iyileşme sonrası seans hâlâ KAYIT/DB nedeniyle reddedildi: {a['seans']}"
    )
    assert sorted(p.name for p in app.glob("*.acilamadi-*")) == [], (
        "kilit anahtar uyuşmazlığı değil — karantina OLMAMALI"
    )
    gunluk = (tmp_path / "log" / "backend_service.log").read_text(encoding="utf-8", errors="replace")
    assert "ai_analyses.reviewed_at kolonu eklenemedi" in gunluk, (
        "kök neden (eklenemeyen kolon + kilit) günlüğe YAZILMADI"
    )
    assert "Yeni SQLCipher anahtari uretildi" not in gunluk, "DB'siz kipe düşerken YENİ ANAHTAR üretildi (Y9 ihlali)"


def test_KRITIK_D245_SIR_COZULEMEZKEN_backend_DBSIZ_acilir_YENI_ANAHTAR_yok_KARANTINA_yok(tmp_path):
    """D2.45 (B-3.14 · Karar 6 · Y9) UÇTAN UCA, GERÇEK `main()`: sır dosyasındaki at-rest anahtarı bu makinede
    çözülemiyor, legacy `.sqlcipher_key` BAYAT. Eskiden tedavi DB'si RuntimeError'u yutup bayat legacy anahtara
    düşüyor, kurtarılabilir geçmişi `.acilamadi-*` olarak KARANTİNAYA alıp yerine bayat anahtarla BOŞ DB kuruyordu
    (ölçüldü). Şimdi backend DB'siz KISITLI kipte açılır (ACİL DURDUR + açılış STOP mutabakatı + hızlı sağlık ucu,
    seans 503); arka plan yeniden açma denemeleri de YENİ ANAHTAR ÜRETMEZ; iki DB, legacy anahtar dosyası ve
    çözülemeyen sır DEĞİŞMEZ, karantina YOK."""
    if not _sqlcipher_var():
        pytest.skip("sqlcipher3 yok — şifreli DB senaryosu kurulamaz")
    s, app = _kos(tmp_path, "sir_cozulemez")
    _ortak_iddialar(s)
    _db_yok_iddialari(s, r"a[çc][ıi]lamad[ıi]", tmp_path)
    assert sorted(p.name for p in app.glob("*.acilamadi-*")) == [], (
        "sır çözülemezken veritabanı KARANTİNAYA alındı (legacy adayla uyuşmazlık kararı — B-3.14)"
    )
    once = json.loads((tmp_path / "d245_once.json").read_text(encoding="utf-8"))
    degisen = [ad for ad in _D245_DOSYALAR if hashlib.sha256((app / ad).read_bytes()).hexdigest() != once[ad]]
    assert degisen == [], f"fail-closed açılışta veri/anahtar dosyasına DOKUNULDU: {degisen}"
    sir = json.loads((app / "pemf_secrets.json").read_text(encoding="utf-8"))
    assert sir["auto"]["sqlcipher_key"] == once["blob"], "çözülemeyen sır EZİLDİ (yeni anahtar üretildi)"
    gunluk = (tmp_path / "log" / "backend_service.log").read_text(encoding="utf-8", errors="replace")
    assert "Yeni SQLCipher anahtari uretildi" not in gunluk, "DB'siz kipe düşerken YENİ ANAHTAR üretildi (Y9 ihlali)"
    # 2-A inceleme A2-1.5: silinen eski log metni yerine legacy adayın DB'yi AÇTIĞI satır (gerçek işaret).
    assert "LEGACY anahtarla acildi" not in gunluk and "legacy yola" not in gunluk, (
        "birincil anahtar OKUNAMAZKEN tedavi DB'si legacy adayla AÇILDI (Karar 6 ihlali)"
    )
    assert "Sır çözülemedi (sqlcipher_key)" in gunluk, "fail-closed nedeni (çözülemeyen sır) günlükte YOK"


def test_KRITIK_D246_BINDING_YOKKEN_sifreli_DB_KARANTINAYA_alinmaz_backend_DBSIZ_acilir(tmp_path):
    """D2.46 (B-3.48 · Y9) UÇTAN UCA, GERÇEK `main()`: iki DB at-rest anahtarıyla şifreli, anahtar sırda okunur, ama
    çocukta sqlcipher3 binding YOK ve bayrak 0. Eskiden hasta DB'si düz bağlantının "file is not a database"ını
    uyuşmazlık sayıp sağlam şifreli dosyayı KARANTİNAYA alıyor, yerine DÜZ-METİN DB kuruyordu. Şimdi backend DB'siz
    KISITLI kipte açılır (ACİL DURDUR + açılış STOP mutabakatı + hızlı sağlık ucu, seans 503); iki DB değişmez,
    karantina YOK, yeni anahtar üretilmez."""
    if not _sqlcipher_var():
        pytest.skip("sqlcipher3 yok — şifreli DB senaryosu kurulamaz")
    s, app = _kos(tmp_path, "binding_yok")
    _ortak_iddialar(s)
    _db_yok_iddialari(s, r"a[çc][ıi]lamad[ıi]", tmp_path)
    assert sorted(p.name for p in app.glob("*.acilamadi-*")) == [], (
        "binding YOKKEN şifreli veritabanı KARANTİNAYA alındı (B-3.48)"
    )
    once = json.loads((tmp_path / "d246_once.json").read_text(encoding="utf-8"))
    degisen = [ad for ad in _D246_DOSYALAR if hashlib.sha256((app / ad).read_bytes()).hexdigest() != once[ad]]
    assert degisen == [], f"binding yokken şifreli DB'ye DOKUNULDU (yerine düz-metin DB?): {degisen}"
    gunluk = (tmp_path / "log" / "backend_service.log").read_text(encoding="utf-8", errors="replace")
    assert "sqlcipher3 binding YOK" in gunluk, "fail-closed nedeni (binding yok) günlükte YOK"
    assert "Yeni SQLCipher anahtari uretildi" not in gunluk


@pytest.mark.parametrize("senaryo", ["sir_bozuk", "sir_cozulemez_ikisi"])
def test_KRITIK_A21_SIR_BOZUK_ya_da_IKI_ANAHTAR_COZULEMEZKEN_backend_ICE_AKTARMADA_OLMEZ_DBSIZ_acilir(
    tmp_path, senaryo
):
    """2-A inceleme A2-1.1 (D2.45 · Y9 · Ö.4-Y8) UÇTAN UCA, GERÇEK `main()`: planın D2.45 kapısı "bozuk sırla açılışta
    POST E-stop 200 ve STM STOP". `pemf_gui.config`in modül düzeyi `ConfigManager()`ı alan anahtarını İÇE AKTARMADA
    alıyordu → sır dosyası bozukken ya da `patient_fernet_key` çözülemezken fail-closed `RuntimeError`
    `backend_service` → `headless_core` → `patient_database` içe aktarmasından kaçıyor, backend HİÇ açılmıyordu:
    ACİL DURDUR, sağlık ucu, açılış STOP mutabakatı ve günlük YOK (ölçüldü — veri sağlam ama cihaz kör). Şimdi backend
    DB'siz KISITLI kipte açılır (seans 503), iki DB değişmez, karantina YOK, YENİ ANAHTAR ÜRETİLMEZ (sır dosyası ezilmez
    / yeniden kurulmaz), neden günlükte."""
    if not _sqlcipher_var():
        pytest.skip("sqlcipher3 yok — şifreli DB senaryosu kurulamaz")
    s, app = _kos(tmp_path, senaryo)
    _ortak_iddialar(s)
    _db_yok_iddialari(s, r"a[çc][ıi]lamad[ıi]", tmp_path)
    assert sorted(p.name for p in app.glob("*.acilamadi-*")) == [], "sır okunamazken veritabanı KARANTİNAYA alındı"
    once = json.loads((tmp_path / "a21_once.json").read_text(encoding="utf-8"))
    degisen = [ad for ad in _A21_DOSYALAR if hashlib.sha256((app / ad).read_bytes()).hexdigest() != once[ad]]
    assert degisen == [], f"sır okunamazken veri dosyasına DOKUNULDU: {degisen}"
    sir = app / "pemf_secrets.json"
    if senaryo == "sir_cozulemez_ikisi":
        assert hashlib.sha256(sir.read_bytes()).hexdigest() == once["pemf_secrets.json"], (
            "çözülemeyen sır dosyası DEĞİŞTİ (yeni anahtar üretildi / ezildi)"
        )
    else:
        # Bozuk dosya kanıt olarak `.corrupt.<zaman>` adına alınır (bilinçli, kapı: test_bozuk_sir_dosyasi_kalici_…);
        # yerine YENİ sır dosyası (= yeni anahtarlar) KURULMAMALI.
        assert not sir.exists(), "bozuk sırın yerine YENİ sır dosyası kuruldu (yeni anahtar üretildi)"
        assert list(app.glob("pemf_secrets.json.corrupt.*")), "bozuk sır kanıt olarak saklanmadı"
    gunluk = (tmp_path / "log" / "backend_service.log").read_text(encoding="utf-8", errors="replace")
    assert "Yeni SQLCipher anahtari uretildi" not in gunluk and "Yeni RASTGELE Fernet" not in gunluk, (
        "sır okunamazken YENİ ANAHTAR üretildi (Y9 ihlali)"
    )
    assert re.search(r"S[ıi]r [çc][öo]z[üu]lemedi|BOZUK|karantina kaniti", gunluk), "sır hatasının nedeni günlükte YOK"


@pytest.mark.skipif(os.name != "nt", reason="Windows ACL (icacls) benzetimi")
def test_KRITIK_A14_IKINCI_HESAP_veri_koku_KILITLI_backend_DBSIZ_acilir_gunluk_TEMPe_yeni_anahtar_YOK(tmp_path):
    """2-A inceleme A2-1.4 (D2.45 · B-3.51 · A-2A.1 · Y9) UÇTAN UCA, GERÇEK `main()`: veri kökü ilk Windows hesabının
    ACL'ine kilitli (benzetim: `icacls /inheritance:r /grant:r *S-1-5-19:(OI)(CI)(F)` — bu kullanıcı listeleyemez/okuyamaz/
    yazamaz; ikinci hesap OLUŞTURULMAZ). D2.45'in birim kapısı günlük dizini ölüm noktasını yalnız "dizin yerinde DOSYA"
    (`FileExistsError`) ile ölçüyordu; ikinci hesabın GERÇEK hatası `PermissionError` (WinError 5) — düşüş yalnız
    `FileExistsError`ı yakalasa 40 kapı yeşil kalıyordu (ölçüldü), backend sebepsiz ölürdü. Beklenen: backend DB'siz KISITLI
    kipte açılır (ACİL DURDUR + açılış STOP mutabakatı + hızlı sağlık ucu, seans 503), günlük kullanıcının TEMP'ine düşer ve
    nedeni söyler, YENİ ANAHTAR üretilmez / kimlik kasasına yazılmaz, ilk hesabın dosyaları DEĞİŞMEZ, karantina YOK."""
    if not _sqlcipher_var():
        pytest.skip("sqlcipher3 yok — şifreli DB senaryosu kurulamaz")
    env, app = _kur(tmp_path, "ikinci_hesap")
    kilit = subprocess.run(
        ["icacls", str(app), "/inheritance:r", "/grant:r", "*S-1-5-19:(OI)(CI)(F)", "/T", "/C"], capture_output=True
    )
    try:
        try:
            os.listdir(app)
            erisim = "LISTELENDI"
        except PermissionError:
            erisim = "REDDEDILDI"
        assert erisim == "REDDEDILDI", f"benzetim kurulamadı (icacls rc={kilit.returncode}): veri kökü listelenebiliyor"
        s = _cocuk(tmp_path, env, "ikinci_hesap")
    finally:
        geri = subprocess.run(["icacls", str(app), "/reset", "/T", "/C"], capture_output=True)
    assert geri.returncode == 0 and os.listdir(app), "veri kökünün ACL'si geri ALINAMADI"
    _ortak_iddialar(s)
    # KP-5 · 18: #22 (`a4b18def`) ikinci hesapta nedeni "açılamadı"dan EYLEM söyleyen erişim iletisine çevirdi (`sistem.db.erisimYok`:
    # "… erişimi yok — başlatıcıdaki paylaşım kartıyla erişim verin."). KRİTİK amaç aynı: DB'siz kip + operatöre NEDEN + EYLEM.
    # (İH kapısı bu dosyayı kaçırdı: test değişen koda yalnız alt süreçteki gerçek `main()` ile ulaşır ve eski metni regex'le
    # bekler — değişen ad / katalog anahtarıyla kurulan grep kapı listesi onu SEÇMEZ; bkz. KAPSAM.md KP-5 · 18.)
    for h in s["saglik"]:
        assert h["dbReady"] is False, s["saglik"]
        assert re.search(r"eri[şs]imi yok", h["dbSebep"] or "") and re.search(r"payla[şs][ıi]m", h["dbSebep"] or ""), (
            f"ikinci hesapta neden ERİŞİM + EYLEM (paylaşım kartı) söylemiyor: {h['dbSebep']!r}"
        )
        assert not re.search(r"a[çc][ıi]lamad[ıi]", h["dbSebep"] or ""), (
            "erişim sorunu 'açılamadı' (bozukluk) gibi söyleniyor"
        )
    # KP-5 · 17 (İH #22 kalıntısı): hasta listesi de AYNI erişim nedenini söyler (sağlık nedeniyle tek kaynak) — "bağlantı / veritabanı
    # açılamıyor" değil; arayüz 503 gerekçesini gösterir (PatientScreen).
    hl = s["hastalar"]
    assert hl["kod"] == 503 and hl["detail"] == s["saglik"][0]["dbSebep"], (
        f"ikinci hesapta hasta listesi erişim nedenini söylemiyor: {hl} · sağlık: {s['saglik'][0]['dbSebep']!r}"
    )
    assert s["seans"]["kod"] == 503 and "kayıt" in s["seans"]["detail"].lower(), f"DB'siz seans: {s['seans']}"
    assert s["sayac"]["update"] == 0, f"DB'siz kipte STM bobini sürülmeye çalışıldı ({s['sayac']['update']})"
    once = json.loads((tmp_path / "ikinci_once.json").read_text(encoding="utf-8"))
    degisen = [ad for ad in _IKINCI_DOSYALAR if hashlib.sha256((app / ad).read_bytes()).hexdigest() != once[ad]]
    assert degisen == [], f"ikinci hesap ilk hesabın dosyalarına DOKUNDU: {degisen}"
    assert sorted(p.name for p in app.glob("*.acilamadi-*")) == [], "erişilemeyen veri kökünde karantina"
    assert s["kasa"] == [], f"ikinci hesapta YENİ ANAHTAR kimlik kasasına yazıldı (Karar 6 · Y9): {s['kasa']}"
    gunluk = Path(env["TEMP"]) / "PEMF_GUI" / "logs" / "backend_service.log"
    assert gunluk.exists(), "günlük yedek dizine (%TEMP%) düşmedi — günlük dizini yazılamayınca backend sebepsiz ölür"
    metin = gunluk.read_text(encoding="utf-8", errors="replace")
    assert "GUNLUK DIZINI YAZILAMADI" in metin and "PermissionError" in metin, "günlük düşüşünün NEDENİ yazılmadı"
    assert "OKUNAMADI/YAZILAMADI" in metin, "sır okunamadığı (fail-closed nedeni) günlükte YOK"
    assert "Yeni SQLCipher anahtari uretildi" not in metin and "Yeni RASTGELE Fernet" not in metin


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


@pytest.mark.parametrize("senaryo", ["goc_gecici_hasta", "goc_gecici_tedavi"])
def test_KRITIK_Y43_acilista_acilamayan_DB_ARKA_PLANDA_acilir_dbReady_YENIDEN_BASLATMADAN_true(tmp_path, senaryo):
    """Y43 (sahip): açılışta göç kilide takıldı → backend DB'siz açıldı (D1.37). Kilit sonradan kalkınca DB arka
    planda açılır; `dbReady` kendiliğinden true, seans başlar. Eskiden "bu süreçte yeniden denenmez" kilidi
    cihazı YENİDEN BAŞLATMADAN tedaviye dönülemiyordu."""
    if not _sqlcipher_var():
        pytest.skip("sqlcipher3 yok")
    s, app = _kos(tmp_path, senaryo)
    _ortak_iddialar(s)
    _db_yok_iddialari(s, r"g[öo]ç", tmp_path)  # kilit sürerken: DB'siz kısıtlı kip (D1.37 sözleşmesi aynen)
    _deneme_surerken_iddialari(s)
    y = s["y43"]
    assert y["deneme_once"] >= 3, (
        f"açılışta açılamayan DB ARKA PLANDA yeniden DENENMEDİ (göç girişimi {y['deneme_once']}; açılış + ≥2 beklenirdi)"
    )
    olcumler = y["once"] + y["sonra"]
    yavas = [h["sure"] for h in olcumler if h["kod"] != 200 or h["sure"] >= SAGLIK_SURE_SINIRI_SN]
    assert not yavas, f"arka plan yeniden denemesi SÜRERKEN /api/health yavaş/düştü: {yavas} (olay döngüsü bloklandı)"
    assert not any(h["dbReady"] for h in y["once"]), f"kilit sürerken dbReady true: {y['once']}"
    assert y["sonra"] and y["sonra"][-1]["dbReady"] is True, (
        f"kilit kalktı ama DB arka planda AÇILMADI — dbReady {[h['dbReady'] for h in y['sonra']][-3:]} "
        f"(göç girişimi {y['deneme_once']}→{y['deneme_sonra']}; cihaz yeniden başlatılmadan tedavi başlamaz)"
    )
    # Kayıt kapısı GEÇİLDİ: bobin sürülmeye çalışıldı. (Çocukta STM kartı yok → ürün "hiçbir bobin komutu kabul
    # etmedi" 503'ü verir; kayıt/DB nedeni OLMAMALI.)
    assert y["update"] >= 1, f"DB açıldı ama seans kayıt kapısında kaldı (bobin sürülmedi): {y['seans']}"
    assert not re.search(r"kay[ıi]t|g[öo][çc]|veritaban", y["seans"]["detail"], re.IGNORECASE), (
        f"DB açıldıktan sonra seans hâlâ KAYIT nedeniyle reddedildi: {y['seans']}"
    )
    assert y["veri"] == "GocBekleyenHasta", f"göç edilen veri okunamadı: {y['veri']}"
    ad = "patients.db" if senaryo.endswith("hasta") else "pemf_treatment_history.db"
    assert (app / ad).read_bytes()[:16] != _SQLITE_BASLIK, f"{ad} hâlâ düz-metin — göç arka planda tamamlanmadı"
    assert sorted(p.name for p in app.glob("*.acilamadi-*")) == [], "karantina kopyası oluştu"
    gunluk = (tmp_path / "log" / "backend_service.log").read_text(encoding="utf-8", errors="replace")
    assert gunluk.count("Yeni SQLCipher anahtari uretildi") <= 1, "arka plan denemesi YENİ anahtar üretti"


def test_Y43_yeniden_deneme_ARALIKLARI_artar_son_aralikta_surer_durdurulunca_biter(monkeypatch, tmp_path):
    """Döngü sınıf özniteliğindeki aralıkları SIRAYLA bekler (5 sn → 30 sn → 2 dk), sonra son aralıkta sürer;
    açılamayan DB'yi her turda dener; durdurma olayı (çekirdek `quit`) döngüyü bitirir."""
    import logging
    import types

    import headless_core as hc
    from database import treatment_history_db as thdb

    araliklar = hc.HeadlessCore.DB_YENIDEN_DENEME_ARALIKLARI_SN
    assert araliklar[0] >= 1 and list(araliklar) == sorted(araliklar) and araliklar[-1] > araliklar[0], araliklar
    assert araliklar[-1] <= 300, f"son aralık {araliklar[-1]} sn — düzelen DB çok geç fark edilir"

    class _Dur:
        def __init__(self):
            self.bekleyisler = []

        def is_set(self):
            return False

        def wait(self, sn):
            self.bekleyisler.append(sn)
            return len(self.bekleyisler) >= 6  # 6. beklemede çekirdek kapanıyor

    denemeler = []

    def _acilmaz(app_data_dir):
        denemeler.append(app_data_dir)
        raise RuntimeError("hala kilitli")

    monkeypatch.setattr(thdb, "acilista_acilamayani_yeniden_ac", _acilmaz)
    sahte = types.SimpleNamespace(
        DB_YENIDEN_DENEME_ARALIKLARI_SN=araliklar,
        db_acilis_hatalari={"tedavi": "Tedavi kaydı veritabanı göç bekliyor"},
        _db_yeniden_dur=_Dur(),
        app_data_dir=tmp_path,
        logger=logging.getLogger("y43"),
        _DB_ADI=hc.HeadlessCore._DB_ADI,
    )
    hc.HeadlessCore._db_yeniden_deneme_dongusu(sahte)
    beklenen = list(araliklar) + [araliklar[-1]] * (6 - len(araliklar))
    assert sahte._db_yeniden_dur.bekleyisler == beklenen, sahte._db_yeniden_dur.bekleyisler
    assert len(denemeler) == 5, f"her bekleyişten sonra (durdurulan hariç) bir deneme beklenirdi: {len(denemeler)}"
    assert sahte.db_acilis_hatalari.get("tedavi"), "açılamayan DB'nin nedeni silindi (dbReady yanlışlıkla true olur)"
