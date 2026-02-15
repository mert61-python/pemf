#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.patient_database import get_patient_database
from database.treatment_history_db import get_treatment_db
from utils.value_utils import normalize_patient_data

def debug_patient_save():
    """Hasta kaydetme işlemini debug eder"""
    
    # Son kaydedilen hastayı al
    patient_db = get_patient_database()
    patients = patient_db.get_all_patients()
    
    if not patients:
        print("Hiç hasta bulunamadı!")
        return
    
    last_patient = patients[-1]
    print("=== SON KAYDEDİLEN HASTA ===")
    print(f"ID: {last_patient.get('id', 'N/A')}")
    print(f"Ad: {last_patient.get('name', 'N/A')}")
    print(f"Tür: {last_patient.get('species', 'N/A')}")
    print(f"Irk: {last_patient.get('breed', 'N/A')}")
    print(f"Yaş: {last_patient.get('age', 'N/A')}")
    print(f"Ağırlık: {last_patient.get('weight', 'N/A')}")
    print(f"Sahip: {last_patient.get('owner', 'N/A')}")
    print(f"Veteriner: {last_patient.get('vet_contact', 'N/A')}")
    
    # Normalize işlemini test et
    print("\n=== NORMALİZE İŞLEMİ ===")
    
    # last_saved_patient formatında simüle et
    simulated_last_saved = {
        "id": last_patient.get('id'),
        "info": last_patient
    }
    
    print(f"Simulated last_saved_patient: {simulated_last_saved}")
    
    if 'info' in simulated_last_saved:
        info = simulated_last_saved['info']
        print(f"Info: {info}")
        
        normalized_info = normalize_patient_data(info)
        print(f"Normalized info: {normalized_info}")
        
        # Session parametrelerini simüle et
        print("\n=== SESSION PARAMETRELERİ ===")
        session_params = {}
        session_params["patient_name"] = {'value': normalized_info['name'], 'unit': ''}
        session_params["patient_age"] = {'value': normalized_info['age'], 'unit': ''}
        session_params["patient_species"] = {'value': normalized_info['species'], 'unit': ''}
        session_params["patient_breed"] = {'value': normalized_info['breed'], 'unit': ''}
        session_params["patient_weight"] = {'value': normalized_info['weight'], 'unit': 'kg'}
        session_params["patient_owner"] = {'value': normalized_info['owner'], 'unit': ''}
        session_params["patient_vet_contact"] = {'value': normalized_info['vet_contact'], 'unit': ''}
        
        for key, value in session_params.items():
            print(f"{key}: {value}")

if __name__ == "__main__":
    debug_patient_save()