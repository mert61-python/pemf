# -*- coding: utf-8 -*-
"""OTB T-1 / T-2 / T-3 (ODM tezgâhı 19-11, onay penceresi):
  · T-2: "Doz (en çok X)" FİZİK tavanıydı; model o dozu veremiyordu (B4 1,81 istenebilir → beklenen 1,59 → engel). SÖZLEŞME: üst sınır
    MODELİN ulaşabildiği (`ulasilabilir_tavan`: modelin yönü duty ≤ 0,5'e ölçekli, zaman domeni) — fizik tavanıyla sınırlı, ayrıca söylenir;
    doz verilmezse başlangıç önerisi bunun %80'i.
  · T-3: tavanın ALTINDA da %10 sapma engel veriyordu (B5 1,44 → 1,63). SÖZLEŞME: önce FİZİK DÜZELTME adımı (genlik × istenen / beklenen,
    duty ≤ 0,5, yeniden zaman domeni denetimi; en çok `DUZELTME_ADIMI`), ancak düzelmezse `dozSapmasi`; düzeltme planda görünür.
  · T-1: "en çok X" kip (Kuyucuk ↔ Tüm petri) ya da haritadan seçilen kuyu değişince yenilenmiyordu. SÖZLEŞME: öneri, petride her kip ve
    görülen her kuyu için ulaşılabilir tavanı taşır (`tavanlar`; plan tavanıyla AYNI hesap) — pencere seçime göre gösterir.
EN ALT sahte: ODAK modeli (yerel alandan yön seçen sahte); alan modeli + kalibrasyon GERÇEK (örnek dosya)."""

from __future__ import annotations

import numpy as np
import pytest
from test_ODK_odak_alan_ve_oneri import A, K, _DogruModel, _plaka  # noqa: F401  aynı düzenek


class _ZayifYonModel(_DogruModel):
    """Tavan köşesinin yönünde ama bir bobini (en güçlüsünü) SIFIRLAYAN model — fizik tavanına ULAŞAMAZ (T-2)."""

    def __init__(self, A, P_hedef, sifir=None, **k):
        super().__init__(A, P_hedef, **k)
        self.u = self.u.astype(float).copy()
        self.u[sifir if sifir is not None else 0] = 0.0


class _AzModel(_DogruModel):
    """Doğru yön, genliği `olcek` kadar AZ veren model (T-3: düzeltilebilir sapma)."""


class _YonBozanModel(_DogruModel):
    """Tavan dozunda doğru yön, ama başka dozlarda tek bobin — düzeltme genliği duty sınırında takılır (T-3: düzelmez → engel)."""

    def __init__(self, A, P_hedef, tavan, **k):
        super().__init__(A, P_hedef, **k)
        self.tavan = tavan

    def tahmin(self, X):
        y = super().tahmin(X)
        if abs(float(X[0, 0]) - self.tavan) > 1e-3:  # tavan 3 basamağa yuvarlanmış gelir
            t = np.zeros_like(y)
            t[0, 0] = y[0, 0]
            return t
        return y


def _hedef(kuyular, e="B3"):
    return next(k for k in kuyular if k["etiket"] == e)


def test_KRITIK_T2_EN_COK_modelin_ULASABILDIGI_fizik_tavani_AYRICA(A):
    from ai_hub.odak import oneri

    kuyular = _plaka()
    m = _ZayifYonModel(A, [_hedef(kuyular)["P"]])
    fizik = oneri.hedef_tavani("KUYUCUK", A, kuyular=kuyular, hedef_etiket="B3")["tavan_mT"]
    plan = oneri.oner("KUYUCUK", A, 0.3 * fizik, model=m, kuyular=kuyular, hedef_etiket="B3")
    assert plan["engel"] is None, plan
    assert plan["fizik_tavan_mT"] == pytest.approx(fizik)
    assert plan["tavan_mT"] < 0.97 * fizik, f"'en çok' hâlâ fizik tavanı: {plan['tavan_mT']} / {fizik}"
    # fizik tavanının altında ama modelin ulaşamadığı doz → istenirken "en çok <ulaşılabilir>" der (sürmeden önce)
    arada = (plan["tavan_mT"] + fizik) / 2
    p2 = oneri.oner("KUYUCUK", A, arada, model=m, kuyular=kuyular, hedef_etiket="B3")
    assert p2["engel"] == "dozTavanUstu" and p2["engel_ek"]["tavan"] == pytest.approx(plan["tavan_mT"]), p2
    # ulaşılabilir tavanın kendisi istenebilir ve sürülebilir (fizik denetimi geçer)
    p3 = oneri.oner("KUYUCUK", A, plan["tavan_mT"], model=m, kuyular=kuyular, hedef_etiket="B3")
    assert p3["engel"] is None and abs(p3["beklenen_mT"] / p3["doz_mT"] - 1) <= oneri.DOZ_SAPMA_SINIRI, p3


