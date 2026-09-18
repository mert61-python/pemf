# -*- coding: utf-8 -*-
# Author: mertaygn
"""BOBİN SAYISI TEK KAYNAK — İş 5'in ÜÇÜNCÜ kaçağı (denetim 2026-09-12).

===============================================================================
NE İSTENMİŞTİ (İş 5, 2026-09-12)
===============================================================================
Sahip: "seans detayında donanım eps kalmış ve bobin 8 de görünüyor ama aslında
çalışmıyor 7 bobinli sistem bunu da düzelt."

Düzeltme `SessionDetailModal` ve kontrol ekranı için yapılmıştı. ⚠️ **Ana Ekran
atlanmıştı** — sahibin ekran görüntüsünde hâlâ görünen yer tam olarak orasıydı:

  · bobin kartları `snapshot.coils` listesinin TAMAMINI çiziyordu → sökülü ESP slotu
    kalıcı "Offline" bir kart olarak sunuluyordu (var olmayan donanım)
  · rozet ve ölçüm kartı `"/8"` SABİTİNİ yazıyordu → payda hiçbir zaman dolmadığı için
    7/7 bağlıyken bile sistem "7/8" yani EKSİK görünüyordu

⚠️ SINIF: "aynı kural N yerde kopyalanmış" — bu depoda tekrar eden arıza sınıfı.
Tek kaynak `services/bobinGorunurlugu.ts` ZATEN vardı ve `espSlotuGorunur` yardımcısı
bile "başlık 1–8 mi 1–7 mi yazacak" diye yorumlanmıştı; Ana Ekran ona hiç bağlanmamıştı.

===============================================================================
NEDEN KAYNAK ÇIPASI (davranış testi değil)
===============================================================================
Payda/süzgeç ekranda hesaplanıyor; bir sonraki geliştirici `coils.length` yerine yeniden
sabit `8` yazarsa hiçbir davranış testi bunu yakalamaz — kart yine çizilir, sayı yine
görünür, yalnız YANLIŞ olur. Bu kapı, kuralın tek kaynaktan okunduğunu ölçer.

⚠️ Yorumlar `c_soy` ile SOYULUR: bu depoda "yorum kapıyı kandırdı" ALTI kez oldu.
"""

from __future__ import annotations

import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))
if str(KOK / "tests") not in sys.path:
    sys.path.insert(0, str(KOK / "tests"))

_PF = KOK / "apps" / "ui" / "src"

#: Bobin ızgarası çizen / bobin sayısı yazan üretim ekranları.
BOBIN_CIZEN_EKRANLAR = (
    "screens/DashboardScreen.tsx",
    "screens/ControlScreen.tsx",
)


def _kaynak(bagil: str) -> str:
    from c_soyucu import c_soy

    return c_soy((_PF / bagil).read_text(encoding="utf-8"))


def test_KRITIK_bobin_cizen_ekranlar_TEK_KAYNAGI_kullanir():
    """⚠️ ASIL KAPI — hayalet bobin 8 kartı.

    MUTASYON: `DashboardScreen`de `gorunurBobinler(snapshot.coils ?? [])` yerine
    `snapshot.coils ?? []` yaz → KIRMIZI (sökülü ESP slotu yeniden çizilir).
    """
    for ekran in BOBIN_CIZEN_EKRANLAR:
        src = _kaynak(ekran)
        assert "gorunurBobinler(" in src, (
            f"{ekran} bobin gorunurlugu tek kaynagini KULLANMIYOR -> sokulu ESP slotu "
            "hayalet 'Offline' kart olarak cizilir (sahip Is 5)"
        )


def test_KRITIK_bobin_paydasi_SABIT_8_DEGIL():
    """⚠️ "7 bobinli sistem" — sabit payda sistemi DAİMA eksik gösterir.

    MUTASYON: `${coilTotal}` yerine `8` yaz → KIRMIZI.
    """
    for ekran in BOBIN_CIZEN_EKRANLAR:
        src = _kaynak(ekran)
        for yasak in ("/8 ", "/ 8`", "/8`", "} / 8", "}/8"):
            assert yasak not in src, (
                f"{ekran} bobin paydasini SABIT 8 yaziyor ({yasak!r}) -> 7 bobinli sistemde "
                "7/7 bagliyken bile ekran '7/8' yani EKSIK gosterir"
            )


def test_KRITIK_STM_bobin_sayisi_tek_yerde_TANIMLI():
    """Payda dinamik olsa bile fiziksel sayı ikinci bir yerde sabitlenirse ayrışır.

    MUTASYON: `bobinGorunurlugu.ts`deki `STM_BOBIN_SAYISI = 7`i 8 yap → KIRMIZI.
    """
    kaynak = _kaynak("services/bobinGorunurlugu.ts")
    assert "STM_BOBIN_SAYISI = 7" in kaynak, (
        "STM bobin sayisi tek kaynagi 7 DEGIL -> sokulu ESP yeniden fiziksel bobin sayilir"
    )


def test_KARSIT_KANIT_ESP_slotu_GERI_GELEBILIR():
    """Karşıt kanıt: kural "slot 8'i sonsuza dek yok say"a KAYMAMALI.

    Sahip ESP kodunun SİLİNMEMESİNİ, ileride hibrit sisteme dönebilmeyi şart koştu.
    Tek kaynak, slot 8 ortaya çıkınca (bağlı YA DA çalışıyor) onu yeniden çizer; ekranlar
    da paydayı ondan türettiği için sayı kendiliğinden 8 olur.
    """
    kaynak = _kaynak("services/bobinGorunurlugu.ts")
    assert "Boolean(c.connected) || Boolean(c.running)" in kaynak, (
        "slot 8 geri gelis yolu KAPANMIS -> ESP takilsa bile ekranda gorunmez ve "
        "enerjili bobin DURDURULAMAZ (2026-09-11 saha arizasi)"
    )
    # ...ve Ana Ekran paydayı görünür listeden türetmeli, sabitten değil.
    src = _kaynak("screens/DashboardScreen.tsx")
    assert "coilTotal" in src and "coils.length" in src, (
        "Ana Ekran paydayi gorunur listeden turetmiyor -> ESP geri takilinca sayi yanlis kalir"
    )
