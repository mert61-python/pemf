// Author: mertaygn, cglrgrkn
import { Dimensions, Platform } from "react-native";
import type { ViewStyle } from "react-native";
import { breakpoints } from "@/theme/breakpoints";

// ── RESPONSIVE ÖLÇEK ─────────────────────────────────────────────────────────
// Tüm boyutlandırma (spacing/typography/radius + bileşenlerdeki ham sayılar) bu
// fabrikadan geçer → her telefon boyutunda orantılı görünür. Referans genişlik 375px
// (yaygın telefon). Çok küçük (~320) ve çok büyük (tablet) ekranlarda aşırıya kaçmasın
// diye clamp'lenir. Uygulama açılışında cihaz genişliğinden bir kez hesaplanır (portre).
const BASE_WIDTH = 375;

/**
 * ÖLÇEK TAVANI — ortama göre.  [S1, 2026-09-04 denetimi · sahip kararı: %110]
 * ÖLÇÜLEN DURUM: tek tavan (1,30) vardı ve kısa kenarı 488 px'i geçen HER yüzey (tablet, WebView2
 * penceresi, LAN tarayıcısı, DPI'lı dizüstü) ona yapışıyordu → kenar çubuğu 322 px, gövde yazısı
 * 17 px, `maxWidth: rs(1100)` 1430 px. PC'de "telefon büyütmesi" görünümünün ve tablet dikeyde
 * içeriğe 352 px kalmasının kökeni buydu.
 * ⚠️ TELEFON FORMÜLÜ BİREBİR KORUNUR (native kısa kenar < 600) → APK'da sıfır fark.
 * GERİ ALMA: `OLCEK_TAVAN_BUYUK_EKRAN = 1.30` (tek satır) → eski davranış.
 */
export const OLCEK_TAVAN_BUYUK_EKRAN = 1.1;
export const OLCEK_TAVAN_TELEFON = 1.3;
/** Native'de "büyük ekran" sınırı = Android sw600dp tablet sınırı. */
const NATIVE_BUYUK_KISA_KENAR = 600;

const _win = Dimensions.get("window");
const _screenW = Math.min(_win.width, _win.height) || BASE_WIDTH; // kısa kenar (portre genişliği)
// Web'de PC penceresi hiçbir zaman 480 px'in altına inmez; telefon tarayıcısı (LAN) telefon
// formülünde kalsın diye eşik `breakpoints.phone`.
const _buyukEkran = Platform.OS === "web" ? _screenW >= breakpoints.phone : _screenW >= NATIVE_BUYUK_KISA_KENAR;
const SCALE = Math.min(Math.max(_screenW / BASE_WIDTH, 0.85), _buyukEkran ? OLCEK_TAVAN_BUYUK_EKRAN : OLCEK_TAVAN_TELEFON);
/** Etkin ölçek (test ve kapı için dışa aktarılır). */
export const OLCEK = SCALE;

/** responsive size — ham pikseli cihaza göre ölçekle (yuvarlanmış). Hard-coded boyut yerine kullan. */
export function rs(size: number): number {
  return Math.round(size * SCALE);
}

/** responsive font — metinler için biraz daha yumuşak ölçek (aşırı büyümesin). */
export function rf(size: number): number {
  const softScale = 1 + (SCALE - 1) * 0.7;
  return Math.round(size * softScale);
}

/**
 * DOKUNMA HEDEFİ TABANLARI — ölçekle KÜÇÜLMEZ.  [S3, 2026-09-04 responsive denetimi]
 * `rs(44)` 320 px telefonda 38 px'e iniyordu: tam da dokunmanın en zor olduğu cihazda hedef
 * WCAG/Android alt sınırının altına düşüyordu. Taban `Math.max` ile korunur, büyük ekranda büyür.
 */
export const touch = {
  /** Birincil dokunma hedefi (düğme, ikon-düğme, satır). */
  min: Math.max(44, rs(44)),
  /** Çip/segment gibi ikincil hedefler. */
  sm: Math.max(40, rs(40)),
  /** Standart hitSlop. */
  slop: { top: 8, bottom: 8, left: 8, right: 8 },
  /**
   * Komşu hedefler arası boşluğa göre GÜVENLİ hitSlop: kural `hitSlop ≤ gap/2`.
   * (Bobin seçicide 8 px hitSlop + 3 px gap ile dokunma alanları üst üste biniyordu → yanlış bobin.)
   */
  slopFor(gap: number) {
    const v = Math.max(0, Math.floor(gap / 2));
    return { top: v, bottom: v, left: v, right: v };
  },
};

/**
 * EKRAN-KONTEYNER GENİŞLİK TAVANLARI — ÖLÇEKSİZ (CSS px).  [S1, 2026-09-04]
 * `maxWidth: rs(1100)` PC'de 1430 px'e çıkıyordu: "en fazla 1100 px" niyetinin tam tersi.
 * maxWidth bir tavandır, telefon-içi orantı değil → `rs()` ile ÇARPILMAZ.
 */
export const layoutMax = { icerik: 1100, genis: 1200, aiHub: 980, ayar: 900, modal: 900 } as const;

/**
 * SİSTEM YAZI ÖLÇEĞİ TAVANI (sahip kararı 2026-09-04: 1,2).  [S6]
 * `allowFontScaling={false}` ASLA kullanılmaz — görme zorluğu olan operatörün tercihi tamamen
 * kapatılmaz, yalnız tavanlanır. Varsayılan `fonts.ts::injectFont` içinde uygulanır.
 */
