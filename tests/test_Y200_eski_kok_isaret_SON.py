# -*- coding: utf-8 -*-
"""22-SON A2a · Y200 bağımsız sonda — GERÇEK `backend_service.main()` alt süreçte (dinleyici YOK: `_build_server` casusu + TestClient),
sahte YALNIZ en alt katta (kaynağın `open`'ı / işaretin `os.replace`'i). Ölçülen durumlar (mevcut Y200 kapısının kolları DIŞINDA):

  * işaret yazımı YARIDA (güç kesintisi = `os._exit` işaretin `os.replace`'inde): sonraki açılış veriyi kaybetmez, işaret geçerli yazılır;
  * çok kök (Y182): iki eski kök — ikincisi hedefte DB varken ATLANIR (birleştirilmez), kaynak bayt aynı, işaret iki ayrı özet tutar;
  * 1.9.50 / ebeveyn hatasıyla BOŞ DB kurulmuş saha (kilitli kaynak → boş `patients.db`): ilk açılışta işaret yazılırken FARKLI kopya
    uyarısı günlükte mi ve belgelenen kurtarma (boş DB + işaret kaldır, yeniden başlat) eski kaydı getiriyor mu. 1.9.50'de yalnız boş DB'yi
    kaldırmanın yettiği (işaret yoktu) ebeveyn worktree'siyle ölçüldü (`DUZELTME-SON-INCELEME.md` §3); burada durum uçla kurulur.

`SON_KOD` ortamı = ürün kökü (varsayılan bu depo).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

import pytest
from betik_alt_sureci import kostur, yalitik_ortam

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="göç yalnız Windows'ta koşar (path_utils)")

TESTLER = Path(__file__).resolve().parent
KOK = Path(os.environ.get("SON_KOD") or TESTLER.parent)
ISARET = ".eski_kok_gocu_tamam"

_SURUCU = r"""
import sys
sys.path.insert(0, {testler!r})
import alt_surec_ag_bekcisi as _ag
sys.path.remove({testler!r})
import builtins, json, logging, os, time
sys.path[:0] = [{kok!r}, {kok!r} + r"\apps\backend"]
KIP, KILITLI, KESINTI, ADLAR = {kip!r}, {kilitli!r}, {kesinti!r}, {adlar!r}
sonuc = {{"kip": KIP}}
GUNLUK = []
import utils.path_utils as _pu

class _Topla(logging.Handler):
    def emit(self, r):
        m = r.getMessage()
        if "GÖÇ" in m:
            GUNLUK.append(r.levelname + " " + m[:700])
logging.getLogger("utils.path_utils").addHandler(_Topla())
if KILITLI:
    _kaynak = os.path.normcase(os.path.join(os.environ["APPDATA"], "PEMF_GUI", "patients.db"))
    _o_open = builtins.open
    def _open(dosya, *a, **k):
        if isinstance(dosya, (str, os.PathLike)) and os.path.normcase(os.path.abspath(str(dosya))) == _kaynak:
            raise PermissionError(13, "sahte: paylasim ihlali", str(dosya))
        return _o_open(dosya, *a, **k)
    builtins.open = _open
if KESINTI:
    _o_replace = os.replace
    def _replace(src, dst, *a, **k):
        if str(dst).endswith(".eski_kok_gocu_tamam"):
            sys.stdout.write("KESINTI " + str(dst) + "\n"); sys.stdout.flush()
            os._exit(7)  # güç kesintisi: geçici dosya yazıldı, yerleştirilmedi
        return _o_replace(src, dst, *a, **k)
    os.replace = _replace

if KIP == "eski":
    from database.patient_database import get_patient_database
    from utils.path_utils import get_app_data_directory
    app = get_app_data_directory()
    pdb = get_patient_database()
    for ad in ADLAR:
        pdb.add_patient({{"name": ad, "species": "kedi"}})
    with pdb._get_connection() as cn:
        cn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    c = getattr(pdb._local, "conn", None)
    if c is not None:
        c.close()
    sonuc["kok"] = str(app)
else:
    import headless_core as _hc
    _hc.HeadlessCore.DB_YENIDEN_DENEME_ARALIKLARI_SN = (0.1, 0.2, 0.3)
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
            r = c.get("/api/health")
            g = r.json() if r.status_code == 200 else {{}}
            sonuc["saglik"] = {{"kod": r.status_code, "dbReady": g.get("dbReady"), "dbSebep": g.get("dbSebep")}}
            sonuc["estop"] = c.post("/api/hardware/emergency_stop").status_code
            sonuc["stop"] = c.post("/api/session/stop", json={{}}).status_code
            try:
                from database.patient_database import get_patient_database
                sonuc["hastalar"] = sorted(str(h.get("name")) for h in get_patient_database().get_all_patients())
            except Exception as e:
                sonuc["hastalar"] = "HATA " + type(e).__name__
            sonuc["hedef"] = sorted(os.listdir(HEDEF))

    bs._build_server = lambda app, args: _Casus()
    try:
        sonuc["rc"] = bs.main(["--host", "127.0.0.1", "--port", "51994", "--no-headless-services"])
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


