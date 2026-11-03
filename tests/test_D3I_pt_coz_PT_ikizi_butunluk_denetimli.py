# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D3I-E.1 (D3.48 · Y18) — `pt_coz` PT İKİZLERİNİ (XAI) ve CPN yara-kapanma modelini BÜTÜNLÜK SÜZGECİNDEN geçirir.

ÖLÇÜLEN KUSUR: `ai_hub/xai_utils/pt_yolu.pt_coz`, `PEMF_AI_MODELS_DIR` altında aday VARSA özetlemeden döndürüyordu. Launcher bu değişkeni
HER ZAMAN verir (`install::backend_env_with` → `<kurulum kökü>\\ai_models`, kurulum kökü `%LOCALAPPDATA%\\PEMF Vet Client`) → sahada
XAI PT ikizleri (kidney_ct / histopath / cat_thermal / cat_sound / feline) ve dilek_hoca CPN (`/api/ai/vision/scratch`; açılış ısıtması
`PEMF_SCRATCH_WARMUP` varsayılan 1; yükleme `weights_only=False`) manifestle TUTMAYAN (başka sürüm / kurcalanmış) dosyayı SESSİZCE yüklüyordu.
D3.48'in "başka sürüm yüklenmez, başka köke düşülmez, 503 + açık uyarı" sözleşmesi bu çözücüde yoktu.

SÖZLEŞME: çözücü (`utils.model_downloader`) VARKEN `pt_coz` onu kullanır — `PEMF_AI_MODELS_DIR` 1. köktür ve aday aynı süzgeçten geçer:
özet tutmazsa `ModelButunlukHatasi` (ana model yolu → `_ai_fail` 503 + `ai.hata.modelButunluk`; XAI ikincil → açıklama üretilmez, analiz
sürer), kesik kopyada sonraki kök. Çözücü YOKSA (ai_service imajı — sahada yok) eski davranış: yalnız mount.
Uçtan uca kollar GERÇEK ağırlıkla (PEMF_AI_MODELS_DIR ya da ürün kökleri; yoksa atlanır, PEMF_GOLDEN_REQUIRED=1'de düşer): kidney_ct'nin PT ikizi yerine BAŞKA
modelin (feline yolov8s.pt) yüklenebilir ağırlığı — HEAD açıklamayı yanlış sürümle SESSİZCE üretiyordu.
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

KOK = Path(__file__).resolve().parents[1]
TESTLER = Path(__file__).resolve().parent
BACKEND = KOK / "apps" / "backend"
TERMAL = "ai_hub/cat_thermal/GhostNetV2.pt"
CPN = "ai_hub/inference_paper_dilek_hoca/ginoro_CpnResNeXt101UNet-fbe875f1a3e5ce2c.pt"
CT_ONNX = "ai_hub/inference_human_kidney_ct/yolov8s.onnx"
CT_PT = "ai_hub/inference_human_kidney_ct/yolov8s.pt"
RETIC_PT = "ai_hub/feline_reticulocytes/yolov8s.pt"


@pytest.fixture
def kok(tmp_path, monkeypatch):
    from utils import model_downloader as md

    monkeypatch.setattr(md, "_manifest_onbellegi", {})
    monkeypatch.setattr(md, "_ozet_onbellegi", {})
    monkeypatch.setenv("PEMF_AI_MODELS_DIR", str(tmp_path / "modeller"))
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "pd"))  # 2. kök boş (sahte ev kökü sızmasın)
    # Makinenin GERÇEK kökleri (kalıcı AppData `.ai_models`, `release_assets/ai_models`, paket) dışarıda: yayın makinesinde (guii, Y30)
    # `release_assets/ai_models`te gerçek GhostNetV2.pt durur → kesik adaydan sonraki kök onu bulur, KARŞIT kol yanlış nedenle
    # kırmızı olurdu (ölçüldü 2026-11-03; temiz klonda o kökler boş). Ürünün kök SIRASI korunur, yalnız tmp altındakiler kalır.
    tum_kokler = md._candidate_model_roots
    monkeypatch.setattr(
        md, "_candidate_model_roots", lambda: [r for r in tum_kokler() if Path(r).is_relative_to(tmp_path)]
    )
    return tmp_path / "modeller", md


def _yaz(kok: Path, rel: str, veri: bytes) -> Path:
    p = kok / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(veri)
    return p


