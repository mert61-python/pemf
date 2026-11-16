// Author: mertaygn, cglrgrkn
/**
 * UYGULAMA İÇİ ONAY / UYARI PENCERESİ — YH-A4 (Tezgâh-2 listesi 4). Ayrıntı: `services/onayKoprusu.ts`.
 *
 * Kök düzende (`app/_layout.tsx`) bir kez takılır; `platformConfirm` / `platformAlert` (web) buraya düşer. İstekler SIRAYLA
 * gösterilir (aynı anda gelen ikinci soru birincinin yanıtını ezmez). Esc / geri tuşu = "Vazgeç" (onay türünde false).
 * ⚠️ ACİL DURDUR bu pencerenin ALTINDA KALMAZ: kayan ACİL DURDUR `document.body` portalıyla her RN-web Modal'ının üstündedir
 * (`UstKatman.web.tsx`, D1.E05 · İG-6.6); bu pencere de sıradan bir Modal'dır (Ö.4-Y8: STOP hiçbir pencereye bağlanmaz).
 * Sağlayıcı sökülürse bekleyen sorular "vazgeç" (false) ile çözülür — askıda söz kalmaz.
 */
import { ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { Modal, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useTranslation } from "react-i18next";
import { Card } from "@/components/ui/Card";
import { colors, radius, rf, rs, spacing, touch } from "@/theme/tokens";
import { OnayIstegi, setOnayIsleyici } from "@/services/onayKoprusu";

interface Bekleyen extends OnayIstegi {
  id: number;
  coz: (deger: boolean) => void;
}

export function OnayPenceresiSaglayici({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const [kuyruk, setKuyruk] = useState<Bekleyen[]>([]);
  const kuyrukRef = useRef<Bekleyen[]>([]);
  kuyrukRef.current = kuyruk;
  const sayac = useRef(0);

  const ac = useCallback(
    (istek: OnayIstegi) =>
      new Promise<boolean>((coz) => {
        sayac.current += 1;
        const id = sayac.current;
        setKuyruk((k) => [...k, { ...istek, id, coz }]);
      }),
    [],
  );

  useEffect(() => {
    setOnayIsleyici(ac);
    return () => {
      setOnayIsleyici(null);
      for (const b of kuyrukRef.current) b.coz(false);
    };
  }, [ac]);

  const ust = kuyruk[0];
  const kapat = (deger: boolean) => {
    if (!ust) return;
    ust.coz(deger);
    setKuyruk((k) => k.filter((b) => b.id !== ust.id));
  };
  const uyari = ust?.tur === "uyari";

  return (
    <>
      {children}
      <Modal visible={!!ust} transparent animationType="fade" onRequestClose={() => kapat(uyari)}>
        <View style={styles.perde}>
          {ust ? (
            <Card style={styles.kart}>
              <View style={styles.govde} accessibilityRole="alert" accessibilityViewIsModal testID="onay-penceresi">
                <Text style={styles.baslik} testID="onay-penceresi-baslik">{ust.baslik}</Text>
                {ust.govde ? <Text style={styles.metin} testID="onay-penceresi-govde">{ust.govde}</Text> : null}
                <View style={styles.satirBtn}>
                  {uyari ? null : (
                    <TouchableOpacity style={styles.ikincil} onPress={() => kapat(false)} accessibilityRole="button"
                      testID="onay-penceresi-vazgec">
                      <Text style={styles.ikincilText}>{t("ortak.iptal")}</Text>
                    </TouchableOpacity>
                  )}
                  <TouchableOpacity style={styles.birincil} onPress={() => kapat(true)} accessibilityRole="button"
                    testID="onay-penceresi-onay">
                    <Text style={styles.birincilText}>{uyari ? t("ortak.kapat") : ust.onayEtiketi || t("ortak.onayla")}</Text>
                  </TouchableOpacity>
                </View>
              </View>
            </Card>
          ) : null}
        </View>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  perde: { flex: 1, backgroundColor: "rgba(0,0,0,0.55)", alignItems: "center", justifyContent: "center", padding: spacing.md },
  kart: { width: "100%", maxWidth: rs(440), maxHeight: "92%" },
  govde: { gap: spacing.sm },
  baslik: { color: colors.text, fontSize: rf(16), fontWeight: "800" },
  metin: { color: colors.textMuted, fontSize: rf(13), lineHeight: rf(19) },
  satirBtn: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.xs },
  birincil: { flex: 1, backgroundColor: colors.cyan, borderRadius: radius.md, paddingVertical: rs(11), alignItems: "center",
              minHeight: touch.min, justifyContent: "center" },
  birincilText: { color: "#04121F", fontWeight: "800", fontSize: rf(13) },
  ikincil: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingVertical: rs(11),
             paddingHorizontal: spacing.md, minHeight: touch.min, justifyContent: "center" },
  ikincilText: { color: colors.textMuted, fontWeight: "700", fontSize: rf(12) },
});
