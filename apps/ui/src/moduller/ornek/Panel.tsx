// Author: mertaygn, cglrgrkn
/**
 * GA (istem 53) B3 / B4 — ÖRNEK MODÜL PANELİ (şablon): yalnız modül araç takımını (`useModul`) ve ortak arayüz parçalarını kullanır.
 * Sahte kartı sürer: frekans / duty / süre → Uygula · Başlat · Durdur. Sınırlar sunucuda (`modul.json`) ve kartta zorlanır.
 * ACİL DURDUR panelde DEĞİL — Kontrol sekmesindeki büyük düğme her zaman görünür ve modüllere de gider.
 */
import { useState } from "react";
import { StyleSheet, Text, TextInput, TouchableOpacity, View } from "react-native";
import { useTranslation } from "react-i18next";
import { useModul } from "@/moduller/arac";
import { modulHataMetni } from "@/services/moduller";
import { colors, rf, rs, spacing, touch } from "@/theme/tokens";

const ALANLAR: { ad: "frekans_hz" | "duty_yuzde" | "sure_dk"; varsayilan: string }[] = [
  { ad: "frekans_hz", varsayilan: "100" },
  { ad: "duty_yuzde", varsayilan: "25" },
  { ad: "sure_dk", varsayilan: "10" },
];

export default function OrnekPanel() {
  const { t } = useTranslation();
  const m = useModul();
  const [deger, setDeger] = useState<Record<string, string>>(Object.fromEntries(ALANLAR.map((a) => [a.ad, a.varsayilan])));
  const etiket = (ad: string) =>
    ad === "frekans_hz" ? t("kontrol.modul.ornek.frekans") : ad === "duty_yuzde" ? t("kontrol.modul.ornek.duty") : t("kontrol.modul.ornek.sure");
  const bobin = m.durum?.bobin === true;
  return (
    <View style={styles.kutu} testID="modul-ornek-panel">
      <Text style={styles.baslik}>{t("kontrol.modul.ornek.baslik")}</Text>
      <View style={styles.satir}>
        {ALANLAR.map((a) => (
          <View key={a.ad} style={styles.alan}>
            <Text style={styles.etiket}>{etiket(a.ad)}</Text>
            <TextInput
              style={styles.giris}
              value={deger[a.ad]}
              onChangeText={(v) => setDeger((d) => ({ ...d, [a.ad]: v }))}
              keyboardType="numeric"
              testID={`modul-ornek-${a.ad}`}
            />
          </View>
        ))}
      </View>
      <View style={styles.satir}>
        <TouchableOpacity
          style={styles.dugme}
          disabled={m.mesgul}
          onPress={() => void m.uygula(Object.fromEntries(ALANLAR.map((a) => [a.ad, Number(deger[a.ad])])))}
          testID="modul-ornek-uygula"
          accessibilityRole="button"
        >
          <Text style={styles.dugmeMetin}>{t("kontrol.modul.ornek.uygula")}</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.dugme} disabled={m.mesgul} onPress={() => void m.baslat()} testID="modul-ornek-baslat" accessibilityRole="button">
          <Text style={styles.dugmeMetin}>{t("kontrol.panel.baslat")}</Text>
        </TouchableOpacity>
        <TouchableOpacity style={[styles.dugme, styles.durdur]} onPress={() => void m.durdur()} testID="modul-ornek-durdur" accessibilityRole="button">
          <Text style={styles.dugmeMetin}>{t("kontrol.panel.durdur")}</Text>
        </TouchableOpacity>
      </View>
      <Text style={styles.durum} testID="modul-ornek-durum">
        {m.durum === null ? t("kontrol.modul.ornek.durumYok") : bobin ? t("kontrol.modul.ornek.bobinAcik") : t("kontrol.modul.ornek.bobinKapali")}
      </Text>
      {m.hata && (
        <Text style={styles.hata} testID="modul-ornek-hata">
          {modulHataMetni(t, m.hata)}
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  kutu: { gap: spacing.sm },
  baslik: { color: colors.text, fontSize: rf(14), fontWeight: "700" },
  satir: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  alan: { flexGrow: 1, minWidth: rs(110), gap: rs(4) },
  etiket: { color: colors.textMuted, fontSize: rf(12) },
  giris: {
    minHeight: touch.min,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: rs(8),
    color: colors.text,
    paddingHorizontal: rs(10),
  },
  dugme: {
    minHeight: touch.min,
    flexGrow: 1,
    justifyContent: "center",
    alignItems: "center",
    backgroundColor: colors.primary,
    borderRadius: rs(10),
    paddingHorizontal: rs(12),
  },
  durdur: { backgroundColor: colors.danger },
  dugmeMetin: { color: colors.white, fontSize: rf(13), fontWeight: "700" },
  durum: { color: colors.text, fontSize: rf(12) },
  hata: { color: colors.warning, fontSize: rf(12), fontWeight: "700" },
});
