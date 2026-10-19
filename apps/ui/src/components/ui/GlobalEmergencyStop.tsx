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
import { Platform, Pressable, StyleSheet, Text, View, type ViewStyle } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { colors, radius, rf, rs, spacing, touch } from "@/theme/tokens";
import { useLiveData } from "@/context/LiveDataContext";
import { platformAlert } from "@/services/apiClient";
import { performEmergencyStop } from "@/services/emergencyStop";
import { emitToast } from "@/services/toastBridge";
// I18N (T11a): metinler `kritikMetin` ile — katalog bozuk / anahtar eksik / i18n başlatılamamış olsa da sabit iki dilli yedek;
// react-i18next'e (Suspense / hazır-değil) BAĞLANMAZ. Kapı: tests/test_i18n_kritik_K5.py + GlobalEmergencyStop.I18N0.kritik.test.tsx.
import { kritikMetin, useKritikDil } from "@/i18n/kritik";
import { useStmBelirsiz } from "@/hooks/useStmBelirsiz";
import { UstKatman } from "@/components/ui/UstKatman";

/**
 * WEB KATMANI (D1.E05 · İG-6.6): düğme `document.body`'ye portalla, `position: fixed` ve bu katmanla çizilir.
 * react-native-web her açık Modal'ı body düzeyinde `z-index: 9999` ile çizer; uygulama kökünün içindeki düğme o
 * katmanın ALTINDA kalıyordu (Modal açıkken dokunuş Modal'a gidiyordu, ölçüldü). Değer 32 bit tamsayının üst
 * sınırına yakın: başka bir tam ekran örtü (Modal, bildirim, rehber) kayan ACİL DURDUR'un üstüne çıkamaz.
 */
export const GES_WEB_KATMAN = 2147483000;
const webUstKatman = { position: "fixed", zIndex: GES_WEB_KATMAN } as unknown as ViewStyle;

