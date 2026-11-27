# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D3.41 + D3.44 (B-9.11 · B-9.15 · B-10.64 · B-10.65) — kurtarma kilidi sevk edilen paketle, requirements.txt ile ve derleme yorumlayıcısıyla
AYNI; derleme betiği farkta DURUR. Tek kaynak `scripts/kilit_denetimi.py`.

ÖLÇÜLEN (10-25): 1.9.51 `_internal`ındaki 100 dağıtımın 12'si kilitte YOK (albumentations, scikit-image, pytorch-lightning, torchmetrics,
werkzeug …) — `pip install --no-deps -r build_tools\\myenv-requirements.txt` ile kurtarma bunları kurmaz; kilitteki `opencv-contrib-python==4.9.0.80`
BAYAT İKİZ meta veri (kurulursa cv2'yi 4.9'a düşürür). cryptography / pillow / opencv / zeroconf sürümleri 15-YH'de (D2) zaten hizalanmıştı.
⛔ İNDİRME / KURULUM / KALDIRMA YOK: kilit ORTAMDAN yeniden yazıldı (ortam kilide göre değil). Sevk ağacı kolu sentetik ağaçla HER ZAMAN koşar;
gerçek derleme çıktısı `PEMF_SEVK_AGACI` ile verilirse o da ölçülür (derleme betiği her derlemede `--sevk` koşar).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK / "scripts"))
import kilit_denetimi as kd  # noqa: E402

URETIM, KILIT = kd.sabitler(kd.URETIM), kd.sabitler(kd.KILIT)
# 1.9.51 `_internal`ında ölçülen, 10-25 öncesi kilitte OLMAYAN 12 dağıtım (sürüm sevk edilen dist-info'dan)
ONCEDEN_EKSIK = {
    "albucore": "0.0.24",
    "albumentations": "2.0.8",
    "cloudpickle": "3.1.2",
    "curl-cffi": "0.15.0",
    "imageio": "2.37.4",
    "lightning-utilities": "0.15.3",
    "pi-heif": "1.4.0",
    "pytorch-lightning": "2.6.5",
    "scikit-image": "0.25.2",
    "tifffile": "2025.5.10",
    "torchmetrics": "1.9.0",
    "werkzeug": "3.1.8",
}


def _agac(tmp_path: Path, dagitim: dict[str, str], *, cv2: str | None = None) -> Path:
    ic = tmp_path / "PEMF_Backend" / "_internal"
    ic.mkdir(parents=True)
    for n, v in dagitim.items():
        d = ic / f"{n.replace('-', '_')}-{v}.dist-info"
        d.mkdir()
        (d / "METADATA").write_text(f"Metadata-Version: 2.1\nName: {n}\nVersion: {v}\n", encoding="utf-8")
    if cv2:
        (ic / "cv2").mkdir()
        (ic / "cv2" / "version.py").write_text(f"opencv_version = \"{cv2}\"\ncontrib = False\n", encoding="utf-8")
    return ic.parent


def test_KRITIK_D3_41_requirements_kilidin_ALT_KUMESI_onnx_torch_SABIT_istisna_kurulmaz():
    assert kd.statik(URETIM, KILIT) == []


def test_KRITIK_D3_41_onceden_eksik_12_SEVK_dagitimi_kilitte_ve_AYNI_surumde(tmp_path):
    dagitim = dict(ONCEDEN_EKSIK)
    dagitim.update({k: KILIT[k] for k in ("numpy", "shap", "onnxruntime")})
    assert kd.sevk(_agac(tmp_path, dagitim, cv2=KILIT["opencv-python"]), URETIM, KILIT) == []