export const MAX_FONT_SCALE = 1.2;

export const colors = {
  bg: "#121827",
  bgAlt: "#182033",
  panel: "#202A42",
  panelSoft: "#26324F",
  border: "#34415F",
  text: "#F7FAFC",
  textMuted: "#AAB6CE",
  textSubtle: "#75829B",
  primary: "#4F8CFF",
  primarySoft: "#213A68",
  success: "#22C55E",
  successSoft: "#183B2A",
  warning: "#F59E0B",
  warningSoft: "#493414",
  danger: "#EF4444",
  dangerSoft: "#481F28",
  cyan: "#22D3EE",
  violet: "#8B5CF6",
  magenta: "#EC4899",
  white: "#FFFFFF"
};

export const spacing = {
  xs: rs(4),
  sm: rs(8),
  md: rs(12),
  lg: rs(16),
  xl: rs(24),
  xxl: rs(32)
};

export const radius = {
  sm: rs(6),
  md: rs(8),
  lg: rs(12),
  xl: rs(20),
  full: 9999,
  card: rs(16), // PREMIUM: yumuşak kart yarıçapı
  btn: rs(13),  // PREMIUM: buton yarıçapı
};

export const typography = {
  title: rf(24),
  subtitle: rf(16),
  body: rf(14),
  caption: rf(12),
  small: rf(11)
};

export const shadows = {
  panel: { shadowColor: "#000", shadowOpacity: 0.24, shadowRadius: 18, shadowOffset: { width: 0, height: 10 }, elevation: 6 },
  // PREMIUM: elevation ölçeği
  sm: { shadowColor: "#000", shadowOpacity: 0.30, shadowRadius: 6, shadowOffset: { width: 0, height: 2 }, elevation: 3 },
  md: { shadowColor: "#000", shadowOpacity: 0.40, shadowRadius: 14, shadowOffset: { width: 0, height: 8 }, elevation: 8 },
  lg: { shadowColor: "#000", shadowOpacity: 0.50, shadowRadius: 26, shadowOffset: { width: 0, height: 16 }, elevation: 14 },
  // PREMIUM: renkli ışıltılar (CTA/aktif öğeler öne çıksın)
  glowPrimary: { shadowColor: colors.primary, shadowOpacity: 0.55, shadowRadius: 20, shadowOffset: { width: 0, height: 6 }, elevation: 10 },
  glowDanger: { shadowColor: colors.danger, shadowOpacity: 0.50, shadowRadius: 20, shadowOffset: { width: 0, height: 6 }, elevation: 10 },
  glowSuccess: { shadowColor: colors.success, shadowOpacity: 0.45, shadowRadius: 18, shadowOffset: { width: 0, height: 6 }, elevation: 9 },
};

// Web'de RN shadow* prop'ları yerine boxShadow — renkli glow web'de de görünür.
const webShadow: Record<keyof typeof shadows, string> = {
  panel: "0 10px 18px rgba(0,0,0,0.24)",
  sm: "0 1px 2px rgba(0,0,0,0.35)",
  md: "0 6px 16px rgba(0,0,0,0.40), 0 2px 5px rgba(0,0,0,0.30)",
  lg: "0 18px 40px rgba(0,0,0,0.50), 0 6px 14px rgba(0,0,0,0.32)",
  glowPrimary: "0 8px 26px rgba(79,140,255,0.50)",
  glowDanger: "0 8px 26px rgba(239,68,68,0.42)",
  glowSuccess: "0 8px 24px rgba(34,197,94,0.36)",
};

/** Platforma uygun gölge/ışıltı: native shadow* prop'ları, web'de boxShadow. */
export function elevation(key: keyof typeof shadows): ViewStyle {
  return Platform.OS === "web" ? ({ boxShadow: webShadow[key] } as ViewStyle) : (shadows[key] as ViewStyle);
}

// ── PREMIUM: gradyanlar (expo-linear-gradient `colors` prop'u — [başlangıç, bitiş]) ──
export const gradients = {
  primary: ["#6EA0FF", "#3466D6"] as [string, string],
  primaryDeep: ["#4F8CFF", "#2F63D6"] as [string, string],
  danger: ["#F98A84", "#DC2626"] as [string, string],
  success: ["#5BE38B", "#16A34A"] as [string, string],
  violet: ["#A78BFA", "#7C3AED"] as [string, string],
  cyan: ["#67E8F9", "#0891B2"] as [string, string],
  surface: ["#1E273F", "#161D30"] as [string, string],
  sheen: ["rgba(255,255,255,0.16)", "rgba(255,255,255,0)"] as [string, string],
};

// ── PREMIUM: cam yüzey (yarı-saydam + üst-kenar iç ışık) ──
export const glass = {
  bg: "rgba(24,32,52,0.55)",
  bgStrong: "rgba(24,32,52,0.72)",
  border: "rgba(255,255,255,0.09)",
  highlight: "rgba(255,255,255,0.10)",
};

// ── PREMIUM: hareket token'ları (built-in Animated; ileride reanimated) ──
export const motion = {
  fast: 140,
  base: 220,
  slow: 380,
  pressScale: 0.97,
  spring: { damping: 15, stiffness: 210, mass: 0.7 },
};
