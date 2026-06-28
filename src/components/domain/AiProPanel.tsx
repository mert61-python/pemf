/**
 * AiProPanel — AI Pro kapalı-döngü kontrol yüzeyi (Kontrol sekmesi).
 * ================================================================
 * Sunucu kamerasından (backend VideoCapture(0)) gelen canlı görüntü + FGS + hedef
 * konumu + organ seçimi + Z-kalibrasyon + süre/sayaç + per-coil diagnostik tablo.
 *
 * Canlı veri: WebSocket 'ai_vision' (LiveDataContext.aiVisionData).
 * Kontrol:    /api/ai/pro/start | stop | organ | calibrate | status
 *
 * NOT: Tam per-organ per-coil DDS hedefleme backend'de KediPredictor (em_kedi)
 * modeli ile gelecek; şimdilik FGS + organ-bias ile uniform sürüş + canlı telemetri.
 */
import { useState, useEffect, useCallback } from "react";
import { View, Text, StyleSheet, TouchableOpacity, Image, TextInput } from "react-native";
import { colors, spacing, typography } from "@/theme/tokens";
import { useLiveData } from "@/context/LiveDataContext";
import { apiGet, apiPost } from "@/services/apiClient";

const ORGANS = [
  { id: 0, name: "Tüm Vücut" }, { id: 1, name: "Mide" }, { id: 2, name: "Böbrek" },
  { id: 3, name: "Karaciğer" }, { id: 4, name: "Mesane" }, { id: 5, name: "Pankreas" }, { id: 6, name: "Bağırsak" },
];

function fmtSec(sec: number): string {
  const s0 = Math.max(0, Math.floor(sec));
  const m = Math.floor(s0 / 60);
  return `${m}:${String(s0 % 60).padStart(2, "0")}`;
}

