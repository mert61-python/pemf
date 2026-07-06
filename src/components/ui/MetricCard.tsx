import { StyleSheet, Text, View } from "react-native";
import { Card } from "@/components/ui/Card";
import { colors, spacing, typography, rf, rs } from "@/theme/tokens";

interface MetricCardProps {
  label: string;
  value: string;
  tone?: string;
}

export function MetricCard({ label, value, tone = colors.primary }: MetricCardProps) {
  return (
    <Card style={styles.card}>
      <View style={[styles.marker, { backgroundColor: tone }]} />
      <Text style={styles.label}>{label}</Text>
      <Text style={styles.value}>{value}</Text>
    </Card>
  );
}

const styles = StyleSheet.create({
  card: {
    gap: spacing.sm,
    minHeight: rs(112)
  },
  marker: {
    borderRadius: 2,
    height: rs(4),
    width: rs(44)
  },
  label: {
    color: colors.textMuted,
    fontSize: typography.caption,
    fontWeight: "700"
  },
  value: {
    color: colors.text,
    fontSize: rf(26),
    fontWeight: "800"
  }
});
