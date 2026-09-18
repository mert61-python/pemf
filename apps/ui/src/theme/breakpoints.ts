// Author: mertaygn, cglrgrkn
export type LayoutKind = "compact" | "phone" | "tablet" | "desktop" | "wide";

export const breakpoints = {
  compact: 0,
  phone: 480,
  tablet: 768,
  desktop: 1024,
  wide: 1440
};

/**
 * KISA YÜKSEKLİK eşiği (px) — yatay telefon ve çok küçültülmüş PC penceresi.
 * [S5, 2026-09-04] Düzen yalnız genişliğe bakıyordu; 360-430 px yükseklikte üst bar + alt bar +
 * kayan ACİL DURDUR içeriğe ~150 px bırakıyordu. Genişlik eşikleriyle KARIŞTIRILMASIN diye ayrı.
 */
export const SHORT_HEIGHT = 500;

export function getLayoutKind(width: number): LayoutKind {
  if (width >= breakpoints.wide) return "wide";
  if (width >= breakpoints.desktop) return "desktop";
  if (width >= breakpoints.tablet) return "tablet";
  if (width >= breakpoints.phone) return "phone";
  return "compact";
}
