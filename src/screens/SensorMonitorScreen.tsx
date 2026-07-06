/**
 * SensorMonitorScreen — Gerçek Zamanlı Sensör Grafikleri
 *
 * Python sensor_data_window.py'nin React karşılığı.
 * Çift eksenli (mT + °C) canlı grafik, 8 bobin seçimi, anlık değerler.
 */
import { useState, useCallback } from "react";
import {
  ScrollView,
  Text,
  View,
  StyleSheet,
  TouchableOpacity,
} from "react-native";
import { colors, spacing, typography, rf, rs } from "@/theme/tokens";
import { useLiveData } from "@/context/LiveDataContext";
import { RealtimeChart } from "@/components/visual/RealtimeChart";

// Grafikteki çizgi renkleriyle BİREBİR aynı kategorik palet (legend/filtre butonu + stat kartı tutarlılığı).
const COIL_COLORS = [
  "#EF4444", "#3B82F6", "#22C55E", "#F97316",
  "#A855F7", "#06B6D4", "#EC4899", "#EAB308",
];

export function SensorMonitorScreen() {
  const { snapshot, sensorHistory, wsConnected } = useLiveData();
  // Grafik genişliği, sarmalayıcının GERÇEK genişliğinden (onLayout) ölçülür → her telefon/
  // yön için container'a tam oturur; tablet/geniş ekranda 1200'de sınırlanır.
  const [chartW, setChartW] = useState(0);
  const coils = snapshot.coils ?? [];

  // Initially show all connected coils
  const [visibleCoils, setVisibleCoils] = useState<Set<number>>(new Set([1, 2, 3, 4, 5, 6, 7, 8]));
  const [showMagnetic, setShowMagnetic] = useState(true);
  const [showTemp, setShowTemp] = useState(true);

  const toggleCoil = useCallback((id: number) => {
    setVisibleCoils((prev) => {
      const next = new Set(prev);
      if (next.has(id)) { next.delete(id); } else { next.add(id); }
      return next;
    });
  }, []);

  return (
    <ScrollView contentContainerStyle={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <View>
          <Text style={styles.title}>📡 Sensör Monitörü</Text>
          <Text style={styles.subtitle}>
            Gerçek zamanlı manyetik alan ve sıcaklık izleme
          </Text>
        </View>
        <View style={[styles.wsBadge, !wsConnected && styles.wsBadgeOff]}>
          <View style={[styles.wsDot, !wsConnected && styles.wsDotOff]} />
          <Text style={styles.wsText}>{wsConnected ? "CANLI" : "BAĞLANTI YOK"}</Text>
        </View>
      </View>

      {/* Chart controls */}
      <View style={styles.controlRow}>
        <Text style={styles.controlLabel}>Eksen:</Text>
        <TouchableOpacity
          style={[styles.axisChip, showMagnetic && styles.axisChipMag]}
          onPress={() => setShowMagnetic((v) => !v)}
        >
          <Text style={styles.axisChipText}>● Manyetik (mT)</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.axisChip, showTemp && styles.axisChipTemp]}
          onPress={() => setShowTemp((v) => !v)}
        >
          <Text style={styles.axisChipText}>-- Sıcaklık (°C)</Text>
        </TouchableOpacity>
      </View>

      {/* Coil filter buttons */}
      <View style={styles.coilBtnRow}>
        {Array.from({ length: 8 }, (_, i) => i + 1).map((id) => {
          const coil = coils.find((c) => c.id === id);
          const connected = coil?.connected ?? false;
          const active = visibleCoils.has(id);
          const color = COIL_COLORS[id - 1];
          return (
            <TouchableOpacity
              key={id}
              style={[
                styles.coilBtn,
                active && { backgroundColor: color + "33", borderColor: color },
                !connected && styles.coilBtnOffline,
              ]}
              onPress={() => toggleCoil(id)}
            >
              <View style={[styles.coilBtnDot, { backgroundColor: active ? color : "#475569" }]} />
              <Text style={[styles.coilBtnText, active && { color }]}>
                Bobin {id}
              </Text>
            </TouchableOpacity>
          );
        })}
      </View>

      {/* Main chart */}
      <View style={styles.chartArea} onLayout={(e) => setChartW(e.nativeEvent.layout.width)}>
        {chartW > 0 && (
          <RealtimeChart
            history={sensorHistory}
            visibleCoils={visibleCoils}
            showMagnetic={showMagnetic}
            showTemp={showTemp}
            width={Math.min(chartW, 1200)}
            height={280}
          />
        )}
      </View>

      {/* Coil stats grid */}
      <Text style={styles.statsTitle}>Anlık Değerler</Text>
      <View style={styles.statsGrid}>
        {Array.from({ length: 8 }, (_, i) => i + 1).map((id) => {
          const coil = coils.find((c) => c.id === id);
          const pts = sensorHistory[id] ?? [];
          const latest = pts[pts.length - 1];
          const color = COIL_COLORS[id - 1];
          return (
            <CoilStatCard
              key={id}
              id={id}
              color={color}
              connected={coil?.connected ?? false}
              running={coil?.running ?? false}
              magneticMt={latest?.magneticMt ?? coil?.magneticMt ?? 0}
              objectTemp={latest?.objectTemp ?? coil?.objectTemp ?? 0}
              currentA={latest?.currentA ?? coil?.currentA ?? 0}
              frequencyHz={coil?.frequencyHz ?? 0}
            />
          );
        })}
      </View>
    </ScrollView>
  );
}

