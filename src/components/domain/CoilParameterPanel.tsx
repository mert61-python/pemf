/**
 * CoilParameterPanel — Tekil bobin için parametre ayar paneli.
 *
 * Python unified_control_window'daki per-coil kontrol panelinin karşılığı.
 * Frekans, duty, faz, süre girişleri ve start/stop butonu içerir.
 */
import { StyleSheet, Text, View, TextInput, TouchableOpacity, AccessibilityInfo } from "react-native";
import { useState, useCallback, useEffect, useRef } from "react";
import { colors, spacing, typography, rf, rs } from "@/theme/tokens";
import { apiPost } from "@/services/apiClient";
import { clampTherapyParams } from "@/services/therapyLimits";

const COIL_COLORS = [
  "#FF5252", "#FF4081", "#E040FB", "#7C4DFF",
  "#536DFE", "#448AFF", "#40C4FF", "#18FFFF",
];

// Bobin yüzey sıcaklığı güvenlik kesme eşiği (°C) — üstünde otomatik durdurma (yanık riski).
const SAFE_TEMP_CUTOFF = 48;

interface Props {
  coilId: number;
  connected: boolean;
  running: boolean;
  objectTemp: number;
  frequencyHz: number;
  dutyCycle: number;
  magneticMt: number;
  currentA: number;
  defaultFreq?: number;
  defaultDuty?: number;
  defaultPhase?: number;
  defaultDuration?: number;
  disabled?: boolean;
  stm32Driven?: boolean;    // Bu bobin STM32 üzerinden mi çalışıyor?
  stmConnected?: boolean;   // STM32 USB bağlı mı?
}

