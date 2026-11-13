# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""ODK8 (sahip 13 Kasım 2026: "ai proları 3 frekansta daha yap 76 107 147 … ai pro kısmına frekans seçme de koy 76 100 107 147") —
AI Pro sürüş frekansı SEÇİLEBİLİR. Kalibrasyon (duty → genlik eğrisi, kazançlar) 100 Hz'de ÖLÇÜLDÜ; diğer frekanslarda duty → genlik,
kalibre RL modelinin (V, R, L, sönüm) tepe akımı oranıyla taşınır, dalga biçimi o frekansta. Her frekansın KENDİ ODAK modeli
(`model_<KIP>_<f>Hz`, kalibrasyon kimliği `…@<f>Hz` — başka frekansın modeli `modelEski` ile SÜRMEZ). Seçim öneri MÜHRÜNE yazılır,
`/start` karta mühürdeki frekansı gönderir, durdurma 100 Hz'e döndürür. Desteklenmeyen frekans 422 (TR + EN, eylem söyler).
EN ALT sahte: ODAK modeli (fizikle tutan) — alan tablosu, kalibrasyon, RL modeli, sürüş katı ve firmware aynası GERÇEK."""

from __future__ import annotations

import json
import os

import ai_pro_aparati as ap
import numpy as np
import pytest
from test_ODK_ai_pro_odak_entegrasyon import M2, P2, _DogruModel, _Hat, _hazirlik, _Sonuc, o  # noqa: F401 — aparat

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORNEK = os.path.join(KOK, "tests", "veri", "odak_kalibrasyon_ornek.json")


def _K():
    with open(ORNEK, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def AA():
    from ai_hub.odak.alan import AlanModeli

    return {f: AlanModeli(_K(), f_hz=f) for f in (76.0, 100.0, 147.0)}


def test_KRITIK_duty_GENLIK_frekansta_RL_tepe_ORANIYLA_tasinir(AA):
    from ai_hub.odak.alan import BIPOLAR, AlanModeli, rl_dalga_bicimi

    K = _K()
    rl = K["rl"]
    dg = AA[100.0].dg
    prm = (float(rl["V"]), float(rl["R_ohm"]), float(rl["L_mH"]))
    son = float(rl.get("sonum_kati", 1.0))
    for f in (76.0, 147.0):
        for c in (0, 5):  # bipolar bobin 1 · tek yönlü bobin 6
            bip = bool(BIPOLAR[c])
            _, t_f = rl_dalga_bicimi(dg, bip, *prm, f, son, n_kayit=1000, n_ince=1000, tepe_dondur=True)
            _, t_0 = rl_dalga_bicimi(dg, bip, *prm, 100.0, son, n_kayit=1000, n_ince=1000, tepe_dondur=True)
            sd = np.zeros(7)
            sd[c] = 0.5
            oran = AA[f].genlik(sd)[c] / AA[100.0].genlik(sd)[c]
            # ölçülen eğri × RL oranı, sonra kesin artan tutulur (eğrinin düz ucu × azalan oran → %0,1 içinde)
            assert oran == pytest.approx(t_f[-1] / t_0[-1], rel=5e-3), (f, c)
        assert np.all(np.diff(AA[f].a_tab, axis=1) > 0), "duty → genlik kesin artan değil (ters çevrilemez)"
    s = np.full(7, 0.5)
    assert np.all(AA[76.0].genlik(s) > AA[100.0].genlik(s)) and np.all(AA[147.0].genlik(s) < AA[100.0].genlik(s))
    # 100 Hz açıkça verilince eskisiyle BİREBİR (kimlik + eğri)
    A0 = AlanModeli(K)
    assert A0.kimlik == AA[100.0].kimlik and np.array_equal(A0.a_tab, AA[100.0].a_tab) and A0.f_hz == 100.0


def test_KRITIK_kimlik_FREKANSI_tasir_ve_dalga_O_frekansta(AA):
    from ai_hub.odak.alan import kalibrasyon_kimligi

    base = kalibrasyon_kimligi(_K())
    assert AA[100.0].kimlik == base and AA[147.0].kimlik == f"{base}@147Hz" and AA[76.0].kimlik == f"{base}@76Hz"
    assert AA[147.0].f_hz == 147.0 and AA[147.0].f_cal == 100.0
    # duty → genlik dönüşümü frekansın azami genliğine kırpılır (76 Hz'de > 1 kullanılabilir, 147 Hz'de < 1'de doyar)
    assert np.allclose(AA[76.0].duty(AA[76.0].a_azami), 0.5) and AA[76.0].a_azami.min() > 1.0
    assert np.allclose(AA[147.0].duty(np.ones(7)), 0.5) and AA[147.0].a_azami.max() < 1.0
    assert np.allclose(AA[100.0].a_azami, 1.0, atol=1e-3)


def test_KRITIK_model_DOSYASI_frekansla_ve_YANLIS_frekans_modeli_SURMEZ(AA, tmp_path):
    from test_ODK_odak_alan_ve_oneri import _kucuk_onnx

    from ai_hub.odak import oneri
    from ai_hub.odak.model import OdakModeli, model_koku

    assert model_koku("FANTOM") == "model_FANTOM" == model_koku("FANTOM", 100.0)
    assert model_koku("FANTOM", 147.0) == "model_FANTOM_147Hz" and model_koku("KEDI_TV", 76) == "model_KEDI_TV_76Hz"
    d147 = tmp_path / "f147"
    d147.mkdir()
    _kucuk_onnx(str(d147), "FANTOM", kimlik=AA[147.0].kimlik)
    for ek in (".onnx", ".json"):
        os.replace(d147 / f"model_FANTOM{ek}", d147 / f"model_FANTOM_147Hz{ek}")
    assert OdakModeli("FANTOM", str(d147), 147.0).kalibrasyon_kimligi.endswith("@147Hz")
    with pytest.raises(FileNotFoundError):
        OdakModeli("FANTOM", str(d147), 100.0)  # 100 Hz dosyası yok → başka frekansın modeli KULLANILMAZ
    # 100 Hz modeli 147 Hz alanıyla → modelEski (SÜRMEZ)
    T = [20.0, -155.0, 10.0]
    fan = {"merkez_P": [0.0, -150.0, 0.0], "theta": 0.4}
    p = oneri.oner("FANTOM", AA[147.0], 0.4, model=_DogruModel(AA[100.0], [T]), hedef_P=T, fantom=fan)
    assert p["engel"] == "modelEski" and p["frek_hz"] == 147.0
    p = oneri.oner("FANTOM", AA[147.0], 0.4, model=_DogruModel(AA[147.0], [T]), hedef_P=T, fantom=fan)
    assert p["engel"] is None and p["frek_hz"] == 147.0 and p["beklenen_mT"] == pytest.approx(0.4, rel=0.02)


def _frekansli_model(o, monkeypatch):
    from ai_hub.odak import oneri

    def al(kip, dizin=None, f_hz=None):
        return _DogruModel(oneri.alan_modeli(o.kok, f_hz), [M2])

    monkeypatch.setattr(oneri, "model_al", al)


def test_KRITIK_ONERI_147_Hz_MUHURE_SURUS_karta_147_DURDURMA_100(o, monkeypatch):
    from kayitci_donanim import paket_coz
    from servers import ai_approval

    _frekansli_model(o, monkeypatch)
    _hazirlik(o)
    r = o.c.post(
        "/api/ai/pro/propose",
        json={"organ_id": 0, "duration_minutes": 5, "model": "fantom", "doz_mT": 0.4, "frek_hz": 147},
    )
    assert r.status_code == 200, r.text[:300]
    od = r.json()["specs"]["odak"]
    assert (
        od["frek_hz"] == 147.0
        and od["kalibrasyon"].endswith("@147Hz")
        and od["beklenen_mT"] == pytest.approx(0.4, rel=0.02)
    )
    ai_approval.approve(r.json()["proposalId"], "arastirmaci@test.local")
    once = len(o.hc.core._hw_send_queue.paketler)
    s = o.c.post("/api/ai/pro/start", json={"proposal_id": r.json()["proposalId"]})
    assert s.status_code == 200, s.text[:300]
    assert o.tekil.odak_ayari["frek_hz"] == 147.0 and o.air._ai_pro_frek_hz == 147.0
    _Hat.sonuc = _Sonuc([(P2, M2, 300)])
    j = ap.kare(o).json()
    assert j.get("driven") is True, j
    paketler = o.hc.core._hw_send_queue.paketler[once:]
    assert paketler, "aparat: sürüş paketi yok"
    _d, _f, freq, *_ = paket_coz(paketler[-1])  # firmware aynası KABUL eder
    surulen = [round(float(x), 3) for x, d in zip(freq[:7], _d[:7]) if float(d) > 0]
    assert surulen and all(x == 147.0 for x in surulen), freq
    o.c.post("/api/ai/pro/stop")
    assert o.air._ai_pro_frek_hz == 100.0, "durdurmadan sonra sürüş frekansı 100'e dönmedi"


def test_KARSIT_frekans_VERILMEZSE_100_Hz_ESKI_davranis(o):
    _hazirlik(o)
    r = o.c.post("/api/ai/pro/propose", json={"organ_id": 0, "duration_minutes": 5, "model": "fantom", "doz_mT": 0.4})
    assert r.status_code == 200, r.text[:300]
    od = r.json()["specs"]["odak"]
    assert od["frek_hz"] == 100.0 and "@" not in od["kalibrasyon"]


@pytest.mark.parametrize("dil,parca", [("tr", "desteklenmiyor"), ("en", "not supported")])
def test_KRITIK_DESTEKLENMEYEN_frekans_422_EYLEM_iki_dilde(o, dil, parca):
    _hazirlik(o)
    r = o.c.post(
        "/api/ai/pro/propose",
        json={"organ_id": 0, "duration_minutes": 5, "model": "fantom", "doz_mT": 0.4, "frek_hz": 120},
        headers={"X-PEMF-Dil": dil},
    )
    assert r.status_code == 422, r.text[:300]
    d = r.json()["detail"]
    assert parca in d and "120" in d and "76, 100, 107, 147" in d, d


@pytest.mark.parametrize("f", [76.0, 107.0, 147.0])
def test_YAPISAL_FREKANS_MODELLERI_o_frekansin_kimligiyle_ve_AI_MODEL_KATMANINDA(f):
    """Her kip için `model_<KIP>_<f>Hz` var, o frekansın kalibrasyon kimliğiyle eğitilmiş, ONNX AI model katmanında (Y282), üst veri depoda."""
    from ai_hub.odak.alan import VERI_DIZINI, AlanModeli, model_katmani_yolu
    from ai_hub.odak.model import KIPLER, model_al, model_koku

    kim = AlanModeli(_K(), f_hz=f).kimlik
    for kip in KIPLER:
        kok = model_koku(kip, f)
        assert os.path.isfile(os.path.join(VERI_DIZINI, f"{kok}.json")), kok
        assert not os.path.exists(os.path.join(VERI_DIZINI, f"{kok}.onnx")), f"{kok}: ONNX depoda (Y282)"
        assert os.path.isfile(model_katmani_yolu(f"{kok}.onnx"))
        m = model_al(kip, f_hz=f)
        assert m.kalibrasyon_kimligi == kim, f"{kok}: başka frekans / kalibrasyonla eğitilmiş"
        assert "doz_mT" in m.ozellik_ad
