# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""ODK11 + Y284 (sahip 13 Kasım 2026, tezgâh B: "zaten hepsi dolu olmayacak ki … kaç tane bulursa ona göre başlamalı, 24 şartını kaldır";
"yeniden çekim sayılmasın kuralı değiştir, yarı dolu plakayla da sürüş olabilmeli koşulluda").
ÖLÇÜLEN (tezgâh 13-11 15:0x): 19 / 24 kuyu sıvılı plaka → petri hattı 19 kuyu verdi → ODAK `plakaYok` (24 şartı) → bobin hiç sürülmedi.
SÖZLEŞME: plaka yeri + yönü GÖRÜLEN kuyulardan katı oturtulur (aralık numuneden), boş kuyuların yeri + kamera pikseli hesaplanır
(`bos`); hedef yalnız görülen kuyu; alt sınır ≥ 3 kuyu iki satır VE iki sütunda (tek çizgide yön / ayna belirsiz) → yoksa `plakaYok`;
sapma > sınır → `plakaUyumsuz` (SÜRMEZ). Boş hücre (`kuyu_skor_esigi`) PEMF kapısında koşullu kipte de sürüşü KESMEZ (Y284).
EN ALT sahte: ODAK modeli (`_DogruModel`, fizikle tutan); alan tablosu + kalibrasyon + plan GERÇEK."""

from __future__ import annotations

import json
import os

import numpy as np
import pytest
from test_ODK_odak_alan_ve_oneri import _DogruModel, _plaka

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORNEK = os.path.join(KOK, "tests", "veri", "odak_kalibrasyon_ornek.json")
#: Tezgâhtaki gibi beş boş kuyu (dağınık)
BOS = ("A6", "B5", "C1", "D3", "D6")


@pytest.fixture(scope="module")
def A():
    from ai_hub.odak.alan import AlanModeli

    with open(ORNEK, encoding="utf-8") as fh:
        return AlanModeli(json.load(fh))


def _yari(kuyular, bos=BOS):
    return [k for k in kuyular if k["etiket"] not in bos]


def _ayna(kuyular):
    """Etiket el yönü ters plaka (satırlar ters: A↔D, B↔C) — kamera / kabin el yönü varsayımı YOK."""
    sat = "ABCD"
    return [{**k, "etiket": f"{sat[3 - sat.index(k['etiket'][0])]}{k['etiket'][1:]}"} for k in kuyular]


@pytest.mark.parametrize("ayna", [False, True], ids=["el_yonu_duz", "el_yonu_ayna"])
def test_KRITIK_YARI_DOLU_plaka_yer_yon_ve_BOS_kuyular_TAM_plakayla_AYNI(ayna):
    from ai_hub.odak import oneri

    tam = _plaka(merkez_b=(30.0, -170.0, -20.0), th=0.7)
    tam = _ayna(tam) if ayna else tam
    g24 = oneri.petri_izgarasi(tam)
    g19 = oneri.petri_izgarasi(_yari(tam))
    assert g19["bulunan"] == 19 and g24["bulunan"] == 24
    assert np.allclose(g19["merkez"], g24["merkez"], atol=1e-6) and g19["theta"] == pytest.approx(
        g24["theta"], abs=1e-9
    )
    for a, b in zip(g24["sira"], g19["sira"]):
        assert a["etiket"] == b["etiket"] and np.allclose(a["P"], b["P"], atol=1e-6), (a, b)
        assert b["bos"] is (b["etiket"] in BOS)
        assert np.allclose(a["px"], b["px"], atol=0.05), (
            a["etiket"],
            a["px"],
            b["px"],
        )  # kamera pikseli de hesaplanır (harita yönü)


def test_KRITIK_ALT_SINIR_uc_kuyu_IKI_satir_IKI_sutun():
    from ai_hub.odak import oneri

    tam = _plaka(th=0.2)
    sec = lambda *e: [k for k in tam if k["etiket"] in e]  # noqa: E731
    g = oneri.petri_izgarasi(sec("A1", "A2", "B1"))  # en küçük geçerli (L)
    assert g["bulunan"] == 3 and len(g["sira"]) == 24 and sum(k["bos"] for k in g["sira"]) == 21
    assert np.allclose(g["merkez"], oneri.petri_izgarasi(tam)["merkez"], atol=1e-6)
    for kuyular, bulunan in (
        (sec("A1", "B2"), 2),
        (sec(*[f"A{c}" for c in range(1, 7)]), 6),
        (sec("A3", "B3", "C3", "D3"), 4),
    ):
        with pytest.raises(oneri.Engel) as e:
            oneri.petri_izgarasi(kuyular)
        assert e.value.kod == "plakaYok" and e.value.ek == {"bulunan": bulunan, "beklenen": 3}, e.value.ek


def test_KRITIK_SAPMA_SINIRI_kayik_kuyu_plakaUyumsuz_SURMEZ():
    from ai_hub.odak import oneri

    kuyular = _yari(_plaka(th=0.4))
    kuyular[3] = {**kuyular[3], "P": (np.asarray(kuyular[3]["P"]) + [25.0, 0.0, 0.0]).tolist()}
    with pytest.raises(oneri.Engel) as e:
        oneri.petri_izgarasi(kuyular)
    assert (
        e.value.kod == "plakaUyumsuz"
        and e.value.ek["bulunan"] == 19
        and e.value.ek["sapma"] > oneri.IZGARA_SAPMA_SINIRI_MM
    )
    # KARŞIT: sınır içindeki gürültü (1 mm) geçer
    gur = _yari(_plaka(th=0.4))
    rng = np.random.default_rng(7)
    gur = [{**k, "P": (np.asarray(k["P"]) + rng.normal(0, 1.0, 3) * [1, 0, 1]).tolist()} for k in gur]
    assert oneri.petri_izgarasi(gur)["bulunan"] == 19


def test_KRITIK_ONERI_YARI_DOLU_KUYUCUK_surulur_harita_24_bos_ISARETLI_bos_kuyu_HEDEF_OLAMAZ(A):
    from ai_hub.odak import oneri

    kuyular = _yari(_plaka())
    hedef = next(k for k in kuyular if k["etiket"] == "B3")
    tv = oneri.hedef_tavani("KUYUCUK", A, kuyular=kuyular, hedef_etiket="B3")
    assert tv["engel"] is None, tv
    plan = oneri.oner(
        "KUYUCUK", A, 0.6 * tv["tavan_mT"], model=_DogruModel(A, [hedef["P"]]), kuyular=kuyular, hedef_etiket="B3"
    )
    assert plan["engel"] is None and plan["beklenen_mT"] == pytest.approx(plan["doz_mT"], rel=0.02), plan
    assert len(plan["kuyular"]) == 24 and sorted(k["etiket"] for k in plan["kuyular"] if k["bos"]) == sorted(BOS)
    assert all(isinstance(k["mT"], float) and k["mT"] > 0 for k in plan["kuyular"])
    assert next(k for k in plan["kuyular"] if k["secili"])["etiket"] == "B3"
    bos_plan = oneri.oner(
        "KUYUCUK", A, 0.6 * tv["tavan_mT"], model=_DogruModel(A, [hedef["P"]]), kuyular=kuyular, hedef_etiket="D3"
    )
    assert bos_plan["engel"] == "kuyuYok" and bos_plan["duty"] == [0.0] * 7, bos_plan


def test_KRITIK_ONERI_YARI_DOLU_TUM_PETRI_plaka_TAMAMI_hedef(A):
    from ai_hub.odak import oneri

    kuyular = _yari(_plaka(px=False))
    g = oneri.kip_girdisi("TUM_PETRI", A, kuyular=kuyular)
    assert len(g["T"]) == 24  # doz plakanın TAMAMINDA (boşlar dahil) en zayıf nokta — tam plakayla aynı tanım
    tv = oneri.hedef_tavani("TUM_PETRI", A, kuyular=kuyular)
    plan = oneri.oner("TUM_PETRI", A, 0.5 * tv["tavan_mT"], model=_DogruModel(A, list(g["T"])), kuyular=kuyular)
    assert plan["engel"] is None and sum(k["bos"] for k in plan["kuyular"]) == 5, plan


@pytest.mark.parametrize("dil,parca", [("tr", "en az 3 kuyu"), ("en", "at least 3 wells")])
def test_KRITIK_ENGEL_metinleri_EYLEM_soyler_iki_dilde(dil, parca):
    for d, kok in (("tr", "apps/backend/i18n/tr.json"), ("en", "apps/backend/i18n/en.json")):
        if d != dil:
            continue
        e = json.load(open(os.path.join(KOK, kok), encoding="utf-8"))["ai"]["pro"]["odak"]["engel"]
        assert parca in e["plakaYok"].replace("{{beklenen}}", "3") and "{{bulunan}}" in e["plakaYok"]
        assert "{{sapma}}" in e["plakaUyumsuz"] and "{{bulunan}}" in e["plakaUyumsuz"]
        if dil == "en":
            assert "petri" not in (e["plakaYok"] + e["plakaUyumsuz"]).lower()  # Y168


def test_KRITIK_Y284_bos_hucre_KOSULLU_kipte_SURUSU_KESMEZ():
    from ai_hub.cv_ortak import pemf_kapisi as pk

    sonuc = {
        "success": True,
        "pemf_valid": True,
        "warnings": ["kuyu_skor_esigi: 5 hucrenin skoru 0.6 altinda - kuyu sayilmadi: A6, B5, C1, D3, D6"],
    }
    k = pk.degerlendir(sonuc, model="petri")
    assert k["surulebilir"] is True and k["nedenler"] == [] and "kuyu_skor_esigi" in k["uyari_kodlari"], k
