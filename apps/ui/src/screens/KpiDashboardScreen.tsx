// Author: mertaygn, cglrgrkn
/**
 * KpiDashboardScreen — Python kpi_dashboard_window.py'nin React karşılığı.
 * Gerçek veriye dayalı KPI kartları — API'den ve canlı sensör verisinden.
 */
import { useEffect, useState, useMemo } from "react";
import { Text, View, StyleSheet } from "react-native";
import { MetricCard } from "@/components/ui/MetricCard";
import { ResponsiveGrid } from "@/components/ui/ResponsiveGrid";
import { Card } from "@/components/ui/Card";
import { colors, spacing, typography, rf, rs, layoutMax } from "@/theme/tokens";
import { useLiveData } from "@/context/LiveDataContext";
import { apiGet } from "@/services/apiClient";
import { BarChart, PieChart } from "react-native-chart-kit";
import { barBolumSayisi } from "@/utils/kpiGrafik";
import { modEtiketi } from "@/utils/seansDegerEtiketi";
import { akimOlcumuAcik, alanGosterilebilir } from "@/utils/olculenAlan";
import { ANLIK_GUC_GORUNUR, bobinGucuW } from "@/utils/bobinGucu";
import { gorunurBobinler, STM_BOBIN_SAYISI, type GorunurlukGirdisi } from "@/services/bobinGorunurlugu";
import { useUserMode, type UserMode } from "@/context/UserModeContext";
import { profilSozlugu } from "@/utils/profilSozlugu";
import { useTranslation } from "react-i18next";

/** Etkin profil — sağlayıcı dışında (yalın ekran testi) `null`; yalnız başlık metni için (kancanın kendisi her çizimde çağrılır). */
function useEtkinProfil(): UserMode {
  try {
    return useUserMode().userMode;
  } catch {
    return null;
  }
}

/**
 * KPI paydası (“x / N”) — ekranın geri kalanıyla AYNI görünürlük kuralından türer.
 *
 * ⚠️ 2026-09-22 saha bulgusu: bu ekran tek başına `gorunurBobinler`i KULLANMIYORDU
 * (Dashboard/Control/SensorMonitor kullanıyor). Backend takılı olmayan ESP slotunu da
 * listelediği için Ana Ekran "7 / 7" derken burası "7 / 8" yazıyordu; liste boşken de
 * sabit `8`e düşülüyordu, oysa ESP söküldükten sonra fiziksel sayı 7.
 *
 * ⚠️ Payda SABİT 7 DEĞİLDİR: ESP slotu ortaya çıkarsa (bağlı **ya da** çalışıyor) yine
 * sayılır — sahip “ileride tekrar hibrit ESP+STM sistemine dönebilirim” dedi.
 * Kapı: `kpiBobinSayisi.test.tsx` (karşı-kanıt testleri 7'yi sabitlemeyi KIRAR).
 */
export function hesaplaBobinSayisi(ham: readonly GorunurlukGirdisi[]): number {
  return gorunurBobinler(ham).length || STM_BOBIN_SAYISI;
}

interface KpiSummary {
  totalSessions: number;
  completedSessions: number;
  stoppedSessions: number;
  avgDurationMin: number;
  modeDistribution: Record<string, number>;
  last7Days: { date: string; count: number }[];
}

