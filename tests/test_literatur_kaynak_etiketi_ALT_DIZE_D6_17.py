# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D6.17 · B-5.12 — literatür doz motoru KISA ANAHTAR ALT-DİZE eşleşmesini 'literature_exact' diye ETİKETLEMEZ.

ÖLÇÜLEN KUSUR (HEAD ebf1c3fe): `find_exact_protocol` tam eşleşme yoksa en-uzun-anahtar ALT-DİZE taraması yapar ve
`get_literature_recommendation` / `recommend_parameters` her bulunan protokolü 'literature_exact' diye etiketler.
'Kaşıntı' → 'kas' (kas spazmı protokolü), 'Ağrısız' → 'ağrı', 'Kemik Ağrısı' → 'kemik' (kırık protokolü; 'ağrı' ile
belirsiz) — arayüz bunlara "Literatür protokolü uygulandı" rozeti gösterir.

Düzeltme (YALNIZ ETİKET — doz DEĞİŞMEZ): 'literature_exact' yalnız (a) tam eşleşmede ya da (b) Türkçe ÇEKİM ekine duyarlı
SÖZCÜK eşleşmesi TEK bir protokolü gösteriyorsa ve bu protokol dönen dozla aynıysa verilir; aksi hâlde alt-dize dalının
AYNI dozu yeni 'literature_partial' etiketiyle döner. Arayüzün 8 hedefi 'literature_exact' + AYNI doz (kâhin: geniş hedef
kümesinde doz HEAD ile bayt aynı — `_inceleme/D6.17/kayit/kahin_*.json`).
"""

from __future__ import annotations

import types

import pytest

from ai.hybrid_recommender import CLINICAL_PROTOCOLS, create_recommender, get_literature_recommendation

#: Arayüzün 8 hedefi (ControlScreen.tsx AUTO_TARGETS) — doz test_literatur_hedef_sozlesmesi.BEKLENEN_DOZ ile aynı (pinli).
_ARAYUZ = {
    "Doku İyileşmesi": (105, 50.0, 30),
    "Eklem Ağrısı": (70, 50.0, 30),
    "Kas Spazmı": (97, 50.0, 25),
    "Kırık İyileşmesi": (60, 37.0, 52),
    "Enflamasyon Azaltma": (87, 47.0, 27),
    "Sinir Rejenerasyonu": (70, 42.0, 37),
    "Bağ Dokusu Tamiri": (75, 40.0, 37),
    "Ödem Azaltma": (110, 45.0, 25),
}

#: İlgisiz / belirsiz metinler: HEAD'de hepsi 'literature_exact' idi. Doz HEAD ile AYNI kalır (pinli, kâhin çıktısından).
_KISMI = {
    "Kaşıntı": (97, 50.0, 25),  # 'kas' alt-dizesi
    "Ağrısız": (70, 50.0, 30),  # 'ağrı' + yokluk eki (-sız) — anlam TERS
    "Kemik Ağrısı": (60, 37.0, 52),  # 'kemik' ve 'ağrı' iki ayrı protokol → belirsiz
    "Yaralanma": (95, 50.0, 30),  # 'yara' + yapım eki
    "Sinirlilik": (70, 42.0, 37),  # 'sinir' + yapım eki
    "Kaslı": (97, 50.0, 25),  # 'kas' + sahiplik eki
    "Kas Ağrısı": (70, 50.0, 30),  # 'kas' ve 'ağrı' iki ayrı protokol → belirsiz
    "Nöropatik Ağrı": (70, 42.0, 37),  # sözcük düzeyinde yalnız 'ağrı' (70/50/30) — dönen doz 'nöropati' alt-dizesinden
}


@pytest.fixture
def istemci(monkeypatch):
    from fastapi.testclient import TestClient
    from servers import api_server as api

    monkeypatch.setattr(api.state, "core", types.SimpleNamespace(stm_uyumlu=None), raising=False)
    with TestClient(api.app) as c:
        yield c


def _oner(c, hedef: str) -> dict:
    y = c.post("/api/hardware/auto_preset", json={"target_condition": hedef})
    assert y.status_code == 200, f"auto_preset {hedef!r}: {y.status_code} {y.text[:200]}"
    return y.json()["parameters"]


@pytest.mark.parametrize("hedef", sorted(_KISMI))
def test_KRITIK_alt_dize_eslesmesi_literature_exact_ETIKETLENMEZ_doz_AYNI(istemci, hedef):
    p = _oner(istemci, hedef)
    assert p["source"] != "literature_exact", f"{hedef!r} alt-dize eşleşmesi 'literature_exact' etiketlendi: {p}"
    assert p["source"] == "literature_partial", f"{hedef!r} beklenen ayrı etiket 'literature_partial': {p}"
    f, d, s = _KISMI[hedef]
    assert (p["freq"], p["duty"], p["duration"]) == (float(f), float(d), float(s)), f"{hedef!r} DOZU değişti: {p}"


@pytest.mark.parametrize("hedef", sorted(_ARAYUZ))
def test_KRITIK_arayuzun_8_hedefi_literature_exact_ve_doz_AYNI(istemci, hedef):
    p = _oner(istemci, hedef)
    assert p["source"] == "literature_exact", f"arayüz hedefi {hedef!r} artık 'literature_exact' değil: {p}"
    f, d, s = _ARAYUZ[hedef]
    assert (p["freq"], p["duty"], p["duration"]) == (float(f), float(d), float(s)), f"{hedef!r} DOZU değişti: {p}"


@pytest.mark.parametrize(
    "hedef",
    ["Eklem Ağrıları", "Akut Ağrılar", "Kas Spazmları", "Doku", "🔥 İnflamasyon", "Bağ dokusu", "Post-op Yara Bakımı"],
)
def test_cekim_ekli_sozcuk_eslesmesi_literature_exact_KALIR(hedef):
    sonuc = get_literature_recommendation(hedef)
    assert sonuc["source"] == "literature_exact", f"{hedef!r} çekim ekli tek-protokol eşleşmesi: {sonuc['source']}"


def test_recommend_parameters_ayni_etiket_sozlesmesi():
    """İkinci çağrı yeri (`recommend_parameters`) aynı etiketi verir — yalnız `get_literature_recommendation` değil."""
    rec = create_recommender()
    hasta = {"species": "dog", "age": 5, "weight": 20}
    assert rec.recommend_parameters(hasta, "Kaşıntı")["source"] == "literature_partial"
    assert rec.recommend_parameters(hasta, "Eklem Ağrısı")["source"] == "literature_exact"
    assert rec.recommend_parameters(hasta, "Zzz Olmayan Hedef 12345")["source"] == "default_wellness"
    assert rec.get_protocol_info("Kaşıntı")["type"] == "partial"
    assert rec.get_protocol_info("Eklem Ağrısı")["type"] == "exact"


@pytest.mark.parametrize("anahtar", sorted(CLINICAL_PROTOCOLS.keys()))
def test_her_anahtar_tam_eslesmede_exact(anahtar):
    assert get_literature_recommendation(anahtar)["source"] == "literature_exact"
