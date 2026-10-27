# Author: mertaygn, cglrgrkn
"""Kritik yol: FGS skorlama — yetersiz keypoint -> -1 (tespit-yok sinyali, 0 'Ağrı Yok' DEĞİL)."""

import numpy as np

from ai_hub.cat_landmark.inference_cat_landmark import compute_fgs


def test_insufficient_keypoints_returns_negative_not_zero():
    # <48 keypoint -> fgs_total = -1 (endpoint bunu detected:false/null'a çevirir).
    res = compute_fgs(np.zeros((10, 2)))
    assert res.get("fgs_total") == -1
    # KRİTİK: 0 dönmemeli (0 'Ağrı Yok' yanlış-güvencesi demek).
    assert res.get("fgs_total") != 0


def test_full_keypoints_returns_valid_or_invalid_range():
    res = compute_fgs(np.random.rand(48, 2))
    assert "fgs_total" in res
    ft = res["fgs_total"]
    assert ft == -1 or (0 <= ft <= 10)


def test_KRITIK_D557_48_GECERLI_noktada_skor_URETILIR_eksi_bir_DEGIL():
    """D5.57 (B-10.117): yukarıdaki test `ft == -1`i de kabul ediyor — yeterlilik eşiği `< 48` yerine `< 4800` yapılınca HER gerçek
    kare "tespit yok" (-1) döner, arayüz ağrı skorunu hiç göstermez ve kapı kümesi YEŞİL kalırdı (ölçüldü, HEAD d38b0db5: 219 passed).
    Belirlenimci (tohumlu) 48 nokta → 0..10 arası tam sayı skor + dolu eylem birimleri; 47 nokta → -1 (sınırın iki yanı).
    MUTASYON: `kp.shape[0] < 48` → `< 4800` / `< 49` → KIRMIZI."""
    kp = np.random.default_rng(557).random((48, 2))
    res = compute_fgs(kp)
    ft = res["fgs_total"]
    assert ft != -1, "48 GEÇERLİ noktada -1 (tespit yok) döndü — yeterlilik eşiği bozuk, ağrı skoru hiç üretilmez"
    assert isinstance(ft, (int, np.integer)) and 0 <= ft <= 10, f"FGS 0..10 dışında: {ft!r}"
    assert res["action_units"] and res["pain_level"] != "Unknown", f"48 noktada eylem birimleri boş: {res!r}"
    # TUR 2 (çürütücü g1): eşik `< 47` yapılınca 47 noktada ürün `IndexError` ile ÇÖKÜYOR — kırmızı rastlantısaldı (iddia hiç
    # değerlendirilmiyordu). 47-kolu artık açık iletiyle: istisna atmaz VE "tespit yok" (-1) döner.
    try:
        eksik = compute_fgs(kp[:47])
    except Exception as e:  # noqa: BLE001 — kapının kırmızısı (ürün eksik noktada çökmemeli)
        raise AssertionError(
            f"47 noktada compute_fgs ÇÖKTÜ ({type(e).__name__}: {e}) — yeterlilik eşiği gevşedi, eksik kare -1 yerine 500 olur"
        ) from e
    assert eksik["fgs_total"] == -1 and eksik["pain_level"] == "Unknown", (
        f"47 noktada skor üretildi (eşik gevşedi): {eksik['fgs_total']!r}"
    )


#: Tohum → 48 noktalık belirlenimci girdi (bbox-göreli). Toplamlar testte PİNLENMEZ, yalnız "girdiye bağlı" (birden çok farklı
#: değer) ve "ağrı bandında en az bir girdi" istenir. Düz tekdüze girdide baş konumu (AU5 = noktaların y ortalaması) hep ~0.5 → AU5
#: hiç sıfır dışı olmaz ve toplamdan düşürülmesi görünmezdi; ikinci küme y'yi aşağı kaydırır (baş omuz hizasının altında).
_TOHUMLAR = (557, 1, 2, 3, 4, 5, 6, 7, 8, 9)


