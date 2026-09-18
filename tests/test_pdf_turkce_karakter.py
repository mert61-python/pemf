# -*- coding: utf-8 -*-
# Author: mertaygn
"""PDF RAPORUNDA TÜRKÇE KARAKTER — sahip bildirimi 2026-09-12.

===============================================================================
NE OLDU
===============================================================================
Sahip: "kaydedilen pdf ler seans için karakter hatası var siyah kutucuk koyulmuş
ı harflerine mesela." (Ekran görüntüsündeki başlık: "Bobin Çal##malar#")

ÖLÇÜLEN KÖK NEDEN: rapor bazı yerlerde ReportLab'in HAZIR stil sayfasını doğrudan
kullanıyordu (`styles['Heading3']` == Helvetica-BoldOblique, `styles['Normal']` ==
Helvetica). Bunlar base-14 **Type1** yazı tipleridir; WinAnsi kodlamasında
`ı ş ğ İ Ş Ğ` kod noktaları YOKTUR → ReportLab sessizce "notdef" (siyah kutu) basar.
Hata yok, uyarı yok, log yok: "çalıştı" ile "bozuk" AYNI görünüyordu.

İKİNCİ KÖK NEDEN: yalnız normal + kalın yüz kaydediliyordu. İTALİK yüz kayıtlı
olmadığı için italik isteyen HER stil zaten Type1'e düşüyordu — yalnız `Heading3`ü
elle düzeltmek arızayı bir sonraki italik stile taşırdı.

===============================================================================
BU DOSYA NE ÖLÇER
===============================================================================
· GERÇEK rapor PDF'inden ÇIKARILAN metin Türkçe harfleri taşıyor mu (uçtan uca)
· Stil sayfasında Type1 metin fontu KALDI mı (sınıfın tamamı, tek nokta değil)
· Dört yüz (normal/kalın/italik/kalın-italik) gerçekten kayıtlı mı
· Yüz bulunamadığında Type1'e değil NORMAL yüze düşülüyor mu
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

fitz = pytest.importorskip("fitz", reason="PyMuPDF yok -> PDF metni cikarilamaz")

#: Raporda GERÇEKTEN geçen, Türkçe-özel harf taşıyan başlıklar.
#: ⚠️ Çıpa sahibin ekran görüntüsündeki başlığa pinli: arıza tam orada görüldü.
TURKCE_BASLIKLAR = ("Bobin Çalışmaları", "PEMF TEDAVİ RAPORU")

#: Type1 notdef'in metin çıkarımında bıraktığı iz (ölçüldü: "Çalışmaları" -> "ÇalIImalarI").
BOZUK_IZ = "ÇalIImalarI"

#: `getattr(self, 'unicode_font', 'Helvetica')` biçimindeki Type1 yedeklerinin SABİT sayısı.
#: ⚠️ Bu yedekler artık ULAŞILAMAZ (dört alan `_register_fonts` başında her durumda atanır),
#: ama kaynakta durmaları yeni bir `getattr` çağrısının aynı hatayı kopyalamasını davet eder.
TYPE1_YEDEK_SAYISI = 16


@pytest.fixture
def rapor(tmp_path):
    """Bobin çalışması OLAN gerçek bir seans + üretilen PDF yolu."""
    from database.treatment_history_db import TreatmentHistoryDB
    from utils.pdf_report_generator import PDFReportGenerator

    kok = tmp_path / "pdf_gecmis"
    kok.mkdir(parents=True, exist_ok=True)
    db = TreatmentHistoryDB(kok)
    sid = db.start_session(treatment_mode="Manuel", patient_name="Mia")
    db.start_coil_run(
        sid,
        1,
        frequency_hz=100,
        duty_percent=50,
        phase=0,
        intensity_mt=0.0,
        hw_type="stm",
        started_epoch=1757000000.0,
    )
    db.end_session(sid, session_status="completed")

    uretici = PDFReportGenerator(kok)
    cikti = str(tmp_path / "rapor.pdf")
    uretici.generate_session_report(session_ids=[sid], output_path=cikti)
    return uretici, Path(cikti)


def _pdf_metni(yol: Path) -> str:
    with fitz.open(str(yol)) as d:
        return "\n".join(sayfa.get_text() for sayfa in d)


# ============================================================================
# 1. ⚠️ ASIL KAPI — UÇTAN UCA: PDF'TEKİ HARFLER DOĞRU
# ============================================================================


def test_KRITIK_PDF_metninde_TURKCE_harfler_DOGRU(rapor):
    """MUTASYON: `_setup_custom_styles` sonundaki `self._stilleri_unicode_yap()` çağrısını
    sil → KIRMIZI ("Bobin ÇalIImalarI" çıkar).

    Sahadaki etki: sahibin bizzat bildirdiği arıza — seans raporunda siyah kutucuklar.
    """
    metin = _pdf_metni(rapor[1])
    assert metin.strip(), "PDF metin uretmedi -> kapi olcemez"
    eksik = [b for b in TURKCE_BASLIKLAR if b not in metin]
    assert not eksik, f"PDF metninde Turkce baslik(lar) BOZUK: {eksik}\n---\n{metin[:600]}"
    assert BOZUK_IZ not in metin, "Type1 notdef izi PDFte DURUYOR (siyah kutucuk)"


def test_KRITIK_gomulu_TTF_var_Type1_degil(rapor):
    """PDF'e gerçekten yazı tipi GÖMÜLMÜŞ mü (base-14 Type1 gömülmez).

    ⚠️ Metin çıkarımı tek başına yetmez: bazı görüntüleyiciler kayıp glifi kendi sistem
    fontuyla ikame edip DOĞRU gösterebilir; aynı PDF başka bir makinede bozuk görünür.
    Gömülü yüz, taşınabilirliğin kanıtıdır.
    """
    with fitz.open(str(rapor[1])) as d:
        fontlar = [f for sayfa in d for f in sayfa.get_fonts(full=True)]
    assert fontlar, "PDF hic font tasimiyor"
    gomulu = [f for f in fontlar if f[1]]  # f[1] = uzanti ("ttf"/"cff"); gomulu degilse bos
    assert gomulu, f"PDFte GOMULU font yok -> Type1 base-14 kullanilmis: {fontlar}"


# ============================================================================
# 2. SINIFIN TAMAMI — TEK NOKTA DEĞİL
# ============================================================================


def test_KRITIK_stil_sayfasinda_Type1_metin_fontu_KALMADI(rapor):
    """⚠️ Arıza `Heading3`te bulundu ama `Normal`, `Heading1/2`, `BodyText`, `Italic`,
    `Bullet`... hepsi aynı sınıftaydı. Üç çağrıyı elle düzeltmek dördüncüsünü bir sonraki
    geliştiriciye bırakırdı.

    MUTASYON: `_stilleri_unicode_yap` gövdesindeki döngüyü sil → KIRMIZI.
    """
    uretici = rapor[0]
    kalan = {
        ad: getattr(st, "fontName", None)
        for ad, st in uretici.styles.byName.items()
        if getattr(st, "fontName", None) in uretici.TYPE1_METIN_FONTLARI
    }
    assert not kalan, f"Type1 metin fontu kullanan stil(ler) KALDI: {kalan}"


def test_KRITIK_DORT_YUZ_de_kayitli_ve_Type1_degil(rapor):
    """⚠️ İKİNCİ KÖK NEDEN: italik yüz kayıtlı olmadığı için italik isteyen HER stil
    Type1'e düşüyordu. Dört rolün dördü de Unicode yüze bağlı olmalı.

    MUTASYON: `_register_fonts`taki italik kaydını `'Helvetica-Oblique'` sabitine çevir → KIRMIZI.
    """
    u = rapor[0]
    roller = {
        "normal": u.unicode_font,
        "kalin": u.unicode_font_bold,
        "italik": u.unicode_font_italic,
        "kalin_italik": u.unicode_font_bold_italic,
    }
    type1 = {k: v for k, v in roller.items() if v in u.TYPE1_METIN_FONTLARI}
    assert not type1, f"su rol(ler) hala Type1: {type1} (tum roller: {roller})"


def test_KRITIK_eksik_yuz_Type1e_DEGIL_normale_duser():
    """⚠️ Kalın/italik dosyası olmayan bir sistemde yedek NORMAL yüz olmalı, Helvetica DEĞİL.
    Helvetica'ya düşmek düzelttiğimiz arızayı geri getirirdi (kalınlık kaybı okunaklıdır,
    harf kaybı değildir).

    MUTASYON: `_yuz_kaydet`in `return yedek` satırını `return "Helvetica-Bold"` yap → KIRMIZI.
    """
    import logging

    from utils.pdf_report_generator import PDFReportGenerator

    u = PDFReportGenerator.__new__(PDFReportGenerator)
    u.logger = logging.getLogger("test")
    assert u._yuz_kaydet("Yok-Bold", "C:/olmayan/yol/yok.ttf", "Arial-Unicode") == "Arial-Unicode"


# ============================================================================
# 3. KAYNAK ÇIPASI — ELLE TYPE1 GERİ GELMESİN
# ============================================================================


def test_KRITIK_kaynakta_Type1_yedegi_ARTMADI():
    """Tablo stilleri fontu `getattr(self, 'unicode_font', 'Helvetica')` ile okuyor.

    SABİT SAYAÇ, ">= 0" DEĞİL: sayı artarsa yeni bir Type1 kaçağı eklenmiş demektir ve o
    tabloda Türkçe harfler yine siyah kutu olur — arıza tek bir tabloda yaşamaya devam eder
    (bu deponun tekrar eden sınıfı).
    """
    src = (KOK / "apps" / "backend" / "utils" / "pdf_report_generator.py").read_text(encoding="utf-8")
    n = src.count("'Helvetica')") + src.count("'Helvetica-Bold')")
    assert n == TYPE1_YEDEK_SAYISI, (
        f"Type1 yedekli getattr sayisi {n}, beklenen {TYPE1_YEDEK_SAYISI}. Arttiysa yeni bir "
        "kacak eklenmis; azaldiysa cipa bayatladi -> sayiyi BILEREK guncelle."
    )
