# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""CANLI E-ALANI — tedavi sürerken elektrik alanını gerçek zamanlı türetir (2026-08-06, hoca isteği).

NEDEN BU TASARIM (uydurma katsayı YOK):
`E_healthy` / `E_cancer` bir fizik formülüyle değil, eğitilmiş bir ONNX **vekil (surrogate)**
modeliyle üretilir (`ai_hub/inference_em_fantom/inference_em_fantom.py::predict`). Model:

    x, y, z (kabin mm) · organ_id · achieved_B (Tesla) · duty_sum  →  D1-7, faz, E_healthy, E_cancer

Bu girdilerden **konum ve organ seans boyunca DEĞİŞMEZ** (hasta/fantom yerinde durur); değişen
yalnız `achieved_B` ve `duty_sum`'dır ve ikisi de canlı telemetride ZATEN vardır. Dolayısıyla
canlı E'yi AYNI modeli canlı B/duty ile çağırarak elde ederiz.

Bunun alternatifi (Faraday'dan analitik bir E ≈ (r/2)·dB/dt bağıntısı uydurmak) İKİ nedenle
reddedildi: (1) kalibrasyonsuz bir katsayı gerektirir — sayı "gerçek zamanlı" görünür ama
doğruluğu bilinmez; (2) AI panelindeki E ile bar'daki E FARKLI yollardan gelir, birbirini
tutmaz ve operatör hangisine güveneceğini bilemez. Aynı modeli kullanmak bu ikisini de çözer.

ÖLÇEKLER (üretim varsayılanlarıyla doğrulandı — `ai_router._AI_ACHIEVED_B/_AI_DUTY_SUM`):
  * ``achieved_B`` **Tesla** (varsayılan 0.001 T = 1 mT). Telemetri mT verir → /1000.
  * ``duty_sum``   boyutsuz duty TOPLAMI (varsayılan 1.5 ≡ 5 bobin × %30). Telemetri yüzde
    verir → Σ(dutyCycle/100). 5×30/100 = 1.5 ile birebir tutar.

MALİYET: model küçük (23 çıktı) ve çağrı ~ms. Yine de istek yolunda ÇALIŞTIRILMAZ — ayrı bir
düşük-frekanslı döngü hesaplayıp sonucu önbelleğe yazar, snapshot yalnız önbelleği okur.
Böylece dashboard-snapshot / WS gecikmesi ARTMAZ.
"""

from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)

# Analizden gelen SABİT bağlam (konum + organ). em_fantom/em_petri analizi çalışınca set edilir.
_ctx_lock = threading.Lock()
_ctx: dict | None = None

# Son hesaplanan canlı değer (snapshot bunu okur — ONNX istek yolunda çalışmaz).
_live_lock = threading.Lock()
_live: dict | None = None

# 2 Hz: göz için akıcı, CPU için önemsiz. Daha hızlısı bar'ı okunamaz yapar.
TICK_S = 0.5


def set_context(regions: list[dict], organ_id: int | None = None) -> None:
    """Analiz sonucundan konum bağlamını sakla. `regions`: her biri en az
    ``centroid_cabin_mm`` (x,y,z) taşıyan tümör bölgeleri. Boş liste → bağlamı TEMİZLE."""
    global _ctx
    if not regions:
        with _ctx_lock:
            _ctx = None
        _set_live(None)
        return
    r0 = regions[0] or {}
    c = r0.get("centroid_cabin_mm") or r0.get("centroid") or []
    if len(c) < 3:
        logger.debug("E-alanı bağlamı kurulamadı: centroid_cabin_mm yok (%s)", sorted(r0)[:6])
        return
    with _ctx_lock:
        _ctx = {
            "x": float(c[0]),
            "y": float(c[1]),
            "z": float(c[2]),
            "organ_id": int(organ_id if organ_id is not None else (r0.get("organ_id") or 1)),
            "set_at": time.time(),
        }
    logger.info(
        "E-alanı canlı bağlamı kuruldu: x=%.1f y=%.1f z=%.1f organ=%s",
        _ctx["x"],
        _ctx["y"],
        _ctx["z"],
        _ctx["organ_id"],
    )


def get_context() -> dict | None:
    with _ctx_lock:
        return dict(_ctx) if _ctx else None


def telemetry_inputs(coils: list[dict]) -> tuple[float, float, int]:
    """Canlı bobin listesinden (``achieved_B`` Tesla, ``duty_sum``, çalışan bobin sayısı).

    YALNIZ ÇALIŞAN bobinler sayılır: duran bobin alan üretmez, ortalamaya katılırsa
    B'yi yapay olarak düşürür. Çalışan yoksa (0.0, 0.0, 0) → çağıran E'yi sıfırlar.
    """
    run = [c for c in (coils or []) if c.get("running")]
    if not run:
        return 0.0, 0.0, 0
    b_mt = sum(float(c.get("magneticMt") or 0.0) for c in run) / len(run)
    duty_sum = sum(float(c.get("dutyCycle") or 0.0) for c in run) / 100.0
    return b_mt / 1000.0, duty_sum, len(run)


def compute(coils: list[dict]) -> dict | None:
    """Canlı bobin durumundan E değerlerini üret. Bağlam yoksa/bobin çalışmıyorsa None."""
    ctx = get_context()
    if not ctx:
        return None
    achieved_b, duty_sum, n = telemetry_inputs(coils)
    if n == 0:
        return {
            "healthy": 0.0,
            "cancer": 0.0,
            "avg": 0.0,
            "activeCoils": 0,
            "achievedB_T": 0.0,
            "dutySum": 0.0,
            "ts": time.time(),
        }
    try:
        pred = _predictor()
        if pred is None:
            return None
        out = pred.predict(ctx["x"], ctx["y"], ctx["z"], ctx["organ_id"], achieved_b, duty_sum)
    except Exception:
        logger.debug("canlı E hesabı başarısız", exc_info=True)
        return None
    return {
        "healthy": float(out.get("result_E_healthy") or 0.0),
        "cancer": float(out.get("result_E_cancer") or 0.0),
        "avg": float(out.get("result_E_avg") or 0.0),
        "activeCoils": n,
        "achievedB_T": achieved_b,
        "dutySum": duty_sum,
        "ts": time.time(),
    }


_pred_lock = threading.Lock()
_pred = None


def _predictor():
    """Modeli BİR KEZ yükle (2 Hz döngüde her tikte yüklemek diski/CPU'yu boşa yorar)."""
    global _pred
    with _pred_lock:
        if _pred is None:
            try:
                from ai_hub.inference_em_fantom.inference_em_fantom import PhantomPredictor

                _pred = PhantomPredictor()
            except Exception:
                logger.warning("E-alanı vekil modeli yüklenemedi; canlı bar kapalı kalacak", exc_info=True)
                _pred = False
        return _pred or None


def get_live() -> dict | None:
    with _live_lock:
        return dict(_live) if _live else None


def _set_live(v: dict | None) -> None:
    global _live
    with _live_lock:
        _live = v


def start_loop(read_coils, is_session_active) -> threading.Thread:
    """2 Hz arka plan döngüsü. `read_coils()` canlı bobin listesi, `is_session_active()` bool.

    Yalnız AKTİF seansta hesaplar — boştayken ONNX çağırmak anlamsız CPU yakar ve
    bar'da eski değeri canlıymış gibi göstermek YANILTICI olur (o durumda None yazılır).
    """

    def _loop():
        while True:
            try:
                if is_session_active() and get_context():
                    _set_live(compute(read_coils()))
                else:
                    _set_live(None)
            except Exception:
                logger.debug("E-alanı döngü hatası", exc_info=True)
            time.sleep(TICK_S)

    t = threading.Thread(target=_loop, daemon=True, name="efield-live")
    t.start()
    return t