def _sha(d: Path) -> dict:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(d.iterdir()) if p.is_file()}


def _kos(
    tmp: Path,
    ad: str,
    kip: str,
    ev: str,
    makine: str | None,
    *,
    kod: Path = KOK,
    kilitli=False,
    kesinti=False,
    adlar=(),
    bekle_sonuc=True,
) -> dict:
    env = yalitik_ortam(tmp / ev)
    env.update(
        {
            "PEMF_DEVICE_IDENTITY_DIR": str(tmp / "kimlik"),
            "PEMF_CLOUD_PROVISION_PATH": str(tmp / "yok" / "p.json"),
            "PEMF_CLOUD_PATIENT_SYNC": "0",
            "SUPABASE_URL": "http://127.0.0.1:9",
            "PEMF_LOG_DIR": str(tmp / f"log_{ad}"),
            "PEMF_ESP_ENABLED": "0",
            "PEMF_FW_AUTO_UPDATE": "0",
            "PEMF_HOTSPOT": "0",
            "PEMF_AI_WARMUP": "0",
            "PEMF_ENABLE_TUNNEL": "0",
            "PEMF_ENCRYPT_AT_REST": "0",
        }
    )
    if makine:
        env["PEMF_DATA_DIR"] = str(tmp / makine)
    betik = tmp / f"surucu_{ad}.py"
    betik.write_text(
        _SURUCU.format(
            testler=str(TESTLER), kok=str(kod), kip=kip, kilitli=kilitli, kesinti=kesinti, adlar=list(adlar)
        ),
        encoding="utf-8",
    )
    p = kostur([str(betik)], cwd=tmp, env=env, sure=420)
    satir = [s for s in p.stdout.splitlines() if s.startswith("SONUC ")]
    if not bekle_sonuc:
        return {"rc": p.returncode, "stdout": p.stdout[-400:], "stderr": p.stderr[-800:]}
    assert p.returncode == 0 and satir, f"{ad} çocuğu düştü rc={p.returncode}: {p.stderr[-1500:]}"
    s = json.loads(satir[-1][len("SONUC ") :])
    assert "kacan" not in s and s["ag"] == [], f"{ad}: {s}"
    return s


def _isaret(hedef: Path) -> dict:
    return json.loads((hedef / ISARET).read_text(encoding="utf-8"))


def test_SON_Y200_isaret_yazimi_YARIDA_kesilirse_veri_kaybolmaz_sonraki_acilis_isareti_gecerli_yazar(tmp_path):
    eski = tmp_path / "ev" / "appdata" / "PEMF_GUI"
    hedef = tmp_path / "makine" / "PEMF_GUI"
    _kos(tmp_path, "eski", "eski", "ev", None, adlar=("A0", "A1"))
    once = _sha(eski)
    k = _kos(tmp_path, "kesinti", "main", "ev", "makine", kesinti=True, bekle_sonuc=False)
    print("OLCUM kesinti", k)
    assert k["rc"] == 7 and "KESINTI" in k["stdout"], f"kesinti aparatı tetiklenmedi (işaret yazımına varılmadı): {k}"
    assert not (hedef / ISARET).exists() and (hedef / (ISARET + ".tmp")).exists(), sorted(os.listdir(hedef))
    a2 = _kos(tmp_path, "sonra", "main", "ev", "makine")
    print("OLCUM sonra", {x: a2.get(x) for x in ("saglik", "hastalar", "hedef")})
    assert a2["saglik"]["dbReady"] is True and a2["hastalar"] == ["A0", "A1"], a2
    assert ISARET in a2["hedef"] and ISARET + ".tmp" not in a2["hedef"], a2["hedef"]
    m = _isaret(hedef)
    assert m.get("surum") == 1 and len(m["kaynaklar"]) == 1, m
    assert a2["estop"] == 200 and a2["stop"] == 200
    assert _sha(eski) == once, "KAYNAK değişti"


def test_SON_Y200_cok_kok_Y182_ikinci_kok_hedefte_DB_varken_ATLANIR_kaynak_ayni_isaret_iki_ozet(tmp_path):
    hedef = tmp_path / "makine" / "PEMF_GUI"
    _kos(tmp_path, "eskiA", "eski", "evA", None, adlar=("A0",))
    _kos(tmp_path, "eskiB", "eski", "evB", None, adlar=("B0", "B1"))
    onceB = _sha(tmp_path / "evB" / "appdata" / "PEMF_GUI")
    a = _kos(tmp_path, "acA", "main", "evA", "makine")
    assert a["hastalar"] == ["A0"] and ISARET in a["hedef"], a
    b = _kos(tmp_path, "acB", "main", "evB", "makine")
    print("OLCUM acB", {x: b.get(x) for x in ("saglik", "hastalar", "hedef", "gunluk")})
    assert b["saglik"]["dbReady"] is True and b["hastalar"] == ["A0"], b
    assert _sha(tmp_path / "evB" / "appdata" / "PEMF_GUI") == onceB, "ikinci kökün KAYNAĞI değişti"
    m = _isaret(hedef)
    assert len(m["kaynaklar"]) == 2, m
    metin = (hedef / ISARET).read_text(encoding="utf-8")
    for yasak in ("evA", "evB", "appdata", "PEMF_GUI", os.environ.get("USERNAME", "\x00")):
        assert yasak.lower() not in metin.lower(), f"işaret yol / ad sızdırıyor: {yasak}"


