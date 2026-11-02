# -*- coding: utf-8 -*-
"""KP-1 · ai/hybrid_recommender.py · sözleşmeler: tür normalizasyonu (sözcük / alt-dize / bilinmeyen), yaş-kilo kategori
sınırları, hasta bilgisi varsayılanları, sayıya çevrilemeyen frekans, Jaccard benzerliği, ağırlıklı interpolasyon (sıfır
benzerlikte None), öneri / protokol bilgisi kaynak dalları, boş anahtarın sözcük eşleşmesinde atlanması, modülün `__main__`
tanıtım çıktısının ürünün kendi önerisini yansıtması.

Saat (`hybrid_recommender.datetime`) modülün kendi içe aktardığı adla sahtelenir. `__main__` bloğu, modül kaynağı AYNI dosya
yolundan ayrı bir ad alanında derlenerek yürütülür (sys.modules'a dokunulmaz; kök günlükçü yapılandırması geri konur).
"""

from __future__ import annotations

import logging
from datetime import datetime as _gercek_datetime

import pytest

from ai import hybrid_recommender as hr

# ───────────────────────────── tür normalizasyonu ─────────────────────────────


def test_tur_IRK_adinin_SOZCUGU_ile_eslesir():
    """'Golden Retriever' tam anahtar değil → ilk tanınan sözcük ('golden') → 'dog'; 'Van Kedisi' → 'van' → 'cat'."""
    assert hr.normalize_species("Golden Retriever") == "dog"
    assert hr.normalize_species("Van Kedisi") == "cat"


def test_tur_ALT_DIZE_eslesmesi_her_iki_yonde():
    """Bitişik yazım 'BritishShorthair' (sözcük yok) → anahtar 'british' girdinin İÇİNDE → 'cat'; kısaltma 'Kitt' → girdi
    'kitty' anahtarının İÇİNDE → 'cat'."""
    assert hr.normalize_species("BritishShorthair") == "cat"
    assert hr.normalize_species("Kitt") == "cat"


def test_tur_BILINMEYEN_None_doner_ve_uyarir(caplog):
    """'Zürafa' hiçbir anahtarla (tam / sözcük / alt-dize) eşleşmez → None + 'not supported for AI' uyarısı."""
    with caplog.at_level(logging.WARNING, logger=hr.logger.name):
        assert hr.normalize_species("Zürafa") is None
    assert any("Unknown species 'Zürafa'" in r.getMessage() for r in caplog.records)


# ───────────────────────────── kaynak etiketi / sözcük eşleşmesi ─────────────────────────────


def test_literatur_kaynagi_protokol_YOKSA_default_wellness():
    """protokol None → 'default_wellness' (hedef metni ne olursa olsun)."""
    assert hr.literatur_kaynagi("Kronik Artrit", None) == "default_wellness"


def test_sozcuk_eslesmesi_BOS_anahtari_ATLAR(monkeypatch):
    """Normalizasyonda tamamen silinen (ör. yalnız emoji) ham anahtar boş norm-anahtar üretir → sözcük eşleşmesinde atlanır:
    sonuç boş anahtarsız hâliyle AYNI, boş anahtarlı aday yok (IndexError yok)."""
    once = hr._sozcuk_eslesmeleri("kas spazmi")
    monkeypatch.setitem(
        hr._CLINICAL_PROTOCOLS_NORM, "", ("🔥", {"freq": 1, "duty": 1, "duration": 1, "intensity": 1.0})
    )
    sonra = hr._sozcuk_eslesmeleri("kas spazmi")
    assert sonra == once
    assert all(k != "" for (_b, _s, k) in sonra)
    assert {k for (_b, _s, k) in sonra} == {"kas", "spazm"}


# ───────────────────────────── hasta profili ─────────────────────────────


@pytest.mark.parametrize(
    "yas, beklenen",
    [(0.5, "young"), (1.99, "young"), (2, "adult"), (8, "adult"), (8.01, "senior"), (15, "senior")],
)
def test_yas_kategorisi_SINIRLARI(yas, beklenen):
    """<2 genç · 2–8 (dahil) yetişkin · >8 yaşlı."""
    assert hr.PatientProfileAdaptor().categorize_age(yas) == beklenen


