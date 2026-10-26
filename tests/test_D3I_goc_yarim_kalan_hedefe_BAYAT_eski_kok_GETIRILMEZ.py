# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D3I-A2.6 (D3.37 · Y10 × at-rest göçü) — HEDEFTE YARIM KALAN GÖÇ / KARANTİNA ARTIĞI VARKEN ESKİ KÖKÜN BAYAT DB'si GETİRİLMEZ.

ÖLÇÜLEN KUSUR (önceden var; Y10 eski kökü kalıcı kıldığı için her açılışta hazır): `backend_service.main` sırası
`get_app_data_directory()` (→ `_kullanicidan_makineye_gocur`: hedefte `db` YOKSA eski kökten kopyala) → `initialize_database()`
(→ `_yarim_goc_toparla`: `db` YOK + `.plain.bak` VARSA geri koy) → DB sınıfları. At-rest göçü `db → .plain.bak` ile `.enc.tmp → db`
ARASINDA kesilirse (güç / süreç öldürme / kalıcı kilit + geri alma düşmesi) hedefte `db` yoktur, GÜNCEL veri `.plain.bak`tadır; sonraki
açılışta eski kök göçü eski kökün AYLARCA ÖNCEKİ kopyasını getirip "SHA-256 doğrulandı" der, toparlama `db` VAR gördüğü için `.plain.bak`ı
geri KOYMAZ → klinik BAYAT veriyi görür, yeni kayıtlar bayat DB'ye yazılır (güncel veri `.plain.bak.<zaman>`da, elle kurtarılır).

SÖZLEŞME: hedefte bu DB'nin göç / karantina artığı (`<ad>.plain.bak[.<zaman>]` · `<ad>.enc.tmp` · `<ad>.acilamadi-*`) varsa hedef
KULLANILMIŞ bir köktür → eski kökten KOPYALANMAZ (WARNING "VERİ GÖÇÜ ATLANDI"); toparlama güncel veriyi geri koyar. `-wal` / `-shm`
artık SAYILMAZ: D3.37'nin yarım kalan kendi WAL kopyası sonraki açılışta DB'yle eşlenir. Eski kök her durumda DEĞİŞMEZ.
Uçtan uca kol GERÇEK `backend_service.main()` (dinleyici YOK: `_build_server` casusu; ağa çıkan yan alt sistemler kayıtçı) ve GERÇEK
kesinti (`.enc.tmp → <ad>` taşımasında `os._exit`) ile koşar; süreç içi kollar artık adlarını tek tek ölçer.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
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
import json, os
sys.path[:0] = [{kok!r}, {backend!r}]
KIP, OLDUR = {kip!r}, {oldur!r}
sonuc = {{"kip": KIP}}
SIRA = []
import utils.path_utils as _pu
import database.sqlcipher_util as _su
_o_kopya, _o_toparla, _o_tasi = getattr(_pu, "_kopyala_dogrula", None), _su._yarim_goc_toparla, _su._tasi_yeniden_dene
def _kopya(kaynak, varis):  # taban (5df8406d) ölçümünde `_kopyala_dogrula` yok — orada sıra yalnız toparlamayı gösterir
    SIRA.append("kopya:" + os.path.basename(str(varis)))
    return _o_kopya(kaynak, varis)
def _toparla(db, logger=None):
    r = _o_toparla(db, logger)
    SIRA.append("toparla:" + os.path.basename(str(db)) + "=" + str(r))
    return r
def _tasi(*a, **k):
    if OLDUR and str(a[0] if a else k.get("kaynak", "")).endswith(OLDUR + ".enc.tmp"):
        sys.stdout.flush()
        os._exit(9)  # GERÇEK kesinti: `db -> .plain.bak` yapıldı, `.enc.tmp -> db` YAPILMADI
    return _o_tasi(*a, **k)
_su._yarim_goc_toparla, _su._tasi_yeniden_dene = _toparla, _tasi
if _o_kopya is not None:
    _pu._kopyala_dogrula = _kopya


def _oku():
    from database.patient_database import get_patient_database
    from database.treatment_history_db import TreatmentHistoryDB
    from utils.path_utils import get_app_data_directory
    sonuc["hastalar"] = sorted(str(h.get("name")) for h in get_patient_database().get_all_patients())
    if KIP == "main":
        from servers import api_server as api
        tdb = api._get_treatment_db()
    else:
        tdb = TreatmentHistoryDB(get_app_data_directory())
    sonuc["seanslar"] = sorted(str(s.get("patient_name")) for s in tdb.get_session_history(limit=100))
    return tdb


