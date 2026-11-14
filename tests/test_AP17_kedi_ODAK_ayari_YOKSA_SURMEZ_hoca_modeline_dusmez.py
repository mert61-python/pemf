# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AP-17 (istem 48 · sahip 14 Kasım): kedi AI Pro sağlayıcısı mühürde ODAK ayarı YOKSA bobin SÜRMEZ (fail-closed, duty 0) — hocanın
`em_kedi` doz modeline (GPU servisi ya da CPU-yerel) DÜŞMEZ. Araştırma sağlayıcılarıyla (petri / fantom) AYNI kural: sürüş kaynağı
yalnız ODAK (CST alan tablosu). Bugün Y142 kedi sürüşünü kapalı tuttuğu için yol ulaşılamaz; bayrak açılmadan ÖNCE kapanır.
EN ALT sahte: hoca doz fonksiyonları (`_predict_and_drive_gpu` / `_cpu`) — çağrılırsa SAYILIR ve sıfır olmayan doz döner (sahte yeşil yok)."""

from __future__ import annotations

import pytest

HOCA_DOZU = ([0.4] * 7, [90.0] * 7, 1.0)


@pytest.fixture
def hoca(monkeypatch):
    from servers import ai_router as air

    cagri: list[str] = []
    monkeypatch.setattr(air, "_predict_and_drive_gpu", lambda *a: cagri.append("gpu") or HOCA_DOZU)
    monkeypatch.setattr(air, "_predict_and_drive_cpu", lambda *a: cagri.append("cpu") or HOCA_DOZU)
    return cagri


@pytest.mark.parametrize("gpu_servisi", [True, False])
def test_KRITIK_kedi_ODAK_ayari_YOKSA_sifir_doz_ve_hoca_modeli_CAGRILMAZ(monkeypatch, hoca, gpu_servisi):
    """MUTASYON: `predict`te ODAK'sız kolu eski delegasyona (`_predict_and_drive_gpu` / `_cpu`) geri çevirin → KIRMIZI."""
    from servers import ai_pro_hedef as hedef
    from servers import ai_router as air

    monkeypatch.setattr(air, "ai_service_enabled", lambda: gpu_servisi)
    sag = hedef.KediSaglayici()
    hedef.odak_ayarla(sag, None)
    assert sag.odak_ayari is None
    D, P, E = sag.predict(10.0, -150.0, 5.0, 2)
    assert hoca == [], f"ODAK'sız kedi seansı hocanın em_kedi modeline düştü ({hoca})"
    assert (list(D), list(P), E) == ([0.0] * 7, [0.0] * 7, 0.0)


def test_KRITIK_dozu_ODAK_olmayan_muhur_ODAK_sayilmaz_SURMEZ(monkeypatch, hoca):
    """Eski / ODAK'sız mühür (`odak` yok ya da `doz_mT` yok) → ayar temizlenir → döngünün zarfı (`_predict_and_drive`) sıfır döner
    (döngü sıfırı "doz yok" sayar, bobin sürülmez). MUTASYON: `odak_ayarla`da `doz_mT is None` denetimini kaldırın ya da kedi
    `predict`ini hoca yoluna çevirin → KIRMIZI."""
    from servers import ai_pro_hedef as hedef
    from servers import ai_router as air

    monkeypatch.setattr(air, "ai_service_enabled", lambda: False)
    sag = hedef.KediSaglayici()
    monkeypatch.setattr(air._ai_hedef_yerel, "saglayici", sag, raising=False)
    for muhur_odak in (None, {}, {"kip": "KEDI_TV"}):
        hedef.odak_ayarla(sag, muhur_odak, "Tüm Vücut")
        assert sag.odak_ayari is None
        assert air._predict_and_drive(10.0, -150.0, 5.0, 0) == ([0.0] * 7, [0.0] * 7, 0.0)
    assert hoca == []


def test_ODAK_ayari_VARSA_surus_ODAKtan_hoca_yine_CAGRILMAZ(monkeypatch, hoca):
    """Karşıt kanıt: ayar varsa sürüş ODAK planından (sıfırlama her şeyi kapatmadı)."""
    from servers import ai_pro_hedef as hedef

    plan = {"engel": None, "duty": [0.1, 0.2, 0.0, 0.0, 0.3, 0.0, 0.25], "faz": [0.0, 36.0, 0.0, 0.0, 180.0, 0.0, 18.0]}
    monkeypatch.setattr(hedef, "odak_plani", lambda *a, **k: dict(plan))
    sag = hedef.KediSaglayici()
    hedef.odak_ayarla(sag, {"doz_mT": 0.4, "kip": "KEDI_TV"}, "Tüm Vücut")
    D, P, _ = sag.predict(0.0, 0.0, 0.0, 0)
    assert (list(D), list(P)) == (plan["duty"], plan["faz"]) and hoca == []
