"""
Hybrid PEMF Parameter Recommender
==================================

Combines rule-based clinical protocols with adaptive patient profiling
and interpolation for comprehensive treatment recommendations.

Features:
- Literature-based clinical protocols (18+ conditions)
- Species, age, weight-based adaptations
- Intelligent parameter interpolation for unknown conditions
- Session history analysis (learns from past treatments)
- Veterinary observation integration

@author: merta
@date: 2025-12-04
"""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def clean_treatment_target(text: str) -> str:
    """
    Tedavi hedefi metnini temizle (emoji ve özel karakterleri kaldır).
    
    Args:
        text: Ham metin (örn: '🔥 İnflamasyon')
        
    Returns:
        Temizlenmiş metin (örn: 'inflamasyon')
    """
    # Türkçe karakter dönüşümü (Python lower() Türkçe İ'yi yanlış çevirir)
    tr_map = str.maketrans('İıĞğÜüŞşÖöÇç', 'iigguussoocc')
    text = text.translate(tr_map)
    
    # Emoji ve özel karakterleri kaldır (sadece harf, rakam, boşluk ve tire)
    text = re.sub(r'[^\w\s-]', '', text, flags=re.ASCII)
    
    # Fazla boşlukları temizle ve küçük harfe çevir
    text = ' '.join(text.split()).lower().strip()
    return text


# Tür eşleştirme sözlüğü (yaygın yazım hataları + ırk varyasyonları → kanonik tür).
# Fonksiyondan çıkarıldı: statik veri; her çağrıda yeniden kurulmaz + tek yerden güncellenir.
# INVARYANT: girdi eşleşmeden ÖNCE clean_treatment_target()'ten geçer (Türkçe ı→i, küçük harf vb.).
# Bu yüzden ANAHTARLAR da ASCII-temiz olmalı ('kopek'/'tavsan'/'malakli') — aksi halde hiç eşleşmez.
_SPECIES_MAP = {
    # Köpek
    'dog': 'dog',
    'kopek': 'dog',
    'kopegi': 'dog',
    'kopk': 'dog',
    'doggo': 'dog',
    'k9': 'dog',
    # Yaygın köpek ırkları
    'golden': 'dog',
    'retriever': 'dog',
    'labrador': 'dog',
    'german': 'dog',
    'shepherd': 'dog',
    'bulldog': 'dog',
    'poodle': 'dog',
    'husky': 'dog',
    'chihuahua': 'dog',
    'beagle': 'dog',
    'corgi': 'dog',
    'kangal': 'dog',
    'akbas': 'dog',
    'malakli': 'dog',  # FIX: eskiden 'malaklı' (ı'lı) idi → clean() 'malakli' üretince eşleşmiyordu

    # Kedi
    'cat': 'cat',
    'kedi': 'cat',
    'kedı': 'cat',
    'kitty': 'cat',
    'feline': 'cat',
    # Yaygın kedi ırkları
    'persian': 'cat',
    'siamese': 'cat',
    'british': 'cat',
    'shorthair': 'cat',
    'scottish': 'cat',
    'fold': 'cat',
    'van': 'cat',
    'ankara': 'cat',

    # At
    'horse': 'horse',
    'at': 'horse',
    'equine': 'horse',
    'pony': 'horse',
    'mare': 'horse',
    'stallion': 'horse',
    'arap': 'horse',
    'safkan': 'horse',

    # Tavşan
    'rabbit': 'rabbit',
    'tavsan': 'rabbit',
    'bunny': 'rabbit',
    'hare': 'rabbit',
}


