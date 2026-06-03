import { MetricCard } from "@/components/ui/MetricCard";
import { ResponsiveGrid } from "@/components/ui/ResponsiveGrid";
import { colors } from "@/theme/tokens";

export function KpiDashboardScreen() {
  return (
    <ResponsiveGrid>
      <MetricCard label="Tedavi Etkinliği" value="78%" tone={colors.primary} />
      <MetricCard label="Ort. Tedavi Süresi" value="15 dk" tone={colors.success} />
      <MetricCard label="Cihaz Çalışma Oranı" value="92%" tone={colors.violet} />
      <MetricCard label="Hasta Memnuniyeti" value="8.7" tone={colors.magenta} />
      <MetricCard label="Bakım Süresi" value="12 dk" tone={colors.warning} />
      <MetricCard label="Anlık Güç" value="42 W" tone={colors.cyan} />
    </ResponsiveGrid>
  );
}
