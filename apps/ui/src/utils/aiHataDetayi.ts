import i18n from "i18next";
// Author: mertaygn, cglrgrkn
/**
 * AI hata YANITINDAKİ `detail`i kullanıcıya gösterilmeden ÖNCE anlaşılır kıl — TEK KAYNAK.
 *
 * ⚠️ SAHA BULGUSU 2026-08-30: Yara analizinde kullanıcı ham "Part exceeded maximum size of
 * 1024KB" (Starlette İngilizce teknik mesajı) görüyor ve NE YAPACAĞINI anlamıyordu ("bug var
 * sandım"). 10+ AI modülü backend `detail`ini AYNEN gösteriyordu.
 *
 * Backend'in KENDİ hataları zaten Türkçe ve kullanıcı-dostu ("Görüntü çok büyük (> 25 MB)…") →
 * onlara DOKUNMA, aynen göster. Yalnız çerçeveden (Starlette/HTTP) sızan İngilizce teknik metinleri
 * eyleme dönüştür. Tanınmayan/boş → çağıranın verdiği modüle-özel varsayılan.
 *
 * (Ayrı dosya: AiHubScreen native modüller (expo-audio/camera) yüklüyor; bu saf fonksiyon jest'te
 * bağımsız test edilebilsin diye buraya taşındı.)
 */
export function aiDetayCumlesi(detail: unknown, varsayilan = i18n.t("ai.hata.analizHatasi")): string {
  const s = typeof detail === "string" ? detail.trim() : "";
  if (!s) return varsayilan;
  const alt = s.toLowerCase();
  // Boyut (Starlette "Part/Field exceeded" ya da HTTP 413): kullanıcıya EYLEM söyle.
  if (
    alt.includes("exceeded maximum size") ||
    alt.includes("part exceeded") ||
    alt.includes("field exceeded") ||
    alt.includes("payload too large") ||
    alt.includes("request entity too large")
  ) {
    return i18n.t("ai.hata.dosyaBuyuk");
  }
  // Görüntü çözümlenemedi (Pillow/decode İngilizce).
  if (alt.includes("cannot identify image") || alt.includes("unsupported image") || alt.includes("cannot decode")) {
    return i18n.t("ai.hata.goruntuOkunamadi");
  }
  // Backend Türkçe/anlaşılır mesaj verdiyse AYNEN göster; saf-ASCII (İngilizce) teknik metinse gizle.
  const turkceİpucu =
    /[çğıİöşüÇĞÖŞÜ]/.test(s) || /büyük|görüntü|hasta|hücre|dosya|geçersiz|bulunamadı|yetersiz/i.test(s);
  return turkceİpucu ? s : varsayilan;
}
