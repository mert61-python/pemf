/**
 * KALİBRASYON ROZETİ — "3B konum gerçekten ölçüldü mü?" sorusunun sade dille yanıtı.
 *
 * Sahip kararı #4: kabin işareti (ArUco) ZORUNLU. Backend işaretsiz yöntemlere güven tavanı
 * uygular (`YONTEM_TAVANI_VARSAYILAN` 0,25 < eşik 0,3) → işaret görünmezse öneri hiç üretilmez.
 * Rozet o REDDİ önceden anlaşılır kılar: operatör "neden öneri gelmiyor" diye beklemez, kamerayı
 * ya da yerleşimi düzeltir.
 *
 * ⚠️ Ham yöntem adı (`aruco_pnp`, `phantom_length`, `pixel`) kullanıcıya GÖSTERİLMEZ — eylem
 * söyleyen hata kuralı. Teknik ad yalnız erişilebilirlik ipucunda/log'da anlamlıdır.
 */
import { View, Text, StyleSheet } from "react-native";
import { colors, spacing, typography } from "@/theme/tokens";

export function KalibrasyonRozeti({ yontem, gorunur = true }: { yontem?: string; gorunur?: boolean }) {
  if (!gorunur) return null;
  const y = String(yontem || "");
  const kalibre = y === "aruco_pnp";
  if (!y) {
    return (
      <View style={[styles.rozet, styles.bekliyor]}>
        <Text style={styles.metin}>3B konum: henüz ölçülmedi — kamera açılınca ölçülür.</Text>
      </View>
    );
  }
  return (
    <View style={[styles.rozet, kalibre ? styles.iyi : styles.kotu]}>
      <Text style={styles.metin}>
        {kalibre
          ? "3B konum: kabin işaretiyle doğrulandı ✓"
          : "Konum ölçülemedi — kabin işareti (arka duvardaki kare kod) kadrajda görünmüyor. " +
            "Kamerayı işaret ve hedef aynı karede kalacak şekilde ayarlayın."}
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
