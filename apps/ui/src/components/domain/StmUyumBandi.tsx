// Author: mertaygn, cglrgrkn
/**
 * CİHAZ KARTI UYUM BANDI — TD1 (tezgâh Oturum 13, 2026-10-14; kullanıcı geri bildirimi K1 / K2).
 *
 * ÖLÇÜLDÜ: kartın yazılımı uygulamayla uyumsuzken (120 baytlık saha imajı ↔ 121 baytlık paket) Ana Ekran "Donanım" YEŞİL,
 * STM32 "Bağlı ✅" görünüyordu; neden yalnız seans başlatınca 409'da ve geliştirici diliyle ("CubeIDE … Açılış satırı '7-ch'
 * demeli" — uyumsuz kart da 7-ch der) çıkıyordu. Backend `hardware.stm.uyumsuz` olayının arayüzde abonesi yoktu.
 * Artık backend kararı (`stmUyum`, WS `stm_uyum`) her ekranda kalıcı bant olarak görünür:
 *   * uyumsuz (`uyumlu: false`) → KIRMIZI: "Cihaz kartının yazılımı bu uygulama sürümüyle uyumsuz — bobinler çalışmaz.
 *     Teknik desteği arayın (kod: FW-PAKET)."
 *   * doğrulanamadı (`uyumlu: null` + kod) → SARI: "Cihaz kartı doğrulanamadı. Kartın üzerindeki SİYAH sıfırlama düğmesine
 *     bir kez basın (mavi değil)."
 * Metin backend'den gelir (tek kaynak `utils/stm32_kimlik.OPERATOR_METNI`); gelmezse aynı metin yedekte. Teknik ayrıntı
 * (destek / servis: python / yakma talimatı) yalnız "Teknik ayrıntı" açılınca. Kapatma düğmesi YOK — durum düzelince kalkar.
 * ⚠️ "Bağlı" ile "uyumlu" AYRI (hafıza "Bağlantı 2-durum"): bağlantı göstergesine üçüncü durum EKLENMEZ.
 * ⚠️ Bant hiçbir şeyi KAPILAMAZ (Ö.4-Y8: ACİL DURDUR her koşulda erişilebilir).
 */
import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { Cpu } from "lucide-react-native";

import { useLiveData } from "@/context/LiveDataContext";
import { colors, radius, rf, rs, spacing, touch } from "@/theme/tokens";
import type { ConnectionState, DashboardSnapshot, StmUyum } from "@/types/domain";
import { useTranslation } from "react-i18next";
import i18n from "i18next";

const k1Yedek = (): string => i18n.t("guvenlik.stmUyum.k1Yedek");
const k2Yedek = (): string => i18n.t("guvenlik.stmUyum.k2Yedek");

export interface StmUyumBandiMetni {
  tur: "kirmizi" | "sari";
  mesaj: string;
  ayrinti: string;
}

/** Gösterilecek bant; gerekmiyorsa null. Uyumsuz → kırmızı; doğrulanamadı (null + kod) → sarı; aksi (uyumlu / bilinmiyor) yok. */
export function stmUyumBandiMetni(u: StmUyum | null | undefined): StmUyumBandiMetni | null {
  if (!u) return null;
  const mesaj = typeof u.mesaj === "string" ? u.mesaj.trim() : "";
  const ayrinti = typeof u.ayrinti === "string" ? u.ayrinti.trim() : "";
  if (u.uyumlu === false) return { tur: "kirmizi", mesaj: mesaj || k1Yedek(), ayrinti };
  if (u.uyumlu === null && u.kod) return { tur: "sari", mesaj: mesaj || k2Yedek(), ayrinti };
  return null;
}

/** Ana Ekran "Donanım" rozeti: bağlıyken kart uyumsuzsa YEŞİL OLMAZ (kırmızı ton), doğrulanamadıysa sarı. */
export function donanimRozetDurumu(s: Pick<DashboardSnapshot, "stm" | "stmUyum">): ConnectionState {
  if (s.stm === "online" && s.stmUyum?.uyumlu === false) return "error";
  if (s.stm === "online" && s.stmUyum?.uyumlu === null && s.stmUyum?.kod) return "warning";
  return s.stm;
}

export function StmUyumBandi() {
  const { t } = useTranslation();
  const { snapshot } = useLiveData();
  const [ayrintiAcik, setAyrintiAcik] = useState(false);
  const bant = stmUyumBandiMetni(snapshot.stmUyum);
  if (!bant) return null;
  const kirmizi = bant.tur === "kirmizi";
  return (
    <View style={[styles.bant, kirmizi ? styles.kirmizi : styles.sari]} accessibilityRole="alert" testID="stm-uyum-bandi">
      <Cpu color={kirmizi ? colors.danger : colors.warning} size={rs(16)} />
      <View style={{ flex: 1 }}>
        <Text style={styles.baslik}>{bant.mesaj}</Text>
        {bant.ayrinti ? (
          <Pressable
            onPress={() => setAyrintiAcik((a) => !a)}
            accessibilityRole="button"
            accessibilityLabel={ayrintiAcik ? t("guvenlik.stmUyum.ayrintiGizle") : t("guvenlik.stmUyum.ayrintiGosterEtiketi")}
            style={styles.ayrintiDugme}
          >
            <Text style={styles.ayrintiDugmeYazi}>
              {ayrintiAcik ? t("guvenlik.stmUyum.ayrintiGizle") : t("guvenlik.stmUyum.ayrintiGoster")}
            </Text>
          </Pressable>
        ) : null}
        {ayrintiAcik && bant.ayrinti ? (
          <Text style={styles.alt} selectable>
            {bant.ayrinti}
          </Text>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  bant: { flexDirection: "row", alignItems: "center", gap: spacing.sm, borderWidth: 1,
          borderRadius: radius.md, padding: spacing.sm, margin: spacing.sm },
  kirmizi: { backgroundColor: colors.dangerSoft, borderColor: colors.danger },
  sari: { backgroundColor: colors.panel, borderColor: colors.warning },
  baslik: { color: colors.text, fontSize: rf(13), fontWeight: "800" },
  ayrintiDugme: { minHeight: touch.min, justifyContent: "center", alignSelf: "flex-start" },
  ayrintiDugmeYazi: { color: colors.textMuted, fontSize: rf(11), textDecorationLine: "underline" },
  alt: { color: colors.textMuted, fontSize: rf(11), marginTop: rs(2), lineHeight: rf(16) },
});
