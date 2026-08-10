# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Petri kuyucuk plakası MAKULLİK denetimi — yanlış modülün fotoğrafına SESSİZCE sonuç üretmeyi engeller.

SAHİP BİLDİRİMİ (2026-08-06) — ÖLÇÜLDÜ ve DOĞRULANDI: `05_FantomTumor.jpeg` (fantom fotoğrafı)
Petri Kuyu ucuna verildiğinde boru hattı hiç itiraz etmeden `success=True, n_wells=2, n_cancer=1`
döndürüyordu; iki SAHTE "kuyucuk" için PetriPredictor çalışıp E_cancer/D/P üretiyordu. Kullanıcı
için bu, `utils/image_domain.py` docstring'indeki CT→patoloji vakasının aynısı: sessiz ve ikna
edici bir YANLIŞ sonuç. Ters yön zaten güvenli (fantom boru hattı petri/kedi fotoğrafını
`phantom_not_detected` ile reddediyor) → karışıklık TEK YÖNLÜ, yalnız bu yön açıktı.

NEDEN MODALİTE DENETİMİ YETMİYOR: ölçüldü — petri achromatic=0.391, fantom achromatic=0.179 →
İKİSİ DE `color`. `utils/image_domain.py` aynı modalitedeki iki modülü ayıramaz (kendi
docstring'i bunu zaten itiraf ediyor). Ayırmak için MODÜL-ÖZEL geometri gerekir; bu dosya odur.
İKİ KATMAN BİRBİRİNİN YERİNE GEÇMEZ: bir CT kesiti bu denetimden geçebilir (07a_BobrekCT_tas.jpg
dairesellik medyanı 0.782 ölçüldü!) ama modalite denetimi onu tutar.

NEDEN `utils/` DEĞİL DE BURADA: `docker/Dockerfile.ai` imaja YALNIZ `ai_hub/` + `ai_service/`
kopyalar. `PEMF_AI_SERVICE_URL` tanımlıyken em_petri isteği `servers/ai_client.py::delegate_infer`
ile GPU mikroservisine gider ve `servers/ai_router.py` HİÇ çalışmaz. Denetim `utils/`e ya da
router'a konsaydı mikroservis dağıtımında KORUMA OLMAZDI (bypass). Boru hattının yanında duruyor:
her iki yol da aynı `PetriCvPipeline.process_image`'i çağırır.

ÖLÇÜLEN AYIRT-EDİCİLİK (petri boru hattı, 8 varyant × 5 girdi; PEMF_AI_DOMAIN_GUARD=0 ile):
    sinyal              GERÇEK PETRI (06/06b)     SAHTE (fantom 05 / kedi 02 / kedi 09)
    dairesellik medyanı 0.61–0.86                 0.29–0.46
    YOLO conf medyanı   0.68–0.95                 0.50–0.81
    en büyük tespit /   0.064–0.166               0.262–0.545   ← 8 varyantın hepsinde ÇAKIŞMASIZ
      kare alanı                                                 (tek başına en sağlam sinyal)
Maliyet ihmal edilebilir: contourArea+arcLength toplam 0.01–0.10 ms; boru hattı toplamı ~270 ms.

KASITLI OLARAK MUHAFAZAKÂR (image_domain.py ile aynı felsefe): dairesellik ve güven sinyalleri
TEK BAŞINA REDDETTİRMEZ — 3 sinyalden EN AZ 2'si geçerse görüntü kabul edilir. Meşru bir araştırma
görüntüsünü bloklamak da bir başarısızlıktır. Ölçülen doğrulama: 16 gerçek-petri varyantının 15'i
geçer (yalnız sentetik 30° döndürme düşer — orada YOLO'nun KENDİSİ de bozuluyor), 10 sahte girdinin
10'u reddedilir.

TEK İSTİSNA — ALAN ORANI VETO'DUR (DENETİM 2026-08-06, ÖLÇÜLEN REGRESYON):
`utils/image_domain.py` aynı gün `em_petri`e GRAYSCALE'i de açtı (gerçek kabin fotoğrafı
`06b_PetriKuyu_aruco.jpg` achromatic=0.9937 ile gri algılanıp reddediliyordu — canlı yanlış-pozitif).
O gevşetme, CT kesitlerini tutan TEK katmanı bu uçtan kaldırdı ve saf 2-of-3 oy onları TUTAMADI:
    07b_BobrekCT_kist.jpg   circ 0.7923 · conf 0.9015 · alan 0.3505 → 2 oy → HTTP 200 "n_wells=1"
    07c_BobrekCT_normal.jpg circ 0.7834 · conf 0.8730 · alan 0.3141 → 2 oy → HTTP 200 "n_wells=1"
Yani böbrek CT kesiti için PetriPredictor çalışıp "kuyucuk" raporlanıyordu — düzeltmeye
çalıştığımız SESSİZ YANLIŞ SONUCUN ta kendisi. Böbrek/organ konturu YUVARLAKTIR (circ ~0.79) ve
YOLO ondan EMİNDİR (conf ~0.90); iki sinyal de bu girdide işe yaramıyor. Ayıran TEK sinyal alan
oranı: gerçek petri (10 varyant, kırpmasız) 0.066–0.166, CT 0.314–0.359 — bu yüzden alan sinyali
oy DEĞİL VETO'dur: kareyi %25'ten fazla kaplayan tek bir tespit, diğer sinyaller ne olursa olsun
petri kuyucuğu değildir (fiziksel gerekçe: kuyucuk plakanın küçük bir parçasıdır).
VETO'NUN BEDELİ ÖLÇÜLDÜ ve KABUL EDİLDİ: ağır kırpılmış (≤%70 kadraj) meşru petri fotoğrafları da
düşer (06b kırp0.70 alan 0.3032; 06 kırp0.50 alan 0.2606). Temiz bir eşik YOK — kırpılmış meşru
petri ile CT alan bandı ÇAKIŞIYOR. Tıbbi cihazda çakışma bölgesinin doğru tarafı REDDETMEKTİR:
kullanıcı ölçümlü mesajı görür ("tam kadraj deneyin") ve kaçış kapağı vardır; kabul edilseydi
yanlış sonucu HİÇ görmezdi. Tam kadrajlı gerçek girdilerin hepsi (06, 06b + 8 varyant) geçer.

KARAR RESİM DÜZEYİNDEDİR, kuyu listesi ASLA budanmaz: ölçüldü, meşru kuyucukların BİREYSEL conf'u
20° döndürmede 0.502'ye, -40 parlaklıkta 0.421'e düşüyor. Tek tek kuyu elemek gerçek kuyuları
sessizce yutar (8 kuyunun 6'sı raporlanır, kullanıcı FARK ETMEZ) — bu, düzeltmeye çalıştığımız
hatanın daha sinsi bir biçimi olurdu.

KAPATMA: `PEMF_AI_PLAUSIBILITY_GUARD=0` → denetim devre dışı (araştırma kaçış kapağı).
"""
from __future__ import annotations

import logging
import math
import os
from typing import Any, Sequence

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# `PipelineResult.error` değeri. servers/ai_router.py bunu 422'ye çevirir; mikroservis yolunda
# JSON `error` alanıyla telden geçer → SÖZLEŞME DİZESİDİR, değiştirilirse ai_router da değişmeli
# (tests/test_petri_plausibility.py bu eşleşmeyi kilitler).
PETRI_REJECT = "not_a_petri_plate"

# Eşikler — ölçülen dağılımların ORTASINDAN değil, GERÇEK PETRİ tarafının en kötü ucundan biraz
# aşağıdan geçirildi (yanlış-pozitif = meşru görüntüyü bloklamak, en pahalı hata).
_MIN_CIRCULARITY = 0.55     # gerçek petri en düşük 0.61 (rot20) / sahte en yüksek 0.46
_MIN_CONF = 0.85            # gerçek petri 0.895+ (orijinal) / sahte en yüksek 0.81
_MAX_AREA_FRAC = 0.25       # gerçek petri en yüksek 0.166 / sahte en düşük 0.262 — VETO (bkz. docstring)
_MIN_VOTES = 2              # dairesellik + güven + alan: en az 2'si → KABUL (alan ayrıca VETO)


def guard_enabled() -> bool:
    """Araştırma kaçış kapağı — `utils/image_domain.py::guard_enabled` ile aynı desen."""
    return os.getenv("PEMF_AI_PLAUSIBILITY_GUARD", "1") != "0"


def _olc(contour: np.ndarray):
    """(dairesellik, alan_px) — ÖLÇÜLEMEDİYSE None.

    "Ölçülemedi" ile "ölçtüm, 0 çıktı" AYRI tutulur (0.0 döndürüp geçmek tehlikeliydi): girdi
    tipi bir gün değişirse (kontur formatı, yeni detector) her ölçüm sessizce 0'a düşer ve
    denetim MEŞRU görüntülerin HEPSİNİ reddetmeye başlardı. Ayrım sayesinde o durumda karar
    verilmez, geçilir (bkz. `is_plausible`).
    """
    try:
        area = float(cv2.contourArea(contour))
        peri = float(cv2.arcLength(contour, True))
    except Exception:
        return None
    if peri <= 0.0 or area <= 0.0:
        return None
    # Kuyucuk maskesi diskretizasyon yüzünden 1.0'ı birkaç binde aşabilir → 1.0'a kırpılır
    # (metrik okunabilir kalsın; karar eşiği alt sınırda olduğu için etkisi yok).
    return min(1.0, 4.0 * math.pi * area / (peri * peri)), area


def circularity(contour: np.ndarray) -> float:
    """4πA/P² — mükemmel daire 1.0, uzun/girintili şekil 0'a yaklaşır. Saf, yan etkisiz.
    Ölçülemeyen girdide 0.0 (çökmez)."""
    r = _olc(contour)
    return r[0] if r else 0.0


def analyze(contours: Sequence[np.ndarray], confs: Sequence[float],
            image_area: float) -> dict[str, Any]:
    """Tespitlerden RESİM DÜZEYİ makullik ölçümlerini çıkar. Saf fonksiyon, model-bağımsız.

    Girdi kasıtlı olarak ilkel (kontur listesi + conf listesi + görüntü alanı): YOLO'ya,
    PetriDetection'a ya da herhangi bir modele bağlanmaz → birim testi modeli YÜKLEMEDEN
    sentetik konturla kuralı kilitleyebilir.
    """
    circs: list[float] = []
    areas: list[float] = []
    olculemeyen = 0
    for c in contours or []:
        r = _olc(c)
        if r is None:
            olculemeyen += 1
            continue
        circs.append(r[0])
        areas.append(r[1])
    confs_f: list[float] = []
    for v in confs or []:
        try:
            confs_f.append(float(v))
        except Exception:
            pass

    area_img = float(image_area) if image_area and float(image_area) > 0 else 0.0
    circ_med = float(np.median(circs)) if circs else 0.0
    conf_med = float(np.median(confs_f)) if confs_f else 0.0
    max_area_frac = (max(areas) / area_img) if (areas and area_img > 0) else 0.0

    area_ok = max_area_frac <= _MAX_AREA_FRAC
    votes = (int(circ_med >= _MIN_CIRCULARITY)
             + int(conf_med >= _MIN_CONF)
             + int(area_ok))
    return {
        "n_detections": len(circs),
        "n_unmeasurable": olculemeyen,
        # VETO SİNYALİ: False ise oy sayısına BAKILMADAN reddedilir (bkz. modül docstring'i —
        # böbrek CT kesiti dairesellik+güven oylarını KAZANIYOR, ayıran tek şey alan oranı).
        "area_ok": bool(area_ok),
        # ÜÇ sinyalin de gerçekten ÖLÇÜLEBİLDİĞİ hal. False ise karar verilmez (fail-open):
        # ölçemediğimiz bir görüntüyü "petri değil" saymak, düzeltmeye çalıştığımız hatanın
        # aynadaki eşi olurdu — meşru analizi sessizce bloklamak.
        "measurable": bool(circs) and bool(confs_f) and area_img > 0,
        "circularity_med": round(circ_med, 4),
        "conf_med": round(conf_med, 4),
        "max_area_frac": round(max_area_frac, 4),
        "votes": votes,
        "votes_required": _MIN_VOTES,
        "thresholds": {"circularity_med": _MIN_CIRCULARITY,
                       "conf_med": _MIN_CONF,
                       "max_area_frac": _MAX_AREA_FRAC},
    }


def is_plausible(metrics: dict) -> bool:
    """Alan VETO'su geçildiyse ve 2-of-3 oy tamamsa görüntü petri plakası (kararsızsa GEÇİR)."""
    try:
        if not metrics.get("measurable", True):
            return True      # ölçemedik → KARAR VERME (fail-open)
        # Alan oranı VETO: tek bir tespit kareyi %25'ten fazla kaplıyorsa diğer sinyaller
        # ne derse desin petri değil (ölçüldü: CT kesiti circ+conf oylarını kazanıyor).
        # Anahtar yoksa VETO UYGULANMAZ (elle kurulmuş/eski metrik sözlüğünde fail-open).
        if not metrics.get("area_ok", True):
            return False
        return int(metrics.get("votes", 0)) >= _MIN_VOTES
    except Exception:
        return True      # ölçüm bozuksa meşru analizi ENGELLEME (fail-open)


def user_message(metrics: dict | None = None) -> str:
    """Kullanıcıya NE ölçüldüğünü, NE beklendiğini ve NE yapması gerektiğini söyleyen Türkçe metin.

    `utils/image_domain.py::DomainMismatch.user_message` tonuyla aynı: suçlayıcı değil, YÖNLENDİRİCİ.
    """
    m = metrics or {}
    olcum = ""
    if m:
        try:
            olcum = (" (ölçülen: dairesellik {c:.2f} — beklenen ≥{mc:.2f}; tespit güveni {k:.2f} — "
                     "beklenen ≥{mk:.2f}; en büyük tespit karenin %{a:.0f}'ini kaplıyor — beklenen "
                     "≤%{ma:.0f})").format(
                c=float(m.get("circularity_med", 0.0)), mc=_MIN_CIRCULARITY,
                k=float(m.get("conf_med", 0.0)), mk=_MIN_CONF,
                a=100.0 * float(m.get("max_area_frac", 0.0)), ma=100.0 * _MAX_AREA_FRAC)
        except Exception:
            olcum = ""
    return ("Bu modül petri kuyucuğu plakası fotoğrafı bekliyor; yüklenen görüntüde petri kuyucuğu "
            "geometrisi bulunamadı{olcum}. Fantom fotoğrafını 'Fantom Tümör' modülüne, hayvan "
            "fotoğrafını ilgili kedi modülüne yükleyin — yanlış modülde üretilen sonuç yanıltıcıdır. "
            "Görüntü gerçekten bir petri plakasıysa kuyucukları tepeden ve tam kadrajda gösteren bir "
            "fotoğraf deneyin (araştırma için denetim PEMF_AI_PLAUSIBILITY_GUARD=0 ile kapatılabilir)."
            ).format(olcum=olcum)


def evaluate(contours: Sequence[np.ndarray], confs: Sequence[float],
             image_area: float) -> tuple[bool, dict[str, Any]]:
    """Boru hattının çağırdığı tek giriş noktası → (kabul_edildi_mi, ölçümler).

    Denetim ÇÖKERSE meşru analizi ASLA engellemez (fail-open): tıbbi bir cihazda bir ölçüm
    hatasının çalışan bir iş akışını kilitlemesi, korumanın sağladığından fazla zarar verir.
    """
    try:
        metrics = analyze(contours, confs, image_area)
    except Exception:
        logger.debug("petri makullik ölçümü başarısız (denetim atlandı)", exc_info=True)
        return True, {}
    if not guard_enabled():
        metrics["guard"] = "off"
        return True, metrics
    ok = is_plausible(metrics)
    if not ok:
        logger.warning("PETRI MAKULLİK REDDİ: ölçüm=%s", metrics)
        metrics["message"] = user_message(metrics)
    return ok, metrics
