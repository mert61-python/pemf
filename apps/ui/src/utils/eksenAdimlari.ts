// Author: mertaygn, cglrgrkn
/**
 * Y306 (sahip 19-11 tezgâh denemesi, madde 4a): seans detayı grafiklerinin eksenleri eşit bölünmüş ham aralıkla çiziliyordu — dar
 * aralıkta (1,35–1,38 mT) 2 basamağa yuvarlanan etiket YİNELENİYOR ("1.35" iki kez), dakika ekseni 0 / 2 / 5 / 7 / 10 düzensizdi.
 * Kural: adım 1 / 2 / 5 × 10^k ("düzgün"), eksen sınırları adımın katlarına genişler, etiket basamağı adımdan türer (en az `enAzBasamak`)
 * → komşu iki etiket aynı metne YUVARLANMAZ. Biçim (ondalık ayırıcı) çağıranda `ondalikMetni` ile — dile göre.
 */
export type Eksen = {
  /** Eksenin alt / üst sınırı (adımın katları; veri aralığını kapsar). */
  min: number;
  max: number;
  adim: number;
  /** Etiketlerin ondalık basamağı (adımın basamağı, en az `enAzBasamak`). */
  basamak: number;
  /** Etiketlenecek değerler, `min`den `max`a adım adım. */
  degerler: number[];
};

/** [`alt`, `ust`] veri aralığı için en çok ~`azamiAralik` bölmeli düzgün eksen. Eşit / geçersiz aralık ±1 açılır. */
export function eksenAdimlari(alt: number, ust: number, azamiAralik = 4, enAzBasamak = 0): Eksen {
  let a = Number.isFinite(alt) ? alt : 0;
  let u = Number.isFinite(ust) ? ust : a + 1;
  if (u < a) [a, u] = [u, a];
  if (u === a) {
    a -= 1;
    u += 1;
  }
  const ham = (u - a) / Math.max(1, azamiAralik);
  const us = Math.pow(10, Math.floor(Math.log10(ham)));
  const oran = ham / us;
  const adim = (oran <= 1 ? 1 : oran <= 2 ? 2 : oran <= 5 ? 5 : 10) * us;
  const min = Math.floor(a / adim + 1e-9) * adim;
  const max = Math.ceil(u / adim - 1e-9) * adim;
  const basamak = Math.max(enAzBasamak, -Math.floor(Math.log10(adim) + 1e-9), 0);
  const n = Math.round((max - min) / adim);
  const degerler = Array.from({ length: n + 1 }, (_, i) => Number((min + i * adim).toFixed(basamak + 3)));
  return { min, max, adim, basamak, degerler };
}
