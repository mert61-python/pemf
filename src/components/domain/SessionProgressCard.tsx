/**
 * SessionProgressCard — Aktif seans ilerleme kartı.
 *
 * Python unified_control_window'daki seans timer göstergesinin React karşılığı.
 */
import { StyleSheet, Text, View, TouchableOpacity, Animated as RNAnimated, Easing as RNEasing } from "react-native";
import { useEffect as useEff, useRef as useR } from "react";
import { colors, spacing, typography, rf, rs } from "@/theme/tokens";

interface Props {
  isActive: boolean;
  mode: string;
  elapsedSec: number;
  remainingSec: number;
  durationSec: number;
  frequencyHz: number;
  intensityMt: number;
  onStop: () => void;
  onEmergencyStop: () => void;
  loading?: boolean;
  /** Bağlantı bayat/çevrimdışı: gösterilen süre/değerler GERÇEK ZAMANLI DOĞRULANAMIYOR → görsel işaretle. */
  stale?: boolean;
}

function formatTime(sec: number): string {
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export function SessionProgressCard({
  isActive,
  mode,
  elapsedSec,
  remainingSec,
  durationSec,
  frequencyHz,
  intensityMt,
  onStop,
  onEmergencyStop,
  loading = false,
  stale = false,
}: Props) {
  const progress = durationSec > 0 ? Math.min(1, elapsedSec / durationSec) : 0;
  const indefinite = durationSec <= 0; // #72: süresiz seans → 00:00/%0 yerine "Süresiz"
  const pulseAnim = useR(new RNAnimated.Value(1)).current;

  useEff(() => {
    // Bayat veride nabız animasyonunu DURDUR: "canlı çalışıyor" izlenimi verme.
    if (!isActive || stale) {
      pulseAnim.setValue(1);
      return;
    }
    const loop = RNAnimated.loop(
      RNAnimated.sequence([
        RNAnimated.timing(pulseAnim, { toValue: 1.08, duration: 1000, easing: RNEasing.ease, useNativeDriver: true }),
        RNAnimated.timing(pulseAnim, { toValue: 1.0, duration: 1000, easing: RNEasing.ease, useNativeDriver: true }),
      ])
    );
    loop.start();
    return () => loop.stop();
  }, [isActive, stale]);

  if (!isActive) {
    return (
      <View style={styles.idleCard}>
        <Text style={styles.idleIcon}>⚡</Text>
        <Text style={styles.idleTitle}>Tedavi Bekleniyor</Text>
        <Text style={styles.idleSubtitle}>Parametreleri ayarlayıp &quot;Seans Başlat&quot; butonuna basın.</Text>
      </View>
    );
  }

  return (
    <RNAnimated.View style={[styles.card, { transform: [{ scale: pulseAnim }] }]}>
      {/* Header */}
      <View style={styles.header}>
        <View style={[styles.activeBadge, stale && styles.staleBadge]}>
          <View style={[styles.pulseDot, stale && styles.staleDot]} />
          <Text style={[styles.activeBadgeText, stale && styles.staleBadgeText]}>
            {stale ? "VERİ DOĞRULANMADI" : "AKTİF SEANS"}
          </Text>
        </View>
        <Text style={styles.modeText}>{mode}</Text>
      </View>

      {stale && (
        <Text style={styles.staleNote}
          accessibilityRole="alert" accessibilityLiveRegion="polite">
          ⚠️ Bağlantı bayat/çevrimdışı — gösterilen süre ve değerler gerçek zamanlı doğrulanamıyor.
        </Text>
      )}

      {/* Progress bar */}
      <View style={styles.progressBg}>
        <View style={[styles.progressFill, { width: `${Math.round(progress * 100)}%` as any }]} />
      </View>

      {/* Times */}
      <View style={styles.timeRow}>
        <View style={styles.timeBlock}>
          <Text style={styles.timeLabel}>GEÇEN</Text>
          <Text style={styles.timeValue}>{formatTime(elapsedSec)}</Text>
        </View>
        <View style={styles.timeBlockCenter}>
          <Text style={styles.progressPct}>{indefinite ? "∞" : `${Math.round(progress * 100)}%`}</Text>
        </View>
        <View style={[styles.timeBlock, { alignItems: "flex-end" }]}>
          <Text style={styles.timeLabel}>KALAN</Text>
          <Text style={[styles.timeValue, { color: indefinite ? colors.textMuted : remainingSec < 60 ? "#ef4444" : colors.primary }]}>
            {indefinite ? "Süresiz" : formatTime(remainingSec)}
          </Text>
        </View>
      </View>

      {/* Params */}
      <View style={styles.paramRow}>
        <ParamChip label="FREKANS" value={`${frequencyHz} Hz`} />
        <ParamChip label="YOĞUNLUK" value={`${intensityMt} mT`} />
      </View>

      {/* Buttons */}
      <View style={styles.btnRow}>
        <TouchableOpacity style={styles.btnStop} onPress={onStop} disabled={loading}
          accessibilityRole="button" accessibilityLabel="Tedavi seansını durdur">
          <Text style={styles.btnStopText} numberOfLines={1} adjustsFontSizeToFit>⏹ Durdur</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.btnEmergency} onPress={onEmergencyStop}
          accessibilityRole="button" accessibilityLabel="Acil durdurma — tüm bobinleri anında durdur">
          <Text style={styles.btnEmergencyText} numberOfLines={1} adjustsFontSizeToFit>🚨 ACİL DURDUR</Text>
        </TouchableOpacity>
      </View>
    </RNAnimated.View>
  );
}

