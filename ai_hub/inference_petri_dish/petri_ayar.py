# -*- coding: utf-8 -*-
# Author: mertaygn
"""Petri Kuyu Analizi — ARAYÜZDEN ayarlanabilir parametrelerin TEK KAYNAĞI.

SAHİP TALEBİ (2026-09-09): "3 parametre arayüzden ayarlanabilir olsun. Görüntünün çözünürlüğü
fazla, yoloya göre resize ekle." → netleştirme: "Altısı da ayarlanabilir olsun."

NEDEN AYRI MODÜL (ne router'da ne arayüzde): parametreyi kabul eden İKİ uç var —
`apps/backend/servers/ai_router.py::analyze_em_petri` (gömülü yol) ve `ai_service/app.py::infer_em_petri`
(GPU mikroservisi, `PEMF_AI_SERVICE_URL` tanımlıyken gömülü yol HİÇ çalışmaz). Sınırı yalnız
birine koymak diğerini korumasız bırakırdı; iki yere kopyalamak ise sürüklenirdi (bugün ölçülen
`scratch_yonu` hatası tam bu sınıftı: parametre zincirin bir halkasında sessizce düşüyordu).
`plausibility.py` ile aynı gerekçe: `docker/Dockerfile.ai` imaja YALNIZ `ai_hub/` + `ai_service/`
kopyalar, bu yüzden paylaşılan kural `apps/backend/utils/`e değil buraya ait.

⚠️ SINIRLAR SÜSLEME DEĞİL: arayüz doğrulaması atlanabilir (uç auth-muaf, `curl` ile doğrudan
çağrılabilir). `resize_max=1` bütün görüntüyü tek piksele indirir, `yolo_conf=0` on binlerce
sahte tespit üretip belleği doldurur. Aralığı UÇTA zorlamak tek gerçek koruma.
"""
from __future__ import annotations

import re

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
    # T3 · Y191b: plaka kipinde ızgara hücresi skoru eşiği (0 = kapalı); varsayılan boru hattında (0,6).
    "kuyu_skor_esigi": (0.0, 1.0),
}

#: `plaus_*` form adı → `plausibility.ESIK_VARSAYILAN` anahtarı. İki isim ayrı bilinçli: telde
#: kısa/ön-ekli ad, ölçüm modülünde metriğin kendi adı.
_ESIK_ADI: dict[str, str] = {
    "plaus_circularity": "circularity_med",
    "plaus_conf": "conf_med",
    "plaus_area_frac": "max_area_frac",
}


#: AI-2 (hocanın petri v2'si): plaka tipi — 0 = tekil petri kapları (eski YOLO kipi), diğerleri SBS/ANSI plakaları.
PLAKA_TIPLERI: tuple[int, ...] = (0, 12, 24, 48, 96)
#: A1 kuyucuğunun görüntü köşesi (hocanın `plate_grid.A1_SHIFT`; "auto" = yatay sol-üst / dikey sağ-üst).
A1_KOSELERI: tuple[str, ...] = ("auto", "tl", "tr", "br", "bl")
_KUYU_RE = re.compile(r"^[A-H](?:[1-9]|1[0-2])$")


class AyarHatasi(ValueError):
    """Aralık dışı/bozuk parametre. Uçlar bunu 422 + Türkçe metne çevirir."""


def varsayilanlar() -> dict[str, float]:
    """Arayüzün "sıfırla" için gösterdiği etkin varsayılanlar (boru hattı + makullik).

    ⚠️ Makullik varsayılanları BURADA TEKRAR YAZILMAZ, `plausibility.ESIK_VARSAYILAN`dan
    okunur: eşik orada değişirse arayüz de birlikte öğrenir.
    """
    # T3 · Y191: YOLO güven varsayılanı boru hattının KENDİSİNDEN okunur (sahip kararı 0,6 orada; kopya sürüklenirdi). Geç içe
    # aktarım: petri_cv_v2 cv2 / numpy çeker, bu modül uçta ondan önce kullanılır.
    import inspect

    from ai_hub.inference_petri_dish.petri_cv_v2.pipeline import PetriCvPipeline

    imza = inspect.signature(PetriCvPipeline.__init__).parameters
    d: dict[str, float] = {
        "yolo_conf": float(imza["yolo_conf"].default),
        "yolo_iou": 0.7,
        "resize_max": 0.0,
        "kuyu_skor_esigi": float(imza["kuyu_skor_esigi"].default),  # T3 · Y191b
    }
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


def _kuyu_listesi(ad: str, ham) -> list[str] | None:
    """"A1, D6" → ["A1", "D6"]; boş → None (YAML'daki değer geçerli). Bozuk kuyucuk adı → AyarHatasi."""
    if ham is None or str(ham).strip() == "":
        return None
    out = []
    for parca in str(ham).replace(";", ",").split(","):
        k = parca.strip().upper()
        if not k:
            continue
        if not _KUYU_RE.match(k):
            raise AyarHatasi(
                f"{ad} içinde geçersiz kuyucuk adı {parca.strip()!r}; A1–H12 biçiminde virgülle ayırın (ör. A1, D6)"
            )
        if k not in out:
            out.append(k)
    return out or None


def coz(
    *,
    yolo_conf=None,
    yolo_iou=None,
    resize_max=None,
    plaus_circularity=None,
    plaus_conf=None,
    plaus_area_frac=None,
    plaus_guard=None,
    plate_type=None,
    control_healthy=None,
    control_cancer=None,
    a1_corner=None,
    kuyu_skor_esigi=None,
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

    ks = _sinirla("kuyu_skor_esigi", kuyu_skor_esigi)  # T3 · Y191b (0 = kapalı geçerli değer)
    if ks is not None:
        kw["kuyu_skor_esigi"] = ks

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

    # ── AI-2: hocanın petri v2 kip / laboratuvar protokolü parametreleri (verilmezse YAML `multiwell:` geçerli) ──
    if plate_type is not None and str(plate_type).strip() != "":
        try:
            pt = int(float(plate_type))
        except (TypeError, ValueError):
            raise AyarHatasi(f"plate_type bir sayı olmalı (gelen: {plate_type!r})") from None
        if pt not in PLAKA_TIPLERI:
            raise AyarHatasi(
                f"plate_type {pt} desteklenmiyor; {', '.join(str(t) for t in PLAKA_TIPLERI)} olmalı "
                "(0 = tekil petri kapları)"
            )
        kw["plate_type"] = pt
    for ad, ham in (("control_healthy", control_healthy), ("control_cancer", control_cancer)):
        liste = _kuyu_listesi(ad, ham)
        if liste is not None:
            kw[ad] = liste
    if a1_corner is not None and str(a1_corner).strip() != "":
        ak = str(a1_corner).strip().lower()
        if ak not in A1_KOSELERI:
            raise AyarHatasi(f"a1_corner {a1_corner!r} geçersiz; {', '.join(A1_KOSELERI)} olmalı")
        kw["a1_corner"] = ak
    return kw
