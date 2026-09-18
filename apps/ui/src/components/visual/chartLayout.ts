// Author: mertaygn, cglrgrkn
/**
 * GRAFİK YERLEŞİM HESAPLARI — saf fonksiyonlar.  [S7 adım 2, 2026-09-04 responsive denetimi]
 * =========================================================================================
 * ÖLÇÜLEN DURUM:
 *  · `RealtimeChart` kenar boşluklarını SABİT tutuyordu: `{ top:20, right:60, bottom:40, left:60 }`.
 *    320 px'lik telefonda çizim alanı 320 − 120 = 200 px'e düşüyor, sıcaklık ekseni kapalıyken bile
 *    sağda 60 px boş yer duruyordu. Yani ekranın %37'si eksen boşluğuna gidiyordu.
 *  · Web tuvali (canvas) mantıksal pikselle kuruluyordu: DPR 2-3 olan ekranlarda çizgi ve yazı
 *    BULANIK çıkıyordu (tıbbi eğri okunurluğu).
 *
 * Hesaplar bileşenden AYRI tutulur ki DOM/canvas olmadan birim testlenebilsin.
 */

export interface Pad {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

/** Dar ekran eşiği (px): altında eksen boşlukları daraltılır. */
export const DAR_ESIK = 400;

/**
 * Eksen boşlukları GENİŞLİKTEN türetilir.
 * · Dar ekranda sol/sağ eksen 60 → 44 (etiketler "12.3" gibi 4 karakter; 44 px yeter).
 * · Sıcaklık ekseni KAPALIYSA sağ boşluk 12'ye iner — orada çizilecek etiket yok.
 */
export function hesaplaPad(width: number, showTemp: boolean): Pad {
  const dar = width < DAR_ESIK;
  return {
    top: 20,
    bottom: 40,
    left: dar ? 44 : 60,
    right: showTemp ? (dar ? 44 : 60) : 12,
  };
}

/** Çizim alanı (eksenler düşülmüş) — negatif olamaz. */
export function cizimAlani(width: number, height: number, pad: Pad) {
  return {
    genislik: Math.max(0, width - pad.left - pad.right),
    yukseklik: Math.max(0, height - pad.top - pad.bottom),
  };
}

export interface TuvalGibi {
  width: number;
  height: number;
  style?: { width?: string; height?: string };
}
export interface BaglamGibi {
  setTransform: (a: number, b: number, c: number, d: number, e: number, f: number) => void;
}

/**
 * Tuvali cihaz piksel oranına göre kurar: iç tampon DPR katı, CSS boyutu mantıksal px,
 * dönüşüm DPR ölçeğinde → çizim kodu mantıksal koordinat kullanmaya devam eder.
 * DPR üst sınırı 3: 4x ekranlarda bellek/performans bedeli okunurluk kazancını aşıyor.
 */
export function canvasBoyutla(
  canvas: TuvalGibi,
  ctx: BaglamGibi,
  w: number,
  h: number,
  dpr: number
): { dpr: number } {
  const oran = Math.min(Math.max(1, dpr || 1), 3);
  canvas.width = Math.round(w * oran);
  canvas.height = Math.round(h * oran);
  if (canvas.style) {
    canvas.style.width = `${w}px`;
    canvas.style.height = `${h}px`;
  }
  ctx.setTransform(oran, 0, 0, oran, 0, 0);
  return { dpr: oran };
}
