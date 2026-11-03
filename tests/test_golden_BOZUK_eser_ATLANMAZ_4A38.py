# -*- coding: utf-8 -*-
"""4A-3.8 önce-kırmızı (A3 incelemesi): D3.03 `tests/golden/eser.py` — diskte DURAN ama bozuk (kesik / yarım indirilmiş,
<100 KB) bir model eseri "eser YOK" sayılıp ATLANIYOR (varsayılan kip), "eser VARKEN yükleme hatası → FAIL" iddiasına rağmen.

Neden: `eser_var_mi` ürün çözücüsü `find_installed_model`i kullanır; o da `_model_integrity_ok` (asgari boyut / sha yan
dosyası) süzgecinden geçmeyen dosyayı GÖRMEZ → bozuk eser = yok → `atla`. Gerçek ağırlıklara dokunulmaz: ürünün kök listesi
(`_candidate_model_roots`) tmp'deki bir köke çevrilir; kökte bozuk CKD ONNX + gerçek preprocessor'ın KOPYASI durur.
"""

from __future__ import annotations

import os
import shutil

import pytest
import utils.model_downloader as md
from golden import eser as E
from golden import yukleyici as Y

D = "ai_hub/inference_human_kidney_disease"


def _kok(tmp_path, onnx_bayt: bytes):
    kok = tmp_path / "ai_models"
    hedef = kok / D
    hedef.mkdir(parents=True)
    en_iyi = (E.KOK / D / "best_model.txt").read_text(encoding="utf-8").strip()
    (hedef / f"{en_iyi}.onnx").write_bytes(onnx_bayt)
    shutil.copy2(E.KOK / "release_assets" / "ai_models" / D / "preprocessor.pkl", hedef / "preprocessor.pkl")
    return kok


def _temiz_klon(monkeypatch, tmp_path):
    """Modül yanı = TEMİZ KLON (yalnız izlenen `best_model.txt`). Yayın makinesinde (guii, Y30) modül yanında git-ignored GERÇEK ONNX /
    preprocessor durur; ürün önce oraya baktığı (`yan_dosya_coz`) ve `eser_var_mi` depo kökünü sorduğu için sahte kökteki bozuk eser
    hiç yüklenmiyordu — üç kol 'gecti' ile kırmızıydı (ölçüldü 2026-11-03)."""
    temiz = tmp_path / "temiz_klon"
    (temiz / D).mkdir(parents=True)
    shutil.copy2(E.KOK / D / "best_model.txt", temiz / D / "best_model.txt")
    monkeypatch.setattr(E, "KOK", temiz)
    monkeypatch.setattr(Y.ckd_modulu(), "THIS_DIR", temiz / D)


def _sonuc(monkeypatch, kok):
    """E.yukle'nin sonucu: ('fail' | 'skip' | 'gecti', ileti)."""
    monkeypatch.setattr(md, "_candidate_model_roots", lambda: [kok])
    _temiz_klon(monkeypatch, kok.parent)
    m = Y.ckd_modulu()
    m.load_model.cache_clear()

    def kur():
        m.load_model()
        return m

    try:
        E.yukle(kur, E.ckd_eserleri(), "CKD")
        return "gecti", ""
    except pytest.fail.Exception as e:
        return "fail", str(e)
    except pytest.skip.Exception as e:
        return "skip", str(e)
    finally:
        m.load_model.cache_clear()


def test_KRITIK_kucuk_bozuk_eser_ATLANMAZ_FAIL_olur(tmp_path, monkeypatch):
    monkeypatch.delenv("PEMF_GOLDEN_REQUIRED", raising=False)
    kok = _kok(tmp_path, os.urandom(1024))  # kesik/yarım ONNX: diskte VAR, ürün bütünlük süzgecinde reddediyor
    durum, ileti = _sonuc(monkeypatch, kok)
    assert durum == "fail", f"diskte DURAN bozuk eser '{durum}' oldu (FAIL beklenirdi): {ileti[:240]}"


def test_KARSIT_buyuk_bozuk_eser_FAIL(tmp_path, monkeypatch):
    """Bütünlük süzgecini geçen (≥100 KB) bozuk ONNX'te ayrım bugün de doğru: onnxruntime hatası → FAIL."""
    monkeypatch.delenv("PEMF_GOLDEN_REQUIRED", raising=False)
    kok = _kok(tmp_path, os.urandom(200_000))
    durum, ileti = _sonuc(monkeypatch, kok)
    assert durum == "fail" and "YUKLEME HATASI" in ileti, (durum, ileti[:240])


def test_KARSIT_eser_HIC_yoksa_ATLANIR(tmp_path, monkeypatch):
    """Eser kökte hiç yoksa (temiz klon sınıfı) varsayılan kipte atlama doğru davranıştır."""
    monkeypatch.delenv("PEMF_GOLDEN_REQUIRED", raising=False)
    kok = tmp_path / "bos_kok"
    kok.mkdir()
    durum, ileti = _sonuc(monkeypatch, kok)
    assert durum == "skip" and "eser yok" in ileti, (durum, ileti[:240])
