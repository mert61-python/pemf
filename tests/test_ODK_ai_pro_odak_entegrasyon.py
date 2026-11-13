# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""ODK (istem 45) — AI Pro araştırma sürüşü ODAK'a bağlı: `/propose` faz / duty'yi ODAK planından alır (doz kullanıcıdan, fizik denetimi
engellerse eylem söyleyen 409), mühüre `odak` yazılır, `/start` döngüye mühürdeki doz / kip / hedefi verir, döngünün `predict`i aynı
dozla yeniden hesaplar (engel → SIFIR), durdurma ayarı temizler. Hoca modeli SÜRÜŞ KAYNAĞI DEĞİL.
EN ALT sahte: ODAK modeli (`ai_hub.odak.oneri.model_al` → fizikle TAM tutan sahte); alan tablosu + kalibrasyon GERÇEK (örnek dosya,
geçici veri kökünde). Bu dosya `kd_kalibrasyon_yardimci`'yı KULLANMAZ (ODAK sahtesi yok) — düzlem kapısı burada elle "geçti" yapılır.
"""

from __future__ import annotations

import json
import os
import shutil

import ai_pro_aparati as ap
import numpy as np
import pytest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORNEK = os.path.join(KOK, "tests", "veri", "odak_kalibrasyon_ornek.json")
P2, M2 = (200.0, 100.0), (-40.0, -140.0, 0.0)


class _Bolge:
    def __init__(self, px, mm, alan, r=10):
        self.centroid_px, self.centroid_cabin_mm = px, mm
        self.organ_id, self.area_px, self.bbox_px = 1, alan, (px[0] - r, px[1] - r, 2 * r, 2 * r)
        self.E_cancer, self.E_healthy, self.tumor_id = 0.9, 0.1, ""


class _Sonuc:
    def __init__(self, bolgeler):
        self.success, self.error, self.method, self.mm_per_px = True, None, "aruco_pnp", 0.0
        self.pemf_valid, self.reliable, self.warnings = True, True, []
        self.pemf_source, self.coord_frame, self.layout = "aruco", "cabin_aruco", {}
        self.tumor_regions = [_Bolge(p, m, a) for p, m, a in bolgeler]
        self.phantom_detection = {"primary": {"solidity": 0.9, "n_blue_inside": 5}}


class _Hat:
    sonuc = None

    def __init__(self, cfg, **kw):
        self.cfg, self._predictor, self.yolo = cfg, None, None

    def process_image(self, frame, achieved_B=None, duty_sum=None):
        return _Hat.sonuc, {}

    def render_panels(self, ctx, result, lang="tr"):
        return {"07_combined": None}


class _Cfg:
    class phantom:  # noqa: N801
        achieved_B, duty_sum = 0.001, 2.4


class _Hoca:
    """Hocanın EM modeli — ODAK'ta SÜRÜŞ yolunda ÇAĞRILMAMALI."""

    def __init__(self):
        self.cagri = 0

    def predict(self, **k):
        self.cagri += 1
        return {**{f"D{i}": 0.45 for i in range(1, 8)}, **{f"P{i}": 0.0 for i in range(1, 8)}}


class _DogruModel:
    """Fizikle TAM tutan sahte ODAK modeli (tavan köşesi yönünde, istenen dozu zaman domeninde veren genlik)."""

    ozellik_ad = ["doz_mT"]

    def __init__(self, A, P_hedef_b):
        from ai_hub.odak.alan import ISARETLER

        self.A, self.MT = A, A.alan(np.asarray(P_hedef_b, float).reshape(-1, 3))
        B = np.linalg.norm(np.einsum("tij,vj->vti", self.MT, ISARETLER), axis=2).min(axis=1)
        self.u = ISARETLER[int(np.argmax(B))]
        self.kalibrasyon_kimligi = A.kimlik
        self.cagri = 0

    def ozellik(self, oz, M, doz_mT):
        return np.array([[doz_mT]])

    def tahmin(self, X):
        self.cagri += 1
        D = float(X[0, 0])
        lo, hi = 0.0, 1.0
        for _ in range(40):
            k = (lo + hi) / 2
            if self.A.td_tepe(self.MT, self.A.isaretli_duty(self.u * k)).min() < D:
                lo = k
            else:
                hi = k
        return (self.u * hi / D)[None, :]


