// Author: mertaygn
/**
 * KPI GRAFİK EKSENİ — "Son 7 Gün — Seans Sayısı" (sahip bildirimi 2026-09-12).
 * ===========================================================================
 * "bu grafiği daha belirgin ve tasarım olarak daha güzel hale getir."
 *
 * ⚠️ EN GÖZE BATAN KUSUR TASARIM DEĞİL, ANLAMDI: y ekseni "11.00 · 8.25 · 5.50 · 2.75 · 0.00"
 * yazıyordu. Seans sayısı TAM SAYIDIR; "8,25 seans" diye bir şey yoktur. Ekseni okuyan kişi
 * çeyrek seans diye bir birim olduğunu sanır ya da (daha kötüsü) okumayı bırakır.
 *
 * Sebep: `react-native-chart-kit` bölüt sayısını sabit 4 alır ve etiketi `max/4` adımlarıyla
 * üretir. 11 sessiz biçimde 2,75'lik adımlara bölünür.
 *
 * ÇÖZÜM: bölüt sayısını, en büyük değeri TAM BÖLEN bir sayı seç → her etiket tam sayı çıkar.
 */

/** Grafikte denenecek bölüt sayıları — çoktan aza (daha çok ızgara çizgisi daha okunaklı). */
const ADAYLAR = [5, 4, 3, 2] as const;

/**
 * `enBuyuk` değerini TAM BÖLEN en uygun bölüt sayısı.
 *
 * ⚠️ Bölen bulunamazsa 1 döner (tek ızgara çizgisi: 0 ve tepe). Kaba görünür ama
 * YANLIŞ GÖRÜNMEZ — ondalıklı bir "seans sayısı" göstermektense az çizgi göstermek yeğdir.
 */
export function eksenBolumSayisi(enBuyuk: number): number {
  const n = Math.floor(Number(enBuyuk) || 0);
  if (n <= 1) return 1;
  for (const s of ADAYLAR) {
    if (n % s === 0) return s;
  }
  return 1;
}

/**
 * Bar grafiğinin veri dizisinden bölüt sayısını türetir.
 *
 * ⚠️ BOŞ/SIFIR VERİDE 1: veri yokken 4 çizgi çizmek, olmayan bir ölçek uydurmak olurdu.
 */
export function barBolumSayisi(veri: readonly number[] | undefined): number {
  if (!veri || veri.length === 0) return 1;
  const enBuyuk = veri.reduce((a, b) => Math.max(a, Number(b) || 0), 0);
  return eksenBolumSayisi(enBuyuk);
}
