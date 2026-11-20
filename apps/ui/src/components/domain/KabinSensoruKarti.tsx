// Author: mertaygn, cglrgrkn
/**
 * KABİN SENSÖRÜ (MLX) KARTI — Y306 (sahip 19-11, madde 6): tek MLX alan sensörü kabinde GEZDİRİLİYOR; değer bir bobinin değil KABİNİN
 * sensörüdür. Ana Ekran, Kontrol ve Sensörler'de AYNI bileşen, bobin kartlarından AYRI. Değer yalnız kanal gerçekten ÖLÇÜYORSA
 * (`measuredFields`, Y6 / D1.67) ve kazanç ayarı doğrulandıysa (TD2) gösterilir; yoksa "—" (0 UYDURULMAZ). Masaüstü + telefon aynı.
 * Hiçbir sürüş / ACİL DURDUR koşulu buradan geçmez — yalnız gösterim.
 */
import { StyleSheet, Text, View } from "react-native";
import { useTranslation } from "react-i18next";
import { Magnet } from "lucide-react-native";
import { useLiveData } from "@/context/LiveDataContext";
import { colors, rf, rs, spacing } from "@/theme/tokens";
import { ondalikMetni } from "@/i18n/dil";
import { alanGosterilebilir } from "@/utils/olculenAlan";
import { KABIN_SENSORU_KANALI } from "@/utils/kabinSensoru";
import type { CoilStatus } from "@/types/domain";

/** Kabin sensörü kanalının canlı alanı (mT) — ölçülmüyorsa / doğrulanamadıysa null. */
export function kabinSensoruAlani(coils: CoilStatus[] | null | undefined): number | null {
  const k = (coils ?? []).find((c) => Number(c?.id) === KABIN_SENSORU_KANALI);
  if (!k || (k as { alanDogrulanamadi?: boolean }).alanDogrulanamadi) return null;
  if (!alanGosterilebilir(k, "magneticMt")) return null;
  const v = Number((k as { magneticMt?: unknown }).magneticMt);
  return Number.isFinite(v) ? v : null;
}

export function KabinSensoruKarti({ testID = "kabin-sensoru-karti" }: { testID?: string }) {
  const { t } = useTranslation();
  const { snapshot } = useLiveData();
  const k = (snapshot?.coils ?? []).find((c) => Number(c?.id) === KABIN_SENSORU_KANALI);
  const deger = kabinSensoruAlani(snapshot?.coils);
  const dogrulanamadi = Boolean((k as { alanDogrulanamadi?: boolean } | undefined)?.alanDogrulanamadi);
  return (
    <View style={styles.kart} testID={testID} accessibilityLabel={t("kontrol.kabinSensoru.baslik")}>
      <View style={styles.baslikSatiri}>
        <Magnet size={rs(16)} color={colors.cyan} />
        <Text style={styles.baslik}>{t("kontrol.kabinSensoru.baslik")}</Text>
        <Text style={styles.deger} testID="kabin-sensoru-deger">
          {deger === null ? "—" : `${ondalikMetni(deger, 2)} mT`}
        </Text>
      </View>
      {dogrulanamadi ? <Text style={styles.uyari}>{t("kontrol.bobin.sensorDogrulanamadi")}</Text> : null}
      <Text style={styles.aciklama}>{t("kontrol.kabinSensoru.aciklama")}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  kart: {
    backgroundColor: colors.panel,
    borderRadius: rs(14),
    padding: rs(12),
    gap: rs(6),
    borderWidth: 1,
    borderColor: colors.border,
  },
  baslikSatiri: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  baslik: { flex: 1, color: colors.text, fontSize: rf(14), fontWeight: "700" },
  deger: { color: colors.cyan, fontSize: rf(16), fontWeight: "800" },
  aciklama: { color: colors.textMuted, fontSize: rf(11) },
  uyari: { color: colors.warning, fontSize: rf(11), fontWeight: "700" },
});
