export type LayoutKind = "compact" | "phone" | "tablet" | "desktop" | "wide";

export const breakpoints = {
  compact: 0,
  phone: 480,
  tablet: 768,
  desktop: 1024,
  wide: 1440
};

export function getLayoutKind(width: number): LayoutKind {
  if (width >= breakpoints.wide) return "wide";
  if (width >= breakpoints.desktop) return "desktop";
  if (width >= breakpoints.tablet) return "tablet";
  if (width >= breakpoints.phone) return "phone";
  return "compact";
}
