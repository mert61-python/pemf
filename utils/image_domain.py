# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Görüntü ALAN (modalite) denetimi — yanlış türde görüntüye GÜVENLE teşhis üretilmesini engeller.

NEDEN (2026-08-06, sahip bildirimi): Böbrek Patoloji modülüne bir **CT kesiti** yüklendiğinde model
hiç itiraz etmeden **"Grade 4 (en ileri) · güven %100"** döndürdü. Sınıflandırıcılar softmax üretir:
girdi eğitim dağılımının TAMAMEN dışında olsa bile olasılıklar 1'e toplanır ve model en yakın
sınıfa %100 "güvenir". Kullanıcı için bu, sessiz ve ikna edici bir YANLIŞ TEŞHİStir — tıbbi bir
cihazda kabul edilemez.

YAKLAŞIM: modelin kendi güvenine GÜVENME; girdinin modalitesini görüntünün fiziksel özelliklerinden
bağımsız olarak ölç ve modülün beklediğiyle karşılaştır. Ucuz, deterministik, model-bağımsız:

  * `grayscale` — CT / röntgen / ultrason: kanallar birbirinin AYNI (akromatik).
  * `stained`   — H&E boyalı patoloji: macenta/mor/pembe baskın, yüksek doygunluk.
  * `color`     — doğal renkli fotoğraf (kedi, petri kuyusu, fantom, laboratuvar).

KASITLI OLARAK MUHAFAZAKÂR: yalnız KESİN uyuşmazlıkta reddeder (ör. %95+ akromatik bir görüntü
gerçek bir H&E preparatı OLAMAZ). Kararsız kalırsa GEÇİRİR — meşru bir araştırma görüntüsünü
yanlışlıkla bloklamak da bir başarısızlıktır.

SINIRI (dürüstlük): modalite denetimi AYNI modalitedeki iki modülü ayıramaz — petri kuyusu ile
fantom fotoğrafı ikisi de `color`'dır (ölçüldü: petri achromatic=0.391, fantom 0.179). Onun için
modül-özel geometri denetimi gerekir → 2026-08-06'da eklendi:
`ai_hub/inference_petri_dish/plausibility.py` (petri yönü; fantom yönü zaten kapalıydı).
İKİ KATMAN BİRBİRİNİN YERİNE GEÇMEZ: CT kesitini modalite tutar, fantom fotoğrafını geometri.