def _kok_kur(kok):
    d = os.path.join(kok, "kabin_kalibrasyonu")
    os.makedirs(d, exist_ok=True)
    shutil.copyfile(ORNEK, os.path.join(d, "alan_kalibrasyonu.json"))
    return kok


@pytest.fixture
def o(monkeypatch, tmp_path):
    import servers.ai_pro_hedef as hedef
    from kayitci_donanim import gercek_hc
    from servers import ai_router as air0

    from ai_hub.odak import oneri

    asil_pd = (
        air0._predict_and_drive
    )  # aparat üst kat doz sahtesini kurar → GERÇEK zarf geri (EN ALT sahte: ODAK modeli)
    ns = ap.kur(monkeypatch, tmp_path)
    monkeypatch.setattr(ns.air, "_predict_and_drive", asil_pd)
    monkeypatch.setattr(ns.air, "_localize_organ", lambda f, oid: hedef.SAGLAYICILAR["fantom"].localize(f, oid))
    ns.hoca = _Hoca()
    cache = {"cls": _Hat, "cfg": _Cfg(), "predictor": ns.hoca, "yolo": None, "yolo_path": "y.onnx"}
    monkeypatch.setattr(ns.air, "_get_or_load_model", lambda ad, y: cache)
    monkeypatch.setattr(ns.air, "_ORGAN_LOCALIZE_INTERVAL_S", 0.0)
    monkeypatch.setenv("PEMF_ARASTIRMA_AIPRO", "1")
    monkeypatch.setenv("PEMF_ARASTIRMA_AIPRO_FANTOM", "1")
    monkeypatch.setattr(hedef, "duzlem_surus_engeli", lambda _s: None)  # düzlem kapısı bu dosyanın konusu değil
    monkeypatch.setattr(
        hedef, "FANTOM_ODAK_ERTELENDI", False
    )  # Y283 kapısı ayrı testte (test_ODK9_*); burada ODAK makinesi sınanır
    ns.kok = _kok_kur(str(tmp_path / "veri_koku"))
    monkeypatch.setattr(hedef, "duzlem_veri_koku", lambda: ns.kok)
    A = oneri.alan_modeli(ns.kok)
    ns.A = A
    ns.model = _DogruModel(A, [M2])
    monkeypatch.setattr(oneri, "model_al", lambda kip, **_k: ns.model)
    tekil = hedef.SAGLAYICILAR["fantom"]
    snap = {
        a: (list(v) if isinstance(v, list) else dict(v) if isinstance(v, dict) else v) for a, v in vars(tekil).items()
    }
    for a, v in vars(hedef.FantomSaglayici()).items():
        setattr(tekil, a, v)
    monkeypatch.setattr(ns.air, "_ai_hedef_modeli", "fantom")
    monkeypatch.setattr(ns.air, "_ai_organ_id", 0)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            ns.tekil = tekil
            yield ns
    finally:
        ns.c.post("/api/ai/pro/stop")
        ns.hc.stop_all_coils()
        ns.geri()
        for a in [a for a in vars(tekil) if a not in snap]:
            delattr(tekil, a)
        for a, v in snap.items():
            setattr(tekil, a, v)


def _hazirlik(o):
    _Hat.sonuc = _Sonuc([(P2, M2, 300)])
    o.air._ai_relocalize = True
    j = ap.kare(o).json()
    assert j.get("detected") is True, j


def _oner(o, **ek):
    return o.c.post("/api/ai/pro/propose", json={"organ_id": 0, "duration_minutes": 5, "model": "fantom", **ek})


def test_KRITIK_ODAK_oneri_faz_duty_ODAK_planindan_ve_MUHURE_yazilir(o):
    _hazirlik(o)
    r = _oner(o, doz_mT=0.5)
    assert r.status_code == 200, r.text[:300]
    sp, me = r.json()["specs"], r.json()["meta"]
    od = sp["odak"]
    assert (
        od["kip"] == "FANTOM"
        and od["doz_mT"] == pytest.approx(0.5)
        and od["beklenen_mT"] == pytest.approx(0.5, rel=0.02)
    )
    assert (
        od["tavan_mT"] > 0.5
        and od["cevre_mT"] > 0
        and od["oran"] > 0
        and "pay_yuzde" in od
        and od["kalibrasyon"] == o.A.kimlik
    )
    assert max(sp["D"]) <= 0.5 and any(d > 0 for d in sp["D"]) and sp["e_field"] == 0.0
    assert o.hoca.cagri == 0, "hocanın EM modeli öneri yolunda çağrıldı"
    assert "xaiSensitivity" not in me, "ODAK önerisinde hoca XAI'si gösterildi"


