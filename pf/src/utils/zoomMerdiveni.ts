// Author: mertaygn
/**
 * ZOOM MERDİVENİ — tam ekranda yakınlaştırma basamakları. [AI Hub planı, ADIM 4 / G12]
 * ===================================================================================
 * ⚠️ SABİT `[1, 2, 4]` MERDİVENİ YETMİYOR — ÖLÇÜLDÜ (2026-09-10 demo turu):
 * 700×540'lık launcher asgari penceresinde sahne genişliği ~600 px. 6048 px genişliğindeki
 * bir mozaikte %400 bile gömülü metni yalnız 9,2 px'e çıkarır — hâlâ okunmaz. Oysa aynı
 * kareyi 1:1 kaynak piksele açmak metni pencereden BAĞIMSIZ olarak ~12 px yapar.
 *
 * Bu yüzden merdivenin son basamağı **kaynak pikseline kilitlidir**: `k = image_w / kutu.w`.
 * ⚠️ Hiçbir basamak 1:1'i AŞMAZ — üstüne çıkmak yalnız JPEG blokları büyütür, bilgi eklemez
 * (kullanıcı "daha fazla yakınlaştırdım ama netleşmedi" der; zoom'a güveni biter).
 *
 * ⚠️ 4096 px SINIRI: Android'de OpenGL doku sınırı yaygın olarak 4096 px'tir; daha büyük bir
 * kareyi 1:1 çizmeye çalışmak boş/siyah doku üretir (sessiz arıza). Kenarı 4096'yı aşan
 * görsellerde 1:1 basamağı GİZLENİR — var olmayan bir yetenek vaat edilmez.
 */

/** Android OpenGL doku sınırı — bunu aşan kenarda 1:1 basamağı gizlenir. */
export const DOKU_SINIRI_PX = 4096;
/** Taban basamaklar (kaynak-bağımsız). */
export const TABAN_BASAMAKLAR = [1, 2];
/** İki basamağın "aynı" sayılacağı tolerans (yuvarlama gürültüsü). */
export const BASAMAK_TOLERANSI = 0.02;

export interface MerdivenGirdisi {
  /** Kodlanan karenin genişliği (backend `image_w`). */
  kaynakW?: number | null;
  /** Kodlanan karenin yüksekliği — 4096 kontrolü için (uzun kenar). */
  kaynakH?: number | null;
  /** Sahnedeki kutu genişliği (px). */
  kutuW: number;
}

/**
 * 1:1 (kaynak piksel) oranı — yoksa `null`.
 *
 * ⚠️ TEK KAYNAK: hem merdiveni kuran hem de etiketi yazan kod bunu okur. İlk yazımda etiket
 * "son basamak tam sayı değilse 1:1'dir" diye TAHMİN ediyordu; 3000/600 = 5,0 gibi tam sayılı
 * bir 1:1'i "%500" diye yazıyordu (testte yakalandı). Tahmin değil, hesap.
 *
 * @returns `kaynakW / kutuW`, ya da: boyut bilinmiyorsa / kaynak zaten sığıyorsa /
 *          uzun kenar `DOKU_SINIRI_PX`'i aşıyorsa `null`.
 */
export function birebirOrani({ kaynakW, kaynakH, kutuW }: MerdivenGirdisi): number | null {
  const w = typeof kaynakW === "number" ? kaynakW : 0;
  const h = typeof kaynakH === "number" ? kaynakH : 0;
  if (!(w > 0) || !(kutuW > 0)) return null;
  if (Math.max(w, h) > DOKU_SINIRI_PX) return null;
  const oran = w / kutuW;
  return oran > 1 + BASAMAK_TOLERANSI ? oran : null;
}

/**
 * Yakınlaştırma basamakları (1 = sahneye sığdırılmış hâli).
 *
 * @returns Artan sırada, tekrarsız basamaklar. Son basamak mümkünse 1:1 kaynak pikseldir.
 *
 * ⚠️ `kaynakW` bilinmiyorsa (eski backend / `image_w` yok) yalnız taban basamaklar döner —
 * uydurma bir 1:1 basamağı GÖSTERİLMEZ.
 */
export function zoomBasamaklari(girdi: MerdivenGirdisi): number[] {
  const birebir = birebirOrani(girdi);
  if (birebir !== null) {
    // ⚠️ 1:1'i AŞAN taban basamaklar atılır — bilgi eklemeyen büyütme sunulmaz.
    return [...TABAN_BASAMAKLAR.filter((b) => b < birebir - BASAMAK_TOLERANSI), birebir];
  }
  const w = typeof girdi.kaynakW === "number" ? girdi.kaynakW : 0;
  const h = typeof girdi.kaynakH === "number" ? girdi.kaynakH : 0;
  // Boyut BİLİNİYOR ve kaynak kutuya zaten sığıyorsa yakınlaştıracak bir şey yok.
  if (w > 0 && girdi.kutuW > 0 && Math.max(w, h) <= DOKU_SINIRI_PX) return [1];
  return [...TABAN_BASAMAKLAR];
}

/** Basamak listesinde bir sonraki (sarma YOK — sınırda kalır). */
export function sonrakiBasamak(basamaklar: number[], simdiki: number): number {
  const i = basamaklar.findIndex((b) => Math.abs(b - simdiki) < BASAMAK_TOLERANSI);
  if (i < 0) return basamaklar[0] ?? 1;
  return basamaklar[Math.min(i + 1, basamaklar.length - 1)] ?? simdiki;
}

/** Basamak listesinde bir önceki (sarma YOK). */
export function oncekiBasamak(basamaklar: number[], simdiki: number): number {
  const i = basamaklar.findIndex((b) => Math.abs(b - simdiki) < BASAMAK_TOLERANSI);
  if (i < 0) return basamaklar[0] ?? 1;
  return basamaklar[Math.max(i - 1, 0)] ?? simdiki;
}

/**
 * "%100" / "%200" / "1:1" etiketi.
 *
 * @param birebir `birebirOrani()` sonucu (yoksa `null`).
 *
 * ⚠️ "1:1" ETİKETİ ÖNEMLİ: "%500" kullanıcıya hiçbir şey söylemez; "1:1" ise "daha fazlası yok,
 * gerçek piksellere bakıyorsun" der — zoom'un neden orada durduğunu açıklar.
 */
export function basamakEtiketi(deger: number, birebir: number | null): string {
  if (birebir !== null && Math.abs(deger - birebir) < BASAMAK_TOLERANSI) return "1:1";
  return `%${Math.round(deger * 100)}`;
}