KAPATMA: `PEMF_AI_DOMAIN_GUARD=0` → denetim tamamen devre dışı (araştırma kaçış kapağı).
"""

from __future__ import annotations

import logging
import os

import cv2
import numpy as np

logger = logging.getLogger(__name__)

GRAYSCALE = "grayscale"
STAINED = "stained"
COLOR = "color"
# DENETİM 2026-08-06: bozuk/boş girdide eskiden COLOR dönülüyordu. histopath {STAINED}'e
# daraltılınca bu, okunamayan bir görüntüde kullanıcıya ALAKASIZ bir "yanlış görüntü türü"
# mesajı gösterdi. Modalite BELİRLENEMİYORSA denetim yapılmamalı (fail-open): gerçekten
# bozuk görüntüyü zaten decode katmanı kendi net mesajıyla reddediyor.
UNKNOWN = "unknown"

_TR = {
    GRAYSCALE: "gri tonlamalı tıbbi görüntü (CT / röntgen / ultrason)",
    STAINED: "boyalı patoloji preparatı (H&E)",
    COLOR: "renkli fotoğraf",
}

# Modül etiketi (ai_router `_decode_image(label=...)`) → kabul edilen modaliteler.
# Etiketi burada OLMAYAN uç denetlenmez (yeni uç eklemek geriye-uyumlu kalsın).
EXPECTED: dict[str, set[str]] = {
    "kidney_ct": {GRAYSCALE},
    # DENETİM 2026-08-06 (SIZINTI — ilk sürümdeki KENDİ hatam düzeltildi): burası `{STAINED, COLOR}`
    # idi; gerekçem "bazı tarayıcılar düşük doygunluk verir" varsayımıydı. ÖLÇÜM bunu çürüttü:
    #   gerçek patoloji  08a/08b/08c → stain_ratio 0.748 / 0.352 / 0.882
    #   patoloji OLMAYAN kedi/segmentasyon/fantom/petri → 0.000 / 0.0002 / 0.0002 / 0.041
    # Yani COLOR'ı kabul etmek, kedi fotoğrafına "Grade 4 · %100" verilmesini SERBEST bırakıyordu —
    # sahibin bildirdiği CT vakasıyla AYNI sınıf hata, sadece başka bir girdiyle. {STAINED}'e
    # daraltıldı; aradaki 8 kat boşluk güvenli ayrım sağlıyor (bkz. _STAIN_RATIO marjı).
    "histopath": {STAINED},
    "reticulocytes": {STAINED, COLOR},
    "landmark": {COLOR},
    "segmentation": {COLOR},
    "cat_organ": {COLOR},
    "em_fantom": {COLOR},
    # DENETİM 2026-08-06 (YANLIŞ-POZİTİF): burası yalnız {COLOR} idi ve GERÇEK bir petri girdisini
    # reddediyordu — `06b_PetriKuyu_aruco.jpg` achromatic_ratio=0.9937 (sat_mean=0.0048) ile
    # `grayscale` algılanıyor (renksiz kuyucuk + gri kabin zemini). Kullanıcı için sonuç
    # "petri modülü petri fotoğrafını kabul etmiyor" olurdu.
    # ⚠️ GEVŞETMENİN BEDELİ VAR — DOĞRULAMADA ÖLÇÜLDÜ: burası GRAYSCALE'e açılınca CT kesitlerini
    # bu uçta tutan TEK katman kalkar ve geometri katmanının O ANKİ saf 2-of-3 oyu onları
    # TUTMADI (07b/07c böbrek CT → HTTP 200, success=True, n_wells=1). Kapatan şey geometri
    # katmanına eklenen ALAN VETO'sudur (plausibility.py `area_ok`). BU İKİSİ BİRLİKTE ANLAMLI:
    # veto sökülürse burası da {COLOR}'a geri alınmalı, yoksa CT sessizce "kuyucuk" üretir.
    "em_petri": {COLOR, GRAYSCALE},
    # "thermal" KASITLI DIŞARIDA: IR kamera hem gri hem renk-haritalı çıktı verebilir.
    # "ai_pro_frame" KASITLI DIŞARIDA: canlı kamera karesi, kullanıcı yüklemesi değil.
}

# Eşikler — muhafazakâr (yanlış-pozitif reddi minimize et).
_ACHROMATIC_CHROMA = 12  # 0-255; bu farkın altındaki piksel "renksiz" sayılır
_GRAYSCALE_RATIO = 0.95  # görüntünün %95'i renksizse => gerçekten gri tonlama
_STAIN_HUE_LO, _STAIN_HUE_HI = 125, 178  # OpenCV H (0-179): mor→macenta→pembe
_STAIN_MIN_SAT = 0.18
# DENETİM 2026-08-06: eşik 0.30 idi. Ölçülen dağılım:
#   patoloji (STAINED olmalı)      : 0.352 (en düşük, 08b) … 0.882
#   patoloji-dışı (COLOR olmalı)   : 0.000 … 0.041 (en yüksek, petri)
# 0.30 eşiği en düşük gerçek patolojiye yalnız %17 pay bırakıyordu → solgun boyanmış bir preparat
# yanlışlıkla REDDEDİLEBİLİRDİ. 0.15, iki dağılımın TAM ORTASINA oturur: en yüksek yanlış-adayın
# 3.6 katı üstünde, en düşük gerçek patolojinin 2.3 katı altında → her İKİ yönde de marj.
_STAIN_RATIO = 0.15


class DomainMismatch(Exception):
    """Görüntü modalitesi modülün beklediğiyle uyuşmuyor."""

    def __init__(self, label: str, detected: str, expected: set[str], metrics: dict):
        self.label = label
        self.detected = detected
        self.expected = expected
        self.metrics = metrics
        super().__init__(self.user_message())

    def user_message(self) -> str:
        bekl = " veya ".join(sorted(_TR.get(e, e) for e in self.expected))
        return (
            f"Bu modül {bekl} bekliyor; yüklenen görüntü {_TR.get(self.detected, self.detected)} "
            f"gibi görünüyor. Yanlış görüntüyle üretilen sonuç yanıltıcı olur — lütfen doğru "
            f"türde bir görüntü yükleyin."
        )


def guard_enabled() -> bool:
    return os.getenv("PEMF_AI_DOMAIN_GUARD", "1") != "0"


def analyze(img: np.ndarray) -> tuple[str, dict]:
    """BGR görüntüden modalite + ölçümleri döndür. Saf fonksiyon, yan etkisiz."""
    if img is None or getattr(img, "size", 0) == 0:
        return UNKNOWN, {}
    # Büyük görüntüde tam çözünürlükte çalışmak gereksiz — istatistik için küçült (hız + gürültü azalır).
    h, w = img.shape[:2]
    if max(h, w) > 512:
        k = 512.0 / max(h, w)
        img = cv2.resize(img, (max(1, int(w * k)), max(1, int(h * k))), interpolation=cv2.INTER_AREA)
    if img.ndim == 2:
        return GRAYSCALE, {"achromatic_ratio": 1.0, "stain_ratio": 0.0}

    b, g, r = (img[:, :, i].astype(np.int16) for i in range(3))
    chroma = np.maximum(np.maximum(np.abs(r - g), np.abs(g - b)), np.abs(b - r))
    achromatic_ratio = float(np.mean(chroma <= _ACHROMATIC_CHROMA))

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    hue = hsv[:, :, 0].astype(np.int16)
    sat = hsv[:, :, 1].astype(np.float32) / 255.0
    stain_mask = (hue >= _STAIN_HUE_LO) & (hue <= _STAIN_HUE_HI) & (sat >= _STAIN_MIN_SAT)
    # Boyalı doku oranı RENKLİ pikseller içinde anlamlı (siyah arka plan payı şişirmesin).
    colored = float(np.mean(chroma > _ACHROMATIC_CHROMA)) or 1e-6
    stain_ratio = float(np.mean(stain_mask))

    metrics = {
        "achromatic_ratio": round(achromatic_ratio, 4),
        "stain_ratio": round(stain_ratio, 4),
        "colored_ratio": round(colored, 4),
        "sat_mean": round(float(sat.mean()), 4),
    }

    if achromatic_ratio >= _GRAYSCALE_RATIO:
        return GRAYSCALE, metrics
    if stain_ratio >= _STAIN_RATIO:
        return STAINED, metrics
    return COLOR, metrics


def check(img: np.ndarray, label: str) -> None:
    """`label` modülü için görüntü modalitesini denetle; uyuşmazsa DomainMismatch fırlat."""
    if not guard_enabled():
        return
    expected = EXPECTED.get(label)
    if not expected:
        return
    try:
        detected, metrics = analyze(img)
    except Exception:
        logger.debug("modalite analizi başarısız (denetim atlandı)", exc_info=True)
        return
    if detected == UNKNOWN or detected in expected:
        return  # UNKNOWN → modalite belirlenemedi, denetim yapma (fail-open, yukarıya bkz.)
    logger.warning(
        "ALAN UYUŞMAZLIĞI [%s]: beklenen=%s algılanan=%s ölçüm=%s", label, sorted(expected), detected, metrics
    )
    raise DomainMismatch(label, detected, expected, metrics)
