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
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { colors, spacing, typography, touch } from "@/theme/tokens";

/** Sihirbaz adımları — sıra ve adlar tek yerde (adlar katalogdan: ai.pro.adim.*). */
const adimAdlari = (t: TFunction): string[] => [
  t("ai.pro.adim.model"),
  t("ai.pro.adim.kamera"),
  t("ai.pro.adim.hedef"),
  t("ai.pro.adim.onay"),
  t("ai.pro.adim.seans"),
];
export type Adim = 1 | 2 | 3 | 4 | 5;

export function AdimGostergesi({
  adim,
  onGeri,
  geriEtiketi,
}: {
  adim: Adim;
  /** Geri dönüş eylemi — verilmezse düğme çizilmez (Adım 1). */
  onGeri?: () => void;
  geriEtiketi?: string;
}) {
  const { t } = useTranslation();
  const adlar = adimAdlari(t);
  const toplam = adlar.length;
  const ad = adlar[adim - 1] ?? "";
  const geri = geriEtiketi ?? t("ai.pro.adim.geri");
  return (
    <View style={styles.wrap}>
      <View style={styles.noktalar}>
        {adlar.map((a, i) => (
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
        accessibilityLabel={t("ai.pro.adim.etiket", { adim, toplam, ad })}
      >
        {t("ai.pro.adim.metin", { adim, toplam, ad })}
      </Text>
      {onGeri ? (
        <TouchableOpacity
          style={styles.geri}
          onPress={onGeri}
          accessibilityRole="button"
          accessibilityLabel={t("ai.pro.adim.geriEtiket", { geriEtiketi: geri })}
        >
          <Text style={styles.geriMetin}>{`‹ ${geri}`}</Text>
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