if KIP in ("eski", "yeni", "kesinti"):
    from database.patient_database import get_patient_database
    from database.treatment_history_db import TreatmentHistoryDB
    from utils.path_utils import get_app_data_directory
    app = get_app_data_directory()
    pdb = get_patient_database()
    tdb = TreatmentHistoryDB(app)
    if KIP != "kesinti":
        n_h, n_s = (3, 2) if KIP == "eski" else (2, 1)
        on = "Eski" if KIP == "eski" else "Yeni"
        for i in range(n_h):
            pdb.add_patient({{"name": "%sHasta%d" % (on, i), "species": "kedi"}})
        for i in range(n_s):
            sid = tdb.start_session("Manual", patient_name="%sSeans%d" % (on, i))
            tdb.end_session(sid)
        with pdb._get_connection() as cn:
            cn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        _oku()
        tdb.close_connections()
    sonuc["kok"] = str(app)
else:
    import backend_service as bs
    yan = []
    bs._start_cloud_sync = lambda logger: yan.append("cloud_sync")
    bs._start_update_checker_safe = lambda logger: yan.append("update_checker")
    bs._donanim_guncellemesi_kur = lambda core, logger, event_bus=None: yan.append("donanim")
    bs._start_db_maintenance = lambda core, logger: yan.append("db_bakim")
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
            SIRA.append("server.run")
            _oku()

    bs._build_server = lambda app, args: _Casus()
    try:
        sonuc["rc"] = bs.main(["--host", "127.0.0.1", "--port", "51998", "--no-headless-services"])
    except BaseException as e:
        import traceback
        sonuc["kacan"] = type(e).__name__ + ": " + str(e)[:300]
        sonuc["iz"] = traceback.format_exc()[-1500:]
    sonuc["yan"] = yan