def test_KRITIK_T2_ulasilabilir_tavan_EN_COK_SINIRLAYAN_bobin_azamisine_olcekler(A):
    """Farklı genlikli yön: ölçek, genliği EN ÇOK sınırlayan bobinin azamisine (duty 0,5) değdirir — öbürleri altında kalır."""
    from ai_hub.odak import oneri

    MT = A.alan(np.array([_hedef(_plaka())["P"]]))
    a = np.array([0.5, 0.25, 0.0, -0.1, 0.0, 0.2, 0.0])
    k = float(np.min(A.a_azami[a != 0] / np.abs(a[a != 0])))
    beklenen = float(A.td_tepe(MT, A.isaretli_duty(a * k)).min())
    assert oneri.ulasilabilir_tavan(A, MT, a) == pytest.approx(beklenen)
    assert np.isclose(np.max(np.abs(a * k) / A.a_azami), 1.0)
    assert oneri.ulasilabilir_tavan(A, MT, np.zeros(7)) == 0.0


def test_KRITIK_T2_doz_VERILMEZSE_ulasilabilir_tavanin_yuzde_80i(A):
    from ai_hub.odak import oneri

    kuyular = _plaka()
    m = _ZayifYonModel(A, [_hedef(kuyular)["P"]])
    plan = oneri.oner("KUYUCUK", A, None, model=m, kuyular=kuyular, hedef_etiket="B3")
    assert plan["engel"] is None, plan
    assert plan["doz_mT"] == pytest.approx(round(0.8 * plan["tavan_mT"], 2), abs=0.011)


def test_KRITIK_T3_sapma_FIZIK_DUZELTMESIYLE_giderilir_duty_yarim_ve_planda_gorunur(A):
    from ai_hub.odak import oneri

    kuyular = _plaka()
    m = _AzModel(A, [_hedef(kuyular)["P"]], olcek=0.8)  # beklenen istenenin ~%80'i (B5 tezgâhı: %15 sapma)
    tv = oneri.hedef_tavani("KUYUCUK", A, kuyular=kuyular, hedef_etiket="B3")["tavan_mT"]
    plan = oneri.oner("KUYUCUK", A, 0.5 * tv, model=m, kuyular=kuyular, hedef_etiket="B3")
    assert plan["engel"] is None, f"düzeltilebilir sapma yine engel: {plan['engel']} {plan.get('engel_ek')}"
    assert abs(plan["beklenen_mT"] / plan["doz_mT"] - 1) <= oneri.DOZ_SAPMA_SINIRI
    assert max(plan["duty"]) <= 0.5 + 1e-9
    d = plan["duzeltme"]
    assert d["ilk_beklenen_mT"] < 0.9 * plan["doz_mT"] and d["kat"] > 1.1, d


def test_KARSIT_T3_sapma_YOKSA_duzeltme_YOK(A):
    from ai_hub.odak import oneri

    kuyular = _plaka()
    m = _DogruModel(A, [_hedef(kuyular)["P"]])
    tv = oneri.hedef_tavani("KUYUCUK", A, kuyular=kuyular, hedef_etiket="B3")["tavan_mT"]
    plan = oneri.oner("KUYUCUK", A, 0.5 * tv, model=m, kuyular=kuyular, hedef_etiket="B3")
    assert plan["engel"] is None and "duzeltme" not in plan


def test_KRITIK_T3_DUZELMEZSE_dozSapmasi_AYNEN_duty_SIFIR(A):
    from ai_hub.odak import oneri

    kuyular = _plaka()
    hedef = _hedef(kuyular)
    tv = oneri.hedef_tavani("KUYUCUK", A, kuyular=kuyular, hedef_etiket="B3")["tavan_mT"]
    m = _YonBozanModel(A, [hedef["P"]], tavan=tv)
    plan = oneri.oner("KUYUCUK", A, 0.8 * tv, model=m, kuyular=kuyular, hedef_etiket="B3")
    assert plan["engel"] == "dozSapmasi" and plan["duty"] == [0.0] * 7, plan
    assert oneri.DUZELTME_ADIMI == 3


def test_KRITIK_T1_petri_TAVANLARI_kip_ve_kuyu_basina_PLANLA_AYNI_bos_kuyu_YOK(A, monkeypatch):
    from ai_hub.odak import oneri

    kuyular = [k for k in _plaka() if k["etiket"] not in ("A1", "D6")]  # iki boş (görülmeyen) kuyu
    modeller = {}

    def model_al(kip, f_hz=None):
        return modeller[kip]

    # her kip için bir sahte (TÜM PETRİ: bütün kuyular; KUYUCUK: B3 yönü — tavan değeri hedefin alanından bağımsız hesaplanır)
    modeller["TUM_PETRI"] = _DogruModel(A, [k["P"] for k in kuyular])
    modeller["KUYUCUK"] = _ZayifYonModel(A, [_hedef(kuyular)["P"]])
    tv = oneri.petri_tavanlari(A, kuyular, model_al_=model_al)
    assert set(tv["KUYUCUK"]) == {k["etiket"] for k in kuyular}, (
        "görülen her kuyu için tavan yok / boş kuyuya tavan verildi"
    )
    assert "A1" not in tv["KUYUCUK"] and "D6" not in tv["KUYUCUK"]
    p_tp = oneri.oner("TUM_PETRI", A, 0.3, model=modeller["TUM_PETRI"], kuyular=kuyular)
    assert tv["TUM_PETRI"] == pytest.approx(p_tp["tavan_mT"])
    for e in ("B3", "C5"):
        p = oneri.oner("KUYUCUK", A, 0.2, model=modeller["KUYUCUK"], kuyular=kuyular, hedef_etiket=e)
        assert tv["KUYUCUK"][e] == pytest.approx(p["tavan_mT"]), e
    assert tv["KUYUCUK"]["B3"] != tv["KUYUCUK"]["C5"], "kuyu değişince tavan yenilenmiyor"