export function AiProPanel() {
  const { aiVisionData: v } = useLiveData();

  const [organId, setOrganId] = useState(0);
  const [duration, setDuration] = useState("20");
  const [running, setRunning] = useState(false);
  const [calibrated, setCalibrated] = useState(false);
  const [busy, setBusy] = useState(false);

  // Backend durumunu senkronla (özellikle süre dolup auto-stop olduğunda).
  useEffect(() => {
    let alive = true;
    const sync = async () => {
      const st = await apiGet<any>("/ai/pro/status", null, { silent: true });
      if (!alive || !st) return;
      setRunning(Boolean(st.active));
      setCalibrated(Boolean(st.calibrated));
      if (typeof st.organId === "number") setOrganId(st.organId);
    };
    sync();
    const id = setInterval(sync, 3000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  const start = useCallback(async () => {
    setBusy(true);
    const res = await apiPost<any>("/ai/pro/start", { organ_id: organId, duration_minutes: parseInt(duration) || 20 }, null);
    if (res?.status === "success") setRunning(true);
    setBusy(false);
  }, [organId, duration]);

  const stop = useCallback(async () => {
    setBusy(true);
    await apiPost<any>("/ai/pro/stop", {}, null);
    setRunning(false);
    setBusy(false);
  }, []);

  const changeOrgan = useCallback(async (id: number) => {
    setOrganId(id);
    await apiPost<any>("/ai/pro/organ", { organ_id: id }, null).catch(() => {});
  }, []);

  const calibrate = useCallback(async () => {
    const res = await apiPost<any>("/ai/pro/calibrate", {}, null);
    if (res?.calibrated) setCalibrated(true);
  }, []);

  const remaining = v?.remainingSec ?? 0;
  const perCoil = v?.perCoil ?? [];

  return (
    <View style={styles.wrap}>
      <Text style={styles.note}>
        📷 Sunucu kamerasından canlı kapalı-döngü tedavi. (Tam per-organ DDS hedefleme yakında.)
      </Text>

      {/* Canlı kamera görüntüsü (sunucudan) */}
      <View style={styles.camBox}>
        {v?.imageBase64 ? (
          <Image source={{ uri: `data:image/jpeg;base64,${v.imageBase64}` }} style={styles.cam} resizeMode="contain" />
        ) : (
          <Text style={styles.camPlaceholder}>{running ? "Görüntü bekleniyor…" : "AI Pro durdu."}</Text>
        )}
      </View>

      {/* Canlı metrikler */}
      <View style={styles.metricRow}>
        <Metric label="FGS" value={`${v?.fgs_total ?? "—"}`} />
        <Metric label="E-Alan" value={`${v?.eField ?? "—"}`} />
        <Metric label="Hedef X" value={`${v?.target?.x ?? "—"}`} />
        <Metric label="Hedef Y" value={`${v?.target?.y ?? "—"}`} />
      </View>

      {/* Organ seçimi */}
      <Text style={styles.label}>🧠 Hedef Organ</Text>
      <View style={styles.organGrid}>
        {ORGANS.map((o) => (
          <TouchableOpacity
            key={o.id}
            style={[styles.organChip, organId === o.id && styles.organChipActive]}
            onPress={() => changeOrgan(o.id)}
          >
            <Text style={[styles.organText, organId === o.id && styles.organTextActive]}>{o.name}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Süre + kalibrasyon */}
      <View style={styles.row}>
        <View style={{ flex: 1 }}>
          <Text style={styles.label}>⏱ Süre (dk)</Text>
          <TextInput style={styles.input} value={duration} onChangeText={setDuration} keyboardType="numeric" editable={!running} selectTextOnFocus />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.label}>Kalan</Text>
          <Text style={styles.countdown}>{running ? fmtSec(remaining) : "—"}</Text>
        </View>
        <View style={{ flex: 1, justifyContent: "flex-end" }}>
          <TouchableOpacity style={[styles.calBtn, calibrated && styles.calBtnDone]} onPress={calibrate}>
            <Text style={styles.calBtnText}>{calibrated ? "✓ Kalibre" : "🎯 Z Kalibre"}</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Start / Stop */}
      <TouchableOpacity
        style={[styles.toggle, running ? styles.toggleStop : styles.toggleStart, busy && { opacity: 0.5 }]}
        onPress={running ? stop : start}
        disabled={busy}
      >
        <Text style={styles.toggleText} numberOfLines={1} adjustsFontSizeToFit>{running ? "⏹ AI Pro'yu Durdur" : "🚀 AI Pro Başlat (1Hz DDS)"}</Text>
      </TouchableOpacity>

      {/* Per-coil diagnostik tablo */}
      <Text style={styles.label}>📊 Bobin Diagnostiği</Text>
      <View style={styles.table}>
        <View style={styles.tr}>
          <Text style={[styles.th, { flex: 1 }]}>Bobin</Text>
          <Text style={[styles.th, { flex: 1 }]}>Frekans</Text>
          <Text style={[styles.th, { flex: 1 }]}>Duty</Text>
          <Text style={[styles.th, { flex: 1 }]}>Faz</Text>
        </View>
        {(perCoil.length ? perCoil : Array.from({ length: 8 }, (_, i) => ({ id: i + 1, freq: 0, duty: 0, phase: 0 }))).map((c) => (
          <View key={c.id} style={styles.tr}>
            <Text style={[styles.td, { flex: 1 }]}>{c.id}</Text>
            <Text style={[styles.td, { flex: 1 }]}>{c.freq} Hz</Text>
            <Text style={[styles.td, { flex: 1 }]}>{c.duty}%</Text>
            <Text style={[styles.td, { flex: 1 }]}>{c.phase}°</Text>
          </View>
        ))}
      </View>
    </View>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.metric}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={styles.metricValue} numberOfLines={1} adjustsFontSizeToFit>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.md },
  note: { color: colors.textMuted, fontSize: typography.small, fontStyle: "italic" },
  camBox: {
    height: 200, backgroundColor: "#000", borderRadius: 12,
    alignItems: "center", justifyContent: "center", overflow: "hidden",
    borderWidth: 1, borderColor: "#1e3a5f",
  },
  cam: { width: "100%", height: "100%" },
  camPlaceholder: { color: colors.textMuted, fontSize: typography.small },
  metricRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  metric: { flex: 1, backgroundColor: "#0f172a", borderRadius: 8, padding: spacing.sm, alignItems: "center" },
  metricLabel: { color: colors.textMuted, fontSize: 10, fontWeight: "700" },
  metricValue: { color: colors.primary, fontSize: typography.body, fontWeight: "800" },
  label: { color: colors.textMuted, fontSize: typography.small, fontWeight: "700", marginBottom: spacing.xs },
  organGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs },
  organChip: {
    backgroundColor: "#1e293b", borderRadius: 16, paddingHorizontal: spacing.md, paddingVertical: spacing.xs,
    borderWidth: 1, borderColor: "#334155",
  },
  organChipActive: { backgroundColor: "#1d4ed8", borderColor: "#3b82f6" },
  organText: { color: colors.textMuted, fontSize: typography.small },
  organTextActive: { color: "#fff", fontWeight: "700" },
  row: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-end" },
  input: {
    backgroundColor: "#1e293b", borderRadius: 8, padding: spacing.sm, color: colors.text,
    fontWeight: "700", borderWidth: 1, borderColor: "#334155", textAlign: "center",
  },
  countdown: { color: colors.primary, fontSize: typography.subtitle, fontWeight: "800", textAlign: "center", paddingVertical: spacing.xs },
  calBtn: { backgroundColor: "#334155", borderRadius: 8, padding: spacing.sm, alignItems: "center" },
  calBtnDone: { backgroundColor: "#15803d" },
  calBtnText: { color: "#fff", fontWeight: "700", fontSize: typography.small },
  toggle: { borderRadius: 12, padding: spacing.md, alignItems: "center" },
  toggleStart: { backgroundColor: "#7c3aed" },
  toggleStop: { backgroundColor: "#ef4444" },
  toggleText: { color: "#fff", fontWeight: "800", fontSize: typography.body },
  table: { backgroundColor: "#0f172a", borderRadius: 10, overflow: "hidden", borderWidth: 1, borderColor: "#1e293b" },
  tr: { flexDirection: "row", borderBottomWidth: 1, borderBottomColor: "#1e293b" },
  th: { color: colors.textMuted, fontSize: 11, fontWeight: "800", padding: spacing.sm },
  td: { color: colors.text, fontSize: typography.small, padding: spacing.sm },
});
