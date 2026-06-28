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
import { BarChart, PieChart } from "react-native-chart-kit";

interface KpiSummary {
  totalSessions: number;
  completedSessions: number;
  stoppedSessions: number;
  avgDurationMin: number;
  modeDistribution: Record<string, number>;
  last7Days: Array<{ date: string; count: number }>;
}

export function KpiDashboardScreen() {
  const { snapshot, sensorHistory } = useLiveData();
  const [kpi, setKpi] = useState<KpiSummary>({
    totalSessions: 0,
    completedSessions: 0,
    stoppedSessions: 0,
    avgDurationMin: 0,
    modeDistribution: {},
    last7Days: [],
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    // Önce bridge'den KPI özetini çek (DB'den)
    const { serviceConfig } = require("@/services/config");
    fetch(`${serviceConfig.bridgeBaseUrl}/kpi/summary`)
      .then(r => r.json())
      .then((data: KpiSummary) => {
        if (mounted) { setKpi(data); setLoading(false); }
      })
      .catch(() => {
        // Fallback: API server'dan history statistics dene
        apiGet<any>("/history/statistics", {}).then((data) => {
          if (mounted && data) {
            setKpi(prev => ({
              ...prev,
              totalSessions: data.total_sessions ?? 0,
              completedSessions: data.completed_sessions ?? 0,
              avgDurationMin: data.avg_duration_minutes ?? 0,
            }));
            setLoading(false);
          }
        });
      });
    return () => { mounted = false; };
  }, []);

  const coils = snapshot.coils ?? [];
  const connectedCoils = coils.filter((c) => c.connected);
  const runningCoils = coils.filter((c) => c.running);

  const COIL_R = 0.5;
  const instantPowerW = runningCoils.reduce((sum, c) => sum + c.currentA * c.currentA * COIL_R, 0);
  const avgTemp = connectedCoils.length > 0
    ? connectedCoils.reduce((s, c) => s + c.objectTemp, 0) / connectedCoils.length
    : 0;
  const avgMag = runningCoils.length > 0
    ? runningCoils.reduce((s, c) => s + c.magneticMt, 0) / runningCoils.length
    : 0;

  const completionRate = kpi.totalSessions > 0
    ? Math.round((kpi.completedSessions / kpi.totalSessions) * 100)
    : null;

  const uptimePct = connectedCoils.length > 0
    ? Math.round((connectedCoils.length / 8) * 100)
    : 0;

  // Geniş ekranda maxWidth (1200) ile sınırla — grafik kartı taşmasın.
  const winW = Math.min(Dimensions.get("window").width, 1200);
  const chartWidth = winW > 768 ? winW / 2 - 40 : winW - 32;

  const chartConfig = {
    backgroundGradientFrom: "#1e293b",
    backgroundGradientTo: "#0f172a",
    color: (opacity = 1) => `rgba(124, 58, 237, ${opacity})`,
    labelColor: (opacity = 1) => `rgba(148, 163, 184, ${opacity})`,
    strokeWidth: 2,
    barPercentage: 0.5,
    useShadowColorFromDataset: false
  };

  // Son 7 gün bar chart verisi
  const last7 = kpi.last7Days.slice().reverse();
  const barData = {
    labels: last7.length > 0
      ? last7.map(d => d.date.slice(5))  // MM-DD formatı
      : ["—", "—", "—", "—", "—", "—", "—"],
    datasets: [{ data: last7.length > 0 ? last7.map(d => d.count) : [0, 0, 0, 0, 0, 0, 0] }]
  };

  // Mod dağılımı pie verisi
  const PIE_COLORS = ["#7c3aed", "#ec4899", "#0ea5e9", "#f59e0b", "#22c55e"];
  const modeEntries = Object.entries(kpi.modeDistribution);
  const pieData = modeEntries.length > 0
    ? modeEntries.map(([name, count], i) => ({
        name, population: count,
        color: PIE_COLORS[i % PIE_COLORS.length],
        legendFontColor: "#94a3b8", legendFontSize: 12
      }))
    : [{ name: "Veri Yok", population: 1, color: "#334155", legendFontColor: "#94a3b8", legendFontSize: 12 }];

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.sectionTitle}>📊 Klinik Göstergeler & Analitik</Text>
      <ResponsiveGrid>
        <MetricCard
          label="Toplam Seans"
          value={loading ? "…" : String(kpi.totalSessions)}
          tone={colors.primary}
        />
        <MetricCard
          label="Tamamlanma Oranı"
          value={loading ? "…" : completionRate !== null ? `${completionRate}%` : "—"}
          tone={colors.success}
        />
        <MetricCard
          label="Ort. Süre"
          value={loading ? "…" : `${Math.round(kpi.avgDurationMin)} dk`}
          tone={colors.violet}
        />
        <MetricCard
          label="Dur. / Hata"
          value={loading ? "…" : String(kpi.stoppedSessions)}
          tone={colors.magenta}
        />
      </ResponsiveGrid>

      <Text style={styles.sectionTitle}>⚡ Anlık Cihaz Durumu</Text>
      <ResponsiveGrid>
        <MetricCard label="Anlık Güç" value={`${instantPowerW.toFixed(1)} W`} tone={colors.cyan} />
        <MetricCard label="Bağlı Bobin" value={`${connectedCoils.length} / 8`} tone={colors.primary} />
        <MetricCard label="Çalışan Bobin" value={`${runningCoils.length} / 8`} tone={colors.success} />
        <MetricCard label="Cihaz Oranı" value={`${uptimePct}%`} tone={colors.violet} />
        <MetricCard label="Ort. Sıcaklık" value={`${avgTemp.toFixed(1)} °C`} tone={colors.warning} />
        <MetricCard label="Ort. Manyetik" value={`${avgMag.toFixed(2)} mT`} tone={colors.cyan} />
      </ResponsiveGrid>

      <Text style={styles.sectionTitle}>📈 Performans Grafikleri</Text>
      <ResponsiveGrid minItemWidth={300}>
        <Card style={styles.chartCard}>
          <Text style={styles.chartTitle}>Son 7 Gün — Seans Sayısı</Text>
          <BarChart
            data={barData}
            width={chartWidth}
            height={220}
            chartConfig={chartConfig}
            style={{ marginVertical: 8, borderRadius: 8 }}
            yAxisLabel=""
            yAxisSuffix=""
          />
        </Card>
        <Card style={styles.chartCard}>
          <Text style={styles.chartTitle}>Tedavi Modu Dağılımı</Text>
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
  container: { padding: spacing.md, gap: spacing.md, paddingBottom: spacing.xxl, width: "100%", maxWidth: 1200, alignSelf: "center" },
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
