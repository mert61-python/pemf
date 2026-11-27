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

import capraz
import pytest

KOK = Path(__file__).resolve().parent.parent
PAKET = KOK / "pemf-app-packages" / "base-deps.zip"

#: BİLİNEN ve KARARI BEKLEYEN istisna. Buraya bir şey eklemek, hukuki bir karar vermektir —
#: `docs/AGPL-KARARI.md` güncellenmeden eklenmemelidir.
_BILINEN_ISTISNALAR = {"ultralytics"}


def _paket_lisanslari():
    """Dağıtılan paketteki (paket adı → lisans metni). `dist-info/METADATA`dan OKUNUR.

    ⚠️ ÇIPA TAŞINDI (2026-09-16) — ve bir DELİK kapandı. Bu fonksiyonun kendi ayrıştırıcısı
    vardı ve yalnız `License:` + `Classifier: License ::` okuyordu. Modern paketler lisansı
    **`License-Expression:`** ile bildiriyor (PEP 639); o alan okunmayınca lisans BOŞ
    görünüyordu. Ölçüldü (sevk edilen `base-deps.zip`): 100 paketin **30'unun** lisansı
    eski okuyucuyla boştu, yenisiyle 0.

    ⚠️ BUGÜN GİZLİ BİR UYUMSUZLUK YOKTU: iki okuyucu da kopyleft kümesini AYNI buluyor
    (`{ultralytics}`). Yani yaşanmış bir ihlal değil, GELECEK için açık bir delikti —
    `License-Expression: AGPL-3.0` diyen yeni bir paket bu kapıya GÖRÜNMEZ olurdu.

    Ayrıştırıcı artık `scripts/lisans_envanteri_uret.py`de TEK yerde; NOTICE üreteci de
    aynı fonksiyonu kullanıyor. (Kendi kopyasını yazmak, bu deponun 2026-09-15'te üç ayrı
    noktada ölçtüğü "aynı kural iki yerde → sessizce ayrıştı" arızasını tekrarlardı.)
    """
    from scripts.lisans_envanteri_uret import paket_lisanslari

    return {ad: lic for ad, (_surum, lic) in paket_lisanslari(PAKET).items()}


def _kopyleft_mu(lisans: str) -> bool:
    """TEK KAYNAK: sınıflandırıcı `scripts/lisans_envanteri_uret.py`de (D4.08, 2026-10-10). LGPL KASITLI DIŞARIDA:
    dinamik bağlamada kapalı kaynak ürünle birlikte dağıtılabilir ve bu projede öyle kullanılır."""
    from scripts.lisans_envanteri_uret import kopyleft_mu

    return kopyleft_mu(lisans)


@pytest.fixture()
def paket_gerekli():
    """Sevk edilen paketten OKUYAN testler için: paket yoksa atla, `PEMF_CAPRAZ_KAYNAK_ZORUNLU=1`de DÜŞ.

    ⚠️ D4.08 (B-10.139): eskiden modül düzeyi `pytestmark = skipif(not PAKET.exists())` vardı → paketsiz ortamda
    (temiz checkout, CI) dosyadaki TÜM testler atlanıyordu; paket gerektirmeyen 4 test (LGPL sınıflandırıcı, NOTICE,
    karar notu) CI'da hiç koşmuyordu. Kapı artık yalnız pakete bakan üç teste uygulanır."""
    capraz.atla_yoksa("pemf-app-packages/base-deps.zip", yalniz_yayin=True)


# ── kapı ─────────────────────────────────────────────────────────────────────


def _paket_kopyleft():
    """4A-3.7 (A3 incelemesi): kopyleft KARARI tüm lisans alanlarından (`paket_kopyleft`) — NOTICE'in tek alanı
    (`metadata_lisansi`) `License: UNKNOWN`/serbest metin/ilk sınıflandırıcı arkasında GPL sınıflandırıcısını gizliyordu."""
    from scripts.lisans_envanteri_uret import paket_kopyleft

    return paket_kopyleft(PAKET)


@pytest.mark.yalniz_yayin_makinesi  # CT1 c (Y324): yalnız yayın makinesi eseri — CI'da gerekçeli atlar, Y30'da atlarsa KIRMIZI
def test_KRITIK_YENI_kopyleft_bagimlilik_EKLENMEZ(paket_gerekli):
    """Yeni bir AGPL/GPL bağımlılık pakete sızarsa uyumsuzluk yüzeyi sessizce büyür.
    Bu test, o kararın BİLİNÇLİ verilmesini zorunlu kılar."""
    kopyleft = _paket_kopyleft()
    yeni = kopyleft - _BILINEN_ISTISNALAR
    assert not yeni, (
        f"Pakete YENİ kopyleft bağımlılık girdi: {sorted(yeni)}. "
        "Kapalı kaynak + ücretli üründe bu, kaynak açma yükümlülüğü doğurur. "
        "Bilinçli bir karar ise docs/AGPL-KARARI.md'yi güncelleyip istisna listesine ekleyin."
    )


