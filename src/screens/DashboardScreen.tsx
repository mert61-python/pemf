import { StyleSheet, Text, View, TouchableOpacity, ScrollView } from "react-native";
import { Activity, Clock, HeartPulse, RadioTower, Wifi } from "lucide-react-native";
import { CoilCard } from "@/components/domain/CoilCard";
import { Card } from "@/components/ui/Card";
import { MetricCard } from "@/components/ui/MetricCard";
import { ResponsiveGrid } from "@/components/ui/ResponsiveGrid";
import { StatusPill } from "@/components/ui/StatusPill";
import { NotificationCenter } from "@/components/ui/NotificationCenter";
import { SystemInfoPanel } from "@/components/domain/SystemInfoPanel";
import { GatewayStatusPanel } from "@/components/domain/GatewayStatusPanel";
import { colors, spacing, typography } from "@/theme/tokens";
import { useLiveData } from "@/context/LiveDataContext";
import { useSessionControl } from "@/hooks/useSessionControl";

export function DashboardScreen() {
  const { snapshot, wsConnected } = useLiveData();
  const { emergencyStop } = useSessionControl();

  const at = snapshot.activeTreatment;
  const coils = snapshot.coils ?? [];
  const connectedCount = coils.filter((c) => c.connected).length;
  const runningCount = coils.filter((c) => c.running).length;

  return (
    <ScrollView contentContainerStyle={styles.container} showsVerticalScrollIndicator={false}>
      {/* Connection status row */}
      <View style={styles.statusRow}>
        <StatusPill label="Gateway" state={snapshot.gateway} />
        <StatusPill label="MQTT" state={snapshot.mqtt} />
        <StatusPill label="STM32" state={snapshot.stm} />
        <View style={[styles.wsBadge, !wsConnected && styles.wsBadgeOff]}>
          <Wifi size={12} color={wsConnected ? "#22c55e" : "#f59e0b"} />
          <Text style={[styles.wsText, !wsConnected && styles.wsTextOff]}>
            {wsConnected ? "CANLI" : "OFFLINE"}
          </Text>
        </View>
      </View>

      {!wsConnected && (
        <View style={styles.offlineBanner}>
          <Text style={styles.offlineBannerText}>⚠️ Canlı bağlantı yok — gösterilen değerler güncel olmayabilir.</Text>
        </View>
      )}

      {/* Metrics */}
      <ResponsiveGrid>
        <MetricCard label="Aktif Frekans" value={`${at.frequencyHz || 0} Hz`} tone={colors.primary} />
        <MetricCard label="Yoğunluk" value={`${at.intensityMt || 0} mT`} tone={colors.warning} />
        <MetricCard label="Kalan Süre" value={`${at.remainingMin || 0} dk`} tone={colors.success} />
        <MetricCard label="Bağlı Bobin" value={`${connectedCount} / 8`} tone={colors.magenta} />
      </ResponsiveGrid>

      {/* Hero row */}
      <View style={styles.heroGrid}>
        {/* Patient card */}
        <Card style={styles.patientCard}>
          <View style={styles.cardHeader}>
            <HeartPulse color={colors.magenta} size={22} />
            <Text style={styles.cardTitle}>Hasta Özeti</Text>
          </View>
          {snapshot.patient?.name ? (
            <>
              <Text style={styles.patientName}>{snapshot.patient.name}</Text>
              <Text style={styles.body}>
                {snapshot.patient.species ?? ""} · {snapshot.patient.breed ?? ""}
              </Text>
              <Text style={styles.body}>Sahip: {snapshot.patient.owner ?? "—"}</Text>
            </>
          ) : (
            <Text style={styles.body}>Aktif hasta yok — hasta seçip seans başlatınca burada görünür.</Text>
          )}
        </Card>

        {/* Active session card */}
        <Card style={styles.treatmentCard}>
          <View style={styles.cardHeader}>
            <Clock color={at.isActive ? colors.success : colors.textMuted} size={22} />
            <Text style={styles.cardTitle}>Aktif Seans</Text>
            {at.isActive && (
              <View style={styles.activeDot} />
            )}
          </View>
          <Text style={styles.patientName}>{at.mode || "Sistem Hazır"}</Text>
          {at.isActive ? (
            <>
              <Text style={styles.body}>
                Çalışan bobin: {runningCount} | Kalan: {at.remainingMin} dk
              </Text>
              <TouchableOpacity style={styles.emergencyBtn} onPress={emergencyStop}>
                <Text style={styles.emergencyBtnText}>🚨 ACİL DURDUR</Text>
              </TouchableOpacity>
            </>
          ) : (
            <Text style={styles.body}>Kontrol panelinden seans başlatabilirsiniz.</Text>
          )}
        </Card>
      </View>

      {/* Coil grid */}
      <View style={styles.sectionHeader}>
        <RadioTower color={colors.primary} size={20} />
        <Text style={styles.sectionTitle}>Bobin Durumları</Text>
        <Text style={styles.sectionBadge}>{connectedCount}/8 Bağlı</Text>
      </View>
      {coils.length === 0 ? (
        <Text style={styles.coilEmptyText}>Bobin verisi bekleniyor… (bağlantı kurulunca görünecek)</Text>
      ) : (
        <ResponsiveGrid minItemWidth={280}>
          {coils.map((coil) => (
            <CoilCard key={coil.id} coil={coil} />
          ))}
        </ResponsiveGrid>
      )}

      {/* Bottom row: Notifications + System Info + Gateway */}
      <View style={styles.bottomGrid}>
        <View style={styles.bottomLeft}>
          <NotificationCenter maxVisible={8} compact />
        </View>
        <View style={styles.bottomRight}>
          <SystemInfoPanel />
          <GatewayStatusPanel />
        </View>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    padding: spacing.md,
    gap: spacing.md,
    paddingBottom: spacing.xxl,
    width: "100%",
    maxWidth: 1200,
    alignSelf: "center",
  },
  statusRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.sm,
    alignItems: "center",
  },
  wsBadge: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    backgroundColor: "#052e16",
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#16a34a",
  },
  wsBadgeOff: { backgroundColor: "#1c1917", borderColor: "#78350f" },
  wsText: { color: "#22c55e", fontSize: 11, fontWeight: "700" },
  wsTextOff: { color: "#f59e0b" },

  heroGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.lg },
  patientCard: { flex: 1, gap: spacing.md, minWidth: 280 },
  treatmentCard: { flex: 1.4, gap: spacing.md, minWidth: 280 },

  cardHeader: { alignItems: "center", flexDirection: "row", gap: spacing.sm },
  cardTitle: { color: colors.text, fontSize: typography.subtitle, fontWeight: "800", flex: 1 },
  activeDot: {
    width: 10, height: 10, borderRadius: 5, backgroundColor: "#22c55e",
    shadowColor: "#22c55e", shadowOpacity: 0.8, shadowRadius: 4,
  },
  patientName: { color: colors.text, fontSize: 22, fontWeight: "800" },
  body: { color: colors.textMuted, fontSize: typography.body },

  emergencyBtn: {
    backgroundColor: "#7f1d1d",
    borderRadius: 10,
    padding: spacing.md,
    alignItems: "center",
    marginTop: spacing.sm,
    borderWidth: 1,
    borderColor: "#ef4444",
  },
  emergencyBtnText: { color: "#fff", fontWeight: "800", fontSize: typography.small },

  sectionHeader: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.sm,
  },
  sectionTitle: { color: colors.text, fontSize: typography.subtitle, fontWeight: "800", flex: 1 },
  sectionBadge: {
    color: colors.textMuted,
    fontSize: typography.small,
    fontWeight: "600",
    backgroundColor: "#1e293b",
    paddingHorizontal: spacing.sm,
    paddingVertical: 3,
    borderRadius: 10,
  },

  bottomGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.md,
    marginTop: spacing.sm,
  },
  bottomLeft: { flex: 2, minWidth: 260 },
  bottomRight: { flex: 1, minWidth: 220, gap: spacing.md },
  offlineBanner: {
    backgroundColor: "#1c1917",
    borderColor: "#78350f",
    borderWidth: 1,
    borderRadius: 10,
    padding: spacing.sm,
  },
  offlineBannerText: { color: "#f59e0b", fontSize: typography.small, fontWeight: "600", textAlign: "center" },
  coilEmptyText: { color: colors.textMuted, fontSize: typography.small, textAlign: "center", paddingVertical: spacing.lg },
});
