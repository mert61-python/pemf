// Author: mertaygn, cglrgrkn
import { StyleSheet, Text, View, TouchableOpacity } from "react-native";
import { Clock, HeartPulse, RadioTower, Wifi } from "lucide-react-native";
import { CoilCard } from "@/components/domain/CoilCard";
import { KabinSensoruKarti } from "@/components/domain/KabinSensoruKarti";
import { bobinKartiVerisi } from "@/utils/kabinSensoru";
import { Card } from "@/components/ui/Card";
import { MetricCard } from "@/components/ui/MetricCard";
import { ResponsiveGrid } from "@/components/ui/ResponsiveGrid";
import { StatusPill } from "@/components/ui/StatusPill";
import { NotificationCenter } from "@/components/ui/NotificationCenter";
import { SystemInfoPanel } from "@/components/domain/SystemInfoPanel";
import { GatewayStatusPanel } from "@/components/domain/GatewayStatusPanel";
import { colors, spacing, typography, rf, rs, layoutMax, radius } from "@/theme/tokens";
import { useLiveData } from "@/context/LiveDataContext";
import { useSessionControl } from "@/hooks/useSessionControl";
import { espEtkinMi, gorunurBobinler } from "@/services/bobinGorunurlugu";
import { canliYogunluk, YOGUNLUK_ETIKETI } from "@/utils/yogunlukGosterimi";
import { modEtiketi } from "@/utils/seansDegerEtiketi";
import { KendiDurdurmaIsareti } from "@/components/ui/KendiDurdurmaKontrolu";
import { donanimRozetDurumu } from "@/components/domain/StmUyumBandi";
import { useTranslation } from "react-i18next";
import { kritikMetin, useKritikDil } from "@/i18n/kritik";
import { useUserMode } from "@/context/UserModeContext";
import { profilSozlugu } from "@/utils/profilSozlugu";

