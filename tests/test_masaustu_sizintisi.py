# -*- coding: utf-8 -*-
# Author: mertaygn
"""SÜİT SAHİBİN MASAÜSTÜNE DOSYA BIRAKAMAZ — 2026-09-11 saha bulgusu.

===============================================================================
NE OLDU
===============================================================================
Sahip: "masaüstüne neden sürekli csv kaydı olmaya devam ediyor, uygulama açık bile
değil." Masaüstünde 18 adet `PEMF_alan_*.csv` birikmişti. İçerikleri:

    # seans,react_1789147282749_69
    # patient_name,Boncuk
    # operator_name,op

...yani TEST FIXTURE verisi. Zaman damgaları test süiti koşularıyla birebir
örtüşüyordu. Uygulama gerçekten hiç açılmamıştı.

KÖK NEDEN: `/session/start` yolundan geçen testler `api_server._seans_alan`
SINGLETON'ını tetikliyor; o da `masaustu_dizini()` → `~/Desktop` çözüp oraya
GERÇEKTEN yazıyordu. Yalnız kendi fixture'ında yolu yamalayan iki test temizdi.

===============================================================================
⚠️ BU NEDEN SADECE "ÇÖP DOSYA" DEĞİL
===============================================================================
1. Dosyalar hasta adı taşıyor. Test verisi bugün uydurma; süit gerçek bir klinik
   makinesinde koşarsa aynı yol GERÇEK hasta adıyla dosya üretir.
2. Sahip bu dosyaları CİHAZIN ÜRETTİĞİ ÖLÇÜM sanıp bana gönderdi — teşhis bir
   süre yanlış veriyle yapıldı.
3. `masaustu_dizini()` masaüstünü bulamazsa `Path.cwd()`e düşer: o durumda süit
   DEPO DİZİNİNE dosya saçar.

Aynı sınıf daha önce veri kökünde yaşandı (`test_veri_dizini_izolasyonu.py`,
2026-08-08). Koruma yazılmıştı ama 2026-09-11'de eklenen masaüstü yoluna
UYGULANMAMIŞTI. Bu dosya o boşluğu kapatır.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))


def _gercek_masaustu_adaylari() -> list[Path]:
    """Üretimdeki `masaustu_dizini()` ile AYNI adaylar — çıpa kendi listesini uydurmaz."""
    ev = Path(os.path.expanduser("~"))
    return [ev / "Desktop", ev / "OneDrive" / "Desktop", ev / "Masaüstü"]


def _masaustu_dosyalari() -> set[Path]:
    bulunan: set[Path] = set()
    for aday in _gercek_masaustu_adaylari():
        if aday.is_dir():
            bulunan |= set(aday.glob("PEMF_alan_*.csv"))
            bulunan |= set(aday.glob("PEMF_*.pdf"))
    return bulunan


# ============================================================================
# 1. ⚠️ ASIL KAPI — seans başlatmak gerçek masaüstüne DOKUNMAZ
# ============================================================================


def test_KRITIK_seans_kaydi_GERCEK_masaustune_YAZMAZ():
    """Üretim singleton'ıyla bir seans açılır ve gerçek masaüstü ÖNCE/SONRA karşılaştırılır.

    ⚠️ Bu test üretim nesnesini (`servers.seans_alan_kaydi.seans_alan_kaydi`) kullanır,
    kendi kopyasını DEĞİL: sızdıran yol tam olarak oydu. Kendi örneğini kurup ölçmek
    arızayı GÖREMEZDİ.

    MUTASYON: `conftest._masaustunu_koru` fixture'ını sil → KIRMIZI (dosya gerçekten
    masaüstünde belirir).
    """
    from servers.seans_alan_kaydi import seans_alan_kaydi

    onceki = _masaustu_dosyalari()
    yol = seans_alan_kaydi.seans_basladi(
        "SIZINTI-KAPISI",
        {"patient_name": "SizintiTesti", "operator_name": "op", "mode": "Manuel"},
    )
    try:
        assert yol is not None, "kayit hic acilamadi -> bu test hicbir sey olcmuyor"
        sonraki = _masaustu_dosyalari()
        yeni = sonraki - onceki
        assert not yeni, (
            "SUIT GERCEK MASAUSTUNE YAZDI: "
            f"{sorted(str(p.name) for p in yeni)} -> sahibin masaustune test cop dosyasi "
            "birakiyoruz (gercek bir klinik makinesinde HASTA ADIYLA dosya uretir)"
        )
        # Karşıt kanıt: dosya bir yere yazıldı, sadece doğru yere.
        assert yol.exists(), "CSV hicbir yere yazilmadi -> izolasyon dosyayi YUTMUS"
    finally:
        seans_alan_kaydi.seans_bitti("kapi testi")


def test_KRITIK_yazilan_yol_gercek_masaustunun_ALTINDA_DEGIL():
    """Yol düzeyinde kontrol: dosya adı değil, DİZİNİ ölçülür.

    Bir önceki test "yeni dosya belirdi mi" diye bakar; bu test "nereye yazıyoruz"
    diye sorar. İkisi ayrı: izolasyon dosyayı gerçek masaüstünün bir ALT KLASÖRÜNE
    yazsaydı ilk test yine yeşil kalırdı (glob alt klasöre inmiyor).
    """
    from servers.seans_alan_kaydi import seans_alan_kaydi

    yol = seans_alan_kaydi.seans_basladi("SIZINTI-YOL", {"patient_name": "YolTesti"})
    try:
        assert yol is not None
        cozulmus = yol.resolve()
        for aday in _gercek_masaustu_adaylari():
            if not aday.exists():
                continue
            assert not cozulmus.is_relative_to(aday.resolve()), f"CSV gercek masaustunun ALTINA yazildi: {cozulmus}"
    finally:
        seans_alan_kaydi.seans_bitti("kapi testi")


# ============================================================================
# 2. İZOLASYON GERÇEKTEN KURULU MU (fixture sessizce düşerse yakala)
# ============================================================================


def test_KRITIK_masaustu_cozucusu_TEST_SIRASINDA_yamalanmis():
    """`_masaustunu_koru` yamayı `try/except` içinde kuruyor — sessizce düşebilir.

    O zaman yukarıdaki kapılar "yeni dosya yok" diye yeşil kalabilirdi (ör. seans hiç
    açılamadıysa). Bu test yamanın VARLIĞINI doğrudan ölçer.

    MUTASYON: fixture'daki `mp.setattr(_sak, "masaustu_dizini", ...)` satırını sil →
    KIRMIZI.
    """
    import servers.seans_alan_kaydi as sak

    dizin, gerekce = sak.masaustu_dizini()
    assert gerekce == "test izolasyonu", (
        f"masaustu cozucusu YAMALANMAMIS (gerekce={gerekce!r}) -> suit gercek masaustune yazabilir"
    )
    for aday in _gercek_masaustu_adaylari():
        if aday.exists():
            assert not Path(dizin).resolve().is_relative_to(aday.resolve())


def test_KRITIK_PDF_ciktisi_da_yonlendirilmis():
    """Aynı sınıfın ikinci örneği: PDF raporları da `~/Desktop`e yazıyordu.

    ⚠️ Bugün süitte sızıntı ÜRETMİYOR (masaüstünde test PDF'i yok) ama yol AÇIK.
    Sınıfı kapatmak, örneği kapatmaktan ucuzdur — CSV'de bunu geç öğrendik.
    """
    pdfmod = pytest.importorskip("utils.pdf_report_generator", reason="reportlab yok — PDF yolu bu ortamda kurulamaz")
    uretici = pdfmod.PDFReportGenerator.__new__(pdfmod.PDFReportGenerator)
    yol = Path(pdfmod.PDFReportGenerator._default_output_path(uretici, "PEMF_Rapor", "Test"))
    for aday in _gercek_masaustu_adaylari():
        if aday.exists():
            assert not yol.resolve().is_relative_to(aday.resolve()), f"PDF gercek masaustune yazilacakti: {yol}"


# ============================================================================
# 3. ÜRETİM DAVRANIŞI BOZULMADI (izolasyon fazla ileri gitmesin)
# ============================================================================


def test_uretimde_masaustu_cozumu_HALA_calisiyor(monkeypatch, tmp_path):
    """Karşıt kanıt: izolasyon üretim mantığını KÖRELTMEMELİ.

    `test_seans_alan_kaydi.py` fonksiyonu `from ... import` ile ALMIŞTIR; o bağ import
    anında kurulduğu için ORİJİNALİ gösterir ve fixture onu etkilemez. Burada aynı
    orijinal yol, sahte bir ev dizini üzerinden sınanır.
    """
    import servers.seans_alan_kaydi as sak

    # ⚠️ `from ... import masaustu_dizini` BURADA İŞE YARAMAZ: bu satır test sırasında
    # koşar ve YAMALI niteliği alır (ilk yazımda tam olarak bu oldu, test kırmızı
    # verdi). Orijinali fixture saklıyor.
    orijinal = sak._orijinal_masaustu_dizini

    sahte_ev = tmp_path / "ev"
    (sahte_ev / "Desktop").mkdir(parents=True)
    monkeypatch.setattr("os.path.expanduser", lambda _p: str(sahte_ev))
    dizin, gerekce = orijinal()
    assert dizin == sahte_ev / "Desktop" and gerekce == "masaüstü"
