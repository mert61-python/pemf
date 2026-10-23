/**
 * Kompakt dil seçici "Türkçe | English" (Y184, sahip 2026-10-22) — profil seçim (karşılama, Çıkış'ın yanında) ve giriş ekranlarında;
 * oturum açmadan / profil seçmeden de dil değişsin. Ayarlar'daki "Dil / Language" kartıyla AYNI kayıt (`useDilSecimi` → AsyncStorage
 * `pemf.dil`, cihaz düzeyi, hesaptan / profilden bağımsız — Y161); seçim anında bütün ekran yeniden çizilir. İngilizce bayrağı
 * kapalıyken HİÇ çizilmez (`dilSecimiGorunur`). Dil adları kendi dillerinde (okuyamadığı dilde kalan kullanıcı da bulsun).
 */
import { StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useTranslation } from "react-i18next";
import { colors, radius, spacing, touch } from "@/theme/tokens";
import { dilSecimiGorunur, type Dil } from "@/i18n";
import { useDilSecimi } from "@/components/domain/DilSecimKarti";

export function DilSecici() {
  const { t } = useTranslation();
  const { etkin, sec } = useDilSecimi();
  if (!dilSecimiGorunur()) return null;

  const secenek = (d: Dil, etiket: string) => (
    <TouchableOpacity
      key={d}
      style={[styles.secenek, etkin === d && styles.secenekSecili]}
      onPress={() => void sec(d)}
      accessibilityRole="button"
      accessibilityState={{ selected: etkin === d }}
      accessibilityLabel={etiket}
      testID={`dil-secici-${d}`}
    >
      <Text style={[styles.metin, etkin === d && styles.metinSecili]}>{etiket}</Text>
    </TouchableOpacity>
  );

  return (
    <View style={styles.kap} accessibilityLabel={t("ayarlar.dil.baslik")} testID="dil-secici">
      {secenek("tr", t("ayarlar.dil.secenekTr"))}
      {secenek("en", t("ayarlar.dil.secenekEn"))}
    </View>
  );
}

const styles = StyleSheet.create({
  kap: { flexDirection: "row", gap: spacing.xs, alignItems: "center" },
  secenek: {
    minHeight: touch.min,
    paddingHorizontal: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: "center",
    justifyContent: "center",
  },
  secenekSecili: { backgroundColor: colors.primary, borderColor: colors.primary },
  metin: { color: colors.textMuted, fontWeight: "700" },
  metinSecili: { color: "#fff" },
});
