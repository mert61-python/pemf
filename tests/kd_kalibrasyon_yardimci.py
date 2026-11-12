# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KD · Y259 test yardımcısı — araştırma (petri / fantom) AI Pro önerisi / başlatması / sürüşü artık GEÇERLİ sabit düzlem kalibrasyonu
ister (`ai_router._duzlem_kalibrasyonu_kapisi` → `ai_pro_hedef.duzlem_surus_engeli`). KD öncesi yazılmış kapı testleri (bayrak, mühür,
koşulsuz kip, otomatik hedef …) BAŞKA bir kuralı ölçer; kalibrasyon ön koşulunu bu aparatla "sağlanmış" kabul eder. Kalibrasyon
kapısının kendisi `test_KD_kalibrasyon_uclari_ve_surus_kapisi.py`'de (yokluk / bozukluk / kamera farkı / fantom ayarı → 409).

ODAK (istem 45): araştırma sürüşünün faz / duty'si artık ODAK planından (`ai_pro_hedef.odak_plani`: alan kalibrasyonu + KNN + fizik
denetimi). ODAK öncesi kapı testlerinin konusu HEDEF SEÇİMİ / MÜHÜR / BAYRAK — doz modeli değil; onların "doz kanıtı" ya yönlendiricinin
SAHTELENMİŞ `_predict_and_drive`'ı ya da sağlayıcının sahte `predictor.predict`'idir (çağrıldığı koordinat = sürülen hedef). Bu aparat
ODAK planını o sahteye bağlar → eski testlerin kanıtı AYNEN geçerli. ODAK'ın kendisi (gerçek alan tablosu, kalibrasyon kapısı, fizik
denetimi, engel → 409, mühür → döngü) `test_ODK_*` dosyalarında, bu aparat OLMADAN.

Kullanım (modül düzeyinde): `from kd_kalibrasyon_yardimci import kd_gecerli_kalibrasyon  # noqa: F401` (düzlem kapısı + ODAK sahtesi) ya da
yalnız ODAK sahtesi: `from kd_kalibrasyon_yardimci import odak_tahminci  # noqa: F401` (düzlem kapısını kendisi ölçen dosyalar).
⚠️ `monkeypatch` İSTEMEZ (hafıza: autouse fikstürü monkeypatch isterse yıkım sırası nöbet fikstürlerini bozar) — elle kaydet / geri yükle.
"""

from __future__ import annotations

import pytest


def _odak_plani_tahminciden(saglayici, konum, hedef_id, doz_mT, istenen_kip=""):
    """ODAK planı yerine testin doz sahtesi: yönlendiricinin SAHTELENMİŞ `_predict_and_drive`'ı varsa o; yoksa sağlayıcının sahte
    `predictor.predict`'i; ikisi de yoksa her bobin 0,3 (kapı testleri dozun DEĞERİNE bakmaz)."""
    from servers import ai_pro_hedef
    from servers import ai_router as air

    x, y, z = konum["x_mm"], konum["y_mm"], konum["z_mm"]
    pd = air._predict_and_drive
    if getattr(saglayici, "ad", "") == "kedi":
        # ODK5: kedi önerisi de ODAK'tan — eski kedi testlerinin doz kanıtı yönlendiricinin (sahte ya da gerçek) `_predict_and_drive`'ı.
        D, P, _ = air._predict_and_drive(x, y, z, hedef_id)
    elif not (
        getattr(pd, "__module__", "") == "servers.ai_router" and getattr(pd, "__qualname__", "") == "_predict_and_drive"
    ):
        D, P, _ = air._predict_and_drive(x, y, z, hedef_id)
    else:
        try:
            cache = saglayici._onbellek()
            with saglayici._kilit:
                sinif = int(saglayici._meta.get("secili_organ_id", 1))
            out = cache["predictor"].predict(
                x=x, y=y, z=z, organ_id=sinif, achieved_B=saglayici.achieved_B, duty_sum=saglayici.duty_sum
            )
            D = [float(out.get(f"D{i}", 0.0)) for i in range(1, 8)]
            P = [float(out.get(f"P{i}", 0.0)) for i in range(1, 8)]
        except (AttributeError, KeyError):
            D, P = [0.3] * 7, [0.0] * 7
    return {
        "kip": ai_pro_hedef.odak_kipi(saglayici, hedef_id, istenen_kip),
        "doz_mT": 1.0 if doz_mT is None else float(doz_mT),
        "duty": [float(d) for d in D],
        "faz": [float(p) for p in P],
        "engel": None,
        "engel_ek": {},
    }


def _odak_sahtesi_kur():
    from servers import ai_pro_hedef

    eski = ai_pro_hedef.odak_plani
    ai_pro_hedef.odak_plani = _odak_plani_tahminciden
    return eski


@pytest.fixture(autouse=True)
def kd_gecerli_kalibrasyon():
    from servers import ai_pro_hedef

    eski = ai_pro_hedef.duzlem_surus_engeli
    ai_pro_hedef.duzlem_surus_engeli = lambda _saglayici: None
    eski_odak = _odak_sahtesi_kur()
    try:
        yield
    finally:
        ai_pro_hedef.duzlem_surus_engeli = eski
        ai_pro_hedef.odak_plani = eski_odak


@pytest.fixture(autouse=True)
def odak_tahminci():
    """Yalnız ODAK sahtesi (düzlem kalibrasyon kapısı GERÇEK kalır)."""
    from servers import ai_pro_hedef

    eski_odak = _odak_sahtesi_kur()
    try:
        yield
    finally:
        ai_pro_hedef.odak_plani = eski_odak
