# Author: mertaygn, cglrgrkn
"""
PDF Rapor Oluşturucu
Veteriner PEMF tedavi seansları için profesyonel PDF raporları oluşturur
"""

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List

# Add parent directory to path for imports
# ⚠️ Depo koku SABIT DERINLIKLE bulunmaz (2026-09-18, F4): modul `apps/backend/utils/`
# altina indi, "bir ust dizin" artik kok DEGIL.
from utils.path_utils import kaynak_kokunu_bul

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = str(kaynak_kokunu_bul(__file__))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

try:
    # DENETIM P1 (SSRF + askida kalma): ReportLab'in mini-XML ayristiricisi <img src="http://...">
    # gorunce TIMEOUT'SUZ urlopen ile o adrese gider. Serbest-metin hasta notu PDF'e boyle
    # girdiginde LAN'daki bir istemci backend'i keyfi bir adrese GET atmaya zorlayabiliyor ve
    # yanit gelmezse SENKRON uc FastAPI threadpool'unu (vars. 40) kilitleyip API'yi yanit veremez
    # hale getiriyordu. Dis kaynak cozumlemesini TAMAMEN kapat: rapor icin gerekli degil.
    import reportlab.rl_config as _rl_config
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm, inch
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    _rl_config.trustedHosts = []  # hicbir dis host cozulmez
    _rl_config.trustedSchemes = []  # http/https/ftp/file semalari kapali
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


from database.treatment_history_db import get_treatment_db

from utils import ceviri
from utils.seans_durum import hedef_etiketi, mod_etiketi

# DENETIM P2: rapor sorgulari SABIT limit=1000 kullaniyordu → yogun bir klinikte en yeni 1000
# seansin DISINDA kalan kayitlar rapora SESSIZCE girmiyordu (hasta raporunda eksik gecmis;
# ID ile ACIKCA istenen seanslar ise hic uyari vermeden dusuyordu). Limit yukseltildi ve
# kirpilma/eksik-ID durumlari artik GORUNUR loglaniyor — sessiz eksik tibbi rapor kabul edilemez.
_HISTORY_FETCH_LIMIT = 50000


def _esc(text) -> str:
    """Serbest-metni ReportLab mini-XML'ine vermeden ONCE kacir.

    DENETIM P1: kullanici yazdigi metin (hasta notu, hasta adi) HIC kacirilmadan Paragraph'a
    veriliyordu. Iki sonuc: (1) <img src="http://..."> ile SSRF/askida kalma (bkz. rl_config
    sertlestirmesi), (2) '<b>kalin' gibi KAPANMAMIS bir etiket ValueError firlatip o seansin
    PDF'ini KALICI olarak 500 yapiyordu. Kacirma ikisini de kokten keser: metin artik veri,
    biçimlendirme dili degil.
    """
    from xml.sax.saxutils import escape

    return escape("" if text is None else str(text))


def _fmt_hms(epoch) -> str:
    """Epoch saniyeyi HH:MM:SS'e çevir; None/geçersizse '-'."""
    if epoch is None:
        return "-"
    try:
        return datetime.fromtimestamp(float(epoch)).strftime("%H:%M:%S")
    except (ValueError, OSError, OverflowError, TypeError):
        return "-"


def _fmt_num(v, fmt: str = "{:.1f}") -> str:
    """Sayıyı biçimle (varsayılan 1 ondalık); None/geçersizse '-' (str fallback)."""
    if v is None:
        return "-"
    try:
        return fmt.format(float(v))
    except (ValueError, TypeError):
        return str(v)


