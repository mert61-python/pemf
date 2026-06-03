import { ReactNode } from "react";
import { StyleSheet, Text, View } from "react-native";
import { Activity, RadioTower, Thermometer, Zap } from "lucide-react-native";
import { Card } from "@/components/ui/Card";
import { StatusPill } from "@/components/ui/StatusPill";
import { colors, spacing, typography } from "@/theme/tokens";
import { CoilStatus } from "@/types/domain";

export function CoilCard({ coil }: { coil: CoilStatus }) {
  return (
    <Card style={styles.card}>
      <View style={styles.header}>
        <View>
          <Text style={styles.title}>Bobin {coil.id}</Text>
          <Text style={styles.sub}>{coil.connected ? "Gateway senkron" : "Veri bekleniyor"}</Text>
        </View>
        <StatusPill label={coil.running ? "Aktif" : coil.connected ? "Hazır" : "Offline"} state={coil.running ? "online" : coil.connected ? "warning" : "offline"} />
      </View>

      <View style={styles.metrics}>
        <MiniMetric icon={<RadioTower color={colors.primary} size={16} />} label="Frekans" value={`${coil.frequencyHz} Hz`} />
        <MiniMetric icon={<Zap color={colors.warning} size={16} />} label="Duty" value={`${coil.dutyCycle}%`} />
        <MiniMetric icon={<Activity color={colors.cyan} size={16} />} label="Alan" value={`${coil.magneticMt.toFixed(2)} mT`} />
        <MiniMetric icon={<Thermometer color={colors.danger} size={16} />} label="Sıcaklık" value={`${coil.objectTemp.toFixed(1)} C`} />
      </View>
    </Card>
  );
}

function MiniMetric({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <View style={styles.mini}>
      {icon}
      <View>
        <Text style={styles.miniLabel}>{label}</Text>
        <Text style={styles.miniValue}>{value}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    gap: spacing.lg
  },
  header: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    gap: spacing.md
  },
  title: {
    color: colors.text,
    fontSize: typography.subtitle,
    fontWeight: "800"
  },
  sub: {
    color: colors.textMuted,
    fontSize: typography.caption,
    marginTop: spacing.xs
  },
  metrics: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.sm
  },
  mini: {
    backgroundColor: colors.bgAlt,
    borderColor: colors.border,
    borderRadius: 8,
    borderWidth: 1,
    flexBasis: "48%",
    flexDirection: "row",
    gap: spacing.sm,
    minHeight: 58,
    padding: spacing.md
  },
  miniLabel: {
    color: colors.textMuted,
    fontSize: typography.small,
    fontWeight: "700"
  },
  miniValue: {
    color: colors.text,
    fontSize: typography.body,
    fontWeight: "800",
    marginTop: 2
  }
});
