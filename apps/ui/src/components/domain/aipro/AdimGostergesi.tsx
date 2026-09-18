/**
 * ADIM GÖSTERGESİ — araştırma AI Pro sihirbazının "neredeyim / geri nasıl dönerim" şeridi.
 *
 * Sahip isteği (Faz 3): "user friendly olmasına önem ver". Araştırmacı kod bilmeden ilerleyebilsin
 * diye ekran 5 adıma bölünür ve HER adımda geri dönüş yolu görünür kalır.
 *
 * ⚠️ Yalnız SUNUM: hiçbir istek atmaz, hiçbir donanıma dokunmaz. Adım numarası panelin
 * durumundan (model seçildi mi / hazırlık sürüyor mu / hedef var mı / öneri geldi mi / seans
 * aktif mi) TÜRETİLİR — ayrı bir "adım" state'i tutulmaz, böylece gösterge ile gerçek durum
 * ayrışamaz.
 */
import { View, Text, TouchableOpacity, StyleSheet } from "react-native";
import { colors, spacing, typography, touch } from "@/theme/tokens";

/** Sihirbaz adımları — sıra ve adlar tek yerde. */
export const ADIMLAR = ["Model", "Kamera", "Hedef", "Onay", "Seans"] as const;
export type Adim = 1 | 2 | 3 | 4 | 5;

export function AdimGostergesi({
  adim,
  onGeri,
  geriEtiketi = "Geri",
}: {
  adim: Adim;
  /** Geri dönüş eylemi — verilmezse düğme çizilmez (Adım 1). */
  onGeri?: () => void;
  geriEtiketi?: string;
}) {
  const ad = ADIMLAR[adim - 1] ?? "";
  return (
    <View style={styles.wrap}>
      <View style={styles.noktalar}>
        {ADIMLAR.map((a, i) => (
          <View
            key={a}
            style={[styles.nokta, i + 1 === adim && styles.noktaAktif, i + 1 < adim && styles.noktaGecti]}
            accessible={false}
          />
        ))}
      </View>
      <Text
        style={styles.metin}
        numberOfLines={1}
        accessibilityRole="header"
        accessibilityLabel={`Adım ${adim} / ${ADIMLAR.length}: ${ad}`}
      >
        {`Adım ${adim}/${ADIMLAR.length} · ${ad}`}
      </Text>
      {onGeri ? (
        <TouchableOpacity
          style={styles.geri}
          onPress={onGeri}
          accessibilityRole="button"
          accessibilityLabel={`${geriEtiketi}: önceki adıma dön`}
        >
          <Text style={styles.geriMetin}>{`‹ ${geriEtiketi}`}</Text>
        </TouchableOpacity>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  noktalar: { flexDirection: "row", gap: 4 },
  nokta: { width: 8, height: 8, borderRadius: 4, backgroundColor: "#334155" },
  noktaGecti: { backgroundColor: colors.success },
  noktaAktif: { backgroundColor: colors.primary, width: 18 },
  metin: { color: colors.textMuted, fontSize: typography.small, fontWeight: "700", flex: 1 },
  // Dokunma tabanı ölçekle küçülmez (dokunma-hedefi kapısı: touch.min).
  geri: {
    minHeight: touch.min, justifyContent: "center", paddingHorizontal: spacing.md,
    borderRadius: 8, backgroundColor: "#334155",
  },
  geriMetin: { color: "#e2e8f0", fontWeight: "700", fontSize: typography.small },
});
