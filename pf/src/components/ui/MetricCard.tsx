// Author: mertaygn, cglrgrkn
import { StyleSheet, Text } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { Card } from "@/components/ui/Card";
import { colors, spacing, typography, rf, rs } from "@/theme/tokens";

interface MetricCardProps {
  label: string;
  value: string;
  tone?: string;
}

/** Hex (#RRGGBB / #RGB / #RRGGBBAA) → rgba (marker gradyanının solma ucu için). */
function withAlpha(hex: string, a: number): string {
  let h = (hex || "").replace("#", "").trim();
  if (h.length === 3) h = h.split("").map((c) => c + c).join("");
  if (h.length === 8) h = h.slice(0, 6); // #RRGGBBAA → RRGGBB (alfa çiftini at)
  // #117: geçersiz/6-haneli-olmayan hex sessizce rgba(0,0,0)/yanlış-kanal üretiyordu → güvenli
  // varsayılana düş (siyah renk üretme).
  if (!/^[0-9a-f]{6}$/i.test(h)) h = "4F8CFF";
  const n = parseInt(h, 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
}

export function MetricCard({ label, value, tone = colors.primary }: MetricCardProps) {
  return (
    <Card style={styles.card}>
      <LinearGradient
        colors={[tone, withAlpha(tone, 0.22)]}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 0 }}
        style={styles.marker}
      />
      {/* #119: tek doğru-etiketli duyuru (etiket+değer birlikte); ayrı Text düğümleri a11y'de bölünmesin. */}
      <Text style={styles.label} accessibilityElementsHidden importantForAccessibility="no">{label}</Text>
      <Text style={styles.value} accessibilityLabel={`${label}: ${value}`}>{value}</Text>
    </Card>
  );
}

const styles = StyleSheet.create({
  card: {
    gap: spacing.sm,
    minHeight: rs(112),
  },
  marker: {
    borderRadius: rs(3),
    height: rs(5),
    width: rs(46),
  },
  label: {
    color: colors.textMuted,
    fontSize: typography.caption,
    fontWeight: "700",
    letterSpacing: 0.3,
    textTransform: "uppercase",
  },
  value: {
    color: colors.text,
    fontSize: rf(27),
    fontWeight: "800",
    letterSpacing: -0.3,
    fontVariant: ["tabular-nums"],
  },
});
