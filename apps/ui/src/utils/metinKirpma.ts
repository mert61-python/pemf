// Author: mertaygn
/**
 * METİN KIRPMA SEZGİSİ — "üç noktadan sonrası okunamıyor" (sahip bildirimi 2026-09-12).
 * ====================================================================================
 * "bildirim sığmayınca üç noktadan sonrasını kullanıcı hiçbir şekilde okuyamıyor"
 * "ai analiz detaylarında yine üç nokta sorunu ve devamını göremeyiş ... bunların üzerine
 *  tıklayınca tam metni gösterme özelliği kazandırılmalı"
 *
 * ═══════════════════════════════════════════════════════════════════════════════
 * ⚠️ NEDEN SEZGİ, NEDEN GERÇEK ÖLÇÜM DEĞİL
 * ═══════════════════════════════════════════════════════════════════════════════
 * "Bu metin gerçekten kırpıldı mı?" sorusunun kesin cevabı yalnız yerleşimden gelir
 * (`onTextLayout` → satır sayısı). Ama o olay `numberOfLines` uygulanmışken platformdan
 * platforma FARKLI davranır (bazı yerlerde yalnız GÖRÜNEN satırları bildirir) ve bu ürün
 * WebView'da koşuyor — yani ölçüme güvenmek, ölçümün sessizce yanıldığı bir platformda
 * "genişlet" ipucunu HİÇ göstermemek demek olurdu. Sahibin şikâyeti tam olarak budur.
 *
 * ⚠️ BU YÜZDEN YETENEK SEZGİYE BAĞLI DEĞİLDİR: `GenisletilebilirMetin` HER ZAMAN
 * dokunulabilir. Sezgi yalnız "… Tümünü gör" İPUCUNUN gösterilip gösterilmeyeceğini
 * belirler. Sezgi yanılırsa en kötü sonuç kozmetiktir (gereksiz bir ipucu); kullanıcı
 * metne yine de ulaşır. Tersi — kırpılmış metinde ipucu göstermemek — sahibin bildirdiği
 * arızanın ta kendisi olurdu.
 */

/**
 * Bir satıra sığdığı VARSAYILAN karakter sayısı.
 *
 * ⚠️ Kasten DÜŞÜK (dar sütunlara göre): sezgi, kırpılmayı KAÇIRMAKTANSA fazladan ipucu
 * göstermeye meyilli olmalı (bkz. dosya başlığı). 320 px'lik dar bir kartta ~34 karakter
 * sığar; geniş ekranda daha çok sığar ama orada da fazladan bir ipucu zarar vermez.
 */
export const SATIR_BASINA_KARAKTER = 34;

/**
 * `metin`, `satir` satıra sığmayıp kırpılmış OLABİLİR mi?
 *
 * Açık satır sonları da sayılır: üç kısa satırlık bir metin, `satir=2` ile kırpılır ama
 * karakter sayısı eşiğin altında kalabilir.
 */
export function kirpikOlabilir(
  metin: unknown,
  satir: number,
  satirBasinaKarakter: number = SATIR_BASINA_KARAKTER,
): boolean {
  const s = typeof metin === "string" ? metin : String(metin ?? "");
  if (!s) return false;
  if (satir <= 0) return false;
  // Açık satır sonları: `satir` taneden fazla satır varsa kesin kırpılır.
  if (s.split("\n").length > satir) return true;
  return s.length > satir * satirBasinaKarakter;
}
