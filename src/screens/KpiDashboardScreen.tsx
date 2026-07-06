/**
 * KpiDashboardScreen — Python kpi_dashboard_window.py'nin React karşılığı.
 * Gerçek veriye dayalı KPI kartları — API'den ve canlı sensör verisinden.
 */
import { useEffect, useState } from "react";
import { ScrollView, Text, View, StyleSheet } from "react-native";
import { MetricCard } from "@/components/ui/MetricCard";
import { ResponsiveGrid } from "@/components/ui/ResponsiveGrid";
import { Card } from "@/components/ui/Card";
import { colors, spacing, typography, rf, rs } from "@/theme/tokens";
import { useLiveData } from "@/context/LiveDataContext";
import { apiGet } from "@/services/apiClient";
import { BarChart, PieChart } from "react-native-chart-kit";

interface KpiSummary {
  totalSessions: number;
  completedSessions: number;
  stoppedSessions: number;
  avgDurationMin: number;
  modeDistribution: Record<string, number>;
  last7Days: { date: string; count: number }[];
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
    // KPI özetini auth'lu (X-API-Key) + timeout'lu apiGet ile çek — uzaktan (tünel,
    // PEMF_REQUIRE_AUTH=1) ham fetch 401 alıp bozuluyordu. apiGet hata/401'de null döner.
    apiGet<KpiSummary | null>("/kpi/summary", null, { silent: true }).then((data) => {
      if (!mounted) return;
      if (data && typeof data.totalSessions === "number") {
        setKpi(data);
        setLoading(false);
        return;
      }
      // Fallback: /history/statistics (alan adları farklı → hepsini dene)
      apiGet<any>("/history/statistics", null, { silent: true }).then((s) => {
        if (!mounted) return;
        if (s) {
          setKpi(prev => ({
            ...prev,
            totalSessions: s.total_sessions ?? 0,
            completedSessions: s.completed_sessions ?? 0,
            avgDurationMin: s.avg_duration_minutes ?? s.average_duration ?? 0,
          }));
        }
        setLoading(false);
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

  // Grafik genişliği kartın GERÇEK iç genişliğinden (onLayout) ölçülür → her telefon/
  // yoğunluk/yön ve tek/çift-kolon gridde kart sınırına TAM oturur. Sabit Dimensions
  // hesabı kartın kendi padding'ini kaçırıp grafiğin kutudan taşmasına yol açıyordu.
  const [chartW, setChartW] = useState(0);

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
      ? last7.map(d => {
          // Güvenli MM-DD: backend string 'YYYY-MM-DD' bekleniyor ama sayı/epoch/ISO gelirse
          // ham .slice(5) ya yanlış etiket ya da (sayıda) TypeError → KPI beyaz ekran veriyordu.
          const raw: any = (d as any)?.date;
          if (typeof raw === "number") {
            const dt = new Date(raw < 1e12 ? raw * 1000 : raw);
            return `${String(dt.getMonth() + 1).padStart(2, "0")}-${String(dt.getDate()).padStart(2, "0")}`;
          }
          const s = String(raw ?? "");
          const m = s.match(/\d{4}-(\d{2}-\d{2})/);
          return m ? m[1] : (s.length >= 5 ? s.slice(5) : (s || "—"));
        })
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
          <View style={styles.chartInner} onLayout={(e) => setChartW(e.nativeEvent.layout.width)}>
            {chartW > 0 && (
              <BarChart
                data={barData}
                width={chartW}
                height={220}
                chartConfig={chartConfig}
                style={styles.chart}
                yAxisLabel=""
                yAxisSuffix=""
              />
            )}
          </View>
        </Card>
        <Card style={styles.chartCard}>
          <Text style={styles.chartTitle}>Tedavi Modu Dağılımı</Text>
          <View style={styles.chartInner} onLayout={(e) => setChartW(e.nativeEvent.layout.width)}>
            {chartW > 0 && (
              <PieChart
                data={pieData}
                width={chartW}
                height={220}
                chartConfig={chartConfig}
                accessor={"population"}
                backgroundColor={"transparent"}
                paddingLeft={"15"}
                center={[10, 0]}
                absolute
              />
            )}
          </View>
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
                  <Text style={[styles.tableCell, { color: "#a78bfa" }]}>{cur > 0 ? power.toFixed(2) : "—"}</Text>
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
  container: { padding: spacing.md, gap: spacing.md, paddingBottom: spacing.xxl, width: "100%", maxWidth: rs(1200), alignSelf: "center" },
  sectionTitle: { color: colors.text, fontSize: typography.subtitle, fontWeight: "700", marginTop: spacing.md },
  chartCard: { padding: spacing.sm, alignItems: 'center', overflow: "hidden" },
  chartInner: { width: "100%", alignItems: "center" },
  chart: { marginVertical: spacing.sm, borderRadius: 8 },
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
  tableHead: { color: colors.textMuted, fontWeight: "700", fontSize: rf(11) },
  tableCell: {
    flex: 1,
    color: colors.text,
    fontSize: rf(13),
    fontWeight: "600",
    fontVariant: ["tabular-nums"] as any,
  },
});
