// Author: mertaygn, cglrgrkn
/**
 * GA (istem 53) A3 — CANLI 3B ALAN HARİTASI: sunucunun `alan_haritasi` iletisini (sürüm 1) çözen SAF yardımcılar.
 * ==============================================================================================================
 * Sunucu (`servers/canli_alan_hesapci.py`) kabin cam içini 20 mm ızgarayla örnekler: tepe |B| (mT) değerleri 8 bit (0..254 × ölçek),
 * 255 = alan tablosunun DIŞI (gösterilmez), C sırası x → y → z. Çerçeve "kabin" (backend): orijin cam içi merkez, +X önden bakanın
 * SOLU, +Y yukarı, +Z ARKAYA. En alt katman taban camının 5 mm üstü (plaka sıvı ortası).
 *
 * YALNIZ GÖSTERİM — "model tahmini, ölçüm değil" (13-11 doğrulaması: plaka bölgesinde ölçülen / model ≈ 1,15–1,25). Hiçbir sürüş kararı
 * bu değerlerden alınmaz.
 */
import { etkinBicimYereli } from "@/i18n/dil";

export type AlanDurumu =
  | "tamam"
  | "sifir"
  | "kalibrasyonYok"
  | "kalibrasyonBozuk"
  | "kalibrasyonEski"
  | "eslemeDogrulanmadi"
  | "modelYok"
  | "modelBozuk"
  | "hata";

export type AlanUyarisi = "dutyKirpildi" | "frekansKalibrasyonDisi";

/** Sunucu iletisinin verisi (`alan_haritasi`, sürüm 1). Yalnız `tamam` durumunda ızgara alanları dolu. */
export interface AlanHaritasiVerisi {
  surum: number;
  durum: AlanDurumu | string;
  zaman: number;
  modelTahmini: boolean;
  kalibrasyon?: string;
  izgara?: { kok: number[]; adim: number; boyut: number[]; cerceve: string; camIc?: number[] };
  deger?: string;
  olcek?: number;
  yok?: number;
  enYuksek?: { mT: number; konum: number[] } | null;
  bobinler?: { bobin: number; frekans: number; duty: number; faz: number }[];
  uyarilar?: string[];
  hesapMs?: number;
}

/** Çözülmüş harita: `kod[(ix * ny + iy) * nz + iz]`, 255 = yok. */
export interface CozulmusHarita {
  kok: [number, number, number];
  adim: number;
  boyut: [number, number, number];
  kod: Uint8Array;
  olcek: number;
  yok: number;
}

export type Katman = "taban" | "orta" | "tavan";
export const KATMANLAR: Katman[] = ["taban", "orta", "tavan"];

const _B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

/** Base64 → bayt (RN'de `atob` her motorda yok — bağımlılıksız çözücü). Geçersiz karakter → null. */
export function base64Coz(metin: string): Uint8Array | null {
  const s = metin.replace(/=+$/, "");
  if (s.length % 4 === 1) return null;
  const out = new Uint8Array(Math.floor((s.length * 3) / 4));
  let bit = 0;
  let tampon = 0;
  let j = 0;
  for (let i = 0; i < s.length; i++) {
    const v = _B64.indexOf(s[i]);
    if (v < 0) return null;
    tampon = (tampon << 6) | v;
    bit += 6;
    if (bit >= 8) {
      bit -= 8;
      out[j++] = (tampon >> bit) & 0xff;
    }
  }
  return out;
}