export function DashboardScreen() {
  const { t } = useTranslation();
  useKritikDil(); // ACİL DURDUR yazıları (kritikMetin) dil değişince yeniden çizilir
  const { snapshot, wsConnected } = useLiveData();
  const { userMode } = useUserMode();
  const arastirmaProfili = userMode === "researcher"; // ODD K-2: «Hasta Özeti» → araştırmada «Örnek Özeti»
  const { emergencyStop } = useSessionControl();

  // CRASH-GUARD: `snapshot` bir WS `snapshot` mesajı ya da HTTP fallback ile TÜMÜYLE değiştirilir
  // (merge değil). Gövde `activeTreatment` içermezse `at.isActive` TypeError atıyor, ErrorBoundary
  // devreye girip Ana Ekran'ı hata kartına çeviriyordu — ve ACİL DURDUR butonu o ekranda olduğu için
  // donanım çalışırken durdurma kontrolü EKRANDAN KAYBOLUYORDU. Aynı dosyanın `coils` erişimi zaten
  // `?? []` kullanıyordu; asimetri kapatıldı.
  const at = snapshot.activeTreatment ?? { isActive: false, mode: "", frequencyHz: 0, intensityMt: 0, remainingMin: 0, elapsedSec: 0, durationSec: 0 };
  // ⚠️ İŞ 5 BURADA DA KAÇMIŞTI (sahip: "7 bobinli sistem"). Ana Ekran hem slot 8 kartını
  // ÇİZİYOR hem de "/8" yazıyordu: ESP sökülü olduğu için var olmayan bir bobin varmış gibi
  // sunuluyor, üstelik payda hiçbir zaman dolmadığı için sistem daima eksik görünüyordu.
  // Kural TEK KAYNAKTA: `gorunurBobinler` (STM 1-7 daima + ESP slotu YALNIZ ortaya çıkınca).
  const coils = gorunurBobinler(snapshot.coils ?? []);
  const yogunluk = canliYogunluk(at);
  const connectedCount = coils.filter((c) => c.connected).length;
  // Payda SABİT DEĞİL: ESP geri takılırsa slot 8 görünür olur ve payda kendiliğinden 8 olur.
  const coilTotal = coils.length;
  const runningCount = coils.filter((c) => c.running).length;
  // GÜVENLİK: E-stop + "çalışıyor" göstergesi seans-bayrağından BAĞIMSIZ olmalı. AI Pro
  // (/ai/pro/start, kimliksiz uzaktan başlatılabilir) / fiziksel / başka-istemci bobinleri
  // enerjiler ama session_* yayınlamaz → at.isActive false kalır. runningCount>0 iken E-stop
  // GİZLİ kalırsa operatör "Sistem Hazır" sanır, oysa donanım hastanın üzerinde çalışıyordur.
  const hardwareRunning = at.isActive || runningCount > 0;

  return (
    <View style={styles.container}>
  {/* [S4 adım 3] İç dikey ScrollView KALDIRILDI: kabuk (AppShell) zaten tek kaydırıcı ve
  keyboardShouldPersistTaps='handled' taşıyor. İç ScrollView'ın yükseklik sınırı
  olmadığı için kendi kaydırmasını hiç üretmiyordu; ama klavye açıkken dokunuşu
  yutup 'Kaydet/Bağlan' düğmelerini İKİ dokunuş gerektiriyordu. */}
      {/* Connection status row */}
      <View style={styles.statusRow}>
        <StatusPill label={t("ana.cihazAgi")} state={snapshot.gateway} />
        {/* ⚠️ "Sistem" (MQTT) rozeti YALNIZ ESP kuruluysa çizilir. ESP kartları söküldüğünde
            (sahip, 2026-09-11) broker çalışmaz ve rozet kalıcı sarı/kırmızı kalırdı — kurulu
            olmayan bir alt sistem için alarm, gerçek alarmları görünmez yapar. */}
        {/* Y230 (BE 3): tek kaynak backend'in ESP-etkin bilgisi — eskiden `mqtt !== devre_disi`ydi ve backend broker erişilebilir
            olunca ESP kapısız "online" yazdığı için rozet ESP kapalıyken YEŞİL yanıyordu (31.10 ölçüldü). */}
        {espEtkinMi(snapshot) && <StatusPill label="ESP / MQTT" state={snapshot.mqtt} />}
        {/* TD1: kart bağlı ama yazılımı uyumsuzsa "Donanım" YEŞİL OLMAZ (tezgâh: uyumsuz kartta yeşildi). */}
        <StatusPill label={t("ana.donanim")} state={donanimRozetDurumu(snapshot)} />
        {/* İNTERNET — NÖTR BİLGİ, ARIZA DEĞİL. Bu cihaz internetsiz tam çalışır; internet
            yalnız UZAKTAN ERİŞİM içindir. Kırmızı rozet yerine ne kaybedildiğini söyler. */}
        {snapshot.internet === "offline" && (
          <View style={styles.internetYok}>
            <Text style={styles.internetYokText}>{t("ana.internetYok")}</Text>
          </View>
        )}
        <View style={[styles.wsBadge, !wsConnected && styles.wsBadgeOff]}>
          <Wifi size={12} color={wsConnected ? "#22c55e" : "#f59e0b"} />
          <Text style={[styles.wsText, !wsConnected && styles.wsTextOff]}>
            {wsConnected ? t("ana.rozetCanli") : t("ana.rozetCevrimdisi")}
          </Text>
        </View>
      </View>

      {/* BE 2d (sahip 31.10): bağlantı yokken ikinci bant ("Canlı bağlantı yok …") KALDIRILDI — kabuğun bandı aynı şeyi söylüyor
          ve eylem veriyor (dokun → bağlanma seçenekleri). */}

      {/* Metrics */}
      <ResponsiveGrid>
        <MetricCard label={t("ana.aktifFrekans")} value={`${at.frequencyHz || 0} Hz`} tone={colors.primary} />
        {/* D1.89 · B-6.27: etiket HANGİ sayının gösterildiğini söyler (ölçülen / kayıt / AI Pro duty); yoksa "—". */}
        <MetricCard label={YOGUNLUK_ETIKETI[yogunluk.tur]} value={yogunluk.deger} tone={colors.warning} />
        <MetricCard label={t("ana.kalanSure")} value={t("ana.dakika", { dk: at.remainingMin || 0 })} tone={colors.success} />
        <MetricCard label={t("ana.bagliBobin")} value={`${connectedCount} / ${coilTotal}`} tone={colors.magenta} />
      </ResponsiveGrid>

      {/* Hero row */}
      <View style={styles.heroGrid}>
        {/* Patient card */}
        <Card style={styles.patientCard}>
          <View style={styles.cardHeader}>
            <HeartPulse color={colors.magenta} size={22} />
            <Text style={styles.cardTitle}>{profilSozlugu({ researcher: arastirmaProfili }).ozetBaslik}</Text>
          </View>
          {snapshot.patient?.name ? (
            <>
              <Text style={styles.patientName}>{snapshot.patient.name}</Text>
              <Text style={styles.body}>
                {snapshot.patient.species ?? ""} · {snapshot.patient.breed ?? ""}
              </Text>
              <Text style={styles.body}>{t("hasta.kart.sahip")}{snapshot.patient.owner ?? "—"}</Text>
            </>
          ) : (
            <Text style={styles.body}>{t("ana.aktifHastaYok")}</Text>
          )}
        </Card>

        {/* Active session card */}
        <Card style={styles.treatmentCard}>
          <View style={styles.cardHeader}>
            <Clock color={hardwareRunning ? colors.success : colors.textMuted} size={22} />
            <Text style={styles.cardTitle}>{t("ana.aktifSeans")}</Text>
            {hardwareRunning && (
              <View style={styles.activeDot} />
            )}
          </View>
          <Text style={styles.patientName}>
            {at.isActive
              ? (modEtiketi(t, at.mode) || t("ana.aktifSeans"))
              : hardwareRunning
                ? t("ana.donanimCalisiyor")
                : t("ana.sistemHazir")}
          </Text>
          {hardwareRunning ? (
            <>
              <Text style={styles.body}>
                {at.isActive
                  ? t("ana.calisanBobinKalan", { count: runningCount, kalan: at.remainingMin })
                  : t("ana.calisanBobinDisi", { count: runningCount })}
              </Text>
              {/* F-1 a11y: ekran-okuyucu için rol+etiket+ipucu (WCAG 4.1.2). Çift-tık koruması BİLEREK YOK —
                  acil-durdurma her dokunuşta anında ateşlenmeli (panik çift-dokunuş yutulmamalı). */}
              <TouchableOpacity
                style={styles.emergencyBtn}
                onPress={emergencyStop}
                accessibilityRole="button"
                accessibilityLabel={kritikMetin("guvenlik.acilDurdur.erisimEtiketi")}
                accessibilityHint={kritikMetin("guvenlik.acilDurdur.erisimIpucu")}
              >
                <Text style={styles.emergencyBtnText}>{kritikMetin("guvenlik.acilDurdur.dugme")}</Text>
              </TouchableOpacity>
              {/* D1.E02 · A-51: düğme ÇİZİLDİĞİ sürece kayan ACİL DURDUR gizlenir (aynı koşulun içinde). */}
              <KendiDurdurmaIsareti />
            </>
          ) : (
            <Text style={styles.body}>{t("ana.kontrolPanelinden")}</Text>
          )}
        </Card>
      </View>

      {/* Coil grid */}
      <View style={styles.sectionHeader}>
        <RadioTower color={colors.primary} size={20} />
        <Text style={styles.sectionTitle}>{t("ana.bobinDurumlari")}</Text>
        <Text style={styles.sectionBadge}>{t("ana.bagliSayisi", { bagli: connectedCount, toplam: coilTotal })}</Text>
      </View>
      {coils.length === 0 ? (
        <Text style={styles.coilEmptyText}>{t("ana.bobinVerisiBekleniyor")}</Text>
      ) : (
        <ResponsiveGrid minItemWidth={280}>
          {coils.map((coil) => (
            <CoilCard key={coil.id} coil={bobinKartiVerisi(coil)} />
          ))}
        </ResponsiveGrid>
      )}
      {/* Y306 (madde 6): MLX alanı bobin kartında değil — AYRI kabin sensörü kartı. */}
      <KabinSensoruKarti />

      {/* Bottom row: Notifications + System Info + Gateway */}
      <View style={styles.bottomGrid}>
        <View style={styles.bottomLeft}>
          {/* [S4 adım 3] 8 → 4: kompakt liste artık kaydırılmıyor, kart Dashboard'u uzatmasın.
              Tam listeye üst bardaki zil ikonundan ulaşılır. */}
          <NotificationCenter maxVisible={4} compact />
        </View>
        <View style={styles.bottomRight}>
          <SystemInfoPanel />
          <GatewayStatusPanel />
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  internetYok: {
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
    borderRadius: radius.full,
    backgroundColor: "rgba(148,163,184,0.08)",
    borderWidth: 1,
    borderColor: "rgba(148,163,184,0.28)",
    justifyContent: "center",
  },
  internetYokText: { color: "#94a3b8", fontSize: typography.caption, fontWeight: "600" },
  container: {
    padding: spacing.md,
    gap: spacing.md,
    // [S4 adım 3] Alt boşluk TEK yerde: AppShell içerik ScrollView'ı veriyor (mobil rs(160)+güvenli
    // alan / masaüstü rs(84)); ekranın kendi dolgusu üstüne binip ~200 px ölü alan bırakıyordu.
    width: "100%",
    maxWidth: layoutMax.genis,
    alignSelf: "center",
  },
  statusRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.sm,
    alignItems: "center",
  },
  wsBadge: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    backgroundColor: "#052e16",
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#16a34a",
  },
  wsBadgeOff: { backgroundColor: "#1c1917", borderColor: "#78350f" },
  wsText: { color: "#22c55e", fontSize: rf(11), fontWeight: "700" },
  wsTextOff: { color: "#f59e0b" },

  heroGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.lg },
  // [S2 adım 5 / ekranA-2] `minWidth` + `flex` birleşimi Yoga'da kartı kaptan TAŞIRIYORDU
  // (flexShrink varsayılanı 0). 768 px tablette kart-içi ACİL DURDUR düğmesinin sağ kenarı
  // kırpılıyordu. flexBasis sarma kararını verir, flexShrink kaba sığdırır.
  patientCard: { flexGrow: 1, flexShrink: 1, flexBasis: rs(280), minWidth: 0, gap: spacing.md },
  treatmentCard: { flexGrow: 1.4, flexShrink: 1, flexBasis: rs(280), minWidth: 0, gap: spacing.md },

  cardHeader: { alignItems: "center", flexDirection: "row", gap: spacing.sm },
  cardTitle: { color: colors.text, fontSize: typography.subtitle, fontWeight: "800", flex: 1 },
  activeDot: {
    width: rs(10), height: rs(10), borderRadius: 5, backgroundColor: "#22c55e",
    shadowColor: "#22c55e", shadowOpacity: 0.8, shadowRadius: 4,
  },
  patientName: { color: colors.text, fontSize: rf(22), fontWeight: "800" },
  body: { color: colors.textMuted, fontSize: typography.body },

  emergencyBtn: {
    backgroundColor: "#7f1d1d",
    borderRadius: 10,
    padding: spacing.md,
    alignItems: "center",
    marginTop: spacing.sm,
    borderWidth: 1,
    borderColor: "#ef4444",
  },
  emergencyBtnText: { color: "#fff", fontWeight: "800", fontSize: typography.small },

  sectionHeader: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.sm,
  },
  sectionTitle: { color: colors.text, fontSize: typography.subtitle, fontWeight: "800", flex: 1 },
  sectionBadge: {
    color: colors.textMuted,
    fontSize: typography.small,
    fontWeight: "600",
    backgroundColor: "#1e293b",
    paddingHorizontal: spacing.sm,
    paddingVertical: 3,
    borderRadius: 10,
  },

  bottomGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.md,
    marginTop: spacing.sm,
  },
  bottomLeft: { flex: 2, minWidth: rs(260) },
  bottomRight: { flex: 1, minWidth: rs(220), gap: spacing.md },
  coilEmptyText: { color: colors.textMuted, fontSize: typography.small, textAlign: "center", paddingVertical: spacing.lg },
});
