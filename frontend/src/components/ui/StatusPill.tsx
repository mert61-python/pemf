import { StyleSheet, Text, View } from "react-native";
import { colors, radius, spacing, typography } from "@/theme/tokens";
import { ConnectionState } from "@/types/domain";

interface StatusPillProps {
  label: string;
  state: ConnectionState;
}

const stateColors: Record<ConnectionState, { bg: string; fg: string }> = {
  online: { bg: colors.successSoft, fg: colors.success },
  warning: { bg: colors.warningSoft, fg: colors.warning },
  offline: { bg: colors.dangerSoft, fg: colors.danger }
};

export function StatusPill({ label, state }: StatusPillProps) {
  const palette = stateColors[state];
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
