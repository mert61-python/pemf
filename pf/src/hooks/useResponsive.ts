// Author: mertaygn, cglrgrkn
/**
 * useResponsive — düzen kararlarının TEK kaynağı  [S2+S5, 2026-09-04 responsive denetimi]
 * ======================================================================================
 * ESKİ DURUM: yalnız pencere GENİŞLİĞİ okunuyordu. İki sistemik sonucu vardı:
 *  1. Kenar çubuğu (240 px) ve içerik boşluğu düşülmediği için ızgara/kompaktlık kararları
 *     gerçek içerik alanından bağımsızdı → 768 px tablet dikeyde 352 px'lik alana 2 sütun.
 *  2. YÜKSEKLİK hiç okunmuyordu → yatay telefonda (360-430 px) üst bar + alt bar + kayan
 *     ACİL DURDUR içeriğe ~150 px bırakıyordu.
 *
 * YENİ: `contentWidth` (AppShell ölçümü, yoksa tahmin), `shellKind` (bottom/rail/sidebar),
 * `isShort/isLandscape`. `isCompact` artık İÇERİK genişliğine de bakar.
 */
import { Platform, useWindowDimensions } from "react-native";
import { getLayoutKind, SHORT_HEIGHT } from "@/theme/breakpoints";
import { COMPACT_CONTENT, estimateContentWidth, getShellKind, shellSidebarWidth } from "@/theme/layout";
import { spacing } from "@/theme/tokens";
import { useShellLayout } from "@/context/ShellLayoutContext";

export function useResponsive() {
  const { width, height } = useWindowDimensions();
  const layout = getLayoutKind(width);
  const isWeb = Platform.OS === "web";
  const isTablet = layout === "tablet";
  const isDesktop = layout === "desktop" || layout === "wide";

  // Kısa yükseklik = yatay telefon (ve çok küçültülmüş PC penceresi). Kabuk buna göre sıkışır.
  const isShort = height < SHORT_HEIGHT;
  const isLandscape = width > height;

  const shellKind = getShellKind(width, isWeb, height);
  const sidebarWidth = shellSidebarWidth(shellKind, isTablet);

  // Ölçülen değer (AppShell içinde) > tahmin (kabuk dışı ekranlar / ilk render).
  const olculen = useShellLayout();
  const contentWidth = olculen ?? estimateContentWidth(width, shellKind, isTablet, spacing.xl);

  // Düzen "kompakt" mı: dar pencere VEYA dar içerik kolonu (kenar çubuğu yüzünden).
  const isCompact = layout === "compact" || layout === "phone" || contentWidth < COMPACT_CONTENT;
  const columns = layout === "wide" ? 4 : layout === "desktop" ? 3 : layout === "tablet" ? 2 : 1;

  return {
    width,
    height,
    layout,
    columns,
    isCompact,
    isTablet,
    isDesktop,
    isShort,
    isLandscape,
    /** Yatay telefon: hem kısa hem yatay (grafik yüksekliği, 2 sütun düzenler için). */
    isLandscapePhone: isShort && isLandscape,
    shellKind,
    sidebarWidth,
    contentWidth,
    isWeb,
    isNative: !isWeb
  };
}
