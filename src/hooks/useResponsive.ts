import { Platform, useWindowDimensions } from "react-native";
import { getLayoutKind } from "@/theme/breakpoints";

export function useResponsive() {
  const { width, height } = useWindowDimensions();
  const layout = getLayoutKind(width);
  const isCompact = layout === "compact" || layout === "phone";
  const isTablet = layout === "tablet";
  const isDesktop = layout === "desktop" || layout === "wide";
  const columns = layout === "wide" ? 4 : layout === "desktop" ? 3 : layout === "tablet" ? 2 : 1;

  return {
    width,
    height,
    layout,
    columns,
    isCompact,
    isTablet,
    isDesktop,
    isWeb: Platform.OS === "web",
    isNative: Platform.OS !== "web"
  };
}
