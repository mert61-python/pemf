# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.94 · B-10.126 · B-10.147 · B-10.148 — üç güvenlik kapısı metin yerine DAVRANIŞA / AST'ye bağlanır.

ÖLÇÜLEN KÖRLÜK (bu commit'te, ürün bugün doğru):
  (a) `torch.load(..., weights_only=True)` kapısı (`test_gradient_xai_ses_termal`) torch + PT ikizi yokken ATLANIYOR
      (CI'da hiç koşmaz) ve kaynak penceresinde METİN arıyordu — aynı penceredeki yorum ("weights_only=True — agirlik
      SAF state_dict") argüman silinse de kapıyı yeşil tutar. Pickle-RCE savunması fiilen kapısızdı.
  (b) Multipart alan limiti (`test_multipart_alan_limiti`) yamayı modül fikstüründe KENDİSİ uyguluyor; `api_server`
      kaynağında yalnız ADIN geçmesine bakıyordu → `api_server`'daki çağrı `pass` olsa yeşil kalır, sahadaki
      "Part exceeded 1024KB" arızası geri gelir.
  (c) 422 zarfı (`test_observability`) yalnız `"input"` ANAHTARINI arıyordu → ham değer başka bir anahtarla
      (`"value": e.get("input")`) dönerse yeşil kalır — PII sızıntısı.

Ö.4: torch/onnx sürümüne dokunulmaz (Y3); kapı sürümden bağımsız (AST, torch import edilmez).
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from betik_alt_sureci import kostur, yalitik_ortam

KOK = Path(__file__).resolve().parents[1]
TESTLER = Path(__file__).resolve().parent


# ── (a) torch.load weights_only — AST, torch'suz ortamda da KOŞAR ───────────────────────────────────────────────
def _torch_load_cagrilari() -> list[tuple[str, int, object]]:
    """Ürün kaynağındaki (`ai_hub`, `apps/backend`) DOĞRUDAN `torch.load(...)` çağrıları → (dosya, satır, weights_only
    anahtar sözcüğünün sabit değeri | 'YOK' | 'SABIT_DEGIL')."""
    sonuc = []
    for kok in (KOK / "ai_hub", KOK / "apps" / "backend"):
        for py in kok.rglob("*.py"):
            if "tests" in py.parts or py.name.startswith("test_"):
                continue
            try:
                agac = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for d in ast.walk(agac):
                if (
                    isinstance(d, ast.Call)
                    and isinstance(d.func, ast.Attribute)
                    and d.func.attr == "load"
                    and isinstance(d.func.value, ast.Name)
                    and d.func.value.id == "torch"
                ):
                    kw = next((k for k in d.keywords if k.arg == "weights_only"), None)
                    deger = (
                        "YOK"
                        if kw is None
                        else (kw.value.value if isinstance(kw.value, ast.Constant) else "SABIT_DEGIL")
                    )
                    sonuc.append((str(py.relative_to(KOK)), d.lineno, deger))
    return sonuc


def test_KRITIK_a_her_dogrudan_torch_load_weights_only_TRUE_AST():
    cagrilar = _torch_load_cagrilari()
    dosyalar = {c[0].replace("\\", "/") for c in cagrilar}
    assert "ai_hub/cat_thermal/inference_cat_thermal.py" in dosyalar and len(cagrilar) >= 4, (
        f"ön koşul: bilinen torch.load çağrıları bulunamadı (AST okuma yolu kırıldı?): {cagrilar}"
    )
    acik = [c for c in cagrilar if c[2] is not True]
    assert not acik, f"weights_only=True OLMAYAN torch.load (pickle-RCE kapısı açık): {acik}"


# ── (b) multipart alan limiti — api_server İÇE AKTARILINCA uygulanır (ayrı süreç) ───────────────────────────────
_COCUK = r"""
import sys
sys.path.insert(0, {testler!r})
import alt_surec_ag_bekcisi as _ag
sys.path.remove({testler!r})
import json, os
sys.path[:0] = [{kok!r}, {backend!r}]
from starlette.requests import Request
once = bool(getattr(Request.form, "_pemf_multipart_patched", False))
import servers.api_server  # noqa: F401 — ölçülen: İÇE AKTARMANIN yan etkisi
sonra = bool(getattr(Request.form, "_pemf_multipart_patched", False))
from fastapi import FastAPI, Form
from fastapi.testclient import TestClient
app = FastAPI()

@app.post("/t")
async def t(image_base64: str = Form(None)):
    return {{"len": len(image_base64 or "")}}

r = TestClient(app).post("/t", data={{"image_base64": "A" * (3 * 1024 * 1024)}})
print("SONUC " + json.dumps({{"once": once, "sonra": sonra, "kod": r.status_code, "ag": _ag.ENGELLENEN}}, default=str))
sys.stdout.flush()
os._exit(0)
"""


def test_KRITIK_b_api_server_ICE_AKTARILINCA_3MB_form_alani_GECER_ayri_surec(tmp_path):
    env = yalitik_ortam(tmp_path / "ev")
    env.update(
        {
            "PEMF_DATA_DIR": str(tmp_path / "veri"),
            "PEMF_LOG_DIR": str(tmp_path / "log"),
            "PEMF_DEVICE_IDENTITY_DIR": str(tmp_path / "kimlik"),
            "PEMF_CLOUD_PROVISION_PATH": str(tmp_path / "yok" / "provizyon.json"),
            "PEMF_CLOUD_PATIENT_SYNC": "0",
            "SUPABASE_URL": "http://127.0.0.1:9",
            "PEMF_ESP_ENABLED": "0",
            "PEMF_FW_AUTO_UPDATE": "0",
            "PEMF_HOTSPOT": "0",
            "PEMF_AI_WARMUP": "0",
            "PEMF_ENABLE_TUNNEL": "0",
        }
    )
    kod = _COCUK.format(testler=str(TESTLER), kok=str(KOK), backend=str(KOK / "apps" / "backend"))
    (tmp_path / "cocuk.py").write_text(kod, encoding="utf-8")
    p = kostur([str(tmp_path / "cocuk.py")], cwd=tmp_path, env=env, sure=300)
    satir = next((s for s in p.stdout.splitlines() if s.startswith("SONUC ")), None)
    assert satir, f"çocuk sonuç basmadı (rc={p.returncode}): {p.stderr[-1500:]}"
    s = json.loads(satir[len("SONUC ") :])
    assert s["once"] is False, f"aparat: yama api_server'dan ÖNCE uygulanmış görünüyor: {s}"
    assert s["ag"] == [], f"çocuk ağa çıkmayı denedi: {s['ag']}"
    assert s["sonra"] is True and s["kod"] == 200, (
        f"api_server içe aktarıldığında multipart alan limiti UYGULANMADI ({s}) — sahadaki 'Part exceeded "
        "1024KB' arızası (Yara Kapanma büyük görüntü) geri gelir"
    )


# ── (c) 422 zarfı — ham girdi HİÇBİR anahtarla dönmez ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("alan", ["frequency", "duration_minutes"])
def test_KRITIK_c_422_yaniti_HAM_GIRDIYI_hicbir_anahtarla_DONDURMEZ(alan):
    from fastapi.testclient import TestClient
    from servers import api_server as api

    ham = "HASTA-ADI-XYZ-Boncuk"
    c = TestClient(api.app, client=("127.0.0.1", 51236))
    r = c.post("/api/session/start", json={"mode": "Manuel", alan: ham, "coil_ids": [1]})
    assert r.status_code == 422, f"aparat: doğrulama hatası beklenirdi ({r.status_code}: {r.text[:120]})"
    assert ham not in r.text and "Boncuk" not in r.text, f"422 yanıtı HAM girdiyi (PII) sızdırıyor: {r.text[:300]}"
    assert r.json().get("errors"), "aparat: zarfta hata listesi yok"
