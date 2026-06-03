import { StyleSheet, Text, View } from "react-native";
import { Card } from "@/components/ui/Card";
import { colors, spacing, typography } from "@/theme/tokens";

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
    minHeight: 112
  },
  marker: {
    borderRadius: 2,
    height: 4,
    width: 44
  },
  label: {
    color: colors.textMuted,
    fontSize: typography.caption,
    fontWeight: "700"
  },
  value: {
    color: colors.text,
    fontSize: 26,
    fontWeight: "800"
  }
});
