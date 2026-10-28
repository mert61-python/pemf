# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D6.20 · B-5.21 — CKD ucu 10 kategorik alanda SÖZLÜK DIŞI değeri (evet, var, 1, true …) 422 ile reddeder (router + :8100).

ÖLÇÜLEN KUSUR (HEAD ebf1c3fe): `KidneyDiseaseInput` kategorikleri serbest `str`; `utils/klinik_asgari.ckd_kapisi` yalnız alan
SAYAR. Eğitilmiş `preprocessor.pkl` OneHotEncoder'ı `drop='first'` + `handle_unknown='ignore'` → sözlük dışı değer SESSİZCE
düşürülen ilk kategoriye döner: `htn: "evet"` = hipertansiyon YOK (ölçüldü: 'evet' 0,115 notckd ↔ 'yes' 0,795 ckd;
`_inceleme/D6.20/kayit/olcum_HEAD.json`). Yanıt 200 ve `filled_fields` o alanı DOLU sayıyordu.

Düzeltme: tek kaynak `klinik_asgari.CKD_KATEGORIK` (eğitim sözlüğü) → iki transport da 422 (router istek dilinde, :8100 Türkçe
sabit — mikroservis katalogsuz). Sözlük değerleri ve eksik / yer tutucu değerler ('', '?', 'NA', NaN) AYNI (kâhin); yer tutucu
`filled_fields`'ta dolu SAYILMAZ (model onu impute eder). Arayüz ve APK 2.3.34 yalnız sözlük kodlarını gönderir (ölçüldü:
`AiHubScreen.tsx` CKD_CATEGORICAL, `git show 764f5f72:pf/src/screens/AiHubScreen.tsx`).
"""

from __future__ import annotations

import capraz
import pytest
from fastapi.testclient import TestClient

#: Asgari kapıyı geçen geçerli taban (6 alan, çekirdek belirteç VAR).
_TABAN = {"sc": 1.2, "bu": 40, "sg": 1.02, "al": 0, "hemo": 15, "age": 50, "bp": 80}

#: TR / EN beklenen metin TESTTE PİNLİ (katalogdan okunmaz).
_TR = (
    "Geçersiz kategorik değer: htn='evet' (geçerli: no, yes). Bu alanlar yalnız sözlükteki değerleri kabul eder; model başka "
    "bir değeri sessizce ilk kategoriye ('no', 'notpresent', 'abnormal', 'good') çevirir ve sonucun klinik anlamı tersine "
    "dönebilir — değeri düzeltip yeniden gönderin."
)
_EN = (
    "Invalid categorical value: htn='evet' (valid: no, yes). These fields accept only the dictionary values; the model "
    "silently turns any other value into the first category ('no', 'notpresent', 'abnormal', 'good') and the clinical "
    "meaning of the result can be reversed — correct the value and send it again."
)


@pytest.fixture(scope="module")
def istemci():
    from servers import api_server

    return TestClient(api_server.app)


@pytest.fixture()
def sahte_tahmin(monkeypatch):
    """Router yolu: gerçek model YERİNE sayaçlı sahte (`ai_router` `from ai_hub.inference_human_kidney_disease import
    predict_one` → PAKET özniteliği yamalanır). Reddedilecek istekte tahmin HİÇ çağrılmamalı."""
    import ai_hub.inference_human_kidney_disease as KD

    durum = {"cagri": []}

    def _sahte(features):
        durum["cagri"].append(dict(features))
        return {"prob_ckd": 0.115, "label": "notckd", "model": "SAHTE"}

    monkeypatch.setattr(KD, "predict_one", _sahte)
    return durum


@pytest.mark.parametrize(
    "alan, deger",
    [
        ("htn", "evet"),
        ("htn", "var"),
        ("htn", "1"),
        ("dm", "true"),
        ("pcc", "var"),
        ("rbc", "anormal"),
        ("appet", "kötü"),
    ],
)
def test_KRITIK_router_sozluk_disi_kategorik_422_tahmin_YOK(istemci, sahte_tahmin, alan, deger):
    r = istemci.post("/api/ai/disease/kidney", json={**_TABAN, alan: deger})
    assert r.status_code == 422, (
        f"{alan}={deger!r} → HTTP {r.status_code} (sessizce ilk kategori sayılıyordu): {r.text[:200]}"
    )
    assert "prob_ckd" not in r.text and "filled_fields" not in r.text, f"reddedilen istekte sonuç sızdı: {r.text[:200]}"
    assert not sahte_tahmin["cagri"], "kapı tahminden SONRA çalışıyor"
    assert f"{alan}='{deger}'" in r.json()["detail"], f"ileti hangi alanın geçersiz olduğunu söylemiyor: {r.text[:300]}"


def test_KRITIK_router_ileti_TR_ve_EN_bayt_bayt(istemci, sahte_tahmin):
    tr = istemci.post("/api/ai/disease/kidney", json={**_TABAN, "htn": "evet"})
    en = istemci.post("/api/ai/disease/kidney", json={**_TABAN, "htn": "evet"}, headers={"X-PEMF-Dil": "en"})
    assert (tr.status_code, en.status_code) == (422, 422)
    assert tr.json()["detail"] == _TR, f"TR ileti: {tr.json()['detail']!r}"
    assert en.json()["detail"] == _EN, f"EN ileti: {en.json()['detail']!r}"


@pytest.mark.parametrize(
    "ek",
    [
        {"htn": "yes"},
        {"htn": "no"},
        {"htn": " YES "},
        {"rbc": "abnormal", "pc": "normal", "pcc": "present", "ba": "notpresent", "appet": "poor"},
        {"dm": "yes", "cad": "no", "pe": "yes", "ane": "no"},
        {"htn": ""},
        {"htn": "?"},
        {},
    ],
)
def test_KARSIT_sozluk_ve_eksik_degerler_GECER_ayni_ozellikler_modele_gider(istemci, sahte_tahmin, ek):
    r = istemci.post("/api/ai/disease/kidney", json={**_TABAN, **ek})
    assert r.status_code == 200, f"geçerli {ek} reddedildi: {r.status_code} {r.text[:200]}"
    assert len(sahte_tahmin["cagri"]) == 1
    giden = sahte_tahmin["cagri"][0]
    for k, v in ek.items():
        assert giden[k] == v, f"modele giden {k} değişti: {giden[k]!r} ≠ {v!r}"


def test_yer_tutucu_DOLU_sayilmaz_filled_fields_modelin_kullandigi(istemci, sahte_tahmin):
    """'?' / 'NA' / '-' modelce EKSİK (impute) — `filled_fields` onları saymaz (7 gerçek alan)."""
    r = istemci.post("/api/ai/disease/kidney", json={**_TABAN, "htn": "?", "dm": "NA", "cad": "-", "pe": "  "})
    assert r.status_code == 200, r.text[:200]
    j = r.json()
    assert j["filled_fields"] == len(_TABAN), f"yer tutucular dolu sayıldı: filled_fields={j['filled_fields']}"


def test_NaN_EKSIK_sayilir_ne_gecersiz_ne_DOLU():
    """D67 orkestratör mutantı (`_bos_mu` NaN'ı tanımaz) YAŞADI: modelin `_eksik` kümesi NaN'ı içerir (impute) — :8100 gövdesi ya da
    iç çağıran float NaN verirse kategorik alan 'geçersiz' diye 422 almamalı, sayısal / kategorik NaN `filled_fields`'ta DOLU sayılmamalı."""
    from utils.klinik_asgari import ckd_dolu, ckd_gecersiz_kategorik

    nan = float("nan")
    assert ckd_gecersiz_kategorik({"htn": nan, "dm": "yes"}) == {}, (
        "NaN kategorik değer 'geçersiz' sayıldı (eksik olmalı)"
    )
    assert sorted(ckd_dolu({"age": nan, "htn": nan, "dm": "yes", "bp": 80})) == ["bp", "dm"], "NaN alan DOLU sayıldı"


def test_KRITIK_8100_ayni_kapi_ayni_TR_ileti(monkeypatch):
    capraz.paket_yoksa_atla("onnxruntime", sebep="ai_service :8100 calisma zamani paketi yok (CI)")
    import ai_hub.inference_human_kidney_disease as KD
    from ai_service import app as servis

    cagri: list = []
    monkeypatch.setattr(
        KD, "predict_one", lambda f: cagri.append(f) or {"prob_ckd": 0.1, "label": "notckd", "model": "S"}
    )
    c = TestClient(servis.app)
    r = c.post("/infer/kidney_disease", json={**_TABAN, "htn": "evet"})
    assert r.status_code == 422, f":8100 sözlük dışı değeri kabul etti: {r.status_code} {r.text[:200]}"
    assert r.json().get("error") == _TR, f":8100 ileti: {r.json()!r}"
    assert not cagri, ":8100 kapısı tahminden SONRA"
    ok = c.post("/infer/kidney_disease", json={**_TABAN, "htn": "yes"})
    assert ok.status_code == 200 and len(cagri) == 1 and cagri[0]["htn"] == "yes", (
        f":8100 geçerli değer: {ok.text[:200]}"
    )


def test_sozluk_EGITIM_kategorileriyle_AYNI():
    """Tek kaynak sözlük, eğitilmiş preprocessor'ın OneHotEncoder kategorileriyle aynı (ağırlık yoksa atlanır)."""
    capraz.atla_yoksa("ai_hub/inference_human_kidney_disease/preprocessor.pkl")
    import pickle
    from pathlib import Path

    from utils.klinik_asgari import CKD_KATEGORIK

    kok = Path(__file__).resolve().parents[1]
    pre = pickle.loads((kok / "ai_hub/inference_human_kidney_disease/preprocessor.pkl").read_bytes())
    _ad, kat, kolonlar = [t for t in pre.transformers_ if t[0] == "cat"][0]
    ohe = dict(kat.steps)["ohe"]
    egitim = {k: tuple(sorted(str(x) for x in c)) for k, c in zip(kolonlar, ohe.categories_)}
    assert {k: tuple(sorted(v)) for k, v in CKD_KATEGORIK.items()} == egitim


# ── TUR 2 kolları (çürütücü, hat D) ─────────────────────────────────────────────────────────────────────────────────────
def test_birden_cok_gecersiz_alan_HEPSI_bildirilir(istemci, sahte_tahmin):
    """Tur 2 kolu (tek öğe ↔ hepsi): iki alan birden sözlük dışıysa ileti İKİSİNİ de söyler — ilkinde durmak operatörü
    düzelt-gönder-yeniden-reddedil döngüsüne sokar."""
    r = istemci.post("/api/ai/disease/kidney", json={**_TABAN, "htn": "evet", "dm": "var"})
    assert r.status_code == 422, f"iki geçersiz alan → HTTP {r.status_code}: {r.text[:200]}"
    d = r.json()["detail"]
    assert "htn='evet'" in d and "dm='var'" in d, f"ileti geçersiz alanların HEPSİNİ söylemiyor: {d!r}"
    assert not sahte_tahmin["cagri"]


def test_uzun_deger_yansitmasi_40_karakterde_KIRPILIR(istemci, sahte_tahmin):
    """Tur 2 kolu (eşik): gelen değer iletide en çok 40 karakter yansıtılır (rapor iddiası; sınırsız yansıtma yanıtı şişirir)."""
    uzun = "x" * 200
    r = istemci.post("/api/ai/disease/kidney", json={**_TABAN, "htn": uzun})
    assert r.status_code == 422, r.text[:200]
    d = r.json()["detail"]
    assert "htn='" + "x" * 40 + "'" in d, f"kırpılmış değer iletide yok: {d[:160]!r}"
    assert "x" * 41 not in d, f"değer 40 karakterden uzun yansıtıldı ({d.count('x')} 'x')"


def test_eksik_kumesi_MODELIN_eksik_kumesiyle_AYNI():
    """Tur 2 kolu (ikiz tanım): kapının "eksik / yer tutucu" kararı modelin `_eksik`iyle BİREBİR aynı olmalı. Kapı bir değeri
    eksik sayıp geçirir ama model onu eksik saymazsa, değer bilinmeyen kategori olarak SESSİZCE ilk kategoriye döner
    (kapının kapattığı klinik ters dönme yeniden açılır). Sonda kümesi testte sabit."""
    capraz.paket_yoksa_atla("onnxruntime", sebep="CKD çıkarım modülü onnxruntime ister (CI)")
    from utils import klinik_asgari as ka

    from ai_hub.inference_human_kidney_disease import inference_human_kidney_disease as ihd

    sondalar = [None, float("nan"), "", " ", "  ", "?", " ? ", "NA", "na", "N/A", "NaN", "nan", "NAN", "—", "-", "--"]
    sondalar += ["yok", "none", "None", "null", "0", "no", "yes", "evet", "unknown", "bilinmiyor"]
    farkli = [s for s in sondalar if bool(ka._bos_mu(s)) != bool(ihd._eksik(s))]
    assert not farkli, f"kapı ↔ model eksik-değer kararı AYRIŞIYOR: {farkli!r}"
