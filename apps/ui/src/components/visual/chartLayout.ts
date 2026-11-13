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

/**
 * ZG-1 (sahip 13 Kasım 2026: "grafikte yakınlaştırma özelliği ve alta zaman ekseni eklenmeli, anlık saat olarak 15:27:13 gibi").
 * Zaman penceresi: tümü · son N saniye (canlı akışı İZLER) · sabit aralık (web'de grafikte sürükleyerek seçilir).
 */
export type ZamanPenceresi = { tip: "tumu" } | { tip: "son"; sn: number } | { tip: "sabit"; bas: number; son: number };

/** Verinin zaman aralığı [tMin, tMax] (saniye) + pencere → görünür [bas, son]. Veri aralığı yoksa null (indeks eksenine düşülür). */
export function gorunurAralik(tMin: number, tMax: number, p?: ZamanPenceresi): { bas: number; son: number } | null {
  if (!Number.isFinite(tMin) || !Number.isFinite(tMax) || !(tMax > tMin)) return null;
  if (!p || p.tip === "tumu") return { bas: tMin, son: tMax };
  if (p.tip === "son") return { bas: Math.max(tMin, tMax - Math.max(1, p.sn)), son: tMax };
  return p.son > p.bas ? { bas: p.bas, son: p.son } : { bas: tMin, son: tMax };
}

/** Saniye (epoch) → yerel saat "SS:DD:ss" (cihazın saati; 15:27:13 gibi). */
export function saatMetni(t: number): string {
  const d = new Date(t * 1000);
  const iki = (n: number) => String(n).padStart(2, "0");
  return `${iki(d.getHours())}:${iki(d.getMinutes())}:${iki(d.getSeconds())}`;
}

const ZAMAN_ADIMLARI_SN = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200];

/** Zaman ekseni işaretleri: okunur adım (etiketler arası en az `enAzPx` piksel), tam adım katlarında, yerel saat metniyle. */
export function zamanIsaretleri(bas: number, son: number, cizimGenisligi: number, enAzPx = 80): { t: number; metin: string }[] {
  if (!(son > bas) || !(cizimGenisligi > 0)) return [];
  const enCok = Math.max(1, Math.floor(cizimGenisligi / enAzPx));
  const adim = ZAMAN_ADIMLARI_SN.find((a) => (son - bas) / a <= enCok) ?? Math.ceil((son - bas) / enCok);
  const out: { t: number; metin: string }[] = [];
  for (let t = Math.ceil(bas / adim) * adim; t <= son + 1e-9; t += adim) out.push({ t, metin: saatMetni(t) });
  return out;
}
