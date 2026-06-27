"""
Patient Input Validator
=======================

Provides real-time validation and suggestions for patient information input.
Helps users enter data in AI-compatible format.
"""

import sys
from pathlib import Path
from typing import Tuple, Optional, List

# Add parent directory to path for direct execution
if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from ai.hybrid_recommender import normalize_species
except ImportError:
    # Fallback if ai module not available
    def normalize_species(species_str):
        """Fallback normalize_species function"""
        species_map = {
            'köpek': 'dog', 'kopek': 'dog', 'dog': 'dog',
            'kedi': 'cat', 'ked': 'cat', 'cat': 'cat',
            'at': 'horse', 'horse': 'horse',
            'tavşan': 'rabbit', 'tavsan': 'rabbit', 'rabbit': 'rabbit'
        }
        return species_map.get(species_str.lower(), 'dog')


class PatientInputValidator:
    """
    Validates and provides suggestions for patient input fields.
    """
    
    # Tür önerileri
    SPECIES_SUGGESTIONS = {
        'dog': ['Köpek', 'Dog', 'Kopek'],
        'cat': ['Kedi', 'Cat', 'Ked'],
        'horse': ['At', 'Horse'],
        'rabbit': ['Tavşan', 'Rabbit', 'Tavsan']
    }
    
    # Yaygın köpek ırkları
    DOG_BREEDS = [
        'Golden Retriever', 'Labrador', 'German Shepherd', 'Bulldog',
        'Poodle', 'Husky', 'Beagle', 'Corgi', 'Chihuahua',
        'Kangal', 'Akbaş', 'Malaklı', 'Karışık'
    ]
    
    # Yaygın kedi ırkları
    CAT_BREEDS = [
        'Persian', 'British Shorthair', 'Scottish Fold', 'Siamese',
        'Van Kedisi', 'Ankara Kedisi', 'Tekir', 'Karışık'
    ]
    
    @staticmethod
    def validate_species(species_text: str) -> Tuple[bool, str, Optional[str]]:
        """
        Tür bilgisini validate et.
        
        Returns:
            (is_valid, message, suggestion)
        """
        if not species_text.strip():
            return False, "⚠️ Tür bilgisi boş bırakılamaz", None
        
        # Normalize et ve kontrol et
        normalized = normalize_species(species_text)
        
        # Bilinen bir türe dönüştü mü?
        if normalized and normalized in ['dog', 'cat', 'horse', 'rabbit']:
            species_name = {
                'dog': 'Köpek',
                'cat': 'Kedi', 
                'horse': 'At',
                'rabbit': 'Tavşan'
            }[normalized]
            
            # Kullanıcının yazdığı normalize edilmiş halinden farklıysa uyar
            if species_text.lower().strip() not in [normalized, species_name.lower()]:
                return True, f"✅ '{species_name}' olarak algılandı", species_name
            else:
                return True, f"✅ Geçerli tür: {species_name}", None
        else:
            # Bilinmeyen tür - uyarı mesajı göster ama kaydetmeye izin ver
            return True, f"ℹ️ '{species_text}' AI tarafından desteklenmiyor. Desteklenen: Köpek, Kedi, At, Tavşan", None
    
    @staticmethod
    def validate_breed(breed_text: str, species: str) -> Tuple[bool, str, Optional[str]]:
        """
        Irk bilgisini validate et.
        
        Returns:
            (is_valid, message, suggestion)
        """
        if not breed_text.strip():
            return True, "ℹ️ Irk bilgisi opsiyonel (Karışık yazabilirsiniz)", "Karışık"
        
        # Türe göre irk önerileri
        normalized_species = normalize_species(species) if species else 'dog'
        
        if normalized_species == 'dog':
            breeds = PatientInputValidator.DOG_BREEDS
            species_name = "köpek"
        elif normalized_species == 'cat':
            breeds = PatientInputValidator.CAT_BREEDS
            species_name = "kedi"
        else:
            # At ve tavşan için özel kontrol yok
            return True, "✅ Irk bilgisi kaydedildi", None
        
        # Girilen ırk listede var mı kontrol et
        breed_lower = breed_text.lower().strip()
        for known_breed in breeds:
            if known_breed.lower() in breed_lower or breed_lower in known_breed.lower():
                return True, f"✅ Geçerli {species_name} ırkı", None
        
        # Bilinmeyen ırk - öneri yap
        top_breeds = breeds[:5]
        suggestions = ", ".join(top_breeds)
        return True, f"ℹ️ Yaygın {species_name} ırkları: {suggestions}", None
    
    @staticmethod
    def validate_age(age_text: str) -> Tuple[bool, str, Optional[str]]:
        """
        Yaş bilgisini validate et.
        
        Returns:
            (is_valid, message, suggestion)
        """
        if not age_text.strip():
            return False, "⚠️ Yaş bilgisi boş bırakılamaz", "5"
        
        try:
            age = float(age_text.replace(',', '.'))
            
            if age < 0:
                return False, "❌ Yaş negatif olamaz", "1"
            elif age == 0:
                return False, "❌ Yaş 0 olamaz (yavru için 0.5 yazabilirsiniz)", "0.5"
            elif age > 50:
                return False, "❌ Yaş çok yüksek (maksimum 50)", "15"
            elif age < 1:
                return True, f"✅ Yavru hayvan ({age} yaş)", None
            elif age <= 8:
                return True, f"✅ Yetişkin hayvan ({age} yaş)", None
            else:
                return True, f"✅ Yaşlı hayvan ({age} yaş)", None
                
        except ValueError:
            return False, "❌ Geçersiz sayı formatı (örn: 5 veya 5.5)", "5"
    
    @staticmethod
    def validate_weight(weight_text: str, species: str) -> Tuple[bool, str, Optional[str]]:
        """
        Ağırlık bilgisini validate et.
        
        Returns:
            (is_valid, message, suggestion)
        """
        if not weight_text.strip():
            return False, "⚠️ Ağırlık bilgisi boş bırakılamaz", "20"
        
        try:
            weight = float(weight_text.replace(',', '.'))
            
            if weight <= 0:
                return False, "❌ Ağırlık 0'dan büyük olmalı", "5"
            
            # Türe göre makul aralık kontrolü
            normalized_species = normalize_species(species) if species else 'dog'
            
            if normalized_species == 'cat':
                if weight < 1:
                    return False, "❌ Kediler için çok düşük (min: 1kg)", "3"
                elif weight > 15:
                    return False, "⚠️ Kediler için çok yüksek (maks: ~12kg)", "5"
                elif weight < 3:
                    return True, f"✅ Küçük kedi ({weight}kg)", None
                elif weight < 6:
                    return True, f"✅ Orta boy kedi ({weight}kg)", None
                else:
                    return True, f"✅ Büyük kedi ({weight}kg)", None
                    
            elif normalized_species == 'dog':
                if weight < 1:
                    return False, "❌ Köpekler için çok düşük (min: 1kg)", "10"
                elif weight > 100:
                    return False, "⚠️ Köpekler için çok yüksek (maks: ~90kg)", "30"
                elif weight < 10:
                    return True, f"✅ Küçük köpek ({weight}kg)", None
                elif weight < 30:
                    return True, f"✅ Orta boy köpek ({weight}kg)", None
                elif weight < 50:
                    return True, f"✅ Büyük köpek ({weight}kg)", None
                else:
                    return True, f"✅ Dev köpek ({weight}kg)", None
                    
            elif normalized_species == 'horse':
                if weight < 100:
                    return False, "❌ Atlar için çok düşük (min: 100kg, pony için 200kg)", "400"
                elif weight > 1000:
                    return False, "⚠️ Atlar için çok yüksek (maks: ~900kg)", "500"
                else:
                    return True, f"✅ At ağırlığı ({weight}kg)", None
                    
            elif normalized_species == 'rabbit':
                if weight < 0.5:
                    return False, "❌ Tavşanlar için çok düşük (min: 0.5kg)", "2"
                elif weight > 10:
                    return False, "⚠️ Tavşanlar için çok yüksek (maks: ~8kg)", "3"
                else:
                    return True, f"✅ Tavşan ağırlığı ({weight}kg)", None
            else:
                return True, f"✅ Ağırlık: {weight}kg", None
                
        except ValueError:
            return False, "❌ Geçersiz sayı formatı (örn: 20 veya 20.5)", "20"
    
    @staticmethod
    def validate_name(name_text: str) -> Tuple[bool, str, Optional[str]]:
        """
        Hayvan adını validate et.
        
        Returns:
            (is_valid, message, suggestion)
        """
        if not name_text.strip():
            return False, "⚠️ Hayvan adı boş bırakılamaz", None
        
        if len(name_text.strip()) < 2:
            return False, "⚠️ Hayvan adı en az 2 karakter olmalı", None
        
        # Sadece rakamlardan oluşuyor mu?
        if name_text.strip().isdigit():
            return False, "❌ Hayvan adı sadece rakamlardan oluşamaz", None
        
        return True, f"✅ Hayvan adı: {name_text.strip()}", None
    
    @staticmethod
    def validate_owner(owner_text: str) -> Tuple[bool, str, Optional[str]]:
        """
        Sahip bilgisini validate et.
        
        Returns:
            (is_valid, message, suggestion)
        """
        if not owner_text.strip():
            return False, "⚠️ Sahip bilgisi boş bırakılamaz", None
        
        if len(owner_text.strip()) < 3:
            return False, "⚠️ Sahip adı en az 3 karakter olmalı", None
        
        return True, f"✅ Sahip: {owner_text.strip()}", None
    
    @staticmethod
    def get_species_autocomplete_list() -> List[str]:
        """Tür için otomatik tamamlama listesi"""
        return ['Köpek', 'Kedi', 'At', 'Tavşan', 'Dog', 'Cat', 'Horse', 'Rabbit']
    
    @staticmethod
    def get_breed_autocomplete_list(species: str) -> List[str]:
        """Irk için otomatik tamamlama listesi"""
        normalized = normalize_species(species) if species else 'dog'
        
        if normalized == 'dog':
            return PatientInputValidator.DOG_BREEDS
        elif normalized == 'cat':
            return PatientInputValidator.CAT_BREEDS
        else:
            return ['Karışık', 'Safkan']
