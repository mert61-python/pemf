// Author: mertaygn
/**
 * KALAN JETON HAKKI — arayüz rozeti (sahip isteği 2026-09-13).
 *
 * ⚠️ SÖZLEŞME: backend ASLA uydurma bir sayı döndürmez. Üç durum vardır ve arayüz üçünü
 * BİRBİRİNDEN AYIRMAK zorundadır:
 *
 *   { etkin: false }                 → ücretlendirme KAPALI  → rozet HİÇ ÇİZİLMEZ
 *   { etkin: true, bilinmiyor: true} → okunamadı (çevrimdışı) → "—" göster
 *   { etkin: true, kalan: N }        → gerçek bakiye          → sayıyı göster
 *
 * ⚠️ "0 jeton" YAZMAK, bilinmeyen durumun karşılığı DEĞİLDİR. Bugün canlıda ücretlendirme
 * kapalı ve kimsenin bakiye satırı yok; rozet "0" deseydi operatör hakkının bittiğini sanırdı.
 * Aynısı çevrimdışı klinik için de geçerli — bu ürün internetsiz çalışır.
 */
import { apiGet } from "@/services/apiClient";

/** Backend `GET /api/jeton/bakiye` yanıtı (servers/jeton.py::bakiye_ozeti). */
export interface JetonBakiyesi {
  etkin: boolean;
  bilinmiyor?: boolean;
  sebep?: "kimlik_yok" | "cevrimdisi" | string;
  /** Ön ödemeli modelde kalan toplam (aylık hak + satın alınan). */
  kalan?: number;
  aylikHak?: number;
  satinAlinan?: number;
  /** Kullandıkça öde modelinde bakiye YOKTUR; faturalanmamış borç gösterilir. */
  borc?: number;
  borcTavani?: number;
  odemeModeli?: "on_odemeli" | "kullandikca" | string;
  /** İşlem başına maliyet ("1 analiz kaç jeton" ipucu için). */
  maliyet?: Record<string, number>;
  /** Çevrimdışı biriken, henüz uzlaşmamış tüketim sayısı. */
  bekleyen?: number;
}

/** Ücretlendirme kapalı kabul edilen güvenli varsayılan — rozet çizilmez. */
export const JETON_KAPALI: JetonBakiyesi = { etkin: false };

export async function jetonBakiyesiGetir(): Promise<JetonBakiyesi> {
  // `silent`: rozet arka planda tazelenir; başarısızlık kullanıcıya toast olarak ATILMAZ
  // (bakiye okunamaması bir ARIZA değil, bilgi eksikliğidir — "—" yeterli sinyal).
  const veri = await apiGet<JetonBakiyesi | null>("/jeton/bakiye", null, { silent: true });
  if (!veri || typeof veri !== "object") {
    // ⚠️ Uç hiç cevap vermediyse KAPALI say. "bilinmiyor" demek, eski backend'lerde
    // (uç yokken) her kullanıcıya kalıcı bir "—" rozeti gösterirdi.
    return JETON_KAPALI;
  }
  return veri;
}

/**
 * Rozette görünecek metin. Tek yer — ekranlar kendi biçimlemesini YAZMASIN
 * (bu depoda "aynı kural N yerde" tekrar eden arıza sınıfı).
 */
export function bakiyeMetni(b: JetonBakiyesi | null | undefined): string | null {
  if (!b || !b.etkin) return null;              // kapalı → rozet yok
  if (b.bilinmiyor) return "—";                  // okunamadı → sayı UYDURMA
  if (b.odemeModeli === "kullandikca") {
    return typeof b.borc === "number" ? `${b.borc} kullanım` : "—";
  }
  return typeof b.kalan === "number" ? String(b.kalan) : "—";
}

/** Bakiye azaldığında rozet rengi değişsin (uyarı eşiği). */
export function bakiyeDurumu(b: JetonBakiyesi | null | undefined): "yok" | "bilinmiyor" | "normal" | "az" | "bitti" {
  if (!b || !b.etkin) return "yok";
  if (b.bilinmiyor) return "bilinmiyor";
  if (b.odemeModeli === "kullandikca") {
    // Borç tavanına yaklaşmak, bakiyenin bitmesiyle aynı sonucu doğurur.
    const tavan = b.borcTavani ?? 0;
    const borc = b.borc ?? 0;
    if (tavan && borc >= tavan) return "bitti";
    if (tavan && borc >= tavan * 0.9) return "az";
    return "normal";
  }
  const kalan = b.kalan ?? 0;
  if (kalan <= 0) return "bitti";
  // ⚠️ EŞİK GEREKÇESİ: en pahalı tek işlem AI Pro seansı = 5 jeton. 5'in altına düşen
  // kullanıcı bir sonraki seansı BAŞLATAMAZ; uyarının orada başlaması gerekir.
  if (kalan < 5) return "az";
  return "normal";
}
