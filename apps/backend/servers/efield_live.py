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

from utils.dongu_guvenligi import dongu_hatasini_bildir

logger = logging.getLogger(__name__)

# Analizden gelen SABİT bağlam (konum + organ). em_fantom/em_petri analizi çalışınca set edilir.
_ctx_lock = threading.Lock()
_ctx: dict | None = None
# O-A2-K.1 (2-A incelemesi): bağlam NESLİ — her kurma ve temizleme bir artırır. Biten AI Pro döngüsünün GEÇ kapanışı yalnız
# kendi döneminin bağlamını siler (`temizle_degismediyse`). Zaman damgası (`set_at`) yetmez: `time.time()` bu makinede
# 15,6 ms çözünürlüklü (ölçüldü) → döngü çıkışıyla aynı tikte kurulan yeni bağlam "eski" sayılırdı.
_ctx_nesli = 0

# Son hesaplanan canlı değer (snapshot bunu okur — ONNX istek yolunda çalışmaz).
_live_lock = threading.Lock()
_live: dict | None = None

# 2 Hz: göz için akıcı, CPU için önemsiz. Daha hızlısı bar'ı okunamaz yapar.
TICK_S = 0.5


def set_context(regions: list[dict], organ_id: int | None = None, model: str | None = None) -> None:
    """Analiz/seans sonucundan konum bağlamını sakla. `regions`: her biri en az
    ``centroid_cabin_mm`` (x,y,z) taşıyan hedef bölgeleri. Boş liste → bağlamı TEMİZLE.

    `model` (2026-09-09, yalnız-ek): bağlamı hangi hedef modeli kurdu ("fantom" | "petri" | ...).
    Vekil E modeli seçimi buna göre yapılır; verilmezse eski davranış (fantom vekili) sürer.
    ⚠️ İmza GERİYE UYUMLU: mevcut çağrılar ve `tests/test_efield_live.py` etkilenmez."""
    global _ctx, _ctx_nesli
    if not regions:
        with _ctx_lock:
            _ctx = None
            _ctx_nesli += 1
        _set_live(None)
        return
    _ad = (model or "").strip().lower() or None
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
            "model": _ad,
            "set_at": time.time(),
        }
        _ctx_nesli += 1
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


def baglam_nesli() -> int:
    """O-A2-K.1: bağlamın şu anki nesli (her kurma/temizleme +1). Bkz. `temizle_degismediyse`."""
    with _ctx_lock:
        return _ctx_nesli


def temizle_degismediyse(nesil: int) -> bool:
    """O-A2-K.1: bağlamı YALNIZ `nesil`den beri kurulmadı/temizlenmediyse temizler (True). AI Pro döngüsü ÇIKTIĞI andaki nesli
    alır; çıkış ile kapanışı arasında yeni bir analiz bağlam kurduysa geç kapanış ona dokunmaz (False)."""
    global _ctx, _ctx_nesli
    with _ctx_lock:
        if _ctx_nesli != nesil:
            return False
        _ctx = None
        _ctx_nesli += 1
    _set_live(None)
    return True


def seans_basladi(tur: str = "", model: str | None = None) -> None:
    """D1.61 · B-1.25 — YENİ seans başlarken analiz bağlamı yalnız AYNI modelin araştırma AI Pro seansında KALIR.

    Bağlamı fantom/petri ANALİZİ kurar (bir tümör konumu). Ölçüldü (plan, 20 olayın 17'si): elle ya da kedi seansında
    bağlam duruyordu → E barı BAŞKA hedefin (önceki analizin) E'sini "● canlı" gösteriyordu. Analiz ucu bağlamı modelsiz
    kurar → fantom vekili (bkz. `_predictor`), bu yüzden modelsiz bağlam "fantom" sayılır."""
    global _ctx_nesli
    ctx = get_context()
    if ctx is None:
        return
    m = (model or "").strip().lower()
    if tur == "ai_pro" and m in ("fantom", "petri") and m == (ctx.get("model") or "fantom"):
        # C2-1.15: korunan bağlam artık YENİ seansındır → nesil artar (biten döngünün geç kapanışı onu silmesin).
        with _ctx_lock:
            _ctx_nesli += 1
        return
    logger.info("Canlı E bağlamı yeni seans başlangıcında temizlendi (tür=%s, model=%s)", tur or "-", m or "-")
    set_context([])


def seans_bitti() -> None:
    """D1.61: seans biterken (durdurma, acil durdurma) bağlam ve son değer TEMİZLENİR — sonraki seansa sızmaz."""
    set_context([])


_aralik_lock = threading.Lock()
_aralik: dict = {}


