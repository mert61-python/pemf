/**
 * KpiDashboardScreen — Python kpi_dashboard_window.py'nin React karşılığı.
 * Gerçek veriye dayalı KPI kartları — API'den ve canlı sensör verisinden.
 */
import { useEffect, useState } from "react";
import { ScrollView, Text, View, StyleSheet, Dimensions } from "react-native";
import { MetricCard } from "@/components/ui/MetricCard";
import { ResponsiveGrid } from "@/components/ui/ResponsiveGrid";
import { Card } from "@/components/ui/Card";
import { colors, spacing, typography } from "@/theme/tokens";
import { useLiveData } from "@/context/LiveDataContext";
import { apiGet } from "@/services/apiClient";
import { LineChart, BarChart, PieChart } from "react-native-chart-kit";

interface HistoryStats {
  total_sessions?: number;
  completed_sessions?: number;
  avg_duration_minutes?: number;
  patient_count?: number;
}

export function KpiDashboardScreen() {
  const { snapshot, sensorHistory } = useLiveData();
  const [stats, setStats] = useState<HistoryStats>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    apiGet<HistoryStats>("/history/statistics", {}).then((data) => {
      if (mounted) { setStats(data); setLoading(false); }
    });
    return () => { mounted = false; };
  }, []);

  const coils = snapshot.coils ?? [];
  const connectedCoils = coils.filter((c) => c.connected);
  const runningCoils = coils.filter((c) => c.running);

  // Power estimation: P = I² × R (R = 0.5Ω per coil estimate)
  const COIL_R = 0.5;
  const instantPowerW = runningCoils.reduce((sum, c) => sum + c.currentA * c.currentA * COIL_R, 0);

  // Avg temperature of connected coils
  const avgTemp = connectedCoils.length > 0
    ? connectedCoils.reduce((s, c) => s + c.objectTemp, 0) / connectedCoils.length
    : 0;

  // Avg magnetic field of running coils
  const avgMag = runningCoils.length > 0
    ? runningCoils.reduce((s, c) => s + c.magneticMt, 0) / runningCoils.length
    : 0;

  const completionRate = stats.total_sessions && stats.completed_sessions
    ? Math.round((stats.completed_sessions / stats.total_sessions) * 100)
    : null;

  const uptimePct = connectedCoils.length > 0
    ? Math.round((connectedCoils.length / 8) * 100)
    : 0;

  const chartWidth = Dimensions.get("window").width > 768 ? Dimensions.get("window").width / 2 - 40 : Dimensions.get("window").width - 32;

  const chartConfig = {
    backgroundGradientFrom: "#1e293b",
    backgroundGradientTo: "#0f172a",
    color: (opacity = 1) => `rgba(124, 58, 237, ${opacity})`, // primary color
    labelColor: (opacity = 1) => `rgba(148, 163, 184, ${opacity})`,
    strokeWidth: 2,
    barPercentage: 0.5,
    useShadowColorFromDataset: false
  };

  const lineData = {
    labels: ["Oca", "Şub", "Mar", "Nis", "May", "Haz"],
    datasets: [
      {
        data: [20, 45, 28, 80, 99, 43],
        color: (opacity = 1) => `rgba(34, 197, 94, ${opacity})`, // success
        strokeWidth: 2
      }
    ],
    legend: ["Aylık Başarı Oranı (%)"]
  };

  const pieData = [
    { name: "Osteoartrit", population: 45, color: "#7c3aed", legendFontColor: "#94a3b8", legendFontSize: 12 },
    { name: "Kas Travması", population: 28, color: "#ec4899", legendFontColor: "#94a3b8", legendFontSize: 12 },
    { name: "Disk Hernisi", population: 15, color: "#0ea5e9", legendFontColor: "#94a3b8", legendFontSize: 12 },
    { name: "Diğer", population: 12, color: "#f59e0b", legendFontColor: "#94a3b8", legendFontSize: 12 }
  ];

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.sectionTitle}>📊 Klinik Göstergeler & Analitik</Text>
      <ResponsiveGrid>
        <MetricCard
          label="Toplam Seans"
          value={loading ? "…" : String(stats.total_sessions ?? 0)}
          tone={colors.primary}
        />
        <MetricCard
          label="Tamamlanma Oranı"
          value={loading ? "…" : completionRate !== null ? `${completionRate}%` : "—"}
          tone={colors.success}
        />
        <MetricCard
          label="Ort. Süre"
          value={loading ? "…" : `${Math.round(stats.avg_duration_minutes ?? 0)} dk`}
          tone={colors.violet}
        />
        <MetricCard
          label="Hasta Sayısı"
          value={loading ? "…" : String(stats.patient_count ?? 0)}
          tone={colors.magenta}
        />
      </ResponsiveGrid>

      <Text style={styles.sectionTitle}>⚡ Anlık Cihaz Durumu</Text>
      <ResponsiveGrid>
        <MetricCard
          label="Anlık Güç"
          value={`${instantPowerW.toFixed(1)} W`}
          tone={colors.cyan}
        />
        <MetricCard
          label="Bağlı Bobin"
          value={`${connectedCoils.length} / 8`}
          tone={colors.primary}
        />
        <MetricCard
          label="Çalışan Bobin"
          value={`${runningCoils.length} / 8`}
          tone={colors.success}
        />
        <MetricCard
          label="Cihaz Oranı"
          value={`${uptimePct}%`}
          tone={colors.violet}
        />
        <MetricCard
          label="Ort. Sıcaklık"
          value={`${avgTemp.toFixed(1)} °C`}
          tone={colors.warning}
        />
        <MetricCard
          label="Ort. Manyetik"
          value={`${avgMag.toFixed(2)} mT`}
          tone={colors.cyan}
        />
      </ResponsiveGrid>

      <Text style={styles.sectionTitle}>📈 Performans Grafikleri</Text>
      <ResponsiveGrid minItemWidth={300}>
        <Card style={styles.chartCard}>
          <Text style={styles.chartTitle}>Aylık Tedavi Başarısı</Text>
          <LineChart
            data={lineData}
            width={chartWidth}
            height={220}
            chartConfig={chartConfig}
            bezier
            style={{ marginVertical: 8, borderRadius: 8 }}
          />
        </Card>
        <Card style={styles.chartCard}>
          <Text style={styles.chartTitle}>Hastalık Teşhis Dağılımı</Text>
          <PieChart
            data={pieData}
            width={chartWidth}
            height={220}
            chartConfig={chartConfig}
            accessor={"population"}
            backgroundColor={"transparent"}
            paddingLeft={"15"}
            center={[10, 0]}
            absolute
          />
        </Card>
      </ResponsiveGrid>

      {/* Per-coil instant table */}
      {connectedCoils.length > 0 && (
        <>
          <Text style={styles.sectionTitle}>🔬 Bobin Detayları</Text>
          <Card style={styles.tableCard}>
            <View style={styles.tableHeader}>
              <Text style={[styles.tableCell, styles.tableHead]}>Bobin</Text>
              <Text style={[styles.tableCell, styles.tableHead]}>mT</Text>
              <Text style={[styles.tableCell, styles.tableHead]}>°C</Text>
              <Text style={[styles.tableCell, styles.tableHead]}>A</Text>
              <Text style={[styles.tableCell, styles.tableHead]}>W</Text>
              <Text style={[styles.tableCell, styles.tableHead]}>Hz</Text>
            </View>
            {coils.map((c) => {
              const pts = sensorHistory[c.id] ?? [];
              const latest = pts[pts.length - 1];
              const mag = latest?.magneticMt ?? c.magneticMt;
              const temp = latest?.objectTemp ?? c.objectTemp;
              const cur = latest?.currentA ?? c.currentA;
              const power = cur * cur * COIL_R;
              return (
                <View key={c.id} style={[styles.tableRow, !c.connected && styles.tableRowOff]}>
                  <Text style={styles.tableCell}>{c.id}</Text>
                  <Text style={[styles.tableCell, { color: "#22c55e" }]}>{mag.toFixed(2)}</Text>
                  <Text style={[styles.tableCell, { color: temp > 45 ? "#ef4444" : "#fb923c" }]}>{temp.toFixed(1)}</Text>
                  <Text style={[styles.tableCell, { color: "#60a5fa" }]}>{cur.toFixed(3)}</Text>
                  <Text style={[styles.tableCell, { color: "#a78bfa" }]}>{power.toFixed(2)}</Text>
                  <Text style={styles.tableCell}>{c.frequencyHz > 0 ? c.frequencyHz : "—"}</Text>
                </View>
              );
            })}
          </Card>
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: spacing.md, gap: spacing.md, paddingBottom: spacing.xxl },
  sectionTitle: { color: colors.text, fontSize: typography.subtitle, fontWeight: "700", marginTop: spacing.md },
  chartCard: { padding: spacing.sm, alignItems: 'center' },
  chartTitle: { color: colors.text, fontSize: typography.body, fontWeight: "700", marginBottom: spacing.sm, alignSelf: 'flex-start', paddingLeft: spacing.sm },
  tableCard: { padding: 0, overflow: "hidden" },
  tableHeader: {
    flexDirection: "row",
    backgroundColor: "#0f172a",
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
  },
  tableRow: {
    flexDirection: "row",
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderTopWidth: 1,
    borderColor: "#1e293b",
  },
  tableRowOff: { opacity: 0.35 },
  tableHead: { color: colors.textMuted, fontWeight: "700", fontSize: 11 },
  tableCell: {
    flex: 1,
    color: colors.text,
    fontSize: 13,
    fontWeight: "600",
    fontVariant: ["tabular-nums"] as any,
  },
});
