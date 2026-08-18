// Author: mertaygn, cglrgrkn
import { ReactNode } from "react";
import { StyleSheet, Text, View } from "react-native";
import { Activity, RadioTower, Thermometer, Zap } from "lucide-react-native";
import { Card } from "@/components/ui/Card";
import { StatusPill } from "@/components/ui/StatusPill";
import { colors, spacing, typography, rs } from "@/theme/tokens";
import { CoilStatus } from "@/types/domain";

/** Güvenli sayı biçimlendirme: sayı değilse (undefined / "44.5" / NaN) çökmek yerine "—". */
function num(v: unknown, digits = 0): string {
  const n = typeof v === "number" ? v : parseFloat(String(v));
  return Number.isFinite(n) ? n.toFixed(digits) : "—";
}

export function CoilCard({ coil }: { coil: CoilStatus }) {
  const isStmCoil = coil.stm32Driven || coil.id <= 5;
  const sourceText = coil.connected
    ? isStmCoil ? "Kablolu senkron" : "Kablosuz senkron"
    : "Veri bekleniyor";

  return (
    <Card style={styles.card}>
      <View style={styles.header}>
        <View>
          <Text style={styles.title}>Bobin {coil.id}</Text>
          <Text style={styles.sub}>{sourceText}</Text>
        </View>
        <StatusPill label={coil.running ? "Aktif" : coil.connected ? "Hazır" : "Offline"} state={coil.running ? "online" : coil.connected ? "warning" : "offline"} />
      </View>

      <View style={styles.metrics}>
        {/* SAVUNMA DERİNLİĞİ: `.toFixed()` sayı OLMAYAN değerde TypeError atar. Normalde
            LiveDataContext.normalizeStmCoils tüm alanları `_num` ile sayıya zorluyor — ama bu
            kart, ACİL DURDUR'un yaşadığı Ana Ekran'da render ediliyor. Tek bir normalize-edilmemiş
            çağrı yeri (ya da ileride eklenecek yeni bir kaynak) bu ekranı çökertirse operatör
            donanım çalışırken durdurma kontrolünü kaybeder. Bileşen kendi girdisini de doğrular. */}
        <MiniMetric icon={<RadioTower color={colors.primary} size={16} />} label="Frekans" value={`${num(coil.frequencyHz)} Hz`} />
        <MiniMetric icon={<Zap color={colors.warning} size={16} />} label="Duty" value={`${num(coil.dutyCycle)}%`} />
        <MiniMetric icon={<Activity color={colors.cyan} size={16} />} label="Alan" value={`${num(coil.magneticMt, 2)} mT`} />
        <MiniMetric icon={<Thermometer color={colors.danger} size={16} />} label="Sıcaklık" value={`${num(coil.objectTemp, 1)} C`} />
      </View>
    </Card>
  );
}

function MiniMetric({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <View style={styles.mini}>
      {icon}
      <View style={{ flexShrink: 1 }}>
        <Text style={styles.miniLabel} numberOfLines={1}>{label}</Text>
        <Text style={styles.miniValue} numberOfLines={1} adjustsFontSizeToFit>{value}</Text>
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
    minHeight: rs(58),
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