def _egitim_sutun_araligi(model: str | None, sutun: int, ad: str) -> tuple[float, float] | None:
    """Vekil modelin bir girdisinin EĞİTİM aralığı: modülün XAI referans örnekleminden (`xai_ref_stats`) OKUNUR, sabit
    yazılmaz → model yeniden eğitilirse kendiliğinden güncellenir. Girdi sırası `x, y, z, organ_id, achieved_B, duty_sum`
    (modül başlığı). Okunamazsa None."""
    _anahtar = "petri" if (model or "").strip().lower() == "petri" else "fantom"
    with _aralik_lock:
        if (_anahtar, sutun) in _aralik:
            return _aralik[(_anahtar, sutun)]
    try:
        if _anahtar == "petri":
            from ai_hub.inference_em_petri import inference_em_petri as _mod
        else:
            from ai_hub.inference_em_fantom import inference_em_fantom as _mod
        bg = _mod.xai_ref_stats()["background"]
        deger = (float(bg[:, sutun].min()), float(bg[:, sutun].max()))
    except Exception:
        logger.warning("E-alanı: %s modelinin eğitim %s aralığı okunamadı", _anahtar, ad, exc_info=True)
        deger = None
    with _aralik_lock:
        _aralik[(_anahtar, sutun)] = deger
    return deger


def egitim_b_araligi_T(model: str | None = None) -> tuple[float, float] | None:
    """İG-5.83 — vekil modelin `achieved_B` EĞİTİM aralığı (Tesla; sütun 4). Okunamazsa None (E gösterilmez)."""
    return _egitim_sutun_araligi(model, 4, "B")


def egitim_duty_araligi(model: str | None = None) -> tuple[float, float] | None:
    """Y51 (sahip) — vekil modelin `duty_sum` EĞİTİM aralığı (sütun 5; fantom ≈ 1,94–2,90). Okunamazsa None."""
    return _egitim_sutun_araligi(model, 5, "duty_sum")


def telemetry_inputs(coils: list[dict]) -> tuple[float | None, float, int]:
    """Canlı bobin listesinden (``achieved_B`` Tesla, ``duty_sum``, çalışan bobin sayısı).

    YALNIZ ÇALIŞAN bobinler sayılır: duran bobin alan üretmez, ortalamaya katılırsa
    B'yi yapay olarak düşürür. Çalışan yoksa (0.0, 0.0, 0) → çağıran E'yi sıfırlar.

    ⚠️ D1.76 (B-1.24): B yalnız alanı GERÇEKTEN ölçülen (`measuredFields`te `magneticMt` olan, D1.67: taze) bobinlerin
    ortalamasıdır. Ölçülmeyen bobinin `magneticMt`i 0.0 başlangıç değeridir; ortalamaya girerse B yapay düşer (7 bobin
    çalışırken yalnız bobin 6 ölçüyorsa 1,842 mT → 0,263 mT). Hiçbir bobin ölçmüyorsa B = None (Y6: ölçülmeyen '—').
    """
    run = [c for c in (coils or []) if c.get("running")]
    if not run:
        return 0.0, 0.0, 0
    olculen = [c for c in run if "magneticMt" in (c.get("measuredFields") or [])]
    b_t = (sum(float(c.get("magneticMt") or 0.0) for c in olculen) / len(olculen) / 1000.0) if olculen else None
    duty_sum = sum(float(c.get("dutyCycle") or 0.0) for c in run) / 100.0
    return b_t, duty_sum, len(run)


def compute(coils: list[dict]) -> dict | None:
    """Canlı bobin durumundan E değerlerini üret. Bağlam yoksa/bobin çalışmıyorsa None.

    E HESAPLANMAZ (değerler None, arayüz '—'; Ö.4-Y9: kıskaç/tavan DEĞİL, yalnız gösterim) — D1.76 · İG-5.83:
      * alan hiçbir çalışan bobinde ölçülmüyorsa (`bOlculmuyor`),
      * ölçülen B modelin eğitim aralığı dışındaysa (`egitimAraligiDisi`) — model orada anlamsız sayı üretir
        (ölçüldü: E(0 mT)/E(1 mT) = 5,5, monoton değil),
      * aralık okunamıyorsa (`egitimAraligiBilinmiyor`)."""
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
    _hesapsiz = None
    if achieved_b is None:
        _hesapsiz = "bOlculmuyor"
    else:
        _aralik_t = egitim_b_araligi_T((ctx or {}).get("model"))
        if _aralik_t is None:
            _hesapsiz = "egitimAraligiBilinmiyor"
        elif not (_aralik_t[0] <= achieved_b <= _aralik_t[1]):
            _hesapsiz = "egitimAraligiDisi"
    if _hesapsiz is not None:
        return {
            "healthy": None,
            "cancer": None,
            "avg": None,
            "activeCoils": n,
            "achievedB_T": achieved_b,
            "dutySum": duty_sum,
            _hesapsiz: True,
            "ts": time.time(),
        }
    try:
        pred = _predictor((ctx or {}).get("model"))
        if pred is None:
            return None
        out = pred.predict(ctx["x"], ctx["y"], ctx["z"], ctx["organ_id"], achieved_b, duty_sum)
    except Exception:
        logger.debug("canlı E hesabı başarısız", exc_info=True)
        return None
    sonuc = {
        "healthy": float(out.get("result_E_healthy") or 0.0),
        "cancer": float(out.get("result_E_cancer") or 0.0),
        "avg": float(out.get("result_E_avg") or 0.0),
        "activeCoils": n,
        "achievedB_T": achieved_b,
        "dutySum": duty_sum,
        "ts": time.time(),
    }
    # Y51 (sahip): toplam duty modelin EĞİTİM aralığı DIŞINDAYSA E yine GÖSTERİLİR ama "eğitim aralığı dışı — güvenilmez"
    # etiketi taşır (B kuralı — İG-5.83, E '—' — AYNEN kalır; bu yalnız gösterim etiketi, sürüş etkilenmez: araştırma hattı
    # sürmez). Tipik seans (5 bobin × %30 = 1,5) fantom aralığının (≈1,94–2,90) dışındadır. Aralık okunamazsa etiket
    # konmaz (bilinmiyor ≠ dışarıda; B okunamazsa zaten E hesaplanmaz).
    _d_aralik = egitim_duty_araligi((ctx or {}).get("model"))
    if _d_aralik is not None and not (_d_aralik[0] <= duty_sum <= _d_aralik[1]):
        sonuc["dutyEgitimAraligiDisi"] = True
        sonuc["dutyEgitimAraligi"] = [round(_d_aralik[0], 2), round(_d_aralik[1], 2)]
    return sonuc