@pytest.mark.parametrize(
    "kilo, beklenen",
    [(9.9, "small"), (10, "medium"), (30, "medium"), (30.1, "large"), (50, "large"), (50.1, "giant"), (180, "giant")],
)
def test_kilo_kategorisi_SINIRLARI(kilo, beklenen):
    """<10 küçük · 10–30 (dahil) orta · 30–50 (dahil) büyük · >50 dev."""
    assert hr.PatientProfileAdaptor().categorize_weight(kilo) == beklenen


def test_hasta_bilgisi_BILINMEYEN_tur_kopege_duser_bayrakli_YAS_KILO_varsayilan(caplog):
    """Bilinmeyen tür → species 'dog' + species_unsupported True + uyarı; yaş yok → 5.0, kilo None → 20.0; girdi sözlüğü
    DEĞİŞMEZ. Bilinen tür → species_unsupported False."""
    ad = hr.PatientProfileAdaptor()
    girdi = {"species": "Zürafa", "weight": None}
    with caplog.at_level(logging.WARNING, logger=hr.logger.name):
        n = ad.normalize_patient_info(girdi)
    assert n == {"species": "dog", "species_unsupported": True, "weight": 20.0, "age": 5.0}
    assert girdi == {"species": "Zürafa", "weight": None}
    assert any("using 'dog' as fallback" in r.getMessage() for r in caplog.records)
    n2 = ad.normalize_patient_info({"species": "Tekir kedi", "age": 3, "weight": 4})
    assert n2["species"] == "cat" and n2["species_unsupported"] is False and (n2["age"], n2["weight"]) == (3, 4)


def test_uyarlama_YASLI_BUYUK_kopek_TR_ondalikli_yas():
    """Ağrı protokolü (70/50/30/1.75) + 'Golden Retriever', yaş '9,5' (TR virgül), 40 kg → yaşlı (×0.8 yoğunluk, ×0.85 süre)
    + büyük (×1.2 süre): yoğunluk 1.4, süre int(int(30×0.85)×1.2)=30, freq 70, duty 50."""
    taban = {"freq": 70, "duty": 50, "duration": 30, "intensity": 1.75}
    u = hr.PatientProfileAdaptor().adapt(taban, {"species": "Golden Retriever", "age": "9,5", "weight": 40})
    assert u["freq"] == 70 and u["duty"] == 50.0 and u["duration"] == 30
    assert u["intensity"] == pytest.approx(1.4)
    assert taban == {"freq": 70, "duty": 50, "duration": 30, "intensity": 1.75}


def test_uyarlama_GENC_DEV_at_suresi_ve_yogunlugu_KLINIK_araliga_kapanir():
    """Kırık (60/37/52/2.0) + at, 1,5 yaş, 180 kg → süre int(int(int(52×1.2)×0.9)×1.4)=77 (≤90), yoğunluk 2.0×1.3×0.85=2.21
    → 2.0'a kapanır."""
    taban = {"freq": 60, "duty": 37, "duration": 52, "intensity": 2.0}
    u = hr.PatientProfileAdaptor().adapt(taban, {"species": "horse", "age": 1.5, "weight": 180})
    assert (u["freq"], u["duty"], u["duration"], u["intensity"]) == (60, 37.0, 77, 2.0)


@pytest.mark.parametrize("frekans", ["yüksek", None])
def test_uyarlama_SAYIYA_CEVRILEMEYEN_frekans_OLDUGU_GIBI_kalir(frekans):
    """freq int'e çevrilemez (ValueError / TypeError) → uyarlama çökmez, freq aynen kalır; diğer alanlar yine kapanır."""
    u = hr.PatientProfileAdaptor().adapt(
        {"freq": frekans, "duty": 120, "duration": 200, "intensity": 5.0}, {"species": "dog", "age": 5, "weight": 20}
    )
    assert u["freq"] == frekans
    assert (u["duty"], u["duration"], u["intensity"]) == (95.0, 90, 2.0)


# ───────────────────────────── benzerlik / interpolasyon ─────────────────────────────