def _girdiler():
    for tohum in _TOHUMLAR:
        yield f"tohum {tohum}", np.random.default_rng(tohum).random((48, 2))
    for tohum in (11, 12, 13):
        kp = np.random.default_rng(tohum).random((48, 2))
        kp[:, 1] = kp[:, 1] * 0.4 + 0.5  # baş aşağıda: y ortalaması ~0.7
        yield f"baş-aşağı tohum {tohum}", kp


def _beklenen_bant(toplam: int) -> str:
    """Evangelista 2019 bantları (modül docstring'i): 0-1 No Pain · 2-3 Mild · 4-6 Moderate · 7-10 Severe (testte SABİT)."""
    return "No Pain" if toplam <= 1 else "Mild" if toplam <= 3 else "Moderate" if toplam <= 6 else "Severe"


def test_KRITIK_D557_FGS_toplami_EYLEM_BIRIMLERINDEN_ve_GIRDIYE_bagli():
    """TUR 2 (çürütücü g2): `fgs_total = 0 * (au1 + … + au5)` (her kare "0 / No Pain") yapılınca eski kapılar + tur 1 kolu YEŞİLDİ —
    yalnız `!= -1`, `0..10` ve eylem birimi dolu aranıyordu. Modülün kendi KRİTİK uyarısı ("0 'Ağrı Yok' yanlış-güvencesi") tam bu mod.
    Kapı: 13 girdide (10 tekdüze + 3 baş-aşağı) (1) beş eylem biriminin her biri 0..2, (2) `fgs_total` = Σ eylem birimi puanı, (3) `pain_level` toplamın
    bandıyla, `pain` = toplam ≥ 4 tutarlı; (4) toplamlar girdiyle DEĞİŞİR (sabit skor değil) ve en az bir girdi ağrı bandında (≥ 2).
    MUTASYON: toplam sabit 0 / bir eylem birimi toplamdan düşer / bant sınırı kayar / `pain` eşiği kayar → KIRMIZI."""
    toplamlar = {}
    sifir_disi = [
        0
    ] * 5  # her eylem biriminin sıfır dışı olduğu girdi sayısı (toplamın HER birimi kapsadığı ölçülebilsin)
    for tohum, kp in _girdiler():
        r = compute_fgs(kp)
        puanlar = [au["score"] for au in r["action_units"].values()]
        sifir_disi = [n + (p > 0) for n, p in zip(sifir_disi, puanlar)]
        assert len(puanlar) == 5 and all(p in (0, 1, 2) for p in puanlar), f"{tohum}: eylem birimleri bozuk: {puanlar}"
        toplam = r["fgs_total"]
        assert toplam == sum(puanlar), (
            f"{tohum}: fgs_total {toplam!r} ≠ eylem birimleri toplamı {sum(puanlar)} ({puanlar}) — skor AU'lardan kopuk"
        )
        assert r["pain_level"] == _beklenen_bant(toplam), (
            f"{tohum}: pain_level {r['pain_level']!r} toplam {toplam} bandıyla ({_beklenen_bant(toplam)!r}) çelişiyor"
        )
        assert bool(r["pain"]) == (toplam >= 4), f"{tohum}: pain={r['pain']!r} ama toplam {toplam} (eşik 4)"
        toplamlar[tohum] = toplam
    assert len(set(toplamlar.values())) > 1, f"FGS girdiden BAĞIMSIZ (hep {set(toplamlar.values())}) — sabit skor"
    assert max(toplamlar.values()) >= 2, (
        f"hiçbir girdide ağrı bandı yok ({toplamlar}) — her kare 'Ağrı Yok' (yanlış güvence)"
    )
    assert all(sifir_disi), (
        f"aparat: bazı eylem birimleri hiçbir girdide sıfır dışı değil ({sifir_disi}) — toplamdan düşmeleri ölçülemez"
    )
