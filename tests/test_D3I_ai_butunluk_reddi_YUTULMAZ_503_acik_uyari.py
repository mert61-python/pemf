# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D3I-A2.4 (D3.48 · Y18) — MODEL BÜTÜNLÜK REDDİ YÜKLEYİCİDE YUTULMAZ: AI ucu 503 + AÇIK uyarı (dosya adıyla, istek dilinde).

ÖLÇÜLEN KUSUR: `ai_router` kidney_ct / histopath / cat_sound / em_petri (YOLO) yükleyicileri ve `catorgan_predictor._resolve_models`
`download_model_sync`'i `except Exception` ile sarıp `ModelButunlukHatasi`ni UYARIYA çeviriyor, modül-yanı yola düşüyordu: donmuş pakette
o yol yok (≥ 5 MB ağırlık `_internal`a girmez) → başka hata → 500 "… analiz hatası" (kedi organda daha kötüsü: "segmentasyon: YOLO model
yok" → 200 "kedi / organ bulunamadı"); kaynak düzende modül-yanı kopya varsa reddedilen kök SESSİZCE atlanıyordu (D3.48 "başka köke
düşüş YOK"). `inference_human_kidney_rna` `scaler.pkl` (joblib = pickle) + ONNX'i modül yanından DENETİMSİZ yüklüyordu.

SÖZLEŞME (Y18): kurulu ağırlık manifestle TUTMAZSA uç 503 + `ai.hata.modelButunluk` (dosya adı; TR / EN istek diline göre); ACİL DURDUR
etkilenmez. kidney_rna yan dosyaları `yan_dosya_coz`dan geçer — donmuş düzende (`_MEIPASS/ai_hub/…`, manifest paketten) de.
Sahte EN ALT katta: yalnız model KÖKÜ (geçici, `PEMF_AI_MODELS_DIR` — ilk aday kök) ve kurcalanmış KOPYA; manifest gerçek takipli dosya;
router / yükleyici / `_ai_fail` / ceviri gerçek. Uçlar alt süreçte (ağ bekçisi, yalıtılmış ortam, süreç içi TestClient — port YOK).
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest
from betik_alt_sureci import kostur, yalitik_ortam

KOK = Path(__file__).resolve().parents[1]
TESTLER = Path(__file__).resolve().parent
BACKEND = KOK / "apps" / "backend"
for _p in (str(BACKEND), str(KOK)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

#: uç → (kurcalanan takipli ağırlık, istek biçimi)
UCLAR = {
    "kidney_ct": ("ai_hub/inference_human_kidney_ct/yolov8s.onnx", "gorsel"),
    "histopath": ("ai_hub/inference_renal_histopath_kmc/v22_kmc_classictrio_kmc.onnx", "gorsel"),
    "cat_sound": ("ai_hub/inference_cat_sound/EfficientNet_Lite0.onnx", "ses"),
    "em_petri": ("ai_hub/inference_petri_dish/yolo11m-seg.onnx", "gorsel"),
    "cat_organ": ("ai_hub/inference_cat_organ/models/yolov8m-seg.onnx", "gorsel"),
}
_YOL = {
    "kidney_ct": "/api/ai/vision/kidney_ct",
    "histopath": "/api/ai/vision/histopath",
    "cat_sound": "/api/ai/sound/cat",
    "em_petri": "/api/ai/vision/em_petri",
    "cat_organ": "/api/ai/vision/cat_organ",
}

_COCUK = r"""
import sys
sys.path.insert(0, {testler!r})
import alt_surec_ag_bekcisi as _ag
sys.path.remove({testler!r})
import io, json, math, os, random, struct, wave
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
Image.fromarray((rng.random((512, 512)) * 255).astype("uint8"), "L").convert("RGB").save(buf, "PNG")
PNG = buf.getvalue()
sb = io.BytesIO()
with wave.open(sb, "wb") as w:  # 1 sn gürültü (sessizlik kapısını GEÇER), 22050 Hz mono 16 bit
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(22050)
    random.seed(0)
    w.writeframes(b"".join(struct.pack("<h", int(12000 * math.sin(i / 7.0) + random.randint(-3000, 3000))) for i in range(22050)))
WAV = sb.getvalue()
c = TestClient(api.app, client=("127.0.0.1", 50123), raise_server_exceptions=False)
sonuc = {{}}
for uc, (yol, bicim) in {uclar!r}.items():
    for dil in ("tr", "en"):
        dosya = ("ses.wav", WAV, "audio/wav") if bicim == "ses" else ("g.png", PNG, "image/png")
        r = c.post(yol, files={{"file": dosya}}, headers={{"X-PEMF-Dil": dil}})
        try:
            detay = r.json().get("detail")
        except Exception:
            detay = r.text[:300]
        sonuc[uc + ":" + dil] = {{"kod": r.status_code, "detay": str(detay)[:400]}}
r = c.post("/api/hardware/emergency_stop")
sonuc["estop"] = r.status_code
sonuc["ag"] = _ag.ENGELLENEN
print("SONUC " + json.dumps(sonuc, ensure_ascii=False, default=str))
sys.stdout.flush()
os._exit(0)
"""


@pytest.fixture(scope="module")
def uc_sonuclari(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("d3i_a24")
    kok = tmp / "modeller"
    for goreli, _ in UCLAR.values():
        hedef = kok / goreli
        hedef.parent.mkdir(parents=True, exist_ok=True)
        hedef.write_bytes(
            b"\x08\x07" + b"K" * 300_000
        )  # asgari boyut ÜSTÜ, manifest özeti TUTMAZ (kurcalanmış / başka sürüm)
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
            # Modalite (alan) kapısı ölçülen kolu ÖNCE keserdi (sentetik görsel CT / H&E / fotoğraf değil) — kaçış kapağıyla kapalı;
            # model çözümü / bütünlük / `_ai_fail` zinciri DEĞİŞMEZ.
            "PEMF_AI_DOMAIN_GUARD": "0",
        }
    )
    yol = tmp / "cocuk.py"
    uclar = {u: (_YOL[u], b) for u, (_, b) in UCLAR.items()}
    yol.write_text(
        _COCUK.format(testler=str(TESTLER), kok=str(KOK), backend=str(BACKEND), uclar=uclar), encoding="utf-8"
    )
    p = kostur([str(yol)], cwd=tmp, env=env, sure=900)
    satir = [s for s in p.stdout.splitlines() if s.startswith("SONUC ")]
    assert satir, p.stdout[-2000:] + p.stderr[-3000:]
    return json.loads(satir[-1][6:])


@pytest.mark.parametrize("uc", list(UCLAR))
def test_KRITIK_D3I_A2_4_butunluk_reddi_YUTULMAZ_503_dosya_adiyla_TR_EN(uc_sonuclari, uc):
    """MUTASYON: uçtaki `except ModelButunlukHatasi: raise` (catorgan: yeniden yükseltme) kaldırılır → o uç KIRMIZI."""
    s = uc_sonuclari
    assert s["ag"] == [], s["ag"]
    dosya = Path(UCLAR[uc][0]).name
    tr, en = s[uc + ":tr"], s[uc + ":en"]
    assert tr["kod"] == 503 and dosya in tr["detay"] and "bütünlük denetimini GEÇMEDİ" in tr["detay"], (
        f"{uc}: bütünlük reddi YUTULDU (Y18: 503 + açık uyarı bekleniyordu): {tr}"
    )
    assert en["kod"] == 503 and dosya in en["detay"] and "failed its integrity check" in en["detay"], f"{uc} (EN): {en}"


def test_KARSIT_D3I_A2_4_butunluk_reddinde_ACIL_DURDUR_calisir(uc_sonuclari):
    assert uc_sonuclari["estop"] == 200, uc_sonuclari["estop"]


# ─────────────────────────── kidney_rna: modül-yanı yan dosyalar — DONMUŞ düzen (`_MEIPASS`) ───────────────────────────


@pytest.fixture
def donmus(tmp_path, monkeypatch):
    """`_MEIPASS/ai_hub/ai_models_sha256.json` (paketteki manifest) + `_MEIPASS/ai_hub/inference_human_kidney_rna/` (D4.27: < 5 MB, app
    katmanı). Kaynak kökün manifesti GÖRÜNMEZ yapılır → yalnız paketteki manifest kullanılır."""
    from utils import model_downloader as md

    ic = tmp_path / "_internal"
    (ic / "ai_hub").mkdir(parents=True)
    shutil.copy2(KOK / "release_assets" / "ai_models_sha256.json", ic / "ai_hub" / "ai_models_sha256.json")
    d = ic / "ai_hub" / "inference_human_kidney_rna"
    shutil.copytree(KOK / "ai_hub" / "inference_human_kidney_rna", d)
    monkeypatch.setattr(sys, "_MEIPASS", str(ic), raising=False)
    monkeypatch.setattr(md, "kaynak_kokunu_bul", lambda *a, **k: tmp_path / "kaynak_yok")
    monkeypatch.setattr(md, "_manifest_onbellegi", {})
    monkeypatch.setattr(md, "_ozet_onbellegi", {})
    assert md._manifest_ozetleri().get("ai_hub/inference_human_kidney_rna/scaler.pkl"), (
        "ön koşul: paketteki manifest okunmadı"
    )
    yield md, d
    for ad in [m for m in sys.modules if m.startswith("d3i_a24_rna")]:
        sys.modules.pop(ad, None)


def _rna_yukle(d: Path):
    spec = importlib.util.spec_from_file_location("d3i_a24_rna", d / "__init__.py", submodule_search_locations=[str(d)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_KARSIT_D3I_A2_4_kidney_rna_DONMUS_duzende_SAGLAM_kopya_yuklenir(donmus):
    md, d = donmus
    assert _rna_yukle(d).KidneyRnaPredictor().expected_cols > 0


def test_KRITIK_D3I_A2_4_kidney_rna_DONMUS_duzende_kurcalanan_OLCEKLEYICI_yuklenmez(donmus):
    """MUTASYON: `scaler.pkl` çözücüden geçmez → KIRMIZI (×1,10 kurcalanmış ölçekleyici sessizce yüklenir)."""
    import joblib

    md, d = donmus
    sc = joblib.load(d / "scaler.pkl")
    sc.scale_ = sc.scale_.copy()
    sc.scale_[0] = sc.scale_[0] * 1.10
    joblib.dump(sc, d / "scaler.pkl")
    with pytest.raises(md.ModelButunlukHatasi) as ex:
        _rna_yukle(d).KidneyRnaPredictor()
    assert Path(ex.value.dosya).name == "scaler.pkl"


def test_KRITIK_D3I_A2_4_kidney_rna_DONMUS_duzende_kurcalanan_ONNX_yuklenmez(donmus):
    """MUTASYON: ONNX çözücüden geçmez → KIRMIZI."""
    md, d = donmus
    onnx = d / "mlp_medium_kirc.onnx"
    veri = bytearray(onnx.read_bytes())
    veri[-1] ^= 0x01
    onnx.write_bytes(bytes(veri))
    with pytest.raises(md.ModelButunlukHatasi) as ex:
        _rna_yukle(d).KidneyRnaPredictor()
    assert Path(ex.value.dosya).name == "mlp_medium_kirc.onnx"