def test_KARSIT_D3_41_sevk_ayrimi_YAKALANIR(tmp_path):
    dagitim = dict(ONCEDEN_EKSIK)
    dagitim["kilitte-olmayan-paket"] = "1.0"
    dagitim["opencv-contrib-python"] = "4.9.0.80"
    dagitim["shap"] = "0.0.1"
    hata = kd.sevk(_agac(tmp_path, dagitim, cv2="4.9.0.80"), URETIM, KILIT)
    metin = "\n".join(hata)
    assert "kilitte-olmayan-paket" in metin and "kilitte YOK" in metin, hata
    assert "opencv-contrib-python" in metin and "istisna" in metin, hata
    assert "`shap` sevk 0.0.1" in metin, hata
    assert "cv2 sevk 4.9.0.80" in metin, hata


def test_KARSIT_D3_41_zeroconf_SURUMU_OKUNAMAZSA_kirmizi_ve_bos_agac_kor_degil(tmp_path):
    ag = _agac(tmp_path, dict(ONCEDEN_EKSIK))
    (ag / "_internal" / "zeroconf").mkdir()
    assert any("zeroconf" in h and "okunamadı" in h for h in kd.sevk(ag, URETIM, KILIT))
    bos = tmp_path / "bos" / "PEMF_Backend"
    (bos / "_internal").mkdir(parents=True)
    assert any("hiç dist-info yok" in h for h in kd.sevk(bos, URETIM, KILIT))


@pytest.mark.yalniz_yayin_makinesi  # CT1 c (Y324): yalnız yayın makinesi eseri — CI'da gerekçeli atlar, Y30'da atlarsa KIRMIZI
@pytest.mark.skipif(
    not Path(sys.base_prefix).joinpath(f"python{sys.version_info.major}{sys.version_info.minor}.zip").exists(),
    reason="gömülü derleme Python'u değil (CI / venv) — statik + sentetik kollar yine koştu",
)
def test_KRITIK_D3_44_derleme_yorumlayicisi_sabitlerle_AYNI():
    assert kd.ortam(URETIM, KILIT) == []


@pytest.mark.yalniz_yayin_makinesi  # CT1 c (Y324): yalnız yayın makinesi eseri — CI'da gerekçeli atlar, Y30'da atlarsa KIRMIZI
def test_D3_41_GERCEK_sevk_agaci_kilitle_AYNI():
    import os

    yol = os.environ.get("PEMF_SEVK_AGACI", "").strip()
    if not yol:
        pytest.skip("PEMF_SEVK_AGACI verilmedi — gerçek derleme çıktısı derleme betiğinin `--sevk` adımında ölçülür")
    assert kd.sevk(Path(yol), URETIM, KILIT) == []


def test_KRITIK_D3_44_derleme_betigi_ONCE_ortam_SONRA_sevk_DENETLER_ve_DURUR():
    src = (KOK / "scripts" / "build_backend_exe.ps1").read_text(encoding="utf-8-sig")
    i_ortam = src.find("kilit_denetimi.py\" --ortam")
    i_py = src.find("-m PyInstaller")
    i_sevk = src.find("kilit_denetimi.py\" --sevk")
    assert -1 < i_ortam < i_py < i_sevk, (i_ortam, i_py, i_sevk)
    for i in (i_ortam, i_sevk):
        sonraki = src[i : i + 400]
        assert "if ($LASTEXITCODE -ne 0) { Die" in sonraki, sonraki


def test_D3_41_istisna_kilitte_GEREKCELI_yorum():
    metin = kd.KILIT.read_text(encoding="utf-8")
    assert not [s for s in metin.splitlines() if s.strip().startswith("opencv-contrib-python==")], (
        "bayat ikiz kilitte SABİTLİ"
    )
    assert "İSTİSNA (D3.41): opencv-contrib-python" in metin


def test_D3_41_B_9_15_security_ci_KURTARMA_KILIDINI_tarar_bloklamaz():
    """Plan B-9.15: CVE taraması sevk edilen kilidi de görsün (bilgi amaçlı — sahip kararı; aynı izinli adım)."""
    src = (KOK / ".github" / "workflows" / "security.yml").read_text(encoding="utf-8")
    assert "pip-audit -r build_tools/myenv-requirements.txt --no-deps --disable-pip" in src