export function KpiDashboardScreen() {
  const { t } = useTranslation();
  const { snapshot, sensorHistory, connectionQuality } = useLiveData();
  const instantStale = connectionQuality !== "live";
  // SG.G1: sayılar profilin seanslarıdır (backend `X-PEMF-Profil`) → başlık da profilin dilinde ("Klinik" araştırmada yok).
  const SK = profilSozlugu({ researcher: useEtkinProfil() === "researcher" });
  const [kpi, setKpi] = useState<KpiSummary>({
    totalSessions: 0,
    completedSessions: 0,
    stoppedSessions: 0,
    avgDurationMin: 0,
    modeDistribution: {},
    last7Days: [],
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    // KPI özetini auth'lu (X-API-Key) + timeout'lu apiGet ile çek — uzaktan (tünel,
    // PEMF_REQUIRE_AUTH=1) ham fetch 401 alıp bozuluyordu. apiGet hata/401'de null döner.
    apiGet<KpiSummary | null>("/kpi/summary", null, { silent: true }).then((data) => {
      if (!mounted) return;
      if (data && typeof data.totalSessions === "number") {
        // ŞEKİL DOĞRULAMASI: eskiden `setKpi(data)` state'i TÜMÜYLE sunucu gövdesiyle değiştiriyordu
        // (yedek dal `...prev` kullandığı hâlde). Sunucu `last7Days` veya `modeDistribution`
        // alanlarını göndermezse bunlar undefined kalıp `.map` / `Object.entries` çağrılarında
        // Raporlar ekranını çökertiyordu. Varsayılanlarla birleştir + dizi/nesne tipini doğrula.
        setKpi((prev) => ({
          ...prev,
          ...data,
          modeDistribution:
            data.modeDistribution && typeof data.modeDistribution === "object" ? data.modeDistribution : {},
          last7Days: Array.isArray(data.last7Days) ? data.last7Days : [],
        }));
        setLoading(false);
        return;
      }
      // Fallback: /history/statistics (alan adları farklı → hepsini dene)
      apiGet<any>("/history/statistics", null, { silent: true }).then((s) => {
        if (!mounted) return;
        if (s) {
          setKpi(prev => ({
            ...prev,
            totalSessions: s.total_sessions ?? 0,
            completedSessions: s.completed_sessions ?? 0,
            avgDurationMin: s.avg_duration_minutes ?? s.average_duration ?? 0,
          }));
        }
        setLoading(false);
      });
    });
    return () => { mounted = false; };
  }, []);

  // Kural TEK KAYNAKTA: `gorunurBobinler` (STM 1-7 daima + ESP slotu YALNIZ ortaya çıkınca).
  // Dashboard/Control/SensorMonitor ile aynı süzgeç — aksi hâlde aynı cihaz iki ekranda
  // farklı bobin sayısı gösterir (2026-09-22 bulgusu: "7 / 7" vs "7 / 8").
  const coils = gorunurBobinler(snapshot.coils ?? []);
  const connectedCoils = coils.filter((c) => c.connected);
  const runningCoils = coils.filter((c) => c.running);
  // Bkz. `hesaplaOrtSicaklik` (dosya sonunda) — ortalama, ÖLÇÜM YAPAN bobinler üzerinden alınır.
  const coilCount = hesaplaBobinSayisi(snapshot.coils ?? []);

  // CH4 · Y154: akım sensörü KAPALIYKEN (varsayılan) bobin tablosunda "A" sütunu hiç çizilmez.
  const akimOlcumu = akimOlcumuAcik(snapshot);
  // TD5 · A-64: "Anlık Güç" akım güvenilir olana dek GİZLİ (eski `COIL_R = 0.5` × sahte akım² → PSU kapalıyken 6,3 W).
  // Direnç tek kaynakta (`utils/bobinGucu`, 8,9 Ω); açılırsa yalnız güvenilir, ölçülmüş akım sayılır.
  const instantPowerW = runningCoils
    .filter((c) => !c.akimGuvenilmez && alanGosterilebilir(c, "currentA"))
    .reduce((sum, c) => sum + bobinGucuW(c.currentA), 0);
  const sicaklik = hesaplaOrtSicaklik(connectedCoils);
  // ⚠️ İNCELEME-2 i6-F-1 (D1.76 · B-1.24 · Y6): ortalama YALNIZ alanı ÖLÇÜLEN çalışan bobinlerden (`alanGosterilebilir`).
  // Ölçülmeyen bobinin 0.0'ı (ya da bayat değeri) ortalamaya girerse 7 bobin çalışırken yalnız bobin 6 ölçüyorsa (1,842 mT)
  // kart "0.26 mT" diyordu (ölçüldü — D1.76'nın E-alanında düzelttiği sayının aynısı); hiçbiri ölçmezken "0.00 mT".
  const alanOlcenler = runningCoils.filter((c) => alanGosterilebilir(c, "magneticMt"));
  const avgMag = alanOlcenler.length > 0
    ? alanOlcenler.reduce((s, c) => s + c.magneticMt, 0) / alanOlcenler.length
    : null;

  const completionRate = kpi.totalSessions > 0
    ? Math.round((kpi.completedSessions / kpi.totalSessions) * 100)
    : null;

  const uptimePct = connectedCoils.length > 0
    ? Math.round((connectedCoils.length / coilCount) * 100)
    : 0;

  // Grafik genişliği kartın GERÇEK iç genişliğinden (onLayout) ölçülür → her telefon/
  // yoğunluk/yön ve tek/çift-kolon gridde kart sınırına TAM oturur. Sabit Dimensions
  // hesabı kartın kendi padding'ini kaçırıp grafiğin kutudan taşmasına yol açıyordu.
  const [chartW, setChartW] = useState(0);

  // F-3: grafik bölümünü useMemo'la → WS her tick'te ekran re-render OLSA da (anlık-durum kartları +
  // bobin tablosu canlı-veri ister) BarChart/PieChart yalnız kpi/genişlik değişince yeniden hesaplanıp
  // render olur (chart-kit render'ı pahalı). Aynı girdi → aynı element referansı = davranış-nötr.
  const chartsSection = useMemo(() => {
    /**
     * ⚠️ SAHİP BİLDİRİMİ (2026-09-12): "bu grafiği daha belirgin ve tasarım olarak daha
     * güzel hale getir."
     *
     * ÖLÇÜLEN KUSURLAR (ekran görüntüsünden):
     *  1) Y EKSENİ ONDALIKLI: "11.00 · 8.25 · 5.50 · 2.75". Seans sayısı TAM SAYIDIR;
     *     "8,25 seans" diye bir birim yok. (Asıl kusur bu — tasarım değil ANLAM hatası.)
     *     → `decimalPlaces: 0` + bölüt sayısı `barBolumSayisi()` ile tepe değeri TAM BÖLER.
     *  2) ÇUBUKLAR ÇOK İNCE (`barPercentage: 0.5`) ve koyu mor zemine yakın renkte →
     *     11 seanslık gün bile zar zor seçiliyor. → daha kalın + DOLGU GRADYANI + parlak renk.
     *  3) DEĞER OKUNAMIYOR: sayıyı görmek için göz eksene gidip geliyordu.
     *     → `showValuesOnTopOfBars` ile sayı çubuğun üstünde.
     *  4) SIFIR GÜNLER "yok" gibi duruyordu → `fromZero` ile taban ortak, kılcal çizgi kalır.
     */
    const chartConfig = {
      backgroundGradientFrom: "#1e293b",
      backgroundGradientTo: "#0f172a",
      color: (opacity = 1) => `rgba(167, 139, 250, ${opacity})`,
      labelColor: (opacity = 1) => `rgba(203, 213, 225, ${opacity})`,
      strokeWidth: 2,
      barPercentage: 0.78,
      barRadius: 5,
      // Dolgu gradyanı: çubuk üstte parlak, altta koyu → koyu zeminde net ayrışır.
      fillShadowGradient: "#a78bfa",
      fillShadowGradientTo: "#6d28d9",
      fillShadowGradientOpacity: 1,
      fillShadowGradientToOpacity: 1,
      // ⚠️ TAM SAYI EKSENİ: "8.25 seans" anlamsızdı.
      decimalPlaces: 0,
      propsForBackgroundLines: { strokeDasharray: "4 6", stroke: "#334155", strokeWidth: 1 },
      propsForLabels: { fontSize: rf(11), fontWeight: "600" },
      useShadowColorFromDataset: false
    };
    // Son 7 gün bar chart verisi
    const last7 = kpi.last7Days.slice().reverse();
    const barData = {
      labels: last7.length > 0
        ? last7.map(d => {
            // Güvenli MM-DD: backend string 'YYYY-MM-DD' bekleniyor ama sayı/epoch/ISO gelirse
            // ham .slice(5) ya yanlış etiket ya da (sayıda) TypeError → KPI beyaz ekran veriyordu.
            const raw: any = (d as any)?.date;
            if (typeof raw === "number") {
              const dt = new Date(raw < 1e12 ? raw * 1000 : raw);
              return `${String(dt.getMonth() + 1).padStart(2, "0")}-${String(dt.getDate()).padStart(2, "0")}`;
            }
            const s = String(raw ?? "");
            const m = s.match(/\d{4}-(\d{2}-\d{2})/);
            return m ? m[1] : (s.length >= 5 ? s.slice(5) : (s || "—"));
          })
        : ["—", "—", "—", "—", "—", "—", "—"],
      // ORTA fix: ham d.count null/NaN olursa chart-kit Math.max/ölçekleme NaN → bar grafik bozulur. Sanitize.
      datasets: [{ data: last7.length > 0 ? last7.map(d => Number(d.count) || 0) : [0, 0, 0, 0, 0, 0, 0] }]
    };
    // Mod dağılımı pie verisi
    const PIE_COLORS = ["#7c3aed", "#ec4899", "#0ea5e9", "#f59e0b", "#22c55e"];
    const modeEntries = Object.entries(kpi.modeDistribution);
    const pieData = modeEntries.length > 0
      ? modeEntries.map(([name, count], i) => ({
          name: modEtiketi(t, name), population: Number(count) || 0,
          color: PIE_COLORS[i % PIE_COLORS.length],
          legendFontColor: "#94a3b8", legendFontSize: rf(12)
        }))
      : [{ name: t("ana.kpi.veriYok"), population: 1, color: "#334155", legendFontColor: "#94a3b8", legendFontSize: rf(12) }];
    return (
      <ResponsiveGrid minItemWidth={300}>
        <Card style={styles.chartCard}>
          <View style={styles.chartHeader}>
            <Text style={styles.chartTitle}>{t("ana.kpi.sonYediGun")}</Text>
            {/* ⚠️ TOPLAM ROZETİ: hepsi sıfır olan bir grafik "veri mi yok, grafik mi bozuk?"
                sorusunu doğuruyordu. Rozet cevabı peşinen verir. */}
            <Text style={styles.chartToplam}>
              {t("ana.kpi.toplamRozet", { n: barData.datasets[0].data.reduce((a, b) => a + b, 0) })}
            </Text>
          </View>
          <View style={styles.chartInner} onLayout={(e) => setChartW(e.nativeEvent.layout.width)}>
            {chartW > 0 && (
              <BarChart
                data={barData}
                width={chartW}
                height={rs(260)}
                chartConfig={chartConfig}
                style={styles.chart}
                yAxisLabel=""
                yAxisSuffix=""
                // ⚠️ Bölüt sayısı tepe değeri TAM BÖLER → her etiket tam sayı (bkz. utils/kpiGrafik).
                segments={barBolumSayisi(barData.datasets[0].data)}
                fromZero
                showValuesOnTopOfBars
                withInnerLines
              />
            )}
          </View>
        </Card>
        <Card style={styles.chartCard}>
          <Text style={styles.chartTitle}>{t("ana.kpi.modDagilimi")}</Text>
          <View style={styles.chartInner} onLayout={(e) => setChartW(e.nativeEvent.layout.width)}>
            {chartW > 0 && (
              <>
                {/* [S7 adım 3 / ekranC-2] Lejant chart-kit'in SVG'si İÇİNDE, x = width/2.5 sabit
                    konumunda çiziliyordu: 300 px'lik kartta mod adları ("Yara İyileşmesi") pastanın
                    ÜZERİNE biniyor ve kırpılıyordu. Lejant artık RN View olarak grafiğin ALTINDA,
                    sarmalı bir satırda. */}
                <PieChart
                  data={pieData}
                  width={chartW}
                  height={rs(200)}
                  chartConfig={chartConfig}
                  accessor={"population"}
                  backgroundColor={"transparent"}
                  paddingLeft={String(Math.round(chartW / 4))}
                  center={[0, 0]}
                  hasLegend={false}
                />
                <View style={styles.pieLejant}>
                  {pieData.map((d) => (
                    <View key={d.name} style={styles.pieLejantOge}>
                      <View style={[styles.pieLejantNokta, { backgroundColor: d.color }]} />
                      <Text style={styles.pieLejantMetin} numberOfLines={1}>
                        {d.name} ({d.population})
                      </Text>
                    </View>
                  ))}
                </View>
              </>
            )}
          </View>
        </Card>
      </ResponsiveGrid>
    );
  }, [kpi.last7Days, kpi.modeDistribution, chartW, t]);

  return (
    <View style={styles.container}>
  {/* [S4 adım 3] İç dikey ScrollView KALDIRILDI: kabuk (AppShell) zaten tek kaydırıcı ve
  keyboardShouldPersistTaps='handled' taşıyor. İç ScrollView'ın yükseklik sınırı
  olmadığı için kendi kaydırmasını hiç üretmiyordu; ama klavye açıkken dokunuşu
  yutup 'Kaydet/Bağlan' düğmelerini İKİ dokunuş gerektiriyordu. */}
      <Text style={styles.sectionTitle}>{SK.kpiBaslik}</Text>
      <ResponsiveGrid>
        <MetricCard
          label={t("ayarlar.sistemBilgi.toplamSeans")}
          value={loading ? "…" : String(kpi.totalSessions)}
          tone={colors.primary}
        />
        <MetricCard
          label={t("ana.kpi.tamamlanmaOrani")}
          value={loading ? "…" : completionRate !== null ? `${completionRate}%` : "—"}
          tone={colors.success}
        />
        <MetricCard
          label={t("ana.kpi.ortSure")}
          value={loading ? "…" : t("ana.kpi.sureDk", { sure: Math.round(kpi.avgDurationMin) })}
          tone={colors.violet}
        />
        <MetricCard
          label={t("ana.kpi.durHata")}
          value={loading ? "…" : String(kpi.stoppedSessions)}
          tone={colors.magenta}
        />
      </ResponsiveGrid>

      <Text style={styles.sectionTitle}>{t("ana.kpi.anlikCihaz")}</Text>
      {instantStale && (
        <Text style={styles.staleBanner} accessibilityRole="alert" accessibilityLiveRegion="polite">
          {t("ana.kpi.bayatUyari")}
        </Text>
      )}
      <View style={instantStale ? { opacity: 0.55 } : undefined}>
        <ResponsiveGrid>
          {ANLIK_GUC_GORUNUR ? (
            <MetricCard label={t("ana.kpi.anlikGuc")} value={`${instantPowerW.toFixed(1)} W`} tone={colors.cyan} />
          ) : null}
          <MetricCard label={t("ana.bagliBobin")} value={`${connectedCoils.length} / ${coilCount}`} tone={colors.primary} />
          <MetricCard label={t("ana.kpi.calisanBobin")} value={`${runningCoils.length} / ${coilCount}`} tone={colors.success} />
          <MetricCard label={t("ana.kpi.cihazOrani")} value={`${uptimePct}%`} tone={colors.violet} />
          {/* ⚠️ DENETİM 2026-08-17: ortalama `connectedCoils.length`'e bölünüyordu ve STM bobinleri
              (1-5) sıcaklık ÖLÇMEDİĞİ için `objectTemp: 0` ile ortalamayı seyreltiyordu — 3 bobin
              50 °C iken kart 18,8 °C, yalnız-STM kabinde 0,0 °C ("serin" diye okunur) gösteriyordu.
              Bu, `CoilThermalHonesty.test.tsx` ile kilitli dürüstlük değişmezinin ihlaliydi:
              "ölçüm yokken SAHTE bir sıcaklık değeri gösterilmez". */}
          <MetricCard
            label={sicaklik.olcumVar ? t("ana.kpi.ortSicaklikBobin", { count: sicaklik.olcenSayisi }) : t("ana.kpi.ortSicaklik")}
            value={sicaklik.olcumVar ? `${sicaklik.deger.toFixed(1)} °C` : t("ana.kpi.olcumYok")}
            tone={colors.warning}
          />
          <MetricCard
            label={avgMag !== null ? t("ana.kpi.ortManyetikBobin", { count: alanOlcenler.length }) : t("ana.kpi.ortManyetik")}
            value={avgMag !== null ? `${avgMag.toFixed(2)} mT` : t("ana.kpi.olcumYok")}
            tone={colors.cyan}
          />
        </ResponsiveGrid>
      </View>

      <Text style={styles.sectionTitle}>{t("ana.kpi.performansGrafikleri")}</Text>
      {chartsSection}

      {/* Per-coil instant table */}
      {connectedCoils.length > 0 && (
        <>
          <Text style={styles.sectionTitle}>{t("ana.kpi.bobinDetaylari")}</Text>
          <Card style={styles.tableCard}>
            <View style={styles.tableHeader}>
              <Text style={[styles.tableCell, styles.tableHead]} numberOfLines={1} adjustsFontSizeToFit>{t("ai.pro.tablo.bobin")}</Text>
              <Text style={[styles.tableCell, styles.tableHead]} numberOfLines={1} adjustsFontSizeToFit>mT</Text>
              <Text style={[styles.tableCell, styles.tableHead]} numberOfLines={1} adjustsFontSizeToFit>°C</Text>
              {akimOlcumu ? (
                <Text style={[styles.tableCell, styles.tableHead]} numberOfLines={1} adjustsFontSizeToFit>A</Text>
              ) : null}
              {ANLIK_GUC_GORUNUR ? (
                <Text style={[styles.tableCell, styles.tableHead]} numberOfLines={1} adjustsFontSizeToFit>W</Text>
              ) : null}
              <Text style={[styles.tableCell, styles.tableHead]} numberOfLines={1} adjustsFontSizeToFit>Hz</Text>
            </View>
            {coils.map((c) => {
              const pts = sensorHistory[c.id] ?? [];
              const latest = pts[pts.length - 1];
              const mag = latest?.magneticMt ?? c.magneticMt;
              const temp = latest?.objectTemp ?? c.objectTemp;
              const cur = latest?.currentA ?? c.currentA;
              const power = bobinGucuW(cur);
              // D1.67 · Y6 (1-D inceleme i2-F-3): bayat / hiç ölçülmemiş alan sayı olarak gösterilmez ('—'); geçmişin SON
              // noktası da sensör sustuğundan beri bayattır — ölçüt bobinin GÜNCEL `measuredFields`'i.
              const magVar = alanGosterilebilir(c, "magneticMt");
              const tempVar = alanGosterilebilir(c, "objectTemp");
              const curVar = !c.akimGuvenilmez && alanGosterilebilir(c, "currentA");
              return (
                <View key={c.id} style={[styles.tableRow, !c.connected && styles.tableRowOff]}>
                  <Text style={styles.tableCell} numberOfLines={1} adjustsFontSizeToFit>{c.id}</Text>
                  <Text style={[styles.tableCell, { color: "#22c55e" }]} numberOfLines={1} adjustsFontSizeToFit>{magVar ? mag.toFixed(2) : "—"}</Text>
                  <Text style={[styles.tableCell, { color: tempVar && temp > 45 ? "#ef4444" : "#fb923c" }]} numberOfLines={1} adjustsFontSizeToFit>{tempVar ? temp.toFixed(1) : "—"}</Text>
                  {akimOlcumu ? (
                    <Text style={[styles.tableCell, { color: "#60a5fa" }]} numberOfLines={1} adjustsFontSizeToFit>{curVar ? cur.toFixed(3) : "—"}</Text>
                  ) : null}
                  {ANLIK_GUC_GORUNUR ? (
                    <Text style={[styles.tableCell, { color: "#a78bfa" }]} numberOfLines={1} adjustsFontSizeToFit>{curVar && cur > 0 ? power.toFixed(2) : "—"}</Text>
                  ) : null}
                  <Text style={styles.tableCell} numberOfLines={1} adjustsFontSizeToFit>{c.frequencyHz > 0 ? c.frequencyHz : "—"}</Text>
                </View>
              );
            })}
          </Card>
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  // [S4 adım 3] Alt boşluk TEK yerde: AppShell içerik ScrollView'ı rs(160)+güvenli alan (mobil) /
  // rs(84) (masaüstü) veriyor. Ekranın kendi paddingBottom'ı bunun ÜSTÜNE binip sayfa sonunda
  // ~200 px ölü alan bırakıyordu.
  container: { padding: spacing.md, gap: spacing.md, width: "100%", maxWidth: layoutMax.genis, alignSelf: "center" },
  sectionTitle: { color: colors.text, fontSize: typography.subtitle, fontWeight: "700", marginTop: spacing.md },
  staleBanner: {
    color: "#f59e0b",
    fontSize: typography.small,
    fontWeight: "600",
    backgroundColor: "#f59e0b18",
    borderRadius: 8,
    padding: spacing.sm,
    marginBottom: spacing.sm,
  },
  chartCard: { padding: spacing.sm, alignItems: 'center', overflow: "hidden" },
  chartInner: { width: "100%", alignItems: "center" },
  pieLejant: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, paddingHorizontal: spacing.sm, justifyContent: "center" },
  pieLejantOge: { flexDirection: "row", alignItems: "center", gap: spacing.xs, maxWidth: "100%" },
  pieLejantNokta: { width: rs(10), height: rs(10), borderRadius: rs(5) },
  pieLejantMetin: { color: colors.textMuted, fontSize: typography.small, flexShrink: 1 },
  chart: { marginVertical: spacing.sm, borderRadius: 8 },
  chartTitle: { color: colors.text, fontSize: typography.body, fontWeight: "800" },
  chartHeader: { width: "100%", flexDirection: "row", flexWrap: "wrap", alignItems: "center",
    justifyContent: "space-between", gap: spacing.xs, marginBottom: spacing.sm, paddingHorizontal: spacing.sm },
  chartToplam: { color: colors.primary, fontSize: typography.small, fontWeight: "800" },
  tableCard: { padding: 0, overflow: "hidden" },
  tableHeader: {
    flexDirection: "row",
    backgroundColor: "#0f172a",
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
  },
  tableRow: {
    flexDirection: "row",
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderTopWidth: 1,
    borderColor: "#1e293b",
  },
  tableRowOff: { opacity: 0.35 },
  tableHead: { color: colors.textMuted, fontWeight: "700", fontSize: rf(11) },
  tableCell: {
    flex: 1,
    minWidth: rs(34),
    color: colors.text,
    fontSize: rf(13),
    fontWeight: "600",
    fontVariant: ["tabular-nums"] as any,
  },
});

/**
 * "Ort. Sıcaklık" — ölçüm YAPAN bobinler üzerinden ortalama.
 *
 * ⚠️ DENETİM 2026-08-17. Ortalama `connectedCoils.length`'e bölünüyordu. Ama STM bobinlerinde
 * (1-5) SICAKLIK TELEMETRİSİ YOKTUR: seri protokol yalnız duty/phase/freq/duration döndürür ve
 * backend `objectTemp`i BİLEREK `0.0` bırakır (`api_server` notu: "0.0-yerine-NULL yolu BILEREK
 * secilmedi; asagi-akis (PDF/KPI/grafik) 0.0 bekliyor"). Ölçülen sonuç:
 *     5 STM (ölçüm yok) + 3 ESP @ 50 °C  →  kart 18,8 °C
 *     yalnız-STM kabin                    →  kart  0,0 °C  ("serin" diye okunur)
 * Üç bobin yanık eşiğine (48 °C) dayanmışken kart 18,8 °C diyordu.
 *
 * ⚠️ Bu, TESTLE KİLİTLİ bir dürüstlük değişmezinin ihlaliydi (2026-08-09 Tier-2 sahip kararı,
 * `CoilThermalHonesty.test.tsx`): "'ÖLÇÜLMÜYOR' İLE 'SERİN' AYIRT EDİLEBİLMELİ … ölçüm yokken
 * SAHTE bir sıcaklık değeri gösterilmez". Karar bu ekrana taşınmamıştı.
 *
 * ⚠️ `0` NÖBETÇİSİ: ölçümü olmayan bobin `0` gönderir, dolayısıyla "ölçüm var" ayrımı sıfır-olmayan
 * POZİTİF değerdir. Negatif değer fiziksel olarak anlamsızdır (sensör arızası) ve ölçüm sayılmaz.
 * Bu ayrımı ortadan kaldırmak `0 °C`yi yeniden "serin" gibi göstermek olurdu.
 *
 * ⚠️ OTOMATİK TERMAL KORUMA YOK (sahip kararı A-47 + Y2; L1-7.2 / i2-F-9): 48 °C üstü yalnız GÖRSEL uyarıdır
 * (`CoilParameterPanel` `SICAKLIK_UYARI_ESIGI_C` — istek gönderilmez, seans engellenmez / durdurulmaz). Burada düzeltilen
 * şey GÖSTERİMİN dürüstlüğüdür; operatör sıcaklığı bu göstergelerden izler.
 *
 * Kilit: `__tests__/kpiSicaklikDurustlugu.test.tsx`.
 */
export function hesaplaOrtSicaklik(
  bagliBobinler: { connected?: boolean; objectTemp?: number; measuredFields?: string[] }[],
): { olcumVar: boolean; deger: number; olcenSayisi: number } {
  // D1.67 · Y6 (1-D inceleme i2-F-3): `measuredFields` varsa ölçüt O'dur — susan sensörün DONMUŞ değeri (> 0) ölçüm değil.
  const olcenler = (bagliBobinler || []).filter(
    (c) =>
      c &&
      c.connected !== false &&
      alanGosterilebilir(c, "objectTemp") &&
      typeof c.objectTemp === "number" &&
      c.objectTemp > 0,
  );
  if (olcenler.length === 0) return { olcumVar: false, deger: 0, olcenSayisi: 0 };
  const toplam = olcenler.reduce((s, c) => s + (c.objectTemp as number), 0);
  return { olcumVar: true, deger: toplam / olcenler.length, olcenSayisi: olcenler.length };
}
