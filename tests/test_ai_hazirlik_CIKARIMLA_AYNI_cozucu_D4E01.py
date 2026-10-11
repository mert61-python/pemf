# -*- coding: utf-8 -*-
"""D4.E01 (İG-9.21, 4-A devri) — AI hazırlık envanteri modeli CANLI çıkarımın çözücüsüyle (`yan_dosya_coz`) arar.

ARIZA: katmanlı launcher düzeninde küçük model dosyaları (ör. böbrek-hastalık `ExtraTrees.onnx`) spec gereği modülün YANINDA
(`_internal/ai_hub/<modül>/…`) sevk edilir (D4.27); profil kökü (`PEMF_AI_MODELS_DIR`) ve `_internal/ai_models` onları taşımaz.
Canlı çıkarım `yan_dosya_coz` ile önce modül-yanına bakar → çalışır; hazırlık (`_model_hazir_mi`) ise yalnız `find_installed_model`'in
5 köküne bakıyordu → `model_yok`. Sonuç: çalışan modül "hazır değil" görünür (sahte kırmızı gösterge) ve build AI kapısı aynı
kaynaktan beslendiği için yanlış teşhis üretir (4-A incelemesi A3 ölçtü; kanıt `k4_ig921.txt`).

Ölçüm: katmanlı düzen benzetimi (TEMP; `sys.frozen` + `sys._MEIPASS`), backend BAŞLATILMAZ. Gerçek ağırlık yalnız OKUNUR (izlenen
`release_assets` kopyası tmp'ye). Hazır önce-kırmızı 4-A incelemesinden (`test_zz_K4_D4E01_…`) alındı, karşıtlarla tamamlandı.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
REL = "ai_hub/inference_human_kidney_disease/ExtraTrees.onnx"


@pytest.fixture
def duzen(tmp_path, monkeypatch):
    meipass = tmp_path / "runtime" / "PEMF_Backend" / "_internal"
    (meipass / "ai_models").mkdir(parents=True)
    profil = tmp_path / "ai_models"
    profil.mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)
    monkeypatch.setenv("PEMF_AI_MODELS_DIR", str(profil))
    return meipass, profil


def _koy(hedef: Path) -> Path:
    hedef.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(KOK / "release_assets" / "ai_models" / REL, hedef)
    return hedef


def test_KRITIK_hazirlik_canli_cikarimin_MODUL_YANINDA_buldugu_modeli_GORUR(duzen):
    meipass, _ = duzen
    modul_yani = _koy(meipass / REL)
    import utils.model_downloader as md
    from servers.ai_router import _model_hazir_mi

    cikarim = Path(md.yan_dosya_coz(modul_yani, REL))
    assert cikarim.is_file(), f"benzetim kurulamadı: çıkarım yolu yok {cikarim}"
    durum, ayrinti = _model_hazir_mi(REL)
    assert durum == "ok", f"canlı çıkarım {cikarim} dosyasını yüklerken hazırlık '{durum}' diyor: {ayrinti}"


def test_KARSIT_profil_kokundeki_model_de_GORULUR(duzen):
    _, profil = duzen
    _koy(profil / REL)
    from servers.ai_router import _model_hazir_mi

    assert _model_hazir_mi(REL)[0] == "ok"


def test_KARSIT_hicbir_yerde_yoksa_model_yok(duzen):
    from servers.ai_router import _model_hazir_mi

    durum, _ = _model_hazir_mi(REL)
    assert durum == "model_yok", f"dosya hiçbir yerde yokken hazırlık '{durum}' (sahte yeşil)"


def test_KARSIT_envanter_yolu_tanimsiz_HATA_kalir():
    from servers.ai_router import _model_hazir_mi

    assert _model_hazir_mi(None)[0] == "envanter_eksik"