export function CoilParameterPanel({
  coilId,
  connected,
  running,
  objectTemp,
  frequencyHz,
  dutyCycle,
  magneticMt,
  currentA,
  defaultFreq = 50,
  defaultDuty = 25,
  defaultPhase = 0,
  defaultDuration = 0,
  disabled = false,
  stm32Driven = false,
  stmConnected = false,
}: Props) {
  const [freq, setFreq] = useState(String(defaultFreq));
  const [duty, setDuty] = useState(String(defaultDuty));
  const [duration, setDuration] = useState(String(defaultDuration));
  const [phase, setPhase] = useState(String(defaultPhase));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const color = COIL_COLORS[(coilId - 1) % 8];

  const sendCommand = useCallback(async (start: boolean): Promise<boolean> => {
    setLoading(true);
    setError(null);
    try {
      // NaN-guard (|| DEĞİL): kullanıcı bilerek 0 yazarsa (bobini parkla) 0 KORUNSUN — eskiden
      // `parseFloat("0") || defaultFreq` 0'ı falsy sayıp default'a döndürüp bobini süründürüyordu.
      const pf = parseFloat(freq);   let f = Number.isNaN(pf) ? defaultFreq : pf;
      const pd = parseFloat(duty);   let d = Number.isNaN(pd) ? defaultDuty : pd;
      const pp = parseFloat(phase);  let ph = Number.isNaN(pp) ? defaultPhase : pp;
      // NaN-guard (|| DEĞİL): boş/geçersiz süre `parseInt(NaN)||0 = 0` ile SESSİZCE "süresiz"
      // oluyordu. Geçersizse default'a düş; ayrıca 0/süresiz'e çözülürse AÇIK uyar (aşağıda).
      const pDur = parseInt(duration, 10);
      let durMin = Number.isNaN(pDur) ? defaultDuration : pDur;
      if (start) {
        // Güvenlik: yalnızca BAŞLAT'ta sınır uygula (stop meşru biçimde 0 olabilir).
        const c = clampTherapyParams({ freq: f, duty: d, phase: ph, duration: durMin });
        f = c.values.freq; d = c.values.duty; ph = c.values.phase; durMin = c.values.duration;
        const warns = [...c.warnings];
        // Süre 0/süresiz: donanım watchdog'u DURATION_MAX'a kaplar (kontrolsüz kalmaz) ama operatör
        // süre girmediğini BİLMELİ — sessiz süresiz-seans olmasın.
        if (durMin <= 0) warns.push("Süre girilmedi — bobin donanım üst-sınırına kadar çalışır; süre belirtmeniz önerilir.");
        if (warns.length) setError(warns.join(" "));
      }
      // YÜKSEK fix: apiPost ağ-hatası/non-2xx'te THROW ETMEZ (fallback=null döner) → dönüşü DOĞRULA.
      // Eskiden yanıt kontrol edilmeden "başarılı" sayılıyordu → STOP sessizce düşse bile kullanıcı
      // bobinin durduğunu sanıyordu (bobin ÇALIŞMAYA DEVAM). null/status:error → açık uyarı ver.
      const res = await apiPost<{ status?: string } | null>(`/coil/${coilId}/control`, {
        freq: f,
        duty: d,
        phase: ph,
        duration: durMin * 60,
        start,
      }, null);
      const ok = !!res && res.status !== "error";
      if (!ok) {
        setError(start
          ? "Komut onaylanamadı — bobin başlatılamamış olabilir, tekrar deneyin."
          : "DURDURMA ONAYLANAMADI — bobin HÂLÂ ÇALIŞIYOR olabilir. ACİL DURDUR'a basın.");
      }
      return ok;
    } catch {
      setError("Komut gönderilemedi");
      return false;
    } finally {
      setLoading(false);
    }
  }, [coilId, freq, duty, phase, duration, defaultFreq, defaultDuty, defaultPhase, defaultDuration]);

  // Güvenlik interlock: aşırı ısınmada bobini otomatik durdur (yanık riski).
  // YÜKSEK fix: (1) sendCommand'i AWAIT et → yalnız TEYİTLİ başarıda "durduruldu" de (sessiz stop-hatasında
  // sahte güvence verme). (2) tek-atış ref → aşırı-ısınma sürerken her telemetri-tick'inde durdurma-spam etme.
  const overheatHandledRef = useRef(false);
  useEffect(() => {
    const overheating = running && objectTemp > SAFE_TEMP_CUTOFF;
    if (!overheating) {
      overheatHandledRef.current = false; // durum normale döndü → yeni episode için guard sıfırla
      return;
    }
    if (overheatHandledRef.current) return; // bu episode zaten ele alındı
    overheatHandledRef.current = true;
    const t = objectTemp;
    (async () => {
      const ok = await sendCommand(false);
      const msg = ok
        ? `Aşırı ısınma (${t.toFixed(1)}°C) — bobin otomatik durduruldu.`
        : `⚠️ AŞIRI ISINMA (${t.toFixed(1)}°C) — otomatik DURDURMA ONAYLANAMADI! ACİL DURDUR'a basın veya cihazı fiziksel güç düğmesinden kapatın.`;
      setError(msg);
      // A11y (#68): yanık-riski uyarısını ekran-okuyucuya AÇIKÇA duyur (live-region'a ek güvence).
      AccessibilityInfo.announceForAccessibility(msg);
    })();
  }, [running, objectTemp, sendCommand]);

  const isDisabled = disabled || !connected || (stm32Driven && !stmConnected);

  return (
    <View style={[styles.card, { borderColor: connected ? color + "44" : "#334155" }]}>
      {/* Header */}
      <View style={styles.header}>
        <View style={styles.headerLeft}>
          <View style={[styles.colorDot, { backgroundColor: connected ? color : "#475569" }]} />
          <Text style={styles.coilTitle}>Bobin {coilId}</Text>
          {stm32Driven ? (
            <View style={styles.sourceBadgeStm}><Text style={styles.sourceBadgeText}>STM32</Text></View>
          ) : (
            <View style={styles.sourceBadgeEsp}><Text style={styles.sourceBadgeText}>WiFi</Text></View>
          )}
        </View>
        <View style={styles.headerRight}>
          {objectTemp > 0 && (
            <View style={[styles.tempBadge, objectTemp > 45 && styles.tempWarning]}
              accessibilityLabel={`Sıcaklık ${objectTemp.toFixed(1)} derece${objectTemp > 45 ? ", yüksek" : ""}`}>
              {/* #121: >45°C uyarısı yalnız-RENK değil — ⚠ ikonu + metin (renk-körü operatör görsün). */}
              <Text style={styles.tempText}>{objectTemp > 45 ? "⚠ " : ""}{objectTemp.toFixed(1)}°C</Text>
            </View>
          )}
          {/* A11y (#67): durum YALNIZ-RENK değil — nokta + kısa metin (renk-körü operatör AKTİF ile
              HAZIR/durmuş bobini ayırt edebilsin; ekran-okuyucu için accessibilityLabel). */}
          <View style={styles.statusWrap}>
            <View
              style={[styles.statusDot, { backgroundColor: running ? "#22c55e" : connected ? "#f59e0b" : "#ef4444" }]}
              accessibilityElementsHidden
              importantForAccessibility="no"
            />
            <Text
              style={[styles.statusLabel, { color: running ? "#22c55e" : connected ? "#f59e0b" : "#ef4444" }]}
              accessibilityLabel={running ? "Durum: Aktif, bobin çalışıyor" : connected ? "Durum: Hazır, bobin durdu" : "Durum: Çevrimdışı"}
            >
              {running ? "Aktif" : connected ? "Hazır" : "Offline"}
            </Text>
          </View>
        </View>
      </View>

      {/* Live readings */}
      <View style={styles.readings}>
        <Reading label="mT" value={magneticMt.toFixed(2)} active={running} />
        <Reading label="A" value={currentA.toFixed(3)} active={running} />
        <Reading label="Hz" value={frequencyHz > 0 ? String(frequencyHz) : "-"} active={running} />
        <Reading label="DC%" value={dutyCycle > 0 ? String(dutyCycle) : "-"} active={running} />
      </View>

      {/* Parameter inputs */}
      <View style={styles.paramGrid}>
        <ParamInput
          label="Frekans (Hz)"
          value={freq}
          onChangeText={setFreq}
          disabled={isDisabled}
          keyboardType="numeric"
        />
        <ParamInput
          label="Duty (%)"
          value={duty}
          onChangeText={setDuty}
          disabled={isDisabled}
          keyboardType="numeric"
        />
        <ParamInput
          label="Faz (°)"
          value={phase}
          onChangeText={setPhase}
          disabled={isDisabled}
          keyboardType="numeric"
        />
        <ParamInput
          label="Süre (dk)"
          value={duration}
          onChangeText={setDuration}
          disabled={isDisabled}
          keyboardType="numeric"
        />
      </View>

      {/* A11y (#68): aşırı-ısınma/otomatik-kesme-başarısız gibi güvenlik uyarıları ekran-okuyucuya
          DUYURULSUN (yanık riski). accessibilityLiveRegion='assertive' + role='alert'. */}
      {error ? (
        <Text style={styles.errorText} accessibilityRole="alert" accessibilityLiveRegion="assertive">
          {error}
        </Text>
      ) : null}

      {/* Control buttons */}
      <View style={styles.btnRow}>
        <TouchableOpacity
          style={[styles.btnStart, isDisabled && styles.btnDisabled]}
          onPress={() => sendCommand(true)}
          disabled={isDisabled || loading}
          accessibilityRole="button"
          accessibilityLabel="Bobini başlat"
        >
          <Text style={styles.btnStartText}>▶ Başlat</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.btnStop, (!running || loading) && styles.btnDisabled]}
          onPress={() => sendCommand(false)}
          disabled={!running || loading}
          accessibilityRole="button"
          accessibilityLabel="Bobini durdur"
        >
          <Text style={styles.btnStopText}>⏹ Durdur</Text>
        </TouchableOpacity>
      </View>

      {!connected && (
        <View style={styles.offlineBanner}>
          <Text style={styles.offlineText}>⚡ Bobin bağlı değil</Text>
        </View>
      )}
    </View>
  );
}

