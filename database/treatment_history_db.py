"""
Tedavi Geçmişi Veritabanı Modülü
PEMF tedavi seanslarının kaydedilmesi ve yönetimi için SQLite veritabanı
"""

import sqlite3
import os
import logging
import threading
from datetime import datetime
from typing import List, Dict, Optional
from contextlib import contextmanager

class TreatmentHistoryDB:
    """PEMF tedavi geçmişi veritabanı yönetim sınıfı (Connection Pool + WAL mode)"""
    
    def __init__(self, app_data_dir):
        """
        Veritabanı bağlantısını başlat
        
        Args:
            app_data_dir: Uygulama veri dizini (Path). Veritabanı dosyası bu dizinde oluşturulur.
        """
        self.db_path = app_data_dir / "pemf_treatment_history.db"
        self.logger = logging.getLogger(__name__)
        
        # HIGH FIX: Thread-local connection storage (connection pool pattern)
        self._local = threading.local()
        self._lock = threading.Lock()
        
        # Veritabanını başlat
        self._init_database()
    
    @contextmanager
    def _get_connection(self):
        """
        HIGH FIX: Thread-safe connection pool context manager.
        Her thread kendi connection'ını kullanır, shared state yok.
        """
        # Check if this thread already has a connection
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            # Create new connection for this thread
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            # Enable WAL mode for better concurrency
            self._local.conn.execute('PRAGMA journal_mode=WAL')
            self._local.conn.execute('PRAGMA synchronous=NORMAL')
            # Enable foreign keys
            self._local.conn.execute('PRAGMA foreign_keys=ON')
            self._local.conn.row_factory = sqlite3.Row
        
        try:
            yield self._local.conn
        except Exception:
            # Rollback on error
            self._local.conn.rollback()
            raise
    
    def close_connections(self):
        """Close all thread-local connections (call on shutdown)"""
        if hasattr(self._local, 'conn') and self._local.conn is not None:
            try:
                self._local.conn.close()
                self._local.conn = None
            except Exception as e:
                self.logger.error(f"Error closing connection: {e}")
    
    def _init_database(self):
        """Veritabanı tablolarını oluştur (HIGH FIX: WAL mode enabled)"""
        try:
            # HIGH FIX: Use connection pool
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Tedavi seansları tablosu
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS treatment_sessions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_date TEXT NOT NULL,
                        start_time TEXT NOT NULL,
                        end_time TEXT,
                        duration_minutes INTEGER,
                        treatment_mode TEXT NOT NULL,
                        target_condition TEXT,
                        frequency_hz REAL,
                        intensity_mt REAL,
                        pulse_duration_ms INTEGER,
                        operator_name TEXT,
                        patient_name TEXT,
                        patient_notes TEXT,
                        session_status TEXT DEFAULT 'completed',
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Tedavi parametreleri detay tablosu
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS session_parameters (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id INTEGER NOT NULL,
                        parameter_name TEXT NOT NULL,
                        parameter_value TEXT NOT NULL,
                        parameter_unit TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (session_id) REFERENCES treatment_sessions (id)
                    )
                ''')
                
                # Sistem ayarları tablosu
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS system_settings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        setting_key TEXT UNIQUE NOT NULL,
                        setting_value TEXT NOT NULL,
                        description TEXT,
                        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # İndeksler oluştur
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_session_date 
                    ON treatment_sessions(session_date)
                ''')
                
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_treatment_mode 
                    ON treatment_sessions(treatment_mode)
                ''')
                
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_session_parameters 
                    ON session_parameters(session_id)
                ''')
                
                # Mevcut tabloya patient_name sütunu ekle (migration)
                try:
                    cursor.execute('ALTER TABLE treatment_sessions ADD COLUMN patient_name TEXT')
                    self.logger.info("patient_name sütunu eklendi")
                except sqlite3.OperationalError:
                    # Sütun zaten varsa hata vermez
                    pass
                
                conn.commit()
                self.logger.info(f"Veritabanı başarıyla başlatıldı: {self.db_path}")
                
        except sqlite3.Error as e:
            self.logger.error(f"Veritabanı başlatma hatası: {e}")
            raise
    
    def start_session(self, treatment_mode: str, target_condition: str = None, 
                     operator_name: str = None, patient_name: str = None) -> int:
        """
        Yeni tedavi seansı başlat
        
        Args:
            treatment_mode: Tedavi modu (Autonomous, Manual, vb.)
            target_condition: Hedef durum (artrit, yara iyileşmesi, vb.)
            operator_name: Uygulayıcı adı
            patient_name: Hasta adı
            
        Returns:
            int: Oluşturulan seans ID'si
        """
        try:
            # HIGH FIX: Use connection pool instead of new connection
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                now = datetime.now()
                session_date = now.strftime('%Y-%m-%d')
                start_time = now.strftime('%H:%M:%S')
                
                cursor.execute('''
                    INSERT INTO treatment_sessions 
                    (session_date, start_time, treatment_mode, target_condition, 
                     operator_name, patient_name, session_status)
                    VALUES (?, ?, ?, ?, ?, ?, 'active')
                ''', (session_date, start_time, treatment_mode, target_condition, operator_name, patient_name))
                
                session_id = cursor.lastrowid
                conn.commit()
                
                self.logger.info(f"Yeni tedavi seansı başlatıldı: ID {session_id}")
                return session_id
                
        except sqlite3.Error as e:
            self.logger.error(f"Seans başlatma hatası: {e}")
            raise
    
    def end_session(self, session_id: int, parameters: Dict = None, 
                   patient_notes: str = None, duration_minutes: int = None):
        """
        Tedavi seansını sonlandır
        
        Args:
            session_id: Seans ID'si
            parameters: Tedavi parametreleri sözlüğü
            patient_notes: Hasta notları
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Seans bilgilerini al
                cursor.execute('''
                    SELECT start_time, session_date FROM treatment_sessions 
                    WHERE id = ?
                ''', (session_id,))
                
                result = cursor.fetchone()
                if not result:
                    raise ValueError(f"Seans bulunamadı: {session_id}")
                
                start_time_str, session_date = result
                
                # Süreyi hesapla (opsiyonel override varsa kullan)
                now = datetime.now()
                end_time = now.strftime('%H:%M:%S')

                if duration_minutes is None:
                    start_datetime = datetime.strptime(f"{session_date} {start_time_str}", 
                                                     '%Y-%m-%d %H:%M:%S')
                    duration_minutes = int((now - start_datetime).total_seconds() / 60)
                
                # Seans bilgilerini güncelle
                update_data = [end_time, duration_minutes, 'completed', session_id]
                update_query = '''
                    UPDATE treatment_sessions 
                    SET end_time = ?, duration_minutes = ?, session_status = ?,
                        updated_at = CURRENT_TIMESTAMP
                '''
                
                if parameters:
                    # Ana parametreleri güncelle
                    if 'frequency_hz' in parameters:
                        update_query += ', frequency_hz = ?'
                        update_data.insert(-1, parameters['frequency_hz'])
                    if 'intensity_mt' in parameters:
                        update_query += ', intensity_mt = ?'
                        update_data.insert(-1, parameters['intensity_mt'])
                    if 'pulse_duration_ms' in parameters:
                        update_query += ', pulse_duration_ms = ?'
                        update_data.insert(-1, parameters['pulse_duration_ms'])
                
                if patient_notes:
                    update_query += ', patient_notes = ?'
                    update_data.insert(-1, patient_notes)
                
                update_query += ' WHERE id = ?'
                
                cursor.execute(update_query, update_data)
                
                # Detaylı parametreleri kaydet
                if parameters:
                    for param_name, param_value in parameters.items():
                        if param_name not in ['frequency_hz', 'intensity_mt', 'pulse_duration_ms']:
                            cursor.execute('''
                                INSERT INTO session_parameters 
                                (session_id, parameter_name, parameter_value)
                                VALUES (?, ?, ?)
                            ''', (session_id, param_name, str(param_value)))
                
                conn.commit()
                self.logger.info(f"Tedavi seansı sonlandırıldı: ID {session_id}")
                
        except sqlite3.Error as e:
            self.logger.error(f"Seans sonlandırma hatası: {e}")
            raise
    
    def get_session_history(self, limit: int = 100, 
                           start_date: str = None, 
                           end_date: str = None,
                           treatment_mode: str = None) -> List[Dict]:
        """
        Tedavi geçmişini getir
        
        Args:
            limit: Maksimum kayıt sayısı
            start_date: Başlangıç tarihi (YYYY-MM-DD)
            end_date: Bitiş tarihi (YYYY-MM-DD)
            treatment_mode: Tedavi modu filtresi
            
        Returns:
            List[Dict]: Tedavi seansları listesi
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                query = '''
                    SELECT ts.id, ts.session_date, ts.start_time, ts.end_time, ts.duration_minutes,
                           ts.treatment_mode, ts.target_condition, ts.frequency_hz, ts.intensity_mt,
                           ts.pulse_duration_ms, ts.operator_name, ts.patient_notes, ts.session_status,
                           sp_name.parameter_value as patient_name,
                           sp_surname.parameter_value as patient_surname,
                           sp_age.parameter_value as patient_age,
                           sp_species.parameter_value as patient_species,
                           sp_breed.parameter_value as patient_breed,
                           sp_weight.parameter_value as patient_weight,
                           sp_owner.parameter_value as patient_owner,
                           sp_vet.parameter_value as patient_vet_contact,
                           sp_veteriner.parameter_value as patient_veteriner,
                           sp_duration.parameter_value as treatment_duration
                    FROM treatment_sessions ts
                    LEFT JOIN session_parameters sp_name ON ts.id = sp_name.session_id AND sp_name.parameter_name = 'patient_name'
                    LEFT JOIN session_parameters sp_surname ON ts.id = sp_surname.session_id AND sp_surname.parameter_name = 'patient_surname'
                    LEFT JOIN session_parameters sp_age ON ts.id = sp_age.session_id AND sp_age.parameter_name = 'patient_age'
                    LEFT JOIN session_parameters sp_species ON ts.id = sp_species.session_id AND sp_species.parameter_name = 'patient_species'
                    LEFT JOIN session_parameters sp_breed ON ts.id = sp_breed.session_id AND sp_breed.parameter_name = 'patient_breed'
                    LEFT JOIN session_parameters sp_weight ON ts.id = sp_weight.session_id AND sp_weight.parameter_name = 'patient_weight'
                    LEFT JOIN session_parameters sp_owner ON ts.id = sp_owner.session_id AND sp_owner.parameter_name = 'patient_owner'
                    LEFT JOIN session_parameters sp_vet ON ts.id = sp_vet.session_id AND sp_vet.parameter_name = 'patient_vet_contact'
                    LEFT JOIN session_parameters sp_veteriner ON ts.id = sp_veteriner.session_id AND sp_veteriner.parameter_name = 'patient_veteriner'
                    LEFT JOIN session_parameters sp_duration ON ts.id = sp_duration.session_id AND sp_duration.parameter_name = 'duration'
                    WHERE 1=1
                '''
                params = []
                
                if start_date:
                    query += ' AND session_date >= ?'
                    params.append(start_date)
                
                if end_date:
                    query += ' AND session_date <= ?'
                    params.append(end_date)
                
                if treatment_mode:
                    query += ' AND treatment_mode = ?'
                    params.append(treatment_mode)
                
                query += ' ORDER BY session_date DESC, start_time DESC LIMIT ?'
                params.append(limit)
                
                cursor.execute(query, params)
                rows = cursor.fetchall()
                
                # Sonuçları sözlük formatına çevir
                columns = [desc[0] for desc in cursor.description]
                sessions = []
                
                for row in rows:
                    session = dict(zip(columns, row))
                    sessions.append(session)
                
                return sessions
                
        except sqlite3.Error as e:
            self.logger.error(f"Geçmiş getirme hatası: {e}")
            raise
    
    def get_session_details(self, session_id: int) -> Optional[Dict]:
        """
        Belirli bir seansın detaylarını getir
        
        Args:
            session_id: Seans ID'si
            
        Returns:
            Dict: Seans detayları ve parametreleri
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Ana seans bilgileri
                cursor.execute('''
                    SELECT * FROM treatment_sessions WHERE id = ?
                ''', (session_id,))
                
                session_row = cursor.fetchone()
                if not session_row:
                    return None
                
                columns = [desc[0] for desc in cursor.description]
                session = dict(zip(columns, session_row))
                
                # Parametreler
                cursor.execute('''
                    SELECT parameter_name, parameter_value, parameter_unit
                    FROM session_parameters WHERE session_id = ?
                ''', (session_id,))
                
                parameters = {}
                for param_row in cursor.fetchall():
                    param_name, param_value, param_unit = param_row
                    parameters[param_name] = {
                        'value': param_value,
                        'unit': param_unit
                    }
                
                session['parameters'] = parameters
                return session
                
        except sqlite3.Error as e:
            self.logger.error(f"Seans detayları getirme hatası: {e}")
            raise
    
    def get_statistics(self) -> Dict:
        """
        Tedavi istatistiklerini getir
        
        Returns:
            Dict: İstatistik bilgileri
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                stats = {}
                
                # Toplam seans sayısı
                cursor.execute('SELECT COUNT(*) FROM treatment_sessions')
                stats['total_sessions'] = cursor.fetchone()[0]
                
                # Bu ay seans sayısı
                current_month = datetime.now().strftime('%Y-%m')
                cursor.execute('''
                    SELECT COUNT(*) FROM treatment_sessions 
                    WHERE session_date LIKE ?
                ''', (f"{current_month}%",))
                stats['monthly_sessions'] = cursor.fetchone()[0]
                
                # Tedavi modlarına göre dağılım
                cursor.execute('''
                    SELECT treatment_mode, COUNT(*) 
                    FROM treatment_sessions 
                    GROUP BY treatment_mode
                ''')
                stats['mode_distribution'] = dict(cursor.fetchall())
                
                # Ortalama seans süresi
                cursor.execute('''
                    SELECT AVG(duration_minutes) 
                    FROM treatment_sessions 
                    WHERE duration_minutes IS NOT NULL
                ''')
                avg_duration = cursor.fetchone()[0]
                stats['average_duration'] = round(avg_duration, 1) if avg_duration else 0
                
                return stats
                
        except sqlite3.Error as e:
            self.logger.error(f"İstatistik getirme hatası: {e}")
            raise
    
    def update_session_notes(self, session_id: int, notes: str):
        """
        Tedavi seansının notlarını güncelle
        
        Args:
            session_id: Güncellenecek seans ID'si
            notes: Yeni notlar
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    UPDATE treatment_sessions 
                    SET patient_notes = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (notes, session_id))
                
                conn.commit()
                self.logger.info(f"Seans notları güncellendi: ID {session_id}")
                
        except sqlite3.Error as e:
            self.logger.error(f"Seans notları güncelleme hatası: {e}")
            raise
    
    def save_completed_session(self, mode: str, patient_info: dict, target_condition: str,
                               start_time: datetime, duration_minutes: float, 
                               planned_duration: int, parameters: dict, 
                               stop_reason: str, connected_coils: List[int]) -> int:
        """
        Tamamlanmış seansı veritabanına kaydet (TEK KAYIT - Basitleştirilmiş Yapı)
        
        Bu metod sadece seans durdurulduğunda çağrılır. Çoklu kayıt sorunu çözülür.
        
        Args:
            mode: Seans modu ('automatic', 'ai', 'manual')
            patient_info: Hasta bilgileri dict
            target_condition: Hedef durum
            start_time: Seans başlangıç zamanı
            duration_minutes: Gerçek seans süresi (dakika)
            planned_duration: Planlanan süre (dakika)
            parameters: Seans parametreleri (frequency, duty, intensity vb.)
            stop_reason: Durma nedeni ('completed', 'user_stopped', 'error')
            connected_coils: Bağlı bobin listesi
            
        Returns:
            int: Oluşturulan session_id
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Hasta bilgilerini parse et (BASİTLEŞTİRİLDİ)
                # patient_info yapısı: {'id': X, 'info': {'name', 'species', 'breed', 'age', 'weight', 'owner', ...}}
                patient_species = "Bilinmiyor"
                patient_breed = ""
                patient_age = ""
                patient_weight = ""
                owner_name = ""
                veteriner_name = ""
                
                if patient_info:
                    # Önce 'info' dict'inden al, yoksa root'tan al
                    info_dict = patient_info.get('info', patient_info)
                    patient_name = info_dict.get('name', 'Bilinmiyor')
                    patient_species = info_dict.get('species', 'Bilinmiyor')
                    patient_breed = info_dict.get('breed', '')
                    
                    # Yaş ve ağırlık string/number olabilir
                    age_val = info_dict.get('age', '')
                    patient_age = str(age_val) if age_val else ''
                    weight_val = info_dict.get('weight', '')
                    patient_weight = str(weight_val) if weight_val else ''
                    
                    owner_name = info_dict.get('owner', '')
                    # Veteriner bilgisi için hem 'veteriner' hem 'vet_contact' kontrol et
                    veteriner_name = info_dict.get('veteriner', '') or info_dict.get('vet_contact', '')
                
                # Seans bilgilerini kaydet
                session_date = start_time.strftime('%Y-%m-%d')
                start_time_str = start_time.strftime('%H:%M:%S')
                end_time = datetime.now()
                end_time_str = end_time.strftime('%H:%M:%S')
                
                # Session status belirleme
                if stop_reason == 'completed':
                    session_status = 'completed'
                elif stop_reason == 'user_stopped':
                    session_status = 'interrupted'
                else:
                    session_status = 'error'
                
                # Parametrelerden frekans ve yoğunluk al
                frequency = parameters.get('frequency', 0)
                intensity = parameters.get('intensity', 0)
                duty_cycle = parameters.get('duty', 0)
                
                # Notlar oluştur
                notes_parts = [
                    f"Mod: {mode.capitalize()}",
                    f"Hedef: {target_condition}",
                    f"Planlanan Süre: {planned_duration} dk",
                    f"Gerçek Süre: {duration_minutes:.1f} dk",
                    f"Durum: {stop_reason}",
                    f"Bağlı Bobinler: {', '.join(map(str, connected_coils))}"
                ]
                
                if patient_breed:
                    notes_parts.append(f"Irk: {patient_breed}")
                if patient_age:
                    notes_parts.append(f"Yaş: {patient_age}")
                if patient_weight:
                    notes_parts.append(f"Ağırlık: {patient_weight}")
                
                patient_notes = " | ".join(notes_parts)
                
                # INSERT session
                cursor.execute('''
                    INSERT INTO treatment_sessions 
                    (session_date, start_time, end_time, duration_minutes, 
                     treatment_mode, target_condition, frequency_hz, intensity_mt,
                     operator_name, patient_name, patient_notes, session_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    session_date, start_time_str, end_time_str, int(duration_minutes),
                    mode, target_condition, frequency, intensity,
                    owner_name, patient_name, patient_notes, session_status
                ))
                
                session_id = cursor.lastrowid
                
                # Parametreleri kaydet (JSON değil, ayrı kayıtlar)
                # stop_reason'ı Türkçeye çevir
                stop_reason_turkish = {
                    'completed': 'Tedavi Başarıyla Tamamlandı',
                    'user_stopped': 'Manuel Müdahale',
                    'manual_stop': 'Manuel Müdahale',
                    'error': 'Hata',
                    'emergency': 'Acil Durdurma'
                }.get(stop_reason, stop_reason)
                
                param_records = [
                    ('frequency_hz', str(frequency), 'Hz'),
                    ('duty_cycle', str(duty_cycle), '%'),
                    ('intensity_mt', str(intensity), 'mT'),
                    ('planned_duration', str(planned_duration), 'min'),
                    ('actual_duration', f"{duration_minutes:.1f}", 'min'),
                    ('stop_reason', stop_reason_turkish, ''),
                    ('connected_coils', ','.join(map(str, connected_coils)), ''),
                    # Hasta bilgileri
                    ('patient_name', patient_name, ''),
                    ('patient_species', patient_species, ''),
                    ('patient_breed', patient_breed, ''),
                    ('patient_age', patient_age, ''),
                    ('patient_weight', patient_weight, 'kg'),
                    ('patient_owner', owner_name, ''),
                    ('patient_veteriner', veteriner_name, ''),
                ]
                
                for param_name, param_value, param_unit in param_records:
                    cursor.execute('''
                        INSERT INTO session_parameters 
                        (session_id, parameter_name, parameter_value, parameter_unit)
                        VALUES (?, ?, ?, ?)
                    ''', (session_id, param_name, param_value, param_unit))
                
                conn.commit()
                
                self.logger.info(
                    f"Completed session saved: ID={session_id}, mode={mode}, "
                    f"patient={patient_name}, duration={duration_minutes:.1f}min, "
                    f"status={session_status}"
                )
                
                return session_id
                
        except Exception as e:
            self.logger.error(f"Failed to save completed session: {e}", exc_info=True)
            raise
    
    def delete_session(self, session_id: int):
        """
        Tedavi seansını sil
        
        Args:
            session_id: Silinecek seans ID'si
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Önce parametreleri sil
                cursor.execute('DELETE FROM session_parameters WHERE session_id = ?', 
                             (session_id,))
                
                # Sonra seansı sil
                cursor.execute('DELETE FROM treatment_sessions WHERE id = ?', 
                             (session_id,))
                
                conn.commit()
                self.logger.info(f"Tedavi seansı silindi: ID {session_id}")
                
        except sqlite3.Error as e:
            self.logger.error(f"Seans silme hatası: {e}")
            raise
    
    def close(self):
        """Veritabanı bağlantısını kapat"""
        # SQLite otomatik olarak bağlantıları kapatır
        pass


# Singleton instance
_treatment_db_instance = None

def get_treatment_db(app_data_dir):
    """Tedavi geçmişi veritabanı singleton instance'ını getir"""
    global _treatment_db_instance
    if _treatment_db_instance is None:
        _treatment_db_instance = TreatmentHistoryDB(app_data_dir)
    return _treatment_db_instance