_pred_lock = threading.Lock()
_pred = None
#: D5.56 (B-10.106): vekil yüklenemediyse NEDEN — "agirlik_yok" (ağırlık dosyası yok: `FileNotFoundError`), "paket_yok" (üçüncü
#: parti çalışma-zamanı paketi yok: depo dışı `ModuleNotFoundError`, ör. CI'da onnxruntime) ya da "hata" (her şey: kırık import /
#: yanlış ad / kod hatası). Eskiden üçü tek `except Exception → False`du: ağırlıklar VARKEN import kırılsa da canlı bar sessizce
#: kapalı kalıyor, kapılar "ağırlık yok" diye ATLIYORDU. Kapılar yalnız ilk ikisinde atlar.
_pred_neden: dict = {}
_DEPO_PAKETLERI = ("ai_hub", "servers", "utils", "database", "controllers", "services")


def _yukleme_nedeni(hata: BaseException) -> str:
    if isinstance(hata, FileNotFoundError):
        return "agirlik_yok"
    if isinstance(hata, ModuleNotFoundError) and (hata.name or "").split(".")[0] not in _DEPO_PAKETLERI:
        return "paket_yok"
    return "hata"


def vekil_yuklenemedi_nedeni(model: str | None = None) -> str | None:
    """`_predictor(model)` None döndüyse nedeni ("agirlik_yok" / "paket_yok" / "hata"); yüklendiyse ya da denenmediyse None."""
    _anahtar = "petri" if (model or "").strip().lower() == "petri" else "fantom"
    with _pred_lock:
        return _pred_neden.get(_anahtar)


def _predictor(model: str | None = None):
    """Vekil E modelini BİR KEZ yükle (2 Hz döngüde her tikte yüklemek diski/CPU'yu boşa yorar).

    `model="petri"` → PetriPredictor, aksi hâlde PhantomPredictor (eski davranış). Sözlükte
    modele göre önbelleklenir; petri seansında fantom vekili kullanmak E barını yanlış ölçeğe
    oturtuyordu (2026-09-09)."""
    global _pred
    _anahtar = "petri" if (model or "").strip().lower() == "petri" else "fantom"
    with _pred_lock:
        if isinstance(_pred, dict) and _anahtar in _pred:
            return _pred[_anahtar] or None
        if not isinstance(_pred, dict):
            _pred = {}
        _pred_neden.pop(_anahtar, None)  # D5.56: yeniden deneme (önbellek sıfırlandı) eski nedeni taşımasın
        try:
            if _anahtar == "petri":
                from ai_hub.inference_em_petri.inference_em_petri import PetriPredictor

                _pred[_anahtar] = PetriPredictor()
            else:
                from ai_hub.inference_em_fantom.inference_em_fantom import PhantomPredictor

                _pred[_anahtar] = PhantomPredictor()
        except Exception as e:
            _pred_neden[_anahtar] = _yukleme_nedeni(e)
            logger.warning(
                "E-alanı vekil modeli yüklenemedi (%s); canlı bar kapalı kalacak", _pred_neden[_anahtar], exc_info=True
            )
            _pred[_anahtar] = False
        return _pred[_anahtar] or None


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
                dongu_hatasini_bildir("E-alanı döngü hatası", logger=logger, seviye=logging.DEBUG)
            time.sleep(TICK_S)

    t = threading.Thread(target=_loop, daemon=True, name="efield-live")
    t.start()
    return t
