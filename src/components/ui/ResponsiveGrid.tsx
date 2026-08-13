// Author: mertaygn, cglrgrkn
import { Children, PropsWithChildren } from "react";
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

  // ORTA fix: Children.toArray → koşullu/falsy child'ları ELER (yoksa `{cond && <X/>}` false-child'ı
  // görünmez ama flexBasis genişliğini işgal eden HAYALET hücre yaratır) + stabil key verir (index-key
  // toggle-kayması önlenir). Tek child da diziye normalize edilir (eski `: children` dalı hücresiz kalıyordu).
  const items = Children.toArray(children);
  return (
    <View style={styles.grid}>
      {items.map((child, index) => (
        <View key={(child as any)?.key ?? index} style={[styles.cell, { flexBasis: basis }]}>
          {child}
        </View>
      ))}
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
    minWidth: 0,  // web: flex item içeriğin altına küçülebilsin (uzun içerik satır kaymasına yol açmasın)
    paddingHorizontal: spacing.sm
  }
});