function Reading({ label, value, active }: { label: string; value: string; active: boolean }) {
  return (
    <View style={styles.reading}>
      <Text style={[styles.readingValue, !active && { color: "#475569" }]}>{value}</Text>
      <Text style={styles.readingLabel}>{label}</Text>
    </View>
  );
}

function ParamInput({
  label,
  value,
  onChangeText,
  disabled,
  keyboardType,
}: {
  label: string;
  value: string;
  onChangeText: (v: string) => void;
  disabled: boolean;
  keyboardType: "numeric" | "default";
}) {
  return (
    <View style={styles.paramInputWrap}>
      <Text style={styles.paramLabel}>{label}</Text>
      <TextInput
        style={[styles.paramInput, disabled && styles.paramInputDisabled]}
        value={value}
        onChangeText={onChangeText}
        editable={!disabled}
        keyboardType={keyboardType}
        selectTextOnFocus
        accessibilityLabel={label}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: "#0f172a",
    borderRadius: 14,
    padding: spacing.md,
    borderWidth: 1,
    gap: spacing.sm,
  },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  headerLeft: { flexDirection: "row", alignItems: "center", gap: spacing.xs },
  headerRight: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  colorDot: { width: rs(10), height: rs(10), borderRadius: 5 },
  coilTitle: { color: colors.text, fontWeight: "700", fontSize: typography.body },
  statusDot: { width: rs(8), height: rs(8), borderRadius: 4 },
  statusWrap: { flexDirection: "row", alignItems: "center", gap: rs(4) },
  statusLabel: { fontSize: rf(10), fontWeight: "700", letterSpacing: 0.3 },
  tempBadge: {
    backgroundColor: "#1e293b",
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 6,
  },
  tempWarning: { backgroundColor: "#7f1d1d" },
  tempText: { color: colors.text, fontSize: rf(11), fontWeight: "700" },

  readings: {
    flexDirection: "row",
    gap: spacing.xs,
    backgroundColor: "#1e293b",
    borderRadius: 8,
    padding: spacing.sm,
  },
  reading: { flex: 1, alignItems: "center" },
  readingValue: { color: colors.primary, fontSize: typography.body, fontWeight: "800", fontVariant: ["tabular-nums"] as any },
  readingLabel: { color: colors.textMuted, fontSize: rf(10), fontWeight: "700" },

  paramGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.xs,
  },
  paramInputWrap: { width: "48%", gap: 2 },
  paramLabel: { color: colors.textMuted, fontSize: rf(11), fontWeight: "600" },
  paramInput: {
    backgroundColor: "#1e293b",
    borderRadius: 6,
    padding: spacing.sm,
    color: colors.text,
    fontSize: typography.body,
    fontWeight: "700",
    borderWidth: 1,
    borderColor: "#334155",
  },
  paramInputDisabled: { opacity: 0.4 },

  btnRow: { flexDirection: "row", gap: spacing.xs },
  btnStart: {
    flex: 1,
    backgroundColor: "#16a34a",
    borderRadius: 8,
    padding: spacing.sm,
    alignItems: "center",
  },
  btnStartText: { color: "#fff", fontWeight: "700", fontSize: typography.small },
  btnStop: {
    flex: 1,
    backgroundColor: "#7f1d1d",
    borderRadius: 8,
    padding: spacing.sm,
    alignItems: "center",
  },
  btnStopText: { color: "#fff", fontWeight: "700", fontSize: typography.small },
  btnDisabled: { opacity: 0.4 },

  errorText: { color: "#ef4444", fontSize: typography.small },
  offlineBanner: {
    backgroundColor: "#1e293b",
    borderRadius: 6,
    padding: spacing.xs,
    alignItems: "center",
  },
  offlineText: { color: "#f59e0b", fontSize: typography.small, fontWeight: "600" },
  sourceBadgeStm: {
    backgroundColor: "#1e3a5f",
    borderRadius: 4,
    paddingHorizontal: 5,
    paddingVertical: 2,
    borderWidth: 1,
    borderColor: "#3b82f6",
  },
  sourceBadgeEsp: {
    backgroundColor: "#14532d",
    borderRadius: 4,
    paddingHorizontal: 5,
    paddingVertical: 2,
    borderWidth: 1,
    borderColor: "#22c55e",
  },
  sourceBadgeText: { color: "#fff", fontSize: rf(9), fontWeight: "800" },
});
