import { PropsWithChildren } from "react";
import { StyleSheet, View } from "react-native";
import { useResponsive } from "@/hooks/useResponsive";
import { spacing } from "@/theme/tokens";

interface ResponsiveGridProps extends PropsWithChildren {
  minItemWidth?: number;
}

export function ResponsiveGrid({ children, minItemWidth = 260 }: ResponsiveGridProps) {
  const { width, columns } = useResponsive();
  const targetColumns = width / columns < minItemWidth ? Math.max(1, columns - 1) : columns;
  const basis = `${100 / targetColumns}%` as const;

  return (
    <View style={styles.grid}>
      {Array.isArray(children)
        ? children.map((child, index) => (
            <View key={index} style={[styles.cell, { flexBasis: basis }]}>
              {child}
            </View>
          ))
        : children}
    </View>
  );
}

const styles = StyleSheet.create({
  grid: {
    flexDirection: "row",
    flexWrap: "wrap",
    marginHorizontal: -spacing.sm,
    rowGap: spacing.lg
  },
  cell: {
    paddingHorizontal: spacing.sm
  }
});
