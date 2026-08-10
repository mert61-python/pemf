# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""MODEL ESERİ SÜRÜM SAPMASI — sessiz "invalid results" riski (2026-08-09 denetimi, Tier 3).

ARIZA: `requirements.txt` `scikit-learn==1.7.2` sabitliyor, ama sahaya çıkan ön-işleyicilerin
çoğu **1.8.0** ile serileştirilmiş (birkaçı 1.6.1). sklearn her yüklemede

    InconsistentVersionWarning: Trying to unpickle estimator StandardScaler from version
    1.8.0 when using version 1.7.2. This might lead to breaking code or INVALID RESULTS.

diyor; hiçbir şey bu uyarıyı toplamıyor, test süiti yeşil kalıyor. En ağırı
`inference_human_kidney_disease/preprocessor.pkl` — SimpleImputer + StandardScaler +
OneHotEncoder + ColumnTransformer'dan oluşan **tam bir boru hattı**; ölçeklemede sessiz bir
kayma teşhis olasılığını doğrudan kaydırır.

NEDEN HATA DEĞİL DE RATCHET: bugün 13 eser uyuşmazlıkta. Uyarıyı sert hataya çevirmek AI
teşhisini ANINDA kapatır — hasta masadayken. Bunun yerine:
  1) mevcut durum burada AÇIKÇA yazılı (baseline),
  2) YENİ bir uyuşmazlık girerse veya bilinen bir eserin sürümü değişirse test KIRILIR,
  3) `tests/test_ai_golden_values.py` sayıların gerçekten kaymadığını kanıtlar.

Kalıcı çözüm (sahibin kararı): eserleri sabitlenmiş sürümle yeniden serileştir, sonra bu
dosyadaki baseline'ı boşalt ve `TOLERE_EDILEN_SAPMA = False` yap.

Bu test AĞIR bağımlılık İSTEMEZ — pickle baytlarını okur, sklearn'i import etmez.
"""

import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]

# `requirements.txt` içindeki sabit. Değişirse baseline yeniden ölçülmelidir.
BEKLENEN_RUNTIME_SKLEARN = "1.7.2"

# Uyuşmazlığa şimdilik izin veriliyor mu? Eserler yeniden serileştirildiğinde False yapın.
TOLERE_EDILEN_SAPMA = True

# ── BASELINE ────────────────────────────────────────────────────────────────
# `ai_hub/` altındaki (canlı çıkarım ağacı) her .pkl için serileştirme sürümü.
# "-" = pickle'da `_sklearn_version` alanı yok (ör. XGBoost native booster) → sapma konusu değil.
BASELINE = {
    "cat_disease/XGBoost.pkl": "-",
    "cat_disease/label_encoder.pkl": "1.7.2",
    "cat_disease/scaler_X.pkl": "1.7.2",
    "em_kedi/scaler_X.pkl": "1.8.0",
    "em_kedi/scaler_extra.pkl": "1.8.0",
    "em_kedi/scaler_y.pkl": "1.8.0",
    "inference_em_fantom/scaler_X.pkl": "1.8.0",
    "inference_em_fantom/scaler_extra.pkl": "1.8.0",
    "inference_em_fantom/scaler_y.pkl": "1.8.0",
    "inference_em_petri/scaler_X.pkl": "1.8.0",
    "inference_em_petri/scaler_extra.pkl": "1.8.0",
    "inference_em_petri/scaler_y.pkl": "1.8.0",
    "inference_human_kidney_disease/preprocessor.pkl": "1.8.0",
    "inference_human_kidney_rna/scaler.pkl": "1.8.0",
}

SURUM_DESENI = re.compile(rb"(\d+\.\d+(?:\.\d+)?)")


def serilestirme_surumu(p: Path) -> str:
    """Pickle içindeki `_sklearn_version` değerini BAYTTAN oku (yükleme YOK — güvenli)."""
    raw = p.read_bytes()
    i = raw.find(b"_sklearn_version")
    if i < 0:
        return "-"
    m = SURUM_DESENI.search(raw[i : i + 80])
    return m.group(1).decode() if m else "?"


def _eserler() -> dict:
    kok = KOK / "ai_hub"
    if not kok.is_dir():
        return {}
    return {p.relative_to(kok).as_posix(): p for p in sorted(kok.rglob("*.pkl"))}


@pytest.fixture(scope="module")
def olculen():
    e = _eserler()
    if not e:
        pytest.skip("ai_hub/ yok (model eserleri kurulu degil)")
    return {ad: serilestirme_surumu(p) for ad, p in e.items()}


# ── ratchet ─────────────────────────────────────────────────────────────────


def test_KRITIK_YENI_surum_uyusmazligi_GIREMEZ(olculen):
    """Asıl kapı: baseline'da olmayan bir uyuşmazlık = biri modeli farklı ortamda yeniden
    üretti ve kimse fark etmedi."""
    yeni = {ad: s for ad, s in olculen.items() if s not in ("-", BEKLENEN_RUNTIME_SKLEARN) and ad not in BASELINE}
    assert not yeni, (
        "BASELINE'da olmayan surum uyusmazligi: "
        + repr(yeni)
        + f"\nRuntime sklearn={BEKLENEN_RUNTIME_SKLEARN}. Eser baska bir ortamda uretilmis; "
        "sayilarin kaymadigini test_ai_golden_values.py ile KANITLA, sonra BASELINE'a ekle."
    )


def test_bilinen_eserin_surumu_DEGISMEZ(olculen):
    """Baseline'daki bir eser sessizce yenilenirse (ör. yeniden eğitim) haber ver."""
    degisen = {ad: (BASELINE[ad], s) for ad, s in olculen.items() if ad in BASELINE and BASELINE[ad] != s}
    assert not degisen, (
        "eser surumu degismis (beklenen, olculen): "
        + repr(degisen)
        + "\nModel yenilendiyse ALTIN DEGERLERI de yeniden olc — sessizce kaymis olabilir."
    )


