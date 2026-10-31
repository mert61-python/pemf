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
import i18n from "i18next";
import { useTranslation } from "react-i18next";

/** Backend ucu (apiClient tabanı `/api`). */
export const SIFIRLA_YOLU = "/hardware/estop_mandali/sifirla";

/** Acil durdurmanın kaynağı → operatörün anlayacağı metin. Bilinmeyen kaynak olduğu gibi gösterilmez (iç ad). */
export function mandalNedeni(neden?: string): string {
  const n = String(neden || "");
  // Y46: mandal önceki süreçten (diskten) geldi — `onceki_oturum:<asıl neden>`; dosya okunamadıysa güvenli tarafta kurulu.
  if (n.startsWith("onceki_oturum:")) {
    const ic = n.slice("onceki_oturum:".length);
    const asil = ic === "dosya_okunamadi" ? i18n.t("guvenlik.mandal.dosyaOkunamadi") : mandalNedeni(ic);
    return i18n.t("guvenlik.mandal.oncekiOturum", { asil });
  }
  if (n === "manual") return i18n.t("guvenlik.mandal.neden.manual");
  // 2026-10-18: launcher kapanışı (`/api/hardware/kapanis_durdur`) — diske YALNIZ bobin çalışırken / seans sürerken yazılır.
  if (n === "uygulama_kapanisi") return i18n.t("guvenlik.mandal.neden.uygulamaKapanisi");
  if (n === "stm_disconnected") return i18n.t("guvenlik.mandal.neden.stmKopusu");
  if (n === "stm_komut_reddi") return i18n.t("guvenlik.mandal.neden.komutReddi");
  if (n === "stm_watchdog_timeout") return i18n.t("guvenlik.mandal.neden.watchdog");
  if (n.startsWith("esp_alarm")) return i18n.t("guvenlik.mandal.neden.espAlarm");
  return i18n.t("guvenlik.mandal.neden.genel");
}

/**
 * TD6 · K12 (tezgâh Oturum 13): nedene göre NE YAPILACAĞI — eskiden her neden aynı cümleyi alıyordu. Backend `eylem` verdiyse
 * (kart reddi: duty metni ya da kart uyumsuzluğu) o; bağlantı kopması / watchdog → kablo; boş → yalnız genel cümle.
 */
export function mandalEylemi(neden?: string, eylem?: string, eylemler?: Partial<Record<string, string>>): string {
  // I18NI-A1.1: sunucu dil karşılığı verdiyse etkin dildeki (EN bant Türkçe cümle basmasın); yoksa (eski sunucu) `eylem` aynen.
  const yerel = eylemler ? String(eylemler[i18n.language] ?? "").trim() : "";
  if (yerel) return yerel;
  const e = String(eylem || "").trim();
  if (e) return e;
  const n = String(neden || "");
  const ic = n.startsWith("onceki_oturum:") ? n.slice("onceki_oturum:".length) : n;
  if (ic === "stm_disconnected" || ic === "stm_watchdog_timeout") return i18n.t("guvenlik.mandal.eylem.kablo");
  if (ic === "stm_komut_reddi") {
    return i18n.t("guvenlik.mandal.eylem.komutReddi");
  }
  return "";
}

export function EstopMandalBandi() {
  const { t } = useTranslation();
  const { snapshot, connectionQuality } = useLiveData();
  const [mesgul, setMesgul] = useState(false);
  const mandal = snapshot?.estopMandali;
  // Y228 (BE 2c · sahip): cihaza bağlı DEĞİLKEN bant gizli — son bilinen mandal ve çalışamayan "Sıfırla" gösterilmez; bağlanınca gerçek
  // durum gelir (Karşılama / Giriş dahil: aynı bileşen). ACİL DURDUR bu kuralın DIŞINDA (kayan düğme bağlantıdan bağımsız kalır).
  if (connectionQuality === "offline") return null;
  if (!mandal?.aktif) return null;
  // Y226 (BE 2a · sahip): PC'deki uygulama BOŞTAYKEN kapatıldı — mandal ve STOP'lar aynen, ama alarm yerine tek NÖTR satır (bağlantı birazdan
  // kopar; kopunca aynı satırı kabuk söyler).
  if (mandal.bostaKapanis === true) {
    return (
      <View style={styles.notr} testID="pc-kapandi-satiri">
        <Text style={styles.notrMetin}>{t("guvenlik.mandal.pcKapandi")}</Text>
      </View>
    );
  }
  const eylem = mandalEylemi(mandal.neden, mandal.eylem, mandal.eylemler);
  // Eylem metni "Sıfırla" adımını ZATEN söylüyorsa (duty reddi, Y74) bant onu ikinci kez yazmaz.
  // 13 §2-d: sunucu METNİNE göre dallanma YOK — makine-okur alan (`eylemSifirlaSoyler`) önce; alan yoksa (eski sunucu) eski metin eşleşmesi.
  const sifirlaSoylendi = typeof mandal.eylemSifirlaSoyler === "boolean" ? mandal.eylemSifirlaSoyler : /Sıfırla/.test(eylem);

  const sifirla = async () => {
    const onay = await platformConfirm(
      t("guvenlik.mandal.sifirlaBaslik"),
      t("guvenlik.mandal.sifirlaGovde"),
      t("guvenlik.mandal.sifirla")
    );
    if (!onay) return;
    setMesgul(true);
    const r = await apiPost<{ status?: string } | null>(SIFIRLA_YOLU, { onay: true }, null);
    setMesgul(false);
    if (r?.status === "success") {
      emitToast(t("guvenlik.mandal.sifirlandi"), "success");
    } else {
      platformAlert(t("guvenlik.mandal.sifirlanamadi"), t("guvenlik.mandal.sifirlanamadiGovde"));
    }
  };

  return (
    <View style={styles.bant} accessibilityRole="alert">
      <Lock color={colors.danger} size={rs(18)} />
      <View style={{ flex: 1 }}>
        <Text style={styles.baslik}>{t("guvenlik.mandal.baslik")}</Text>
        {/* 1-C inceleme i3-F-2: "Bobinler durduruldu" GÜVENCESİ yazılmaz — mandal iletisi teyit taşımaz, E-stop teyitsiz
            bitebilir (kablo çıkık / ölü gönderici). Bant EYLEM söyler. */}
        <Text style={styles.alt}>
          {t("guvenlik.mandal.altMetin", {
            neden: mandalNedeni(mandal.neden),
            eylem: eylem ? eylem + " " : "",
            sonuc: sifirlaSoylendi ? t("guvenlik.mandal.sifirlamaBaslatmaz") : t("guvenlik.mandal.onceSifirla"),
          })}
        </Text>
      </View>
      <Pressable
        onPress={sifirla}
        disabled={mesgul}
        style={[styles.dugme, mesgul && { opacity: 0.6 }]}
        accessibilityRole="button"
        accessibilityLabel={t("guvenlik.mandal.sifirlaEtiketi")}
        accessibilityHint={t("guvenlik.mandal.sifirlaIpucu")}
      >
        <Text style={styles.dugmeMetni}>{mesgul ? t("guvenlik.mandal.sifirlaniyor") : t("guvenlik.mandal.sifirla")}</Text>
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
  notr: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.sm, margin: spacing.sm },
  notrMetin: { color: colors.textMuted, fontSize: rf(12), textAlign: "center" },
});
