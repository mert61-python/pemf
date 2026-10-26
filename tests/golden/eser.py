# -*- coding: utf-8 -*-
"""AI model eseri VAR mı — "dosya yok" ile "yükleme hatası"nı AYIRAN tek karar noktası (D3.03 · B-10.79/81/82, 2026-10-10).

🔴 ÖLÇÜLEN DURUM: AI altın değer / kedi XAI kapıları yüklemeyi `except Exception: skip` ile sarıyordu. Eser DİSKTEYKEN bile
yükleme hatası (CKD `load_model`'de AttributeError, `CatDiseasePredictor.__init__` istisnası, yanlış yol FileNotFoundError'u)
"eser yok" sayılıp ATLANIYORDU → sklearn/xgboost kayması modeli öldürse süit "atlandı" derdi. CKD asgari girdi testleri ise
ön-koşulu MODÜL dizininde arıyordu; ürün ağırlıkları izlenen `release_assets/ai_models`ten çözdüğü için temiz klonda ve
CI'da 4 test hiç koşmuyordu.

Karar: eserin varlığı ÜRÜNÜN KENDİ ÇÖZÜCÜSÜYLE (modül yanı ya da `find_installed_model` — canlı çıkarımın baktığı kökler)
ölçülür. Eser VARKEN yükleme istisnası → FAIL (her kipte). Eser YOKSA ya da üçüncü taraf bir bağımlılık kurulu değilse
(`ModuleNotFoundError`, ad depo paketi DEĞİL) → ATLA; `PEMF_GOLDEN_REQUIRED=1`'de DÜŞ.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[2]
#: Depo içi üst düzey paketler — bunlardan birinin ModuleNotFoundError'u "bağımlılık yok" değil ÜRÜN HATASIDIR.
_DEPO_PAKETLERI = frozenset({"ai_hub", "utils", "servers", "database", "services", "controllers", "golden", "ai"})


def zorunlu_mu() -> bool:
    return os.environ.get("PEMF_GOLDEN_REQUIRED") == "1"


def atla(sebep: str):
    """Eser yoksa atla — ama yayın makinesinde (PEMF_GOLDEN_REQUIRED=1) atlamak YASAK."""
    if zorunlu_mu():
        pytest.fail(f"PEMF_GOLDEN_REQUIRED=1 ama AI eseri testi kosulamiyor: {sebep}")
    pytest.skip(sebep)


def eser_var_mi(*rel_yollar: str) -> bool:
    """Her `ai_hub/...` yolu modül yanında ya da ürünün model köklerinde DİSKTE duruyor mu.

    ⚠️ 4A-3.8 (A3 incelemesi): eskiden yalnız `find_installed_model` soruluyordu; o, bütünlük süzgecinden (asgari boyut /
    sha yan dosyası) geçmeyen dosyayı GÖRMEZ → diskte DURAN kesik/yarım eser "yok" sayılıp ATLANIYORDU. Bozuk eser "yok"
    değil "VAR ama yüklenemiyor"dur → FAIL. Kökler ürünün KENDİ listesi (`_candidate_model_roots`; aynı ad/kök kuralı)."""
    from utils.model_downloader import ModelButunlukHatasi, _candidate_model_roots, find_installed_model

    def _diskte(r: str) -> bool:
        try:
            if (KOK / r).exists() or find_installed_model(r):
                return True
        except ModelButunlukHatasi:
            return True  # D3.48: bütünlük reddi = eser VAR ama bozuk → yükleme FAIL (atlanmaz — 4A-3.8 ile aynı ilke)
        return any((k / r).is_file() or (k / Path(r).name).is_file() for k in _candidate_model_roots())

    return bool(rel_yollar) and all(_diskte(r) for r in rel_yollar)


def ckd_eserleri() -> tuple[str, ...]:
    """CKD'nin yüklediği iki dosya: best_model.txt'nin adlandırdığı ONNX + preprocessor (load_model ile aynı)."""
    d = "ai_hub/inference_human_kidney_disease"
    try:
        en_iyi = (KOK / d / "best_model.txt").read_text(encoding="utf-8").strip()
    except OSError:
        return (f"{d}/best_model.txt",)
    return (f"{d}/{en_iyi}.onnx", f"{d}/preprocessor.pkl")


def bagimlilik_eksik_mi(hata: BaseException) -> bool:
    if not isinstance(hata, ModuleNotFoundError):
        return False
    ust = (hata.name or "").split(".")[0]
    return bool(ust) and ust not in _DEPO_PAKETLERI


def yukle(kur, eserler: tuple[str, ...], ad: str):
    """`kur()`u çağır; eser VARKEN istisna → FAIL; eser yoksa / 3. taraf bağımlılık yoksa → atla."""
    try:
        return kur()
    except Exception as e:  # karar aşağıda — yutulmaz
        ozet = f"{type(e).__name__}: {str(e)[:160]}"
        if bagimlilik_eksik_mi(e):
            atla(f"{ad}: bagimlilik kurulu degil ({ozet})")
        if eser_var_mi(*eserler):
            pytest.fail(f"{ad}: model eseri VAR {list(eserler)} ama YUKLEME HATASI — {ozet}")
        atla(f"{ad}: eser yok {list(eserler)} ({ozet})")
