"""
Tedavi Seansı Yöneticisi
PEMF tedavi seanslarının otomatik kaydedilmesi ve yönetimi
"""

import logging
import threading
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Any

from .treatment_history_db import get_treatment_db
from utils.simple_signal import SimpleSignal


class SessionManager:
    """Tedavi seansı yönetim sınıfı"""

    def __init__(self, app_data_dir, parent=None):
        # parent is accepted for backward compatibility with older PyQt callers.
        self.session_started = SimpleSignal()
        self.session_ended = SimpleSignal()
        self.session_error = SimpleSignal()
        self.app_data_dir = Path(app_data_dir)
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

        # Sensor sample batching (anlik T/B/I kayitlari)
        self._sensor_sample_batch = []
        self._sensor_batch_size = 50
        self._sensor_flush_interval_seconds = 5.0
        self._last_sensor_flush_ts = time.monotonic()
        self._sensor_batch_lock = threading.Lock()

        self._apply_performance_config()
        
        self.logger.info("SessionManager başlatıldı (transaction batching enabled)")

    def _apply_performance_config(self):
        """SQLite batch/flush ayarlarını config dosyasından yükle."""
        try:
            candidate_paths = [
                self.app_data_dir / "config.json",
                Path(__file__).resolve().parent.parent / "config" / "config.json",
            ]

            try:
                from utils.path_utils import resource_path

                candidate_paths.append(resource_path("config/config.json"))
                candidate_paths.append(resource_path("config/config.json.template"))
            except Exception:
                pass

            cfg = None
            selected_path = None
            for config_path in candidate_paths:
                if config_path and Path(config_path).exists():
                    with open(config_path, 'r', encoding='utf-8') as handle:
                        cfg = json.load(handle)
                    selected_path = Path(config_path)
                    break

            if cfg is None:
                raise FileNotFoundError("config.json not found in candidate paths")

            sqlite_cfg = cfg.get('performance', {}).get('sqlite', {})
            batch_size = int(sqlite_cfg.get('sensor_batch_size', self._sensor_batch_size))
            flush_interval = float(sqlite_cfg.get('sensor_flush_interval_seconds', self._sensor_flush_interval_seconds))

            self._sensor_batch_size = max(10, min(batch_size, 1000))
            self._sensor_flush_interval_seconds = max(0.2, min(flush_interval, 30.0))

            self.logger.info(
                "SessionManager sensor batch config loaded from %s: size=%d, flush_interval=%.2fs",
                selected_path,
                self._sensor_batch_size,
                self._sensor_flush_interval_seconds
            )
        except Exception as e:
            self.logger.warning(f"SessionManager performance config yüklenemedi, default kullanılıyor: {e}")
    
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

            # Session lifecycle event + outbox kaydı (offline-first)
            lifecycle_payload = {
                'event': 'session_started',
                'session_id': session_id,
                'treatment_mode': treatment_mode,
                'target_condition': target_condition,
                'operator_name': operator_name,
                'patient_name': patient_name,
                'timestamp': datetime.now().isoformat()
            }
            self.db.record_session_event(session_id, 'session_started', lifecycle_payload, severity='info')
            self.db.enqueue_outbox_message(
                topic='pemf/system/session',
                payload=json.dumps(lifecycle_payload, ensure_ascii=True),
                qos=1,
                retain=False,
                source='session_manager',
                correlation_id=str(session_id),
                idempotency_key=f"session-start-{session_id}"
            )
            
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

    def add_sensor_sample(self, coil_id: str, sensor_data: Dict[str, Any]):
        """Aktif seans için sensör örneği kuyruğa ekle."""
        if self.current_session_id is None:
            return

        sample_ts = datetime.now().timestamp()
        sample_record = {
            'coil_id': str(coil_id),
            'sample_ts': sample_ts,
            'temperature_c': sensor_data.get('object_temp', sensor_data.get('temperature')),
            'magnetic_field_mt': sensor_data.get('magnetic_field'),
            'current_a': sensor_data.get('current'),
            'pwm_frequency_hz': sensor_data.get('pwm_frequency'),
            'pwm_duty_percent': sensor_data.get('pwm_duty_cycle', sensor_data.get('pwm_duty')),
            'payload': {
                'sensors_ok': sensor_data.get('sensors_ok'),
                'temp_sensor_ok': sensor_data.get('temp_sensor_ok'),
                'magnetic_sensor_ok': sensor_data.get('magnetic_sensor_ok'),
                'current_sensor_ok': sensor_data.get('current_sensor_ok'),
                'timestamp': sensor_data.get('timestamp')
            }
        }

        with self._sensor_batch_lock:
            self._sensor_sample_batch.append(sample_record)
            should_flush_by_size = len(self._sensor_sample_batch) >= self._sensor_batch_size
            should_flush_by_time = (time.monotonic() - self._last_sensor_flush_ts) >= self._sensor_flush_interval_seconds
            if should_flush_by_size or should_flush_by_time:
                self._flush_sensor_sample_batch()

    def _flush_sensor_sample_batch(self):
        """Kuyruktaki sensör örneklerini tek transaction ile kaydet."""
        if not self._sensor_sample_batch or self.current_session_id is None:
            return

        pending_samples = list(self._sensor_sample_batch)
        self._sensor_sample_batch.clear()
        self._last_sensor_flush_ts = time.monotonic()

        saved = self.db.add_sensor_samples_batch(self.current_session_id, pending_samples)
        if saved <= 0:
            self.logger.warning("Sensor sample batch kaydedilemedi")
    
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

            with self._sensor_batch_lock:
                if self._sensor_sample_batch:
                    self._flush_sensor_sample_batch()
            
            # Final notları ekle
            if final_notes:
                self.add_note(final_notes)

            # Final notes sonrası oluşabilecek son değişiklikleri de flush et
            with self._batch_lock:
                if self._parameter_batch:
                    self._flush_parameter_batch()

            with self._sensor_batch_lock:
                if self._sensor_sample_batch:
                    self._flush_sensor_sample_batch()
            
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

            lifecycle_payload = {
                'event': 'session_ended',
                'session_id': session_to_end,
                'duration_minutes': duration_override,
                'treatment_mode': self.treatment_mode,
                'target_condition': self.target_condition,
                'timestamp': datetime.now().isoformat()
            }
            self.db.record_session_event(session_to_end, 'session_ended', lifecycle_payload, severity='info')
            self.db.enqueue_outbox_message(
                topic='pemf/system/session',
                payload=json.dumps(lifecycle_payload, ensure_ascii=True),
                qos=1,
                retain=False,
                source='session_manager',
                correlation_id=str(session_to_end),
                idempotency_key=f"session-end-{session_to_end}"
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


# Singleton instances
_session_manager_instance = None
_session_manager_lock = threading.Lock()

def get_session_manager(app_data_dir):
    """Session manager singleton instance'ını getir"""
    global _session_manager_instance
    with _session_manager_lock:
        if _session_manager_instance is None:
            _session_manager_instance = SessionManager(app_data_dir)
    return _session_manager_instance
