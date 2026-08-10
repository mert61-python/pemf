# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AI ALTIN DEĞER TESTLERİ — "invalid results" sessizce olamaz (2026-08-09 denetimi, Tier 3).

ARIZA: üretim ön-işleyicileri (StandardScaler / SimpleImputer / OneHotEncoder /
ColumnTransformer) **sklearn 1.8.0** ile serileştirilmiş; `requirements.txt` runtime'ı
**1.7.2** sabitliyor. sklearn her yüklemede

    "This might lead to breaking code or INVALID RESULTS"

diyor. Buna karşı tek savunma "sayılar hâlâ aynı mı" sorusunu soran bir testtir; yoksa
ölçeklemede yarım standart sapmalık bir kayma teşhisi kaydırır ve süit yeşil kalır.

KAPSAM: sapmalı bir sklearn eseri kullanan ve API'den erişilebilen 5 tahminci —
CKD (ColumnTransformer boru hattı), em_fantom, em_petri, em_kedi, RNA.

TOLERANS: sınıf/etiket ve sıralama TAM eşleşmeli. Sayılarda `rel=1e-4` — ONNX Runtime
sürümleri arası float32 gürültüsü ~1e-6'dır, ölçekleme kayması ise 1e-1 mertebesinde;
eşik ikisini rahatça ayırır.

