# -*- coding: utf-8 -*-

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import sqlite3
from database.treatment_history_db import get_treatment_db

def check_session_data():
    """Session verilerini detaylı kontrol eder"""
    
    db = get_treatment_db()
    
    print("=== SESSION TABLOSU ===")
    with sqlite3.connect(db.db_path) as conn:
        cursor = conn.cursor()
        
        # Son session'ı al
        cursor.execute('''
            SELECT id, session_date, start_time, end_time, duration_minutes, 
                   treatment_mode, target_condition, operator_name, patient_name,
                   session_status, created_at, updated_at
            FROM treatment_sessions 
            ORDER BY id DESC LIMIT 1
        ''')
        
        session = cursor.fetchone()
        if session:
            print(f"Session ID: {session[0]}")
            print(f"Tarih: {session[1]}")
            print(f"Başlangıç: {session[2]}")
            print(f"Bitiş: {session[3]}")
            print(f"Süre: {session[4]} dakika")
            print(f"Tedavi Modu: {session[5]}")
            print(f"Hedef Durum: {session[6]}")
            print(f"Operatör: {session[7]}")
            print(f"Hasta Adı: {session[8]}")
            print(f"Durum: {session[9]}")
            print(f"Oluşturulma: {session[10]}")
            print(f"Güncellenme: {session[11]}")
            
            session_id = session[0]
            
            print(f"\n=== SESSION PARAMETERS (Session ID: {session_id}) ===")
            cursor.execute('''
                SELECT parameter_name, parameter_value
                FROM session_parameters 
                WHERE session_id = ?
                ORDER BY parameter_name
            ''', (session_id,))
            
            parameters = cursor.fetchall()
            if parameters:
                for param_name, param_value in parameters:
                    print(f"{param_name}: {param_value}")
            else:
                print("Hiç parametre bulunamadı!")
        else:
            print("Hiç session bulunamadı!")

if __name__ == "__main__":
    check_session_data()