# -*- coding: utf-8 -*-
"""KP (Y236 · kapsam) — `servers/entitlement.py` abonelik kapıları: Supabase doğrulaması, başlık yedeği, önbellek, araştırma kapısı, AI kuyruğu.

Bugün `PEMF_TIER_ENFORCED` KAPALI (satış açılmadı) ama kapılar açıldığı gün tıbbi güvenlik iddiaları taşır: tedavi uçları ASLA kuyruğa
girmez, Supabase kesintisinde ödeyen araştırmacı 402 yemez (fail-open), token yokken başlığa GÜVENİLMEZ (fail-closed, Audit P3), kuyruk
zaman aşımında izin SIZMAZ (Audit P3). Bu dosyadan önce `_supabase_entitlement`, token yolu ve kuyruğun hiçbiri koşmuyordu (%50).
Ağa ÇIKILMAZ: `requests.post` ve kasa okuması (`utils.secrets_manager.get_secret`) en alt katta sahte.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from servers import entitlement as en


def _istek(baslik=None, yol="/api/ai/analiz", state=True):
    return SimpleNamespace(
        headers={k.lower(): v for k, v in (baslik or {}).items()},
        state=SimpleNamespace() if state else None,
        url=SimpleNamespace(path=yol),
    )


class _Yanit:
    def __init__(self, kod=200, govde=None, icerik=True):
        self.status_code, self._g, self.content = kod, govde, b"x" if icerik else b""
        self.ok = 200 <= kod < 300

    def json(self):
        return self._g


@pytest.fixture
def supabase(monkeypatch):
    import requests
    import utils.secrets_manager as sm

    cagrilar: list = []
    durum = {
        "yanit": _Yanit(200, []),
        "sir": {"supabase_url": "https://ornek.supabase.co/", "supabase_anon_key": " anon "},
    }
    monkeypatch.setattr(sm, "get_secret", lambda ad, *a, **k: durum["sir"].get(ad))

    def _post(url, **k):
        cagrilar.append((url, k))
        y = durum["yanit"]
        if isinstance(y, Exception):
            raise y
        return y

    monkeypatch.setattr(requests, "post", _post)
    monkeypatch.setattr(en, "_entitlement_cache", {})
    durum["cagrilar"] = cagrilar
    return durum


def test_KRITIK_supabase_satiri_tier_ve_eklentiye_cevrilir_RPC_ile_istenir(supabase):
    supabase["yanit"] = _Yanit(200, [{"tier": "PRO", "status": "active", "addons": ["Research", ""]}])
    e = en._supabase_entitlement("jwt-1")
    assert (e.tier, e.addons, e.research, e.realtime, e.verified) == ("pro", ("research",), True, False, True)
    url, k = supabase["cagrilar"][0]
    assert url == "https://ornek.supabase.co/rest/v1/rpc/abonelik_getir", "tablo değil SECURITY DEFINER RPC çağrılmalı"
    assert k["headers"]["Authorization"] == "Bearer jwt-1" and k["headers"]["apikey"] == "anon" and k["json"] == {}
    supabase["yanit"] = _Yanit(200, [{"tier": "pro_plus", "status": "trialing", "addons": "research, x"}])
    e = en._supabase_entitlement("jwt-2")
    assert e.realtime and e.addons == ("research", "x")


@pytest.mark.parametrize(
    "satir",
    [
        {"tier": "pro_plus", "status": "past_due", "addons": ["research"]},
        {"tier": "elmas", "status": "active", "addons": []},
        {"tier": None, "status": None, "addons": None},
    ],
)
def test_KRITIK_etkin_olmayan_ya_da_tanimsiz_abonelik_EN_DUSUK_katmana_ve_eklentisiz_duser(supabase, satir):
    supabase["yanit"] = _Yanit(200, [satir])
    e = en._supabase_entitlement("jwt")
    assert e.tier == "baslangic"
    if satir["status"] == "past_due":
        assert e.addons == (), "ödenmemiş abonelikte eklenti korundu"


def test_supabase_yanit_turleri_KESIN_ya_da_YEDEGE_dusme(supabase):
    supabase["yanit"] = _Yanit(200, [])
    assert en._supabase_entitlement("t") == en.Entitlement(tier="baslangic"), "abonelik yok = başlangıç"
    supabase["yanit"] = _Yanit(200, None, icerik=False)
    assert en._supabase_entitlement("t").tier == "baslangic"
    for kod in (401, 403):
        supabase["yanit"] = _Yanit(kod)
        assert en._supabase_entitlement("t") == en.Entitlement(), (
            "geçersiz token tedaviyi bloklamamalı (fail-open varsayılan)"
        )
    supabase["yanit"] = _Yanit(503)
    assert en._supabase_entitlement("t") is None
    supabase["yanit"] = OSError("ag yok")
    assert en._supabase_entitlement("t") is None
    supabase["yanit"] = _Yanit(200, [{"tier": "pro", "status": "active", "addons": 7}])
    assert en._supabase_entitlement("t").addons == ()
    supabase["sir"] = {"supabase_url": "", "supabase_anon_key": "a"}
    assert en._supabase_entitlement("t") is None, "Supabase yapılandırılmamışken istek atıldı"


def test_KRITIK_token_yolu_ONBELLEKLI_kesintide_DOGRULANMAMIS_isaretlenir(supabase):
    supabase["yanit"] = _Yanit(200, [{"tier": "pro", "status": "active", "addons": []}])
    r = _istek({"Authorization": "Bearer jwt-x"})
    assert en._resolve_uncached(r).tier == "pro"
    assert en._resolve_uncached(_istek({"Authorization": "Bearer jwt-x"})).tier == "pro"
    assert len(supabase["cagrilar"]) == 1, "önbellek çalışmıyor (her istekte Supabase'e gidiliyor)"
    supabase["yanit"] = _Yanit(500)
    d = en._resolve_uncached(_istek({"Authorization": "bearer jwt-y", "X-PEMF-Tier": "pro_plus"}))
    assert d.verified is False and d.tier == "pro_plus"
    assert en._resolve_uncached(_istek({"Authorization": "Bearer jwt-y"})).verified is False
    assert len(supabase["cagrilar"]) == 2, "kısa negatif önbellek yok → çift sorgu"


def test_KRITIK_kesinti_NEGATIF_onbellegi_en_cok_5_sn_kesin_sonuc_TTL_boyu_tutulur(supabase, monkeypatch):
    """Supabase kesintisinde DOĞRULANMAMIŞ sonuç yalnız ≤ 5 sn tutulur → servis dönünce ödeyen kullanıcı TTL (60 sn) boyunca
    yanlış "doğrulanmamış" kalmaz; KESİN sonuç ise TTL boyunca yeniden sorgulanmaz."""
    saat = {"t": 1000.0}
    monkeypatch.setattr(en, "time", SimpleNamespace(monotonic=lambda: saat["t"]))
    monkeypatch.setattr(en, "_CACHE_TTL", 60.0)
    supabase["yanit"] = _Yanit(500)
    assert en._resolve_uncached(_istek({"Authorization": "Bearer jwt-z"})).verified is False
    supabase["yanit"] = _Yanit(200, [{"tier": "pro", "status": "active", "addons": ["research"]}])
    saat["t"] += 4.9
    assert en._resolve_uncached(_istek({"Authorization": "Bearer jwt-z"})).verified is False, (
        "negatif önbellek 5 sn dolmadan bitti"
    )
    saat["t"] += 0.2  # 5,1 sn → negatif kayıt süresi DOLDU → yeniden sorgu
    d = en._resolve_uncached(_istek({"Authorization": "Bearer jwt-z"}))
    assert d.verified is True and d.research is True, "kesinti bitti ama doğrulanmamış sonuç TTL boyunca tutuldu"
    n = len(supabase["cagrilar"])
    saat["t"] += 59.0
    assert (
        en._resolve_uncached(_istek({"Authorization": "Bearer jwt-z"})).research is True
        and len(supabase["cagrilar"]) == n
    )
    saat["t"] += 1.1
    en._resolve_uncached(_istek({"Authorization": "Bearer jwt-z"}))
    assert len(supabase["cagrilar"]) == n + 1, "kesin sonuç TTL dolunca yeniden doğrulanmadı"


def test_onbellek_512_ustunde_temizlenir(supabase, monkeypatch):
    dolu = {f"t{i}": (10**12, en.Entitlement()) for i in range(513)}
    monkeypatch.setattr(en, "_entitlement_cache", dolu)
    supabase["yanit"] = _Yanit(200, [])
    en._resolve_uncached(_istek({"Authorization": "Bearer yeni"}))
    assert list(en._entitlement_cache) == ["yeni"]


def test_baslik_yedegi_ve_istek_ici_memo(monkeypatch):
    assert en._headers_entitlement(_istek({"X-PEMF-Tier": "PRO", "X-PEMF-Addons": "research, b"})) == en.Entitlement(
        "pro", ("research", "b")
    )
    assert en._headers_entitlement(_istek({"X-PEMF-Tier": "sahte"})).tier == en.DEFAULT_TIER
    assert en._headers_entitlement(SimpleNamespace(headers=None)) == en.Entitlement(), (
        "bozuk istek fail-open varsayılana düşmeli"
    )
    r = _istek({"X-PEMF-Tier": "pro"})
    ilk = en.resolve_entitlement(r)
    r.headers["x-pemf-tier"] = "baslangic"
    assert en.resolve_entitlement(r) is ilk, "aynı istekte ikinci kapı yeniden çözdü (memo yok)"
    assert en.resolve_entitlement(_istek({"X-PEMF-Tier": "pro"}, state=False)).tier == "pro", "state yokken çözüm düştü"
    assert en._bearer_token(_istek({"Authorization": "Basic abc"})) == ""


def test_KRITIK_arastirma_kapisi_kapaliyken_noop_aciKken_tokensiz_FAIL_CLOSED(supabase, monkeypatch):
    en.require_research(_istek({"X-PEMF-Addons": "research"}))  # kapalı → no-op
    monkeypatch.setattr(en, "TIER_ENFORCED", True)
    with pytest.raises(HTTPException) as h:
        en.require_research(_istek({"X-PEMF-Addons": "research"}))
    assert h.value.status_code == 402, "token yokken sahte başlığa güvenildi (Audit P3)"
    supabase["yanit"] = _Yanit(200, [{"tier": "pro", "status": "active", "addons": []}])
    with pytest.raises(HTTPException) as h:
        en.require_research(_istek({"Authorization": "Bearer t1"}))
    assert h.value.detail["error"] == "research_required"
    supabase["yanit"] = _Yanit(200, [{"tier": "pro", "status": "active", "addons": ["research"]}])
    en.require_research(_istek({"Authorization": "Bearer t2"}))
    supabase["yanit"] = OSError("kesinti")
    en.require_research(
        _istek({"Authorization": "Bearer t3"})
    )  # Supabase kesintisinde ödeyen araştırmacı 402 YEMEZ (fail-open)


def _kapidan_gec(r):
    async def _kos():
        g = en.ai_queue_gate(r)
        await g.__anext__()
        with pytest.raises(StopAsyncIteration):
            await g.__anext__()

    asyncio.run(_kos())


def test_KRITIK_kuyruk_kapali_ise_ve_TEDAVI_uclarinda_HIC_beklemez(monkeypatch):
    _kapidan_gec(_istek())
    monkeypatch.setattr(en, "TIER_ENFORCED", True)

    async def _dolu():
        s = asyncio.Semaphore(0)  # kuyruk tamamen DOLU
        monkeypatch.setattr(en, "_ai_semaphore", s)

        async def _gecer_ve_temiz_biter(g):
            await asyncio.wait_for(g.__anext__(), 1.0)  # kuyruğa girseydi burada asılırdı
            with pytest.raises(StopAsyncIteration):  # uç bitti → üreteç tek adımda kapanır
                await g.__anext__()
            assert s._value == 0, "kuyruğa girmeyen istek bitişte semafor izni SALIVERDİ (izin sızıntısı)"

        for yol in ("/api/ai/pro/stop", "/api/ai/ai_pro/frame", "/api/ai/landmark"):
            await _gecer_ve_temiz_biter(en.ai_queue_gate(_istek({"X-PEMF-Tier": "baslangic"}, yol=yol)))
        await _gecer_ve_temiz_biter(en.ai_queue_gate(_istek({"X-PEMF-Tier": "pro_plus"})))

    asyncio.run(_dolu())


def test_kuyruk_sinirsiz_beklemede_semafor_tutulur_ve_birakilir(monkeypatch):
    monkeypatch.setattr(en, "TIER_ENFORCED", True)
    monkeypatch.setattr(en, "AI_QUEUE_MAX_WAIT", 0.0)

    async def _kos():
        s = asyncio.Semaphore(1)
        monkeypatch.setattr(en, "_ai_semaphore", s)
        g = en.ai_queue_gate(_istek({"X-PEMF-Tier": "pro"}))
        await g.__anext__()
        assert s.locked(), "istek boyunca kuyruk izni tutulmadı"
        with pytest.raises(StopAsyncIteration):
            await g.__anext__()
        assert not s.locked()

    asyncio.run(_kos())


def test_KRITIK_kuyruk_zaman_asiminda_FAIL_OPEN_ve_izin_SIZMAZ(monkeypatch):
    monkeypatch.setattr(en, "TIER_ENFORCED", True)
    monkeypatch.setattr(en, "AI_QUEUE_MAX_WAIT", 0.05)

    async def _kos():
        s = asyncio.Semaphore(1)
        monkeypatch.setattr(en, "_ai_semaphore", s)
        await s.acquire()  # başka bir analiz izni tutuyor
        g = en.ai_queue_gate(_istek({"X-PEMF-Tier": "pro"}))
        await asyncio.wait_for(g.__anext__(), 1.0)  # 0,05 sn sonra fail-open
        with pytest.raises(StopAsyncIteration):
            await g.__anext__()
        s.release()
        for _ in range(5):
            await asyncio.sleep(0)
        assert s._value == 1, f"zaman aşımından sonra izin SIZDI (kapasite {s._value})"
        g = en.ai_queue_gate(_istek({"X-PEMF-Tier": "pro"}))
        await g.__anext__()
        assert s.locked()
        await g.aclose()

    asyncio.run(_kos())


def test_BOZUK_ortam_degerleri_modulu_OLDURMEZ_varsayilana_duser(monkeypatch):
    """D1.14: kuyruk / abonelik ayarındaki yazım hatası backend'i (dolayısıyla ACİL DURDUR ucunu) açılışta öldürmemeli."""
    monkeypatch.setenv("PEMF_AI_QUEUE_CONCURRENCY", "bir")
    monkeypatch.setenv("PEMF_AI_QUEUE_MAX_WAIT", "4,5")
    monkeypatch.setenv("PEMF_DEFAULT_TIER", "elmas")
    spec = importlib.util.spec_from_file_location("kp_entitlement_kopya", Path(en.__file__))
    kopya = importlib.util.module_from_spec(spec)
    # dataclass + ertelenmiş açıklama: `dataclasses` modülü sys.modules'tan arar → kopya YALNIZ bu test boyunca kayıtlı (gerçek
    # `servers.entitlement` girdisine ve paket özniteliğine dokunulmaz).
    monkeypatch.setitem(sys.modules, "kp_entitlement_kopya", kopya)
    spec.loader.exec_module(kopya)
    assert (kopya.AI_QUEUE_CONCURRENCY, kopya.AI_QUEUE_MAX_WAIT, kopya.DEFAULT_TIER) == (1, 30.0, "pro_plus")
