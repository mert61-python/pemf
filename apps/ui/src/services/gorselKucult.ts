// Author: mertaygn
/**
 * gorselKucult — YÜKLEME ÖNCESİ görsel küçültme (web/Canvas yolu).
 *
 * ============================================================================
 * ⚠️ PLATFORM BOŞLUĞU (AI Hub planı §ADIM 1, 2026-09-12'de kapatıldı)
 * ============================================================================
 * Native tarafta `shrinkForUpload` (expo-image-manipulator) her fotoğrafı yüklemeden
 * önce 1500 px / JPEG %70'e indiriyordu. **Web tarafında hiçbir küçültme YOKTU**:
 * 14 dosya-seçici `URL.createObjectURL(file)` ile HAM dosyayı alıyordu.
 *
 * Ölçülen sonuçlar:
 *  · aynı analiz platforma göre **8× farklı** boyutta yükleniyordu,
 *  · backend (Starlette) multipart part sınırı **1 MB**'tır → web'de modern bir telefon
 *    fotoğrafı "Part exceeded maximum size of 1024KB" ile REDDEDİLİYORDU,
 *  · tünel üzerinden çalışan kurulumlarda gereksiz bellek/ağ yükü.
 *
 * ============================================================================
 * ⚠️ FAIL-OPEN — AKIŞ ASLA KIRILMAZ
 * ============================================================================
 * Canvas/decode başarısız olursa (bozuk dosya, HEIC, bellek) **orijinal dosya** döner.
 * Native taraf da aynı sözleşmeyi kullanıyor (`catch → orijinali döndür`): küçültme bir
 * OPTİMİZASYONDUR, bir kapı değil. Kullanıcının analizi, sıkıştırma yüzünden engellenmez.
 *
 * ⚠️ BÜYÜTME YOK: `min(1, ...)`. Küçük bir görseli şişirmek dosyayı büyütür, bilgi eklemez.
 */

/**
 * Yükleme öncesi uzun kenar tavanı (px).
 * ⚠️ `shrinkForUpload` ile AYNI olmalı — ayrışırsa aynı analiz platforma göre farklı
 * çözünürlükte gider ve model girdisi platforma bağımlı hale gelir.
 * Kapı: `gorselKucult.test.ts` bu sabitin ekrandaki değerle eşleştiğini ölçer.
 */
export const YUKLEME_AZAMI_KENAR = 1500;

/** Yükleme JPEG kalitesi (0-1). ⚠️ `shrinkForUpload`taki `compress: 0.7` ile AYNI. */
export const YUKLEME_JPEG_KALITESI = 0.7;

/** Bu boyutun altındaki dosyaya DOKUNULMAZ — yeniden kodlamak kaliteyi boşuna düşürür. */
export const KUCULTME_ESIGI_BAYT = 512 * 1024;

/**
 * Web `File`ını yükleme için küçültür. Başarısızlıkta ORİJİNALİ döndürür.
 *
 * @param file Kullanıcının seçtiği dosya.
 * @returns Küçültülmüş JPEG `File` ya da (dokunulmadıysa/başarısızlıkta) orijinal.
 */
export async function webIcinKucult(file: File): Promise<File> {
  try {
    // ⚠️ Zaten küçük dosyayı yeniden kodlamak SAF KAYIP: boyut kazancı yok, kalite düşer.
    if (!file || file.size <= KUCULTME_ESIGI_BAYT) return file;
    // Görsel olmayan bir şey seçildiyse dokunma (ör. PDF) — çağıran kendi doğrulamasını yapar.
    if (file.type && !file.type.startsWith("image/")) return file;

    const bitmap = await _bitmapAc(file);
    const { width, height } = bitmap;
    if (!width || !height) return file;

    const sc = Math.min(1, YUKLEME_AZAMI_KENAR / Math.max(width, height));
    if (sc >= 1) return file; // zaten tavanın altında → yeniden kodlama YOK

    const w = Math.max(1, Math.round(width * sc));
    const h = Math.max(1, Math.round(height * sc));
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    if (!ctx) return file;
    ctx.drawImage(bitmap as CanvasImageSource, 0, 0, w, h);

    const blob = await new Promise<Blob | null>((cozumle) =>
      canvas.toBlob(cozumle, "image/jpeg", YUKLEME_JPEG_KALITESI),
    );
    if (!blob) return file;
    // ⚠️ Küçültme dosyayı BÜYÜTTÜYSE orijinali koru (çok küçük/az renkli görsellerde olur).
    if (blob.size >= file.size) return file;

    const ad = file.name.replace(/\.[^.]+$/, "") + ".jpg";
    return new File([blob], ad, { type: "image/jpeg", lastModified: Date.now() });
  } catch {
    return file; // fail-open
  }
}

/** `createImageBitmap` varsa onu, yoksa `<img>` yedeğini kullan (eski WebView'lar). */
async function _bitmapAc(file: File): Promise<{ width: number; height: number }> {
  const g = globalThis as unknown as { createImageBitmap?: (b: Blob) => Promise<ImageBitmap> };
  if (typeof g.createImageBitmap === "function") {
    return await g.createImageBitmap(file);
  }
  // ⚠️ YEDEK YOL: WebView2 eski sürümlerinde `createImageBitmap` olmayabiliyor; o durumda
  // küçültmeyi tamamen bırakmak yerine klasik `<img>` çözme yolunu kullan.
  const url = URL.createObjectURL(file);
  try {
    return await new Promise((cozumle, reddet) => {
      const img = new Image();
      img.onload = () => cozumle(img);
      img.onerror = () => reddet(new Error("goruntu cozulemedi"));
      img.src = url;
    });
  } finally {
    URL.revokeObjectURL(url);
  }
}