@pytest.mark.parametrize("rel", [TERMAL, CPN], ids=["xai_ikizi_termal", "cpn_yara_kapanma"])
def test_KRITIK_D3I_E1_manifestle_TUTMAYAN_aday_YUKLENMEZ_baska_koke_DUSULMEZ(kok, rel):
    """MUTASYON: aday özetlenmeden döner (= HEAD) → KIRMIZI."""
    from ai_hub.xai_utils.pt_yolu import pt_coz

    k, md = kok
    _yaz(k, rel, b"\x80\x02" + b"K" * 300_000)  # asgari boyut ÜSTÜ, manifest özeti TUTMAZ (başka sürüm / kurcalanmış)
    with pytest.raises(md.ModelButunlukHatasi) as ex:
        pt_coz(rel)
    assert Path(ex.value.dosya).name == Path(rel).name and ex.value.sebep == "ozet"


def test_KARSIT_D3I_E1_KESIK_aday_dondurulmez_sonraki_koke_bakilir(kok):
    """Kesik (asgari boyut altı) kopya D3.48'deki gibi yarım kurulum sayılır: döndürülmez; başka kökte yoksa açık FileNotFoundError."""
    from ai_hub.xai_utils.pt_yolu import pt_coz

    k, _ = kok
    _yaz(k, TERMAL, b"\x80\x02kesik")
    with pytest.raises(FileNotFoundError):
        pt_coz(TERMAL)


def test_KARSIT_D3I_E1_DOGRULANAN_aday_dondurulur(kok):
    """Bütünlüğü doğrulanan aday (`.sha256` yan dosyası) aynen döner — süzgeç her şeyi reddederek geçemez."""
    from ai_hub.xai_utils.pt_yolu import pt_coz

    k, _ = kok
    rel = "ai_hub/d3i_e1_deneme/ikiz.pt"
    p = _yaz(k, rel, os.urandom(200_000))
    (p.parent / "ikiz.pt.sha256").write_text(hashlib.sha256(p.read_bytes()).hexdigest(), encoding="utf-8")
    assert Path(pt_coz(rel)) == p


def test_KARSIT_D3I_E1_cozucusuz_IMAJ_profili_yalniz_mount(kok, monkeypatch):
    """ai_service imajı (`utils.model_downloader` YOK — sahada kullanılmaz): eski davranış, mount'taki aday döner.
    MUTASYON: imaj kolu kaldırılır → KIRMIZI (GPU servisinde XAI ölür)."""
    from ai_hub.xai_utils.pt_yolu import pt_coz

    k, _ = kok
    p = _yaz(k, TERMAL, b"\x80\x02" + b"K" * 300_000)
    monkeypatch.setitem(sys.modules, "utils.model_downloader", None)  # import → ImportError
    assert Path(pt_coz(TERMAL)) == p


# ─────────────────────────── uçtan uca (GERÇEK ağırlık, alt süreç, süreç içi TestClient — port YOK) ───────────────────────────

_COCUK = r"""
import sys
sys.path.insert(0, {testler!r})
import alt_surec_ag_bekcisi as _ag
sys.path.remove({testler!r})
import io, json, os
sys.path[:0] = [{kok!r}, {backend!r}]
import numpy as np
from PIL import Image
from fastapi.testclient import TestClient
from servers import api_server as api
import servers.ai_router as air
air.ai_service_enabled = lambda: False
api.app.dependency_overrides[air.require_research] = lambda: None
buf = io.BytesIO()
rng = np.random.default_rng(0)
Image.fromarray((rng.random((320, 320)) * 255).astype("uint8"), "L").convert("RGB").save(buf, "PNG")
PNG = buf.getvalue()
c = TestClient(api.app, client=("127.0.0.1", 50124), raise_server_exceptions=False)
s = {{}}
r = c.post("/api/ai/vision/kidney_ct", files={{"file": ("g.png", PNG, "image/png")}}, data={{"explain": "true"}})
j = r.json() if r.headers.get("content-type", "").startswith("application/json") else {{}}
s["ct"] = {{"kod": r.status_code, "xai_gorsel": bool(j.get("xai_image_base64")), "xai_hata": j.get("xai_error"),
           "detay": str(j.get("detail"))[:300]}}
for dil in ("tr", "en"):
    r = c.post("/api/ai/vision/scratch", files={{"file": ("g.png", PNG, "image/png")}}, headers={{"X-PEMF-Dil": dil}})
    try:
        d = r.json().get("detail")
    except Exception:
        d = r.text[:300]
    s["scratch:" + dil] = {{"kod": r.status_code, "detay": str(d)[:400]}}
s["estop"] = c.post("/api/hardware/emergency_stop").status_code
s["ag"] = _ag.ENGELLENEN
print("SONUC " + json.dumps(s, ensure_ascii=False, default=str))
sys.stdout.flush()
os._exit(0)
"""


