import { memo, useId } from "react";
import { StyleSheet, useWindowDimensions, View } from "react-native";
import Svg, { Defs, RadialGradient, Stop, Rect } from "react-native-svg";
import { colors } from "@/theme/tokens";

interface AuroraProps {
  /** 0.5 = sönük · 1 = normal · 1.4 = canlı */
  intensity?: number;
}

/**
 * Premium aurora arka planı — react-native-svg radyal-gradyan mesh (yumuşak glow; blur-lib gerekmez).
 * Ekranın en altına (içeriğin arkasına) absolute yerleştirilir. Web + native uyumlu.
 * SVG id'leri örnek-başına benzersiz (useId) → aynı anda iki aurora çakışmaz.
 */
function AuroraBackgroundImpl({ intensity = 1 }: AuroraProps) {
  const { width, height } = useWindowDimensions();
  const uid = useId().replace(/:/g, "");
  const o = (v: number) => Math.min(1, Math.max(0, v * intensity));
  return (
    <View pointerEvents="none" style={[StyleSheet.absoluteFill, styles.bg]}>
      <Svg width={width} height={height} style={StyleSheet.absoluteFill}>
        <Defs>
          <RadialGradient id={`av${uid}`} cx="16%" cy="10%" r="62%">
            <Stop offset="0%" stopColor={colors.violet} stopOpacity={o(0.4)} />
            <Stop offset="100%" stopColor={colors.violet} stopOpacity={0} />
          </RadialGradient>
          <RadialGradient id={`ab${uid}`} cx="86%" cy="92%" r="66%">
            <Stop offset="0%" stopColor={colors.primary} stopOpacity={o(0.34)} />
            <Stop offset="100%" stopColor={colors.primary} stopOpacity={0} />
          </RadialGradient>
          <RadialGradient id={`ac${uid}`} cx="97%" cy="15%" r="46%">
            <Stop offset="0%" stopColor={colors.cyan} stopOpacity={o(0.16)} />
            <Stop offset="100%" stopColor={colors.cyan} stopOpacity={0} />
          </RadialGradient>
        </Defs>
        <Rect x={0} y={0} width={width} height={height} fill={`url(#av${uid})`} />
        <Rect x={0} y={0} width={width} height={height} fill={`url(#ab${uid})`} />
        <Rect x={0} y={0} width={width} height={height} fill={`url(#ac${uid})`} />
      </Svg>
    </View>
  );
}

// #116: React.memo → parent (canlı-veri shell) her telemetri tick'inde re-render olsa da
// intensity prop'u değişmedikçe tam-ekran 3-gradyan SVG yeniden çizilmez.
export const AuroraBackground = memo(AuroraBackgroundImpl);

const styles = StyleSheet.create({
  bg: { backgroundColor: colors.bg },
});