def test_benzerlik_BOS_hedefte_0_ortak_sozcukte_JACCARD():
    """Yalnız emoji hedef (temizlenince boş) → 0.0; 'Kronik' ↔ 'kronik artrit' → 1/2."""
    ip = hr.ParameterInterpolator()
    assert ip.calculate_similarity("🔥", "kronik artrit") == 0.0
    assert ip.calculate_similarity("kronik artrit", "🔥") == 0.0
    assert ip.calculate_similarity("Kronik", "kronik artrit") == pytest.approx(0.5)


def test_benzer_protokoller_ESIK_ve_SIRA():
    """'akut kronik' → yalnız 'kronik artrit' (1/3) ve 'akut ağrı' (1/3) eşiği (0.2) geçer; eşit skorda tablo sırası korunur."""
    benzer = hr.ParameterInterpolator().find_similar_protocols("akut kronik")
    assert [(ad, round(s, 3)) for ad, _p, s in benzer] == [("kronik artrit", 0.333), ("akut ağrı", 0.333)]
    assert benzer[0][1] is hr.CLINICAL_PROTOCOLS["kronik artrit"]


def test_interpolasyon_AGIRLIKLI_ortalama_ve_top_n():
    """'akut kronik': iki eşit-ağırlıklı protokol → freq int(77.5)=77, duty 52.5, süre int(25.0)=25, yoğunluk 1.625,
    evidence 'interpolated', kaynaklar sıralı; top_n=1 → yalnız 'kronik artrit' değerleri."""
    ip = hr.ParameterInterpolator()
    r = ip.interpolate("akut kronik")
    assert r["freq"] == 77 and r["duration"] == 25
    assert r["duty"] == pytest.approx(52.5) and r["intensity"] == pytest.approx(1.625)
    assert r["evidence"] == "interpolated" and r["source_protocols"] == ["kronik artrit", "akut ağrı"]
    r1 = ip.interpolate("akut kronik", top_n=1)
    assert (r1["freq"], r1["duration"], r1["source_protocols"]) == (70, 30, ["kronik artrit"])
    assert r1["duty"] == pytest.approx(50.0) and r1["intensity"] == pytest.approx(1.75)


class _EsiksizInterpolator(hr.ParameterInterpolator):
    """Eşiği 0'a indiren alt sınıf (benzerlik hesabı GERÇEK): hiç ortak sözcük yoksa tüm protokoller 0 skorla döner."""

    def find_similar_protocols(self, target_condition, min_similarity=0.2):
        return super().find_similar_protocols(target_condition, min_similarity=0.0)


def test_interpolasyon_TOPLAM_benzerlik_SIFIR_ise_None_sifira_bolmez():
    """Eşiksiz arama 'Zürafa' için yalnız 0-skorlu protokoller döndürür (liste boş DEĞİL) → interpolate None (ZeroDivision yok)."""
    ip = _EsiksizInterpolator()
    benzer = ip.find_similar_protocols("Zürafa")
    assert benzer and all(s == 0.0 for _a, _p, s in benzer)
    assert ip.interpolate("Zürafa") is None


# ───────────────────────────── öneri / protokol bilgisi ─────────────────────────────


class _SabitSaat:
    @staticmethod
    def now():
        return _gercek_datetime(2026, 11, 1, 9, 30, 0)


def test_oneri_INTERPOLASYON_dalinda_kaynak_interpolated_ve_zaman_damgasi(monkeypatch):
    """'Kronik' (tam / alt-dize protokol yok, 'kronik artrit' ile 1/2 benzer) + yetişkin orta köpek → kaynak 'interpolated',
    70 Hz / %50.0 / 30 dk / 1.75, evidence 'interpolated', hasta profili yankılanır, damga sahte saatten."""
    monkeypatch.setattr(hr, "datetime", _SabitSaat)
    r = hr.HybridPEMFRecommender().recommend_parameters({"species": "Kangal", "age": 5, "weight": 20}, "Kronik")
    assert r["source"] == "interpolated" and r["evidence"] == "interpolated"
    assert (r["freq"], r["duty"], r["duration"]) == (70, 50.0, 30)
    assert r["intensity"] == pytest.approx(1.75)
    assert r["patient_profile"] == {"species": "Kangal", "age": 5, "weight": 20}
    assert r["timestamp"] == "2026-11-01T09:30:00"


