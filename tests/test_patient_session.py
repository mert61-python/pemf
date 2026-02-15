#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.patient_database import get_patient_database
from database.session_manager import get_session_manager
from database.treatment_history_db import get_treatment_db
from utils.value_utils import normalize_patient_data
import sqlite3

def test_patient_session():
    """Test hasta kaydı ve session parametreleri"""
    
    print("=== TEST HASTA KAYDI ===")
    
    # Test hasta bilgileri
    test_patient = {
        'name': 'TEST KEDI',
        'species': 'KEDI',
        'breed': 'VAN KEDİSİ',
        'age': '3',
        'weight': '4.5',
        'owner': 'TEST SAHİBİ',
        'vet_contact': 'TEST VETERİNER'
    }
    
    # Hasta kaydet
    patient_db = get_patient_database()
    patient_id = patient_db.add_patient(test_patient)
    print(f"Test hasta kaydedildi: {patient_id}")
    
    # Session manager al
    session_manager = get_session_manager()
    
    # Session başlat
    session_id = session_manager.start_session(
        treatment_mode="Test",
        target_condition="Test Durumu",
        operator_name="Test Operatör",
        patient_name=test_patient['name']
    )
    
    print(f"Test session başlatıldı: {session_id}")
    
    # Hasta bilgilerini normalize et
    normalized_info = normalize_patient_data(test_patient)
    print(f"Normalize edilmiş bilgiler: {normalized_info}")
    
    # Session parametrelerini ekle
    session_manager.add_parameter('patient_name', normalized_info['name'])
    session_manager.add_parameter('patient_age', normalized_info['age'])
    session_manager.add_parameter('patient_species', normalized_info['species'])
    session_manager.add_parameter('patient_breed', normalized_info['breed'])
    session_manager.add_parameter('patient_weight', normalized_info['weight'], 'kg')
    session_manager.add_parameter('patient_owner', normalized_info['owner'])
    session_manager.add_parameter('patient_vet_contact', normalized_info['vet_contact'])
    
    print("Session parametreleri eklendi")
    
    # Veritabanından kontrol et
    print("\n=== VERİTABANI KONTROLÜ ===")
    db = get_treatment_db()
    
    with sqlite3.connect(db.db_path) as conn:
        cursor = conn.cursor()
        
        # Session bilgilerini al
        cursor.execute('''
            SELECT id, patient_name, treatment_mode, target_condition
            FROM treatment_sessions 
            WHERE id = ?
        ''', (session_id,))
        
        session = cursor.fetchone()
        if session:
            print(f"Session ID: {session[0]}")
            print(f"Hasta Adı: {session[1]}")
            print(f"Tedavi Modu: {session[2]}")
            print(f"Hedef Durum: {session[3]}")
            
            # Session parametrelerini al
            cursor.execute('''
                SELECT parameter_name, parameter_value
                FROM session_parameters 
                WHERE session_id = ?
                ORDER BY parameter_name
            ''', (session_id,))
            
            parameters = cursor.fetchall()
            print(f"\nSession Parametreleri ({len(parameters)} adet):")
            for param_name, param_value in parameters:
                print(f"  {param_name}: {param_value}")
        else:
            print("Session bulunamadı!")
    
    # Session'ı sonlandır
    session_manager.end_session("Test tamamlandı")
    print(f"\nTest session sonlandırıldı: {session_id}")

if __name__ == "__main__":
    test_patient_session()