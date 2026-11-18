// Author: mertaygn, cglrgrkn
/**
 * ALAN SENSÖRÜ BANDI (ODD B-6 · ODK-B keşfi 18-11, sahip ekranı 1–2): Y285 MLX bekçisi bir bobinin `B=` telemetrisi kesilince sensörü
 * DÜŞTÜ ilan eder (`coil_status.alanKayip`) ve zile bildirim düşer — ama SEANS sürerken operatör bunu görmüyordu (zil listesine sessizce).
 * Bant, seans / sürüş varken HER ekranda görünür; sensör yeniden bağlanınca (`alanKayip` iner) ya da sürüş bitince kendiliğinden kalkar.
 * Metin "alan sensörü (MLX)" der (kartta TEK MLX var — "Bobin 6 manyetik alan sensörü" kullanıcıya bobine ait bir parça gibi okunuyordu).
 * Bant hiçbir şeyi KAPILAMAZ (Ö.4-Y8: ACİL DURDUR her koşulda erişilebilir) ve sürüşü durdurmaz (yalnız gösterim).
 */
import { StyleSheet, Text, View } from "react-native";
import { Magnet } from "lucide-react-native";
import i18n from "i18next";
import { useTranslation } from "react-i18next";

import { useLiveData } from "@/context/LiveDataContext";
import { colors, radius, rf, rs, spacing } from "@/theme/tokens";

type BantCoil = { id?: number; running?: boolean; alanKayip?: boolean };
type BantSnapshot = { coils?: BantCoil[] | null; activeTreatment?: { isActive?: boolean } | null } | null | undefined;

/** Gösterilecek metin; bant gerekmiyorsa null. YALNIZ sürüş / seans varken ve en az bir bobinde `alanKayip === true` iken. */
export function alanSensoruBandiMetni(snapshot: BantSnapshot): { baslik: string; aciklama: string } | null {
  const coils = Array.isArray(snapshot?.coils) ? snapshot!.coils! : [];
  const kayip = coils.filter((c) => c?.alanKayip === true);
  if (!kayip.length) return null;
  const surus = snapshot?.activeTreatment?.isActive === true || coils.some((c) => c?.running === true);
  if (!surus) return null;
  const kanal = kayip.map((c) => String(c.id ?? "?")).join(", ");
  return {
    baslik: i18n.t("bant.alanSensoru.baslik"),
    aciklama: i18n.t("bant.alanSensoru.aciklama", { kanal }),
  };
}

export function AlanSensoruBandi() {
  useTranslation(); // metin çağrı anında çevrilir → dil değişince yeniden çiz
  const { snapshot } = useLiveData();
  const metin = alanSensoruBandiMetni(snapshot as BantSnapshot);
  if (!metin) return null;
  return (
    <View style={styles.bant} accessibilityRole="alert" testID="alan-sensoru-bandi">
      <Magnet color={colors.warning} size={rs(16)} />
      <View style={{ flex: 1 }}>
        <Text style={styles.baslik}>{metin.baslik}</Text>
        <Text style={styles.alt}>{metin.aciklama}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  bant: { flexDirection: "row", alignItems: "center", gap: spacing.sm,
          backgroundColor: colors.warningSoft, borderWidth: 1, borderColor: colors.warning,
          borderRadius: radius.md, padding: spacing.sm, margin: spacing.sm },
  baslik: { color: colors.text, fontSize: rf(13), fontWeight: "800" },
  alt: { color: colors.textMuted, fontSize: rf(11), marginTop: rs(2), lineHeight: rf(16) },
});
