# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Sitede satilan HER plan, backend'in TANIDIGI bir tier olmali (8. parti).

BULUNAN KUSUR: `pemf-vet-web/src/config.ts::PLANS` icine "Kullandikca Ode" plani eklendi
(tier='kullandikca'), ama `servers/entitlement.py::VALID_TIERS` yalnizca
{baslangic, pro, pro_plus} taniyordu. `_supabase_entitlement` satiri okurken:

    if tier not in VALID_TIERS or inactive:
        tier = "baslangic"

Yani ODEME YAPAN bir kullandikca-ode abonesi, tier'i tanınmadigi icin SESSIZCE en dusuk
katmana dusurulurdu (`TIER_ENFORCED` acildiginda paylasimli AI kuyruguna girer). Kullanici
para oder, hizmeti ucretsiz katman gibi alir — ve hicbir yerde hata gorunmez.

Bu, deponun 1 numarali hata deseni: "ayni sozluk iki yerde, biri guncellenir".
Kapi: sitedeki plan tier'lari ile backend'in VALID_TIERS kumesi AYNI olmali.

⚠️ Bu test bir SATIS acma islemi DEGILDIR: `PEMF_TIER_ENFORCED` ve `FREE_MODE` durumuna
dokunmaz (sahip karari: satis kapali kalacak). Yalnizca iki sozlugun ayrismasini onler.
"""

from __future__ import annotations

import re
from pathlib import Path

_KOK = Path(__file__).resolve().parent.parent


def _web_tierlari() -> set[str]:
    src = (_KOK / "pemf-vet-web" / "src" / "config.ts").read_text(encoding="utf-8", errors="replace")
    # PLANS girdilerindeki `tier: '...'` degerleri (tip birlesimini degil, GERCEK planlari oku).
    return set(re.findall(r"^\s*tier:\s*'([a-z_]+)',", src, re.M))


def _backend_tierlari() -> set[str]:
    src = (_KOK / "servers" / "entitlement.py").read_text(encoding="utf-8", errors="replace")
    m = re.search(r"VALID_TIERS\s*=\s*\{([^}]*)\}", src)
    assert m, "entitlement.py icinde VALID_TIERS bulunamadi"
    return set(re.findall(r'"([a-z_]+)"', m.group(1)))


def test_KRITIK_sitede_satilan_her_plan_backendde_TANIMLI():
    web = _web_tierlari()
    backend = _backend_tierlari()
    assert web, "site tarafinda hic plan tier'i okunamadi (test kor kalmis)"

    tanimsiz = web - backend
    assert not tanimsiz, (
        f"Sitede satilan ama backend'in TANIMADIGI tier(lar): {sorted(tanimsiz)}. "
        f"`_supabase_entitlement` bunlari sessizce 'baslangic'e dusurur → odeme yapan kullanici "
        f"en dusuk katman muamelesi gorur. VALID_TIERS: {sorted(backend)}"
    )


def test_KARSIT_KANIT_backend_uydurma_tier_TANIMAMALI():
    """Asiri-genisleme korumasi: kapiyi 'her seyi kabul et' diye gecmek, spoof edilebilir
    `X-PEMF-Tier` basligini serbest birakir (o baslik dogrulanmis kaynak yokken kullaniliyor)."""
    backend = _backend_tierlari()
    for uydurma in ("sinirsiz", "admin", "vip", "kurumsal"):
        assert uydurma not in backend, f"backend tanimsiz bir tier'i ({uydurma!r}) kabul ediyor — VALID_TIERS gevsemis"


def test_KRITIK_kuyruk_ayricaligi_SITEDE_VAAT_EDILMEDIGI_icin_kapali_kalir():
    """⚠️ OLGU DUZELTMESI (8. parti): "islem onceligi vaadinin KARSILIGI YOKTU" diye yazmistim;
    ölçünce yanlis cikti — karsiligi VAR: `ai_queue_gate` + `_ai_semaphore` gercek bir
    es-zamanlilik sinirlayicisidir ve `ai_router`a bagli. Dogru ifade: mekanizma VAR ama
    `PEMF_TIER_ENFORCED` KAPALI oldugu icin bugun HIC calismiyor; ustelik klinigin KENDI
    makinesindeki bir sinirlayici, "sunucuda sira" degil.

    Bu test iki seyi birden tutar:
      (a) bayrak varsayilan KAPALI kalir (acilirsa Pro kullanicilar habersizce yavaslar —
          site artik boyle bir sey vaat etmiyor, yani ACIKLANMAMIS bir kisitlama olurdu),
      (b) mekanizmanin kendisi SILINMEZ (ileride tekrar aciklanip acilabilir).
    """
    src = (_KOK / "servers" / "entitlement.py").read_text(encoding="utf-8", errors="replace")
    assert 'TIER_ENFORCED: bool = _flag("PEMF_TIER_ENFORCED", False)' in src, (
        "tier enforcement varsayilani ACIK olmus → site vaat etmediği hâlde Pro kullanicilar "
        "paylasimli kuyruga girer (aciklanmamis kisitlama)"
    )

    # ⚠️ METIN TARAMASI YETMEZ (M27 ilk turda KACTI): semafor DEGISKENI yeniden adlandirilinca
    # modul NameError ile patliyordu ama "_ai_semaphore" dizgisi baska satirlarda durdugu icin
    # test yesil kaliyordu. Gercek ice-aktarimla nesnenin VARLIGINI ve TURUNU olc.
    import asyncio
    import importlib

    ent = importlib.import_module("servers.entitlement")
    semafor = getattr(ent, "_ai_semaphore", None)
    assert isinstance(semafor, asyncio.Semaphore), (
        "kuyruk mekanizmasi (asyncio.Semaphore) yok ya da bozulmus — ileride aciklanip "
        f"acilamaz hâle gelir; bulunan: {type(semafor).__name__}"
    )
    assert callable(getattr(ent, "ai_queue_gate", None)), "ai_queue_gate kapisi kaybolmus"
