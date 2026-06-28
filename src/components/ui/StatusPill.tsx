import { StyleSheet, Text, View } from "react-native";
import { colors, radius, spacing, typography } from "@/theme/tokens";
import { ConnectionState } from "@/types/domain";

interface StatusPillProps {
  label: string;
  state: ConnectionState;
}

const STATE_COLORS: Record<ConnectionState, { bg: string; fg: string }> = {
  online: { bg: "#052e16", fg: "#22c55e" }, // success soft
  warning: { bg: "#451a03", fg: "#f59e0b" }, // warning soft
  offline: { bg: "#450a0a", fg: "#ef4444" }, // danger soft
  error: { bg: "#450a0a", fg: "#ef4444" } // danger soft
};

export function StatusPill({ label, state }: StatusPillProps) {
  // Beklenmeyen status string'inde çökmeyi önle (harici cihaz 'connecting'/'degraded' yayınlayabilir).
  const palette = STATE_COLORS[state] ?? STATE_COLORS.offline;
  return (
    <View style={[styles.pill, { backgroundColor: palette.bg, borderColor: palette.fg }]}>
      <View style={[styles.dot, { backgroundColor: palette.fg }]} />
      <Text style={[styles.label, { color: palette.fg }]} numberOfLines={1}>
        {label}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  pill: {
    alignItems: "center",
    borderRadius: radius.sm,
    borderWidth: 1,
    flexDirection: "row",
    gap: spacing.sm,
    minHeight: 32,
    paddingHorizontal: spacing.md
  },
  dot: {
    borderRadius: 4,
    height: 8,
    width: 8
  },
  label: {
    fontSize: typography.caption,
    fontWeight: "700"
  }
});
