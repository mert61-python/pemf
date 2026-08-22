# Author: mertaygn, cglrgrkn
"""
Abonelik tier-enforcement (A1) — real-time↔kuyruk + Araştırma-eklenti kapıları.

⚠️ AI uçları sahibin kararıyla auth-MUAF (bkz. auth-exemptions). Bu modül enforcement'ı
FLAG-GATED + FAIL-OPEN yapar: `PEMF_TIER_ENFORCED` KAPALIYKEN her şey no-op (mevcut davranış
korunur; canlı bozulmaz). Supabase `subscriptions` + Stripe CANLI olunca AÇILIR.

TIER KAYNAĞI (öncelik sırası):
  1) Supabase-DOĞRULAMALI (üretim): `Authorization: Bearer <supabase_jwt>` → Supabase REST
     `subscriptions` (apikey=anon + Bearer=kullanıcı JWT). Supabase JWT'yi DOĞRULAR ve RLS yalnız
     kullanıcının satırını döndürür → tier SPOOF EDİLEMEZ. Sonuç kısa süre cache'lenir.
  2) FALLBACK (dev / enforce-off / token-yok / Supabase-config-yok / altyapı-hatası):
     `X-PEMF-Tier` / `X-PEMF-Addons` başlıkları. ⚠️ SPOOF-edilebilir — yalnız doğrulama mümkün
     olmadığında + fail-open için. Device auth `X-API-Key` kullandığından `Authorization` serbesttir.

TIBBİ-CİHAZ GÜVENLİĞİ: entitlement bir COMPUTE-ÖNCELİĞİ (kuyruk) + ticari kapıdır, GÜVENLİK/
emniyet kontrolü DEĞİL. Bu yüzden her belirsizlikte FAIL-OPEN (tedaviyi asla bloklama):
Supabase erişilemezse / token bayatsa → DEFAULT_TIER. Backend safety-limit'leri (freq/duty/48°C)
bundan tamamen bağımsızdır ve buradan etkilenmez.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from dataclasses import dataclass
from dataclasses import replace as _replace

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)


def _flag(name: str, default: bool = False) -> bool:
    return os.getenv(name, "1" if default else "0").strip().lower() in ("1", "true", "yes", "on")


# ── Yapılandırma (env) ──────────────────────────────────────────────────────
# Enforcement ana anahtarı — Supabase + Stripe hazır olana kadar KAPALI.
TIER_ENFORCED: bool = _flag("PEMF_TIER_ENFORCED", False)

# ⚠️ SİTEDEKİ PLANLARLA AYNI KÜME OLMALI (`pemf-vet-web/src/config.ts::PLANS`). Ayrışırsa
# `_supabase_entitlement` tanımadığı tier'ı SESSİZCE "baslangic"e düşürür → ödeme yapan
# kullanıcı en düşük katman muamelesi görür ve hiçbir yerde hata görünmez.
# `kullandikca` (8. parti, ön ödemesiz üyelik) bu yüzden buraya eklendi.
# Kilit: tests/test_tier_kullandikca_tanimi.py
VALID_TIERS = {"baslangic", "kullandikca", "pro", "pro_plus"}
# Kuyruk bypass'ı YALNIZ Pro+'ta. Kullandıkça-öde bilerek DIŞARIDA: yeni bir ayrıcalık icat
# etmiyoruz, yalnız sessiz düşürmeyi kapatıyoruz. Kuyruk gerçekten açılacaksa (bugün
# `PEMF_TIER_ENFORCED` KAPALI) kullandıkça-öde abonesinin nereye düşeceği SAHİP KARARIDIR.
REALTIME_TIERS = {"pro_plus"}

# Doğrulanmış kaynak yoksa varsayılan tier (fail-open). Geçersiz env değeri → pro_plus'a düzelt
# (aksi halde fail-open sessizce KUYRUĞA düşerdi — bulgu #4).
DEFAULT_TIER: str = (os.getenv("PEMF_DEFAULT_TIER", "pro_plus") or "pro_plus").strip().lower()
if DEFAULT_TIER not in VALID_TIERS:
    logger.warning("Geçersiz PEMF_DEFAULT_TIER=%r → 'pro_plus' kullanılıyor", DEFAULT_TIER)
    DEFAULT_TIER = "pro_plus"

# Non-realtime (Pro/Başlangıç) eşzamanlı AI limiti — üstündeki istekler bekler (= kuyruk). Pro+ bypass.
AI_QUEUE_CONCURRENCY: int = max(1, int(os.getenv("PEMF_AI_QUEUE_CONCURRENCY", "1") or "1"))
# Kuyrukta MAKS bekleme (sn) — aşılırsa fail-open (ağır analiz bile süresiz beklemesin — bulgu #1). 0=sınırsız.
AI_QUEUE_MAX_WAIT: float = max(0.0, float(os.getenv("PEMF_AI_QUEUE_MAX_WAIT", "30") or "30"))
# Supabase doğrulama sonucu cache TTL (sn) + REST zaman aşımı (sn).
_CACHE_TTL: float = max(5.0, float(os.getenv("PEMF_ENTITLEMENT_CACHE_TTL", "60") or "60"))
_SUPABASE_TIMEOUT: float = max(1.0, float(os.getenv("PEMF_ENTITLEMENT_TIMEOUT", "4") or "4"))

# TEDAVİ kontrol/sürüş uçları ASLA kuyruğa girmez (tıbbi güvenlik — bulgu #1): AI Pro başlat/durdur/
# durum/organ/kalibrasyon + gerçek-zamanlı sürüş döngüsü (ai_pro/frame) + bobin süren landmark.
# Kuyruk YALNIZ ağır tek-seferlik ANALİZ uçları içindir (FGS/hastalık/böbrek/histopat/petri…).
_QUEUE_BYPASS_FRAGMENTS = ("/ai/pro/", "/ai/ai_pro/", "/landmark")

# Aktif sayılmayan abonelik durumları → hak "baslangic"e düşer (eklenti de düşer).
_INACTIVE_STATUS = {
    "canceled",
    "cancelled",
    "unpaid",
    "past_due",
    "incomplete",
    "incomplete_expired",
    "paused",
}

# token → (expiry_monotonic, Entitlement); çok-thread erişim için kilit (bulgu #5).
_entitlement_cache: dict[str, tuple[float, "Entitlement"]] = {}
_cache_lock = threading.Lock()


@dataclass(frozen=True)
class Entitlement:
    tier: str = DEFAULT_TIER
    addons: tuple[str, ...] = ()
    # False → token vardı ama Supabase DOĞRULANAMADI (ağ/5xx). require_research bunu bloklamaz
    # (fail-open — ödeyen araştırmacı Supabase kesintisinde 402 yememeli — bulgu #2).
    verified: bool = True

    @property
    def realtime(self) -> bool:
        return self.tier in REALTIME_TIERS

    @property
    def research(self) -> bool:
        return "research" in self.addons


def _bearer_token(request: Request) -> str:
    """`Authorization: Bearer <supabase_jwt>` — device auth X-API-Key kullanır, bu header serbest."""
    h = request.headers.get("authorization") or ""
    return h[7:].strip() if h[:7].lower() == "bearer " else ""


def _headers_entitlement(request: Request) -> Entitlement:
    """FALLBACK: X-PEMF-Tier/Addons başlıkları (SPOOF-edilebilir → yalnız doğrulama yoksa + fail-open)."""
    try:
        tier = (request.headers.get("x-pemf-tier") or "").strip().lower() or DEFAULT_TIER
        if tier not in VALID_TIERS:
            tier = DEFAULT_TIER
        raw = (request.headers.get("x-pemf-addons") or "").strip().lower()
        addons = tuple(a for a in raw.replace(" ", "").split(",") if a)
        return Entitlement(tier=tier, addons=addons)
    except Exception:  # noqa: BLE001 — fail-open
        return Entitlement()


def _supabase_entitlement(token: str) -> "Entitlement | None":
    """Supabase REST ile RLS-kapsamlı subscription çek (token'ı SUPABASE doğrular → spoof-proof).

    Dönüş:
      Entitlement → KESİN sonuç (satır yoksa 'baslangic'; token geçersizse fail-open DEFAULT).
      None        → config-yok / ağ / altyapı hatası → çağıran başlık-fallback + fail-open yapar.
    """
    try:
        from utils.secrets_manager import get_secret

        base = (get_secret("supabase_url") or "").rstrip("/")
        anon = (get_secret("supabase_anon_key") or "").strip()
        if not base or not anon:
            return None  # Supabase yapılandırılmamış → header fallback
        import requests

        # ⚠️ RPC ÜZERİNDEN (sahip kararı 2026-08-21): eskiden `/rest/v1/subscriptions` tablosu
        # doğrudan okunuyordu; bu, `authenticated` rolüne tabloda SELECT yetkisi BIRAKILMASINI
        # zorunlu kılıyordu (RLS politikası tek başına yetmez) ve Supabase'in yeni tabloya verdiği
        # varsayılan yetkileri kaynağında kapatmayı engelliyordu.
        # `abonelik_getir()` SECURITY DEFINER'dır, kimliği `auth.uid()`ten alır (parametre YOK) ve
        # yalnız gereken 5 alanı döndürür — `stripe_*` sütunları artık hiç gelmiyor.
        r = requests.post(
            f"{base}/rest/v1/rpc/abonelik_getir",
            json={},
            headers={
                "apikey": anon,
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=_SUPABASE_TIMEOUT,
        )
        if r.status_code in (401, 403):
            # Token geçersiz/bayat → kimlik doğrulanamadı. Tıbbi cihaz: tedaviyi BLOKLAMA →
            # fail-open DEFAULT. (Zaten header-fallback de aynı sonucu verirdi; enforcement
            # compute-önceliği içindir, güvenlik değil.)
            return Entitlement()
        if not r.ok:
            return None  # 5xx vb. altyapı hatası → fallback + fail-open
        rows = r.json() if r.content else []
        if not isinstance(rows, list) or not rows:
            return Entitlement(tier="baslangic")  # abonelik YOK = en düşük tier (kuyruk, eklenti-yok)
        row = rows[0] or {}
        status = str(row.get("status") or "").strip().lower()
        inactive = status in _INACTIVE_STATUS
        tier = str(row.get("tier") or "baslangic").strip().lower()
        if tier not in VALID_TIERS or inactive:
            tier = "baslangic"
        av = row.get("addons") or []
        if isinstance(av, str):
            av = [a for a in av.replace(" ", "").split(",") if a]
        addons: tuple[str, ...] = (
            ()
            if inactive
            else tuple(str(a).strip().lower() for a in (av if isinstance(av, (list, tuple)) else []) if a)
        )
        return Entitlement(tier=tier, addons=addons)
    except Exception:  # noqa: BLE001 — her hata → fallback + fail-open
        logger.debug("Supabase entitlement lookup başarısız (fail-open)", exc_info=True)
        return None


def resolve_entitlement(request: Request) -> Entitlement:
    """İstekten entitlement çöz. Öncelik: Supabase-DOĞRULAMALI (Bearer→RLS lookup, cache'li,
    spoof-proof). Yoksa/hata → X-PEMF-* başlık fallback (dev/enforce-off; fail-open).

    Aynı istekte iki kapı (require_research + ai_queue_gate) çağırdığından sonuç request.state'e
    memolanır → tek Supabase lookup (bulgu #3).

    ⚠️ BLOKLAYAN ağ çağrısı içerebilir → SENKRON çağır (FastAPI sync-dependency'yi threadpool'a
    atar) VEYA async bağlamdan `await asyncio.to_thread(resolve_entitlement, request)` ile çağır.
    """
    memo = getattr(request.state, "_pemf_entitlement", None)
    if memo is not None:
        return memo
    ent = _resolve_uncached(request)
    try:
        request.state._pemf_entitlement = ent
    except Exception:  # noqa: BLE001 — state yoksa sessizce geç
        pass
    return ent


def _resolve_uncached(request: Request) -> Entitlement:
    token = _bearer_token(request)
    if token:
        now = time.monotonic()
        with _cache_lock:
            hit = _entitlement_cache.get(token)
        if hit and hit[0] > now:
            return hit[1]
        ent = _supabase_entitlement(token)
        if ent is not None:  # KESİN sonuç → cache'le (_CACHE_TTL)
            with _cache_lock:
                if len(_entitlement_cache) > 512:
                    _entitlement_cache.clear()  # basit sınır (JWT'ler ~saatlik döner, sızma yok)
                _entitlement_cache[token] = (now + _CACHE_TTL, ent)
            return ent
        # token VARDI ama Supabase doğrulayamadı (ağ/5xx) → fail-open ama DOĞRULANMAMIŞ işaretle
        # (require_research bloklamaz — bulgu #2). Kısa neg-cache → çift-lookup önler (bulgu #3).
        unverified = _replace(_headers_entitlement(request), verified=False)
        with _cache_lock:
            _entitlement_cache[token] = (now + min(5.0, _CACHE_TTL), unverified)
        return unverified
    # Token yok → başlık fallback (dev/enforce-off; başlıklar bilerek "verified" sayılır)
    return _headers_entitlement(request)


def require_research(request: Request) -> None:
    """Araştırma modeli uçları için dependency. Enforce kapalıysa no-op; açıkken eklenti yoksa 402.

    SYNC dependency → FastAPI bunu threadpool'a atar; içindeki bloklayan Supabase çağrısı event
    loop'u BLOKLAMAZ (async değil kasıtlı)."""
    if not TIER_ENFORCED:
        return
    # Audit P3: enforcement AÇIKKEN Bearer token YOKSA header-fallback'e (X-PEMF-Addons:research) GÜVENME
    # → fail-CLOSED (kesin 402). Token VARSA + Supabase-down → aşağıdaki fail-open korunur (ödeyen
    # araştırmacı kesintide 402 yemesin, bulgu #2).
    if not _bearer_token(request):
        raise HTTPException(
            status_code=402,
            detail={
                "error": "research_required",
                "message": "Araştırma modelleri doğrulanmış abonelik gerektirir (kimlik doğrulama gerekli).",
            },
        )
    ent = resolve_entitlement(request)
    # DOĞRULANAMADIYSA (token vardı, Supabase ulaşılamadı) BLOKLAMA — fail-open (bulgu #2):
    # ödeyen bir araştırmacı Supabase kesintisinde 402 yememeli.
    if not ent.verified:
        return
    if not ent.research:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "research_required",
                "message": "Araştırma modelleri Araştırma eklentisi gerektirir.",
            },
        )


