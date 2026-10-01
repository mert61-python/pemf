// Author: mertaygn, cglrgrkn
/**
 * ACİL DURDURMA MANDALI BANDI — D1.81 · sahip kararı Y4.
 * ======================================================
 * Y4: "E-stop MANDALLANIR; operatörün ayrı ve bilinçli 'sıfırla' eylemi olmadan hiçbir START kabul edilmez.
 * Sıfırlama kendi başına yeniden başlatmaz; sıfırlamadan sonra yeni bir START ayrıca gerekir."
 *
 * Backend mandalı her acil durdurmada (düğme, STM kopması/reddi/watchdog'u, ESP alarmı) kurar; kuruluyken elle
 * başlatma, AI (Auto), AI Pro (`/frame` ve döngü), mobil ve legacy START'ları REDDEDİLİR (409). Operatör nedenini
 * görmeli ve mandalı kaldırabilmeli — oturum açılmamışken de (Karşılama/Giriş ekranları; A-58/Y23 ile tutarlı:
 * ACİL DURDUR'un olduğu her yerde mandal durumu ve "Sıfırla" da olmalı).
 *
 * Durum WS anlık görüntüsünden/`estop_mandali` iletisinden gelir (`snapshot.estopMandali`). Alan yoksa (eski
 * backend) bant YOK. "Sıfırla" onay ister (bilinçli eylem) ve yalnız mandalı kaldırır — bobin BAŞLATMAZ.
 * Bant hiçbir şeyi KAPILAMAZ: ACİL DURDUR her koşulda erişilebilir kalır (Ö.4-Y8).
 */
import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { Lock } from "lucide-react-native";

import { useLiveData } from "@/context/LiveDataContext";
import { apiPost, platformAlert, platformConfirm } from "@/services/apiClient";
import { emitToast } from "@/services/toastBridge";
import { colors, radius, rf, rs, spacing, touch } from "@/theme/tokens";

/** Backend ucu (apiClient tabanı `/api`). */
export const SIFIRLA_YOLU = "/hardware/estop_mandali/sifirla";

/** Acil durdurmanın kaynağı → operatörün anlayacağı metin. Bilinmeyen kaynak olduğu gibi gösterilmez (iç ad). */
export function mandalNedeni(neden?: string): string {
  const n = String(neden || "");
  if (n === "manual") return "ACİL DURDUR düğmesi";
  if (n === "stm_disconnected") return "STM32 bağlantı kaybı";
  if (n === "stm_komut_reddi") return "kart komutları reddetti";
  if (n === "stm_watchdog_timeout") return "STM32 watchdog zaman aşımı";
  if (n.startsWith("esp_alarm")) return "ESP güvenlik alarmı";
  return "acil durdurma";
}

export function EstopMandalBandi() {
  const { snapshot } = useLiveData();
  const [mesgul, setMesgul] = useState(false);
  const mandal = snapshot?.estopMandali;
  if (!mandal?.aktif) return null;

  const sifirla = async () => {
    const onay = await platformConfirm(
      "Acil durdurma mandalı sıfırlansın mı?",
      "Sıfırlama bobinleri BAŞLATMAZ. Bobinlerin durduğunu ve hastanın güvende olduğunu kontrol edin; " +
        "tedaviye devam etmek için başlatmayı ayrıca verin.",
      "Sıfırla"
    );
    if (!onay) return;
    setMesgul(true);
    const r = await apiPost<{ status?: string } | null>(SIFIRLA_YOLU, {}, null);
    setMesgul(false);
    if (r?.status === "success") {
      emitToast("Mandal sıfırlandı — başlatma yeniden mümkün (bobinler başlatılmadı)", "success");
    } else {
      platformAlert("Mandal sıfırlanamadı", "Cihaza ulaşılamadı ya da istek reddedildi. Bağlantıyı kontrol edip yeniden deneyin.");
    }
  };

  return (
    <View style={styles.bant} accessibilityRole="alert">
      <Lock color={colors.danger} size={rs(18)} />
      <View style={{ flex: 1 }}>
        <Text style={styles.baslik}>ACİL DURDURMA MANDALLI — yeni başlatma kapalı</Text>
        <Text style={styles.alt}>
          {`Neden: ${mandalNedeni(mandal.neden)}. Bobinler durduruldu. Yeniden başlatmak için önce "Sıfırla"; ` +
            "sıfırlama bobinleri başlatmaz."}
        </Text>
      </View>
      <Pressable
        onPress={sifirla}
        disabled={mesgul}
        style={[styles.dugme, mesgul && { opacity: 0.6 }]}
        accessibilityRole="button"
        accessibilityLabel="Acil durdurma mandalını sıfırla"
        accessibilityHint="Mandalı kaldırır; bobinleri başlatmaz"
      >
        <Text style={styles.dugmeMetni}>{mesgul ? "Sıfırlanıyor…" : "Sıfırla"}</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  bant: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    backgroundColor: colors.dangerSoft,
    borderWidth: 1,
    borderColor: colors.danger,
    borderRadius: radius.md,
    padding: spacing.sm,
    margin: spacing.sm,
  },
  baslik: { color: colors.text, fontSize: rf(13), fontWeight: "800" },
  alt: { color: colors.textMuted, fontSize: rf(11), marginTop: rs(2), lineHeight: rf(16) },
  dugme: {
    minHeight: touch.min,
    paddingHorizontal: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.danger,
    alignItems: "center",
    justifyContent: "center",
  },
  dugmeMetni: { color: colors.danger, fontWeight: "800", fontSize: rf(13) },
});