@pytest.mark.yalniz_yayin_makinesi  # CT1 c (Y324): yalnız yayın makinesi eseri — CI'da gerekçeli atlar, Y30'da atlarsa KIRMIZI
def test_bilinen_istisna_HALA_GECERLI(paket_gerekli):
    """İstisna listesi 'ölü' kalmasın: `ultralytics` paketten çıkarsa (ONNX'e taşındıysa)
    bu test düşer ve listeden silinmesi hatırlatılır — sorun çözüldüğünde kapı da kapanmalı."""
    kopyleft = _paket_kopyleft()
    kalan = _BILINEN_ISTISNALAR & kopyleft
    assert kalan == _BILINEN_ISTISNALAR, (
        f"Bu istisnalar artık pakette YOK: {sorted(_BILINEN_ISTISNALAR - kopyleft)}. "
        "Sorun çözülmüşse istisna listesinden çıkarın ve docs/AGPL-KARARI.md'yi kapatın."
    )


@pytest.mark.yalniz_yayin_makinesi  # CT1 c (Y324): yalnız yayın makinesi eseri — CI'da gerekçeli atlar, Y30'da atlarsa KIRMIZI
def test_ultralytics_AGPL_olarak_tespit_ediliyor(paket_gerekli):
    """Tespit mantığının kendisi çalışıyor mu — yoksa kapı boş güvence verirdi."""
    lisanslar = _paket_lisanslari()
    assert "ultralytics" in lisanslar, "ultralytics pakette bulunamadi (tespit bozuk olabilir)"
    assert _kopyleft_mu(lisanslar["ultralytics"]), f"AGPL tespit edilemedi: {lisanslar['ultralytics']!r}"


def test_LGPL_kopyleft_SAYILMAZ():
    """LGPL kasıtlı dışarıda: dinamik bağlamada kapalı kaynak ürünle dağıtılabilir."""
    assert not _kopyleft_mu("LGPL-2.1")
    assert not _kopyleft_mu("GNU Lesser General Public License v3 (LGPLv3)")
    assert not _kopyleft_mu("GNU Library or Lesser General Public License (LGPL)")
    assert _kopyleft_mu("AGPL-3.0") and _kopyleft_mu("GPL-3.0")


@pytest.mark.parametrize(
    "lisans",
    [
        "GPL",  # yalın klasik `License: GPL` — eski sınıflandırıcı KAÇIRIYORDU
        "LGPL-2.1 AND GPL-3.0",  # bileşik ifade: LGPL geçtiği için TAMAMI muaf sayılıyordu
        "GPL-2.0-only",
        "GPLv2+",
        "AGPL-3.0-or-later",
        "GNU General Public License v3 (GPLv3)",
        "GNU Affero General Public License v3",
    ],
)
def test_KRITIK_kopyleft_siniflandirici_GPL_bicimlerini_TANIR(lisans):
    """D4.08 (B-10.94): yeni bir GPL bağımlılık bu biçimlerden biriyle gelirse kopyleft kapısına GÖRÜNMEZDİ."""
    assert _kopyleft_mu(lisans), f"kopyleft TANINMADI: {lisans!r}"


@pytest.mark.parametrize("lisans", ["MIT", "BSD-3-Clause", "Apache-2.0", "MPL-2.0", "PSF-2.0", "", "LGPL-3.0-or-later"])
def test_KARSIT_KANIT_kopyleft_OLMAYAN_lisans_kopyleft_SAYILMAZ(lisans):
    assert not _kopyleft_mu(lisans), f"kopyleft OLMAYAN lisans kopyleft sayıldı: {lisans!r}"


def test_KRITIK_sahte_pakette_GPL_bagimlilik_YAKALANIR(tmp_path):
    """Uçtan uca (paket GEREKMEZ — CI'da koşar): sahte `base-deps.zip`te iki dist-info; gerçek ayrıştırıcı +
    sınıflandırıcı ikisini de kopyleft bulmalı (`License: GPL` + GPLv3 sınıflandırıcısı; PEP 639 bileşik ifade)."""
    from scripts.lisans_envanteri_uret import paket_lisanslari

    sahte = tmp_path / "base-deps.zip"
    with zipfile.ZipFile(sahte, "w") as z:
        z.writestr(
            "PEMF_Backend/_internal/gplpaket-1.0.dist-info/METADATA",
            "Name: gplpaket\nLicense: GPL\nClassifier: License :: OSI Approved :: GNU General Public License v3 (GPLv3)\n",
        )
        z.writestr(
            "PEMF_Backend/_internal/karisik-2.0.dist-info/METADATA",
            "Name: karisik\nLicense-Expression: LGPL-2.1 AND GPL-3.0\n",
        )
        z.writestr("PEMF_Backend/_internal/mitpaket-3.0.dist-info/METADATA", "Name: mitpaket\nLicense: MIT\n")
    lisanslar = {ad: lic for ad, (_s, lic) in paket_lisanslari(sahte).items()}
    assert set(lisanslar) == {"gplpaket", "karisik", "mitpaket"}, lisanslar
    kopyleft = {ad for ad, lic in lisanslar.items() if _kopyleft_mu(lic)}
    assert kopyleft == {"gplpaket", "karisik"}, f"kopyleft kümesi yanlış: {kopyleft} ({lisanslar})"


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
