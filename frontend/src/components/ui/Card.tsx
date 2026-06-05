import { PropsWithChildren } from "react";
import { Platform, StyleSheet, View, ViewStyle, StyleProp } from "react-native";
import { colors, radius, shadows, spacing } from "@/theme/tokens";

interface CardProps extends PropsWithChildren {
  style?: StyleProp<ViewStyle>;
}

export function Card({ children, style }: CardProps) {
  return <View style={[styles.card, cardShadow, style]}>{children}</View>;
}

const cardShadow: ViewStyle =
  Platform.OS === "web"
    ? ({ boxShadow: "0 10px 18px rgba(0, 0, 0, 0.24)" } as ViewStyle)
    : shadows.panel;

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.panel,
    borderColor: colors.border,
    borderRadius: radius.md,
    borderWidth: 1,
    padding: spacing.lg
  }
});
