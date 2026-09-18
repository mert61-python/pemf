// Author: mertaygn, cglrgrkn
import { Children, PropsWithChildren, useState } from "react";
import { LayoutChangeEvent, StyleSheet, View } from "react-native";
import { useResponsive } from "@/hooks/useResponsive";
import { rs, spacing } from "@/theme/tokens";

interface ResponsiveGridProps extends PropsWithChildren {
  minItemWidth?: number;
}

/**
 * SÜTUN SAYISI GERÇEK KAPTAN  [S2 adım 3, 2026-09-04 responsive denetimi]
 * ======================================================================
 * ESKİ: `width / columns < minItemWidth` — karar PENCERE genişliğinden veriliyordu. Kabuklu
 * tablette 768 px'lik pencerenin 240 px'i kenar çubuğu, 48 px'i içerik boşluğuydu; ızgara 352 px'e
 * 2 sütun yerleştirip bobin kartını 182 px'e düşürüyordu (ekranB-1).
 *
 * YENİ: sütun = clamp(floor(gridW / (rs(minItemWidth) + 2×sm)), 1, üstSınır)
 *  · gridW ölçülür (onLayout). Ölçüm gelene kadar `contentWidth + 2×sm` TAHMİNİ kullanılır —
 *    ızgaranın marginHorizontal'ı −sm olduğu için ölçülen genişlik kaptan 2×sm fazladır; tahmin
 *    aynı ölçekte olunca "1 sütun → N sütun" flicker'ı olmaz.
 *  · minItemWidth çağıranda ÖLÇEKSİZ yazılır, burada rs() ile ölçeklenir (kart içi yazı/padding de
 *    rs ile büyüdüğünden tutarlı).
 *  · ÜST SINIR = max(columns, 2). Düz `columns` sınırı TELEFONDA REGRESYON yapardı: telefonda
 *    columns = 1'dir, oysa 8 sensör kartı ve 5 sayısal AI girişi bugün 2'li diziliyor. Genişlik
 *    hesabı büyük kartları zaten telefonda tek sütuna indirir; üst sınırın asıl işi geniş ekranda:
 *    2560 px'te 8 sütuna dağılmayı columns=4'te durdurur.
 */
export function ResponsiveGrid({ children, minItemWidth = 260 }: ResponsiveGridProps) {
  const { contentWidth, columns } = useResponsive();
  const [olculen, setOlculen] = useState(0);

  const onLayout = (e: LayoutChangeEvent) => {
    const w = e.nativeEvent.layout.width;
    // 1 px altı titreşim setState tetiklemesin (ölçüm döngüsü / gereksiz render).
    setOlculen((eski) => (Math.abs(w - eski) < 1 ? eski : w));
  };

  const izgaraGenislik = olculen || contentWidth + 2 * spacing.sm;
  const hucreEn = rs(minItemWidth) + 2 * spacing.sm;
  const ustSinir = Math.max(columns, 2);
  const sutun = Math.min(Math.max(1, Math.floor(izgaraGenislik / hucreEn)), ustSinir);
  const basis = `${100 / sutun}%` as const;

  // ORTA fix: Children.toArray → koşullu/falsy child'ları ELER (yoksa `{cond && <X/>}` false-child'ı
  // görünmez ama flexBasis genişliğini işgal eden HAYALET hücre yaratır) + stabil key verir (index-key
  // toggle-kayması önlenir). Tek child da diziye normalize edilir (eski `: children` dalı hücresiz kalıyordu).
  const items = Children.toArray(children);
  return (
    <View style={styles.grid} onLayout={onLayout}>
      {items.map((child, index) => (
        <View key={(child as { key?: string })?.key ?? index} style={[styles.cell, { flexBasis: basis }]}>
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
