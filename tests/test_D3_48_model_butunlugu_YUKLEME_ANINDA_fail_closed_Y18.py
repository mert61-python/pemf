# Author: mertaygn, cglrgrkn
"""D3.48 (B-5.14) + İG-5.40 · Y18 (sahip) — model ve yan dosyalara YÜKLEME ANINDA bütünlük denetimi: takipli SHA manifesti (D3.45
`release_assets/ai_models_sha256.json`; donmuşta `_internal/ai_hub/`) ya da `.sha256` yan dosyası. Tutmazsa yüklenmez, logger.error yazılır,
sonraki köke SESSİZ düşüş yok; AI ucu 503 + açık uyarı. Manuel seans ve ACİL DURDUR etkilenmez.

ÖLÇÜLEN (HEAD): doz yolundaki em_kedi `scaler_X.pkl`ı `scale_[0]` ×1,10 kurcalanınca GERÇEK yükleyici uyarısız yüklüyor (plan: D1 0,162 →
0,146); `yan_dosya_coz` modül-yanı dosyayı denetimsiz döndürüyor, `_model_integrity_ok` yalnız `.sha256` yan dosyası varsa SHA bakıyor
(sevk edilmiyor), reddi `print` ile yazıp (`frozen` EXE'de stdout NUL) `find_installed_model` SONRAKİ köke düşüyordu (İG-5.40).
Sahte EN ALT katta: yalnız model kökleri (geçici dizin) ve kurcalanmış kopya; manifest GERÇEK takipli dosya.
"""

from __future__ import annotations

import importlib.util
import logging
import shutil
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
EMK = KOK / "ai_hub" / "em_kedi"


@pytest.fixture
def md(monkeypatch):
    from utils import model_downloader as md

    monkeypatch.setattr(md, "_manifest_onbellegi", {})
    monkeypatch.setattr(md, "_ozet_onbellegi", {})
    return md


def _kurcala(kaynak: Path, hedef: Path) -> None:
    import joblib

    sc = joblib.load(kaynak)
    sc.scale_ = sc.scale_.copy()
    sc.scale_[0] = sc.scale_[0] * 1.10
    joblib.dump(sc, hedef)


def _em_kedi_kopyasi(tmp_path: Path, kurcalanmis: bool) -> Path:
    d = tmp_path / "em_kedi"
    d.mkdir()
    shutil.copy2(EMK / "inference_em_kedi.py", d / "inference_em_kedi.py")
    for ad in ("scaler_extra.pkl", "scaler_y.pkl"):
        shutil.copy2(EMK / ad, d / ad)
    if kurcalanmis:
        _kurcala(EMK / "scaler_X.pkl", d / "scaler_X.pkl")
    else:
        shutil.copy2(EMK / "scaler_X.pkl", d / "scaler_X.pkl")
    return d


