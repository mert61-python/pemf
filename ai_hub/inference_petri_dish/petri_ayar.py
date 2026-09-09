# -*- coding: utf-8 -*-
# Author: mertaygn
"""Petri Kuyu Analizi — ARAYÜZDEN ayarlanabilir parametrelerin TEK KAYNAĞI.

SAHİP TALEBİ (2026-09-09): "3 parametre arayüzden ayarlanabilir olsun. Görüntünün çözünürlüğü
fazla, yoloya göre resize ekle." → netleştirme: "Altısı da ayarlanabilir olsun."

NEDEN AYRI MODÜL (ne router'da ne arayüzde): parametreyi kabul eden İKİ uç var —
`servers/ai_router.py::analyze_em_petri` (gömülü yol) ve `ai_service/app.py::infer_em_petri`
(GPU mikroservisi, `PEMF_AI_SERVICE_URL` tanımlıyken gömülü yol HİÇ çalışmaz). Sınırı yalnız
birine koymak diğerini korumasız bırakırdı; iki yere kopyalamak ise sürüklenirdi (bugün ölçülen
`scratch_yonu` hatası tam bu sınıftı: parametre zincirin bir halkasında sessizce düşüyordu).
`plausibility.py` ile aynı gerekçe: `docker/Dockerfile.ai` imaja YALNIZ `ai_hub/` + `ai_service/`
kopyalar, bu yüzden paylaşılan kural `utils/`e değil buraya ait.

⚠️ SINIRLAR SÜSLEME DEĞİL: arayüz doğrulaması atlanabilir (uç auth-muaf, `curl` ile doğrudan
çağrılabilir). `resize_max=1` bütün görüntüyü tek piksele indirir, `yolo_conf=0` on binlerce
sahte tespit üretip belleği doldurur. Aralığı UÇTA zorlamak tek gerçek koruma.
"""
from __future__ import annotations

from .plausibility import ESIK_VARSAYILAN

#: Ayarlanabilir sayısal parametre → (alt, üst) kapsayıcı sınır. Anahtarlar aynı zamanda
#: uçlardaki Form alan adları ve arayüzdeki alan adlarıdır (tek isim, üç katman).
SINIRLAR: dict[str, tuple[float, float]] = {
    "yolo_conf": (0.01, 0.95),
    "yolo_iou": (0.10, 0.95),
    "resize_max": (320.0, 8000.0),
    "plaus_circularity": (0.0, 1.0),
    "plaus_conf": (0.0, 1.0),
    "plaus_area_frac": (0.01, 1.0),
}

#: `plaus_*` form adı → `plausibility.ESIK_VARSAYILAN` anahtarı. İki isim ayrı bilinçli: telde
#: kısa/ön-ekli ad, ölçüm modülünde metriğin kendi adı.
_ESIK_ADI: dict[str, str] = {
    "plaus_circularity": "circularity_med",
    "plaus_conf": "conf_med",
    "plaus_area_frac": "max_area_frac",
}


class AyarHatasi(ValueError):
    """Aralık dışı/bozuk parametre. Uçlar bunu 422 + Türkçe metne çevirir."""


def varsayilanlar() -> dict[str, float]:
    """Arayüzün "sıfırla" için gösterdiği etkin varsayılanlar (boru hattı + makullik).

    ⚠️ Makullik varsayılanları BURADA TEKRAR YAZILMAZ, `plausibility.ESIK_VARSAYILAN`dan
    okunur: eşik orada değişirse arayüz de birlikte öğrenir.
    """
    d: dict[str, float] = {"yolo_conf": 0.25, "yolo_iou": 0.7, "resize_max": 0.0}
    for form_adi, esik_adi in _ESIK_ADI.items():
        d[form_adi] = float(ESIK_VARSAYILAN[esik_adi])
    return d


def _sayi(ad: str, deger) -> float:
    try:
        return float(deger)
    except (TypeError, ValueError):
        raise AyarHatasi(f"{ad} bir sayı olmalı (gelen: {deger!r}); alanı boş bırakırsanız varsayılan kullanılır") from None


def _sinirla(ad: str, deger) -> float | None:
    """None → None (varsayılan kullanılır). Aralık dışı → AyarHatasi (ne yapılacağını söyler)."""
    if deger is None or deger == "":
        return None
    d = _sayi(ad, deger)
    if ad == "resize_max" and d == 0:
        return None  # 0 = küçültme KAPALI (arayüzdeki "kapalı" seçeneği)
    alt, ust = SINIRLAR[ad]
    if not (alt <= d <= ust):
        raise AyarHatasi(
            f"{ad} değeri {alt:g} ile {ust:g} arasında olmalı (gelen: {d:g}); "
            f"bu aralığa çekin ya da alanı boşaltıp varsayılana dönün"
        )
    return d


def coz(
    *,
    yolo_conf=None,
    yolo_iou=None,
    resize_max=None,
    plaus_circularity=None,
    plaus_conf=None,
    plaus_area_frac=None,
    plaus_guard=None,
) -> dict:
    """Ham form değerlerini `PetriCvPipeline(**kwargs)` sözlüğüne çevirir.

    VERİLMEYEN PARAMETRE HİÇ KONULMAZ (None ile ezilmez): boru hattının kendi varsayılanı
    geçerli kalır, yani hiçbir parametre gönderilmezse davranış BİT-BİT bugünküyle aynıdır.
    Bu, "arayüz ayarı ekledik, sessizce hepsini sıfıra çektik" regresyonunu yapısal olarak
    imkânsız kılar — gate `test_bos_istek_bos_kwargs`.

    Raises:
        AyarHatasi: sayı değil ya da aralık dışı.
    """
    kw: dict = {}
    for ad, ham in (("yolo_conf", yolo_conf), ("yolo_iou", yolo_iou)):
        d = _sinirla(ad, ham)
        if d is not None:
            kw[ad] = d

    rs = _sinirla("resize_max", resize_max)
    if rs is not None:
        kw["resize_max"] = int(rs)

    esikler: dict[str, float] = {}
    for form_adi, esik_adi in _ESIK_ADI.items():
        d = _sinirla(form_adi, {"plaus_circularity": plaus_circularity,
                                "plaus_conf": plaus_conf,
                                "plaus_area_frac": plaus_area_frac}[form_adi])
        if d is not None:
            esikler[esik_adi] = d
    if esikler:
        kw["plaus_esikler"] = esikler

    if plaus_guard is not None:
        kw["plaus_guard"] = bool(plaus_guard)
    return kw
