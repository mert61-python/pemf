import { ReactNode } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { colors, radius, spacing, typography } from "@/theme/tokens";

type ButtonVariant = "primary" | "danger" | "secondary" | "ghost";

interface ButtonProps {
  label: string;
  icon?: ReactNode;
  variant?: ButtonVariant;
  onPress?: () => void;
  disabled?: boolean;
}

export function Button({ label, icon, variant = "primary", onPress, disabled }: ButtonProps) {
  return (
    <Pressable
      accessibilityRole="button"
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.base,
        styles[variant],
        pressed && styles.pressed,
        disabled && styles.disabled
      ]}
    >
      {icon ? <View style={styles.icon}>{icon}</View> : null}
      <Text style={[styles.label, variant === "ghost" && styles.ghostLabel]} numberOfLines={1}>
        {label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    alignItems: "center",
    borderRadius: radius.md,
    flexDirection: "row",
    gap: spacing.sm,
    justifyContent: "center",
    minHeight: 44,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md
  },
  primary: { backgroundColor: colors.primary },
  danger: { backgroundColor: colors.danger },
  secondary: { backgroundColor: colors.panelSoft, borderColor: colors.border, borderWidth: 1 },
  ghost: { backgroundColor: "transparent", borderColor: colors.border, borderWidth: 1 },
  pressed: { opacity: 0.82 },
  disabled: { opacity: 0.45 },
  icon: { alignItems: "center", justifyContent: "center" },
  label: {
    color: colors.white,
    fontSize: typography.body,
    fontWeight: "700"
  },
  ghostLabel: {
    color: colors.text
  }
});
