import { Dimensions } from "react-native";

// ── RESPONSIVE ÖLÇEK ─────────────────────────────────────────────────────────
// Tüm boyutlandırma (spacing/typography/radius + bileşenlerdeki ham sayılar) bu
// fabrikadan geçer → her telefon boyutunda orantılı görünür. Referans genişlik 375px
// (yaygın telefon). Çok küçük (~320) ve çok büyük (tablet) ekranlarda aşırıya kaçmasın
// diye clamp'lenir. Uygulama açılışında cihaz genişliğinden bir kez hesaplanır (portre).
const BASE_WIDTH = 375;
const _screenW = Math.min(Dimensions.get("window").width, Dimensions.get("window").height); // kısa kenar (portre genişliği)
const _rawScale = (_screenW || BASE_WIDTH) / BASE_WIDTH;
// 0.85 (küçük telefon) … 1.30 (büyük telefon/küçük tablet) arası
const SCALE = Math.min(Math.max(_rawScale, 0.85), 1.30);

/** responsive size — ham pikseli cihaza göre ölçekle (yuvarlanmış). Hard-coded boyut yerine kullan. */
export function rs(size: number): number {
  return Math.round(size * SCALE);
}

/** responsive font — metinler için biraz daha yumuşak ölçek (aşırı büyümesin). */
export function rf(size: number): number {
  const softScale = 1 + (SCALE - 1) * 0.7;
  return Math.round(size * softScale);
}

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
};

export const typography = {
  title: rf(24),
  subtitle: rf(16),
  body: rf(14),
  caption: rf(12),
  small: rf(11)
};

export const shadows = {
  panel: {
    shadowColor: "#000",
    shadowOpacity: 0.24,
    shadowRadius: 18,
    shadowOffset: { width: 0, height: 10 },
    elevation: 6
  }
};