# ── Kuyruk (compute-önceliği): Pro+ real-time bypass; diğerleri paylaşımlı semafor ─────────────
_ai_semaphore = asyncio.Semaphore(AI_QUEUE_CONCURRENCY)


async def ai_queue_gate(request: Request):
    """Router-seviyesi yield-dependency. Enforce kapalı → no-op. Açıkken Pro+ kuyruksuz;
    Pro/Başlangıç paylaşımlı semafora girer (istek boyunca tutar → eşzamanlılık sınırı = kuyruk).

    GÜVENLİK (bulgu #1): tedavi kontrol/sürüş uçları (_QUEUE_BYPASS_FRAGMENTS) ASLA kuyruğa girmez —
    durdurma/sürüş asla ağır bir analiz arkasında beklemez. Ayrıca kuyruk beklemesi AI_QUEUE_MAX_WAIT
    ile sınırlıdır → aşılırsa fail-open (süresiz bekleme yok).

    resolve_entitlement BLOKLAYAN ağ çağrısı içerebildiğinden `asyncio.to_thread` ile threadpool'a
    atılır → event loop BLOKLANMAZ (senkron-in-async tuzağından kaçınılır)."""
    if not TIER_ENFORCED:
        yield
        return
    # Tedavi kontrol/sürüş uçları → kuyruk YOK (tıbbi güvenlik).
    if any(frag in request.url.path for frag in _QUEUE_BYPASS_FRAGMENTS):
        yield
        return
    ent = await asyncio.to_thread(resolve_entitlement, request)
    if ent.realtime:
        yield  # Pro+ → gerçek-zamanlı, kuyruk yok
        return
    # Pro/Başlangıç → paylaşımlı semafor (kuyruk). Sınırsız beklemeyi engelle → fail-open.
    if AI_QUEUE_MAX_WAIT <= 0:
        async with _ai_semaphore:
            yield
        return
    # Audit P3: py3.10'da wait_for(semaphore.acquire()) timeout-anında permit verilmişse iptal edilen
    # coroutine finally'ye ulaşmaz → permit SIZAR (kapasite 0'a iner, her istek AI_QUEUE_MAX_WAIT bekler).
    # shield + done-callback ile: timeout'ta task bağımsız sürer; permit sonradan kazanılırsa RELEASE edilir.
    _acq = asyncio.ensure_future(_ai_semaphore.acquire())
    try:
        await asyncio.wait_for(asyncio.shield(_acq), timeout=AI_QUEUE_MAX_WAIT)
    except asyncio.TimeoutError:
        _acq.add_done_callback(
            lambda t: _ai_semaphore.release() if (not t.cancelled() and t.exception() is None) else None
        )
        _acq.cancel()
        yield  # çok beklendi → fail-open (analizi/tedaviyi süresiz bloklama)
        return
    try:
        yield
    finally:
        _ai_semaphore.release()
