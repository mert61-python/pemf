# -*- coding: utf-8 -*-
"""
Karakter Encoding Test Scripti
Hasta kayıt sisteminde Türkçe karakterler, özel semboller ve büyük/küçük harf duyarlılığını test eder.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.patient_database import get_patient_database
from windows.treatment_history_window import TreatmentHistoryWindow

def test_character_encoding():
    """Karakter encoding testlerini çalıştır"""
    print("🧪 Karakter Encoding Testleri Başlatılıyor...")
    
    # Test verileri - Türkçe karakterler, özel semboller, büyük/küçük harf
    test_patients = [
        {
            "name": "Çiğdem",
            "species": "Köpek", 
            "breed": "Golden Retriever",
            "age": "3 yaş",
            "weight": "25.5 kg",
            "owner": "Mehmet ÖZTÜRK",
            "vet_contact": "Dr. Şule İNCE - 0532-123-4567"
        },
        {
            "name": "Müşfik",
            "species": "kedi",  # küçük harf
            "breed": "van kedisi",  # küçük harf
            "age": "2 YAŞ",  # büyük harf
            "weight": "4.2 KG",  # büyük harf
            "owner": "ayşe güneş",  # küçük harf
            "vet_contact": "dr. ümit çelik - 0555-987-6543"  # küçük harf
        },
        {
            "name": "Şeker & Bal",  # özel sembol
            "species": "Kuş",
            "breed": "Muhabbet Kuşu",
            "age": "1.5 yaş",
            "weight": "45 gr",
            "owner": "Gülşah YILMAZ-KAYA",  # tire işareti
            "vet_contact": "Prof. Dr. Özgür ŞAHIN (Uzman) - 0212-555-0123"  # parantez ve özel karakterler
        },
        {
            "name": "Çağla'nın Kedisi",  # apostrof
            "species": "Kedi",
            "breed": "Tekir",
            "age": "5",  # sadece sayı
            "weight": "3.8",  # sadece sayı
            "owner": "İbrahim & Zeynep ÇAĞLAR",  # & işareti
            "vet_contact": "Vet. Hekim Gökçe ÜNAL - gokce@vetclinic.com"  # email
        },
        {
            "name": "",  # boş isim
            "species": "Köpek",
            "breed": "",  # boş ırk
            "age": "Bilinmiyor",
            "weight": "",  # boş ağırlık
            "owner": "Test Kullanıcısı",
            "vet_contact": ""  # boş veteriner
        }
    ]
    
    db = get_patient_database()
    
    print("\n📝 Test Hastalarını Kaydediyor...")
    saved_patients = []
    
    for i, patient in enumerate(test_patients, 1):
        try:
            print(f"\n{i}. Hasta: {patient['name'] or 'BOŞ İSİM'}")
            print(f"   Tür: {patient['species']}")
            print(f"   Irk: {patient['breed']}")
            print(f"   Yaş: {patient['age']}")
            print(f"   Ağırlık: {patient['weight']}")
            print(f"   Sahip: {patient['owner']}")
            print(f"   Veteriner: {patient['vet_contact']}")
            
            patient_id = db.add_patient(patient)
            saved_patients.append(patient_id)
            print(f"   ✅ Kaydedildi - ID: {patient_id[:8]}...")
            
        except Exception as e:
            print(f"   ❌ Hata: {e}")
    
    print(f"\n📊 Toplam {len(saved_patients)} hasta kaydedildi.")
    
    # Kaydedilen hastaları geri oku ve kontrol et
    print("\n🔍 Kaydedilen Verileri Kontrol Ediyor...")
    
    for patient_id in saved_patients:
        try:
            patient = db.get_patient(patient_id)
            if patient:
                print(f"\n📋 Hasta ID: {patient_id[:8]}...")
                print(f"   İsim: '{patient['name']}'")
                print(f"   Tür: '{patient['species']}'")
                print(f"   Irk: '{patient['breed']}'")
                print(f"   Yaş: '{patient['age']}'")
                print(f"   Ağırlık: '{patient['weight']}'")
                print(f"   Sahip: '{patient['owner']}'")
                print(f"   Veteriner: '{patient['vet_contact']}'")
                
                # Karakter encoding kontrolü
                for key, value in patient.items():
                    if isinstance(value, str):
                        if any(char in value for char in 'çğıöşüÇĞIİÖŞÜ'):
                            print(f"   🇹🇷 Türkçe karakter tespit edildi: {key} = '{value}'")
                        if any(char in value for char in '&()-@.'):
                            print(f"   🔣 Özel sembol tespit edildi: {key} = '{value}'")
            else:
                print(f"   ❌ Hasta bulunamadı: {patient_id}")
                
        except Exception as e:
            print(f"   ❌ Okuma hatası: {e}")
    
    print("\n🧪 Test Tamamlandı!")
    return saved_patients

def test_get_safe_value_function():
    """get_safe_value fonksiyonunu test et"""
    print("\n🔧 get_safe_value Fonksiyon Testleri...")
    
    # treatment_history_window'dan get_safe_value fonksiyonlarını test et
    test_values = [
        ("Çağla", "Normal Türkçe karakter"),
        ("", "Boş string"),
        (None, "None değeri"),
        ("none", "Küçük harf none"),
        ("NONE", "Büyük harf NONE"),
        ("None", "Başlık harf None"),
        ("Belirtilmemiş", "Belirtilmemiş değeri"),
        ("BELİRTİLMEMİŞ", "Büyük harf Belirtilmemiş"),
        ("Müşfik & Çiğdem", "Özel karakterli isim"),
        ("Dr. Özgür ŞAHIN", "Profesyonel unvan"),
        ("0", "Sıfır değeri"),
        ("", "Boş string tekrar")
    ]
    
    # İlk get_safe_value fonksiyonu (update_table'dan)
    def get_safe_value_1(value, default='Bilinmiyor'):
        if value is None or value == '' or str(value).lower() == 'none' or str(value) == 'Belirtilmemiş':
            return default
        return str(value)
    
    # İkinci get_safe_value fonksiyonu (load_session_details'den)
    def get_safe_value_2(param_dict, default='Belirtilmemiş'):
        if isinstance(param_dict, dict):
            value = param_dict.get('value', default)
            if value is None or value == '' or str(value).lower() == 'none':
                return default
            return str(value)
        return default
    
    print("\n📋 get_safe_value_1 (update_table) Testleri:")
    for value, description in test_values:
        result = get_safe_value_1(value)
        print(f"   {description}: '{value}' -> '{result}'")
    
    print("\n📋 get_safe_value_2 (load_session_details) Testleri:")
    for value, description in test_values:
        # Dict formatında test
        dict_value = {'value': value, 'unit': ''}
        result = get_safe_value_2(dict_value)
        print(f"   {description} (dict): {dict_value} -> '{result}'")
        
        # Direkt değer testi
        result_direct = get_safe_value_2(value)
        print(f"   {description} (direct): '{value}' -> '{result_direct}'")

if __name__ == "__main__":
    print("🚀 Karakter Encoding Test Scripti Başlatılıyor...\n")
    
    try:
        # Hasta kayıt testleri
        saved_patients = test_character_encoding()
        
        # get_safe_value fonksiyon testleri
        test_get_safe_value_function()
        
        print("\n✅ Tüm testler tamamlandı!")
        
    except Exception as e:
        print(f"\n❌ Test hatası: {e}")
        import traceback
        traceback.print_exc()