export function GlobalEmergencyStop({
  bottomOffset = 0,
  compact = false,
  gizle = false,
}: {
  bottomOffset?: number;
  /** Kısa ekranda (yatay telefon) dar ve sağa hizalı çizilir — ASLA gizlenmez/küçülmez. */
  compact?: boolean;
  /**
   * Bu ROTA KENDİ durdurma düğmesini çiziyor mu? (sahip bildirimi 2026-09-12:
   * "seans başlatınca şu sol altta çıkan acil durdurma kutusunu kaldır zaten bir sürü var")
   *
   * ⚠️ KAPSAM BİLEREK DAR: sahibin gerekçesi FAZLALIKTIR, durdurmaya karşı olmak değil.
   * Uygulamanın 10 rotasının 8'inde (Akıllı Teşhis, Ayarlar, Geçmiş, Hastalar, Raporlar,
   * Sensörler, AI Geçmişi, Simülasyon) bu düğme TEK durdurma kontrolüdür ve otonom sürüş
   * tam da Akıllı Teşhis'ten başlatılabiliyor. Oralarda gizlemek, fazlalığı değil ERİŞİMİ
   * kaldırmak olurdu. Bu yüzden bayrak YALNIZ kendi düğmesi olan rotalarda true olur.
   * Kapı: `globalAcilDurdurKapsami.test.tsx`.
   */
  gizle?: boolean;
}) {
  const { snapshot } = useLiveData();
  const insets = useSafeAreaInsets();
  const [busy, setBusy] = useState(false);
  useKritikDil(); // dil değişince yeniden çiz (abonelik bozulursa yedek dilde kalır)

  const running = (snapshot.coils ?? []).filter((c) => c?.running).length;
  const active = snapshot.activeTreatment?.isActive === true;

  // ⚠️ HASTA GÜVENLİĞİ — [ekranB-2, 2026-09-04 responsive denetimi]
  // STM seri bağlantısı koptuğunda `LiveDataContext.normalizeStmCoils` 1-5 numaralı bobinleri
  // `running:false` yapar. Bu "bobin DURDU" değil, "durum BİLİNMİYOR" demektir — üstelik WiFi
  // bobinleri (6-8) o sırada gerçekten sürülüyor olabilir. Eski kod belirsizliği "hiçbir şey
  // çalışmıyor" sayıp acil durdurma düğmesini TAM DA operatörün en çok ihtiyaç duyduğu anda
  // gizliyordu. KURAL: bir kez "çalışıyor" gördüysek, STM yeniden çevrimiçi olup "durdu" diyene
  // kadar düğme EKRANDA KALIR. Hiç çalışmamışsa (donanımsız/demo makine) gürültü yapmaz.
  // D1.E03: kural TEK kaynakta (`useStmBelirsiz`) — kabuk söküm kapısı (`useTeardownGuard`) aynı ölçütü kullanır.
  const belirsiz = useStmBelirsiz(snapshot);

  // ⚠️ D1.E04 · İG-6.7: TEYİTSİZ acil durdurmadan sonra düğme EKRANDA KALIR. Backend teyitten bağımsız `running:false`
  // yayınlar (canlı durumu sıfırlar) — bu "durdu" kanıtı DEĞİLDİR; eskiden düğme tam burada kalkıyordu (ölçüldü). Teyit:
  // backend `estop_teyit` (E-stop teyidi ya da kartın tüm-sıfır ACK'i). Yerel bayrak: bu düğmenin teyitsiz basışı (backend
  // iletisi gelmezse de); teyitli basış ya da backend teyidiyle kalkar.
  const [yerelTeyitsiz, setYerelTeyitsiz] = useState(false);
  const backendTeyitli = snapshot.estopTeyit?.teyitli === true;
  useEffect(() => {
    if (backendTeyitli) setYerelTeyitsiz(false);
  }, [backendTeyitli, snapshot.estopTeyit?.zaman]);
  const teyitsiz = snapshot.estopTeyit?.teyitli === false || yerelTeyitsiz;

  if (gizle) return null;
  if (!running && !active && !belirsiz && !teyitsiz) return null;

  const onPress = async () => {
    // Çift-tık koruması YOK (bilinçli): panik anındaki ikinci dokunuş yutulmamalı. `busy` yalnız
    // görsel geri bildirim içindir, dokunuşu engellemez.
    setBusy(true);
    emitToast(kritikMetin("guvenlik.acilDurdur.gonderiliyor"), "info");
    const { confirmed, kartReddetti } = await performEmergencyStop();
    setBusy(false);
    setYerelTeyitsiz(!confirmed);
    if (confirmed) emitToast(kritikMetin("guvenlik.acilDurdur.durduruldu"), "success");
    else {
      // TD3: kart STOP'u reddettiyse eylem: gücü kes / USB'yi çıkar.
      if (kartReddetti)
        platformAlert(kritikMetin("guvenlik.acilDurdur.kartRedBaslik"), kritikMetin("guvenlik.acilDurdur.kartRedGovde"));
      else platformAlert(kritikMetin("guvenlik.acilDurdur.teyitsizBaslik"), kritikMetin("guvenlik.acilDurdur.teyitsizGovde"));
    }
  };

  // D1.E05: web'de body düzeyine portal + en üst katman (her açık Modal'ın üstünde); native'de yerinde.
  return (
    <UstKatman>
      <View
        style={[
          styles.wrap,
          compact && styles.wrapCompact,
          Platform.OS === "web" && webUstKatman,
          {
            bottom: bottomOffset + insets.bottom + spacing.md,
            left: Math.max(spacing.md, insets.left),
            right: Math.max(spacing.md, insets.right),
          },
        ]}
        pointerEvents="box-none"
      >
        <Pressable
          onPress={onPress}
          style={[styles.btn, compact && styles.btnCompact]}
          accessibilityRole="button"
          accessibilityLabel={kritikMetin("guvenlik.acilDurdur.erisimEtiketi")}
          accessibilityHint={kritikMetin("guvenlik.acilDurdur.erisimIpucu")}
        >
          <Text style={styles.text} numberOfLines={1} adjustsFontSizeToFit>
            {busy
              ? kritikMetin("guvenlik.acilDurdur.durduruluyor")
              : teyitsiz
                ? kritikMetin("guvenlik.acilDurdur.dugmeTeyitsiz")
                : belirsiz
                  ? kritikMetin("guvenlik.acilDurdur.dugmeBaglantiYok")
                  : running > 0
                    ? kritikMetin("guvenlik.acilDurdur.dugmeBobin", { count: running })
                    : kritikMetin("guvenlik.acilDurdur.dugme")}
          </Text>
        </Pressable>
      </View>
    </UstKatman>
  );
}

const styles = StyleSheet.create({
  wrap: {
    position: "absolute",
    // left/right inline verilir (yatay çentik güvenli alanı) — bkz. render.
    alignItems: "center",
    zIndex: 10000,
  },
  wrapCompact: { alignItems: "flex-end" },
  btn: {
    backgroundColor: colors.danger,
    borderRadius: radius.md,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.xl,
    // ⚠️ HASTA GÜVENLİĞİ: taban ölçekle küçülmez — rs(52) 320 px'te 44'ün ALTINA (41) iniyordu.
    minHeight: Math.max(touch.min, rs(52)),
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
  // Kısa ekranda dar ama TAM metinli (adjustsFontSizeToFit sığdırır); asla gizlenmez.
  btnCompact: { maxWidth: rs(260), paddingHorizontal: spacing.md },
  text: { color: "#fff", fontWeight: "800", fontSize: rf(15), letterSpacing: 0.4 },
});
