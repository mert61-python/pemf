# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Y51 (sahip, D1.61 devamı) — araştırma vekil modelinde toplam duty (`duty_sum`) EĞİTİM aralığı dışındaysa canlı E değeri
GÖSTERİLİR ama "eğitim aralığı dışı — güvenilmez" etiketi taşır. B aralığı denetimi (İG-5.83: dışarıdaysa E '—') AYNEN
kalır. Sürüş etkilenmez (araştırma hattı sürmez).

ÖLÇÜLEN KUSUR (DUZELTME-D1D §4 D1.61 Açık-1): vekil fantom modeli `duty_sum` ≈ 1,94–2,90 aralığında eğitildi; tipik seans
(5 bobin × %30 = 1,5) aralık DIŞINDA ama canlı E barı bunu hiç söylemeden sayı gösteriyordu.

GERÇEK: `efield_live.compute` + modelin `xai_ref_stats` referans örnekleminden okunan aralık (sütun 5). Sahte: yalnız vekil
tahmini (ağırlıklar bu yalıtılmış ortamda yok — sabit E döndürür). Arayüz fikstürü
`apps/ui/src/components/domain/__tests__/__fixtures__/efieldDuty.Y51.json` buradan üretilir (`Y51_FIKSTUR_YAZ=1`).
"""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parents[1]
_FIKSTUR = _KOK / "apps" / "ui" / "src" / "components" / "domain" / "__tests__" / "__fixtures__" / "efieldDuty.Y51.json"


class _SahteVekil:
    def predict(self, x, y, z, organ_id, achieved_B, duty_sum):
        return {"result_E_healthy": 0.021, "result_E_cancer": 0.055, "result_E_avg": 0.038}


@pytest.fixture
def ef(monkeypatch):
    from servers import efield_live

    efield_live.set_context([])
    efield_live.set_context([{"centroid_cabin_mm": [-43.6, 0.0, 0.0], "organ_id": 1}])
    assert efield_live.get_context() is not None, "aparat: baglam kurulamadi"
    monkeypatch.setattr(efield_live, "_predictor", lambda model=None: _SahteVekil())
    try:
        yield efield_live
    finally:
        efield_live.set_context([])


def _bobinler(n: int, duty: float, b_mt: float = 1.0) -> list[dict]:
    return [{"running": True, "magneticMt": b_mt, "dutyCycle": duty, "measuredFields": ["magneticMt"]}] * n


def test_KRITIK_tipik_seans_duty_1_5_E_GOSTERILIR_ve_GUVENILMEZ_etiketi_tasir(ef):
    v = ef.compute(_bobinler(5, 30))  # Σduty = 1,5
    assert v["dutySum"] == pytest.approx(1.5)
    assert v["cancer"] == pytest.approx(0.055) and v["healthy"] == pytest.approx(0.021), f"deger GIZLENDI: {v}"
    assert v.get("dutyEgitimAraligiDisi") is True, f"egitim araligi disi etiketi yok: {v}"
    alt, ust = ef.egitim_duty_araligi()
    assert v["dutyEgitimAraligi"] == [round(alt, 2), round(ust, 2)]
    assert not v.get("egitimAraligiDisi"), "B araligi icindeyken B bayragi kalkmamali"


def test_KARSIT_duty_egitim_araliginda_etiket_YOK(ef):
    v = ef.compute(_bobinler(7, 34))  # Σduty = 2,38 (fantom ≈ 1,94–2,90 içinde)
    assert v["cancer"] == pytest.approx(0.055)
    assert "dutyEgitimAraligiDisi" not in v, v


def test_KARSIT_B_araligi_disinda_E_YINE_gosterilmez_IG583_aynen(ef):
    v = ef.compute(_bobinler(5, 30, b_mt=2.0))
    assert v["cancer"] is None and v.get("egitimAraligiDisi") is True, f"IG-5.83 kurali bozuldu: {v}"


@pytest.mark.parametrize(
    "model, modul",
    [
        ("fantom", "ai_hub.inference_em_fantom.inference_em_fantom"),
        ("petri", "ai_hub.inference_em_petri.inference_em_petri"),
    ],
)
def test_KRITIK_duty_araligi_MODELIN_referans_orneklemiNDEN_okunur(model, modul):
    from servers import efield_live

    bg = importlib.import_module(modul).xai_ref_stats()["background"]
    assert efield_live.egitim_duty_araligi(model) == (
        pytest.approx(float(bg[:, 5].min())),
        pytest.approx(float(bg[:, 5].max())),
    )


def test_arayuz_fiksturu_GERCEK_compute_ile_AYNI(ef):
    disarida = {**ef.compute(_bobinler(5, 30)), "ts": 0}
    icerde = {**ef.compute(_bobinler(7, 34)), "ts": 0}
    metin = json.dumps({"disarida": disarida, "icerde": icerde}, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if os.environ.get("Y51_FIKSTUR_YAZ") == "1":
        _FIKSTUR.parent.mkdir(parents=True, exist_ok=True)
        _FIKSTUR.write_text(metin, encoding="utf-8")
    assert _FIKSTUR.exists(), "arayuz fiksturu yok (Y51_FIKSTUR_YAZ=1 ile uret)"
    assert json.loads(_FIKSTUR.read_text(encoding="utf-8")) == json.loads(metin), "arayuz fiksturu BAYAT"
