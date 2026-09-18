// Author: mertaygn, cglrgrkn
/**
 * IconButton — ikon-only dokunma hedefi ilkeli.  [S3 adım 3, 2026-09-04 responsive denetimi]
 * =========================================================================================
 * ÖLÇÜLEN DURUM: ikon-only düğmeler (kapat X, bildirim zili, bağlantı yenile, ayarlar, yenile)
 * yalnız ikonun kendi boyutu kadar dokunulabilir alandı: 16-20 px ikon + 4-6 px padding = 24-32 px.
 * Erişilebilirlik tabanı 44 px; 320 px'lik telefonda ve titreyen elde ıskalanıyorlardı.
 *
 * SÖZLEŞME:
 *  1. Kutu ÖLÇEKTEN BAĞIMSIZ olarak en az `touch.min` (44) — `rs()` ile AŞAĞI inmez.
 *  2. `label` ZORUNLU → ekran okuyucu her zaman ne olduğunu söyler (ikonun metni yoktur).
 *  3. `style` geçişi görsel farkı korur (mevcut renk/çerçeve stilleri aynen aktarılır);
 *     taban ölçüler stil dizisinde ÖNCE gelir, çağıran yalnız görünümü ezebilir…
 *  4. …ama minWidth/minHeight'ı ezmek isterse bilinçli olmalı: `boyutEzilebilir` bayrağı yoksa
 *     taban stilden SONRA uygulanır.
 *
 * ⚠️ hitSlop komşu hedeflerle binişmemeli: sıkı yerleşimde `touch.slopFor(gap)` verin.
 */
import { ReactNode } from "react";
import { Pressable, StyleProp, StyleSheet, ViewStyle } from "react-native";
import { touch } from "@/theme/tokens";

export interface IconButtonProps {
  /** Ekran okuyucu etiketi — ZORUNLU (ikonun okunacak metni yoktur). */
  label: string;
  onPress: () => void;
  children: ReactNode;
  style?: StyleProp<ViewStyle>;
  /** Native ek tampon. Sıkı ızgarada `touch.slopFor(gap)` kullanın. */
  hitSlop?: { top: number; bottom: number; left: number; right: number };
  disabled?: boolean;
  accessibilityHint?: string;
  testID?: string;
}

export function IconButton({
  label,
  onPress,
  children,
  style,
  hitSlop = touch.slop,
  disabled,
  accessibilityHint,
  testID,
}: IconButtonProps) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      hitSlop={hitSlop}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityHint={accessibilityHint}
      accessibilityState={{ disabled: !!disabled }}
      testID={testID}
      // Taban ölçüler SONRA: çağıranın stili rengi/çerçeveyi ezer, dokunma tabanını ezemez.
      style={[styles.taban, style, styles.olcu]}
    >
      {children}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  taban: { alignItems: "center", justifyContent: "center" },
  olcu: { minWidth: touch.min, minHeight: touch.min },
});