def test_T1_tavanlar_PLAKA_yoksa_ya_da_MODEL_yoksa_BOS(A):
    from ai_hub.odak import oneri

    def yok(kip, f_hz=None):
        raise FileNotFoundError(kip)

    assert oneri.petri_tavanlari(A, [], model_al_=yok) == {"KUYUCUK": {}}
    assert oneri.petri_tavanlari(A, _plaka(), model_al_=yok) == {"KUYUCUK": {}}


def test_KRITIK_T1_oneri_YANITI_tavanlari_TASIR_muhur_dozu_DEGISMEZ(monkeypatch):
    """`/propose` petri ODAK özetine `tavanlar` ekler (yalnız gösterim); mühürdeki doz / plan aynı."""
    import time

    import servers.ai_pro_hedef as hedef
    import servers.ai_router as air
    import servers.api_server as apis
    from fastapi.testclient import TestClient

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
    beklenen = {"TUM_PETRI": 1.5, "KUYUCUK": {"C2": 1.2, "C6": 1.1}}
    monkeypatch.setattr(hedef, "odak_tavanlari", lambda s, f=None: beklenen)
    snap = dict(air._ai_organ_cache)
    C2 = {"id": 7, "label": "Kuyu C2", "x": 10.0, "y": -150.0, "z": 20.0, "reliability": 0.95, "pxn": [0.3, 0.5]}
    air._ai_organ_cache.update(
        {
            "localized": True,
            "organ_id": 0,
            "model": "petri",
            "at": time.time(),
            "x_mm": 10.0,
            "y_mm": -150.0,
            "z_mm": 20.0,
            "reliability": 0.95,
            "kosulsuz": False,
            "targets": [C2],
            "secili_id": 7,
            "target_label": "Kuyu C2",
        }
    )
    try:
        r = TestClient(apis.app).post(
            "/api/ai/pro/propose", json={"organ_id": 0, "model": "petri", "odak_kip": "KUYUCUK", "doz_mT": 0.6}
        )
        assert r.status_code == 200, r.text
        od = r.json()["specs"]["odak"]
        assert od["tavanlar"] == beklenen and od["doz_mT"] == 0.6 and od["tavan_mT"] == 1.2
    finally:
        air._ai_organ_cache.clear()
        air._ai_organ_cache.update(snap)


def test_T1_tavanlar_PETRI_DISINDA_yok():
    import types

    import servers.ai_pro_hedef as hedef

    assert hedef.odak_tavanlari(types.SimpleNamespace(ad="fantom")) is None


def test_T2_model_DOSYASI_yoksa_modelYok_duty_SIFIR(A, monkeypatch):
    from ai_hub.odak import oneri

    def yok(kip, f_hz=None):
        raise FileNotFoundError(kip)

    monkeypatch.setattr(oneri, "model_al", yok)
    plan = oneri.oner("KUYUCUK", A, 0.5, kuyular=_plaka(), hedef_etiket="B3")
    assert plan["engel"] == "modelYok" and plan["duty"] == [0.0] * 7


def test_KRITIK_T1_saglayici_tavanlari_SON_LOKALIZASYONUN_kuyulariyla_hata_olursa_None(A, monkeypatch, tmp_path):
    import shutil
    from pathlib import Path

    import servers.ai_pro_hedef as hedef

    from ai_hub.odak import oneri

    kok = tmp_path / "veri"
    (kok / "kabin_kalibrasyonu").mkdir(parents=True)
    shutil.copyfile(
        Path(__file__).parent / "veri" / "odak_kalibrasyon_ornek.json",
        kok / "kabin_kalibrasyonu" / "alan_kalibrasyonu.json",
    )
    monkeypatch.setattr(hedef, "duzlem_veri_koku", lambda: kok)
    kuyular = _plaka()
    monkeypatch.setattr(oneri, "model_al", lambda kip, f_hz=None: _ZayifYonModel(A, [_hedef(kuyular)["P"]]))
    p = hedef.PetriSaglayici()
    p._meta = {"odak_adaylar": kuyular}
    tv = hedef.odak_tavanlari(p)
    assert tv["TUM_PETRI"] > 0 and set(tv["KUYUCUK"]) == {k["etiket"] for k in kuyular}
    monkeypatch.setattr(oneri, "petri_tavanlari", lambda *a, **k: 1 / 0)
    assert hedef.odak_tavanlari(p) is None  # yalnız gösterim: hata öneriyi düşürmez