def normalize_species(species: str) -> str:
    """Tür/ırk adını kanonik türe normalize et (yazım-hatası toleranslı): 'dog'/'cat'/'horse'/'rabbit',
    bilinmiyorsa None. Sıra: temizle → tam eşleşme → kelime-bazlı → substring → bilinmeyen."""
    normalized = clean_treatment_target(species)

    # 1) Tam eşleşme
    if normalized in _SPECIES_MAP:
        return _SPECIES_MAP[normalized]

    # 2) Kelime bazlı eşleşme (ırk adında tür geçiyor mu?)
    for word in normalized.split():
        if word in _SPECIES_MAP:
            matched = _SPECIES_MAP[word]
            logger.debug(f"Species normalized: '{species}' -> '{matched}' (via word '{word}')")
            return matched

    # 3) Substring eşleşmesi (son çare)
    for key, value in _SPECIES_MAP.items():
        if key in normalized or normalized in key:
            logger.debug(f"Species normalized: '{species}' -> '{value}' (via substring '{key}')")
            return value

    # Bilinmeyen tür → None
    logger.warning(f"Unknown species '{species}', not supported for AI")
    return None


# ==================== CLINICAL PROTOCOL DATABASE ====================
CLINICAL_PROTOCOLS = {
    'kronik artrit': {'freq': 70, 'duty': 50, 'duration': 30, 'intensity': 1.75, 'evidence': 'high'},
    'osteoartrit': {'freq': 80, 'duty': 50, 'duration': 30, 'intensity': 1.75, 'evidence': 'high'},
    'ağrı': {'freq': 70, 'duty': 50, 'duration': 30, 'intensity': 1.75, 'evidence': 'high'},
    'akut ağrı': {'freq': 85, 'duty': 55, 'duration': 20, 'intensity': 1.5, 'evidence': 'medium'},
    'inflamasyon': {'freq': 87, 'duty': 47, 'duration': 27, 'intensity': 1.25, 'evidence': 'high'},
    'iltihap': {'freq': 87, 'duty': 47, 'duration': 27, 'intensity': 1.25, 'evidence': 'high'},
    'kırık': {'freq': 60, 'duty': 37, 'duration': 52, 'intensity': 2.0, 'evidence': 'high'},
    'kemik': {'freq': 60, 'duty': 37, 'duration': 52, 'intensity': 2.0, 'evidence': 'high'},
    'post-op yara': {'freq': 95, 'duty': 50, 'duration': 30, 'intensity': 1.5, 'evidence': 'high'},
    'yara': {'freq': 95, 'duty': 50, 'duration': 30, 'intensity': 1.5, 'evidence': 'high'},
    'doku': {'freq': 105, 'duty': 50, 'duration': 30, 'intensity': 1.5, 'evidence': 'high'},
    'anksiyete': {'freq': 62, 'duty': 45, 'duration': 37, 'intensity': 2.0, 'evidence': 'medium'},
    'stres': {'freq': 62, 'duty': 45, 'duration': 37, 'intensity': 2.0, 'evidence': 'medium'},
    'kas': {'freq': 97, 'duty': 50, 'duration': 25, 'intensity': 1.5, 'evidence': 'high'},
    'spazm': {'freq': 97, 'duty': 50, 'duration': 25, 'intensity': 1.5, 'evidence': 'high'},
    'kas yorgunluğu': {'freq': 90, 'duty': 48, 'duration': 22, 'intensity': 1.3, 'evidence': 'medium'},
    'nörolojik': {'freq': 70, 'duty': 42, 'duration': 37, 'intensity': 1.15, 'evidence': 'high'},
    'ivdd': {'freq': 70, 'duty': 42, 'duration': 37, 'intensity': 1.15, 'evidence': 'high'},
    'nöropati': {'freq': 70, 'duty': 42, 'duration': 37, 'intensity': 1.15, 'evidence': 'high'},
    'wellness': {'freq': 77, 'duty': 50, 'duration': 30, 'intensity': 1.0, 'evidence': 'high'},
    'rahatlama': {'freq': 77, 'duty': 50, 'duration': 30, 'intensity': 1.0, 'evidence': 'high'},
    'ödem': {'freq': 110, 'duty': 45, 'duration': 25, 'intensity': 1.5, 'evidence': 'medium'},
    'tendon': {'freq': 75, 'duty': 40, 'duration': 37, 'intensity': 1.75, 'evidence': 'high'},
    'ligament': {'freq': 75, 'duty': 40, 'duration': 37, 'intensity': 1.75, 'evidence': 'high'},
}


