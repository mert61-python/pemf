// Author: mertaygn, cglrgrkn
/**
 * SessionProgressCard — Aktif seans ilerleme kartı.
 *
 * Python unified_control_window'daki seans timer göstergesinin React karşılığı.
 */
import { StyleSheet, Text, View, TouchableOpacity, Animated as RNAnimated, Easing as RNEasing } from "react-native";
import { useEffect as useEff, useRef as useR } from "react";
import { colors, spacing, typography, rf, rs } from "@/theme/tokens";
import { canliYogunluk, YOGUNLUK_ETIKETI_BUYUK } from "@/utils/yogunlukGosterimi";
import { modEtiketi } from "@/utils/seansDegerEtiketi";
import { useTranslation } from "react-i18next";
import { kritikMetin, useKritikDil } from "@/i18n/kritik";

interface Props {
  isActive: boolean;
  mode: string;
  elapsedSec: number;
  remainingSec: number;
  durationSec: number;
  frequencyHz: number;
  /** REÇETE yoğunluğu (operatörün yazdığı; cihaza gönderilmez). */
  intensityMt: number;
  /**
   * ÖLÇÜLEN yoğunluk — STM sensöründen gelen SEANS TEPE |B| (mT).
   * ⚠️ null/undefined = ölçüm YOK (0 DEĞİL) → kart reçete değerine düşer ve etiket "(kayıt)" olur.
   */
  measuredIntensityMt?: number | null;
  /**
   * SEANS BOYU en büyük ölçülen |B| (mT). `measuredIntensityMt` ANLIK (son saniyenin
   * tepesi) iken bu asla düşmez ve kayda/PDF'e giren sayıdır.
   * ⚠️ null/undefined = ölçüm YOK → tepe rozeti HİÇ çizilmez (0 gösterilmez).
   */
  measuredPeakMt?: number | null;
  /** D1.89: AI Pro'nun bobin 1 plan duty'si (%) — mT DEĞİL; reçete ve ölçüm yokken "DUTY" etiketiyle gösterilir. */
  dutyTemsilYuzde?: number | null;
  /** ODD K-11: AI Pro ODAK seansında seçilen doz (mT) ve planın sürdüğü bobin sayısı — "DUTY (AI planı, bobin 1)" yerine. */
  odakDozMt?: number | null;
  odakBobinSayisi?: number | null;
  onStop: () => void;
  onEmergencyStop: () => void;
  loading?: boolean;
  /** Acil durdurma komutu uçuşta mı (buton metnini değiştirir; buton DEVRE DIŞI KALMAZ). */
  stopping?: boolean;
  /** Bağlantı bayat/çevrimdışı: gösterilen süre/değerler GERÇEK ZAMANLI DOĞRULANAMIYOR → görsel işaretle. */
  stale?: boolean;
}

/**
 * [S6 adım 4 / ekranB-8] HER ZAMAN 'mm:ss' — saatli dal KALDIRILDI.
 * Klinik seans kapağı 120 dk olduğu için en fazla 6 karakter çıkar ("120:00"). Saatli biçim
 * ("1:05:30") 320 px'te NORMAL yazı ölçeğinde bile taşıyordu; sistem ölçeği 1,3'te kart genişliğini
 * aşıp kırpılıyordu — hekimin KALAN süreyi okuyamaması hasta güvenliği açısından kabul edilemez.
 */
/**
 * KRİTİK SAYISAL ALAN sözleşmesi: tek satır, sığmıyorsa KÜÇÜLTÜLEREK sığdırılır, sistem yazı
 * ölçeği burada 1,1 ile daha sıkı tavanlanır. Süre asla kırpılmaz/sarılmaz.
 */
const SURE_METNI = {
  numberOfLines: 1,
  adjustsFontSizeToFit: true,
  minimumFontScale: 0.6,
  maxFontSizeMultiplier: 1.1,
} as const;