def test_baselinedaki_eser_KAYBOLMAZ(olculen):
    """Eser silinirse ya da yeniden adlandırılırsa çıkarım çalışma anında patlar; burada yakala."""
    kayip = sorted(set(BASELINE) - set(olculen))
    # release_assets tek-kaynak olduğu için geliştirici ağacında bazıları bulunmayabilir;
    # yalnız ai_hub/ ağacı hiç yoksa skip edilir (fixture). Buradaki kayıp gerçek kayıptır.
    assert not kayip, f"BASELINE'da olup diskte olmayan eser: {kayip}"


def test_runtime_sklearn_sabiti_baseline_ile_TUTARLI():
    """`requirements.txt` sabiti değişirse tüm baseline geçersizdir — sessizce geçmesin."""
    req = (KOK / "requirements.txt").read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^scikit-learn==([\d.]+)", req, re.M)
    assert m, "requirements.txt icinde scikit-learn sabiti bulunamadi"
    assert m.group(1) == BEKLENEN_RUNTIME_SKLEARN, (
        f"scikit-learn sabiti {m.group(1)} oldu ama bu dosya {BEKLENEN_RUNTIME_SKLEARN} varsayiyor. "
        "Surum yukseltildiyse BASELINE + ALTIN DEGERLER yeniden olculmeli."
    )


def test_sapma_hala_TOLERE_ediliyorsa_gerekce_belgeli(olculen):
    """`TOLERE_EDILEN_SAPMA = False` yapıldığında bu test, kalan her uyuşmazlığı KIRAR —
    yani eserler yeniden serileştirilene kadar bayrak açılamaz. Kapatma anahtarı budur."""
    uyusmaz = {ad: s for ad, s in olculen.items() if s not in ("-", "?", BEKLENEN_RUNTIME_SKLEARN)}
    if TOLERE_EDILEN_SAPMA:
        assert uyusmaz, (
            "hic uyusmazlik kalmamis ama TOLERE_EDILEN_SAPMA hala True — bayragi False yapin, kapi kalicilassin."
        )
        return
    assert not uyusmaz, "TOLERE_EDILEN_SAPMA=False ama hala uyusmayan eser var: " + repr(uyusmaz)