sonuc["sira"] = SIRA
sonuc["ag"] = _ag.ENGELLENEN
print("SONUC " + json.dumps(sonuc, ensure_ascii=False, default=str))
sys.stdout.flush()
os._exit(0)
"""


def _kos(tmp_path: Path, kip: str, at_rest: str, makine: bool, oldur: str = "") -> tuple[int, dict | None, str]:
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
    kod = _SURUCU.format(testler=str(TESTLER), kok=str(KOK), backend=str(BACKEND), kip=kip, oldur=oldur)
    betik = tmp_path / f"surucu_{kip}.py"
    betik.write_text(kod, encoding="utf-8")
    p = kostur([str(betik)], cwd=tmp_path, env=env, sure=420)
    satir = [s for s in p.stdout.splitlines() if s.startswith("SONUC ")]
    return p.returncode, (json.loads(satir[-1][len("SONUC ") :]) if satir else None), p.stderr[-1500:]


def _goruntu(d: Path) -> dict:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in d.iterdir() if p.is_file()}


@pytest.mark.parametrize("kesilen", ["patients.db", "pemf_treatment_history.db"])
def test_KRITIK_D3I_A2_6_yarim_at_rest_gocunden_sonra_GERCEK_acilis_GUNCEL_veriyi_gosterir_ESKI_KOK_getirilmez(
    tmp_path, kesilen
):
    """MUTASYON: artık denetimi yok (= HEAD) → KIRMIZI (eski kökün bayat kopyası gelir, toparlama `db` VAR görür)."""
    eski = tmp_path / "ev" / "appdata" / "PEMF_GUI"
    hedef = tmp_path / "makine" / "PEMF_GUI"
    rc, e, err = _kos(tmp_path, "eski", "0", makine=False)
    assert rc == 0 and e and e["ag"] == [] and Path(e["kok"]) == eski, err
    rc, y, err = _kos(tmp_path, "yeni", "0", makine=True)
    assert rc == 0 and y and y["ag"] == [] and Path(y["kok"]) == hedef, err
    guncel_h = sorted([f"EskiHasta{i}" for i in range(3)] + [f"YeniHasta{i}" for i in range(2)])
    guncel_s = sorted([f"EskiSeans{i}" for i in range(2)] + ["YeniSeans0"])
    assert y["hastalar"] == guncel_h and y["seanslar"] == guncel_s, f"senaryo kurulamadı (yeni kök): {y}"
    once = _goruntu(eski)

    rc, _, err = _kos(tmp_path, "kesinti", "1", makine=True, oldur=kesilen)
    assert rc == 9, f"kesinti kurulamadı (rc={rc}): {err}"
    assert not (hedef / kesilen).exists() and (hedef / (kesilen + ".plain.bak")).exists(), sorted(
        p.name for p in hedef.iterdir()
    )

    rc, s, err = _kos(tmp_path, "main", "1", makine=True)
    assert rc == 0 and s and s.get("run") and "kacan" not in s, f"main() server.run'a ulaşmadı: {s} {err}"
    assert s["ag"] == [], s["ag"]
    sira = s["sira"]
    assert (s["hastalar"], s["seanslar"]) == (guncel_h, guncel_s), (
        f"klinik GÜNCEL veriyi görmüyor: hastalar {s['hastalar']} · seanslar {s['seanslar']} (açılış sırası: {sira})"
    )
    assert "kopya:" + kesilen not in sira, f"eski kökün BAYAT {kesilen} kopyası hedefe getirildi (sıra: {sira})"
    # Açılış sırası GERÇEK main()'de: eski kök göçü → toparlama (güncel veri geri konur) → DB sınıfları → server.run
    assert "toparla:" + kesilen + "=True" in sira and sira.index("toparla:" + kesilen + "=True") < sira.index(
        "server.run"
    ), sira
    assert _goruntu(eski) == once, "eski kök değişti / silindi (Y10)"
    assert not list(hedef.glob(kesilen + ".plain.bak*")), "toparlanan göçün düz-metin kopyası kaldı"


# ─────────────────────────── süreç içi: artık adları (sahte eski / yeni kök, saf dosya) ───────────────────────────


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
    monkeypatch.setattr(pu, "_GOC_ENGELI", {}, raising=False)
    for ad in ("patients.db", "pemf_treatment_history.db"):
        (eski / ad).write_bytes(DUZ_DB)
    return pu, eski, yeni


@pytest.mark.parametrize(
    "artik",
    [".plain.bak", ".plain.bak.20261026_120000", ".enc.tmp", ".acilamadi-20261026_120000"],
    ids=["yarim_goc_plain_bak", "kenara_alinmis_plain_bak", "enc_tmp", "karantina"],
)
def test_KRITIK_D3I_A2_6_hedefte_goc_ARTIGI_varken_eski_kok_KOPYALANMAZ(kokler, caplog, artik):
    pu, eski, yeni = kokler
    (yeni / ("pemf_treatment_history.db" + artik)).write_bytes(b"GUNCEL-VERI")
    once = _goruntu(eski)
    with caplog.at_level(logging.WARNING):
        pu._kullanicidan_makineye_gocur(yeni)
    assert not (yeni / "pemf_treatment_history.db").exists(), (
        f"hedefte '{artik}' artığı varken eski kökün BAYAT DB'si getirildi"
    )
    assert (yeni / ("pemf_treatment_history.db" + artik)).read_bytes() == b"GUNCEL-VERI", "artık değişti"
    assert (yeni / "patients.db").read_bytes() == DUZ_DB, (
        "ÖTEKİ DB'nin göçü de durdu (artık yalnız kendi DB'sini bağlar)"
    )
    assert _goruntu(eski) == once, "eski kök değişti"
    assert any(
        "VERİ GÖÇÜ ATLANDI" in r.getMessage() and "pemf_treatment_history.db" in r.getMessage() for r in caplog.records
    ), "atlama günlüğe yazılmadı"


def test_KARSIT_D3I_A2_6_yalniz_WAL_kalintisi_ARTIK_SAYILMAZ_D337_esleme_kolu(kokler):
    """D3.37: WAL taşındı, DB yerleşmedi, kopyalanan WAL geri alınamadı (göç engeli) → sonraki açılış DB'yi kopyalayıp o WAL'la
    eşlemeli. `-wal` artık sayılsaydı DB hiç gelmez, yetim WAL yeni / boş DB'ye uygulanırdı."""
    pu, eski, yeni = kokler
    (eski / "patients.db-wal").write_bytes(b"ESKI-WAL")
    shutil.copyfile(eski / "patients.db-wal", yeni / "patients.db-wal")
    pu._kullanicidan_makineye_gocur(yeni)
    assert (yeni / "patients.db").read_bytes() == DUZ_DB, "yalnız WAL kalıntısı varken DB göçü durdu"