def _yukle(d: Path):
    spec = importlib.util.spec_from_file_location(f"d348_em_kedi_{d.parent.name}", d / "inference_em_kedi.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_KRITIK_D3_48_kurcalanmis_em_kedi_olcekleyicisi_GERCEK_yukleyicide_REDDEDILIR(md, tmp_path, caplog):
    d = _em_kedi_kopyasi(tmp_path, kurcalanmis=True)
    with caplog.at_level(logging.ERROR, logger="utils.model_downloader"):
        with pytest.raises(md.ModelButunlukHatasi) as e:
            _yukle(d)
    assert e.value.sebep == "ozet" and e.value.dosya.endswith("scaler_X.pkl")
    assert any("REDDİ" in r.getMessage() and "scaler_X.pkl" in r.getMessage() for r in caplog.records), (
        "ret günlüğe yazılmadı"
    )


def test_KARSIT_D3_48_dogru_ozetli_kopya_KABUL_edilir(md, tmp_path):
    d = _em_kedi_kopyasi(tmp_path, kurcalanmis=False)
    mod = _yukle(d)
    assert Path(mod.SCALER_X_PATH) == d / "scaler_X.pkl"


@pytest.fixture
def kokler(md, tmp_path, monkeypatch):
    r1, r2 = tmp_path / "kok1", tmp_path / "kok2"
    for r in (r1, r2):
        (r / "ai_hub" / "em_kedi").mkdir(parents=True)
    monkeypatch.setattr(md, "_candidate_model_roots", lambda: [r1, r2])
    return r1, r2


def test_KRITIK_D3_48_IG_5_40_kurcalanmis_kok_kopyasi_SONRAKI_koke_DUSMEZ_logger_print_DEGIL(
    md, kokler, caplog, capsys
):
    r1, r2 = kokler
    _kurcala(EMK / "scaler_X.pkl", r1 / "ai_hub/em_kedi/scaler_X.pkl")
    shutil.copy2(EMK / "scaler_X.pkl", r2 / "ai_hub/em_kedi/scaler_X.pkl")  # SAĞLAM kopya ikinci kökte
    with caplog.at_level(logging.ERROR, logger="utils.model_downloader"):
        with pytest.raises(md.ModelButunlukHatasi):
            md.find_installed_model("ai_hub/em_kedi/scaler_X.pkl")
    assert capsys.readouterr().out == "", "ret print ile yazıldı (donmuş EXE'de stdout NUL)"
    assert caplog.records, "ret günlüğe yazılmadı"


def test_KARSIT_D3_48_kesik_kopyada_eski_davranis_sonraki_kok_ve_GUNLUK(md, kokler, caplog):
    r1, r2 = kokler
    (r1 / "ai_hub/em_kedi/scaler_X.pkl").write_bytes(b"x" * 10)  # asgari boyut (200 B) altı — yarım kurulum
    shutil.copy2(EMK / "scaler_X.pkl", r2 / "ai_hub/em_kedi/scaler_X.pkl")
    with caplog.at_level(logging.ERROR, logger="utils.model_downloader"):
        assert md.find_installed_model("ai_hub/em_kedi/scaler_X.pkl") == str(r2 / "ai_hub/em_kedi/scaler_X.pkl")
    assert any("küçük" in r.getMessage() for r in caplog.records)


def test_KARSIT_D3_48_manifestte_OLMAYAN_dosya_eski_davranis(md, kokler):
    r1, _ = kokler
    (r1 / "ai_hub/em_kedi/yeni_model.pkl").write_bytes(b"y" * 500)
    assert md.find_installed_model("ai_hub/em_kedi/yeni_model.pkl") == str(r1 / "ai_hub/em_kedi/yeni_model.pkl")


def test_KRITIK_D3_48_Y18_AI_ucu_503_ve_ACIK_uyari_diger_hata_500(md):
    from servers.ai_router import _ai_fail

    h = _ai_fail("Analiz hatası", md.ModelButunlukHatasi(r"C:\\x\\scaler_X.pkl", "ozet"))
    assert h.status_code == 503 and "scaler_X.pkl" in str(h.detail)
    sarili = FileNotFoundError(
        "BiLSTM_XXL_Raw.onnx bulunamadı. İndirme hatası: model butunluk denetimi gecmedi: C:/y.onnx (ozet)"
    )
    assert _ai_fail("Analiz hatası", sarili).status_code == 503, "modülün sardığı bütünlük reddi 500'e düştü"
    assert _ai_fail("Analiz hatası", ValueError("başka")).status_code == 500


def test_D3_48_manifest_PAKETE_girer_APP_katmaninda_yoksa_derleme_DURUR():
    spec = (KOK / "build_tools" / "PEMF_Backend_onedir.spec").read_text(encoding="utf-8")
    assert "datas.append((_model_manifest, 'ai_hub'))" in spec
    assert "ai_models_sha256.json yok" in spec and "raise SystemExit" in spec[spec.find("_model_manifest =") :][:600]
    zip_ = (KOK / "build_tools" / "make_base_zip.py").read_text(encoding="utf-8")
    assert "'PEMF_Backend/_internal/ai_hub'," in zip_, "ai_hub APP katmanında değil — manifest bayatlar"