class PatientProfileAdaptor:
    """
    Adapts treatment parameters based on patient characteristics.
    """
    
    ADAPTATION_RULES = {
        # Tür bazlı faktörler
        'species': {
            'dog': {'intensity': 1.0, 'duration': 1.0},
            'köpek': {'intensity': 1.0, 'duration': 1.0},
            'cat': {'intensity': 0.7, 'duration': 0.8},
            'kedi': {'intensity': 0.7, 'duration': 0.8},
            'horse': {'intensity': 1.3, 'duration': 1.2},
            'at': {'intensity': 1.3, 'duration': 1.2},
            'rabbit': {'intensity': 0.6, 'duration': 0.7},
            'tavşan': {'intensity': 0.6, 'duration': 0.7},
        },
        
        # Yaş kategorileri
        'age_categories': {
            'young': {'intensity': 0.85, 'duration': 0.9},   # <2 yaş
            'adult': {'intensity': 1.0, 'duration': 1.0},    # 2-8 yaş
            'senior': {'intensity': 0.8, 'duration': 0.85}   # >8 yaş
        },
        
        # Ağırlık kategorileri (kg)
        'weight_categories': {
            'small': {'duration': 0.75},      # <10kg
            'medium': {'duration': 1.0},      # 10-30kg
            'large': {'duration': 1.2},       # 30-50kg
            'giant': {'duration': 1.4}        # >50kg
        }
    }
    
    def categorize_age(self, age: float) -> str:
        """Yaşı kategorize et"""
        if age < 2:
            return 'young'
        elif age <= 8:
            return 'adult'
        else:
            return 'senior'
    
    def categorize_weight(self, weight: float) -> str:
        """Ağırlığı kategorize et"""
        if weight < 10:
            return 'small'
        elif weight <= 30:
            return 'medium'
        elif weight <= 50:
            return 'large'
        else:
            return 'giant'
    
    def normalize_patient_info(self, patient_info: Dict) -> Dict:
        """
        Hasta bilgilerini normalize et.
        
        Args:
            patient_info: Ham hasta bilgileri
            
        Returns:
            Normalize edilmiş hasta bilgileri
        """
        normalized = patient_info.copy()
        
        # Tür normalizasyonu
        if 'species' in normalized:
            species_normalized = normalize_species(normalized['species'])
            # None dönerse (bilinmeyen tür) varsayılan köpek kullan ama uyar
            if species_normalized is None:
                logger.warning(f"Species '{normalized['species']}' not in AI database, using 'dog' as fallback")
                normalized['species'] = 'dog'
                normalized['species_unsupported'] = True  # Flag ekle
            else:
                normalized['species'] = species_normalized
                normalized['species_unsupported'] = False
        
        # Yaş ve ağırlık varsayılanları
        if 'age' not in normalized or normalized['age'] is None:
            normalized['age'] = 5.0
        if 'weight' not in normalized or normalized['weight'] is None:
            normalized['weight'] = 20.0
            
        return normalized
    
    def adapt(self, base_params: Dict, patient_info: Dict) -> Dict:
        """
        Temel protokolü hasta profiline göre uyarla.
        
        Args:
            base_params: Temel protokol parametreleri
            patient_info: Hasta bilgileri (species, age, weight)
            
        Returns:
            Uyarlanmış parametreler
        """
        # Önce hasta bilgilerini normalize et
        patient_info = self.normalize_patient_info(patient_info)
        
        adapted = base_params.copy()
        
        # Tür adaptasyonu (artık normalize edilmiş)
        species = patient_info.get('species', 'dog')
        species_factor = self.ADAPTATION_RULES['species'].get(
            species, 
            self.ADAPTATION_RULES['species']['dog']
        )
        adapted['intensity'] = adapted.get('intensity', 1.0) * species_factor['intensity']
        adapted['duration'] = int(adapted['duration'] * species_factor['duration'])
        
        # Yaş adaptasyonu
        age = patient_info.get('age', 5)
        age_category = self.categorize_age(age)
        age_factor = self.ADAPTATION_RULES['age_categories'][age_category]
        adapted['intensity'] = adapted.get('intensity', 1.0) * age_factor['intensity']
        adapted['duration'] = int(adapted['duration'] * age_factor['duration'])
        
        # Ağırlık adaptasyonu
        weight = patient_info.get('weight', 15)
        weight_category = self.categorize_weight(weight)
        weight_factor = self.ADAPTATION_RULES['weight_categories'][weight_category]
        adapted['duration'] = int(adapted['duration'] * weight_factor['duration'])
        
        # Duty cycle'ı sınırla (10-95%)
        adapted['duty'] = max(10.0, min(95.0, adapted['duty']))
        
        # Duration'ı sınırla (5-90 dk)
        adapted['duration'] = max(5, min(90, adapted['duration']))
        
        return adapted