/** `tamam` iletisini çözer; eksik / tutarsız (boyut × değer uzunluğu) iletide null — bozuk ileti haritayı ÇİZDİRMEZ. */
export function haritayiCoz(v: AlanHaritasiVerisi | null | undefined): CozulmusHarita | null {
  if (!v || v.durum !== "tamam" || !v.izgara || typeof v.deger !== "string") return null;
  const { kok, adim, boyut } = v.izgara;
  if (!Array.isArray(kok) || kok.length !== 3 || !Array.isArray(boyut) || boyut.length !== 3) return null;
  if (!boyut.every((n) => Number.isInteger(n) && n > 0) || !(adim > 0)) return null;
  const kod = base64Coz(v.deger);
  if (!kod || kod.length !== boyut[0] * boyut[1] * boyut[2]) return null;
  return {
    kok: [kok[0], kok[1], kok[2]],
    adim,
    boyut: [boyut[0], boyut[1], boyut[2]],
    kod,
    olcek: typeof v.olcek === "number" && v.olcek > 0 ? v.olcek : 0,
    yok: typeof v.yok === "number" ? v.yok : 255,
  };
}

/** Katman → y indeksi: taban = en alt (plaka), orta = ortanın altındaki, tavan = en üst. */
export function katmanIndeksi(h: CozulmusHarita, katman: Katman): number {
  const ny = h.boyut[1];
  if (katman === "taban") return 0;
  if (katman === "tavan") return ny - 1;
  return Math.floor((ny - 1) / 2);
}

/** Bir hücre: ekran satır / sütunu → kabin konumu (mm) + değer (mT; tablo dışı → null). */
export interface KesitHucresi {
  satir: number;
  sutun: number;
  x: number;
  y: number;
  z: number;
  mT: number | null;
}

/**
 * Yatay kesit, ÜSTTEN bakış (ön AŞAĞIDA): ekran sütunu soldan sağa = önden bakanın solundan sağına (+X SOLDA → sütun 0 = en büyük X),
 * ekran satırı yukarıdan aşağıya = arkadan öne (satır 0 = en büyük Z, arka cam). Döner: satır × sütun hücreleri.
 */
export function kesit(h: CozulmusHarita, iy: number): KesitHucresi[][] {
  const [nx, ny, nz] = h.boyut;
  const satirlar: KesitHucresi[][] = [];
  for (let satir = 0; satir < nz; satir++) {
    const iz = nz - 1 - satir;
    const hucreler: KesitHucresi[] = [];
    for (let sutun = 0; sutun < nx; sutun++) {
      const ix = nx - 1 - sutun;
      const k = h.kod[(ix * ny + iy) * nz + iz];
      hucreler.push({
        satir,
        sutun,
        x: h.kok[0] + ix * h.adim,
        y: h.kok[1] + iy * h.adim,
        z: h.kok[2] + iz * h.adim,
        mT: k === h.yok ? null : k * h.olcek,
      });
    }
    satirlar.push(hucreler);
  }
  return satirlar;
}

/** Kesitin en büyük değeri (tablo dışı hariç); boşsa 0. */
export function kesitEnBuyuk(satirlar: KesitHucresi[][]): number {
  let m = 0;
  for (const s of satirlar) for (const h of s) if (h.mT !== null && h.mT > m) m = h.mT;
  return m;
}

/** Renk ölçeği (0 → 1): koyu mavi → camgöbeği → sarı → kırmızı (renk körlüğüne dayanıklı sıra, açık / koyu temada okunur). */
const _DURAKLAR: [number, [number, number, number]][] = [
  [0, [30, 41, 99]],
  [0.35, [14, 165, 233]],
  [0.7, [250, 204, 21]],
  [1, [220, 38, 38]],
];

export function renk(oran: number): string {
  const t = Math.min(1, Math.max(0, Number.isFinite(oran) ? oran : 0));
  let i = 0;
  while (i < _DURAKLAR.length - 2 && t > _DURAKLAR[i + 1][0]) i++;
  const [t0, c0] = _DURAKLAR[i];
  const [t1, c1] = _DURAKLAR[i + 1];
  const u = (t - t0) / (t1 - t0);
  const c = c0.map((v, j) => Math.round(v + (c1[j] - v) * u));
  return `rgb(${c[0]}, ${c[1]}, ${c[2]})`;
}

/** mT gösterimi: 2 ondalık, etkin dilin biçimi (Y295: tr → 1,07 · en → 1.07). */
export function mTBicimle(deger: number): string {
  return deger.toLocaleString(etkinBicimYereli(), { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
