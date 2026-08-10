# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""LİSANS YÜZEYİ KAPISI (2026-08-09 denetimi, Tier 2).

DURUM: ürün kapalı kaynak, `.pyd` ile tersine mühendisliğe karşı korunmuş ve ücretli abonelikle
satılıyor. Buna rağmen yayınlanan `base-deps.zip` içinde **AGPL-3.0** lisanslı `ultralytics`
(321 dosya) dağıtılıyor. AGPL, türev çalışmanın kaynağının alıcıya açılmasını şart koşar; yani
bu teorik değil GERÇEKLEŞMİŞ bir uyumsuzluktur (bkz. `docs/AGPL-KARARI.md`).

⚠️ BU TESTLER SORUNU ÇÖZMEZ. Karar hukuk + bütçe işidir (ticari lisans / ONNX'e taşıma).
Bu dosyanın işi, yüzeyin **sessizce büyümesini** engellemektir: bugün bilinen tek istisna
açıkça listelidir; pakete YENİ bir kopyleft bağımlılık girerse test DÜŞER ve karar bilinçli
olarak verilir. Sorunu "bilinen ve izlenen" hâle getirir.
"""

import re
import zipfile
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
PAKET = KOK / "pemf-app-packages" / "base-deps.zip"

#: Kopyleft sayılan lisans imzaları. LGPL KASITLI DIŞARIDA: dinamik bağlamada kapalı kaynak
#: ürünle birlikte dağıtılabilir ve bu projede öyle kullanılır.
_KOPYLEFT = ("AGPL", "GPL-3", "GPL-2", "GPLV3", "GPLV2", "GNU GENERAL PUBLIC")

#: BİLİNEN ve KARARI BEKLEYEN istisna. Buraya bir şey eklemek, hukuki bir karar vermektir —
#: `docs/AGPL-KARARI.md` güncellenmeden eklenmemelidir.
_BILINEN_ISTISNALAR = {"ultralytics"}


def _paket_lisanslari():
    """Dağıtılan paketteki (paket adı → lisans metni). `dist-info/METADATA`dan OKUNUR."""
    out = {}
    with zipfile.ZipFile(PAKET) as z:
        for n in z.namelist():
            m = re.match(r"PEMF_Backend/_internal/([^/]+)-([^/]+)\.dist-info/METADATA$", n)
            if not m:
                continue
            meta = z.read(n).decode("utf-8", "replace")
            lic = ""
            for satir in meta.splitlines()[:80]:
                if satir.startswith("License:"):
                    lic = satir.split(":", 1)[1].strip()
                elif satir.startswith("Classifier: License ::") and not lic:
                    lic = satir.split("::")[-1].strip()
            out[m.group(1).lower()] = lic
    return out


def _kopyleft_mu(lisans: str) -> bool:
    u = (lisans or "").upper()
    if "LGPL" in u:
        return False
    return any(k in u for k in _KOPYLEFT)


pytestmark = pytest.mark.skipif(
    not PAKET.exists(), reason="base-deps.zip yok (temiz checkout / CI) — lisans yüzeyi paketten okunur"
)


# ── kapı ─────────────────────────────────────────────────────────────────────


def test_KRITIK_YENI_kopyleft_bagimlilik_EKLENMEZ():
    """Yeni bir AGPL/GPL bağımlılık pakete sızarsa uyumsuzluk yüzeyi sessizce büyür.
    Bu test, o kararın BİLİNÇLİ verilmesini zorunlu kılar."""
    kopyleft = {ad for ad, lic in _paket_lisanslari().items() if _kopyleft_mu(lic)}
    yeni = kopyleft - _BILINEN_ISTISNALAR
    assert not yeni, (
        f"Pakete YENİ kopyleft bağımlılık girdi: {sorted(yeni)}. "
        "Kapalı kaynak + ücretli üründe bu, kaynak açma yükümlülüğü doğurur. "
        "Bilinçli bir karar ise docs/AGPL-KARARI.md'yi güncelleyip istisna listesine ekleyin."
    )


def test_bilinen_istisna_HALA_GECERLI():
    """İstisna listesi 'ölü' kalmasın: `ultralytics` paketten çıkarsa (ONNX'e taşındıysa)
    bu test düşer ve listeden silinmesi hatırlatılır — sorun çözüldüğünde kapı da kapanmalı."""
    kopyleft = {ad for ad, lic in _paket_lisanslari().items() if _kopyleft_mu(lic)}
    kalan = _BILINEN_ISTISNALAR & kopyleft
    assert kalan == _BILINEN_ISTISNALAR, (
        f"Bu istisnalar artık pakette YOK: {sorted(_BILINEN_ISTISNALAR - kopyleft)}. "
        "Sorun çözülmüşse istisna listesinden çıkarın ve docs/AGPL-KARARI.md'yi kapatın."
    )


def test_ultralytics_AGPL_olarak_tespit_ediliyor():
    """Tespit mantığının kendisi çalışıyor mu — yoksa kapı boş güvence verirdi."""
    lisanslar = _paket_lisanslari()
    assert "ultralytics" in lisanslar, "ultralytics pakette bulunamadi (tespit bozuk olabilir)"
    assert _kopyleft_mu(lisanslar["ultralytics"]), f"AGPL tespit edilemedi: {lisanslar['ultralytics']!r}"


def test_LGPL_kopyleft_SAYILMAZ():
    """LGPL kasıtlı dışarıda: dinamik bağlamada kapalı kaynak ürünle dağıtılabilir."""
    assert not _kopyleft_mu("LGPL-2.1")
    assert not _kopyleft_mu("GNU Lesser General Public License v3 (LGPLv3)")
    assert _kopyleft_mu("AGPL-3.0") and _kopyleft_mu("GPL-3.0")


# ── belgeler ─────────────────────────────────────────────────────────────────


def test_NOTICE_dosyasi_VAR_ve_ultralyticsi_ISARETLER():
    p = KOK / "THIRD_PARTY_LICENSES.md"
    assert p.exists(), "atıf (NOTICE) dosyasi yok"
    metin = p.read_text(encoding="utf-8")
    assert "ultralytics" in metin and "AGPL-3.0" in metin


def test_NOTICE_uyumu_SAGLADIGINI_IDDIA_ETMEZ():
    """⚠️ En kolay yanılgı: NOTICE eklenince 'uyumlu olduk' sanmak. Atıf yükümlülüğü ile
    kaynak açma yükümlülüğü AYRI şeylerdir; dosya bunu açıkça söylemeli."""
    metin = (KOK / "THIRD_PARTY_LICENSES.md").read_text(encoding="utf-8")
    assert "KARŞILAMAZ" in metin, "NOTICE, uyum sagladigi yanilgisina kapi birakiyor"


def test_karar_notu_VAR_ve_agirlik_lisansini_ISARETLER():
    """Ağırlık lisansı nüansı denetimde YOKTU ve (b) seçeneğini geçersiz kılabilir —
    karar notunda mutlaka bulunmalı."""
    p = KOK / "docs" / "AGPL-KARARI.md"
    assert p.exists(), "karar notu yok"
    metin = p.read_text(encoding="utf-8")
    assert "ağırlık" in metin.lower(), "onceden egitilmis agirlik lisansi nuansi yazilmamis"
    assert "petri" in metin.lower() and "kidney_ct" in metin.lower(), "uretim yolundaki moduller listelenmemis"
