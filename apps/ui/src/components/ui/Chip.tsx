// Author: mertaygn, cglrgrkn
/**
 * Chip + ChipRow — seçilebilir etiket ilkeli.  [S3 adım 4, 2026-09-04 responsive denetimi]
 * =======================================================================================
 * ÖLÇÜLEN DURUM: uygulamada 11 ayrı çip stili vardı (gözlem tepkileri, AI geçmişi filtreleri,
 * sensör bobin seçimi, kontrol ekranı ön ayarları…). Hepsi `paddingVertical: spacing.xs` ile
 * kuruluydu → 320 px telefonda çip yüksekliği 26-30 px, erişilebilirlik tabanı 40 px.
 * Yan yana dizildiklerinde aralarındaki boşluk da 4 px olduğu için komşu çipe basılıyordu.
 *
 * SÖZLEŞME:
 *  1. Yükseklik ÖLÇEKTEN BAĞIMSIZ en az `touch.sm` (40) — çipler ikincil hedeftir, 44 değil 40.
 *  2. GÖRSEL DEĞİŞİKLİK YOK ilkesi: `style` / `activeStyle` / `textStyle` / `activeTextStyle`
 *     geçişiyle mevcut renkler aynen taşınır; göç = stil objesini prop'a taşımak.
 *  3. `accessibilityState.selected` seçili durumu ekran okuyucuya bildirir (renk tek başına yetmez).
 *  4. Satır boşluğu `spacing.sm` (8) — ChipRow bunu tek yerden verir.
 *
 * ⚠️ Taban ölçü stil dizisinde SONRA gelir: çağıran rengi ezer, dokunma tabanını ezemez.
 */
import { ReactNode } from "react";
import { StyleProp, StyleSheet, Text, TextStyle, TouchableOpacity, View, ViewStyle } from "react-native";
import { radius, spacing, touch, typography } from "@/theme/tokens";

export interface ChipProps {
  label: string;
  active?: boolean;
  onPress: () => void;
  style?: StyleProp<ViewStyle>;
  activeStyle?: StyleProp<ViewStyle>;
  textStyle?: StyleProp<TextStyle>;
  activeTextStyle?: StyleProp<TextStyle>;
  accessibilityLabel?: string;
  disabled?: boolean;
  /** Etiketin solunda ikon/nokta. */
  left?: ReactNode;
  testID?: string;
}

export function Chip({
  label,
  active = false,
  onPress,
  style,
  activeStyle,
  textStyle,
  activeTextStyle,
  accessibilityLabel,
  disabled,
  left,
  testID,
}: ChipProps) {
  return (
    <TouchableOpacity
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? label}
      accessibilityState={{ selected: active, disabled: !!disabled }}
      testID={testID}
      style={[styles.cip, style, active && activeStyle, styles.olcu]}
    >
      {left}
      <Text style={[styles.metin, textStyle, active && activeTextStyle]} numberOfLines={1}>
        {label}
      </Text>
    </TouchableOpacity>
  );
}

/** Çip satırı — sarmalı ve 8 px boşluğu tek yerden verir (komşu hedefe basma riski). */
export function ChipRow({ children, style }: { children: ReactNode; style?: StyleProp<ViewStyle> }) {
  return <View style={[styles.satir, style]}>{children}</View>;
}

const styles = StyleSheet.create({
  cip: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.xs,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderRadius: radius.full,
  },
  // Taban SONRA uygulanır → çağıranın stili yüksekliği düşüremez.
  olcu: { minHeight: touch.sm },
  metin: { fontSize: typography.small, fontWeight: "600" },
  satir: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
});