class ParameterInterpolator:
    """
    Bilinmeyen durumlar için benzer protokollerden parametre tahmini.
    """
    
    def calculate_similarity(self, target: str, protocol_name: str) -> float:
        """
        İki durum arasındaki benzerliği hesapla (basit kelime eşleşmesi).
        
        Returns:
            0.0-1.0 arası benzerlik skoru
        """
        # Temizle ve kelimelere ayır
        target_clean = clean_treatment_target(target)
        protocol_clean = clean_treatment_target(protocol_name)
        
        target_words = set(target_clean.split())
        protocol_words = set(protocol_clean.split())
        
        if not target_words or not protocol_words:
            return 0.0
        
        # Jaccard similarity
        intersection = target_words.intersection(protocol_words)
        union = target_words.union(protocol_words)
        
        return len(intersection) / len(union) if union else 0.0
    
    def find_similar_protocols(self, target_condition: str, min_similarity: float = 0.2) -> List[Tuple[str, Dict, float]]:
        """
        Hedef durum için benzer protokolleri bul.
        
        Returns:
            List of (protocol_name, protocol_params, similarity_score)
        """
        similar = []
        
        for protocol_name, params in CLINICAL_PROTOCOLS.items():
            similarity = self.calculate_similarity(target_condition, protocol_name)
            if similarity >= min_similarity:
                similar.append((protocol_name, params, similarity))
        
        # Benzerlik skoruna göre sırala (en yüksekten en düşüğe)
        similar.sort(key=lambda x: x[2], reverse=True)
        
        return similar
    
    def interpolate(self, target_condition: str, top_n: int = 3) -> Optional[Dict]:
        """
        Benzer protokollerden ağırlıklı ortalama ile parametre tahmini.
        
        Args:
            target_condition: Hedef durum
            top_n: Kaç benzer protokol kullanılacak
            
        Returns:
            Tahmin edilen parametreler veya None
        """
        similar = self.find_similar_protocols(target_condition)
        
        if not similar:
            logger.warning(f"'{target_condition}' için benzer protokol bulunamadı")
            return None
        
        # En benzer top_n protokolü al
        top_similar = similar[:top_n]
        
        # Ağırlıkları normalize et
        total_similarity = sum(sim for _, _, sim in top_similar)
        if total_similarity == 0:
            return None
        
        weights = [sim / total_similarity for _, _, sim in top_similar]
        
        # Ağırlıklı ortalama hesapla
        freq = sum(params['freq'] * w for (_, params, _), w in zip(top_similar, weights))
        duty = sum(params['duty'] * w for (_, params, _), w in zip(top_similar, weights))
        duration = sum(params['duration'] * w for (_, params, _), w in zip(top_similar, weights))
        intensity = sum(params['intensity'] * w for (_, params, _), w in zip(top_similar, weights))
        
        logger.info(f"'{target_condition}' için interpolasyon: {len(top_similar)} benzer protokolden tahmin")
        for name, _, sim in top_similar:
            logger.debug(f"  - {name} (benzerlik: {sim:.2f})")
        
        return {
            'freq': int(freq),
            'duty': duty,
            'duration': int(duration),
            'intensity': intensity,
            'evidence': 'interpolated',
            'source_protocols': [name for name, _, _ in top_similar]
        }


