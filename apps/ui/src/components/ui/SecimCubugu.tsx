// Author: mertaygn
/**
 * SEÇİM ÇUBUĞU — toplu işlem kipindeki üst şerit.
 * ================================================
 * "N seçildi · Tümünü Seç / Temizle · Sil". Seans geçmişi ve hasta veritabanı AYNI şeridi
 * kullanır (bkz. `useCokluSecim`) → iki ekranda iki farklı toplu-silme deneyimi doğmaz.
 *
 * ⚠️ SİL DÜĞMESİ SEÇİM BOŞKEN DEVRE DIŞI: aktif bırakmak, "sil"e basan operatöre hiçbir şey
 * olmadığını düşündürür ve ikinci kez basmasına yol açardı — ikinci basış, bu arada bir kayıt
 * seçilmişse gerçekten siler.
 */
import { ActivityIndicator, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { colors, radius, rs, spacing, touch, typography } from "@/theme/tokens";

export function SecimCubugu({
  seciliSayi,
  hepsiSecili,
  onTumunuSec,
  onTemizle,
  onSil,
  onVazgec,
  siliniyor = false,
  silEtiketi = "Seçilenleri Sil",
  gizliSayi = 0,
  testID = "secim-cubugu",
}: {
  seciliSayi: number;
  hepsiSecili: boolean;
  onTumunuSec: () => void;
  onTemizle: () => void;
  onSil: () => void;
  onVazgec: () => void;
  siliniyor?: boolean;
  silEtiketi?: string;
  /**
   * EKRANA YÜKLENMEMİŞ / GÖSTERİLMEMİŞ kayıt sayısı (0 = hepsi ekranda).
   *
   * ⚠️ NEDEN VAR (denetim 2026-09-12): "Tümünü Seç" adına rağmen YALNIZ ekranda olanları
   * seçer — ki bu doğrudur (görmediğiniz kayıt silinemez, bkz. `useCokluSecim` hayalet
   * seçim). Ama adı "Tümünü" olan bir düğme 200 kayıtlık listede 60'ını seçince operatör
   * bunu FARK ETMİYOR. Sayı biliniyorsa açıkça söylenir.
   */
  gizliSayi?: number;
  testID?: string;
}) {
  const bosSecim = seciliSayi === 0;
  return (
    <View style={styles.cubuk} testID={testID}>
      <View style={styles.sayacAlani}>
        <Text style={styles.sayac} numberOfLines={1} testID={`${testID}-sayac`}>
          {bosSecim ? "Silmek için kayıt seçin" : `${seciliSayi} kayıt seçildi`}
        </Text>
        {gizliSayi > 0 ? (
          <Text style={styles.gizliNot} testID={`${testID}-gizli`}>
            {`${gizliSayi} kayıt ekranda değil — seçilmez`}
          </Text>
        ) : null}
      </View>
      <View style={styles.dugmeler}>
        <TouchableOpacity
          style={styles.ikincil}
          onPress={hepsiSecili ? onTemizle : onTumunuSec}
          accessibilityRole="button"
          testID={`${testID}-tumunu`}
        >
          <Text style={styles.ikincilYazi}>{hepsiSecili ? "Seçimi Temizle" : "Tümünü Seç"}</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={styles.ikincil}
          onPress={onVazgec}
          accessibilityRole="button"
          testID={`${testID}-vazgec`}
        >
          <Text style={styles.ikincilYazi}>Vazgeç</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.sil, (bosSecim || siliniyor) && styles.silPasif]}
          onPress={onSil}
          disabled={bosSecim || siliniyor}
          accessibilityRole="button"
          accessibilityState={{ disabled: bosSecim || siliniyor }}
          testID={`${testID}-sil`}
        >
          {siliniyor ? (
            <ActivityIndicator color={colors.white} />
          ) : (
            <Text style={styles.silYazi} numberOfLines={1}>
              {bosSecim ? silEtiketi : `${silEtiketi} (${seciliSayi})`}
            </Text>
          )}
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  cubuk: {
    flexDirection: "row",
    flexWrap: "wrap",
    alignItems: "center",
    justifyContent: "space-between",
    gap: spacing.sm,
    marginBottom: spacing.md,
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.primary,
    backgroundColor: colors.bgAlt,
  },
  sayacAlani: { flexShrink: 1 },
  sayac: { color: colors.text, fontSize: typography.body, fontWeight: "800" },
  gizliNot: { color: colors.textMuted, fontSize: typography.small, marginTop: 2 },
  dugmeler: { flexDirection: "row", flexWrap: "wrap", alignItems: "center", gap: spacing.sm },
  ikincil: {
    paddingHorizontal: spacing.md,
    borderRadius: rs(8),
    borderWidth: 1,
    borderColor: colors.border,
    minHeight: touch.min,
    justifyContent: "center",
  },
  ikincilYazi: { color: colors.primary, fontWeight: "700", fontSize: typography.small },
  sil: {
    paddingHorizontal: spacing.lg,
    borderRadius: rs(8),
    backgroundColor: colors.danger,
    minHeight: touch.min,
    justifyContent: "center",
    alignItems: "center",
  },
  silPasif: { opacity: 0.45 },
  silYazi: { color: colors.white, fontWeight: "800", fontSize: typography.small },
});
