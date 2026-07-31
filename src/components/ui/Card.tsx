import { PropsWithChildren } from "react";
import { StyleSheet, View, ViewStyle, StyleProp } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { colors, radius, spacing, glass, gradients, elevation } from "@/theme/tokens";

type CardVariant = "solid" | "glass" | "outline" | "gradient";

interface CardProps extends PropsWithChildren {
  style?: StyleProp<ViewStyle>;
  variant?: CardVariant;
}

/**
 * Premium kart: katmanlı gölge + üst-kenar iç-ışığı (yukarıdan aydınlatılmış his).
 * variant="glass" yarı-saydam cam (aurora/renkli arka planlarda parlar),
 * "gradient" ince yüzey gradyanı, "outline" gölgesiz çerçeve.
 */
export function Card({ children, style, variant = "solid" }: CardProps) {
  const glassy = variant === "glass";
  const outline = variant === "outline";
  const gradient = variant === "gradient";
  return (
    <View
      style={[
        styles.card,
        elevation(outline ? "sm" : "md"),
        glassy && styles.glass,
        outline && styles.outline,
        style,
      ]}
    >
      {gradient ? (
        <LinearGradient
          colors={gradients.surface}
          start={{ x: 0, y: 0 }}
          end={{ x: 0, y: 1 }}
          style={[StyleSheet.absoluteFill, styles.fill]}
          pointerEvents="none"
        />
      ) : null}
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.panel,
    borderColor: colors.border,
    borderTopColor: "rgba(255,255,255,0.09)", // üst-kenar ışığı — premium derinlik
    borderRadius: radius.card,
    borderWidth: 1,
    padding: spacing.lg,
  },
  glass: {
    backgroundColor: glass.bg,
    borderColor: glass.border,
    borderTopColor: glass.highlight,
  },
  outline: {
    backgroundColor: "transparent",
  },
  fill: { borderRadius: radius.card },
});
