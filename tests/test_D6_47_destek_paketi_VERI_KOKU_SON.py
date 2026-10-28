# -*- coding: utf-8 -*-
"""22-SON A2a · SON-A2.3 · D6.47 `PEMF_Backend.exe --destek-paketi` SAHADA, RUNBOOK'un söylediği gibi (kullanıcının PowerShell'i: launcher'ın
ÇOCUĞUNA verdiği `PEMF_DATA_DIR` / `PEMF_ENCRYPT_AT_REST` YOK; aynı Windows oturumu) çalıştırılınca:

  * RUNBOOK satırı AYNEN (`--destek-paketi`, hedef dışında bayrak yok) — paket saha kökünün (launcher: `%PROGRAMDATA%\\PEMF_System\\PEMF_GUI`)
    günlüğünü İÇERMELİ, hasta adı MASKELİ olmalı, kullanıcı kökünde (`%APPDATA%\\PEMF_GUI`) yeni DB / sır YARATILMAMALI;
  * `--veri-dizini <saha kökü>` (RUNBOOK'un ikinci yolu) — yasak dosya yok, günlük var, hasta adı MASKELİ (RUNBOOK: "kullanıcının oturumunda
    çalıştırın — hasta adlarının maskelenmesi için şifreli DB'yi açabilmeli");
  * iki paket üretimi sonrası saha DB'si hâlâ ŞİFRELİ ve veri OKUNUR (launcher çocuğu ortamıyla).

Sahte EN ALT katta: yalnız ortam (yalıtık ev — sahte APPDATA / PROGRAMDATA). GERÇEK `backend_service.main()` alt süreçte, ağ bekçisi önde.
Saha kökü, GERÇEK backend'in launcher çocuğu ortamıyla (`PEMF_DATA_DIR=%PROGRAMDATA%\\PEMF_System`, at-rest AÇIK) bir kez açılıp hasta + seans +
günlük üretmesiyle kurulur.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import zipfile
from pathlib import Path

import pytest
from betik_alt_sureci import kostur, yalitik_ortam

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="saha yolu Windows")

TESTLER = Path(__file__).resolve().parent
KOK = TESTLER.parent
HASTA = "Zeytinyagli SonA2Hasta"

_SURUCU = r"""
import sys
sys.path.insert(0, {testler!r})
import alt_surec_ag_bekcisi as _ag
sys.path.remove({testler!r})
import json, os
sys.path[:0] = [{kok!r}, {kok!r} + r"\apps\backend"]
KIP, ARGV = {kip!r}, {argv!r}
sonuc = {{"kip": KIP}}
import backend_service as bs
if KIP == "kur":
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

    class _Casus:
        should_exit = False
        force_exit = False

        def run(self):
            import logging
            from database.patient_database import get_patient_database
            from servers import api_server as api
            get_patient_database().add_patient({{"name": {hasta!r}, "species": "kedi"}})
            tdb = api._get_treatment_db()
            sid = tdb.start_session("Manual", target_condition="artrit", operator_name="Dr SonA2", patient_name={hasta!r},
                                    operator_email="dr.sona2@ornek.invalid")
            tdb.end_session(sid, parameters={{"frequency": 50, "duty": 40, "coils": [1]}}, duration_minutes=5)
            logging.getLogger("saha").warning("SAHA-GUNLUK-ISARETI hasta=%s", {hasta!r})
            sonuc["kuruldu"] = True

    bs._build_server = lambda app, args: _Casus()
    sonuc["rc"] = bs.main(["--host", "127.0.0.1", "--port", "51993", "--no-headless-services"])
elif KIP == "veri":
    from utils.path_utils import get_app_data_directory
    from database.patient_database import get_patient_database
    from database.treatment_history_db import get_treatment_db
    sonuc["hastalar"] = sorted(str(h.get("name")) for h in get_patient_database().get_all_patients())
    tdb = get_treatment_db(get_app_data_directory())
    sonuc["atRest"] = getattr(tdb, "at_rest_encrypted", None)
    with tdb._get_connection() as cn:
        sonuc["seanslar"] = cn.execute("SELECT COUNT(*) FROM treatment_sessions").fetchone()[0]
else:
    try:
        sonuc["rc"] = bs.main(ARGV)
    except BaseException as e:
        import traceback
        sonuc["kacan"] = type(e).__name__ + ": " + str(e)[:300]
        sonuc["iz"] = traceback.format_exc()[-1200:]
