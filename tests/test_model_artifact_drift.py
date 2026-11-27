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

import json
import re
import subprocess
from pathlib import Path

import capraz
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
        capraz.atla("ai_hub/ altında *.pkl model eseri yok (model eserleri kurulu değil)")  # D5-F: eski düz pytest.skip
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


def _izlenen_eserler():
    """`ai_hub` altında git'te İZLENEN .pkl eserleri. Temiz bir checkout'ta bunlar MUTLAKA
    bulunur; yoksa gerçekten kaybolmuşlardır. git yoksa/çalışmazsa None."""
    try:
        r = subprocess.run(
            ["git", "ls-files", "ai_hub/**/*.pkl"],
            cwd=str(KOK),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception:
        return None
    if r.returncode != 0:
        return None
    on = "ai_hub/"
    return {s[len(on) :] for s in r.stdout.split() if s.startswith(on) and s.endswith(".pkl")}


def test_baselinedaki_eser_KAYBOLMAZ(olculen):
    """Eser silinirse ya da yeniden adlandırılırsa çıkarım çalışma anında patlar; burada yakala.

    ⚠️ 2026-08-12: bu test CI'da düşüyordu. Sebep eser kaybı DEĞİL — BASELINE'ın 14 eserinden
    yalnız 9'u depoda izlenir; kalanlar tek-kaynak `release_assets/ai_models`tedir (2,1 GB,
    `.gitignore`). Temiz checkout'ta o 5'i hiç var olmaz, dolayısıyla "kayıp" sanılıyordu.
    Fixture yalnız `ai_hub/` ağacının TAMAMEN yokluğunu atlıyor, bu ara durumu görmüyordu.

    Doğru çizgi: İZLENEN eser her ortamda bulunmak ZORUNDA (kaybı her zaman hata). İzlenmeyen
    eser ise ancak model seti kuruluyken beklenir — kurulu olup olmadığı, izlenmeyenlerden
    HERHANGİ birinin diskte bulunmasıyla anlaşılır. Böylece kısmi kayıp (biri var, öteki
    silinmiş) geliştirici/yayın makinesinde hâlâ yakalanır; CI ise izlenen 9 eseri korumaya
    devam eder — koruma kalkmaz, yalnız ortamda var olamayacak dosyalar beklenmez.
    """
    mevcut = set(olculen)
    beklenen = beklenen_eserler(set(BASELINE), _izlenen_eserler(), mevcut, _ci_paketi_eserleri())
    kayip = sorted(beklenen - mevcut)
    assert not kayip, f"BASELINE'da olup diskte olmayan eser: {kayip}"


def _ci_paketi_eserleri() -> set:
    """CI model paketinin (E13, `scripts/ci_modelleri_listesi.json`) depo ağacına koyduğu `ai_hub/**/*.pkl` eserleri (ai_hub göreli)."""
    veri = json.loads((KOK / "scripts" / "ci_modelleri_listesi.json").read_text(encoding="utf-8"))
    on = "depo/ai_hub/"
    return {d["yol"][len(on) :] for d in veri["dosyalar"] if d["yol"].startswith(on) and d["yol"].endswith(".pkl")}


def beklenen_eserler(baseline: set, izlenen, mevcut: set, ci_paketi: set) -> set:
    """Diskte BULUNMASI gereken BASELINE eserleri.

    ⚠️ KP-6 (2026-11-16, CI-eşdeğeri ölçümü): E13 CI model paketi izlenmeyen `inference_human_kidney_rna/scaler.pkl`i depo
    ağacına koyar. Eski kural ("izlenmeyenlerden HERHANGİ biri varsa tam model seti kurulu") bunu tam set sandı ve CI'da
    paketle birlikte em_petri ×3 + kidney_disease ölçekleyicilerini bekleyip KIRMIZI verdi (CI anahtarı eklendiği gün CI düşerdi).
    Doğru çizgi: tam set, CI paketinde OLMAYAN bir izlenmeyen eserle anlaşılır; CI paketinin eserleri ise biri varsa HEPSİ
    beklenir (paket kısmi yerleşemez). İzlenen eser her ortamda zorunlu; git yoksa (izlenen None) tam BASELINE."""
    if izlenen is None:
        return set(baseline)  # git yok → eski (tam) davranışa dön
    izlenmeyen = baseline - izlenen
    ci = ci_paketi & izlenmeyen
    if (izlenmeyen - ci) & mevcut:
        return set(baseline)
    return (baseline & izlenen) | (ci if ci & mevcut else set())


def test_KP6_ci_paketi_eserleri_BASELINEin_izlenmeyen_eserleri():
    """Listedeki `.pkl` eserleri BASELINE'da olmalı (olmayan bir ad `beklenen_eserler`de sessizce etkisiz kalırdı)."""
    ci = _ci_paketi_eserleri()
    # CT1 b (istem 66): paket genişledi — modül yanı izlenmeyen BÜTÜN .pkl eserleri (em_petri ×3 + kidney_disease + kidney_rna)
    assert ci == {
        "inference_human_kidney_rna/scaler.pkl",
        "inference_em_petri/scaler_X.pkl",
        "inference_em_petri/scaler_extra.pkl",
        "inference_em_petri/scaler_y.pkl",
        "inference_human_kidney_disease/preprocessor.pkl",
    }, ci
    assert ci <= set(BASELINE)


_B = {"a_izli.pkl", "b_izli.pkl", "c_petri.pkl", "d_ckd.pkl", "e_ci.pkl"}
_IZ = {"a_izli.pkl", "b_izli.pkl"}
_CI = {"e_ci.pkl"}


@pytest.mark.parametrize(
    "mevcut,kayip",
    [
        # CI paketiyle (E13): izlenen + paket eseri var → tam set SANILMAZ, kayıp YOK (KP-6 öncesi c, d "kayıp" sayılıyordu)
        ({"a_izli.pkl", "b_izli.pkl", "e_ci.pkl"}, set()),
        # temiz CI (paketsiz): yalnız izlenenler beklenir
        ({"a_izli.pkl", "b_izli.pkl"}, set()),
        # izlenen eser kaybı HER ortamda yakalanır (paketli de)
        ({"a_izli.pkl", "e_ci.pkl"}, {"b_izli.pkl"}),
        ({"a_izli.pkl"}, {"b_izli.pkl"}),
        # geliştirici / yayın makinesi: tam set kurulu, kısmi kayıp YAKALANIR (paket eseri dahil)
        ({"a_izli.pkl", "b_izli.pkl", "c_petri.pkl", "e_ci.pkl"}, {"d_ckd.pkl"}),
        ({"a_izli.pkl", "b_izli.pkl", "c_petri.pkl", "d_ckd.pkl"}, {"e_ci.pkl"}),
        ({"a_izli.pkl", "b_izli.pkl", "c_petri.pkl", "d_ckd.pkl", "e_ci.pkl"}, set()),
    ],
)
def test_KP6_beklenen_eserler_karari(mevcut, kayip):
    assert beklenen_eserler(_B, _IZ, mevcut, _CI) - mevcut == kayip


def test_KP6_beklenen_eserler_git_yoksa_TAM_baseline():
    assert beklenen_eserler(_B, None, set(), _CI) == _B


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