function ParamChip({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.paramChip}>
      <Text style={styles.paramLabel}>{label}</Text>
      <Text style={styles.paramValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  idleCard: {
    backgroundColor: "#1e293b",
    borderRadius: 16,
    padding: spacing.xl,
    alignItems: "center",
    borderWidth: 1,
    borderStyle: "dashed",
    borderColor: "#334155",
  },
  idleIcon: { fontSize: rf(36), marginBottom: spacing.sm },
  idleTitle: { color: colors.text, fontWeight: "700", fontSize: typography.subtitle },
  idleSubtitle: { color: colors.textMuted, fontSize: typography.small, marginTop: spacing.xs, textAlign: "center" },

  card: {
    backgroundColor: "#0f1729",
    borderRadius: 16,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: "#22c55e44",
    shadowColor: "#22c55e",
    shadowOpacity: 0.15,
    shadowRadius: 12,
    gap: spacing.md,
  },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  activeBadge: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.xs,
    backgroundColor: "#22c55e22",
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
    borderRadius: 20,
  },
  pulseDot: {
    width: rs(8),
    height: rs(8),
    borderRadius: 4,
    backgroundColor: "#22c55e",
  },
  activeBadgeText: { color: "#22c55e", fontWeight: "700", fontSize: typography.small },
  modeText: { color: colors.textMuted, fontSize: typography.small },
  staleBadge: { backgroundColor: "#f59e0b22" },
  staleDot: { backgroundColor: "#f59e0b" },
  staleBadgeText: { color: "#f59e0b" },
  staleNote: {
    color: "#f59e0b",
    fontSize: typography.small,
    fontWeight: "600",
    backgroundColor: "#f59e0b18",
    borderRadius: 8,
    padding: spacing.sm,
  },

  progressBg: {
    height: rs(8),
    backgroundColor: "#1e293b",
    borderRadius: 4,
    overflow: "hidden",
  },
  progressFill: {
    height: "100%",
    backgroundColor: "#22c55e",
    borderRadius: 4,
  },

  timeRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  timeBlock: { flex: 1 },
  timeBlockCenter: { flex: 1, alignItems: "center" },
  timeLabel: { color: colors.textMuted, fontSize: rf(10), fontWeight: "700", letterSpacing: 1 },
  timeValue: { color: colors.text, fontSize: typography.title, fontWeight: "800", fontVariant: ["tabular-nums"] as any },
  progressPct: { color: "#22c55e", fontSize: typography.subtitle, fontWeight: "700" },

  paramRow: { flexDirection: "row", gap: spacing.sm },
  paramChip: {
    flex: 1,
    backgroundColor: "#1e293b",
    borderRadius: 8,
    padding: spacing.sm,
    alignItems: "center",
  },
  paramLabel: { color: colors.textMuted, fontSize: rf(10), fontWeight: "700", letterSpacing: 1 },
  paramValue: { color: colors.primary, fontSize: typography.body, fontWeight: "700" },

  btnRow: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.xs },
  btnStop: {
    flex: 1,
    backgroundColor: "#1e293b",
    borderRadius: 10,
    padding: spacing.md,
    alignItems: "center",
    borderWidth: 1,
    borderColor: "#475569",
  },
  btnStopText: { color: colors.text, fontWeight: "700" },
  btnEmergency: {
    flex: 1,
    backgroundColor: "#ef4444",
    borderRadius: 10,
    padding: spacing.md,
    alignItems: "center",
  },
  btnEmergencyText: { color: "#fff", fontWeight: "800" },
});