class PDFReportGenerator:
    """PEMF tedavi raporları için PDF oluşturucu"""

    def __init__(self, app_data_dir=None):
        """
        PDF rapor oluşturucuyu başlat

        Args:
            app_data_dir: Uygulama veri dizini (Path veya str). None ise varsayılan konum kullanılır.
        """
        self.logger = logging.getLogger(__name__)

        # app_data_dir'yi belirle
        if app_data_dir is None:
            # Varsayılan app_data_dir'yi bul
            try:
                from utils.path_utils import get_app_data_directory

                app_data_dir = get_app_data_directory()
            except Exception as e:
                self.logger.warning(f"app_data_dir alınamadı, varsayılan kullanılıyor: {e}")
                # ⚠️ 2026-10-18: burada `from pathlib import Path` vardı → Python `Path`'i TÜM __init__ için YEREL sayıyordu;
                # dizgi `app_data_dir` verilince aşağıdaki `Path(app_data_dir)` UnboundLocalError atıyordu. Modül düzeyindeki
                # `Path` kullanılır.
                app_data_dir = Path.home() / ".pemf_gui"

        # Path'e çevir
        if isinstance(app_data_dir, str):
            app_data_dir = Path(app_data_dir)

        self.app_data_dir = app_data_dir
        self.db = get_treatment_db(app_data_dir)

        if not REPORTLAB_AVAILABLE:
            raise ImportError("ReportLab kütüphanesi gerekli. 'pip install reportlab' komutunu çalıştırın.")

        # Türkçe karakter desteği için font kaydet
        self._register_fonts()

        # Stil ayarları
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    #: ⚠️ ReportLab'in GÖMÜLÜ (base-14) Type1 yazı tipleri. HİÇBİRİ Türkçe `ı ş ğ İ Ş Ğ`
    #: taşımaz — WinAnsi kodlamasında o kod noktaları YOKTUR; ReportLab sessizce "notdef"
    #: (siyah kutu) basar, hata da vermez, log da yazmaz.
    #: ⚠️ SAHİP BİLDİRİMİ (2026-09-12): "kaydedilen pdf ler seans için karakter hatası var
    #: siyah kutucuk koyulmuş ı harflerine mesela." ÖLÇÜLDÜ: `styles['Heading3']` ==
    #: Helvetica-BoldOblique → "Bobin Çalışmaları" PDF'te "Bobin ÇalIImalarI" çıkıyordu.
    #: Symbol/ZapfDingbats BİLEREK dışarıda: onlar metin değil, simge yazı tipidir.
    TYPE1_METIN_FONTLARI = frozenset(
        {
            "Helvetica",
            "Helvetica-Bold",
            "Helvetica-Oblique",
            "Helvetica-BoldOblique",
            "Times-Roman",
            "Times-Bold",
            "Times-Italic",
            "Times-BoldItalic",
            "Courier",
            "Courier-Bold",
            "Courier-Oblique",
            "Courier-BoldOblique",
        }
    )

    #: Denenecek Unicode yazı tipi AİLELERİ: (aile_adı, normal, kalın, italik, kalın-italik).
    #: ⚠️ DÖRT YÜZ BİRDEN: eskiden yalnız normal+kalın kaydediliyordu ve hazır stil sayfasının
    #: italik isteyen stilleri (`Heading3` → *-BoldOblique) Type1'e DÜŞÜYORDU. Arızanın kökü buydu.
    FONT_AILELERI = (
        (
            "Arial-Unicode",
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/ariali.ttf",
            "C:/Windows/Fonts/arialbi.ttf",
        ),
        (
            "DejaVu-Unicode",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf",
        ),
        (
            "DejaVu-Unicode",
            "C:/Windows/Fonts/DejaVuSans.ttf",
            "C:/Windows/Fonts/DejaVuSans-Bold.ttf",
            "C:/Windows/Fonts/DejaVuSans-Oblique.ttf",
            "C:/Windows/Fonts/DejaVuSans-BoldOblique.ttf",
        ),
        (
            "Mac-Unicode",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/System/Library/Fonts/Supplemental/Arial Italic.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold Italic.ttf",
        ),
    )

    def _register_fonts(self):
        """Türkçe karakter desteği: bir Unicode ailenin DÖRT YÜZÜNÜ birden kaydet.

        ⚠️ NEDEN DÖRT YÜZ: ReportLab'in hazır stil sayfası kalın ve İTALİK yüz ister
        (`Heading3` = *-BoldOblique). Kayıtlı olmayan yüz Type1 Helvetica'ya düşer ve
        Türkçe harfler siyah kutuya döner — sahibin bildirdiği arızanın TAM kökü.

        ⚠️ EKSİK YÜZ KABUL EDİLİR, EKSİK AİLE EDİLMEZ: normal yüz bulunamazsa bu aile
        atlanır. Bulunan normalin yanında kalın/italik yoksa o rol NORMALE düşer — Type1'e
        DEĞİL. (Kalınlığı kaybetmek okunaklıdır; harfi kaybetmek değildir.)
        """
        # ⚠️ DÖRT ALAN DA HER DURUMDA TANIMLI: tablo stilleri bunları `getattr` ile okur ve
        # tanımsız kalan biri sessizce Type1'e düşerdi (arızanın ikinci kapısı).
        self.unicode_font = 'Helvetica'
        self.unicode_font_bold = 'Helvetica-Bold'
        self.unicode_font_italic = 'Helvetica-Oblique'
        self.unicode_font_bold_italic = 'Helvetica-BoldOblique'
        for aile, normal, kalin, italik, kalin_italik in self.FONT_AILELERI:
            try:
                if not os.path.exists(normal):
                    continue
                pdfmetrics.registerFont(TTFont(aile, normal))
                self.unicode_font = aile
                self.unicode_font_bold = self._yuz_kaydet(f"{aile}-Bold", kalin, aile)
                self.unicode_font_italic = self._yuz_kaydet(f"{aile}-Italic", italik, aile)
                self.unicode_font_bold_italic = self._yuz_kaydet(f"{aile}-BoldItalic", kalin_italik, aile)
                # ⚠️ AİLE KAYDI `<b>` / `<i>` İŞARETLEMESİ İÇİN ŞART: Paragraph içindeki
                # `<b>Hasta Notları:</b>` aile bağı olmadan kalın yüzü BULAMAZ ve ReportLab
                # sentetik kalınlaştırma yerine Type1'e düşebilir.
                pdfmetrics.registerFontFamily(
                    aile,
                    normal=self.unicode_font,
                    bold=self.unicode_font_bold,
                    italic=self.unicode_font_italic,
                    boldItalic=self.unicode_font_bold_italic,
                )
                self.logger.info("Unicode yazi tipi ailesi kaydedildi: %s", aile)
                return
            except Exception as e:
                self.logger.warning("Yazi tipi ailesi kaydedilemedi (%s): %s", aile, e)
        self.logger.warning("Unicode yazi tipi BULUNAMADI -> Helvetica. PDF'te Turkce harfler siyah kutu gorunebilir.")

    def _yuz_kaydet(self, ad: str, yol: str, yedek: str) -> str:
        """Tek bir yüzü kaydet; dosya yoksa/bozuksa `yedek` (normal yüz) adını döndür.

        ⚠️ YEDEK NORMAL YÜZDÜR, Helvetica DEĞİL: eksik kalın yüz yüzünden Type1'e düşmek,
        düzeltmek istediğimiz arızayı geri getirirdi.
        """
        try:
            if os.path.exists(yol):
                pdfmetrics.registerFont(TTFont(ad, yol))
                return ad
        except Exception as e:
            self.logger.warning("Yazi tipi yuzu kaydedilemedi (%s): %s", ad, e)
        return yedek

    def _unicode_yuz(self, type1_adi: str) -> str:
        """Bir base-14 Type1 adını, AYNI kalınlık/eğiklikteki Unicode yüze eşler."""
        kalin = "Bold" in type1_adi
        egik = ("Oblique" in type1_adi) or ("Italic" in type1_adi)
        if kalin and egik:
            return self.unicode_font_bold_italic
        if kalin:
            return self.unicode_font_bold
        if egik:
            return self.unicode_font_italic
        return self.unicode_font

    def _stilleri_unicode_yap(self):
        """Stil sayfasındaki HER Type1 metin stilini Unicode yüze çevirir.

        ⚠️ NOKTA DÜZELTME YETMEZ: arıza `styles['Heading3']`te bulundu ama aynı sınıftaki
        `Normal`, `Heading1/2`, `BodyText`, `Italic`, `Bullet`... hepsi Type1'di. Üç çağrıyı
        elle düzeltmek dördüncüsünü bir sonraki geliştiriciye bırakırdı. Kapı: bu döngüden
        SONRA hiçbir stilde base-14 metin fontu KALMAMALI (test_pdf_turkce_karakter.py).
        """
        if self.unicode_font in self.TYPE1_METIN_FONTLARI:
            return  # hicbir Unicode yuz bulunamadi; cevirecek bir sey yok
        for stil in self.styles.byName.values():
            ad = getattr(stil, "fontName", None)
            if ad in self.TYPE1_METIN_FONTLARI:
                stil.fontName = self._unicode_yuz(ad)
            alt = getattr(stil, "bulletFontName", None)
            if alt in self.TYPE1_METIN_FONTLARI:
                stil.bulletFontName = self._unicode_yuz(alt)

    def _setup_custom_styles(self):
        """Rapor için özel paragraf stillerini kaydet (Unicode font varsa onu, yoksa Helvetica)."""
        font_name = getattr(self, 'unicode_font', 'Helvetica')
        font_bold = getattr(self, 'unicode_font_bold', 'Helvetica-Bold')
        # Stil tanımları veri-güdümlü: her biri bir spec sözlüğü → tek döngüde eklenir.
        specs = [
            dict(
                name='CustomTitle',
                parent=self.styles['Title'],
                fontName=font_bold,
                fontSize=18,
                spaceAfter=30,
                alignment=TA_CENTER,
                textColor=colors.darkblue,
            ),
            dict(
                name='SectionHeader',
                parent=self.styles['Heading2'],
                fontName=font_bold,
                fontSize=14,
                spaceAfter=12,
                spaceBefore=20,
                textColor=colors.darkblue,
                borderWidth=1,
                borderColor=colors.darkblue,
                borderPadding=5,
            ),
            dict(
                name='PatientInfo',
                parent=self.styles['Normal'],
                fontName=font_name,
                fontSize=11,
                spaceAfter=6,
                leftIndent=20,
            ),
            dict(
                name='Footer',
                parent=self.styles['Normal'],
                fontName=font_name,
                fontSize=8,
                alignment=TA_CENTER,
                textColor=colors.grey,
            ),
            dict(name='UnicodeNormal', parent=self.styles['Normal'], fontName=font_name, fontSize=10, spaceAfter=6),
        ]
        for spec in specs:
            self.styles.add(ParagraphStyle(**spec))
        # ⚠️ EN SONDA: hazır stil sayfasından gelen HER Type1 metin stilini de Unicode yüze
        # çevir. Rapor bunlardan bazılarını doğrudan kullanıyor (`Heading3`, `Normal`) ve
        # orada Türkçe harfler siyah kutu oluyordu (sahip bildirimi 2026-09-12).
        self._stilleri_unicode_yap()

    def generate_session_report(
        self,
        session_ids: List[int],
        output_path: str = None,
        include_patient_info: bool = True,
        include_statistics: bool = True,
    ) -> str:
        """
        Seçili seanslar için PDF raporu oluştur

        Args:
            session_ids: Rapor edilecek seans ID'leri
            output_path: Çıktı dosya yolu
            include_patient_info: Hasta bilgilerini dahil et
            include_statistics: İstatistikleri dahil et

        Returns:
            str: Oluşturulan PDF dosya yolu
        """
        try:
            # ⚠️ D2-3.4 (2-D incelemesi): "Toplam Seans" BULUNAN seans sayısıdır; yinelenen kimlik tek seans; bulunamayan (silinmiş)
            # seans PDF'in KENDİSİNDE söylenir. Eskiden başlık istenen kimlik sayısını yazıyor (silinmiş seçimde "2" başlık / 1 seans;
            # hiçbiri yokken "1" başlık / seanssız PDF), eksik seans yalnız günlükte kalıyordu.
            # Kapı: tests/test_pdf_TOPLAM_SEANS_bulunan_seanslarla_TUTARLI_D234.py
            session_ids = list(dict.fromkeys(int(x) for x in session_ids))
            bulunan = self._fetch_sessions(session_ids)
            output_path = output_path or self._default_output_path("PEMF_Tedavi_Raporu")
            story = []
            self._add_header(story)
            self._add_report_info(story, len(bulunan))
            if len(bulunan) < len(session_ids):
                _ek = {"istenen": len(session_ids), "eksik": len(session_ids) - len(bulunan)}
                story.append(Paragraph(_esc(ceviri.t("pdf.seans.uyariEksik", **_ek)), self.styles['UnicodeNormal']))
            if include_statistics:
                self._add_statistics_section(story, session_ids)
            self._add_sessions_section(story, session_ids, include_patient_info)
            self._add_footer(story)
            return self._build_pdf(story, output_path, "PDF raporu")
        except Exception as e:
            self.logger.error(f"PDF raporu oluşturma hatası: {e}")
            raise

    def generate_patient_report(
        self, patient_name: str, start_date: str = None, end_date: str = None, output_path: str = None
    ) -> str:
        """
        Belirli bir hasta için kapsamlı rapor oluştur

        Args:
            patient_name: Hasta adı
            start_date: Başlangıç tarihi (YYYY-MM-DD)
            end_date: Bitiş tarihi (YYYY-MM-DD)
            output_path: Çıktı dosya yolu

        Returns:
            str: Oluşturulan PDF dosya yolu
        """
        try:
            patient_sessions = self._get_patient_sessions(patient_name, start_date, end_date)
            output_path = output_path or self._default_output_path("PEMF_Hasta_Raporu", patient_name)
            story = []
            self._add_header(story)
            self._add_patient_header(story, patient_sessions[0], patient_name)
            self._add_patient_statistics(story, patient_sessions)
            self._add_patient_treatment_history(story, patient_sessions)
            self._add_footer(story)
            return self._build_pdf(story, output_path, "Hasta raporu")
        except Exception as e:
            self.logger.error(f"Hasta raporu oluşturma hatası: {e}")
            raise

    def generate_xai_report(
        self,
        baslik: str,
        ogeler: list,
        output_path: str = None,
        ust_baslik: str | None = None,
        alt_baslik: str | None = None,
        alt_bilgi: str | None = None,
    ) -> str:
        """XAI toplu çıktısını PDF'e derle (xai-entegrasyon-plani §KALAN B — opsiyonel XAI görseli).

        Args:
            baslik: rapor üst başlığı (serbest metin — kaçırılır)
            ogeler: [{"etiket": str, "goruntu": str|Path|None, "aciklama": str|None, "satirlar": [str]|None}, ...]
            output_path: çıktı .pdf yolu (None → masaüstü, zaman damgalı)
            ust_baslik / alt_baslik / alt_bilgi: sayfa başlığı, alt başlığı ve altbilgisi (None → tedavi raporu varsayılanları).
                2026-10-18 (sahip: AI analiz raporu "tamamen türkçe ve anlaşılır olmalı"): AI analiz PDF'i "PEMF TEDAVİ RAPORU"
                ve İngilizce alt başlık / altbilgi YERİNE kendi Türkçe metnini verir.

        Görüntüsü olmayan öğe yalnız metin satırı olur; OKUNAMAYAN görüntü öğeyi
        DÜŞÜRMEZ (uyarı + metin — zarif düşüş: tek bozuk PNG raporu 500 yapmamalı). `satirlar` madde madde yazılır.
        """
        from reportlab.lib.utils import ImageReader

        output_path = output_path or self._default_output_path("PEMF_XAI_Raporu")
        story = []
        if ust_baslik is None and alt_baslik is None:
            self._add_header(story)
        else:
            self._add_header(story, ust_baslik or "", alt_baslik or "")
        story.append(Paragraph(_esc(baslik), self.styles['SectionHeader']))
        story.append(Spacer(1, 8))
        for oge in ogeler:
            story.append(Paragraph(f"<b>{_esc(oge.get('etiket', '-'))}</b>", self.styles['UnicodeNormal']))
            g = oge.get('goruntu')
            if g:
                try:
                    # Ön-doğrulama (düşman-doğrulama 2026-08-27): ReportLab görüntüyü doc.build
                    # ANINDA çözer — bozuk/dev tek görüntü o aşamada TÜM PDF'i düşürüyordu.
                    # PIL ile burada tam decode edilir ki hata bu öğenin zarif-düşüş dalına düşsün.
                    from PIL import Image as _PilImage

                    with _PilImage.open(str(g)) as _im:
                        _im.load()
                    iw, ih = ImageReader(str(g)).getSize()
                    # A4 metin alanına sığdır (en-boy korunur): maks 15cm genişlik / 16cm yükseklik
                    olcek = min((15 * cm) / iw, (16 * cm) / ih, 1.0)
                    story.append(Image(str(g), width=iw * olcek, height=ih * olcek))
                except Exception as e:
                    self.logger.warning("XAI raporu: görüntü okunamadı, metinle geçildi (%s): %s", g, e)
                    story.append(
                        Paragraph(_esc(ceviri.t("pdf.xai.goruntuOkunamadi", g=g)), self.styles['UnicodeNormal'])
                    )
            if oge.get('aciklama'):
                story.append(Paragraph(_esc(oge['aciklama']), self.styles['UnicodeNormal']))
            for satir in oge.get('satirlar') or []:
                story.append(Paragraph("• " + _esc(str(satir)), self.styles['UnicodeNormal']))
            story.append(Spacer(1, 12))
        self._add_footer(story, alt_bilgi)
        return self._build_pdf(story, output_path, "XAI raporu")

    def _default_output_path(self, prefix: str, name_hint: str = "") -> str:
        """Masaüstünde zaman-damgalı çıktı yolu üret (opsiyonel güvenli-karakterli hasta-adı parçası)."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        desktop = os.path.expanduser("~/Desktop")
        if name_hint:
            safe = "".join(c for c in name_hint if c.isalnum() or c in (' ', '-', '_')).rstrip()
            return os.path.join(desktop, f"{prefix}_{safe}_{timestamp}.pdf")
        return os.path.join(desktop, f"{prefix}_{timestamp}.pdf")

    def _build_pdf(self, story, output_path: str, label: str) -> str:
        """Story'yi A4 (2cm kenar boşluğu) PDF'e derle, logla ve yolu döndür."""
        doc = SimpleDocTemplate(
            output_path, pagesize=A4, rightMargin=2 * cm, leftMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm
        )
        doc.build(story)
        self.logger.info(f"{label} oluşturuldu: {output_path}")
        return output_path

    def _get_patient_sessions(self, patient_name: str, start_date, end_date):
        """Tam-ada göre (opsiyonel tarih aralığı) hasta seanslarını getir; hiç yoksa ValueError."""
        sessions = self.db.get_session_history(
            limit=_HISTORY_FETCH_LIMIT, start_date=start_date, end_date=end_date, internal_full=True
        )
        if len(sessions) >= _HISTORY_FETCH_LIMIT:
            self.logger.warning(
                "Hasta raporu: gecmis %d kayitta KIRPILDI — rapor EKSIK olabilir (tarih araligi daraltin).",
                _HISTORY_FETCH_LIMIT,
            )
        # ⚠️ TÜRKÇE-GÜVENLİ KARŞILAŞTIRMA (saha bulgusu 2026-08-30): eskiden iki taraf da
        # `str.lower()` kullanıyordu. `patient_name` bir HTTP parametresi (kullanıcı/istemci
        # girişi); DB'deki adla arasında herhangi bir case-dönüşümü olursa 'İ'/'I' tuzağı
        # yüzünden "seans bulunamadı" hatası doğuyordu (hasta adı raporu üretilemiyordu).
        # Arama indeksiyle AYNI katlamayı kullanır (utils.turkce_metin) → ayrışma imkânsız.
        from utils.turkce_metin import arama_katla

        _hedef = arama_katla(patient_name or "")
        patient_sessions = [
            s
            for s in sessions
            # None-güvenli: SQL NULL → Python None; .get(k, '') anahtar VAR ama None ise None döner
            # → str+None TypeError → PDF daima 500 (Audit P1). `or ''` hem eksik hem None'u boşa çevirir.
            if arama_katla((s.get('patient_name') or '') + ' ' + (s.get('patient_surname') or '')) == _hedef
        ]
        if not patient_sessions:
            raise ValueError(f"'{patient_name}' adlı hasta için seans bulunamadı")
        return patient_sessions

    def _fetch_sessions(self, session_ids):
        """Verilen ID'lerin seanslarını getir — geçmişten TEK sorgu + ID eşleme (döngü-içi tekrar
        sorgu yok). session_ids sırasını korur; bulunamayanları atlar.

        ⚠️ D2.28 (B-3.68): istenen kimlikler SQL'e GEÇER (`session_ids`). Eskiden geçmişin en yeni `_HISTORY_FETCH_LIMIT` seansı
        çekilip Python'da eşleniyordu: o pencerenin dışındaki AÇIKÇA seçilmiş seans rapora girmiyor, "Toplam Seans" ile istatistik
        çelişiyordu (her raporda tüm geçmiş belleğe de çekiliyordu). Kapı: tests/test_pdf_secili_seans_SQL_suzgeci_D228.py"""
        istenen = sorted({int(x) for x in session_ids})
        if not istenen:
            return []
        by_id = {
            s['id']: s for s in self.db.get_session_history(limit=len(istenen), internal_full=True, session_ids=istenen)
        }
        found = [by_id[sid] for sid in session_ids if sid in by_id]
        missing = [sid for sid in session_ids if sid not in by_id]
        if missing:
            # ACIKCA istenen seans rapora GIRMEDI → sessizce atlamak tibbi raporu yaniltir.
            self.logger.error(
                "PDF raporu: istenen %d seans bulunamadi ve rapora GIRMEDI: %s", len(missing), missing[:20]
            )
        return found

    def _add_header(
        self,
        story,
        baslik: str | None = None,
        alt_baslik: str | None = None,
    ):
        """Rapor başlığını ekle (boş başlık / alt başlık yazılmaz; verilmezse varsayılan — rapor dilinde)."""
        # I18N: varsayılan argüman tanım anında (içe aktarmada) değerlendirilirdi → dil donardı. None → çağrı anında çeviri.
        if baslik is None:
            baslik = ceviri.t("pdf.baslik.varsayilan")
        if alt_baslik is None:
            alt_baslik = ceviri.t("pdf.baslik.altVarsayilan")
        # Logo (eğer varsa)
        logo_path = Path(__file__).parent / "assets" / "pemf_logo.png"
        if logo_path.exists():
            try:
                logo = Image(str(logo_path), width=2 * inch, height=1 * inch)
                story.append(logo)
                story.append(Spacer(1, 12))
            except Exception:
                pass

        # Ana başlık
        if baslik:
            story.append(Paragraph(_esc(baslik), self.styles['CustomTitle']))

        # Alt başlık
        if alt_baslik:
            subtitle = Paragraph(_esc(alt_baslik), self.styles['Normal'])
            subtitle.alignment = TA_CENTER
            story.append(subtitle)
        story.append(Spacer(1, 20))

    def _add_report_info(self, story, session_count):
        """Rapor bilgilerini ekle"""
        report_date = datetime.now().strftime("%d/%m/%Y %H:%M")

        info_data = [
            [ceviri.t("pdf.bilgi.raporTarihi"), report_date],
            [ceviri.t("pdf.bilgi.toplamSeans"), str(session_count)],
            [ceviri.t("pdf.bilgi.raporTuru"), ceviri.t("pdf.bilgi.seansGecmisiRaporu")],
        ]

        info_table = Table(info_data, colWidths=[3 * cm, 5 * cm])
        info_table.setStyle(
            TableStyle(
                [
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (0, -1), getattr(self, 'unicode_font_bold', 'Helvetica-Bold')),
                    ('FONTNAME', (1, 0), (1, -1), getattr(self, 'unicode_font', 'Helvetica')),
                    ('FONTSIZE', (0, 0), (-1, -1), 10),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ]
            )
        )

        story.append(info_table)
        story.append(Spacer(1, 20))

    def _add_statistics_section(self, story, session_ids):
        """İstatistik bölümünü ekle (toplam/ortalama süre + tedavi-modu dağılımı)."""
        story.append(Paragraph(ceviri.t("pdf.seans.istatistikler"), self.styles['SectionHeader']))
        sessions = self._fetch_sessions(session_ids)
        if not sessions:
            story.append(Paragraph(ceviri.t("pdf.seans.istatistikYok"), self.styles['UnicodeNormal']))
            return
        story.append(self._build_stats_table(sessions))
        story.append(Spacer(1, 20))

    def _build_stats_table(self, sessions) -> "Table":
        """Seans listesinden özet istatistik tablosu (toplam/ortalama süre + mod sayıları)."""
        total_duration = sum(s.get('duration_minutes', 0) or 0 for s in sessions)
        avg_duration = total_duration / len(sessions) if sessions else 0
        mode_counts = {}
        for session in sessions:
            mode = session.get('treatment_mode', ceviri.t("ai.deger.unknown"))
            mode_counts[mode] = mode_counts.get(mode, 0) + 1

        stats_data = [
            [ceviri.t("pdf.seans.toplamSeansSayisi"), str(len(sessions))],
            [ceviri.t("pdf.seans.toplamTedaviSuresi"), ceviri.t("pdf.sure.dakika", n=total_duration)],
            [ceviri.t("pdf.seans.ortalamaSeansSuresi"), ceviri.t("pdf.sure.dakika", n=f"{avg_duration:.1f}")],
        ]
        for mode, count in mode_counts.items():
            stats_data.append(
                [ceviri.t("pdf.seans.modu", mode=mod_etiketi(mode)), ceviri.t("pdf.seans.seansSayisi", count=count)]
            )

        table = Table(stats_data, colWidths=[6 * cm, 4 * cm])
        table.setStyle(
            TableStyle(
                [
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (0, -1), getattr(self, 'unicode_font_bold', 'Helvetica-Bold')),
                    ('FONTNAME', (1, 0), (1, -1), getattr(self, 'unicode_font', 'Helvetica')),
                    ('FONTSIZE', (0, 0), (-1, -1), 10),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),
                    ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
                ]
            )
        )
        return table

    def _add_sessions_section(self, story, session_ids, include_patient_info):
        """Seans detayları bölümünü ekle"""
        story.append(Paragraph(ceviri.t("pdf.seans.tedaviSeanslari"), self.styles['SectionHeader']))
        sessions = self._fetch_sessions(session_ids)
        sessions.sort(key=lambda x: (x.get('session_date', ''), x.get('start_time', '')))

        for i, session in enumerate(sessions, 1):
            self._add_single_session(story, session, i, include_patient_info)
            if i < len(sessions):
                story.append(Spacer(1, 15))

    def _add_single_session(self, story, session, session_num, include_patient_info):
        """Tek seans detayını ekle: başlık + bilgi tablosu + hasta notları + bobin çalışmaları."""
        tarih = _esc(session.get('session_date', ceviri.t("ai.deger.unknown")))
        title = ceviri.t("pdf.seans.baslik", no=session_num, tarih=tarih)
        story.append(Paragraph(title, self.styles['Heading3']))

        details = self.db.get_session_details(session.get('id'))
        parameters = details.get('parameters', {}) if details else {}
        rows = self._session_info_rows(session, parameters, include_patient_info)

        session_table = Table(rows, colWidths=[4 * cm, 6 * cm])
        session_table.setStyle(
            TableStyle(
                [
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (0, -1), getattr(self, 'unicode_font_bold', 'Helvetica-Bold')),
                    ('FONTNAME', (1, 0), (1, -1), getattr(self, 'unicode_font', 'Helvetica')),
                    ('FONTSIZE', (0, 0), (-1, -1), 9),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),
                    ('BACKGROUND', (0, 0), (0, -1), colors.lightblue),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ]
            )
        )
        story.append(session_table)

        # Hasta notları (varsa)
        patient_notes = session.get('patient_notes', '')
        if patient_notes:
            story.append(Spacer(1, 10))
            story.append(Paragraph(ceviri.t("pdf.seans.hastaNotlari"), self.styles['UnicodeNormal']))
            story.append(Paragraph(_esc(patient_notes), self.styles['PatientInfo']))

        # Bobin çalışmaları tablosu (best-effort; hata olursa mevcut PDF'i bozmadan atla).
        try:
            self._add_coil_runs_table(story, session.get('id'))
        except Exception as e:
            self.logger.warning(f"Bobin calismalari tablosu atlandi (session {session.get('id')}): {e}")

    @staticmethod
    def _format_duration(parameters: dict, session: dict) -> str:
        """Süre gösterimi: parametrelerdeki dinamik değer öncelikli, yoksa duration_minutes.
        Tam sayıysa ondalıksız, değilse 1 ondalık; geçersiz/boşsa '0'."""
        duration = (
            parameters.get('duration', {}).get('value')
            if 'duration' in parameters
            else session.get('duration_minutes', 0) or 0
        )
        if duration and str(duration).replace('.', '').isdigit():
            d = float(duration)
            return f"{d:.0f}" if d == int(d) else f"{d:.1f}"
        return "0"

    def _session_info_rows(self, session: dict, parameters: dict, include_patient_info: bool):
        """Seans bilgi tablosunun satırları; istenirse hasta bilgileri araya eklenir (aynı sıra)."""
        rows = [
            [ceviri.t("gecmis.csv.tarih"), session.get('session_date', ceviri.t("ai.deger.unknown"))],
            [ceviri.t("pdf.seans.baslangicSaati"), session.get('start_time', ceviri.t("ai.deger.unknown"))],
            [ceviri.t("pdf.seans.bitisSaati"), session.get('end_time', ceviri.t("ai.deger.unknown"))],
            [ceviri.t("pdf.seans.sure"), ceviri.t("pdf.sure.dakika", n=self._format_duration(parameters, session))],
            [
                ceviri.t("pdf.seans.tedaviModu"),
                mod_etiketi(session.get('treatment_mode', ceviri.t("ai.deger.unknown"))),
            ],
            [
                ceviri.t("pdf.seans.hedefDurum"),
                hedef_etiketi(session.get('target_condition', ceviri.t("pdf.belirtilmemis"))),
            ],
            [
                ceviri.t("pdf.seans.frekans"),
                f"{parameters.get('frequency', {}).get('value', session.get('frequency_hz', 0)) or 0} Hz",
            ],
            # ⚠️ DENETİM 2026-08-09 (Tier 2) — "Yoğunluk: X mT" SATIRI KALDIRILDI.
            # Operatörün girdiği mT değeri CİHAZA HİÇ ULAŞMIYOR: STM binary paketi
            # (`<BB 5f 5f 5f 5I H` = duty/phase/freq/duration) ve ESP MQTT komutu
            # (`freq/duty/phase/duration`) alan sanki YOK. Değer yalnız DB'ye yazılıyor.
            # Bu satır, hasta sahibine giden bir raporda UYGULANMAMIŞ bir dozu uygulanmış gibi
            # gösteriyordu — üçüncü kişiye yanlış tıbbi beyan. Gerçek çözüm firmware'dedir
            # (paketi genişlet + osiloskopla doğrula); o yapılana kadar rapor bunu İDDİA ETMEZ.
            [
                ceviri.t("pdf.seans.veteriner"),
                parameters.get('patient_vet_contact', {}).get(
                    'value', session.get('operator_name', ceviri.t("pdf.belirtilmemis"))
                ),
            ],
        ]
        if include_patient_info:
            # ⚠️ SEANS SATIRINA DÜŞ (kampanya bulgusu S18-EK, 2026-08-14). Eskiden ad YALNIZCA
            # `parameters`tan okunuyordu; oysa `patient_name` seans satırında ÜST DÜZEYDE durur
            # (CSV/JSON oradan okuduğu için DOĞRUydu) ve `parameters` çoğu kayıtta adı içermez →
            # PDF her seans için "Hasta Adı: Bilinmiyor" yazıyordu. Bu bir TIBBİ RAPORDUR ve
            # hasta sahibine/başka kliniğe gider; kime ait olduğu belirsiz bir tedavi kaydı
            # hukuken ve tıbben kullanılamaz. `patient_vet_contact` satırı bu deseni zaten
            # kullanıyordu — hasta adına uygulanmamıştı.
            # ⚠️ SIRALAMA HAKKINDA DÜZELTME (ilk yazımım yanlıştı): "parameters öncelikli, seans
            # satırı yedek" gerekçesi ÜRETİMDE GEÇERSİZDİR — `_fetch_sessions` satırları
            # `get_session_history`ten gelir ve o SQL zaten `COALESCE(sp_name.parameter_value,
            # ts.patient_name)` yapar (treatment_history_db.py:2079). Yani `session['patient_name']`
            # parametre değerini ZATEN içerir; iki kaynağın çelişmesi imkânsızdır ve tek başına
            # `session.get('patient_name')` eşdeğer olurdu. Zincir yine de KORUNDU: bu fonksiyon
            # elle kurulmuş sözlüklerle de (testler, olası başka çağıranlar) doğru çalışsın.
            # ⚠️ `session['patient_surname']` üretimde HEP None'dır (`sp_surname` COALESCE'siz ve
            # oraya yazan yok) — savunma amaçlı duruyor, çalıştığı iddia EDİLMİYOR.
            patient_name = parameters.get('patient_name', {}).get('value', '') or session.get('patient_name') or ''
            patient_surname = (
                parameters.get('patient_surname', {}).get('value', '') or session.get('patient_surname') or ''
            )
            patient_full_name = f"{patient_name} {patient_surname}".strip()
            rows.insert(4, [ceviri.t("pdf.seans.hastaAdi"), patient_full_name or ceviri.t("ai.deger.unknown")])
            rows.insert(
                5,
                [
                    ceviri.t("pdf.seans.hastaYasi"),
                    parameters.get('patient_age', {}).get('value', ceviri.t("pdf.belirtilmemis")),
                ],
            )
            rows.insert(
                6,
                [
                    ceviri.t("pdf.seans.turIrk"),
                    f"{parameters.get('patient_species', {}).get('value', '')} / {parameters.get('patient_breed', {}).get('value', '')}".strip(
                        ' /'
                    ),
                ],
            )
            rows.insert(
                7,
                [
                    ceviri.t("pdf.seans.agirlik"),
                    parameters.get('patient_weight', {}).get('value', ceviri.t("pdf.belirtilmemis")),
                ],
            )
            rows.insert(
                8,
                [
                    ceviri.t("pdf.seans.sahip"),
                    parameters.get('patient_owner', {}).get('value', ceviri.t("pdf.belirtilmemis")),
                ],
            )
        return rows

    def _add_coil_runs_table(self, story, session_id):
        """Bir seansın bobin çalışmalarını PDF tablosu olarak ekle.
        Veri yoksa hiçbir şey eklemez. Sıcaklık/akım özeti sensor_run_summary'den."""
        if session_id is None:
            return
        runs = self.db.get_session_coil_runs(session_id)
        if not runs:
            return
        summaries = self.db.get_run_summaries(session_id)
        story.append(Spacer(1, 10))
        story.append(Paragraph(ceviri.t("pdf.seans.bobinCalismalari"), self.styles['Heading3']))
        story.append(self._build_coil_runs_table(runs, summaries))

    def _build_coil_runs_table(self, runs, summaries) -> "Table":
        """Bobin çalışması kayıtlarını başlıklı + stilli ReportLab Table'ına dönüştür."""
        # ⚠️ "Şiddet (mT)" → "Ayarlanan (mT)": değer operatörün GİRDİĞİ hedeftir, cihazın
        # uyguladığı ölçülmüş bir şiddet DEĞİLDİR (STM/ESP paketlerinde mT alanı yok).
        # Klinik-içi bir tabloda kaydı tutmak meşru; "şiddet" demek ölçülmüş gibi okutur.
        table_data = [
            [
                ceviri.t("gecmis.csv.bobin"),
                ceviri.t("pdf.seans.saat"),
                ceviri.t("pdf.seans.sureSn"),
                "Hz",
                "Duty (%)",
                ceviri.t("pdf.seans.ayarlananMt"),
                ceviri.t("pdf.seans.ortSic"),
                ceviri.t("pdf.seans.maksSic"),
            ]
        ]
        for r in runs:
            summ = summaries.get(r.get('id')) or {}
            table_data.append(
                [
                    str(r.get('coil_id', '-')),
                    _fmt_hms(r.get('started_epoch')),
                    _fmt_num(r.get('duration_seconds'), "{:.0f}"),
                    _fmt_num(r.get('frequency_hz'), "{:.0f}"),
                    _fmt_num(r.get('duty_percent'), "{:.0f}"),
                    _fmt_num(r.get('intensity_mt')),
                    _fmt_num(summ.get('temp_avg')),
                    _fmt_num(summ.get('temp_max')),
                ]
            )

        table = Table(
            table_data, colWidths=[1.4 * cm, 2 * cm, 1.8 * cm, 1.4 * cm, 1.6 * cm, 2 * cm, 2.2 * cm, 2.2 * cm]
        )
        table.setStyle(
            TableStyle(
                [
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), getattr(self, 'unicode_font_bold', 'Helvetica-Bold')),
                    ('FONTNAME', (0, 1), (-1, -1), getattr(self, 'unicode_font', 'Helvetica')),
                    ('FONTSIZE', (0, 0), (-1, -1), 8),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),
                    ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ]
            )
        )
        return table

    def _add_patient_header(self, story, session, patient_name):
        """Hasta raporu başlığını ekle"""
        story.append(
            Paragraph(ceviri.t("pdf.hasta.baslik", ad=_esc(patient_name).upper()), self.styles['SectionHeader'])
        )

        # Hasta bilgileri - Parametrelerden al
        session_details = self.db.get_session_details(session.get('id'))
        parameters = session_details.get('parameters', {}) if session_details else {}

        # ⚠️ BELGE KENDİ İÇİNDE ÇELİŞMESİN (2026-08-14). Başlık satırı adı sorgu parametresinden
        # taşıdığı için "HASTA RAPORU: PAMUK" yazarken, tablo "Hasta Adı: Belirtilmemiş" diyordu:
        # aynı sayfada iki farklı beyan. Sebep `_session_info_rows`takiyle AYNI — ad yalnızca
        # `session_parameters`tan okunuyordu, oysa hiçbir üretim yolu oraya `patient_name` yazmaz
        # (tek yazılan seans-parametresi `patient_owner_email`). Ad, seans satırında durur.
        patient_info = [
            [
                ceviri.t("pdf.hasta.adi"),
                parameters.get('patient_name', {}).get('value')
                or session.get('patient_name')
                or ceviri.t("pdf.belirtilmemis"),
            ],
            [
                ceviri.t("pdf.hasta.soyadi"),
                parameters.get('patient_surname', {}).get('value')
                or session.get('patient_surname')
                or ceviri.t("pdf.belirtilmemis"),
            ],
            [ceviri.t("pdf.hasta.yas"), parameters.get('patient_age', {}).get('value', ceviri.t("pdf.belirtilmemis"))],
            [
                ceviri.t("pdf.hasta.tur"),
                parameters.get('patient_species', {}).get('value', ceviri.t("pdf.belirtilmemis")),
            ],
            [
                ceviri.t("pdf.hasta.irk"),
                parameters.get('patient_breed', {}).get('value', ceviri.t("pdf.belirtilmemis")),
            ],
            [
                ceviri.t("pdf.hasta.agirlik"),
                parameters.get('patient_weight', {}).get('value', ceviri.t("pdf.belirtilmemis")),
            ],
            [
                ceviri.t("pdf.hasta.sahip"),
                parameters.get('patient_owner', {}).get('value', ceviri.t("pdf.belirtilmemis")),
            ],
            [
                ceviri.t("pdf.hasta.veteriner"),
                parameters.get('patient_vet_contact', {}).get('value', ceviri.t("pdf.belirtilmemis")),
            ],
            [ceviri.t("pdf.hasta.ilkTedavi"), session.get('session_date', ceviri.t("ai.deger.unknown"))],
        ]

        patient_table = Table(patient_info, colWidths=[3 * cm, 7 * cm])
        patient_table.setStyle(
            TableStyle(
                [
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (0, -1), getattr(self, 'unicode_font_bold', 'Helvetica-Bold')),
                    ('FONTNAME', (1, 0), (1, -1), getattr(self, 'unicode_font', 'Helvetica')),
                    ('FONTSIZE', (0, 0), (-1, -1), 11),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ]
            )
        )

        story.append(patient_table)
        story.append(Spacer(1, 20))

    def _add_patient_statistics(self, story, sessions):
        """Hasta istatistiklerini ekle"""
        story.append(Paragraph(ceviri.t("pdf.hasta.istatistikler"), self.styles['SectionHeader']))

        total_sessions = len(sessions)
        total_duration = sum(s.get('duration_minutes', 0) or 0 for s in sessions)
        avg_duration = total_duration / total_sessions if total_sessions else 0

        # Tarih aralığı
        dates = [s.get('session_date', '') for s in sessions if s.get('session_date')]
        first_date = min(dates) if dates else ceviri.t("ai.deger.unknown")
        last_date = max(dates) if dates else ceviri.t("ai.deger.unknown")

        stats_data = [
            [ceviri.t("pdf.seans.toplamSeansSayisi"), str(total_sessions)],
            [ceviri.t("pdf.seans.toplamTedaviSuresi"), ceviri.t("pdf.sure.dakika", n=total_duration)],
            [ceviri.t("pdf.seans.ortalamaSeansSuresi"), ceviri.t("pdf.sure.dakika", n=f"{avg_duration:.1f}")],
            [ceviri.t("pdf.hasta.ilkTedaviTarihi"), first_date],
            [ceviri.t("pdf.hasta.sonTedaviTarihi"), last_date],
        ]

        stats_table = Table(stats_data, colWidths=[5 * cm, 5 * cm])
        stats_table.setStyle(
            TableStyle(
                [
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (0, -1), getattr(self, 'unicode_font_bold', 'Helvetica-Bold')),
                    ('FONTNAME', (1, 0), (1, -1), getattr(self, 'unicode_font', 'Helvetica')),
                    ('FONTSIZE', (0, 0), (-1, -1), 10),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),
                    ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
                ]
            )
        )

        story.append(stats_table)
        story.append(Spacer(1, 20))

    def _add_patient_treatment_history(self, story, sessions):
        """Hasta tedavi geçmişini ekle"""
        story.append(Paragraph(ceviri.t("pdf.hasta.tedaviGecmisi"), self.styles['SectionHeader']))

        # Seansları tarihe göre sırala
        sessions.sort(key=lambda x: (x.get('session_date', ''), x.get('start_time', '')))

        # Tablo başlıkları
        table_data = [
            # "Yoğunluk (mT)" sütunu KALDIRILDI — bkz. yukarıdaki not (cihaza ulaşmayan değer).
            [
                ceviri.t("gecmis.csv.tarih"),
                ceviri.t("pdf.hasta.sureDk"),
                ceviri.t("gecmis.csv.mod"),
                ceviri.t("pdf.hasta.frekansHz"),
                ceviri.t("gecmis.csv.hedef"),
            ]
        ]

        for session in sessions:
            row = [
                session.get('session_date', ceviri.t("ai.deger.unknown")),
                str(session.get('duration_minutes', 0) or 0),
                mod_etiketi(session.get('treatment_mode', ceviri.t("ai.deger.unknown"))),
                str(session.get('frequency_hz', 0) or 0),
                hedef_etiketi(session.get('target_condition', ceviri.t("pdf.belirtilmemis"))),
            ]
            table_data.append(row)

        history_table = Table(table_data, colWidths=[2.5 * cm, 1.5 * cm, 2 * cm, 2 * cm, 2 * cm, 3 * cm])
        history_table.setStyle(
            TableStyle(
                [
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), getattr(self, 'unicode_font_bold', 'Helvetica-Bold')),
                    ('FONTNAME', (0, 1), (-1, -1), getattr(self, 'unicode_font', 'Helvetica')),
                    ('FONTSIZE', (0, 0), (-1, -1), 8),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),
                    ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
                ]
            )
        )

        story.append(history_table)

    def _add_footer(self, story, metin: str | None = None):
        """Rapor alt bilgisini ekle (`metin` verilirse o + rapor tarihi)."""
        story.append(Spacer(1, 30))
        if metin:
            story.append(
                Paragraph(
                    _esc(
                        ceviri.t("pdf.altBilgi.tarihli", metin=metin, tarih=datetime.now().strftime('%d.%m.%Y %H:%M'))
                    ),
                    self.styles['Footer'],
                )
            )
            return

        footer_text = ceviri.t("pdf.altBilgi.varsayilan", tarih=datetime.now().strftime('%d/%m/%Y %H:%M'))

        footer = Paragraph(footer_text, self.styles['Footer'])
        story.append(footer)


def get_pdf_generator(app_data_dir=None):
    """
    PDF rapor oluşturucu singleton instance'ını döndür

    Args:
        app_data_dir: Uygulama veri dizini (Path veya str). None ise varsayılan konum kullanılır.
    """
    if not hasattr(get_pdf_generator, '_instance') or get_pdf_generator._instance is None:
        get_pdf_generator._instance = PDFReportGenerator(app_data_dir)
    return get_pdf_generator._instance


# Test fonksiyonu
if __name__ == "__main__":
    try:
        from pathlib import Path

        # Test için varsayılan app_data_dir
        test_app_data_dir = Path.home() / ".pemf_gui"
        test_app_data_dir.mkdir(parents=True, exist_ok=True)

        generator = PDFReportGenerator(app_data_dir=test_app_data_dir)

        # Test raporu oluştur
        test_sessions = [1, 2, 3]  # Test seans ID'leri
        output_file = generator.generate_session_report(session_ids=test_sessions, output_path="test_report.pdf")

        print(f"Test raporu oluşturuldu: {output_file}")

    except Exception as e:
        print(f"Test hatası: {e}")
        import traceback

        traceback.print_exc()