class HybridPEMFRecommender:
    """
    Hibrit PEMF parametre önerici.
    
    Combines:
    1. Literature-based clinical protocols
    2. Patient profile adaptation
    3. Parameter interpolation
    4. Session history learning (future)
    """
    
    def __init__(self, app_data_dir: Optional[Path] = None):
        """
        Initialize recommender.
        
        Args:
            app_data_dir: Application data directory for session history
        """
        self.clinical_db = CLINICAL_PROTOCOLS
        self.adaptor = PatientProfileAdaptor()
        self.interpolator = ParameterInterpolator()
        self.app_data_dir = app_data_dir
        
        logger.info(f"Hybrid PEMF Recommender initialized with {len(self.clinical_db)} clinical protocols")
    
    def find_exact_protocol(self, treatment_target: str) -> Optional[Dict]:
        """
        Literatürde TAM eşleşme ara.
        
        Args:
            treatment_target: Tedavi hedefi (emoji içerebilir: '🔥 İnflamasyon')
            
        Returns:
            Protokol parametreleri veya None
        """
        # Emoji ve özel karakterleri temizle
        target_clean = clean_treatment_target(treatment_target)
        
        logger.debug(f"Searching for: '{treatment_target}' -> cleaned: '{target_clean}'")
        
        # Direkt eşleşme
        if target_clean in self.clinical_db:
            logger.info(f"Exact match found: '{target_clean}'")
            return self.clinical_db[target_clean].copy()
        
        # Substring eşleşmesi (tedavi hedefinde protokol adı geçiyor mu?)
        for protocol_name in self.clinical_db.keys():
            if protocol_name in target_clean:
                logger.info(f"Substring match found: '{protocol_name}' in '{target_clean}'")
                return self.clinical_db[protocol_name].copy()
        
        return None
    
    def recommend_parameters(self, 
                            patient_info: Dict,
                            treatment_target: str,
                            session_history: Optional[List[Dict]] = None) -> Dict:
        """
        Akıllı parametre önerisi (3 aşamalı).
        
        Args:
            patient_info: Hasta bilgileri (species, age, weight)
            treatment_target: Tedavi hedefi
            session_history: Geçmiş seans verileri (optional)
            
        Returns:
            Önerilen parametreler ve metadata
        """
        # Aşama 1: Literatürde TAM eşleşme var mı?
        exact_match = self.find_exact_protocol(treatment_target)
        
        if exact_match:
            base_params = exact_match
            source = 'literature_exact'
        else:
            # Aşama 2: Benzer protokolden interpolasyon
            interpolated = self.interpolator.interpolate(treatment_target, top_n=3)
            
            if interpolated:
                base_params = interpolated
                source = 'interpolated'
            else:
                # Fallback: Genel wellness protokolü
                logger.warning(f"No match for '{treatment_target}', using default wellness protocol")
                base_params = self.clinical_db['wellness'].copy()
                source = 'default_wellness'
        
        # Aşama 3: Hasta profiline göre kişiselleştirme
        adapted_params = self.adaptor.adapt(base_params, patient_info)
        
        # Metadata ekle
        result = {
            'freq': adapted_params['freq'],
            'duty': round(adapted_params['duty'], 1),
            'duration': adapted_params['duration'],
            'intensity': adapted_params.get('intensity', 1.0),
            'evidence': adapted_params.get('evidence', 'unknown'),
            'source': source,
            'patient_profile': {
                'species': patient_info.get('species', 'unknown'),
                'age': patient_info.get('age', 0),
                'weight': patient_info.get('weight', 0),
            },
            'timestamp': datetime.now().isoformat()
        }
        
        # Log
        logger.info(
            f"Recommendation generated: {result['freq']}Hz, {result['duty']}%, {result['duration']}min "
            f"(source: {source}, evidence: {result['evidence']})"
        )
        
        return result
    
    def get_protocol_info(self, treatment_target: str) -> Dict:
        """
        Bir tedavi hedefi hakkında detaylı bilgi al.
        
        Returns:
            Protocol info including evidence level, similar protocols, etc.
        """
        exact = self.find_exact_protocol(treatment_target)
        
        if exact:
            return {
                'found': True,
                'type': 'exact',
                'params': exact,
                'similar_protocols': []
            }
        
        # Benzer protokolleri bul
        similar = self.interpolator.find_similar_protocols(treatment_target, min_similarity=0.1)
        
        return {
            'found': False,
            'type': 'none',
            'params': None,
            'similar_protocols': [
                {'name': name, 'similarity': sim, 'params': params}
                for name, params, sim in similar[:5]
            ]
        }


