// Author: mertaygn, cglrgrkn
/**
 * KAMERA/GÖRÜNTÜ KUTUSU — oran kilidi.  [S7 adım 5-6, 2026-09-04 responsive denetimi]
 * ==================================================================================
 * ÖLÇÜLEN DURUM: canlı önizleme kutusu SABİT yükseklikteydi ve `resizeMode` ile dolduruluyordu.
 * Kutu oranı ile karenin oranı tutmadığı için görüntü kırpılıyor; üzerine çizilen ORGAN İŞARETLERİ
 * (AI Pro / CatOrgan) kırpılmamış koordinatlara göre yerleştiği için canlı görüntüyle KAYIYORDU.
 * Bu bir tıbbi karar ekranı: işaret kayması yanlış organa bakılmasına yol açar.
 *
 * ⚠️ `aspectRatio` + `maxHeight` BİRLİKTE KULLANILMAZ: maxHeight yüksekliği kırpınca genişlik
 * %100 kaldığı için oran yine bozulur. Bunun yerine AÇIK px kutu hesaplanır.
 *
 * KARE ORANI KAYNAĞI: backend yanıtındaki `image_w`/`image_h`. Yoksa cihaz yönüne göre makul
 * varsayılan (portre 3/4, yatay 4/3) — `takePictureAsync`in width/height'ı KULLANILMAZ
 * (Android'de EXIF rotasyonu öncesi/sonrası belirsiz; backend cv2.imdecode EXIF'i yok sayar).
 */

export interface KareBoyutu {
  image_w?: number | null;
  image_h?: number | null;
}

/** Portre varsayılanı (genişlik/yükseklik). */
export const VARSAYILAN_PORTRE = 3 / 4;
/** Yatay varsayılanı. */
export const VARSAYILAN_YATAY = 4 / 3;

/** Kare oranı (genişlik / yükseklik). Geçersiz/eksik boyutta yön varsayılanına düşer. */
export function kareOrani(kare: KareBoyutu | null | undefined, portre: boolean): number {
  const w = kare?.image_w;
  const h = kare?.image_h;
  if (typeof w === "number" && typeof h === "number" && w > 0 && h > 0) return w / h;
  return portre ? VARSAYILAN_PORTRE : VARSAYILAN_YATAY;
}

/**
 * Ölçülen kap genişliğinden AÇIK px kutu üretir.
 * Yükseklik ekran yüksekliğinin `tavan` katıyla sınırlanır (yatay telefonda kutu ekranı yemesin);
 * genişlik daima yükseklik × oran → kutu TAM oranlı, dolayısıyla cover ≡ contain, kırpma yok.
 */
export function kameraKutusu(
  kutuW: number,
  oran: number,
  ekranH: number,
  tavan = 0.55
): { width: number; height: number } {
  const guvenliOran = oran > 0 ? oran : VARSAYILAN_PORTRE;
  const h = Math.min(kutuW / guvenliOran, Math.round(ekranH * tavan));
  return { width: Math.round(h * guvenliOran), height: Math.round(h) };
}
