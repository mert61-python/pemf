// Author: mertaygn, cglrgrkn
/**
 * GlobalEmergencyStop — donanım çalışırken HER ekranda görünen acil durdurma.
 * =========================================================================
 * NEDEN: ACİL DURDUR yalnız üç yerde vardı — DashboardScreen, ControlScreen'in sayfa sonu ve
 * SessionProgressCard. Uygulamanın 10 rotasının 8'inde (Akıllı Teşhis, Ayarlar, Tedavi Geçmişi,
 * Hastalar, Raporlar, Sensörler, AI Geçmişi, Simülasyon) durdurma kontrolü YOKTU. Üstelik
 * ControlScreen'deki buton sticky değil: Manuel sekmede 8 bobinlik panelin altında kaldığından
 * ekran dışına kayıyordu. Otonom sürüş (AI Pro / AI-Auto) tam da AI Hub'dan başlatılabildiği
 * hâlde o ekranda hiç durdurma yoktu.
 *
 * Buton, seans bayrağından BAĞIMSIZ olarak "herhangi bir bobin çalışıyor VEYA aktif tedavi var"
 * durumunda belirir: AI Pro / fiziksel / başka istemci bobinleri enerjileyip session_* yayınlamaz,
 * bu yüzden yalnız `activeTreatment.isActive`e bakmak yanıltıcıdır (DashboardScreen'deki
 * `hardwareRunning` mantığının aynısı).
 */
import { useEffect, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { colors, radius, rf, rs, spacing } from "@/theme/tokens";
import { useLiveData } from "@/context/LiveDataContext";
import { platformAlert } from "@/services/apiClient";
import {
  performEmergencyStop,
  EMERGENCY_STOP_UNCONFIRMED_TITLE,
  EMERGENCY_STOP_UNCONFIRMED_BODY,
} from "@/services/emergencyStop";
import { emitToast } from "@/services/toastBridge";

export function GlobalEmergencyStop({ bottomOffset = 0 }: { bottomOffset?: number }) {
  const { snapshot } = useLiveData();
  const insets = useSafeAreaInsets();
  const [busy, setBusy] = useState(false);

  const running = (snapshot.coils ?? []).filter((c) => c?.running).length;
  const active = snapshot.activeTreatment?.isActive === true;

  // ⚠️ HASTA GÜVENLİĞİ — [ekranB-2, 2026-09-04 responsive denetimi]
  // STM seri bağlantısı koptuğunda `LiveDataContext.normalizeStmCoils` 1-5 numaralı bobinleri
  // `running:false` yapar. Bu "bobin DURDU" değil, "durum BİLİNMİYOR" demektir — üstelik WiFi
  // bobinleri (6-8) o sırada gerçekten sürülüyor olabilir. Eski kod belirsizliği "hiçbir şey
  // çalışmıyor" sayıp acil durdurma düğmesini TAM DA operatörün en çok ihtiyaç duyduğu anda
  // gizliyordu. KURAL: bir kez "çalışıyor" gördüysek, STM yeniden çevrimiçi olup "durdu" diyene
  // kadar düğme EKRANDA KALIR. Hiç çalışmamışsa (donanımsız/demo makine) gürültü yapmaz.
  const stmBelirsiz = snapshot.stm !== "online";
  const [belirsizKilit, setBelirsizKilit] = useState(false);
  useEffect(() => {
    if (running > 0 || active) setBelirsizKilit(true);
    else if (!stmBelirsiz) setBelirsizKilit(false);
  }, [running, active, stmBelirsiz]);
  const belirsiz = stmBelirsiz && belirsizKilit && running === 0 && !active;

  if (!running && !active && !belirsiz) return null;

  const onPress = async () => {
    // Çift-tık koruması YOK (bilinçli): panik anındaki ikinci dokunuş yutulmamalı. `busy` yalnız
    // görsel geri bildirim içindir, dokunuşu engellemez.
    setBusy(true);
    emitToast("Acil durdurma gönderiliyor…", "info");
    const { confirmed } = await performEmergencyStop();
    setBusy(false);
    if (confirmed) emitToast("Tüm bobinler durduruldu ✓", "success");
    else platformAlert(EMERGENCY_STOP_UNCONFIRMED_TITLE, EMERGENCY_STOP_UNCONFIRMED_BODY);
  };

  return (
    <View style={[styles.wrap, { bottom: bottomOffset + insets.bottom + spacing.md }]} pointerEvents="box-none">
      <Pressable
        onPress={onPress}
        style={styles.btn}
        accessibilityRole="button"
        accessibilityLabel="Acil durdur"
        accessibilityHint="Tüm bobinleri anında durdurur ve aktif seansı sonlandırır"
      >
        <Text style={styles.text} numberOfLines={1} adjustsFontSizeToFit>
          {busy
            ? "🚨 DURDURULUYOR…"
            : belirsiz
              ? "🚨 ACİL DURDUR (bağlantı yok)"
              : `🚨 ACİL DURDUR${running > 0 ? ` (${running} bobin)` : ""}`}
        </Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    position: "absolute",
    left: spacing.md,
    right: spacing.md,
    alignItems: "center",
    zIndex: 10000,
  },
  btn: {
    backgroundColor: colors.danger,
    borderRadius: radius.md,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.xl,
    minHeight: rs(52),
    alignItems: "center",
    justifyContent: "center",
    alignSelf: "stretch",
    maxWidth: rs(520),
    shadowColor: "#000",
    shadowOpacity: 0.45,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: rs(4) },
    elevation: 12,
    borderWidth: 2,
    borderColor: "#fff3",
  },
  text: { color: "#fff", fontWeight: "800", fontSize: rf(15), letterSpacing: 0.4 },
});
