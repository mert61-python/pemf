# -*- coding: utf-8 -*-
"""
Merkezi değer güvenlik fonksiyonları
Bu modül, tüm sistemde tutarlı default değer yönetimi sağlar.
"""

def get_safe_value(value, default='Belirtilmemiş'):
    """
    Güvenli değer döndürür. None, boş string veya problematik değerler için default döndürür.
    
    Args:
        value: Kontrol edilecek değer
        default: Varsayılan değer (default: 'Belirtilmemiş')
    
    Returns:
        str: Güvenli değer veya default
    """
    if value is None:
        return default
    
    # String'e çevir ve strip et
    str_value = str(value).strip()
    
    # Boş string kontrolü
    if not str_value:
        return default
    
    # Küçük harfe çevir
    lower_value = str_value.lower()
    
    # Türkçe karakterleri normalize et
    normalized_value = lower_value
    turkish_chars = {'ı': 'i', 'ş': 's', 'ğ': 'g', 'ü': 'u', 'ö': 'o', 'ç': 'c', 'İ': 'i'}
    for tr_char, en_char in turkish_chars.items():
        normalized_value = normalized_value.replace(tr_char, en_char)
    
    # Problematik değerler listesi
    problematic_values = {
        'none',
        'belirtilmemis',  # normalize edilmiş hali
        'belirtilmemiş',  # orijinal Türkçe hali
        'belirsiz',
        'bilgi yok',
        'yok',
        '-',
        '?',
        'bilinmiyor',
        'bilinmıyor',     # alternatif yazım
        'n/a',
        'na',
        'null',
        'undefined'
    }
    
    # Problematik değer kontrolü
    if lower_value in problematic_values or normalized_value in problematic_values:
        return default
    
    return str_value


def get_safe_patient_name(value):
    """
    Hasta adı için özel güvenli değer fonksiyonu.
    
    Args:
        value: Hasta adı değeri
    
    Returns:
        str: Güvenli hasta adı veya 'Belirtilmemiş'
    """
    return get_safe_value(value, 'Belirtilmemiş')


def get_safe_patient_info(value):
    """
    Hasta bilgileri için özel güvenli değer fonksiyonu.
    
    Args:
        value: Hasta bilgisi değeri
    
    Returns:
        str: Güvenli hasta bilgisi veya 'Belirtilmemiş'
    """
    return get_safe_value(value, 'Belirtilmemiş')


def normalize_patient_data(patient_data):
    """
    Hasta verilerini normalize eder.
    
    Args:
        patient_data (dict): Hasta verileri dictionary'si
    
    Returns:
        dict: Normalize edilmiş hasta verileri
    """
    if not isinstance(patient_data, dict):
        return {}
    
    normalized = {}
    
    # Hasta bilgisi alanları
    patient_fields = [
        'name', 'age', 'species', 'breed', 'weight', 
        'owner', 'vet_contact', 'patient_id'
    ]
    
    for field in patient_fields:
        if field in patient_data:
            normalized[field] = get_safe_value(patient_data[field])
        else:
            normalized[field] = 'Belirtilmemiş'
    
    return normalized
