"""
Hasta Veritabanı Yönetim Sistemi

Bu modül, PEMF vet sisteminde hasta bilgilerinin saklanması ve yönetimi için
JSON tabanlı bir veritabanı sistemi sağlar.

Ana Özellikler:
    - Hasta bilgilerini JSON formatında saklama
    - Hasta ekleme, güncelleme, silme ve arama işlemleri
    - Benzersiz hasta ID'leri ile veri bütünlüğü
    - Thread-safe dosya işlemleri

@author: merta
"""

import sqlite3
import os
import uuid
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

class PatientDatabase:
    """
    Hasta veritabanı yönetim sınıfı.
    
    CRITICAL FIX: SQLite kullanarak hasta bilgilerini saklar (JSON'dan migrate).
    Thread-safe işlemler için kilit mekanizması ve connection pool kullanır.
    """
    
    def __init__(self, db_file: str = "patients.db"):
        """
        Veritabanını başlatır.
        
        Args:
            db_file (str): Veritabanı dosyasının adı (.db extension)
        """
        self.db_file = Path(db_file)
        self.lock = threading.Lock()
        self._init_database()
    
    def _init_database(self):
        """SQLite veritabanı ve tabloları oluşturur."""
        try:
            with sqlite3.connect(self.db_file) as conn:
                # Enable WAL mode for better concurrency
                conn.execute('PRAGMA journal_mode=WAL')
                conn.execute('PRAGMA synchronous=NORMAL')
                
                cursor = conn.cursor()
                
                # Patients table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS patients (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        species TEXT,
                        breed TEXT,
                        age TEXT,
                        weight TEXT,
                        owner TEXT,
                        vet_contact TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                ''')
                
                # Index for faster searches
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_patient_name 
                    ON patients(name)
                ''')
                
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_patient_owner 
                    ON patients(owner)
                ''')
                
                conn.commit()
        except sqlite3.Error as e:
            raise RuntimeError(f"Database initialization failed: {e}")
    
    def add_patient(self, patient_info: Dict[str, str]) -> str:
        """
        Yeni hasta ekler (SQLite).
        
        Args:
            patient_info (Dict[str, str]): Hasta bilgileri
                - name: Hayvanın adı
                - species: Hayvanın türü
                - breed: Hayvanın ırkı
                - age: Hayvanın yaşı
                - weight: Hayvanın ağırlığı
                - owner: Hayvanın sahibi
                - vet_contact: Veteriner iletişim bilgileri
        
        Returns:
            str: Oluşturulan hasta ID'si
        """
        with self.lock:
            patient_id = str(uuid.uuid4())
            now = datetime.now().isoformat()
            
            try:
                with sqlite3.connect(self.db_file) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT INTO patients 
                        (id, name, species, breed, age, weight, owner, vet_contact, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        patient_id,
                        patient_info.get("name", ""),
                        patient_info.get("species", ""),
                        patient_info.get("breed", ""),
                        patient_info.get("age", ""),
                        patient_info.get("weight", ""),
                        patient_info.get("owner", ""),
                        patient_info.get("vet_contact", ""),
                        now,
                        now
                    ))
                    conn.commit()
                
                return patient_id
            except sqlite3.Error as e:
                raise RuntimeError(f"Failed to add patient: {e}")
    
    def get_patient(self, patient_id: str) -> Optional[Dict[str, Any]]:
        """
        Belirtilen ID'ye sahip hastayı getirir (SQLite).
        
        Args:
            patient_id (str): Hasta ID'si
        
        Returns:
            Optional[Dict[str, Any]]: Hasta bilgileri veya None
        """
        with self.lock:
            try:
                with sqlite3.connect(self.db_file) as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    cursor.execute('SELECT * FROM patients WHERE id = ?', (patient_id,))
                    row = cursor.fetchone()
                    
                    if row:
                        return dict(row)
                    return None
            except sqlite3.Error:
                return None
    
    def get_all_patients(self) -> List[Dict[str, Any]]:
        """
        Tüm hastaları getirir (SQLite).
        
        SQLite WAL mode: Bu read-only işlem lock gerektirmez.
        SQLite'ın kendi reader-writer lock mekanizmasını kullanır.
        
        Returns:
            List[Dict[str, Any]]: Hasta listesi
        """
        try:
            with sqlite3.connect(self.db_file, timeout=10.0) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM patients ORDER BY created_at DESC')
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except sqlite3.Error as e:
            return []
    
    def update_patient(self, patient_id: str, patient_info: Dict[str, str]) -> bool:
        """
        Hasta bilgilerini günceller (SQLite).
        
        Args:
            patient_id (str): Hasta ID'si
            patient_info (Dict[str, str]): Güncellenecek hasta bilgileri
        
        Returns:
            bool: Güncelleme başarılı ise True
        """
        with self.lock:
            try:
                with sqlite3.connect(self.db_file) as conn:
                    cursor = conn.cursor()
                    
                    # Build dynamic update query based on provided fields
                    updates = []
                    values = []
                    for key, value in patient_info.items():
                        if key in ['name', 'species', 'breed', 'age', 'weight', 'owner', 'vet_contact']:
                            updates.append(f"{key} = ?")
                            values.append(value)
                    
                    if not updates:
                        return False
                    
                    updates.append("updated_at = ?")
                    values.append(datetime.now().isoformat())
                    values.append(patient_id)
                    
                    query = f"UPDATE patients SET {', '.join(updates)} WHERE id = ?"
                    cursor.execute(query, values)
                    conn.commit()
                    
                    return cursor.rowcount > 0
            except sqlite3.Error:
                return False
    
    def delete_patient(self, patient_id: str) -> bool:
        """
        Hastayı siler (SQLite).
        
        Args:
            patient_id (str): Hasta ID'si
        
        Returns:
            bool: Silme başarılı ise True
        """
        # Timeout ile lock almaya çalış (10 saniye)
        lock_acquired = self.lock.acquire(timeout=10.0)
        if not lock_acquired:
            return False
        
        try:
            with sqlite3.connect(self.db_file, timeout=30.0) as conn:
                cursor = conn.cursor()
                
                # Önce hastanın var olup olmadığını kontrol et
                cursor.execute('SELECT id, name FROM patients WHERE id = ?', (patient_id,))
                existing = cursor.fetchone()
                if not existing:
                    return False
                
                # Silme işlemi
                cursor.execute('DELETE FROM patients WHERE id = ?', (patient_id,))
                rowcount = cursor.rowcount
                conn.commit()
                
                return rowcount > 0
        except sqlite3.Error:
            return False
        finally:
            self.lock.release()
    
    def clear_all_patients(self) -> bool:
        """
        Tüm hastaları siler (Database cleanup için).
        
        CAUTION: Bu işlem geri alınamaz!
        
        Returns:
            bool: Silme başarılı ise True
        """
        with self.lock:
            try:
                with sqlite3.connect(self.db_file) as conn:
                    cursor = conn.cursor()
                    cursor.execute('DELETE FROM patients')
                    conn.commit()
                    # Vacuum to reclaim space
                    cursor.execute('VACUUM')
                    return True
            except sqlite3.Error as e:
                print(f"Error clearing patients: {e}")
                return False
    
    def search_patients(self, search_term: str) -> List[Dict[str, Any]]:
        """
        Hasta adı veya sahibi adına göre arama yapar (SQLite LIKE).
        
        Args:
            search_term (str): Arama terimi
        
        Returns:
            List[Dict[str, Any]]: Bulunan hastalar
        """
        with self.lock:
            try:
                with sqlite3.connect(self.db_file) as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    
                    search_pattern = f"%{search_term}%"
                    cursor.execute('''
                        SELECT * FROM patients 
                        WHERE name LIKE ? OR owner LIKE ? OR species LIKE ?
                        ORDER BY created_at DESC
                    ''', (search_pattern, search_pattern, search_pattern))
                    
                    rows = cursor.fetchall()
                    return [dict(row) for row in rows]
            except sqlite3.Error:
                return []
    
    def get_patient_count(self) -> int:
        """
        Toplam hasta sayısını döndürür (SQLite COUNT).
        
        Returns:
            int: Hasta sayısı
        """
        with self.lock:
            try:
                with sqlite3.connect(self.db_file) as conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT COUNT(*) FROM patients')
                    return cursor.fetchone()[0]
            except sqlite3.Error:
                return 0

# Global veritabanı instance'ı
_patient_db = None

def get_patient_database(app_data_dir=None) -> PatientDatabase:
    """
    Global hasta veritabanı instance'ını döndürür (SQLite).
    
    Args:
        app_data_dir: Uygulama veri dizini (Path). None ise varsayılan konum kullanılır.
    
    Returns:
        PatientDatabase: Hasta veritabanı instance'ı
    """
    global _patient_db
    if _patient_db is None:
        # app_data_dir'yi belirle
        if app_data_dir is None:
            try:
                from windows.gui_pyqt_v11 import get_app_data_directory
                app_data_dir = get_app_data_directory()
            except Exception:
                # Fallback: varsayılan konum
                from pathlib import Path
                app_data_dir = Path.home() / ".pemf_gui"
        
        # CRITICAL FIX: Use .db extension for SQLite
        db_file = app_data_dir / "patients.db"
        _patient_db = PatientDatabase(str(db_file))
    return _patient_db
