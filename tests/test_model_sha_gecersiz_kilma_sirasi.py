# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""MODEL ACILMADAN ONCE SHA KAYDI GECERSIZ KILINIR (denetim 2026-08-23, bulgu C12).

OLCULEN DURUM: `flow.rs`te model paketi acan IKI dongu var ve AYNI kurali paylasmalari gerekiyordu:

  · `profilleri_yenile`  → `record_model_sha(..., "")` ONCE, extract SONRA, gercek sha EN SON. ✅
  · `install_profiles`   → extract ONCE, sha SONRA. ❌ (arada gecersiz kilma YOK)

NEDEN ONEMLI: `repair()` dogrudan `install_profiles`e duser ve onarim senaryosunda
`installed_packages.json` ZATEN o modelin dogru sha'sini tasir. Model zip'i acilirken elektrik
kesilir / kullanici iptal ederse diskte YARIM (kesik .onnx) bir model agaci kalir ama kayit hala
manifest sha'siyla ESLESIR → `pending_updates` o profili "guncel" sayar ve oto-guncelleme onu bir
daha ASLA yenilemez. `kurulum_saglam_mi` yalniz runtime agacina baktigi icin client "Hazir!" der.

Kullanici acisindan sonuc: AI analizi anlasilmaz bir hatayla duser, hicbir yerde "model bozuk"
denmez ve tek care kullanicinin kendiliginden tekrar "Onar"a basmasidir.

⚠️ BU BIR SIRA KURALIDIR, VARLIK KURALI DEGIL. `record_model_sha(..., "")` cagrisinin dosyada
BULUNMASI yetmez; extract'tan ONCE gelmesi gerekir. Test ikisini de olcer.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parents[1]
_FLOW = _KOK / "launcher" / "core" / "src" / "flow.rs"


@pytest.fixture(scope="module")
def kaynak() -> str:
    return _FLOW.read_text(encoding="utf-8", errors="replace")


def _model_dongusu(kaynak: str, fonksiyon: str) -> str:
    """Verilen fonksiyonun govdesinden model dongusunu cikarir."""
    m = re.search(rf"fn {re.escape(fonksiyon)}\s*\(", kaynak)
    assert m, f"`{fonksiyon}` bulunamadi — flow.rs bicimi degismis olabilir"
    sonraki = re.search(r"\n(?:pub\s+)?fn\s+\w+\s*\(", kaynak[m.end() :])
    govde = kaynak[m.end() : m.end() + (sonraki.start() if sonraki else len(kaynak))]
    assert "record_model_sha" in govde, f"`{fonksiyon}` model sha kaydi yapmiyor — akis degismis"
    return govde


@pytest.mark.parametrize("fonksiyon", ["install_profiles", "profilleri_yenile"])
def test_KRITIK_sha_EXTRACTTAN_ONCE_gecersiz_kilinir(kaynak, fonksiyon):
    """🔴 ASIL KURAL: yarida kesilen acilim 'guncel' kaydi BIRAKAMAZ."""
    g = _model_dongusu(kaynak, fonksiyon)
    # Gecersiz kilma: bos dize ile record_model_sha.
    m_gecersiz = re.search(r'record_model_sha\([^)]*,\s*""\s*\)', g)
    assert m_gecersiz, (
        f"`{fonksiyon}` model acilmadan ONCE sha kaydini GECERSIZ KILMIYOR — yarida kesilen "
        "onarim/kurulum, diskte YARIM bir model birakip kaydi 'guncel' halde tutar; o profil bir "
        "daha ASLA yenilenmez ve AI analizi anlasilmaz bir hatayla duser (bulgu C12)"
    )
    # ⚠️ MODEL acilimini bul, fonksiyondaki ILK acilimi DEGIL: `install_profiles` once base.zip'i
    # aciyor, yani ilk `extract` cagrisi model dongusunden ONCE gelir. Ilk yazimda bu dusunulmemis
    # ve test dogru kodu yanlis-KIRMIZI gostermisti. Dogru olcum: gecersiz kilmadan SONRA gelen
    # ilk acilim, gercek sha yazimindan ONCE olmali.
    i_extract = g.find("extract::extract_zip_cancellable", m_gecersiz.end())
    assert i_extract > 0, (
        f"`{fonksiyon}` gecersiz kilmadan SONRA model acilimi yok — gecersiz kilma anlamsiz "
        "(kayit hemen gercek sha ile yeniden yaziliyorsa koruma olusmaz)"
    )
    m_gercek = re.search(r'record_model_sha\((?![^)]*,\s*""\s*\))[^)]*\)', g[i_extract:])
    assert m_gercek, f"`{fonksiyon}` acilimdan sonra gercek sha'yi yazmiyor — profil hep bayat kalir"


@pytest.mark.parametrize("fonksiyon", ["install_profiles", "profilleri_yenile"])
def test_KRITIK_gercek_sha_EXTRACTTAN_SONRA_yazilir(kaynak, fonksiyon):
    """Karsi-kanit: gercek sha acilim BASARILI olduktan sonra yazilmali.

    Once yazilsaydi gecersiz kilma anlamsizlasirdi (kayit yine 'guncel' kalirdi).
    """
    g = _model_dongusu(kaynak, fonksiyon)
    i_extract = g.find("extract::extract_zip_cancellable")
    gercekler = [m.start() for m in re.finditer(r'record_model_sha\((?![^)]*,\s*""\s*\))[^)]*\)', g)]
    assert gercekler, f"`{fonksiyon}` gercek sha'yi hic yazmiyor"
    assert all(p > i_extract for p in gercekler), (
        f"`{fonksiyon}` gercek sha'yi acilimdan ONCE yaziyor — yarim acilim 'guncel' gorunur"
    )