sonuc["ag"] = _ag.ENGELLENEN
print("SONUC " + json.dumps(sonuc, ensure_ascii=False, default=str))
sys.stdout.flush()
os._exit(0)
"""


def _makine_koku(tmp: Path) -> Path:
    """launcher `backend_env`: `PEMF_DATA_DIR = %PROGRAMDATA%\\PEMF_System` (yalıtık evde `ev/programdata`)."""
    return tmp / "ev" / "programdata" / "PEMF_System"


def _kos(tmp: Path, ad: str, kip: str, argv: list, launcher_cocugu: bool) -> dict:
    env = yalitik_ortam(tmp / "ev")
    env.update(
        {
            "PEMF_DEVICE_IDENTITY_DIR": str(tmp / "kimlik"),
            "PEMF_CLOUD_PROVISION_PATH": str(tmp / "yok" / "p.json"),
            "PEMF_CLOUD_PATIENT_SYNC": "0",
            "SUPABASE_URL": "http://127.0.0.1:9",
            "PEMF_ESP_ENABLED": "0",
            "PEMF_FW_AUTO_UPDATE": "0",
            "PEMF_HOTSPOT": "0",
            "PEMF_AI_WARMUP": "0",
            "PEMF_ENABLE_TUNNEL": "0",
        }
    )
    if launcher_cocugu:  # launcher'ın backend_env'i (saha): makine kökü + at-rest AÇIK
        env.update({"PEMF_DATA_DIR": str(_makine_koku(tmp)), "PEMF_ENCRYPT_AT_REST": "1"})
    betik = tmp / f"surucu_{ad}.py"
    betik.write_text(
        _SURUCU.format(testler=str(TESTLER), kok=str(KOK), kip=kip, argv=argv, hasta=HASTA), encoding="utf-8"
    )
    p = kostur([str(betik)], cwd=tmp, env=env, sure=420)
    satir = [s for s in p.stdout.splitlines() if s.startswith("SONUC ")]
    assert p.returncode == 0 and satir, f"{ad} çocuğu düştü rc={p.returncode}: {p.stderr[-1500:]}"
    s = json.loads(satir[-1][len("SONUC ") :])
    s["stdout"] = p.stdout[-1500:]
    assert "kacan" not in s and s["ag"] == [], f"{ad}: {s}"
    return s


def _agac(d: Path) -> dict:
    if not d.exists():
        return {}
    return {
        str(p.relative_to(d)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()[:12]
        for p in sorted(d.rglob("*"))
        if p.is_file()
    }


def _paket(zip_yolu: Path) -> dict:
    with zipfile.ZipFile(zip_yolu) as z:
        return {n: z.read(n).decode("utf-8", "replace") for n in z.namelist()}


@pytest.fixture
def saha(tmp_path):
    k = _kos(tmp_path, "kur", "kur", [], launcher_cocugu=True)
    assert k.get("kuruldu"), k
    makine = _makine_koku(tmp_path) / "PEMF_GUI"
    gunluk = makine / "logs" / "backend_service.log"
    assert gunluk.is_file() and "SAHA-GUNLUK-ISARETI" in gunluk.read_text(encoding="utf-8", errors="replace"), (
        f"saha kökü kurulamadı (günlük): {sorted(_agac(makine))}"
    )
    assert not (tmp_path / "ev" / "appdata" / "PEMF_GUI").exists(), "aparat: kullanıcı kökü saha kurulumunda oluşmamalı"
    return tmp_path, makine


def _yasak(icerik: dict) -> list:
    return [
        n
        for n in icerik
        if n.lower().endswith((".db", ".db-wal", ".db-shm", ".enc"))
        or "secret" in n.lower()
        or "sqlcipher" in n.lower()
        or "kurtarma" in n.lower()
        or "kimlik" in n.lower()
    ]


def test_SON_A23_RUNBOOK_komutu_SAHA_KOKUNUN_gunlugunu_MASKELI_paketler_ve_kullanici_kokunde_DB_YARATMAZ(saha):
    """RUNBOOK satırı AYNEN (yalnız `--destek-paketi` + hedef)."""
    tmp, makine = saha
    kullanici = tmp / "ev" / "appdata" / "PEMF_GUI"
    once_k = _agac(kullanici)
    hedef = tmp / "cikti" / "destek.zip"
    _kos(tmp, "runbook", "paket", ["--destek-paketi", "--cikti", str(hedef)], launcher_cocugu=False)
    icerik = _paket(hedef)
    sonra_k = _agac(kullanici)
    print(
        "OLCUM runbook", {"zip": sorted(icerik), "kullanici_once": sorted(once_k), "kullanici_sonra": sorted(sonra_k)}
    )
    print("OLCUM runbook OZET", icerik.get("OZET.json", "")[:900])
    assert not _yasak(icerik), f"pakette yasak dosya: {_yasak(icerik)}"
    gunlukler = [n for n in icerik if n.startswith("logs/")]
    assert any("SAHA-GUNLUK-ISARETI" in icerik[n] for n in gunlukler), (
        f"SON-A2.3: RUNBOOK komutuyla üretilen pakette SAHA KÖKÜNÜN günlüğü YOK (yanlış kök — %APPDATA%\\PEMF_GUI): logs={gunlukler}"
    )
    yeni = sorted(set(sonra_k) - set(once_k))
    assert not [y for y in yeni if y.endswith((".db", ".json"))], (
        f"SON-A2.3: RUNBOOK komutu KULLANICI kökünde yeni veritabanı / sır YARATTI (saha kökü değil): {yeni}"
    )
    assert not any(HASTA in v for v in icerik.values()), "SON-A2.3: hasta adı pakette MASKELENMEDEN duruyor"


def test_SON_A23_veri_dizini_ile_paket_YASAK_dosya_icermez_hasta_adi_MASKELI(saha):
    tmp, makine = saha
    hedef = tmp / "cikti" / "destek2.zip"
    _kos(
        tmp,
        "veri_dizini",
        "paket",
        ["--destek-paketi", "--cikti", str(hedef), "--veri-dizini", str(makine)],
        launcher_cocugu=False,
    )
    icerik = _paket(hedef)
    print("OLCUM veri_dizini", {"zip": sorted(icerik)})
    print("OLCUM veri_dizini OZET", icerik.get("OZET.json", "")[:900])
    assert not _yasak(icerik), f"pakette yasak dosya: {_yasak(icerik)}"
    assert any("SAHA-GUNLUK-ISARETI" in v for n, v in icerik.items() if n.startswith("logs/")), sorted(icerik)
    assert not any(HASTA in v for v in icerik.values()), (
        "SON-A2.3: --veri-dizini ile (aynı Windows oturumu, RUNBOOK'un dediği gibi) hasta adı pakette MASKELENMEDEN duruyor — şifreli DB "
        f"açılamadı (anahtar başka kökte aranıyor): OZET={icerik.get('OZET.json', '')[:400]}"
    )


def _ayrinti(d: Path) -> dict:
    out = {}
    for ad in (
        "pemf_treatment_history.db",
        "pemf_treatment_history.db-wal",
        "patients.db",
        "patients.db-wal",
        "pemf_secrets.json",
    ):
        p = d / ad
        if p.is_file():
            b = p.read_bytes()
            out[ad] = [len(b), hashlib.sha256(b).hexdigest()[:10], b[:16] == b"SQLite format 3\x00"]
    return out


def test_SON_A23_paket_uretimi_sonrasi_saha_DB_SIFRELI_ve_veri_OKUNUR(saha):
    """ÖLÇÜM + koruma: paket üretimi saha DB'sini düz-metne çevirmez, kayıt kaybettirmez (WAL denetim noktası bayt değiştirebilir)."""
    tmp, makine = saha
    a0 = _ayrinti(makine)
    _kos(
        tmp,
        "p1",
        "paket",
        ["--destek-paketi", "--cikti", str(tmp / "c1.zip"), "--veri-dizini", str(makine)],
        launcher_cocugu=False,
    )
    _kos(tmp, "p2", "paket", ["--destek-paketi", "--cikti", str(tmp / "c2.zip")], launcher_cocugu=False)
    a2 = _ayrinti(makine)
    print("OLCUM ayrinti", json.dumps({"once": a0, "sonra": a2}, ensure_ascii=False))
    assert not any(v[2] for k, v in a2.items() if k.endswith(".db")), "paket üretimi şifreli DB'yi DÜZ-METNE çevirdi"
    assert a0.get("pemf_secrets.json") == a2.get("pemf_secrets.json"), "paket üretimi sır dosyasını değiştirdi"
    v = _kos(tmp, "veri_okuma", "veri", [], launcher_cocugu=True)
    print("OLCUM veri_okuma", {x: v.get(x) for x in ("hastalar", "seanslar", "atRest")})
    assert v.get("hastalar") == [HASTA] and v.get("seanslar", 0) >= 1 and v.get("atRest") is True, (
        f"paketten sonra saha verisi OKUNAMIYOR / KAYIP: {v}"
    )
