# -*- coding: utf-8 -*-
# Author: mertaygn
"""KALAN JETON HAKKI KULLANICIYA GÖRÜNÜR — sahip isteği 2026-09-13.

Sahip: *"kullanıcı da kalan hakkını görmeli ama bence."*

===============================================================================
BU DOSYA NEYİ KORUYOR
===============================================================================
Bakiye göstermek kolay; **yanlış** bakiye göstermek tehlikelidir. İki sessiz yalan sınıfı var
ve ikisi de bu depoda daha önce yaşandı ("sahte değer göster" sınıfı):

1. **Ücretlendirme KAPALIYKEN "0 jeton" yazmak.** Bugün canlıda `PEMF_JETON_ENFORCED=0` ve
   hiçbir kullanıcının bakiye satırı yok. Rozet "0" yazsaydı, sınırsız çalışan bir klinikte
   operatör hakkının bittiğini sanardı. Uç bu durumda `etkin:false` döner → rozet ÇİZİLMEZ.

2. **Çevrimdışıyken "0 jeton" yazmak.** Bakiye Supabase'den okunur; klinik internetsizken okuma
   düşer. O an 0 yazmak, çalışan sistemi bitmiş gibi gösterir. Uç `bilinmiyor:true` döner →
   arayüz "—" gösterir. ⚠️ Bu ürün internetsiz çalışır (bkz. [[pemf-internetsiz-calisma...]]).

3. **Bakiyeyi sormanın jeton yakması.** `ai_router`ın bağımlılıklarında `jeton_gate` var ve
   `_islem_turu` tanımadığı yolu `"goruntu"` (1 jeton) sınıfına düşürür. Uç oraya konsaydı
   her rozet tazelemesi 1 jeton harcardı — bakiyeye bakmak bakiyeyi eritirdi. Bu yüzden uç
   `system_router`dadır ve kapı bunu ölçer.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

os.environ.setdefault("PEMF_SIMULATE", "1")


class _SahteIstek:
    """Yalnız `headers` taşıyan asgari Request ikizi."""

    def __init__(self, token: str = ""):
        self.headers = {"authorization": f"Bearer {token}"} if token else {}


@pytest.fixture
def jeton(monkeypatch):
    from servers import jeton as _j

    return _j


# ============================================================================
# 1. BAYRAK KAPALI → ROZET ÇİZİLMEZ (sahte "0" YOK)
# ============================================================================


def test_KRITIK_enforce_KAPALIYKEN_etkin_false(jeton, monkeypatch):
    """⚠️ ASIL KAPI — bugünkü canlı durum.

    MUTASYON: `bakiye_ozeti` başındaki `if not JETON_ENFORCED` dalını sil → KIRMIZI
    (kapalı sistemde "0 jeton" görünür ve operatör hakkı bitti sanır).
    """
    monkeypatch.setattr(jeton, "JETON_ENFORCED", False)
    ozet = jeton.bakiye_ozeti(_SahteIstek("abc"))
    assert ozet == {"etkin": False}, f"ucretlendirme KAPALIYKEN rozet verisi uretildi: {ozet}"
    assert "kalan" not in ozet, "kapaliyken 'kalan' alani DONMEMELI (arayuz 0 yazar)"


# ============================================================================
# 2. ÇEVRİMDIŞI → "—", ASLA 0
# ============================================================================


def test_KRITIK_okunamayinca_SIFIR_DEGIL_bilinmiyor(jeton, monkeypatch):
    """⚠️ İnternetsiz klinikte "0 jeton" yazmak, çalışan sistemi bitmiş göstermektir.

    MUTASYON: `except` dalını `return {"etkin": True, "kalan": 0}` yap → KIRMIZI.
    """
    monkeypatch.setattr(jeton, "JETON_ENFORCED", True)

    def _patla(_token):
        raise ConnectionError("ag yok")

    monkeypatch.setattr(jeton, "_bakiye_satiri_oku", _patla)
    ozet = jeton.bakiye_ozeti(_SahteIstek("abc"))
    assert ozet["etkin"] is True
    assert ozet["bilinmiyor"] is True, "okunamadi ama 'bilinmiyor' isaretlenmedi"
    assert "kalan" not in ozet, f"okunamazken SAYI donduruldu -> arayuz yanlis bakiye gosterir: {ozet}"


def test_kimliksiz_istekte_TAHMIN_URETMEZ(jeton, monkeypatch):
    """Bakiye kişiye özeldir; token yoksa başkasının sayısı gösterilemez."""
    monkeypatch.setattr(jeton, "JETON_ENFORCED", True)
    ozet = jeton.bakiye_ozeti(_SahteIstek(""))
    assert ozet["bilinmiyor"] is True and "kalan" not in ozet


# ============================================================================
# 3. GERÇEK BAKİYE DOĞRU HESAPLANIR (karşıt kanıt: kural "hep bilinmiyor de" değil)
# ============================================================================


def test_KRITIK_gercek_bakiye_AYLIK_ARTI_SATIN(jeton, monkeypatch):
    """Kalan = aylık hak + satın alınan. Tüketim sırası da bu (önce aylık).

    MUTASYON: `aylik + satin` yerine yalnız `satin` yaz → KIRMIZI.
    """
    monkeypatch.setattr(jeton, "JETON_ENFORCED", True)
    monkeypatch.setattr(
        jeton,
        "_bakiye_satiri_oku",
        lambda _t: {"aylik_hak": 40, "satin_alinan": 60, "odeme_modeli": "on_odemeli"},
    )
    ozet = jeton.bakiye_ozeti(_SahteIstek("abc"))
    assert ozet["bilinmiyor"] is False
    assert ozet["kalan"] == 100, f"kalan yanlis: {ozet}"
    assert ozet["aylikHak"] == 40 and ozet["satinAlinan"] == 60
    # Arayüz "1 analiz kaç jeton" diyebilsin diye maliyet tablosu da gider.
    assert ozet["maliyet"]["goruntu"] == 1 and ozet["maliyet"]["ai_pro_seans"] == 5


def test_KRITIK_kullandikca_modelinde_BAKIYE_DEGIL_BORC(jeton, monkeypatch):
    """Kullandıkça ödemede bakiye kavramı YOK — önden ödeme yoktur, borç birikir.

    "Kalan: 0" yazmak bu modelde düpedüz yanlış olur (kullanıcı hâlâ analiz yapabilir).

    MUTASYON: `if model == "kullandikca"` dalını sil → KIRMIZI.
    """
    monkeypatch.setattr(jeton, "JETON_ENFORCED", True)
    monkeypatch.setattr(
        jeton,
        "_bakiye_satiri_oku",
        lambda _t: {"aylik_hak": 0, "satin_alinan": 0, "odeme_modeli": "kullandikca", "kullandikca_borc": 7},
    )
    ozet = jeton.bakiye_ozeti(_SahteIstek("abc"))
    assert "kalan" not in ozet, "kullandikca modelinde 'kalan' gosterilemez (yaniltici)"
    assert ozet["borc"] == 7 and ozet["borcTavani"] == jeton.BORC_TAVANI


# ============================================================================
# 4. ⚠️ BAKİYEYİ SORMAK JETON YAKMAMALI
# ============================================================================


def test_KRITIK_bakiye_ucu_JETON_KAPISININ_ARKASINDA_DEGIL():
    """⚠️ `ai_router` bağımlılıklarında `jeton_gate` var ve `_islem_turu` tanımadığı yolu
    "goruntu" (1 jeton) sayar → uç oraya konsaydı rozeti her tazeleme 1 jeton yakardı.

    MUTASYON: ucu `ai_router`a taşı → KIRMIZI.
    """
    from servers import jeton as _j
    from servers import system_router

    yollar = {getattr(r, "path", "") for r in system_router.router.routes}
    assert "/api/jeton/bakiye" in yollar, "bakiye ucu system_router'da DEGIL"

    # Karşıt kanıt: yol gerçekten "ücretli işlem" sınıfına düşmüyor mu?
    assert _j._islem_turu("/api/jeton/bakiye") is None, (
        "bakiye yolu bir ucretli islem turune esleniyor -> bakiyeye bakmak bakiyeyi eritir"
    )


def test_GUVENLIK_yollari_hala_jetondan_BAGIMSIZ():
    """Bu turda jeton yüzeyine dokunuldu; tedavi/E-stop kapılanmadığı DEĞİŞMEZİ korunmalı."""
    from servers.jeton import GUVENLIK_YOLLARI

    for zorunlu in ("seans_baslat", "seans_durdur", "acil_durdur"):
        assert zorunlu in GUVENLIK_YOLLARI, f"{zorunlu} guvenlik yollarindan CIKARILMIS"