def test_protokol_bilgisi_BULUNAMAZSA_benzerler_EN_COK_5_ve_skorlu():
    """'Kronik' → found False, type 'none', params None; benzerler (eşik 0.1) 'kronik artrit' 0.5 + parametreleri.
    'Eklem Sorunu' → benzer yok (boş liste)."""
    rec = hr.HybridPEMFRecommender()
    bilgi = rec.get_protocol_info("Kronik")
    assert (bilgi["found"], bilgi["type"], bilgi["params"]) == (False, "none", None)
    assert bilgi["similar_protocols"] == [
        {"name": "kronik artrit", "similarity": 0.5, "params": hr.CLINICAL_PROTOCOLS["kronik artrit"]}
    ]
    bos = rec.get_protocol_info("Eklem Sorunu")
    assert bos["found"] is False and bos["similar_protocols"] == []


def test_protokol_bilgisi_COK_benzerde_skor_AZALAN_sirada():
    """Beş çok-sözcüklü protokolle sözcük paylaşan ama hiçbir anahtarı alt-dize olarak İÇERMEYEN hedef → found False;
    benzerler: 'kronik artrit' (2/6) başta, ardından dört eşit 1/7 skorlu protokol tablo sırasıyla."""
    hedef = "artrit akut kronik bag post-op yorgunlugu"
    bilgi = hr.HybridPEMFRecommender().get_protocol_info(hedef)
    assert bilgi["found"] is False and bilgi["type"] == "none"
    assert [(b["name"], round(b["similarity"], 3)) for b in bilgi["similar_protocols"]] == [
        ("kronik artrit", 0.333),
        ("akut ağrı", 0.143),
        ("post-op yara", 0.143),
        ("kas yorgunluğu", 0.143),
        ("bağ dokusu", 0.143),
    ]


# ───────────────────────────── __main__ tanıtımı ─────────────────────────────


def test_main_TANITIM_ciktisi_URUNUN_kendi_onerisini_yansitir(capsys):
    """Modül `__main__` olarak yürütülür → 4 tanıtım başlığı + her öneri satırı aynı girdiyle `recommend_parameters`ın
    döndürdüğü freq / duty / süre / kaynak / kanıt ile AYNI; 'Eklem Sorunu' bulunamaz (Found: False, Type: none)."""
    kaynak = open(hr.__file__, encoding="utf-8").read()
    kok = logging.getLogger()
    eski_isleyiciler, eski_duzey = kok.handlers[:], kok.level
    try:
        exec(compile(kaynak, hr.__file__, "exec"), {"__name__": "__main__", "__file__": hr.__file__})
    finally:
        kok.handlers[:] = eski_isleyiciler
        kok.setLevel(eski_duzey)
    cikti = capsys.readouterr().out
    rec = hr.create_recommender()
    for no, (hasta, hedef) in enumerate(
        [
            ({"species": "dog", "age": 8, "weight": 25}, "Kronik Artrit"),
            ({"species": "cat", "age": 4, "weight": 5}, "Kas Ağrısı"),
            ({"species": "horse", "age": 1.5, "weight": 180}, "Kırık İyileşmesi"),
        ],
        start=1,
    ):
        r = rec.recommend_parameters(hasta, hedef)
        assert f"   Recommendation: {r['freq']}Hz, {r['duty']}%, {r['duration']}min" in cikti, (no, cikti)
        assert f"   Source: {r['source']}, Evidence: {r['evidence']}" in cikti, (no, cikti)
    assert "1. EXACT MATCH TEST: Kronik Artrit" in cikti
    assert "   Source: literature_exact, Evidence: high" in cikti
    assert "   Recommendation: 60Hz, 37%, 77min" in cikti  # duty tamsayı protokolden round(37, 1) = 37
    assert "   Found: False, Type: none" in cikti and "   Similar protocols:" in cikti
    assert cikti.rstrip().endswith("=" * 60)
