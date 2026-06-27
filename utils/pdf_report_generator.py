"""
PDF Rapor Oluşturucu
Veteriner PEMF tedavi seansları için profesyonel PDF raporları oluşturur
"""

import os
import sys
import logging
from datetime import datetime
from typing import List
from pathlib import Path

# Add parent directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch, cm
    from reportlab.lib import colors
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, 
                                   TableStyle, Image)
    from reportlab.lib.enums import TA_CENTER
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import platform
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


from database.treatment_history_db import get_treatment_db


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
                from pathlib import Path
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
    
    def _register_fonts(self):
        """Türkçe karakter desteği için fontları kaydet"""
        try:
            # Windows sistem fontlarını kullan
            if platform.system() == "Windows":
                # Arial fontunu kaydet (Türkçe karakterleri destekler)
                arial_path = "C:/Windows/Fonts/arial.ttf"
                arial_bold_path = "C:/Windows/Fonts/arialbd.ttf"
                
                if os.path.exists(arial_path):
                    pdfmetrics.registerFont(TTFont('Arial-Unicode', arial_path))
                    self.unicode_font = 'Arial-Unicode'
                    self.logger.info("Arial-Unicode font kaydedildi")
                    
                    if os.path.exists(arial_bold_path):
                        pdfmetrics.registerFont(TTFont('Arial-Unicode-Bold', arial_bold_path))
                        self.unicode_font_bold = 'Arial-Unicode-Bold'
                else:
                    # Fallback: DejaVu fontlarını dene
                    self._try_dejavu_fonts()
            else:
                # Linux/Mac için DejaVu fontlarını dene
                self._try_dejavu_fonts()
                
        except Exception as e:
            self.logger.warning(f"Unicode font kaydedilemedi: {e}")
            # Fallback olarak Helvetica kullan
            self.unicode_font = 'Helvetica'
            self.unicode_font_bold = 'Helvetica-Bold'
    
    def _try_dejavu_fonts(self):
        """DejaVu fontlarını kaydetmeyi dene"""
        try:
            # DejaVu Sans fontları (çoğu Linux dağıtımında mevcut)
            dejavu_paths = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/System/Library/Fonts/DejaVuSans.ttf",
                "C:/Windows/Fonts/DejaVuSans.ttf"
            ]
            
            for path in dejavu_paths:
                if os.path.exists(path):
                    pdfmetrics.registerFont(TTFont('DejaVu-Unicode', path))
                    self.unicode_font = 'DejaVu-Unicode'
                    self.logger.info("DejaVu-Unicode font kaydedildi")
                    break
            else:
                # Hiçbir font bulunamazsa Helvetica kullan
                self.unicode_font = 'Helvetica'
                self.unicode_font_bold = 'Helvetica-Bold'
                self.logger.warning("Unicode font bulunamadı, Helvetica kullanılacak")
                
        except Exception as e:
            self.logger.warning(f"DejaVu font kaydedilemedi: {e}")
            self.unicode_font = 'Helvetica'
            self.unicode_font_bold = 'Helvetica-Bold'
    
    def _setup_custom_styles(self):
        """Özel stil ayarlarını oluştur"""
        # Unicode font varsa kullan, yoksa varsayılan font
        font_name = getattr(self, 'unicode_font', 'Helvetica')
        font_bold = getattr(self, 'unicode_font_bold', 'Helvetica-Bold')
        
        # Başlık stilleri
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Title'],
            fontName=font_bold,
            fontSize=18,
            spaceAfter=30,
            alignment=TA_CENTER,
            textColor=colors.darkblue
        ))
        
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading2'],
            fontName=font_bold,
            fontSize=14,
            spaceAfter=12,
            spaceBefore=20,
            textColor=colors.darkblue,
            borderWidth=1,
            borderColor=colors.darkblue,
            borderPadding=5
        ))
        
        self.styles.add(ParagraphStyle(
            name='PatientInfo',
            parent=self.styles['Normal'],
            fontName=font_name,
            fontSize=11,
            spaceAfter=6,
            leftIndent=20
        ))
        
        self.styles.add(ParagraphStyle(
            name='Footer',
            parent=self.styles['Normal'],
            fontName=font_name,
            fontSize=8,
            alignment=TA_CENTER,
            textColor=colors.grey
        ))
        
        # Normal metin için Unicode font stili
        self.styles.add(ParagraphStyle(
            name='UnicodeNormal',
            parent=self.styles['Normal'],
            fontName=font_name,
            fontSize=10,
            spaceAfter=6
        ))
    
    def generate_session_report(self, session_ids: List[int], 
                              output_path: str = None,
                              include_patient_info: bool = True,
                              include_statistics: bool = True) -> str:
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
            # Çıktı dosya yolu belirle (masaüstü)
            if not output_path:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                desktop_path = os.path.expanduser("~/Desktop")
                output_path = os.path.join(desktop_path, f"PEMF_Tedavi_Raporu_{timestamp}.pdf")
            
            # PDF dokümanını oluştur
            doc = SimpleDocTemplate(
                output_path,
                pagesize=A4,
                rightMargin=2*cm,
                leftMargin=2*cm,
                topMargin=2*cm,
                bottomMargin=2*cm
            )
            
            # Rapor içeriğini oluştur
            story = []
            
            # Başlık
            self._add_header(story)
            
            # Rapor bilgileri
            self._add_report_info(story, len(session_ids))
            
            # İstatistikler (eğer istenirse)
            if include_statistics:
                self._add_statistics_section(story, session_ids)
            
            # Seans detayları
            self._add_sessions_section(story, session_ids, include_patient_info)
            
            # Footer
            self._add_footer(story)
            
            # PDF'i oluştur
            doc.build(story)
            
            self.logger.info(f"PDF raporu oluşturuldu: {output_path}")
            return output_path
            
        except Exception as e:
            self.logger.error(f"PDF raporu oluşturma hatası: {e}")
            raise
    
    def generate_patient_report(self, patient_name: str, 
                              start_date: str = None,
                              end_date: str = None,
                              output_path: str = None) -> str:
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
            # Hasta seanslarını getir
            sessions = self.db.get_session_history(
                limit=1000,
                start_date=start_date,
                end_date=end_date
            )
            
            # Hasta adına göre filtrele
            patient_sessions = [
                s for s in sessions 
                if (s.get('patient_name', '') + ' ' + s.get('patient_surname', '')).strip().lower() 
                == patient_name.lower()
            ]
            
            if not patient_sessions:
                raise ValueError(f"'{patient_name}' adlı hasta için seans bulunamadı")
            
            # Çıktı dosya yolu belirle (masaüstü)
            if not output_path:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_name = "".join(c for c in patient_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
                desktop_path = os.path.expanduser("~/Desktop")
                output_path = os.path.join(desktop_path, f"PEMF_Hasta_Raporu_{safe_name}_{timestamp}.pdf")
            
            # PDF dokümanını oluştur
            doc = SimpleDocTemplate(
                output_path,
                pagesize=A4,
                rightMargin=2*cm,
                leftMargin=2*cm,
                topMargin=2*cm,
                bottomMargin=2*cm
            )
            
            story = []
            
            # Başlık
            self._add_header(story)
            
            # Hasta bilgileri
            self._add_patient_header(story, patient_sessions[0], patient_name)
            
            # Hasta istatistikleri
            self._add_patient_statistics(story, patient_sessions)
            
            # Tedavi geçmişi
            self._add_patient_treatment_history(story, patient_sessions)
            
            # Footer
            self._add_footer(story)
            
            # PDF'i oluştur
            doc.build(story)
            
            self.logger.info(f"Hasta raporu oluşturuldu: {output_path}")
            return output_path
            
        except Exception as e:
            self.logger.error(f"Hasta raporu oluşturma hatası: {e}")
            raise
    
    def _add_header(self, story):
        """Rapor başlığını ekle"""
        # Logo (eğer varsa)
        logo_path = Path(__file__).parent / "assets" / "pemf_logo.png"
        if logo_path.exists():
            try:
                logo = Image(str(logo_path), width=2*inch, height=1*inch)
                story.append(logo)
                story.append(Spacer(1, 12))
            except Exception:
                pass
        
        # Ana başlık
        title = Paragraph("PEMF TEDAVİ RAPORU", self.styles['CustomTitle'])
        story.append(title)
        
        # Alt başlık
        subtitle = Paragraph(
            "Pulsed Electromagnetic Field Therapy - Veteriner Uygulaması",
            self.styles['Normal']
        )
        subtitle.alignment = TA_CENTER
        story.append(subtitle)
        story.append(Spacer(1, 20))
    
    def _add_report_info(self, story, session_count):
        """Rapor bilgilerini ekle"""
        report_date = datetime.now().strftime("%d/%m/%Y %H:%M")
        
        info_data = [
            ["Rapor Tarihi:", report_date],
            ["Toplam Seans:", str(session_count)],
            ["Rapor Türü:", "Tedavi Geçmişi Raporu"]
        ]
        
        info_table = Table(info_data, colWidths=[3*cm, 5*cm])
        info_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), getattr(self, 'unicode_font_bold', 'Helvetica-Bold')),
            ('FONTNAME', (1, 0), (1, -1), getattr(self, 'unicode_font', 'Helvetica')),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        
        story.append(info_table)
        story.append(Spacer(1, 20))
    
    def _add_statistics_section(self, story, session_ids):
        """İstatistik bölümünü ekle"""
        story.append(Paragraph("İSTATİSTİKLER", self.styles['SectionHeader']))
        
        # Seansları getir
        sessions = []
        for session_id in session_ids:
            session_data = self.db.get_session_history(limit=1000)
            session = next((s for s in session_data if s['id'] == session_id), None)
            if session:
                sessions.append(session)
        
        if not sessions:
            story.append(Paragraph("İstatistik verisi bulunamadı.", self.styles['UnicodeNormal']))
            return
        
        # İstatistikleri hesapla
        total_duration = sum(s.get('duration_minutes', 0) or 0 for s in sessions)
        avg_duration = total_duration / len(sessions) if sessions else 0
        
        # Tedavi modları dağılımı
        mode_counts = {}
        for session in sessions:
            mode = session.get('treatment_mode', 'Bilinmiyor')
            mode_counts[mode] = mode_counts.get(mode, 0) + 1
        
        # İstatistik tablosu
        stats_data = [
            ["Toplam Seans Sayısı", str(len(sessions))],
            ["Toplam Tedavi Süresi", f"{total_duration} dakika"],
            ["Ortalama Seans Süresi", f"{avg_duration:.1f} dakika"],
        ]
        
        for mode, count in mode_counts.items():
            stats_data.append([f"{mode} Modu", f"{count} seans"])
        
        stats_table = Table(stats_data, colWidths=[6*cm, 4*cm])
        stats_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), getattr(self, 'unicode_font_bold', 'Helvetica-Bold')),
            ('FONTNAME', (1, 0), (1, -1), getattr(self, 'unicode_font', 'Helvetica')),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
        ]))
        
        story.append(stats_table)
        story.append(Spacer(1, 20))
    
    def _add_sessions_section(self, story, session_ids, include_patient_info):
        """Seans detayları bölümünü ekle"""
        story.append(Paragraph("TEDAVİ SEANSLARI", self.styles['SectionHeader']))
        
        # Seansları getir ve sırala
        sessions = []
        for session_id in session_ids:
            session_data = self.db.get_session_history(limit=1000)
            session = next((s for s in session_data if s['id'] == session_id), None)
            if session:
                sessions.append(session)
        
        # Tarihe göre sırala
        sessions.sort(key=lambda x: (x.get('session_date', ''), x.get('start_time', '')))
        
        for i, session in enumerate(sessions, 1):
            self._add_single_session(story, session, i, include_patient_info)
            if i < len(sessions):
                story.append(Spacer(1, 15))
    
    def _add_single_session(self, story, session, session_num, include_patient_info):
        """Tek seans detayını ekle"""
        # Seans başlığı
        session_title = f"Seans {session_num} - {session.get('session_date', 'Bilinmiyor')}"
        story.append(Paragraph(session_title, self.styles['Heading3']))
        
        # Seans detaylarını ve parametrelerini al
        session_details = self.db.get_session_details(session.get('id'))
        parameters = session_details.get('parameters', {}) if session_details else {}
        
        # Dinamik süreyi kontrol et
        duration = parameters.get('duration', {}).get('value') if 'duration' in parameters else session.get('duration_minutes', 0) or 0
        if duration and str(duration).replace('.', '').isdigit():
            duration_display = f"{float(duration):.0f}" if float(duration) == int(float(duration)) else f"{float(duration):.1f}"
        else:
            duration_display = "0"
        
        # Seans bilgileri tablosu
        session_data = [
            ["Tarih", session.get('session_date', 'Bilinmiyor')],
            ["Başlangıç Saati", session.get('start_time', 'Bilinmiyor')],
            ["Bitiş Saati", session.get('end_time', 'Bilinmiyor')],
            ["Süre", f"{duration_display} dakika"],
            ["Tedavi Modu", session.get('treatment_mode', 'Bilinmiyor')],
            ["Hedef Durum", session.get('target_condition', 'Belirtilmemiş')],
            ["Frekans", f"{parameters.get('frequency', {}).get('value', session.get('frequency_hz', 0)) or 0} Hz"],
            ["Yoğunluk", f"{parameters.get('intensity', {}).get('value', session.get('intensity_mt', 0)) or 0} mT"],
            ["Veteriner", parameters.get('patient_vet_contact', {}).get('value', session.get('operator_name', 'Belirtilmemiş'))],
        ]
        
        # Hasta bilgileri (eğer istenirse)
        if include_patient_info:
            patient_name = parameters.get('patient_name', {}).get('value', '') or ''
            patient_surname = parameters.get('patient_surname', {}).get('value', '') or ''
            patient_full_name = f"{patient_name} {patient_surname}".strip()
            
            session_data.insert(4, ["Hasta Adı", patient_full_name or 'Bilinmiyor'])
            session_data.insert(5, ["Hasta Yaşı", parameters.get('patient_age', {}).get('value', 'Belirtilmemiş')])
            session_data.insert(6, ["Tür/Irk", f"{parameters.get('patient_species', {}).get('value', '')} / {parameters.get('patient_breed', {}).get('value', '')}".strip(' /')])
            session_data.insert(7, ["Ağırlık", parameters.get('patient_weight', {}).get('value', 'Belirtilmemiş')])
            session_data.insert(8, ["Sahip", parameters.get('patient_owner', {}).get('value', 'Belirtilmemiş')])
        
        session_table = Table(session_data, colWidths=[4*cm, 6*cm])
        session_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), getattr(self, 'unicode_font_bold', 'Helvetica-Bold')),
            ('FONTNAME', (1, 0), (1, -1), getattr(self, 'unicode_font', 'Helvetica')),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('BACKGROUND', (0, 0), (0, -1), colors.lightblue),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        
        story.append(session_table)
        
        # Hasta notları (eğer varsa)
        patient_notes = session.get('patient_notes', '')
        if patient_notes:
            story.append(Spacer(1, 10))
            story.append(Paragraph("<b>Hasta Notları:</b>", self.styles['UnicodeNormal']))
            story.append(Paragraph(patient_notes, self.styles['PatientInfo']))
    
    def _add_patient_header(self, story, session, patient_name):
        """Hasta raporu başlığını ekle"""
        story.append(Paragraph(f"HASTA RAPORU: {patient_name.upper()}", self.styles['SectionHeader']))
        
        # Hasta bilgileri - Parametrelerden al
        session_details = self.db.get_session_details(session.get('id'))
        parameters = session_details.get('parameters', {}) if session_details else {}
        
        patient_info = [
            ["Hasta Adı:", parameters.get('patient_name', {}).get('value', 'Belirtilmemiş')],
            ["Hasta Soyadı:", parameters.get('patient_surname', {}).get('value', 'Belirtilmemiş')],
            ["Yaş:", parameters.get('patient_age', {}).get('value', 'Belirtilmemiş')],
            ["Tür:", parameters.get('patient_species', {}).get('value', 'Belirtilmemiş')],
            ["Irk:", parameters.get('patient_breed', {}).get('value', 'Belirtilmemiş')],
            ["Ağırlık:", parameters.get('patient_weight', {}).get('value', 'Belirtilmemiş')],
            ["Sahip:", parameters.get('patient_owner', {}).get('value', 'Belirtilmemiş')],
            ["Veteriner:", parameters.get('patient_vet_contact', {}).get('value', 'Belirtilmemiş')],
            ["İlk Tedavi:", session.get('session_date', 'Bilinmiyor')],
        ]
        
        patient_table = Table(patient_info, colWidths=[3*cm, 7*cm])
        patient_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), getattr(self, 'unicode_font_bold', 'Helvetica-Bold')),
            ('FONTNAME', (1, 0), (1, -1), getattr(self, 'unicode_font', 'Helvetica')),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        
        story.append(patient_table)
        story.append(Spacer(1, 20))
    
    def _add_patient_statistics(self, story, sessions):
        """Hasta istatistiklerini ekle"""
        story.append(Paragraph("HASTA İSTATİSTİKLERİ", self.styles['SectionHeader']))
        
        total_sessions = len(sessions)
        total_duration = sum(s.get('duration_minutes', 0) or 0 for s in sessions)
        avg_duration = total_duration / total_sessions if total_sessions else 0
        
        # Tarih aralığı
        dates = [s.get('session_date', '') for s in sessions if s.get('session_date')]
        first_date = min(dates) if dates else 'Bilinmiyor'
        last_date = max(dates) if dates else 'Bilinmiyor'
        
        stats_data = [
            ["Toplam Seans Sayısı", str(total_sessions)],
            ["Toplam Tedavi Süresi", f"{total_duration} dakika"],
            ["Ortalama Seans Süresi", f"{avg_duration:.1f} dakika"],
            ["İlk Tedavi Tarihi", first_date],
            ["Son Tedavi Tarihi", last_date],
        ]
        
        stats_table = Table(stats_data, colWidths=[5*cm, 5*cm])
        stats_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), getattr(self, 'unicode_font_bold', 'Helvetica-Bold')),
            ('FONTNAME', (1, 0), (1, -1), getattr(self, 'unicode_font', 'Helvetica')),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
        ]))
        
        story.append(stats_table)
        story.append(Spacer(1, 20))
    
    def _add_patient_treatment_history(self, story, sessions):
        """Hasta tedavi geçmişini ekle"""
        story.append(Paragraph("TEDAVİ GEÇMİŞİ", self.styles['SectionHeader']))
        
        # Seansları tarihe göre sırala
        sessions.sort(key=lambda x: (x.get('session_date', ''), x.get('start_time', '')))
        
        # Tablo başlıkları
        table_data = [
            ["Tarih", "Süre (dk)", "Mod", "Frekans (Hz)", "Yoğunluk (mT)", "Hedef"]
        ]
        
        for session in sessions:
            row = [
                session.get('session_date', 'Bilinmiyor'),
                str(session.get('duration_minutes', 0) or 0),
                session.get('treatment_mode', 'Bilinmiyor'),
                str(session.get('frequency_hz', 0) or 0),
                str(session.get('intensity_mt', 0) or 0),
                session.get('target_condition', 'Belirtilmemiş')
            ]
            table_data.append(row)
        
        history_table = Table(table_data, colWidths=[2.5*cm, 1.5*cm, 2*cm, 2*cm, 2*cm, 3*cm])
        history_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), getattr(self, 'unicode_font_bold', 'Helvetica-Bold')),
            ('FONTNAME', (0, 1), (-1, -1), getattr(self, 'unicode_font', 'Helvetica')),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
        ]))
        
        story.append(history_table)
    
    def _add_footer(self, story):
        """Rapor alt bilgisini ekle"""
        story.append(Spacer(1, 30))
        
        footer_text = f"""
        Bu rapor PEMF (Pulsed Electromagnetic Field) tedavi cihazı tarafından otomatik olarak oluşturulmuştur.
        Rapor tarihi: {datetime.now().strftime('%d/%m/%Y %H:%M')}
        
        Veteriner PEMF Tedavi Sistemi v1.0
        """
        
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
        output_file = generator.generate_session_report(
            session_ids=test_sessions,
            output_path="test_report.pdf"
        )
        
        print(f"Test raporu oluşturuldu: {output_file}")
        
    except Exception as e:
        print(f"Test hatası: {e}")
        import traceback
        traceback.print_exc()
