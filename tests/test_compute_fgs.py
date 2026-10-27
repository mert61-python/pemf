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


# ── TUR 3 (çürütücü 2 y5): YÖN — eylem birimleri ağrı belirtisi ARTTIKÇA azalmaz ─────────────────────────────────────────────
# Tur 2 kolları iç TUTARLILIĞI ölçüyordu (Σ AU, bant, girdiye bağlılık), YÖNÜ değil: AU2'de `au2 = 0` ↔ `au2 = 2` (açık göz 2, sıkı
# kapalı göz 0 — ağrılı kediye "Ağrı Yok" yanlış güvencesi) geniş kümede (325 passed) YEŞİLDİ. Kapı: aynı yüzde YALNIZ bir belirti
# adım adım ağırlaştırılır (göz kapanır / baş iner / kulak ucu tabana yatar) → ilgili eylem birimi AZALMAZ (monoton) ve iki uç
# arasında ARTAR. Eşikler (THRESH) testte PİNLENMEZ — yalnız sıra; uçlar normalize yüz koordinatlarının iki ucundadır.
_YON_TOHUMLARI = (557, 1, 2)


def _au(kp, ad: str) -> int:
    return compute_fgs(kp)["action_units"][ad]["score"]


def _goz(kp, yari_yukseklik: float):
    """İki göz de genişliği 0.2 olan yatay çizgi üzerinde; `yari_yukseklik` 0 = tam kapalı (CatFLW: sağ 3-7, sol 8-11)."""
    kp = kp.copy()
    a = yari_yukseklik
    kp[3], kp[7] = [0.30, 0.40], [0.20, 0.40]  # sağ göz merkez / dış köşe (genişlik = 2 × 0.1)
    kp[9], kp[8] = [0.60, 0.40], [0.80, 0.40]  # sol göz iç / dış köşe
    kp[4], kp[6], kp[5] = [0.27, 0.40 - a], [0.33, 0.40 - a], [0.30, 0.40 + a]
    kp[10], kp[11] = [0.70, 0.40 - a], [0.70, 0.40 + a]
    return kp


def _kulak(kp, yukselik: float):
    """Kulak tabanları y=0.30'da; uçlar tabandan `yukselik` kadar yukarıda, yana 0.11 açık (0 = uç tabana yatmış)."""
    kp = kp.copy()
    kp[22], kp[26], kp[27], kp[31] = [0.25, 0.30], [0.35, 0.30], [0.65, 0.30], [0.75, 0.30]
    kp[24], kp[29] = [0.19, 0.30 - yukselik], [0.81, 0.30 - yukselik]
    return kp


def _bas(kp, kayma: float):
    """Yüz dikeyde 0.2'ye sıkıştırılıp `kayma` kadar aşağı ötelenir (yalnız baş konumu değişir — öteleme geometriyi bozmaz)."""
    kp = kp.copy()
    kp[:, 1] = kp[:, 1] * 0.2 + kayma
    return kp


def _monoton_ve_artan(dizi: list, etiket: str) -> None:
    dusus = [(i, dizi[i], dizi[i + 1]) for i in range(len(dizi) - 1) if dizi[i + 1] < dizi[i]]
    assert not dusus, f"{etiket}: belirti AĞIRLAŞIRKEN puan DÜŞTÜ (yön ters) {dizi} — düşüşler {dusus}"
    assert dizi[-1] > dizi[0], f"{etiket}: en hafif ve en ağır uçta puan aynı {dizi} — eylem birimi belirtiye KÖR"


def test_KRITIK_D557_FGS_YONU_goz_kapaninca_AU2_bas_inince_AU5_kulak_yatinca_AU1_AZALMAZ():
    """MUTASYON: AU2 / AU5 / AU1 dallarında 0 ↔ 2 (ters yön), bir dalı sabitlemek → KIRMIZI. Eşik değeri testte YOK."""
    for tohum in _YON_TOHUMLARI:
        kp = np.random.default_rng(tohum).random((48, 2))
        goz = [
            _au(_goz(kp, a), "AU2_Orbital_Tightening") for a in (0.30, 0.20, 0.12, 0.10, 0.08, 0.06, 0.04, 0.02, 0.0)
        ]
        _monoton_ve_artan(goz, f"tohum {tohum} AU2 (göz açıktan kapalıya)")
        bas = [_au(_bas(kp, k), "AU5_Head_Position") for k in (0.0, 0.1, 0.2, 0.3, 0.4, 0.45, 0.5, 0.6, 0.7, 0.8)]
        _monoton_ve_artan(bas, f"tohum {tohum} AU5 (baş yukarıdan aşağıya)")
        kulak = [_au(_kulak(kp, r), "AU1_Ear_Position") for r in (0.30, 0.25, 0.20, 0.15, 0.10, 0.05, 0.0)]
        _monoton_ve_artan(kulak, f"tohum {tohum} AU1 (kulak dikten yatığa)")
