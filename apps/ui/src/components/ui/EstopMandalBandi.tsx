// Author: mertaygn, cglrgrkn
/**
 * ACİL DURDURMA MANDALI BANDI — D1.81 · sahip kararı Y4.
 * ======================================================
 * Y4: "E-stop MANDALLANIR; operatörün ayrı ve bilinçli 'sıfırla' eylemi olmadan hiçbir START kabul edilmez.
 * Sıfırlama kendi başına yeniden başlatmaz; sıfırlamadan sonra yeni bir START ayrıca gerekir."
 *
 * Backend mandalı her acil durdurmada kurar (düğme, ESP alarmı, STM reddi; STM kopması / watchdog'u bobin ÇALIŞIRKEN —
 * seans olsun olmasın, sahip kararı Y45; boştayken kurmaz). Mandal DİSKE yazılır ve yeniden başlatmada kurulu kalır
 * (Y46): bant o zaman "önceki oturumda ACİL DURDUR — sıfırlanmadı" der. Kuruluyken elle
 * başlatma, AI (Auto), AI Pro (`/frame` ve döngü), mobil ve legacy START'ları REDDEDİLİR (409). Operatör nedenini
 * görmeli ve mandalı kaldırabilmeli — oturum açılmamışken de (Karşılama/Giriş ekranları; 1-C oturum talimatı).
 * 1-C inceleme i3-F-3 KAPANDI (D1.87, 1-E): bu iki ekranda artık kayan ACİL DURDUR da var (A-58 Karşılama / Y23 Giriş) —
 * ekran mandalı kaldırabildiği her yerde durdurabilir de.
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
  // Y46: mandal önceki süreçten (diskten) geldi — `onceki_oturum:<asıl neden>`; dosya okunamadıysa güvenli tarafta kurulu.
  if (n.startsWith("onceki_oturum:")) {
    const ic = n.slice("onceki_oturum:".length);
    const asil = ic === "dosya_okunamadi" ? "mandal dosyası okunamadı" : mandalNedeni(ic);
    return `önceki oturumda ACİL DURDUR — sıfırlanmadı (${asil})`;
  }
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
    const r = await apiPost<{ status?: string } | null>(SIFIRLA_YOLU, { onay: true }, null);
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
        {/* 1-C inceleme i3-F-2: "Bobinler durduruldu" GÜVENCESİ yazılmaz — mandal iletisi teyit taşımaz, E-stop teyitsiz
            bitebilir (kablo çıkık / ölü gönderici). Bant EYLEM söyler. */}
        <Text style={styles.alt}>
          {`Neden: ${mandalNedeni(mandal.neden)}. Bobinlerin durduğunu cihazda kontrol edin. Yeniden başlatmak için ` +
            'önce "Sıfırla"; sıfırlama bobinleri başlatmaz.'}
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
