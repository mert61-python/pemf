# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""CKD (böbrek hastalığı) — ASGARİ GİRDİ KURALI (2026-08-07, sahip bildirimi).

ARIZA: "Hiçbir veri girmeden analiz yaptığımda %78 çıkıyor." Tüm alanlar opsiyonel olduğu
için boş istek preprocessor tarafından impute ediliyor ve model eğitim setinin ÖN-OLASILIĞINI
döndürüyordu. Kullanıcı bunu hasta verisinden çıkmış bir teşhis sanıyor.

Aynı sınıf hata `/api/ai/disease` (kedi) ucunda daha önce kapatılmıştı; bu uç atlanmıştı.
"""

import os
from pathlib import Path

os.environ.pop("PEMF_SIMULATE", None)

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from servers import api_server

    return TestClient(api_server.app)


# ─────────────────────────────────────────────────────────────────────────────
# ÇIKARIM GEREKTİREN TESTLER (2026-08-12)
# ─────────────────────────────────────────────────────────────────────────────
# Bu dosyanın ASIL kapısı — yetersiz girdiyi 422 ile reddetmek — modelden ÖNCE, doğrulama
# katmanında çalışır ve her ortamda koşar. Ama "meşru kullanım engellenmemeli" testleri
# gerçekten çıkarım yapar; onlar için İKİ şey gerekir ve ikisi de CI'da YOKTUR:
#   • `onnxruntime` — `requirements-test.txt`e bilerek alınmadı (ağır AI bağımlılığı),
#   • `.onnx` ağırlıkları — `ai_hub/inference_human_kidney_disease/` altında yalnız KOD ve
#     metadata izlenir; ağırlıklar tek-kaynak `release_assets/ai_models`tedir (`.gitignore`).
# Bu yüzden CI'da uç 500 dönüyor ve 3 test düşüyordu (2026-08-12 teşhisi). Yalnız
# `onnxruntime` eklemek ÇÖZMEZDİ — ağırlık yine olmazdı; o yüzden bağımlılık eklenmedi.
#
# Konvansiyon `test_ai_golden_values.py` ile aynı: eser yoksa ATLA, ama `PEMF_GOLDEN_REQUIRED=1`
# ayarlıysa atlamak YASAK (yayın makinesi sessiz atlamayı imkânsız kılar).
_MODEL_DIZINI = Path(__file__).resolve().parents[1] / "ai_hub" / "inference_human_kidney_disease"


def _cikarim_neden_olmaz() -> str:
    try:
        import onnxruntime  # noqa: F401
    except Exception as e:
        return f"onnxruntime yok ({type(e).__name__})"
    if not any(_MODEL_DIZINI.glob("*.onnx")):
        return f"model ağırlıkları yok: {_MODEL_DIZINI.name}/*.onnx (release_assets tek-kaynak)"
    return ""


@pytest.fixture()
def cikarim_gerekir():
    """Gerçek çıkarım yapılamıyorsa testi atlar (yayın makinesinde düşürür)."""
    sebep = _cikarim_neden_olmaz()
    if not sebep:
        return
    if os.environ.get("PEMF_GOLDEN_REQUIRED") == "1":
        pytest.fail(f"PEMF_GOLDEN_REQUIRED=1 ama CKD çıkarımı koşulamıyor: {sebep}")
    pytest.skip(f"CKD çıkarımı koşulamıyor: {sebep}")


TAM = {
    "age": 48,
    "bp": 80,
    "sg": 1.02,
    "al": 1,
    "su": 0,
    "bgr": 121,
    "bu": 36,
    "sc": 1.2,
    "sod": 137,
    "pot": 4.4,
    "hemo": 15.4,
    "pcv": 44,
    "wc": 7800,
    "rc": 5.2,
    "rbc": "normal",
    "pc": "normal",
    "pcc": "notpresent",
    "ba": "notpresent",
    "htn": "yes",
    "dm": "no",
    "cad": "no",
    "appet": "good",
    "pe": "no",
    "ane": "no",
}


# ── ASIL ARIZA ──────────────────────────────────────────────────────────────
def test_BOS_istek_sonuc_URETMEZ(client):
    r = client.post("/api/ai/disease/kidney", json={})
    assert r.status_code == 422, f"boş formla sonuç üretildi: {r.text[:200]}"
    d = r.json().get("detail", "")
    assert "yeterli klinik veri yok" in d
    assert "yanıltıcı" in d, "kullanıcıya NEDEN reddedildiği açıklanmalı"


def test_bos_istekte_olasilik_DONMEZ(client):
    """Yanıt gövdesinde hiçbir olasılık sayısı olmamalı — kullanıcı %78 görmemeli."""
    r = client.post("/api/ai/disease/kidney", json={})
    assert "prob_ckd" not in r.text and "prob_pct" not in r.text


def test_COK_AZ_alanla_reddedilir(client):
    r = client.post("/api/ai/disease/kidney", json={"age": 48, "bp": 80})
    assert r.status_code == 422


def test_cekirdek_belirtec_YOKSA_reddedilir(client):
    """6 alan dolu ama hiçbiri böbrek işleviyle ilgili değil → tahminde renal sinyal yok."""
    r = client.post("/api/ai/disease/kidney", json={"age": 48, "bp": 80, "su": 0, "sod": 137, "pot": 4.4, "wc": 7800})
    assert r.status_code == 422
    assert "böbrek işlevine dair" in r.json().get("detail", "")


# ── MEŞRU KULLANIM ENGELLENMEMELİ ───────────────────────────────────────────
def test_TAM_form_calisir(client, cikarim_gerekir):
    r = client.post("/api/ai/disease/kidney", json=TAM)
    assert r.status_code == 200, r.text[:200]
    d = r.json()
    assert d["status"] == "success" and "prob_ckd" in d
    assert d["imputed_fields"] == 0
    assert d["low_evidence"] is False


def test_asgari_gecerli_form_calisir(client, cikarim_gerekir):
    """6 alan + çekirdek belirteç → geçmeli (model eksikleri zaten impute etmek üzere tasarlı)."""
    r = client.post("/api/ai/disease/kidney", json={"age": 60, "bp": 90, "sc": 3.1, "bu": 90, "hemo": 9.8, "al": 3})
    assert r.status_code == 200, r.text[:200]
    assert r.json()["filled_fields"] == 6


# ── ŞEFFAFLIK ───────────────────────────────────────────────────────────────
def test_AZ_veriyle_uretilen_sonuc_ISARETLENIR(client, cikarim_gerekir):
    """6/24 alanla üretilen tahmin, 24/24 ile aynı güvenle sunulmamalı."""
    r = client.post("/api/ai/disease/kidney", json={"age": 60, "bp": 90, "sc": 3.1, "bu": 90, "hemo": 9.8, "al": 3})
    d = r.json()
    assert d["low_evidence"] is True, "az veriyle üretilen sonuç işaretlenmedi"
    assert d["imputed_fields"] == 18


def test_bos_metin_dolu_SAYILMAZ(client):
    """'   ' gibi boş metinler alan doldurmuş sayılıp kuralı atlatmamalı."""
    r = client.post(
        "/api/ai/disease/kidney", json={"rbc": "  ", "pc": "  ", "pcc": " ", "ba": " ", "htn": " ", "dm": " "}
    )
    assert r.status_code == 422


def test_KATEGORIK_EKSIKKEN_impute_edilir_abnormal_SAYILMAZ(cikarim_gerekir):
    """B5 (denetim 2026-09-03, OLCULDU): `_normalise_record` eksik kategorigi `None` gecirince
    object-dtype `SimpleImputer(most_frequent)` onu EKSIK SAYMIYORDU (maske `X != X`), OHE
    (`drop='first', handle_unknown='ignore'`) tum-sifir = DUSURULEN kategori ('abnormal') kodluyordu
    → hicbir bulgu secmemis SAGLIKLI hasta %6 yerine %60 CKD aliyordu. Ayni kusur `float('nan')`
    (predict_batch / CSV yolu) icin de vardi: `str(nan).lower()`='nan' METNI → yine unknown.
    Artik eksik → np.nan → GERCEK impute (normal/notpresent/no/good) — acik-normal ile AYNI olasilik.
    MUTASYON: np.nan → None geri alinirsa UserWarning('Found unknown categories') + olasilik farki → KIRMIZI."""
    import warnings

    import pandas as pd

    from ai_hub.inference_human_kidney_disease.inference_human_kidney_disease import (
        ALL_FEATURES,
        predict_batch,
        predict_one,
    )

    sayisal = {"sg": 1.02, "al": 0, "su": 0, "bgr": 100, "bu": 30, "sc": 1.0, "hemo": 15.0, "pcv": 45}
    acik = {
        **sayisal,
        "rbc": "normal",
        "pc": "normal",
        "pcc": "notpresent",
        "ba": "notpresent",
        "htn": "no",
        "dm": "no",
        "cad": "no",
        "appet": "good",
        "pe": "no",
        "ane": "no",
    }
    ref = predict_one(acik)["prob_ckd"]
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)  # 'Found unknown categories' → test kirmizi
        eksik = predict_one(sayisal)  # kategorikler hic yok (None)
        nan_float = predict_one({**sayisal, "rbc": float("nan")})  # float NaN kategorik
        batch = predict_batch(pd.DataFrame([{**sayisal, "rbc": float("nan")}], columns=ALL_FEATURES))
    assert abs(eksik["prob_ckd"] - ref) < 1e-6, "eksik kategorik 'abnormal' gibi kodlandi (None impute edilmedi)"
    assert abs(nan_float["prob_ckd"] - ref) < 1e-6, "float NaN kategorik 'nan' METNI olarak gitti (impute edilmedi)"
    assert abs(float(batch["prob_ckd"].iloc[0]) - ref) < 1e-6, "predict_batch NaN kategorik impute edilmedi"
