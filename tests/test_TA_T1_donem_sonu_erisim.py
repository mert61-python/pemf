# Author: mertaygn, cglrgrkn
"""TA T1 (Y292-1) · backend hak katmanı: iptal / ödeme gecikmesi = ÖDENMİŞ DÖNEM SONUNA KADAR erişim.

Önce: `servers/entitlement.py` `canceled` / `past_due` satırını görür görmez hakkı kesiyordu (`current_period_end` RPC'den
gelip hiç okunmuyordu) → iptal eden ödeyen kullanıcı dönem ortasında "Başlangıç"a düşüyordu; yayınlanan sözleşme ise dönem
sonuna dek erişim vaat ediyor. Sahte EN ALT katta: `requests.post` (Supabase RPC yanıtı) + `get_secret`; ayrıştırıcı GERÇEK.
Karşıt kollar: dönem bitti → yok · aktif → var · NULL → yok (bugünkü davranış).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from servers import entitlement as en


class _Yanit:
    def __init__(self, govde):
        self.status_code = 200
        self.ok = True
        self.content = b"x"
        self._g = govde

    def json(self):
        return self._g


@pytest.fixture
def satir(monkeypatch):
    import requests
    import utils.secrets_manager as sm

    durum: dict = {"satir": {}}
    sir = {"supabase_url": "https://ornek.supabase.co", "supabase_anon_key": "anon"}
    monkeypatch.setattr(sm, "get_secret", lambda ad, *a, **k: sir.get(ad))
    monkeypatch.setattr(requests, "post", lambda url, **k: _Yanit([durum["satir"]]))
    monkeypatch.setattr(en, "_entitlement_cache", {})
    return durum


def _iso(gun: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=gun)).isoformat()


@pytest.mark.parametrize("durum", ["canceled", "past_due", "cancelled", "unpaid", "paused"])
def test_KRITIK_iptal_ya_da_gecikmede_odenmis_donem_SURERKEN_hak_KORUNUR(satir, durum):
    satir["satir"] = {"tier": "pro_plus", "status": durum, "addons": ["research"], "current_period_end": _iso(3)}
    e = en._supabase_entitlement("jwt")
    assert (e.tier, e.addons, e.realtime, e.research) == ("pro_plus", ("research",), True, True), (
        f"{durum}: ödenmiş dönem sürerken hak kesildi"
    )


@pytest.mark.parametrize("durum", ["canceled", "past_due"])
def test_KRITIK_KARSIT_donem_BITTI_ya_da_NULL_ise_hak_KESILIR(satir, durum):
    for son in (_iso(-1), None, "", "yarin", "2026-13-45T99:00:00Z"):
        satir["satir"] = {"tier": "pro_plus", "status": durum, "addons": ["research"], "current_period_end": son}
        e = en._supabase_entitlement("jwt")
        assert (e.tier, e.addons) == ("baslangic", ()), f"{durum} · dönem sonu {son!r}: hak kesilmedi"
    satir["satir"] = {"tier": "pro", "status": durum, "addons": []}  # alan hiç gelmezse de kesilir
    assert en._supabase_entitlement("jwt").tier == "baslangic"


def test_KARSIT_aktif_abonelik_donem_sonu_gecmis_olsa_da_ERISIR(satir):
    # Yenileme bildirimi gecikmiş olabilir: `active` satır dönem sonuna bakılmadan aktiftir (bugünkü davranış).
    satir["satir"] = {"tier": "pro", "status": "active", "addons": [], "current_period_end": _iso(-30)}
    assert en._supabase_entitlement("jwt").tier == "pro"
    satir["satir"] = {"tier": "pro", "status": "trialing", "addons": [], "current_period_end": None}
    assert en._supabase_entitlement("jwt").tier == "pro"


SIMDI = datetime(2026, 11, 19, 12, 0, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("ham", "beklenen"),
    [
        ("2026-11-19T12:00:01+00:00", True),
        ("2026-11-19T12:00:00+00:00", False),  # tam sınırda: dönem BİTTİ
        ("2026-11-19T11:59:59+00:00", False),
        ("2026-11-19T12:00:00.123456+00:00", False),  # kesir atılır (saniye hassasiyeti)
        ("2026-11-19T12:00:01.12+00:00", True),  # 2 haneli kesir (3.10 fromisoformat tek başına reddeder)
        ("2026-11-19T12:00:01Z", True),
        ("2026-11-19T12:00:01z", True),
        ("2026-11-19 12:00:01+00", True),  # Postgres metin biçimi
        ("2026-11-19T15:00:01+03", True),  # +03 = 12:00:01 UTC
        ("2026-11-19T14:59:59+03:00", False),
        ("2026-11-19T12:00:01", True),  # saat dilimsiz → UTC
        ("2026-11-20", True),  # yalnız tarih → UTC gece yarısı
        ("2026-11-19", False),
        ("  2026-11-19T12:00:01+00:00  ", True),
        ("bozuk", False),
        (None, False),
        ("", False),
        (0, False),
    ],
)
def test_donem_suruyor_bicimler_ve_sinir(ham, beklenen):
    assert en._donem_suruyor(ham, SIMDI) is beklenen


def test_donem_suruyor_simdi_verilmezse_gercek_saat():
    assert en._donem_suruyor(_iso(1)) is True
    assert en._donem_suruyor(_iso(-1)) is False
