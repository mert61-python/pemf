"""
Tedavi Seansı Yöneticisi
PEMF tedavi seanslarının otomatik kaydedilmesi ve yönetimi
"""

import logging
import threading
from datetime import datetime
from typing import Dict, Optional, Any
from PyQt6.QtCore import QObject, pyqtSignal

from .treatment_history_db import get_treatment_db

class SessionManager(QObject):
    """Tedavi seansı yönetim sınıfı"""
    
    # Sinyaller
    session_started = pyqtSignal(int)  # session_id
    session_ended = pyqtSignal(int)    # session_id
    session_error = pyqtSignal(str)    # error_message
    
    def __init__(self, app_data_dir, parent=None):
        super().__init__(parent)
        self.db = get_treatment_db(app_data_dir)
        self.logger = logging.getLogger(__name__)
        
        # Aktif seans bilgileri
        self.current_session_id = None
        self.session_start_time = None
        self.session_parameters = {}
        self.treatment_mode = None
        self.target_condition = None
        self.operator_name = None
        self.patient_name = None
        
        # HIGH FIX: Parameter batching (100 params = 1 transaction)
        self._parameter_batch = []
        self._batch_size = 100
        self._batch_lock = threading.Lock()
        
        self.logger.info("SessionManager başlatıldı (transaction batching enabled)")
    
    def start_session(self, treatment_mode: str, target_condition: str = None, 
                     operator_name: str = None, patient_name: str = None, 
                     initial_parameters: Optional[Dict] = None) -> Optional[int]:
        """
        Yeni tedavi seansı başlat
        
        Args:
            treatment_mode: Tedavi modu (Autonomous, Manual, Custom)
            target_condition: Hedef durum (artrit, yara iyileşmesi, vb.)
            operator_name: Uygulayıcı adı
            patient_name: Hasta adı
            initial_parameters: Başlangıç parametreleri
            
        Returns:
            Optional[int]: Başarılı ise session_id, hata durumunda None
        """
        try:
            # Eğer aktif seans varsa önce onu sonlandır
            if self.current_session_id is not None:
                self.logger.warning("Aktif seans var, önce sonlandırılıyor")
                self.end_session()
            
            # Yeni seans başlat
            session_id = self.db.start_session(
                treatment_mode=treatment_mode,
                target_condition=target_condition,
                operator_name=operator_name,
                patient_name=patient_name
            )
            
            # Seans bilgilerini sakla
            self.current_session_id = session_id
            self.session_start_time = datetime.now()
            self.treatment_mode = treatment_mode
            self.target_condition = target_condition
            self.operator_name = operator_name
            self.patient_name = patient_name
            self.session_parameters = initial_parameters.copy() if initial_parameters else {}
            
            self.logger.info(f"Tedavi seansı başlatıldı: ID {session_id}, Mod: {treatment_mode}")
            
            # Sinyal gönder
            self.session_started.emit(session_id)
            
            return session_id
            
        except Exception as e:
            error_msg = f"Seans başlatma hatası: {str(e)}"
            self.logger.error(error_msg)
            self.session_error.emit(error_msg)
            return None
    
    def update_parameters(self, parameters: Dict[str, Any]):
        """
        Seans parametrelerini güncelle
        
        Args:
            parameters: Güncellenecek parametreler
        """
        if self.current_session_id is None:
            self.logger.warning("Aktif seans yok, parametreler güncellenemedi")
            return
        
        # Parametreleri birleştir
        self.session_parameters.update(parameters)
        
        self.logger.debug(f"Seans parametreleri güncellendi: {parameters}")
    
    def add_parameter(self, name: str, value: Any, unit: str = None):
        """
        Tek parametre ekle
        
        Args:
            name: Parametre adı
            value: Parametre değeri
            unit: Parametre birimi
        """
        if self.current_session_id is None:
            self.logger.warning("Aktif seans yok, parametre eklenemedi")
            return
        
        if unit:
            self.session_parameters[name] = {'value': value, 'unit': unit}
            param_value_to_save = value
        else:
            self.session_parameters[name] = value
            param_value_to_save = value
        
        # Parametreyi gerçek zamanlı olarak veritabanına kaydet
        try:
            import sqlite3
            with sqlite3.connect(self.db.db_path) as conn:
                cursor = conn.cursor()
                
                # Önce mevcut parametreyi sil
                cursor.execute('''
                    DELETE FROM session_parameters 
                    WHERE session_id = ? AND parameter_name = ?
                ''', (self.current_session_id, name))
                
                # Yeni parametreyi ekle
                cursor.execute('''
                    INSERT INTO session_parameters 
                    (session_id, parameter_name, parameter_value)
                    VALUES (?, ?, ?)
                ''', (self.current_session_id, name, str(param_value_to_save)))
                
                conn.commit()
                
        except Exception as e:
            self.logger.error(f"Parametre veritabanına kaydedilemedi: {e}")
        
        # HIGH FIX: Add to batch instead of immediate INSERT
        with self._batch_lock:
            self._parameter_batch.append((self.current_session_id, name, str(param_value_to_save)))
            
            # Flush batch if size limit reached
            if len(self._parameter_batch) >= self._batch_size:
                self._flush_parameter_batch()
        
        self.logger.debug(f"Parametre eklendi (batched): {name} = {value} {unit or ''}")
    
    def _flush_parameter_batch(self):
        """
        HIGH FIX: Flush parameter batch to database (executemany for efficiency).
        Reduces disk writes from N to 1 transaction.
        """
        if not self._parameter_batch:
            return
        
        try:
            import sqlite3
            from .treatment_history_db import get_treatment_db
            
            # Use connection pool from treatment_history_db
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                
                # HIGH FIX: executemany() - single transaction for all params
                cursor.executemany('''
                    INSERT INTO session_parameters 
                    (session_id, parameter_name, parameter_value)
                    VALUES (?, ?, ?)
                ''', self._parameter_batch)
                
                conn.commit()
                
                self.logger.debug(f"Parameter batch flushed: {len(self._parameter_batch)} parameters")
                self._parameter_batch.clear()
        
        except Exception as e:
            self.logger.error(f"Failed to flush parameter batch: {e}")
            self._parameter_batch.clear()  # Clear to avoid retry loop
    
    def set_frequency(self, frequency_hz: float):
        """Frekans parametresini ayarla"""
        self.add_parameter('frequency_hz', frequency_hz, 'Hz')
    
    def set_intensity(self, intensity_mt: float):
        """Yoğunluk parametresini ayarla"""
        self.add_parameter('intensity_mt', intensity_mt, 'mT')
    
    def set_pulse_duration(self, duration_ms: int):
        """Pulse süresi parametresini ayarla"""
        self.add_parameter('pulse_duration_ms', duration_ms, 'ms')
    
    def set_treatment_duration(self, duration_minutes: int):
        """Tedavi süresi parametresini ayarla"""
        self.add_parameter('treatment_duration', duration_minutes, 'dakika')
    
    def add_note(self, note: str):
        """Seans notunu ekle/güncelle"""
        if self.current_session_id is None:
            self.logger.warning("Aktif seans yok, not eklenemedi")
            return
        
        # Mevcut notu al ve yenisini ekle
        current_note = self.session_parameters.get('patient_notes', '')
        if current_note:
            updated_note = f"{current_note}\n{note}"
        else:
            updated_note = note
        
        self.session_parameters['patient_notes'] = updated_note
        self.logger.debug(f"Seans notu eklendi: {note}")
    
    def end_session(self, final_notes: str = None, session_id: int = None, actual_duration: float = None) -> bool:
        """
        Aktif seansı sonlandır

        Backwards-compatible: older callers may call without arguments. Newer callers
        can provide `session_id` and `actual_duration` (minutes, float).

        Args:
            final_notes: Son notlar
            session_id: Opsiyonel, sonlandırılacak seans ID'si (varsayılan: aktif seans)
            actual_duration: Opsiyonel, gerçek süre (dakika cinsinden, float)

        Returns:
            bool: Başarılı ise True
        """
        if self.current_session_id is None:
            # Eğer caller spesifik bir session_id verdiyse buna göre devam et
            if session_id is None:
                self.logger.warning("Sonlandırılacak aktif seans yok")
                return False
        
        try:
            # HIGH FIX: Flush any remaining batched parameters
            with self._batch_lock:
                if self._parameter_batch:
                    self._flush_parameter_batch()
            
            # Final notları ekle
            if final_notes:
                self.add_note(final_notes)
            
            # Hasta notlarını ayrı olarak al
            patient_notes = self.session_parameters.pop('patient_notes', None)
            
            # Parametreleri düzenle - sadece tedavi parametrelerini al (hasta parametreleri zaten kaydedildi)
            processed_parameters = {}
            treatment_params = ['frequency_hz', 'intensity_mt', 'pulse_duration_ms', 'duration']
            
            for key, value in self.session_parameters.items():
                # Sadece tedavi parametrelerini işle, hasta parametreleri zaten gerçek zamanlı kaydedildi
                if key in treatment_params:
                    if isinstance(value, dict) and 'value' in value:
                        # Unit'li parametre - sadece değeri al
                        processed_parameters[key] = value['value']
                    else:
                        # Normal parametre
                        processed_parameters[key] = value
            
            # Hangi session_id ile sonlandıracağımızı belirle
            session_to_end = session_id if session_id is not None else self.current_session_id

            # Seansı sonlandır (DB'ye duration override geçilebilir)
            # actual_duration bir float (dakika) olarak gelirse int'e çevir
            duration_override = None
            if actual_duration is not None:
                try:
                    duration_override = int(round(actual_duration))
                except Exception:
                    duration_override = None

            self.db.end_session(
                session_id=session_to_end,
                parameters=processed_parameters,
                patient_notes=patient_notes,
                duration_minutes=duration_override
            )

            session_id = session_to_end
            
            self.logger.info(f"Tedavi seansı sonlandırıldı: ID {session_id}")
            
            # Seans bilgilerini temizle
            self.current_session_id = None
            self.session_start_time = None
            self.session_parameters = {}
            self.treatment_mode = None
            self.target_condition = None
            self.operator_name = None
            
            # Sinyal gönder
            self.session_ended.emit(session_id)
            
            return True
            
        except Exception as e:
            error_msg = f"Seans sonlandırma hatası: {str(e)}"
            self.logger.error(error_msg)
            self.session_error.emit(error_msg)
            return False
    
    def is_session_active(self) -> bool:
        """Aktif seans var mı kontrol et"""
        return self.current_session_id is not None
    
    def get_current_session_id(self) -> Optional[int]:
        """Aktif seans ID'sini getir"""
        return self.current_session_id
    
    def get_session_duration(self) -> int:
        """Aktif seansın süresini dakika olarak getir"""
        if self.session_start_time is None:
            return 0
        
        duration = datetime.now() - self.session_start_time
        return int(duration.total_seconds() / 60)
    
    def get_session_info(self) -> Dict:
        """Aktif seans bilgilerini getir"""
        if self.current_session_id is None:
            return {}
        
        return {
            'session_id': self.current_session_id,
            'start_time': self.session_start_time,
            'duration_minutes': self.get_session_duration(),
            'treatment_mode': self.treatment_mode,
            'target_condition': self.target_condition,
            'operator_name': self.operator_name,
            'parameters': self.session_parameters.copy()
        }
    
    def force_end_session(self):
        """Seansı zorla sonlandır (hata durumunda)"""
        if self.current_session_id is not None:
            self.logger.warning(f"Seans zorla sonlandırılıyor: ID {self.current_session_id}")
            
            try:
                # Hata notu ekle
                self.add_note("Seans zorla sonlandırıldı")
                self.end_session()
            except Exception as e:
                self.logger.error(f"Zorla sonlandırma hatası: {e}")
                # Seans bilgilerini temizle
                self.current_session_id = None
                self.session_start_time = None
                self.session_parameters = {}
                self.treatment_mode = None
                self.target_condition = None
                self.operator_name = None