function CoilStatCard({
  id, color, connected, running,
  magneticMt, objectTemp, currentA, frequencyHz,
}: {
  id: number; color: string; connected: boolean; running: boolean;
  magneticMt: number; objectTemp: number; currentA: number; frequencyHz: number;
}) {
  return (
    <View style={[styles.statCard, { borderColor: connected ? color + "44" : "#1e293b" }]}>
      <View style={styles.statCardHeader}>
        <View style={[styles.statDot, { backgroundColor: running ? "#22c55e" : connected ? color : "#334155" }]} />
        <Text style={styles.statCardTitle}>Bobin {id}</Text>
      </View>
      {connected ? (
        <>
          <Metric label="Manyetik" value={`${magneticMt.toFixed(2)} mT`} color="#22c55e" />
          <Metric label="Sıcaklık" value={`${objectTemp.toFixed(1)} °C`} color={objectTemp > 45 ? "#ef4444" : "#fb923c"} />
          <Metric label="Akım" value={`${currentA.toFixed(3)} A`} color="#60a5fa" />
          <Metric label="Frekans" value={frequencyHz > 0 ? `${frequencyHz} Hz` : "—"} color="#a78bfa" />
        </>
      ) : (
        <Text style={styles.offlineText}>Bağlı değil</Text>
      )}
    </View>
  );
}

function Metric({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <View style={styles.metric}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={[styles.metricValue, { color }]}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { padding: spacing.md, gap: spacing.md, paddingBottom: spacing.xxl, width: "100%", maxWidth: rs(1200), alignSelf: "center" },
  chartArea: { width: "100%", alignItems: "center" },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-start",
    flexWrap: "wrap",
    gap: spacing.sm,
  },
  title: { color: colors.text, fontSize: typography.subtitle, fontWeight: "800" },
  subtitle: { color: colors.textMuted, fontSize: typography.small },
  wsBadge: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    backgroundColor: "#052e16",
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: "#16a34a",
  },
  wsBadgeOff: { backgroundColor: "#1c1917", borderColor: "#78350f" },
  wsDot: { width: rs(8), height: rs(8), borderRadius: 4, backgroundColor: "#22c55e" },
  wsDotOff: { backgroundColor: "#f59e0b" },
  wsText: { color: "#22c55e", fontWeight: "700", fontSize: typography.small },

  controlRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    flexWrap: "wrap",
  },
  controlLabel: { color: colors.textMuted, fontSize: typography.small, fontWeight: "600" },
  axisChip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: 20,
    backgroundColor: "#1e293b",
    borderWidth: 1,
    borderColor: "#334155",
  },
  axisChipMag: { borderColor: "#22c55e", backgroundColor: "#052e16" },
  axisChipTemp: { borderColor: "#fb923c", backgroundColor: "#431407" },
  axisChipText: { color: colors.text, fontSize: typography.small, fontWeight: "600" },

  coilBtnRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.xs,
  },
  coilBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    paddingHorizontal: spacing.sm,
    paddingVertical: 6,
    borderRadius: 8,
    backgroundColor: "#1e293b",
    borderWidth: 1,
    borderColor: "#334155",
  },
  coilBtnOffline: { opacity: 0.4 },
  coilBtnDot: { width: rs(6), height: rs(6), borderRadius: 3 },
  coilBtnText: { color: colors.textMuted, fontSize: rf(12), fontWeight: "600" },

  statsTitle: {
    color: colors.text,
    fontSize: typography.body,
    fontWeight: "700",
    marginTop: spacing.xs,
  },
  statsGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.sm,
  },
  statCard: {
    minWidth: rs(140),
    flex: 1,
    backgroundColor: "#0a0f1e",
    borderRadius: 12,
    padding: spacing.md,
    borderWidth: 1,
    gap: spacing.xs,
  },
  statCardHeader: { flexDirection: "row", alignItems: "center", gap: 6, marginBottom: 4 },
  statDot: { width: rs(8), height: rs(8), borderRadius: 4 },
  statCardTitle: { color: colors.text, fontWeight: "700", fontSize: typography.small },
  metric: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  metricLabel: { color: colors.textMuted, fontSize: rf(11) },
  metricValue: { fontWeight: "700", fontSize: rf(12), fontVariant: ["tabular-nums"] as any },
  offlineText: { color: "#475569", fontSize: typography.small, textAlign: "center", paddingVertical: spacing.sm },
});
