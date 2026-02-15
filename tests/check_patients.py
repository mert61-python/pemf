#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
sys.path.append(os.path.dirname(__file__))

from database.patient_database import get_patient_database
from database.treatment_history_db import get_treatment_db
import json

def main():
    print('=== VERİTABANINDAKİ HASTA BİLGİLERİ ===')
    db = get_patient_database()
    patients = db.get_all_patients()
    print(f'Toplam hasta sayısı: {len(patients)}')
    print()

    # Son 3 hastayı göster
    for i, patient in enumerate(patients[-3:], 1):
        print(f'{i}. Hasta:')
        print(f'   ID: {patient.get("id", "N/A")[:8]}...')
        print(f'   Ad: "{patient.get("name", "N/A")}"')
        print(f'   Tür: "{patient.get("species", "N/A")}"')
        print(f'   Irk: "{patient.get("breed", "N/A")}"')
        print(f'   Yaş: "{patient.get("age", "N/A")}"')
        print(f'   Ağırlık: "{patient.get("weight", "N/A")}"')
        print(f'   Sahip: "{patient.get("owner", "N/A")}"')
        print(f'   Veteriner: "{patient.get("vet_contact", "N/A")}"')
        print()

    print('\n=== SESSION VERİLERİNDEKİ HASTA BİLGİLERİ ===')
    history_db = get_treatment_db()
    sessions = history_db.get_session_history()
    print(f'Toplam session sayısı: {len(sessions)}')
    print()

    # Son 3 session'ı göster
    for i, session in enumerate(sessions[-3:], 1):
        print(f'{i}. Session:')
        session_id = session.get("id", "N/A")
        if isinstance(session_id, int):
            print(f'   Session ID: {session_id}')
        else:
            print(f'   Session ID: {str(session_id)[:8]}...')
        print(f'   Tarih: {session.get("start_time", "N/A")}')
        print(f'   Hasta Adı: "{session.get("patient_name", "N/A")}"')
        print(f'   Hasta Türü: "{session.get("patient_species", "N/A")}"')
        print(f'   Hasta Irkı: "{session.get("patient_breed", "N/A")}"')
        print(f'   Hasta Yaşı: "{session.get("patient_age", "N/A")}"')
        print(f'   Hasta Ağırlığı: "{session.get("patient_weight", "N/A")}"')
        print(f'   Hasta Sahibi: "{session.get("patient_owner", "N/A")}"')
        print(f'   Veteriner: "{session.get("patient_vet_contact", "N/A")}"')
        print()

if __name__ == "__main__":
    main()