class AutoSessionLogger:
    """Otomatik seans kayıt yardımcısı"""
    
    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager
        self.logger = logging.getLogger(__name__)
    
    def log_autonomous_session(self, target_condition: str, frequency: float, 
                             intensity: float, duration: int, operator: str = None, 
                             patient_info: Dict = None):
        """
        Autonomous mod seansını kaydet
        
        Args:
            target_condition: Hedef durum
            frequency: Frekans (Hz)
            intensity: Yoğunluk (mT)
            duration: Süre (dakika)
            operator: Uygulayıcı
            patient_info: Hasta bilgileri
        """
        try:
            # Seans başlat
            success = self.session_manager.start_session(
                treatment_mode="Autonomous",
                target_condition=target_condition,
                operator_name=operator
            )
            
            if success:
                # Parametreleri ayarla
                self.session_manager.set_frequency(frequency)
                self.session_manager.set_intensity(intensity)
                self.session_manager.set_treatment_duration(duration)
                
                # Hasta bilgilerini ekle
                if patient_info:
                    # Ana pencereden gelen hasta bilgilerini doğru field adlarıyla kaydet
                    if 'info' in patient_info:
                        info = patient_info['info']
                        self.session_manager.add_parameter('patient_name', info.get('name', ''))
                        self.session_manager.add_parameter('patient_surname', '')  # Ana pencerede surname yok
                        self.session_manager.add_parameter('patient_age', info.get('age', ''))
                        self.session_manager.add_parameter('patient_species', info.get('species', ''))
                        self.session_manager.add_parameter('patient_breed', info.get('breed', ''))
                        self.session_manager.add_parameter('patient_weight', info.get('weight', ''))
                        self.session_manager.add_parameter('patient_owner', info.get('owner', ''))
                        self.session_manager.add_parameter('patient_vet_contact', info.get('vet_contact', ''))
                        
                        patient_name = info.get('name', 'Bilinmiyor')
                        self.logger.info(f"Autonomous seans kaydı başlatıldı: {target_condition} - Hasta: {patient_name}")
                    else:
                        # Eski format için backward compatibility
                        self.session_manager.add_parameter('patient_name', patient_info.get('name', ''))
                        self.session_manager.add_parameter('patient_surname', patient_info.get('surname', ''))
                        self.session_manager.add_parameter('patient_age', patient_info.get('age', ''))
                        self.session_manager.add_parameter('patient_gender', patient_info.get('gender', ''))
                        self.session_manager.add_parameter('patient_phone', patient_info.get('phone', ''))
                        self.session_manager.add_parameter('patient_email', patient_info.get('email', ''))
                        self.session_manager.add_parameter('patient_address', patient_info.get('address', ''))
                        self.session_manager.add_parameter('patient_medical_history', patient_info.get('medical_history', ''))
                        
                        patient_name = f"{patient_info.get('name', '')} {patient_info.get('surname', '')}".strip()
                        self.logger.info(f"Autonomous seans kaydı başlatıldı: {target_condition} - Hasta: {patient_name}")
                else:
                    self.logger.info(f"Autonomous seans kaydı başlatıldı: {target_condition}")
            
        except Exception as e:
            self.logger.error(f"Autonomous seans kayıt hatası: {e}")
    
    def log_manual_session(self, parameters: Dict, operator: str = None):
        """
        Manual mod seansını kaydet
        
        Args:
            parameters: Manuel parametreler
            operator: Uygulayıcı
        """
        try:
            # Seans başlat
            success = self.session_manager.start_session(
                treatment_mode="Manual",
                operator_name=operator,
                initial_parameters=parameters
            )
            
            if success:
                self.logger.info("Manual seans kaydı başlatıldı")
            
        except Exception as e:
            self.logger.error(f"Manual seans kayıt hatası: {e}")
    
    def log_parameter_change(self, parameter_name: str, old_value: Any, new_value: Any):
        """
        Parametre değişikliğini kaydet
        
        Args:
            parameter_name: Parametre adı
            old_value: Eski değer
            new_value: Yeni değer
        """
        if self.session_manager.is_session_active():
            change_note = f"Parametre değişikliği: {parameter_name} {old_value} -> {new_value}"
            self.session_manager.add_note(change_note)
            self.logger.debug(change_note)
    
    def log_treatment_event(self, event_type: str, description: str):
        """
        Tedavi olayını kaydet
        
        Args:
            event_type: Olay tipi (start, pause, resume, stop, error)
            description: Olay açıklaması
        """
        if self.session_manager.is_session_active():
            timestamp = datetime.now().strftime("%H:%M:%S")
            event_note = f"[{timestamp}] {event_type.upper()}: {description}"
            self.session_manager.add_note(event_note)
            self.logger.info(event_note)


# Singleton instances
_session_manager_instance = None
_auto_logger = None

def get_session_manager(app_data_dir):
    """Session manager singleton instance'ını getir"""
    global _session_manager_instance
    if _session_manager_instance is None:
        _session_manager_instance = SessionManager(app_data_dir)
    return _session_manager_instance

def get_auto_logger(app_data_dir=None) -> AutoSessionLogger:
    """
    Auto logger singleton instance'ını getir
    
    Args:
        app_data_dir: Uygulama veri dizini (Path). None ise varsayılan konum kullanılır.
    """
    global _auto_logger
    if _auto_logger is None:
        # app_data_dir'yi belirle
        if app_data_dir is None:
            try:
                from windows.gui_pyqt_v11 import get_app_data_directory
                app_data_dir = get_app_data_directory()
            except Exception:
                # Fallback: varsayılan konum
                from pathlib import Path
                app_data_dir = Path.home() / ".pemf_gui"
        
        _auto_logger = AutoSessionLogger(get_session_manager(app_data_dir))
    return _auto_logger