function formatTime(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export function SessionProgressCard({
  isActive,
  mode,
  elapsedSec,
  remainingSec,
  durationSec,
  frequencyHz,
  intensityMt,
  measuredIntensityMt = null,
  measuredPeakMt = null,
  dutyTemsilYuzde = null,
  odakDozMt = null,
  odakBobinSayisi = null,
  onStop,
  onEmergencyStop,
  loading = false,
  stopping = false,
  stale = false,
}: Props) {
  const { t } = useTranslation();
  useKritikDil(); // ACİL DURDUR yazıları (kritikMetin) dil değişince yeniden çizilir
  const progress = durationSec > 0 ? Math.min(1, elapsedSec / durationSec) : 0;
  const indefinite = durationSec <= 0; // #72: süresiz seans → 00:00/%0 yerine "Süresiz"
  const pulseAnim = useR(new RNAnimated.Value(1)).current;
  const yogunluk = canliYogunluk({ intensityMt, measuredIntensityMt, dutyTemsilYuzde, odakDozMt, odakBobinSayisi });

  useEff(() => {
    // Bayat veride nabız animasyonunu DURDUR: "canlı çalışıyor" izlenimi verme.
    if (!isActive || stale) {
      pulseAnim.setValue(1);
      return;
    }
    const loop = RNAnimated.loop(
      RNAnimated.sequence([
        RNAnimated.timing(pulseAnim, { toValue: 1.08, duration: 1000, easing: RNEasing.ease, useNativeDriver: true }),
        RNAnimated.timing(pulseAnim, { toValue: 1.0, duration: 1000, easing: RNEasing.ease, useNativeDriver: true }),
      ])
    );
    loop.start();
    return () => loop.stop();
  }, [isActive, stale]);

  if (!isActive) {
    return (
      <View style={styles.idleCard}>
        <Text style={styles.idleIcon}>⚡</Text>
        <Text style={styles.idleTitle}>{t("seans.kart.bekleniyor")}</Text>
        <Text style={styles.idleSubtitle}>{t("seans.kart.bekleniyorAlt")}</Text>
      </View>
    );
  }

  return (
    <RNAnimated.View style={[styles.card, { transform: [{ scale: pulseAnim }] }]}>
      {/* Header */}
      <View style={styles.header}>
        <View style={[styles.activeBadge, stale && styles.staleBadge]}>
          <View style={[styles.pulseDot, stale && styles.staleDot]} />
          <Text style={[styles.activeBadgeText, stale && styles.staleBadgeText]}>
            {stale ? t("seans.kart.veriDogrulanmadi") : t("seans.kart.aktifSeans")}
          </Text>
        </View>
        <Text style={styles.modeText}>{modEtiketi(t, mode)}</Text>
      </View>

      {stale && (
        <Text style={styles.staleNote}
          accessibilityRole="alert" accessibilityLiveRegion="polite">
          {t("seans.kart.bayatBaglanti")}
        </Text>
      )}

      {/* Progress bar */}
      <View style={styles.progressBg}>
        <View style={[styles.progressFill, { width: `${Math.round(progress * 100)}%` as any }]} />
      </View>

      {/* Times */}
      <View style={styles.timeRow}>
        <View style={styles.timeBlock}>
          <Text style={styles.timeLabel}>{t("seans.kart.gecen")}</Text>
          <Text style={styles.timeValue} {...SURE_METNI}>{formatTime(elapsedSec)}</Text>
        </View>
        <View style={styles.timeBlockCenter}>
          <Text style={styles.progressPct}>{indefinite ? "∞" : t("ai.ortak.yuzde", { deger: Math.round(progress * 100) })}</Text>
        </View>
        <View style={[styles.timeBlock, { alignItems: "flex-end" }]}>
          <Text style={styles.timeLabel}>{t("seans.kart.kalan")}</Text>
          <Text
            style={[styles.timeValue, { color: indefinite ? colors.textMuted : remainingSec < 60 ? "#ef4444" : colors.primary }]}
            {...SURE_METNI}
          >
            {indefinite ? t("seans.kart.suresiz") : formatTime(remainingSec)}
          </Text>
        </View>
      </View>

      {/* Params */}
      <View style={styles.paramRow}>
        <ParamChip label={t("seans.kart.frekans")} value={`${frequencyHz} Hz`} />
        {/* ⚠️ İKİ FARKLI YOĞUNLUK — ETİKET HANGİSİ OLDUĞUNU SÖYLER.
            M3 (denetim 2026-09-03): reçete mT'si CIHAZA GÖNDERİLMEZ (STM/ESP paketi mT
            taşımaz), yalnız kayda yazılır; FREKANS ile yan yana eşit gösterilince operatör
            uygulanan doz sanıyordu → "(kayıt)" etiketi o beklentiyi düzeltir.
            2026-09-11 (sahip): STM'e MLX90393 bağlandı → GERÇEK ölçüm varken onu göster ve
            etiketi "(ölçülen)" yap. ⚠️ Ölçüm yokken 0 GÖSTERİLMEZ: reçeteye düşülür ve
            etiket yine "(kayıt)" olur — "0 mT ölçtük" demek, ölçmediğimizi ölçtük demektir.
            D1.89: kural TEK KAYNAKTA (`canliYogunluk`): reçete yoksa "—" (eskiden "0 mT"); AI Pro'nun bobin 1 duty'si
            "DUTY … %x" (eskiden "YOĞUNLUK (kayıt) 37 mT"). */}
        <ParamChip label={YOGUNLUK_ETIKETI_BUYUK[yogunluk.tur]} value={yogunluk.deger} />
        {/* SEANS TEPESİ — ayrı rozet, ayrı soru.
            "Şu an ne veriyoruz" (ölçülen, saniyelik) ile "bu seansta en fazla ne verdik"
            (tepe) farklı sayılardır: anlık değer darbe fazına ve ayar değişimine göre
            oynar, tepe ise asla düşmez. Tek rozette birleştirmek operatörü yanıltırdı —
            frekansı değiştirince düşmeyen bir "ölçüm" görürdü.
            ⚠️ Ölçüm yokken ÇİZİLMEZ: 0 göstermek "0 mT ölçtük" demektir. */}
        {measuredPeakMt != null && (
          <ParamChip label={t("seans.kart.tepe")} value={`${measuredPeakMt.toFixed(2)} mT`} />
        )}
      </View>

      {/* Buttons */}
      <View style={styles.btnRow}>
        {/* ⚠️ D1.82 · Y47 (sahip): durdurma düğmesi istek sürerken KİLİTLENMEZ. Eskiden `disabled={loading}` idi:
            başlatma ya da durdurma isteği askıdayken (≤ 8 sn) ikinci basış yutuluyordu. `loading` yalnız etikettir;
            ikinci basış yeni bir `/session/stop` gönderir (idempotent). */}
        <TouchableOpacity style={[styles.btnStop, loading && styles.btnBusy]} onPress={onStop}
          accessibilityRole="button" accessibilityState={{ busy: loading }}
          accessibilityLabel={t("seans.kart.durdurEtiketi")}>
          <Text style={styles.btnStopText} numberOfLines={1} adjustsFontSizeToFit>
            {loading ? t("kontrol.ekran.durduruluyor") : t("kontrol.panel.durdur")}
          </Text>
        </TouchableOpacity>
        {/* ACİL DURDUR asla disabled DEĞİL (panik anında dokunuş yutulmamalı); yalnız durum yazısı değişir. */}
        <TouchableOpacity style={styles.btnEmergency} onPress={onEmergencyStop}
          accessibilityRole="button" accessibilityState={{ busy: stopping }}
          accessibilityLabel={kritikMetin("guvenlik.acilDurdur.seansKartiEtiketi")}>
          {/* Y222 (sahip): dar ekranda yazı KESİLMEZ ve KISALTILMAZ — satır sınırı yok, sığmazsa iki satıra iner. Eskiden
              `numberOfLines={1} adjustsFontSizeToFit` idi: react-native-web sığdırmayı uygulamaz → 360 px'te "🚨 EMERGEN…". */}
          <Text style={styles.btnEmergencyText}>
            {stopping ? kritikMetin("guvenlik.acilDurdur.durduruluyor") : kritikMetin("guvenlik.acilDurdur.dugme")}
          </Text>
        </TouchableOpacity>
      </View>
    </RNAnimated.View>
  );
}

function ParamChip({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.paramChip}>
      <Text style={styles.paramLabel}>{label}</Text>
      <Text style={styles.paramValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  idleCard: {
    backgroundColor: "#1e293b",
    borderRadius: 16,
    padding: spacing.xl,
    alignItems: "center",
    borderWidth: 1,
    borderStyle: "dashed",
    borderColor: "#334155",
  },
  idleIcon: { fontSize: rf(36), marginBottom: spacing.sm },
  idleTitle: { color: colors.text, fontWeight: "700", fontSize: typography.subtitle },
  idleSubtitle: { color: colors.textMuted, fontSize: typography.small, marginTop: spacing.xs, textAlign: "center" },

  card: {
    backgroundColor: "#0f1729",
    borderRadius: 16,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: "#22c55e44",
    shadowColor: "#22c55e",
    shadowOpacity: 0.15,
    shadowRadius: 12,
    gap: spacing.md,
  },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  activeBadge: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.xs,
    backgroundColor: "#22c55e22",
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
    borderRadius: 20,
  },
  pulseDot: {
    width: rs(8),
    height: rs(8),
    borderRadius: 4,
    backgroundColor: "#22c55e",
  },
  activeBadgeText: { color: "#22c55e", fontWeight: "700", fontSize: typography.small },
  modeText: { color: colors.textMuted, fontSize: typography.small },
  staleBadge: { backgroundColor: "#f59e0b22" },
  staleDot: { backgroundColor: "#f59e0b" },
  staleBadgeText: { color: "#f59e0b" },
  staleNote: {
    color: "#f59e0b",
    fontSize: typography.small,
    fontWeight: "600",
    backgroundColor: "#f59e0b18",
    borderRadius: 8,
    padding: spacing.sm,
  },

  progressBg: {
    height: rs(8),
    backgroundColor: "#1e293b",
    borderRadius: 4,
    overflow: "hidden",
  },
  progressFill: {
    height: "100%",
    backgroundColor: "#22c55e",
    borderRadius: 4,
  },

  timeRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  timeBlock: { flex: 1 },
  timeBlockCenter: { flex: 1, alignItems: "center" },
  // [S6/S7-10] 10 px etiket 320 px'te 9 px'e düşüyordu; taban typography.small (11).
  timeLabel: { color: colors.textMuted, fontSize: typography.small, fontWeight: "700", letterSpacing: 1 },
  timeValue: { color: colors.text, fontSize: typography.title, fontWeight: "800", fontVariant: ["tabular-nums"] as any },
  progressPct: { color: "#22c55e", fontSize: typography.subtitle, fontWeight: "700" },

  paramRow: { flexDirection: "row", gap: spacing.sm },
  paramChip: {
    flex: 1,
    backgroundColor: "#1e293b",
    borderRadius: 8,
    padding: spacing.sm,
    alignItems: "center",
  },
  paramLabel: { color: colors.textMuted, fontSize: typography.small, fontWeight: "700", letterSpacing: 1 },
  paramValue: { color: colors.primary, fontSize: typography.body, fontWeight: "700" },

  btnRow: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.xs },
  btnStop: {
    flex: 1,
    backgroundColor: "#1e293b",
    borderRadius: 10,
    padding: spacing.md,
    alignItems: "center",
    borderWidth: 1,
    borderColor: "#475569",
  },
  btnStopText: { color: colors.text, fontWeight: "700" },
  btnBusy: { opacity: 0.55 },
  btnEmergency: {
    flex: 1,
    backgroundColor: "#ef4444",
    borderRadius: 10,
    padding: spacing.md,
    alignItems: "center",
  },
  btnEmergencyText: { color: "#fff", fontWeight: "800", textAlign: "center" },
});
