/**
 * DİL SEÇİMİ (Y161) — saf kurallar: cihaz dilinin okunması, bayrak, geçerlilik. React / i18next İÇERMEZ (test edilebilir).
 *
 * Kural:
 *  - İlk açılış cihaz dilidir: `tr*` → tr, DİĞER HER ŞEY → en; okunamazsa tr.
 *  - Ayarlar'dan seçilen dil bu cihazda hatırlanır (AsyncStorage `pemf.dil`; web'de aynı anahtar `localStorage`'da). Hesaptan ve
 *    profilden BAĞIMSIZDIR, çıkışta silinmez (profil seçiminin kalıcı OLMAMASI kuralı ayrı ve değişmez).
 *  - Bayrak (`I18N_EN_ACIK`) kapalıyken etkin dil HER ZAMAN tr.
 *  - Cihaz dili `expo-localization` OLMADAN okunur (yerel modül yasak): `Intl` → `navigator.language` → `NativeModules`.
 */
import { NativeModules, Platform } from "react-native";
import { I18N_EN_ACIK } from "./bayrak";
import { etkinDilDegeri, type Dil } from "./durum";

export type { Dil };
export const DILLER: readonly Dil[] = ["tr", "en"];
export const YEDEK_DIL: Dil = "tr";
export const DIL_DEPO_ANAHTARI = "pemf.dil";

export function gecerliDil(x: unknown): Dil | null {
  return x === "tr" || x === "en" ? x : null;
}

/** Yerel ayar kodu → dil: `tr`, `tr-TR`, `tr_TR` → tr; boş / okunamayan → tr; diğer her şey (en-GB, de-DE …) → en. */
export function dileIndirge(yerel: string | null | undefined): Dil {
  const s = String(yerel ?? "").trim().toLowerCase().replace(/_/g, "-");
  if (!s) return YEDEK_DIL;
  return s === "tr" || s.startsWith("tr-") ? "tr" : "en";
}

/** Cihazın / tarayıcının yerel ayar kodu (okunamazsa null). Sıra: Intl (Hermes + tarayıcı) → navigator → yerel modül ayarı. */
export function cihazYereli(): string | null {
  try {
    const l = Intl.DateTimeFormat().resolvedOptions().locale;
    if (l) return l;
  } catch {
    /* sıradaki kaynak */
  }
  try {
    const n = (globalThis as { navigator?: { language?: string } }).navigator?.language;
    if (n) return n;
  } catch {
    /* sıradaki kaynak */
  }
  try {
    const nm = NativeModules as Record<string, any>;
    const m = nm?.I18nManager?.localeIdentifier ?? nm?.SettingsManager?.settings?.AppleLocale;
    if (m) return String(m);
  } catch {
    /* okunamadı */
  }
  return null;
}

let _bayrakTesti: boolean | null = null;

/**
 * YALNIZ TEST: bayrağı geçici açar / kapatır (`null` = gerçek bayrak). jest kurulumu i18n'i her test dosyasından ÖNCE yüklediği için
 * `jest.mock("@/i18n/bayrak")` geç kalır; EN'i deneyen testler bunu kullanır ve `afterEach`'te `null`a döndürür.
 * ⚠️ Üretim kodu ÇAĞIRMAZ — K-5 kapısı test dışı çağrıyı kırmızı yapar.
 */
export function __bayrakTestiAyarla(v: boolean | null): void {
  _bayrakTesti = v;
}

/** Bayrağın etkin değeri (üretimde `I18N_EN_ACIK`). */
export function bayrakAcik(): boolean {
  return _bayrakTesti ?? I18N_EN_ACIK;
}

/** Etkin dil: bayrak kapalıyken tr; açıkken kayıtlı seçim, yoksa cihaz dili. */
export function etkinDil(secim: unknown, yerel: string | null | undefined, enAcik: boolean = bayrakAcik()): Dil {
  if (!enAcik) return YEDEK_DIL;
  return gecerliDil(secim) ?? dileIndirge(yerel);
}

/** Ayarlar'daki "Dil / Language" seçeneği görünür mü (bayrakla aynı). */
export function dilSecimiGorunur(enAcik: boolean = bayrakAcik()): boolean {
  return enAcik;
}

/** Web'de kayıtlı seçim EŞZAMANLI (ilk karede titreme olmasın). Yerelde null — AsyncStorage zaman uyumsuz okunur. */
export function kayitliDilEszamanli(): Dil | null {
  if (Platform.OS !== "web") return null;
  try {
    return gecerliDil((globalThis as { localStorage?: Storage }).localStorage?.getItem(DIL_DEPO_ANAHTARI));
  } catch {
    return null;
  }
}

/** Gösterim yerel ayarı (`Intl` biçimleri için): tr → tr-TR, en → en-GB (24 saat, gün-ay-yıl). */
export function bicimYereli(d: Dil): string {
  return d === "en" ? "en-GB" : "tr-TR";
}

/**
 * Y295 (17-11, sahip): ekrandaki tarih / saat / sayı biçiminin yerel ayarı ETKİN DİLDEN türer — TEK yardımcı (eşleme `bicimYereli`):
 * tr → `tr-TR` (17.11.2026) · en → `en-GB` (17/11/2026, 24 saat, 1,234.56). Sabit `"tr-TR"` YAZILMAZ (İngilizce arayüzde Türkçe
 * tarih biçimi kalıyordu). Ad sıralaması (`localeCompare(…, "tr")`) ve arama katlaması (`aramaNormalize`) bunu KULLANMAZ — veri
 * Türkçe. Bileşen dışı yardımcılar da okur; bileşenler dil değişince zaten yeniden çizilir.
 */
export function etkinBicimYereli(): string {
  return bicimYereli(etkinDilDegeri());
}