# ==================== CONVENIENCE FUNCTIONS ====================

def create_recommender(app_data_dir: Optional[Path] = None) -> HybridPEMFRecommender:
    """
    Factory function to create a recommender instance.
    """
    return HybridPEMFRecommender(app_data_dir)


def get_literature_recommendation(treatment_target: str, app_data_dir: Optional[Path] = None) -> Dict:
    """
    Return literature protocol using only session target.

    This function intentionally ignores patient-specific fields (species/age/weight)
    and does not apply interpolation/adaptation logic.

    Args:
        treatment_target: Session goal text from UI
        app_data_dir: Kept for API compatibility, not used

    Returns:
        Dict containing freq, duty, duration, evidence and source
    """
    recommender = create_recommender(app_data_dir)

    target_clean = clean_treatment_target(treatment_target)
    source = 'default_wellness'

    protocol = recommender.find_exact_protocol(treatment_target)
    if protocol is not None:
        source = 'literature_exact'
    else:
        # Fallback to default wellness when no direct/substring protocol exists
        protocol = recommender.clinical_db['wellness'].copy()

    return {
        'freq': int(protocol['freq']),
        'duty': float(protocol['duty']),
        'duration': int(protocol['duration']),
        'intensity': float(protocol.get('intensity', 1.0)),
        'evidence': protocol.get('evidence', 'unknown'),
        'source': source,
        'target': target_clean,
        'timestamp': datetime.now().isoformat()
    }


# ==================== TESTING ====================

if __name__ == '__main__':
    # Configure logging
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    
    # Test cases
    print("=" * 60)
    print("HYBRID PEMF RECOMMENDER - TEST CASES")
    print("=" * 60)
    
    recommender = create_recommender()
    
    # Test 1: Exact match
    print("\n1. EXACT MATCH TEST: Kronik Artrit")
    patient1 = {'species': 'dog', 'age': 8, 'weight': 25}
    rec1 = recommender.recommend_parameters(patient1, "Kronik Artrit")
    print(f"   Recommendation: {rec1['freq']}Hz, {rec1['duty']}%, {rec1['duration']}min")
    print(f"   Source: {rec1['source']}, Evidence: {rec1['evidence']}")
    
    # Test 2: Interpolation
    print("\n2. INTERPOLATION TEST: Kas Ağrısı (unknown)")
    patient2 = {'species': 'cat', 'age': 4, 'weight': 5}
    rec2 = recommender.recommend_parameters(patient2, "Kas Ağrısı")
    print(f"   Recommendation: {rec2['freq']}Hz, {rec2['duty']}%, {rec2['duration']}min")
    print(f"   Source: {rec2['source']}, Evidence: {rec2['evidence']}")
    
    # Test 3: Young horse
    print("\n3. SPECIES TEST: Young Horse - Kırık İyileşmesi")
    patient3 = {'species': 'horse', 'age': 1.5, 'weight': 180}
    rec3 = recommender.recommend_parameters(patient3, "Kırık İyileşmesi")
    print(f"   Recommendation: {rec3['freq']}Hz, {rec3['duty']}%, {rec3['duration']}min")
    print(f"   Source: {rec3['source']}, Evidence: {rec3['evidence']}")
    
    # Test 4: Protocol info
    print("\n4. PROTOCOL INFO TEST: Eklem Sorunu (unknown)")
    info = recommender.get_protocol_info("Eklem Sorunu")
    print(f"   Found: {info['found']}, Type: {info['type']}")
    print("   Similar protocols:")
    for sim in info['similar_protocols'][:3]:
        print(f"     - {sim['name']} (similarity: {sim['similarity']:.2f})")
    
    print("\n" + "=" * 60)
