import { StyleSheet, Text, View } from "react-native";
import { Activity, Clock, HeartPulse, RadioTower } from "lucide-react-native";
import { CoilCard } from "@/components/domain/CoilCard";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { MetricCard } from "@/components/ui/MetricCard";
import { ResponsiveGrid } from "@/components/ui/ResponsiveGrid";
import { StatusPill } from "@/components/ui/StatusPill";
import { colors, spacing, typography } from "@/theme/tokens";
import { DashboardSnapshot } from "@/types/domain";

interface DashboardScreenProps {
  commandStatus: string;
  onStart: () => void;
  onStop: () => void;
  snapshot: DashboardSnapshot;
}

export function DashboardScreen({ commandStatus, onStart, onStop, snapshot }: DashboardScreenProps) {
  return (
    <>
      <View style={styles.statusRow}>
        <StatusPill label="Gateway" state={snapshot.gateway} />
        <StatusPill label="MQTT" state={snapshot.mqtt} />
        <StatusPill label="STM32" state={snapshot.stm} />
      </View>

      <ResponsiveGrid>
        <MetricCard label="Aktif Frekans" value={`${snapshot.activeTreatment.frequencyHz} Hz`} tone={colors.primary} />
        <MetricCard label="Yoğunluk" value={`${snapshot.activeTreatment.intensityMt} mT`} tone={colors.warning} />
        <MetricCard label="Kalan Süre" value={`${snapshot.activeTreatment.remainingMin} dk`} tone={colors.success} />
      </ResponsiveGrid>

      <View style={styles.heroGrid}>
        <Card style={styles.patientCard}>
          <View style={styles.cardHeader}>
            <HeartPulse color={colors.magenta} size={22} />
            <Text style={styles.cardTitle}>Hasta Özeti</Text>
          </View>
          <Text style={styles.patientName}>{snapshot.patient.name}</Text>
          <Text style={styles.body}>{snapshot.patient.species} · {snapshot.patient.breed}</Text>
          <Text style={styles.body}>Sahip: {snapshot.patient.owner}</Text>
          <Button label="Hasta Bilgisini Güncelle" variant="secondary" />
        </Card>

        <Card style={styles.treatmentCard}>
          <View style={styles.cardHeader}>
            <Clock color={colors.success} size={22} />
            <Text style={styles.cardTitle}>Aktif Seans</Text>
          </View>
          <Text style={styles.patientName}>{snapshot.activeTreatment.mode}</Text>
          <Text style={styles.body}>Parametreler gerçek zamanlı izlemeye hazır.</Text>
          <Text style={styles.commandStatus}>{commandStatus}</Text>
          <View style={styles.actions}>
            <Button label="Seansı Başlat" icon={<Activity color={colors.white} size={16} />} onPress={onStart} />
            <Button label="Acil Durdur" variant="danger" onPress={onStop} />
          </View>
        </Card>
      </View>

      <View style={styles.sectionHeader}>
        <RadioTower color={colors.primary} size={20} />
        <Text style={styles.sectionTitle}>Bobin Durumları</Text>
      </View>
      <ResponsiveGrid minItemWidth={280}>
        {snapshot.coils.map((coil) => (
          <CoilCard key={coil.id} coil={coil} />
        ))}
      </ResponsiveGrid>
    </>
  );
}

const styles = StyleSheet.create({
  statusRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.sm
  },
  heroGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.lg
  },
  patientCard: {
    flex: 1,
    gap: spacing.md,
    minWidth: 280
  },
  treatmentCard: {
    flex: 1.4,
    gap: spacing.md,
    minWidth: 280
  },
  cardHeader: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.sm
  },
  cardTitle: {
    color: colors.text,
    fontSize: typography.subtitle,
    fontWeight: "800"
  },
  patientName: {
    color: colors.text,
    fontSize: 22,
    fontWeight: "800"
  },
  body: {
    color: colors.textMuted,
    fontSize: typography.body
  },
  commandStatus: {
    color: colors.textSubtle,
    fontSize: typography.caption,
    fontWeight: "700"
  },
  actions: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.md,
    marginTop: spacing.sm
  },
  sectionHeader: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.sm
  },
  sectionTitle: {
    color: colors.text,
    fontSize: typography.subtitle,
    fontWeight: "800"
  }
});