def test_KRITIK_ODAK_doz_VERILMEZSE_tavanin_yuzde_80i(o):
    _hazirlik(o)
    r = _oner(o)
    assert r.status_code == 200, r.text[:300]
    od = r.json()["specs"]["odak"]
    assert od["doz_mT"] == pytest.approx(round(0.8 * od["tavan_mT"], 2), abs=0.011)


@pytest.mark.parametrize("dil,parca", [("tr", "en çok"), ("en", "At most")])
def test_KRITIK_ODAK_doz_TAVAN_USTU_409_eylem_soyler_IKI_DILDE(o, dil, parca):
    _hazirlik(o)
    r = o.c.post(
        "/api/ai/pro/propose",
        json={"organ_id": 0, "duration_minutes": 5, "model": "fantom", "doz_mT": 99.0},
        headers={"X-PEMF-Dil": dil},
    )
    assert r.status_code == 409 and parca in r.json()["detail"], r.text[:300]


def test_KRITIK_ODAK_kalibrasyon_YOKSA_oneri_409(o):
    _hazirlik(o)
    os.remove(os.path.join(o.kok, "kabin_kalibrasyonu", "alan_kalibrasyonu.json"))
    r = _oner(o, doz_mT=0.5)
    assert r.status_code == 409 and "kalibrasyonu yok" in r.json()["detail"], r.text[:300]


def test_KRITIK_ODAK_MUHUR_doz_kip_DONGUYE_gecer_SURER_durdurma_TEMIZLER(o):
    from servers import ai_approval

    _hazirlik(o)
    pid = _oner(o, doz_mT=0.4).json()["proposalId"]
    ai_approval.approve(pid, "arastirmaci@test.local")
    s = o.c.post("/api/ai/pro/start", json={"proposal_id": pid})
    assert s.status_code == 200, s.text[:300]
    assert o.tekil.odak_ayari == {"doz_mT": 0.4, "kip": "FANTOM", "hedef_etiket": "Tümör 1", "frek_hz": 100.0}
    once = o.model.cagri
    _Hat.sonuc = _Sonuc([(P2, M2, 300)])
    j = ap.kare(o).json()
    assert j.get("driven") is True and o.model.cagri > once, j
    assert o.hoca.cagri == 0
    o.c.post("/api/ai/pro/stop")
    assert o.tekil.odak_ayari is None


def test_KRITIK_ODAK_seansta_kalibrasyon_KAYBOLURSA_predict_SIFIR(o):
    o.tekil.odak_ayari = {"doz_mT": 0.4, "kip": "FANTOM", "hedef_etiket": ""}
    D, P, e = o.tekil.predict(*M2, 1)
    assert any(d > 0 for d in D) and e == 0.0
    os.remove(os.path.join(o.kok, "kabin_kalibrasyonu", "alan_kalibrasyonu.json"))
    assert o.tekil.predict(*M2, 1) == ([0.0] * 7, [0.0] * 7, 0.0)


# ── birim: kip / etiket / metin / ayar / petri ızgarası ───────────────────────────────────────────────────
def test_KRITIK_odak_kipi_ve_etiket_eki():
    import servers.ai_pro_hedef as hedef

    P = type("P", (), {"ad": "petri", "hedef_etiketi": "Kuyu"})()
    assert hedef.odak_kipi(P, 3) == "KUYUCUK" and hedef.odak_kipi(P, 0, "tum_petri") == "TUM_PETRI"
    assert hedef.odak_kipi(type("F", (), {"ad": "fantom"})(), 1) == "FANTOM"
    kedi = type("K", (), {"ad": "kedi"})()
    assert hedef.odak_kipi(kedi, 0) == "KEDI_TV" and hedef.odak_kipi(kedi, 2) == "KEDI_ORGAN"
    with pytest.raises(ValueError):
        hedef.odak_kipi(type("X", (), {"ad": "yok"})(), 0)
    assert (
        hedef._etiket_eki(P, "Kuyu B4") == "B4"
        and hedef._etiket_eki(P, "B4") == "B4"
        and hedef._etiket_eki(P, None) == ""
    )
    assert hedef.odak_destekli(P) and hedef.odak_destekli(kedi)  # ODK5: kedi önerisi de ODAK'tan (sürüşü Y142 kapalı)


