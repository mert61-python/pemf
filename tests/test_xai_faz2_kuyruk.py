# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""FAZ 2 KUYRUĞU: FELINE/CT EigenCAM + RNA Integrated Gradients (plan §5/§7).

ÖLÇÜLEN DURUM: retikülosit/CT tespitleri annotated görsel döner ama modelin hangi hücre
kümelerine/bölgelere dayandığı ayrıca görünmez (EigenCAM label-agnostik, GRADIENT'SİZ —
YOLO'da Grad-CAM gürültülü, doc §10.1). RNA ucu KIRC/other olasılığı döner ama HANGİ
GENLERİN kararı sürüklediğini dönmez (Captum IG; CT-XAI Faz-0 karar #4 ile ONAYLI).

DÜZELTME: xai_retikulosit_isi_haritasi + xai_ct_isi_haritasi (PT-YOLO cache + tek-iş
kilidi + bellek-içi base64) ve RNA xai_top_genler (IG internal_batch_size'lı; hasta
başına signed top-N gen; ⚠️ N>25 hastada üretilmez — 60MB CSV'de IG maliyet patlaması).
Router explain=true kablolaması + ai_service paritesi; XAI hatası analizi düşürmez.

CI notu: torch yok + PT'ler gitignore'lu → gerçek-model testleri açık-reason skipif;
kablolama testleri mock'la her ortamda (yerleşik desen).
"""

from __future__ import annotations

import ast
import base64
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

KOK = Path(__file__).resolve().parents[1]

_FELINE_PT = KOK / "release_assets/ai_models/ai_hub/feline_reticulocytes/yolov8s.pt"
_CT_PT = KOK / "release_assets/ai_models/ai_hub/inference_human_kidney_ct/yolov8s.pt"
_RNA_PT = KOK / "ai_hub/inference_human_kidney_rna/mlp_medium_kirc.pt"


def _torch_var() -> bool:
    try:
        import torch  # noqa: F401

        return True
    except ImportError:
        return False


from golden.eser import eser_var_mi as _eser_var_mi  # noqa: E402
from golden.eser import zorunlu_mu as _zorunlu_mu

# AII-3.13: koşul ürünün model kökünü (PEMF_AI_MODELS_DIR) de görür; PEMF_GOLDEN_REQUIRED=1'de ATLANMAZ (4-A SKIP→FAIL)
yolo_pt_gerekir = pytest.mark.skipif(
    not (
        _torch_var()
        and _eser_var_mi("ai_hub/feline_reticulocytes/yolov8s.pt", "ai_hub/inference_human_kidney_ct/yolov8s.pt")
    )
    and not _zorunlu_mu(),
    reason="torch/YOLO-PT yok (CI) — gerçek tespit hedefli CAM (DetCAM) testi modelli ortamda",
)
# D5-F (K5-F P5): `yolo_pt_gerekir` ile AYNI desen — eskiden düz `_RNA_PT.exists()`: golden zorunlu kipte de ATLIYORDU.
rna_pt_gerekir = pytest.mark.skipif(
    not (_torch_var() and _eser_var_mi("ai_hub/inference_human_kidney_rna/mlp_medium_kirc.pt")) and not _zorunlu_mu(),
    reason="torch/mlp PT yok (CI) — gerçek IG testi modelli ortamda",
)


def _b64_gorsel(b64: str) -> np.ndarray:
    import cv2

    img = cv2.imdecode(np.frombuffer(base64.b64decode(b64), np.uint8), cv2.IMREAD_COLOR)
    assert img is not None, "xai_image_base64 geçerli görsel değil"
    return img


# ── 1) YOLO CAM — gerçek PT'lerle (AI1.X2/X3: EigenCAM → tespit hedefli HiRes-CAM; yerleşim kapısı
#        tests/test_xai_yolo_TESPIT_hedefli_cam_AI1_X2_X3.py) ───────────────────────────────────────────────
@yolo_pt_gerekir
def test_KRITIK_feline_detcam_URETIR_ve_DETERMINISTIK(tmp_path):
    import cv2

    from ai_hub.feline_reticulocytes.inference_feline_reticulocytes import xai_retikulosit_isi_haritasi

    rng = np.random.default_rng(4)
    img = (rng.random((320, 320, 3)) * 255).astype(np.uint8)
    p = tmp_path / "kan.jpg"
    cv2.imwrite(str(p), img)
    r1 = xai_retikulosit_isi_haritasi(str(p))
    ov = _b64_gorsel(r1["xai_image_base64"])
    assert float(ov.std()) > 1.0 and r1.get("method") == "hirescam"
    r2 = xai_retikulosit_isi_haritasi(str(p))
    assert r1["xai_image_base64"] == r2["xai_image_base64"], "tespit hedefli CAM deterministik değil"


@yolo_pt_gerekir
def test_KRITIK_ct_detcam_URETIR(tmp_path):
    import cv2

    from ai_hub.inference_human_kidney_ct.inference_human_kidney_ct import xai_ct_isi_haritasi

    rng = np.random.default_rng(6)
    img = (rng.random((320, 320, 3)) * 255).astype(np.uint8)
    p = tmp_path / "ct.jpg"
    cv2.imwrite(str(p), img)
    r = xai_ct_isi_haritasi(str(p))
    ov = _b64_gorsel(r["xai_image_base64"])
    assert float(ov.std()) > 1.0 and r.get("method") == "hirescam"


def _explain_cagrilari(dugumler) -> list:
    return [
        c
        for d in dugumler
        for c in ast.walk(d)
        if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.func.attr == "explain"
    ]


def test_YAPISAL_yolo_cam_tek_is_kilidi():
    """AI1.X2/X3: kilit + explain CAM hesabını yapan yardımcıya taşındı (xai_*_isi_haritasi onu çağırır).

    ⚠️ D5.57 (B-10.171): eskiden metin SIRASI ölçülüyordu (`_XAI_KILIT` konumu < `.explain(` konumu) — `return expl.explain(...)`
    `with` bloğunun DIŞINA alınınca (girinti 8→4) sıra aynı kaldığından YEŞİLDİ (ölçüldü, HEAD d38b0db5): CAM hesabı kilitsiz, iki
    eşzamanlı istek önbellekteki hook'lu açıklayıcıyı paylaşır. Artık AST: `.explain(...)` çağrısı `with _XAI_KILIT:` GÖVDESİNDE
    ve işlevde kilit DIŞINDA hiç `.explain(` yok (yorum / docstring görünmez)."""
    for dosya, fn in [
        ("ai_hub/feline_reticulocytes/inference_feline_reticulocytes.py", "retikulosit_cam_haritasi"),
        ("ai_hub/inference_human_kidney_ct/inference_human_kidney_ct.py", "ct_cam_haritasi"),
    ]:
        agac = ast.parse((KOK / dosya).read_text(encoding="utf-8", errors="replace"))
        f = next((d for d in agac.body if isinstance(d, ast.FunctionDef) and d.name == fn), None)
        assert f is not None, f"{dosya}: {fn} bulunamadı (çıpa kaymış)"
        kilitli = [
            w
            for w in ast.walk(f)
            if isinstance(w, ast.With)
            and any(isinstance(i.context_expr, ast.Name) and i.context_expr.id == "_XAI_KILIT" for i in w.items)
        ]
        assert kilitli, f"{dosya}:{fn} `with _XAI_KILIT:` bloğu YOK — YOLO CAM kilitsiz"
        icerde = {id(c) for w in kilitli for c in _explain_cagrilari(w.body)}
        hepsi = _explain_cagrilari(f.body)
        assert hepsi and icerde, f"{dosya}:{fn} `.explain(...)` kilit gövdesinde DEĞİL (kilitsiz CAM hesabı)"
        assert all(id(c) in icerde for c in hepsi), f"{dosya}:{fn} kilit DIŞINDA `.explain(...)` çağrısı var"


_XAI_MODULLERI = [
    (
        "ai_hub/feline_reticulocytes/inference_feline_reticulocytes.py",
        "ai_hub.feline_reticulocytes.inference_feline_reticulocytes",
    ),
    (
        "ai_hub/inference_human_kidney_ct/inference_human_kidney_ct.py",
        "ai_hub.inference_human_kidney_ct.inference_human_kidney_ct",
    ),
]


def _kilitli_govdeler(agac) -> list:
    return [
        w
        for w in ast.walk(agac)
        if isinstance(w, ast.With)
        and any(isinstance(i.context_expr, ast.Name) and i.context_expr.id == "_XAI_KILIT" for i in w.items)
    ]


@pytest.mark.parametrize("dosya,modul_adi", _XAI_MODULLERI)
def test_KRITIK_D557_XAI_kilidi_GERCEK_kilit_ve_MODULDEKI_tum_explain_cagrilari_kilitli(dosya, modul_adi):
    """TUR 2 (çürütücü la / lb): `test_YAPISAL_yolo_cam_tek_is_kilidi` yalnız `with _XAI_KILIT:` BİÇİMİNE ve yalnız
    `*_cam_haritasi` gövdesine bakıyordu → (la) `_XAI_KILIT = contextlib.nullcontext()` (kilit no-op) ve (lb) ikiz çağrı yeri
    `xai_retikulosit_isi_haritasi`nin önbellekteki açıklayıcıda `.explain(...)`i KİLİTSİZ çağırması geniş kümede (320 passed) YEŞİLDİ.
    Kapı: (1) DAVRANIŞ — modülün `_XAI_KILIT`i iki iş parçacığını gerçekten DIŞLAR (bu iş parçacığı tutarken başka iş parçacığı
    `acquire(blocking=False)` ile ALAMAZ); (2) AST — MODÜLDEKİ HER `.explain(` çağrısı bir `with _XAI_KILIT:` gövdesinde (ikiz yerler,
    yorum / docstring görünmez). MUTASYON: kilit nullcontext / Semaphore(2); ikiz yerde kilitsiz explain → KIRMIZI."""
    import importlib
    import threading

    mod = importlib.import_module(modul_adi)
    kilit = getattr(mod, "_XAI_KILIT", None)
    assert callable(getattr(kilit, "acquire", None)) and callable(getattr(kilit, "release", None)), (
        f"{dosya}: _XAI_KILIT bir kilit DEĞİL ({type(kilit).__name__}) — eşzamanlı CAM istekleri hook'lu açıklayıcıyı paylaşır"
    )
    assert kilit.acquire(timeout=5), f"{dosya}: aparat — _XAI_KILIT alınamadı (başka iş tutuyor)"
    try:
        alindi: list = []
        t = threading.Thread(target=lambda: alindi.append(kilit.acquire(blocking=False)), daemon=True)
        t.start()
        t.join(5)
        if alindi == [True]:
            kilit.release()  # sızan ikinci edinimi geri ver (bozuk kilitte bile durum temiz kalsın)
        assert alindi == [False], (
            f"{dosya}: _XAI_KILIT iki iş parçacığını DIŞLAMIYOR ({type(kilit).__name__}; ikinci edinim {alindi}) — CAM hesabı kilitsiz"
        )
    finally:
        kilit.release()
    agac = ast.parse((KOK / dosya).read_text(encoding="utf-8", errors="replace"))
    icerde = {id(c) for w in _kilitli_govdeler(agac) for c in _explain_cagrilari(w.body)}
    hepsi = _explain_cagrilari(agac.body)
    assert hepsi, f"{dosya}: modülde `.explain(...)` çağrısı yok (çıpa kaymış)"
    disarda = [f"satır {c.lineno}" for c in hepsi if id(c) not in icerde]
    assert not disarda, f"{dosya}: kilit DIŞINDA `.explain(...)` çağrısı var (ikiz çağrı yeri kilitsiz): {disarda}"


# ── 2) RNA IG — gerçek PT ile ────────────────────────────────────────────────
@rna_pt_gerekir
def test_KRITIK_rna_ig_top_genler_URETIR_ve_DETERMINISTIK():
    import pandas as pd

    from ai_hub.inference_human_kidney_rna.inference_human_kidney_rna import xai_top_genler

    # Sentetik 20531-gen tablosu (2 hasta) — GERÇEK scaler/fs_idx/PT zinciriyle akar.
    rng = np.random.default_rng(12)
    n_gen = 20531
    df = pd.DataFrame(
        rng.random((2, n_gen)).astype(np.float32) * 100.0,
        index=["hasta_A", "hasta_B"],
        columns=[f"gene_{i}" for i in range(n_gen)],
    )
    a = xai_top_genler(df, top_n=8)
    assert len(a) == 2
    for satir in a:
        tg = satir["top_genes"]
        assert len(tg) == 8 and all(t["gene"].startswith("gene_") for t in tg)
        assert sum(abs(t["attribution"]) for t in tg) > 1e-8, "IG katkıları ~0 — zincir kırık"
    b = xai_top_genler(df, top_n=8)
    assert a == b, "aynı CSV'ye farklı gen açıklaması (IG deterministik olmalı)"


# ── 3) Uç kablolamaları (mock — her ortamda) ─────────────────────────────────
_SENT_IMG = {"xai_image_base64": base64.b64encode(b"x").decode(), "method": "eigencam"}


@pytest.fixture()
def istemci(monkeypatch):
    import servers.ai_router as air
    import servers.api_server as apis

    monkeypatch.setattr(air, "ai_service_enabled", lambda: False)
    return TestClient(apis.app), air


def _jpg_b64() -> str:
    """RENKLİ test görüntüsü — modalite kapısı düz/gri kareyi haklı olarak reddediyor
    (kapı çalışıyor; test kapıdan GEÇEBİLEN kan-yayması-benzeri renkli doku üretir)."""
    import cv2

    rng = np.random.default_rng(3)
    img = np.zeros((64, 64, 3), dtype=np.uint8)
    img[..., 2] = (rng.random((64, 64)) * 120 + 120).astype(np.uint8)  # kırmızı ağırlıklı (BGR)
    img[..., 1] = (rng.random((64, 64)) * 90 + 40).astype(np.uint8)
    img[..., 0] = (rng.random((64, 64)) * 60 + 30).astype(np.uint8)
    ok, buf = cv2.imencode(".jpg", img)
    return base64.b64encode(buf.tobytes()).decode()


def test_KRITIK_feline_endpoint_explain_kablolamasi(istemci, monkeypatch):
    client, air = istemci
    import ai_hub.feline_reticulocytes.inference_feline_reticulocytes as ifr

    class _R:  # ultralytics result taklidi (endpoint'in okuduğu alanlar)
        boxes = None
        save_dir = ""

    class _M:
        def predict(self, **k):
            return [_R()]

    monkeypatch.setattr(air, "_get_or_load_model", lambda ad, yukleyici: _M())
    cagri = []
    monkeypatch.setattr(ifr, "xai_retikulosit_isi_haritasi", lambda *a, **k: cagri.append(1) or _SENT_IMG)

    r = client.post("/api/ai/vision/reticulocytes", data={"image_base64": _jpg_b64(), "explain": "true"})
    assert r.status_code == 200, r.text
    assert r.json().get("xai_image_base64") == _SENT_IMG["xai_image_base64"] and cagri

    r2 = client.post("/api/ai/vision/reticulocytes", data={"image_base64": _jpg_b64()})
    assert r2.status_code == 200 and "xai_image_base64" not in r2.json()


def test_KRITIK_rna_endpoint_explain_kablolamasi_ve_N_SINIRI(istemci, monkeypatch):
    import io

    import pandas as pd

    client, air = istemci
    import ai_hub.inference_human_kidney_rna.inference_human_kidney_rna as ihr

    class _P:
        expected_cols = 5
        classes = ["other", "KIRC"]

        def predict(self, df):
            return [{"patient_id": str(i), "prediction": "KIRC", "confidence": 0.9} for i in df.index]

    monkeypatch.setattr(air, "_get_or_load_model", lambda ad, yukleyici: _P())
    sentinel = [{"patient_id": "p0", "top_genes": [{"gene": "gene_1", "attribution": 0.5}]}]
    gelen: list = []  # TUR 2 (çürütücü bb, gömülü ikiz): XAI yüklenen TÜM hastalarla çağrılır
    monkeypatch.setattr(ihr, "xai_top_genler", lambda df, **k: gelen.append([str(i) for i in df.index]) or sentinel)

    def _csv(n_hasta):
        df = pd.DataFrame(np.ones((n_hasta, 5)), index=[f"p{i}" for i in range(n_hasta)], columns=list("abcde"))
        buf = io.BytesIO()
        df.to_csv(buf)
        return base64.b64encode(buf.getvalue()).decode()

    r = client.post("/api/ai/rna/kidney", data={"csv_base64": _csv(3), "explain": "true"})
    assert r.status_code == 200, r.text
    assert r.json().get("xai") == sentinel, "explain=true iken RNA yanıtı xai taşımıyor"
    assert gelen == [["p0", "p1", "p2"]], f"RNA XAI yüklenen hastaların TAMAMIYLA çağrılmıyor: {gelen}"

    # N sınırı: 26 hasta → IG maliyet patlaması engellenir, analiz YİNE döner.
    r2 = client.post("/api/ai/rna/kidney", data={"csv_base64": _csv(26), "explain": "true"})
    assert r2.status_code == 200
    b2 = r2.json()
    assert "xai" not in b2 and b2.get("xai_error"), "N>25 sınırı uygulanmadı (60MB CSV'de IG patlar)"

    r3 = client.post("/api/ai/rna/kidney", data={"csv_base64": _csv(3)})
    assert r3.status_code == 200 and "xai" not in r3.json() and "xai_error" not in r3.json()


def test_KRITIK_rna_xai_hatasi_analizi_DUSURMEZ(istemci, monkeypatch):
    import io

    import pandas as pd

    client, air = istemci
    import ai_hub.inference_human_kidney_rna.inference_human_kidney_rna as ihr

    class _P:
        expected_cols = 5
        classes = ["other", "KIRC"]

        def predict(self, df):
            return [{"patient_id": "p0", "prediction": "other", "confidence": 0.7}]

    monkeypatch.setattr(air, "_get_or_load_model", lambda ad, yukleyici: _P())

    def _patla(*a, **k):
        raise RuntimeError("captum patladı (test)")

    monkeypatch.setattr(ihr, "xai_top_genler", _patla)
    df = pd.DataFrame(np.ones((1, 5)), index=["p0"], columns=list("abcde"))
    buf = io.BytesIO()
    df.to_csv(buf)
    b64 = base64.b64encode(buf.getvalue()).decode()
    r = client.post("/api/ai/rna/kidney", data={"csv_base64": b64, "explain": "true"})
    assert r.status_code == 200, f"XAI hatası RNA analizini düşürdü: {r.text}"
    body = r.json()
    assert body.get("predictions") and body.get("xai_error") and "xai" not in body


# ── 3b) ai_service IN-PROCESS smoke (gerçek PT, CPU) ─────────────────────────
# Docker bu makinede yok → cu128 İMAJ smoke'u GPU makinesinde (scripts/ai_service_xai_smoke.ps1).
# Burada imaj-DIŞI ama GERÇEK handler+PT yolu doğrulanır: /infer/thermal explain=true uçtan uca.
@yolo_pt_gerekir
def test_KRITIK_ai_service_inprocess_thermal_explain_SMOKE(tmp_path):
    import cv2

    import ai_service.app as sapp

    sc = TestClient(sapp.app)
    yy, xx = np.mgrid[0:224, 0:224].astype(np.float32)
    sicak = np.exp(-(((yy - 112) ** 2 + (xx - 112) ** 2) / (2 * 40.0**2)))
    # SG.G4: termal uç termal kamera görüntüsüne benzemeyen girdiyi 422'ler (palet uyumu) → sıcak leke GERÇEK bir termal paletle.
    img = cv2.applyColorMap((sicak * 255).astype(np.uint8), cv2.COLORMAP_INFERNO)
    ok, buf = cv2.imencode(".jpg", img)
    r = sc.post(
        "/infer/thermal",
        files={"file": ("t.jpg", buf.tobytes(), "image/jpeg")},
        data={"explain": "true"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("status") == "success"
    assert body.get("xai_image_base64"), f"servis explain yolu ısı haritası dönmedi: {list(body)}"
    _b64_gorsel(body["xai_image_base64"])


# ── 4) parite ────────────────────────────────────────────────────────────────
#: (:8100 uç yolu, XAI işlevi, yanıtta XAI çıktısını taşıyan alan)
_KUYRUK_UCLARI = [
    ("/infer/reticulocytes", "xai_retikulosit_isi_haritasi", "xai_image_base64"),
    ("/infer/kidney_ct", "xai_ct_isi_haritasi", "xai_image_base64"),
    ("/infer/rna", "xai_top_genler", "xai"),
]


def _ai_service_ucu(agac: ast.Module, yol: str) -> ast.FunctionDef:
    for f in agac.body:
        if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dek in f.decorator_list:
                if isinstance(dek, ast.Call) and dek.args and getattr(dek.args[0], "value", None) == yol:
                    return f
    raise AssertionError(f"ai_service {yol} ucu bulunamadı (çıpa kaymış)")


def test_YAPISAL_ai_service_kuyruk_XAI_paritesi():
    """:8100 kuyruk uçları XAI işlevini GERÇEKTEN çağırır ve sonucu (ya da `xai_error`u) yanıta yazar.

    ⚠️ D5.57 (B-10.170): eskiden uç başlığından sonraki 4500 KARAKTERDE işlev ADI ve "explain" aranıyordu — ad ucun DOCSTRING'inde de
    geçtiği için ("TEK-KAYNAK xai_ct_isi_haritasi") çağrı yorumlansa / silinse de YEŞİLDİ (ölçüldü, HEAD d38b0db5: CT çağrısı yerine
    boş sözlük → 219 passed). Artık AST (yorum / docstring görünmez): uç gövdesinde işleve bir `Call` VE `yanit[<alan>]` ile
    `yanit["xai_error"]` atamaları var. Değer akışı: `test_KRITIK_D557_ai_service_kuyruk_explain_YANITA_girer`."""
    agac = ast.parse((KOK / "ai_service" / "app.py").read_text(encoding="utf-8"))
    for yol, fn, alan in _KUYRUK_UCLARI:
        f = _ai_service_ucu(agac, yol)
        cagrilar = [
            c
            for c in ast.walk(f)
            if isinstance(c, ast.Call)
            and (
                (isinstance(c.func, ast.Attribute) and c.func.attr == fn)
                or (isinstance(c.func, ast.Name) and c.func.id == fn)
            )
        ]
        assert cagrilar, f":8100 {yol} {fn} ÇAĞRILMIYOR (yalnız yorum / docstring'de) — XAI paritesi yok"
        atamalar = {
            h.slice.value
            for a in ast.walk(f)
            if isinstance(a, ast.Assign)
            for h in a.targets
            if isinstance(h, ast.Subscript)
            and isinstance(h.value, ast.Name)
            and h.value.id == "yanit"
            and isinstance(h.slice, ast.Constant)
        }
        assert {alan, "xai_error"} <= atamalar, (
            f":8100 {yol} yanıta `{alan}` / `xai_error` yazmıyor: {sorted(atamalar)}"
        )


@pytest.mark.parametrize("yol,fn,alan", _KUYRUK_UCLARI)
def test_KRITIK_D557_ai_service_kuyruk_explain_YANITA_girer(monkeypatch, yol, fn, alan):
    """D5.57 (B-10.170): GERÇEK :8100 ucu (süreç içi TestClient, port YOK) + sahte model; explain=true → yanıtta XAI işlevinin
    çıktısı AYNEN; açıklama patlarsa `xai_error` + analiz yine 200 (açıklama ikincil). onnxruntime ÇALIŞMA-ZAMANI bağımlılığıdır
    (requirements.txt + requirements-test.txt; `ai_service.app` modül düzeyinde içe aktarır) — atlama YOK.
    MUTASYON: `yanit["xai"] = …` → `pass`; CT çağrısı yerine boş sözlük; retikülosit yanıt ataması yoruma → KIRMIZI."""
    import io

    import cv2
    import pandas as pd

    import ai_service.app as sapp

    monkeypatch.delenv("PEMF_AI_DOMAIN_GUARD", raising=False)
    monkeypatch.setattr(sapp, "_kapi", lambda *a, **k: None)  # modalite kapısı bu kapının konusu değil
    client = TestClient(sapp.app)

    class _Sahte:
        expected_cols = 5
        classes = ["other", "KIRC"]

        def predict(self, *a, **k):
            if a and isinstance(a[0], pd.DataFrame):
                return [{"patient_id": str(i), "prediction": "KIRC", "confidence": 0.9} for i in a[0].index]
            return {"n_detections": 0, "class_counts": {}, "detections": []}

        def draw_overlay(self, *a, **k):
            return np.zeros((32, 32, 3), dtype=np.uint8)

    class _SahteYolo:
        def predict(self, **k):
            class _R:
                boxes = None

                def plot(self):
                    return np.zeros((32, 32, 3), dtype=np.uint8)

            return [_R()]

    monkeypatch.setattr(sapp.predictors, "get", lambda ad: _SahteYolo() if ad == "reticulocytes" else _Sahte())
    if yol == "/infer/rna":
        import ai_hub.inference_human_kidney_rna.inference_human_kidney_rna as mod

        df = pd.DataFrame(
            np.round(np.random.default_rng(557).random((2, 5)) * 100, 3), index=["p0", "p1"], columns=list("abcde")
        )
        buf = io.BytesIO()
        df.to_csv(buf)
        dosya = ("r.csv", buf.getvalue(), "text/csv")
        sentinel = [{"patient_id": "p0", "top_genes": [{"gene": "a", "attribution": 0.5}]}]
        # TUR 2 (çürütücü bb): XAI YÜKLENEN tablonun TAMAMIYLA (iki hasta, aynı değerler) çağrılmalı
        yuklenen = ("tablo", ["p0", "p1"], df.to_numpy().tolist())
    else:
        if yol == "/infer/reticulocytes":
            import ai_hub.feline_reticulocytes.inference_feline_reticulocytes as mod
        else:
            import ai_hub.inference_human_kidney_ct.inference_human_kidney_ct as mod
        ok, jpg = cv2.imencode(".jpg", (np.random.default_rng(5).random((64, 64, 3)) * 255).astype(np.uint8))
        assert ok, "aparat: JPEG kodlanamadı"
        dosya = ("g.jpg", jpg.tobytes(), "image/jpeg")
        sentinel = {"xai_image_base64": "RDU1Nw==", "method": "hirescam"}
        # TUR 2 (çürütücü bb): XAI işlevine verilen yol, çağrı anında YÜKLENEN baytları taşır (başka kare / boş dosya değil)
        yuklenen = ("dosya", jpg.tobytes())
    cagri: list = []

    def _kaydeden(*a, **k):
        arg = a[0] if a else next(iter(k.values()), None)
        if isinstance(arg, pd.DataFrame):
            cagri.append(("tablo", [str(i) for i in arg.index], np.round(arg.to_numpy(dtype=float), 3).tolist()))
        else:
            cagri.append(("dosya", Path(arg).read_bytes() if arg and Path(str(arg)).is_file() else None))
        return sentinel

    monkeypatch.setattr(mod, fn, _kaydeden)
    r = client.post(yol, files={"file": dosya}, data={"explain": "true"})
    assert r.status_code == 200, f"{yol}: {r.status_code} {r.text[:200]}"
    beklenen = sentinel if alan == "xai" else sentinel["xai_image_base64"]
    assert cagri and r.json().get(alan) == beklenen, (
        f":8100 {yol} explain=true yanıtında XAI çıktısı (`{alan}`) yok / farklı: {sorted(r.json())}"
    )
    assert cagri == [yuklenen], (
        f":8100 {yol}: XAI YÜKLENEN veriyle çağrılmıyor (açıklama başka girdiye ait): "
        f"{[(c[0], c[1] if c[0] == 'tablo' else (len(c[1]) if c[1] else None)) for c in cagri]}"
    )
    r0 = client.post(yol, files={"file": dosya})
    assert r0.status_code == 200 and alan not in r0.json() and "xai_error" not in r0.json(), (
        f"KARŞIT: explain istenmeden XAI üretildi ya da hata yazıldı ({yol})"
    )

    def _patla(*a, **k):
        raise RuntimeError("D557 XAI SIMULE ARIZA")

    monkeypatch.setattr(mod, fn, _patla)
    r2 = client.post(yol, files={"file": dosya}, data={"explain": "true"})
    assert r2.status_code == 200 and r2.json().get("xai_error") and alan not in r2.json(), (
        f":8100 {yol}: XAI hatası analizi düşürdü ya da xai_error yok: {r2.status_code} {r2.text[:200]}"
    )