def _bos_db_saha(tmp_path: Path) -> Path:
    """1.9.50 / ebeveyn göç hatasının bıraktığı saha (hedefte BOŞ `patients.db`, işaret YOK, anahtarlar ve dolu kopya eski kökte) — eski
    sürüm KOŞTURULMADAN: (1) uç kilitli kaynakla açılır → anahtarlar taşınır, DB atlanır, Y200 gereği boş DB KURULMAZ; (2) uç eski kökü
    olmayan başka bir kullanıcı eviyle açılır → göç kaynağı yok, makine kökünde (eski kökün anahtarlarıyla) boş DB kurulur, işaret yazılmaz.
    (A2a sondası durumu ebeveyn worktree'siyle üretiyordu; tam süitte o yok → kapı hep ATLANIRDI — 22-SON orkestratör.)"""
    hedef = tmp_path / "makine" / "PEMF_GUI"
    _kos(tmp_path, "eski", "eski", "ev", None, adlar=("S0", "S1"))
    k = _kos(tmp_path, "kilitli", "main", "ev", "makine", kilitli=True)
    assert "patients.db" not in k["hedef"] and ISARET not in k["hedef"], (
        f"Y200: kilitli kaynakta boş DB kurulmamalı: {k}"
    )
    b = _kos(tmp_path, "bos_ev", "main", "evbos", "makine")
    print("OLCUM bos_ev", {x: b.get(x) for x in ("saglik", "hastalar", "hedef")})
    assert b["hastalar"] == [] and "patients.db" in b["hedef"] and ISARET not in b["hedef"], (
        f"boş DB sahası kurulamadı: {b}"
    )
    return hedef


def _bos_db_kaldir(hedef: Path) -> None:
    for ek in ("", "-wal", "-shm"):
        p = hedef / ("patients.db" + ek)
        if p.exists():
            p.unlink()


def test_SON_A21_bos_DB_sahada_ucun_ilk_acilisi_isareti_yazarken_FARKLI_kaynak_UYARISI_ve_belgelenen_kurtarma_calisir(
    tmp_path,
):
    """SON-A2.1: uçta İLK açılış (kilit yok) hedefte DB 'var' (boş) diye kalıcı işareti YAZAR (Y200 S-D3I.6 — bilerek); ardından
    'boş DB'yi kaldır + yeniden başlat' eski kaydı GETİRMEZ (işaret eski kökü kapattı). İşaret yazılırken eski kökte hedeftekinden
    FARKLI bir kopya kaldığı ve kurtarmanın İŞARETİ de kaldırmak olduğu günlükte YAZILMALI; belgelenen kurtarma eski kaydı getirmeli."""
    hedef = _bos_db_saha(tmp_path)
    u = _kos(tmp_path, "ilk", "main", "ev", "makine")
    print("OLCUM uc ilk", {x: u.get(x) for x in ("saglik", "hastalar", "hedef", "gunluk")})
    assert ISARET in u["hedef"] and u["hastalar"] == [], u
    assert u["estop"] == 200 and u["stop"] == 200
    _bos_db_kaldir(hedef)
    k = _kos(tmp_path, "isaretli", "main", "ev", "makine")
    print("OLCUM uc isaret varken kurtarma", k.get("hastalar"))
    assert k["hastalar"] == [], "S-D3I.6: işaret varken eski kökün kopyası GELMEMELİ"
    uyari = [g for g in u["gunluk"] if g.startswith("WARNING") and "FARKLI" in g and ISARET in g and "patients.db" in g]
    assert uyari, (
        "SON-A2.1: uç ilk açılışta kalıcı işareti yazdı ama eski kökte hedeftekinden FARKLI kopya kaldığını ve kurtarmanın işareti de "
        f"kaldırmak olduğunu GÜNLÜĞE YAZMADI (teknik destek 1.9.50 yolunu dener, boş liste kalır). gunluk={u['gunluk']}"
    )
    _bos_db_kaldir(hedef)
    (hedef / ISARET).unlink()
    r = _kos(tmp_path, "kurtarma", "main", "ev", "makine")
    print("OLCUM uc belgelenen kurtarma", {x: r.get(x) for x in ("saglik", "hastalar", "hedef")})
    assert r["hastalar"] == ["S0", "S1"] and r["estop"] == 200 and r["stop"] == 200, r
    assert ISARET in r["hedef"], "kurtarma göçü atlamasız bitti — işaret yeniden yazılmalı"