ATLAMA: `.onnx` ağırlıkları depoda YOK (`.gitignore`), 2,1 GB'lık tek kaynak
`release_assets/ai_models`. Eser yoksa test atlanır — AMA `PEMF_GOLDEN_REQUIRED=1` ile
atlama YASAKLANIR; yayın makinesi bunu ayarlayarak sessiz atlamayı imkânsız kılar.
"""

import json
import os
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
ALTIN = json.loads((KOK / "tests" / "golden" / "ai_golden_values.json").read_text(encoding="utf-8"))

# ⚠️ `ai_hub`i sys.path'e EKLEMEYİN — `inference_em_petri` adını pakete çözer ve
# `test_petri_plausibility.py`nin 11 testini kırar (bkz. tests/golden/yukleyici.py).
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "tests"))  # `tests` paket değil (conftest tabanlı toplama)
from golden import girdiler as G  # noqa: E402
from golden import yukleyici as Y  # noqa: E402

REL = 1e-4
ZORUNLU = os.environ.get("PEMF_GOLDEN_REQUIRED") == "1"


def _atla(sebep: str):
    """Eser yoksa atla — ama yayın makinesinde atlamak YASAK."""
    if ZORUNLU:
        pytest.fail(f"PEMF_GOLDEN_REQUIRED=1 ama altin deger testi kosulamiyor: {sebep}")
    pytest.skip(sebep)


def _yukle(kur, sebep: str):
    try:
        return kur()
    except Exception as e:  # eser/bağımlılık yok
        _atla(f"{sebep} ({type(e).__name__}: {str(e)[:120]})")


def _karsilastir(olculen: dict, beklenen: dict, etiket: str):
    """Her alanı tek tek karşılaştır; hangi alanın kaydığını mesajda söyle."""
    eksik = sorted(set(beklenen) - set(olculen))
    assert not eksik, f"{etiket}: cikti alanlari kayboldu: {eksik}"
    for k, bek in beklenen.items():
        gel = olculen[k]
        if isinstance(bek, str):
            assert gel == bek, f"{etiket}.{k}: SINIF DEGISTI {gel!r} != {bek!r}"
        else:
            assert gel == pytest.approx(bek, rel=REL, abs=1e-9), (
                f"{etiket}.{k}: {gel!r} != {bek!r} (rel={REL}) — on-isleyici kaymis olabilir"
            )


# ── CKD: en karmaşık sapma (SimpleImputer+StandardScaler+OneHotEncoder+ColumnTransformer) ──


@pytest.fixture(scope="module")
def ckd():
    def kur():
        m = Y.ckd_modulu()
        m.load_model()  # eser gerçekten var mı — burada patlasın
        return m

    return _yukle(kur, "CKD eserleri yok")


@pytest.mark.parametrize("durum", ["hasta", "saglikli", "eksik"])
def test_KRITIK_CKD_altin_degerleri(ckd, durum):
    girdi = {"hasta": G.CKD_HASTA, "saglikli": G.CKD_SAGLIKLI, "eksik": G.CKD_EKSIK}[durum]
    _karsilastir(ckd.predict_one(girdi), ALTIN["ckd"][durum], f"ckd[{durum}]")


def test_KRITIK_CKD_eksik_alan_yolu_IMPUTER_calistirir(ckd):
    """Eksik alanlı örnek, ölçekleme sapmasının en çok ısırdığı yolu (impute→ölçek) zorlar.
    Bu örnek altın değerden saparsa ColumnTransformer boru hattı gerçekten kaymış demektir."""
    a = ckd.predict_one(G.CKD_HASTA)["prob_ckd"]
    b = ckd.predict_one(G.CKD_EKSIK)["prob_ckd"]
    assert a != b, "eksik alan hicbir sey degistirmedi — imputer yolu hic calismamis olabilir"


# ── EM tahmincileri ─────────────────────────────────────────────────────────


@pytest.fixture(scope="module", params=sorted(Y.EM_TAHMINCILER), ids=lambda a: a)
def em(request):
    ad = request.param
    return ad, _yukle(lambda: Y.em_tahminci(ad), f"{ad} eserleri yok")


@pytest.mark.parametrize("nokta", ["orta", "kose"])
def test_KRITIK_EM_altin_degerleri(em, nokta):
    ad, p = em
    girdi = G.EM_ORTA if nokta == "orta" else G.EM_KOSE
    _karsilastir(p.predict(**girdi), ALTIN[ad][nokta], f"{ad}[{nokta}]")


# ── RNA ─────────────────────────────────────────────────────────────────────


def test_KRITIK_RNA_altin_degerleri():
    csv = KOK / G.RNA_CSV
    if not csv.exists():
        _atla("RNA test CSV'si yok")

    def kur():
        import pandas as pd

        return Y.rna_tahminci(), pd

    tahminci, pd = _yukle(kur, "RNA eserleri yok")

    df = pd.read_csv(csv, index_col=0)
    olculen = tahminci.predict(df)
    beklenen = ALTIN["rna"]["csv"]
    assert len(olculen) == len(beklenen), f"RNA hasta sayisi degisti: {len(olculen)} != {len(beklenen)}"
    for i, (o, b) in enumerate(zip(olculen, beklenen)):
        _karsilastir(o, b, f"rna[{i}]")


# ── kapı: altın dosyası ile ölçüm script'i AYNI girdileri kullanmalı ────────


def test_KRITIK_yukleyici_sys_pathi_KIRLETMEZ():
    """REGRESYON (2026-08-10): bu dosya bir ara `ai_hub`i `sys.path`e ekliyordu; bu,
    `inference_em_petri` adını modül dosyası yerine PAKETE çözüyor ve
    `test_petri_plausibility.py`nin 11 testini kırıyordu — ama YALNIZ iki dosya aynı oturumda
    koştuğunda. Tek dosya çalıştıran biri bunu asla göremez; kapı burada durmalı."""
    assert str(KOK / "ai_hub") not in sys.path, (
        "ai_hub sys.path'e eklenmis — em_petri ad cakismasi baska testleri kirar (bkz. tests/golden/yukleyici.py)"
    )
    paket = sys.modules.get("inference_em_petri")
    assert paket is None or getattr(paket, "PetriPredictor", None) is not None, (
        "`inference_em_petri` adi PetriPredictor'i OLMAYAN pakete cozulmus — "
        "petri_cv/pipeline.py bu adi modul dosyasi sanar ve patlar"
    )


def test_altin_dosyasi_olcum_ortamini_KAYDEDIYOR():
    """Değerler hangi sürümlerle ölçüldüğü yazılı değilse, bir kırılmayı teşhis etmek imkânsız."""
    ort = ALTIN.get("_olcum_ortami", {})
    for alan in ("sklearn", "numpy", "python"):
        assert ort.get(alan), f"altin dosyasinda olcum ortami eksik: {alan}"


def test_altin_dosyasi_TUM_tahmincileri_kapsiyor():
    """Sapmalı eser kullanan bir tahminci altın dosyasına eklenmeden eklenirse, korumasız kalır.
    `test_model_artifact_drift.BASELINE` ile çapraz kontrol."""
    from test_model_artifact_drift import BASELINE, BEKLENEN_RUNTIME_SKLEARN

    # sapmalı eseri olan dizinler → tahminci adı
    dizin_tahminci = {
        "em_kedi": "em_kedi",
        "inference_em_fantom": "em_fantom",
        "inference_em_petri": "em_petri",
        "inference_human_kidney_disease": "ckd",
        "inference_human_kidney_rna": "rna",
    }
    sapmali_dizinler = {ad.split("/")[0] for ad, s in BASELINE.items() if s not in ("-", BEKLENEN_RUNTIME_SKLEARN)}
    beklenen = {dizin_tahminci[d] for d in sapmali_dizinler if d in dizin_tahminci}
    kapsanmayan = sorted(beklenen - set(ALTIN))
    assert not kapsanmayan, (
        f"sapmali eser kullanan ama altin degeri OLMAYAN tahminci: {kapsanmayan} — "
        "tests/golden/olc_altin_degerler.py ile olcup ekleyin."
    )
    bilinmeyen = sorted(sapmali_dizinler - set(dizin_tahminci))
    assert not bilinmeyen, (
        f"sapmali eseri olan ama bu haritada olmayan dizin: {bilinmeyen} — "
        "yeni bir tahminci eklenmis; altin degerini olcup dizin_tahminci'ye ekleyin."
    )