def _gercek_agirlik_koku() -> Path | None:
    """Gerçek ağırlık kökü: önce `PEMF_AI_MODELS_DIR` (denetim koşucusu verir), yoksa ÜRÜNÜN kendi kök listesi (`_candidate_model_roots`;
    yayın makinesinde `release_assets/ai_models`). Y30 (`yayin_oncesi_suit.ps1`) değişkeni VERMEZ — yalnız ona bakılınca iki uçtan uca
    kol PEMF_GOLDEN_REQUIRED=1'de her yayında düşüyordu (ölçüldü 2026-11-03)."""
    from utils.model_downloader import _candidate_model_roots

    env = os.environ.get("PEMF_AI_MODELS_DIR", "")
    for k in ([Path(env)] if env else []) + list(_candidate_model_roots()):
        if all((Path(k) / r).is_file() for r in (CT_ONNX, RETIC_PT)):
            return Path(k)
    return None


@pytest.fixture(scope="module")
def uctan_uca(tmp_path_factory):
    from golden.eser import atla

    gercek = _gercek_agirlik_koku()
    if gercek is None:
        atla("gerçek ağırlık kökü yok (PEMF_AI_MODELS_DIR / ürün kökleri: release_assets/ai_models)")
    tmp = tmp_path_factory.mktemp("d3i_e1")
    kok = tmp / "modeller"
    for hedef, kaynak in ((CT_ONNX, CT_ONNX), (CT_PT, RETIC_PT)):  # PT ikizi yerine BAŞKA modelin yüklenebilir ağırlığı
        (kok / hedef).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(gercek / kaynak, kok / hedef)
    (kok / CPN).parent.mkdir(parents=True, exist_ok=True)
    (kok / CPN).write_bytes(b"\x80\x02" + b"K" * 300_000)  # CPN: manifestle TUTMAYAN kopya
    env = yalitik_ortam(tmp / "ev")
    env.update(
        {
            "PEMF_AI_MODELS_DIR": str(kok),
            "PEMF_DATA_DIR": str(tmp / "veri"),
            "PEMF_DEVICE_IDENTITY_DIR": str(tmp / "kimlik"),
            "PEMF_CLOUD_PROVISION_PATH": str(tmp / "yok" / "p.json"),
            "PEMF_LOG_DIR": str(tmp / "log"),
            "PEMF_CLOUD_PATIENT_SYNC": "0",
            "SUPABASE_URL": "http://127.0.0.1:9",
            "PEMF_ESP_ENABLED": "0",
            "PEMF_AI_WARMUP": "0",
            "PEMF_SCRATCH_WARMUP": "0",
            "PEMF_AI_DOMAIN_GUARD": "0",  # modalite kapısı sentetik görseli ÖNCE keserdi — ölçülen zincir değişmez
        }
    )
    yol = tmp / "cocuk.py"
    yol.write_text(_COCUK.format(testler=str(TESTLER), kok=str(KOK), backend=str(BACKEND)), encoding="utf-8")
    p = kostur([str(yol)], cwd=tmp, env=env, sure=900)
    satir = [x for x in p.stdout.splitlines() if x.startswith("SONUC ")]
    assert satir, p.stdout[-2000:] + p.stderr[-3000:]
    return json.loads(satir[-1][6:])


def test_KRITIK_D3I_E1_XAI_ikizi_BASKA_surum_iken_aciklama_URETILMEZ_analiz_SURER(uctan_uca):
    s = uctan_uca["ct"]
    assert uctan_uca["ag"] == [], uctan_uca["ag"]
    assert s["kod"] == 200, f"ana analiz (bütünlüğü doğrulanmış ONNX) etkilenmemeli: {s}"
    assert not s["xai_gorsel"] and s["xai_hata"], (
        f"PT ikizi yerine BAŞKA modelin ağırlığıyla açıklama SESSİZCE üretildi: {s}"
    )


def test_KRITIK_D3I_E1_CPN_manifestle_TUTMAZKEN_yara_kapanma_503_ACIK_uyari_TR_EN(uctan_uca):
    tr, en = uctan_uca["scratch:tr"], uctan_uca["scratch:en"]
    dosya = Path(CPN).name
    assert tr["kod"] == 503 and dosya in tr["detay"] and "bütünlük denetimini GEÇMEDİ" in tr["detay"], tr
    assert en["kod"] == 503 and dosya in en["detay"] and "failed its integrity check" in en["detay"], en
    assert uctan_uca["estop"] == 200
