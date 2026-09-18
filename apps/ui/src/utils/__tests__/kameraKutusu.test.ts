// Author: mertaygn, cglrgrkn
/**
 * KAMERA KUTUSU ORAN KİLİDİ  [S7 adım 5-6 / aihub-1, aihub-2, 2026-09-04 denetimi]
 * ===============================================================================
 * ⚠️ TIBBİ KARAR EKRANI: canlı önizleme kutusunun oranı kareyle tutmadığında görüntü kırpılıyor,
 * üzerine çizilen ORGAN İŞARETLERİ kırpılmamış koordinatlara göre yerleştiği için canlı
 * görüntüyle KAYIYORDU — hekim yanlış organa bakabilir.
 *
 * SÖZLEŞME:
 *  1. Oran KAYNAĞI backend (`image_w`/`image_h`); yoksa cihaz yönüne göre varsayılan.
 *  2. Kutu TAM oranlı hesaplanır → cover ≡ contain, hiçbir platformda kırpma yok.
 *  3. Yükseklik ekran yüksekliğinin `tavan` katını aşmaz (yatay telefonda kutu ekranı yemesin);
 *     genişlik o zaman DA yüksekliğe göre küçülür — oran korunur.
 *
 * ⚠️ MUTASYON: kutuW doğrudan genişlik olarak döndürülürse 4. ve 5. vaka KIRILIR
 * (tam da denetim öncesi davranış: yükseklik kırpılır, genişlik %100 kalır → oran bozulur).
 */
import { kameraKutusu, kareOrani, VARSAYILAN_PORTRE, VARSAYILAN_YATAY } from "@/utils/kameraKutusu";

describe("kare oranı", () => {
  it("KRİTİK: backend boyutu varsa ondan türetilir", () => {
    expect(kareOrani({ image_w: 1280, image_h: 960 }, true)).toBeCloseTo(4 / 3, 6);
    expect(kareOrani({ image_w: 960, image_h: 1280 }, false)).toBeCloseTo(3 / 4, 6);
  });

  it("boyut yoksa cihaz yönüne göre varsayılana düşer", () => {
    expect(kareOrani(null, true)).toBe(VARSAYILAN_PORTRE);
    expect(kareOrani(undefined, false)).toBe(VARSAYILAN_YATAY);
    expect(kareOrani({}, true)).toBe(VARSAYILAN_PORTRE);
  });

  it("bozuk boyut (0 / negatif / eksik yarı) varsayılana düşer — sıfıra bölme yok", () => {
    expect(kareOrani({ image_w: 0, image_h: 960 }, true)).toBe(VARSAYILAN_PORTRE);
    expect(kareOrani({ image_w: 1280, image_h: 0 }, true)).toBe(VARSAYILAN_PORTRE);
    expect(kareOrani({ image_w: -5, image_h: 5 }, false)).toBe(VARSAYILAN_YATAY);
    expect(kareOrani({ image_w: 1280 }, true)).toBe(VARSAYILAN_PORTRE);
  });
});

describe("kutu boyutu", () => {
  it("tavan devrede DEĞİLKEN kap genişliğini tam kullanır", () => {
    // 335 / (3/4) = 447; tavan 1000 × 0,55 = 550 → sınır devrede değil.
    expect(kameraKutusu(335, 3 / 4, 1000)).toEqual({ width: 335, height: 447 });
  });

  it("telefon dikeyinde (844 px) tavan 464 px'te devreye girer", () => {
    // Denetim öncesi kutu 390 px genişlikte 520 px yükseklik istiyordu ve içeriği aşağı itiyordu.
    const k = kameraKutusu(390, 3 / 4, 844);
    expect(k.height).toBe(464);
    expect(k.width).toBe(348);
  });

  it("KRİTİK: tavan devreye girince GENİŞLİK de küçülür (oran korunur)", () => {
    const k = kameraKutusu(1274, 4 / 3, 700);
    expect(k.height).toBe(385); // 700 × 0,55
    expect(k.width).toBe(513); // 385 × 4/3 — kap genişliği 1274 DEĞİL
    expect(k.width / k.height).toBeCloseTo(4 / 3, 2);
  });

  it("KRİTİK: yatay telefonda kutu ekranı yemez", () => {
    const k = kameraKutusu(900, 4 / 3, 400, 0.5);
    expect(k.height).toBeLessThanOrEqual(200);
    expect(k.width / k.height).toBeCloseTo(4 / 3, 2);
  });

  it("her durumda oran korunur (kırpma yok)", () => {
    for (const [w, oran, h] of [
      [320, 3 / 4, 568],
      [768, 4 / 3, 1024],
      [1274, 16 / 9, 700],
    ] as [number, number, number][]) {
      const k = kameraKutusu(w, oran, h);
      expect(k.width / k.height).toBeCloseTo(oran, 1);
    }
  });

  it("geçersiz oran portre varsayılanına düşer (çökme yok)", () => {
    const k = kameraKutusu(300, 0, 800);
    expect(k.width / k.height).toBeCloseTo(VARSAYILAN_PORTRE, 2);
  });
});