def test_KRITIK_odak_engel_metni_SAYI_bicimi():
    import servers.ai_pro_hedef as hedef

    m = hedef.odak_engel_metni({"engel": "dozTavanUstu", "engel_ek": {"tavan": 1.23456}})
    assert "1.23" in m and "{{" not in m


def test_KRITIK_odak_ayarla_KEDIDE_yok_sayilir_ve_dozsuz_TEMIZLER():
    import servers.ai_pro_hedef as hedef

    kedi = type("K", (), {})()
    hedef.odak_ayarla(kedi, {"doz_mT": 1.0})
    assert not hasattr(kedi, "odak_ayari")
    f = hedef.FantomSaglayici()
    hedef.odak_ayarla(f, {"doz_mT": 0.7, "kip": "FANTOM"}, "Tümör 3")
    assert f.odak_ayari == {"doz_mT": 0.7, "kip": "FANTOM", "hedef_etiket": "Tümör 3", "frek_hz": 100.0}
    hedef.odak_ayarla(f, {"kip": "FANTOM"})
    assert f.odak_ayari is None
    hedef.odak_ayarla(f, {"doz_mT": 0.7})
    hedef.odak_ayarla(f, None)
    assert f.odak_ayari is None


def test_KRITIK_odak_plani_PETRI_izgarasi_META_dan_ve_tavan_ENGELI(monkeypatch, tmp_path):
    import servers.ai_pro_hedef as hedef

    from ai_hub.odak import oneri
    from ai_hub.odak.alan import olcum_to_backend

    kok = _kok_kur(str(tmp_path))
    monkeypatch.setattr(hedef, "duzlem_veri_koku", lambda: kok)
    A = oneri.alan_modeli(kok)
    kuyular = []
    for r in range(4):
        for c in range(6):
            P = olcum_to_backend(np.array([(c - 2.5) * 19.3, -165.0, (r - 1.5) * 19.3]))
            kuyular.append({"etiket": f"{'ABCD'[r]}{c + 1}", "P": P.tolist(), "px": [c * 40, r * 40]})

    class _Petri:
        ad, hedef_etiketi = "petri", "Kuyu"

        def __init__(self, k):
            self.k = k

        def son_lokalizasyon_meta(self):
            return {"odak_adaylar": self.k}

    hedefP = next(k["P"] for k in kuyular if k["etiket"] == "C2")
    monkeypatch.setattr(oneri, "model_al", lambda kip, **_k: _DogruModel(A, [hedefP]))
    plan = hedef.odak_plani(_Petri(kuyular), {"target_label": "Kuyu C2"}, 5, None, "KUYUCUK")
    assert plan["engel"] is None and plan["kip"] == "KUYUCUK" and len(plan["kuyular"]) == 24, plan
    # ızgara eksik + doz yok → tavan hesabı engeller (doz None kalır)
    p2 = hedef.odak_plani(_Petri(kuyular[:5]), {"target_label": "Kuyu C2"}, 5, None, "TUM_PETRI")
    assert p2["engel"] == "plakaYok" and p2["doz_mT"] is None and p2["duty"] == [0.0] * 7
    assert json.loads(json.dumps(plan))  # mühüre yazılabilir (JSON)


def test_KRITIK_ODK6_kare_SURUSUNDEN_SONRA_canli_E_ODAK_CST_ve_durdurmada_TEMIZ(o):
    """ODK6: GERÇEK `/frame` + GERÇEK `_drive_coils_ai_pro` → sürülen ODAK planının CST E'si canlı E çubuğuna yazılır; durdurma siler."""
    from servers import ai_approval
    from servers import efield_live as ef

    ef.odak_guncelle(None)
    _hazirlik(o)
    pid = _oner(o, doz_mT=0.4).json()["proposalId"]
    ai_approval.approve(pid, "arastirmaci@test.local")
    assert o.c.post("/api/ai/pro/start", json={"proposal_id": pid}).status_code == 200
    _Hat.sonuc = _Sonuc([(P2, M2, 300)])
    j = ap.kare(o).json()
    assert j.get("driven") is True, j
    od = ef.odak_degeri()
    assert od is not None and od["cancer"] > 0 and od["healthy"] > 0, od
    o.c.post("/api/ai/pro/stop")
    assert ef.odak_degeri() is None, "durdurmadan sonra ODAK E'si kaldı"
