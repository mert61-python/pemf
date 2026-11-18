# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""ODD B-3 (ODK-B keşfi 18-11, kum havuzu 13b) — `/ai/pro/propose` "konum ESKİ" ile "BULUNAMADI"yı AYIRIR.

ÖLÇÜLEN: onay penceresi açılınca önizleme durup kamera bırakılıyor → lokalizasyon yaşlanıyor; 120 sn'den eski önbellekle yeniden hesap
409 `konumlandirilmadi` + ipucu dönüyordu: "Kuyu (otomatik) henüz konumlandırılmadı. Kuyu (otomatik) seçilemedi — hedefi tepsinin ortasına
alın…" — asıl neden (ölçüm 2 dk'dan eski) SONDA (yalnız istemci saatiyle eklenen cümlede), ad seçilen kuyu değil "otomatik".
SÖZLEŞME: önbellek aynı hedef / model için lokalize ama 120 sn'den eskiyse → 409 `ai.pro.hata.konumBayat`: asıl neden BAŞTA, seçilen
kuyunun (haritadan seçildiyse o, değilse önizlemenin seçtiği) adıyla, eylem "Konumu tazele ve yeniden hesapla". Lokalize değilse /
başka hedef / başka model → eski `konumlandirilmadi` AYNEN. TR + EN. Düzen `test_AP_B3_…` ile aynı (ODAK planı sahte).
"""

import time

import pytest
from fastapi.testclient import TestClient

C2 = {"id": 7, "label": "Kuyu C2", "x": 10.0, "y": -150.0, "z": 20.0, "reliability": 0.95, "pxn": [0.3, 0.5]}
C6 = {"id": 11, "label": "Kuyu C6", "x": 60.0, "y": -150.0, "z": 25.0, "reliability": 0.9, "pxn": [0.6, 0.5]}


@pytest.fixture()
def o(monkeypatch):
    import servers.ai_pro_hedef as hedef
    import servers.ai_router as air
    import servers.api_server as apis

    monkeypatch.setenv("PEMF_ARASTIRMA_AIPRO", "1")
    monkeypatch.setattr(hedef, "duzlem_surus_engeli", lambda _s: None)
    monkeypatch.setattr(
        hedef,
        "odak_plani",
        lambda *a, **k: {
            "kip": "KUYUCUK",
            "doz_mT": 0.6,
            "tavan_mT": 1.2,
            "duty": [0.2] * 7,
            "faz": [0.0] * 7,
            "frek_hz": 100.0,
        },
    )
    snap = dict(air._ai_organ_cache)

    def _kur(yas_s: float, **ek):
        air._ai_organ_cache.update(
            {
                "localized": True,
                "organ_id": 0,
                "model": "petri",
                "at": time.time() - yas_s,
                "x_mm": C2["x"],
                "y_mm": C2["y"],
                "z_mm": C2["z"],
                "reliability": 0.95,
                "kosulsuz": False,
                "targets": [C2, C6],
                "secili_id": 7,
                "target_label": "Kuyu C2",
                **ek,
            }
        )

    yield TestClient(apis.app), _kur
    air._ai_organ_cache.clear()
    air._ai_organ_cache.update(snap)


def _oner(c, dil="tr", **ek):
    return c.post(
        "/api/ai/pro/propose",
        json={"organ_id": 0, "model": "petri", "duration_minutes": 5, **ek},
        headers={"X-PEMF-Dil": dil},
    )


def test_KRITIK_B3_ESKI_konum_HARITADAN_secilen_kuyunun_adiyla_neden_BASTA(o):
    c, kur = o
    kur(130.0)
    r = _oner(c, kuyu="C6", odak_kip="KUYUCUK", doz_mT=0.6)
    assert r.status_code == 409, r.text
    d = r.json()["detail"]
    assert d.startswith("Kuyu C6 için konum ölçümü eski (2 dakikadan önce)"), d
    assert "Konumu tazele ve yeniden hesapla" in d and "otomatik" not in d and "henüz konumlandırılmadı" not in d, d


def test_KRITIK_B3_ESKI_konum_otomatik_oneride_ONIZLEMENIN_sectigi_kuyu(o):
    c, kur = o
    kur(125.0)
    d = _oner(c, doz_mT=0.5).json()["detail"]
    assert d.startswith("Kuyu C2 için konum ölçümü eski"), d


def test_KRITIK_B3_ESKI_konum_INGILIZCE(o):
    c, kur = o
    kur(130.0)
    d = _oner(c, dil="en", kuyu="C6").json()["detail"]
    assert d.startswith("The position measurement for Well C6 is out of date (taken more than 2 minutes ago)"), d
    assert "Refresh position and recalculate" in d, d


@pytest.mark.parametrize(
    "ek",
    [
        {"localized": False},  # bulunamadı
        {"organ_id": 5},  # başka hedef
        {"model": "fantom"},  # başka model
    ],
    ids=["lokalize_degil", "baska_hedef", "baska_model"],
)
def test_KARSIT_B3_BULUNAMADI_ya_da_baska_hedef_ESKI_konumlandirilmadi_AYNEN(o, ek):
    c, kur = o
    kur(130.0, **ek)
    d = _oner(c).json()["detail"]
    assert "henüz konumlandırılmadı" in d and "konum ölçümü eski" not in d, d


def test_KARSIT_B3_TAZE_konum_oneri_VERILIR(o):
    c, kur = o
    kur(5.0)
    assert _oner(c, kuyu="C6").status_code == 200


def test_B3_ESKI_konum_etiketsiz_onizleme_HEDEF_ADI_ve_KEDI_organ_adi(o):
    from servers import ai_pro_hedef

    c, kur = o
    kur(130.0, target_label="")
    d = _oner(c).json()["detail"]
    assert d.startswith("Kuyu (otomatik) için konum ölçümü eski"), d
    kur(130.0, organ_id=2, model="kedi", target_label="")
    r = c.post(
        "/api/ai/pro/propose",
        json={"organ_id": 2, "model": "kedi", "duration_minutes": 5},
        headers={"X-PEMF-Dil": "tr"},
    )
    ad = ai_pro_hedef.hedef_gosterim_adi(ai_pro_hedef.saglayici_al("kedi"), 2)
    assert r.status_code == 409 and r.json()["detail"].startswith(f"{ad} için konum ölçümü eski"), r.text[:300]
