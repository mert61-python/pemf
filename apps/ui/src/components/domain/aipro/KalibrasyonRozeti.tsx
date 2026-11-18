/**
 * KALİBRASYON ROZETİ — "3B konum gerçekten ölçüldü mü?" sorusunun sade dille yanıtı.
 *
 * Sahip kararı #4: kabin işareti (ArUco) ZORUNLU. Backend işaretsiz yöntemlere güven tavanı
 * uygular (`YONTEM_TAVANI_VARSAYILAN` 0,25 < eşik 0,3) → işaret görünmezse öneri hiç üretilmez.
 * Rozet o REDDİ önceden anlaşılır kılar: operatör "neden öneri gelmiyor" diye beklemez, kamerayı
 * ya da yerleşimi düzeltir.
 *
 * KD-3a (B-KD3a.1, tezgâh 2026-11-11): SABİT DÜZLEM kipinde (`sabit_duzlem` — kabin kalibrasyonu, ArUco ARANMAZ) rozet
 * "kabin işareti (kare kod) görünmüyor" diyordu: konum ölçülse de (onay penceresi) kapı kalibrasyon nedeniyle kesse de
 * (taban ayarı yanlış → "kamera oynamış"). Artık: ölçüldüyse "kabin kalibrasyonuyla ölçüldü ✓"; kapı FİZİKSEL nedenle
 * kestiyse sunucunun EYLEM metni (`kapiEylem`, istek / cihaz dilinde); ikisi de yoksa "numune aranıyor".
 *
 * ⚠️ Ham yöntem adı (`aruco_pnp`, `sabit_duzlem`, `phantom_length`, `pixel`) kullanıcıya GÖSTERİLMEZ — eylem
 * söyleyen hata kuralı. Teknik ad yalnız erişilebilirlik ipucunda/log'da anlamlıdır.
 */
import { View, Text, StyleSheet } from "react-native";
import { colors, spacing, typography } from "@/theme/tokens";
import { useTranslation } from "react-i18next";

export function KalibrasyonRozeti({
  yontem,
  gorunur = true,
  localized = false,
  kapiEylem = "",
  kameraAcik = false,
}: {
  yontem?: string;
  gorunur?: boolean;
  /** Konum bu karede ölçüldü mü (onay penceresinde her zaman true — öneri yalnız lokalize karede üretilir). */
  localized?: boolean;
  /** KD-3a: kapının FİZİKSEL eylem metni (sunucu `kapiEylem`; kesmediyse boş). */
  kapiEylem?: string;
  /** ODD K-4: kamera açık (önizleme / seans) — yöntem henüz gelmediyse "kamera açılınca ölçülür" DEĞİL "ölçülüyor". */
  kameraAcik?: boolean;
}) {
  const { t } = useTranslation();
  if (!gorunur) return null;
  const y = String(yontem || "");
  if (y === "sabit_duzlem") {
    const eylem = String(kapiEylem || "");
    const durum = localized ? "iyi" : eylem ? "kotu" : "bekliyor";
    return (
      <View style={[styles.rozet, styles[durum]]} testID={`kalibrasyon-rozeti-duzlem-${durum}`}>
        <Text style={styles.metin}>
          {localized
            ? t("ai.pro.kalibrasyon.duzlemOlculdu")
            : eylem
              ? t("ai.pro.kalibrasyon.duzlemOlculemedi", { eylem })
              : t("ai.pro.kalibrasyon.duzlemBekliyor")}
        </Text>
      </View>
    );
  }
  const kalibre = y === "aruco_pnp";
  if (!y) {
    return (
      <View style={[styles.rozet, styles.bekliyor]}>
        <Text style={styles.metin}>{kameraAcik ? t("ai.pro.kalibrasyon.olculuyor") : t("ai.pro.kalibrasyon.bekliyor")}</Text>
      </View>
    );
  }
  return (
    <View style={[styles.rozet, kalibre ? styles.iyi : styles.kotu]}>
      <Text style={styles.metin}>
        {kalibre
          ? t("ai.pro.kalibrasyon.dogrulandi")
          : t("ai.pro.kalibrasyon.olculemedi")}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  rozet: { borderRadius: 8, paddingHorizontal: spacing.sm, paddingVertical: spacing.xs, borderWidth: 1 },
  iyi: { backgroundColor: colors.successSoft, borderColor: colors.success },
  kotu: { backgroundColor: colors.warningSoft, borderColor: colors.warning },
  bekliyor: { backgroundColor: "#0f172a", borderColor: "#1e293b" },
  metin: { color: colors.text, fontSize: typography.small, fontWeight: "700" },
});
