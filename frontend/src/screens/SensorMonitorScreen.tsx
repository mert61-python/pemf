import { StyleSheet, Text } from "react-native";
import { Card } from "@/components/ui/Card";
import { ResponsiveGrid } from "@/components/ui/ResponsiveGrid";
import { Sparkline } from "@/components/visual/Sparkline";
import { colors, spacing, typography } from "@/theme/tokens";
import { DashboardSnapshot } from "@/types/domain";

export function SensorMonitorScreen({ snapshot }: { snapshot: DashboardSnapshot }) {
  const magnetic = snapshot.coils.map((coil) => coil.magneticMt);
  const current = snapshot.coils.map((coil) => coil.currentA);
  const temp = snapshot.coils.map((coil) => coil.objectTemp);

  return (
    <ResponsiveGrid minItemWidth={330}>
      <SensorPanel title="Manyetik Alan" unit="mT" values={magnetic} color={colors.primary} />
      <SensorPanel title="Akım" unit="A" values={current} color={colors.warning} />
      <SensorPanel title="Nesne Sıcaklığı" unit="C" values={temp} color={colors.danger} />
    </ResponsiveGrid>
  );
}

function SensorPanel({ title, unit, values, color }: { title: string; unit: string; values: number[]; color: string }) {
  const latest = values[values.length - 1] ?? 0;
  return (
    <Card style={styles.panel}>
      <Text style={styles.title}>{title}</Text>
      <Text style={[styles.value, { color }]}>{latest.toFixed(2)} {unit}</Text>
      <Sparkline values={values} color={color} />
    </Card>
  );
}

const styles = StyleSheet.create({
  panel: {
    gap: spacing.md
  },
  title: {
    color: colors.text,
    fontSize: typography.subtitle,
    fontWeight: "800"
  },
  value: {
    fontSize: 26,
    fontWeight: "800"
  }
});
