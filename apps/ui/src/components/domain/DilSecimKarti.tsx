/**
 * "Dil / Language" kartı (Ayarlar · Y161) — bayrak (`I18N_EN_ACIK`) KAPALIYKEN HİÇ ÇİZİLMEZ (Ayarlar onu `dilSecimiGorunur()` ile
 * koşullar; Türkçe görünüm göç boyunca aynen kalır).
 *
 * Seçim bu cihazda saklanır (`dilSec` → AsyncStorage `pemf.dil`), hesaptan / profilden bağımsızdır; değişince bütün ekranlar yeniden
 * çizilir (yeniden başlatma yok). Masaüstünde (backend bu makinede) seçim ayrıca sunucuya bildirilir → launcher ve istek dışı
 * üretimler (zamanlanmış bildirim, arka plan PDF) aynı dili kullanır. Bildirim düşerse arayüz dili yine değişir (sessiz değil:
 * yalnız yerel kayıt düşerse kullanıcıya eylem söyleyen ileti gösterilir).
 * Dil adları kendi dillerinde yazılır ("Türkçe" / "English") — okuyamadığı dilde kalan kullanıcı da bulsun.
 */
import { StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useTranslation } from "react-i18next";
import { Languages } from "lucide-react-native";
import { Card } from "@/components/ui/Card";
import { colors, radius, spacing, touch, typography } from "@/theme/tokens";
import { dilSec, type Dil } from "@/i18n";
import { apiPost } from "@/services/apiClient";
import { backendBuMakinede } from "@/services/backendKonumu";
import { useToast } from "@/components/ui/ToastProvider";

/** Dil seçiminin TEK yolu (Y184: Ayarlar kartı + giriş / karşılama ekranlarının `DilSecici`'si AYNI kaydı kullanır). */
export function useDilSecimi(): { etkin: Dil; sec: (d: Dil) => Promise<void> } {
  const { t, i18n } = useTranslation();
  const { showToast } = useToast();
  const etkin: Dil = i18n.language === "en" ? "en" : "tr";

  const sec = async (d: Dil) => {
    const { dil, kaydedildi } = await dilSec(d);
    if (!kaydedildi) showToast(t("ayarlar.dil.kayitHatasi"), "error");
    if (backendBuMakinede()) {
      await apiPost("/settings/arayuz-dili", { dil }, null, { silent: true });
    }
  };
  return { etkin, sec };
}

export function DilSecimKarti() {
  const { t } = useTranslation();
  const { etkin, sec } = useDilSecimi();

  const secenek = (d: Dil, etiket: string) => (
    <TouchableOpacity
      key={d}
      style={[styles.secenek, etkin === d && styles.secenekSecili]}
      onPress={() => void sec(d)}
      accessibilityRole="button"
      accessibilityState={{ selected: etkin === d }}
      accessibilityLabel={etiket}
      testID={`dil-secenek-${d}`}
    >
      <Text style={[styles.secenekMetni, etkin === d && styles.secenekMetniSecili]}>{etiket}</Text>
    </TouchableOpacity>
  );

  return (
    <Card style={styles.card}>
      <View style={styles.baslikSatiri}>
        <Languages color={colors.primary} size={20} />
        <Text style={styles.baslik}>{t("ayarlar.dil.baslik")}</Text>
      </View>
      <Text style={styles.aciklama}>{t("ayarlar.dil.aciklama")}</Text>
      <View style={styles.secenekler}>
        {secenek("tr", t("ayarlar.dil.secenekTr"))}
        {secenek("en", t("ayarlar.dil.secenekEn"))}
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  card: { marginBottom: spacing.md, gap: spacing.sm },
  baslikSatiri: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  baslik: { fontSize: typography.subtitle, fontWeight: "700", color: colors.text },
  aciklama: { fontSize: typography.caption, color: colors.textMuted },
  secenekler: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" },
  secenek: {
    minHeight: touch.min,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
  },
  secenekSecili: { backgroundColor: colors.primary },
  secenekMetni: { color: colors.primary, fontWeight: "700" },
  secenekMetniSecili: { color: "#fff" },
});
