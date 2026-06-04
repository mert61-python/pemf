/**
 * ControlScreen — Tam Tedavi Kontrol Ekranı
 *
 * Python unified_control_window.py'nin React karşılığı.
 * 3 sekme: Otomatik Mod | Manuel Mod | AI Modu
 */
import { useState, useCallback } from "react";
import {
  ScrollView,
  Text,
  View,
  StyleSheet,
  TouchableOpacity,
  TextInput,
  Alert,
} from "react-native";
import { colors, spacing, typography } from "@/theme/tokens";
import { useLiveData } from "@/context/LiveDataContext";
import { useSessionControl } from "@/hooks/useSessionControl";
import { SessionProgressCard } from "@/components/domain/SessionProgressCard";
import { CoilParameterPanel } from "@/components/domain/CoilParameterPanel";
import { apiGet, apiPost } from "@/services/apiClient";

// ─── Tab types ────────────────────────────────────────────────────────────────
type TabKey = "automatic" | "manual" | "ai";

const TABS: { key: TabKey; label: string; icon: string }[] = [
  { key: "automatic", label: "Otomatik", icon: "🤖" },
  { key: "manual",    label: "Manuel",   icon: "🎛" },
  { key: "ai",        label: "AI Modu",  icon: "🧠" },
];

// ─── Target conditions ─────────────────────────────────────────────────────
const AUTO_TARGETS = [
  "Doku İyileşmesi", "Eklem Ağrısı", "Kas Spazmı",
  "Kırık İyileşmesi", "Enflamasyon Azaltma", "Sinir Rejenerasyonu",
  "Bağ Dokusu Tamiri", "Ödem Azaltma",
];

// ─── Component ────────────────────────────────────────────────────────────────
export function ControlScreen() {
  const { snapshot } = useLiveData();
  const {
    isActive, treatment, elapsedSec, remainingSec,
    loading, error, startSession, stopSession, emergencyStop,
  } = useSessionControl();

  const [activeTab, setActiveTab] = useState<TabKey>("manual");

  // ── Otomatik Mod state ─────────────────────────────────────────────────
  const [autoTarget, setAutoTarget] = useState(AUTO_TARGETS[0]);
  const [autoFreq, setAutoFreq] = useState("50");
  const [autoDuty, setAutoDuty] = useState("25");
  const [autoDuration, setAutoDuration] = useState("20");

  // ── Manuel Mod state ───────────────────────────────────────────────────
  const [masterFreq, setMasterFreq] = useState("50");
  const [masterDuty, setMasterDuty] = useState("25");
  const [masterDuration, setMasterDuration] = useState("20");
  const [selectedCoils, setSelectedCoils] = useState<Set<number>>(
    new Set([1, 2, 3, 4, 5, 6, 7, 8])
  );

  // ── AI Mod state ───────────────────────────────────────────────────────
  const [aiTarget, setAiTarget] = useState(AUTO_TARGETS[0]);
  const [aiAnalyzing, setAiAnalyzing] = useState(false);
  const [aiResult, setAiResult] = useState<any>(null);

  // ─── Helpers ─────────────────────────────────────────────────────────────
  const toggleCoil = useCallback((id: number) => {
    setSelectedCoils((prev) => {
      const next = new Set(prev);
      if (next.has(id)) { next.delete(id); } else { next.add(id); }
      return next;
    });
  }, []);

  const patientName = snapshot.patient?.name || "";

  // ─── Session start handlers ───────────────────────────────────────────────
  const handleStartAuto = async () => {
    const ok = await startSession({
      patientName,
      mode: "Otomatik",
      targetCondition: autoTarget,
      frequency: parseFloat(autoFreq) || 50,
      duty: parseFloat(autoDuty) || 25,
      intensity: parseFloat(autoDuty) || 25,
      durationMinutes: parseInt(autoDuration) || 20,
      coilIds: Array.from(selectedCoils),
    });
    if (!ok) Alert.alert("Hata", error ?? "Seans başlatılamadı.");
  };

  const handleStartManual = async () => {
    if (selectedCoils.size === 0) {
      Alert.alert("Uyarı", "En az bir bobin seçin.");
      return;
    }
    const ok = await startSession({
      patientName,
      mode: "Manuel",
      frequency: parseFloat(masterFreq) || 50,
      duty: parseFloat(masterDuty) || 25,
      intensity: parseFloat(masterDuty) || 25,
      durationMinutes: parseInt(masterDuration) || 20,
      coilIds: Array.from(selectedCoils),
    });
    if (!ok) Alert.alert("Hata", error ?? "Seans başlatılamadı.");
  };

  const handleAiAnalyze = async () => {
    setAiAnalyzing(true);
    setAiResult(null);
    try {
      const rec = await apiPost<any>("/hardware/auto_preset", { target_condition: aiTarget }, null);
      setAiResult(rec);
      if (rec?.parameters) {
        setAutoFreq(String(rec.parameters.freq ?? 50));
        setAutoDuty(String(rec.parameters.duty ?? 25));
        setAutoDuration(String(Math.round(rec.parameters.duration ?? 20)));
      }
    } catch {
      setAiResult({ error: "AI analizi başarısız" });
    } finally {
      setAiAnalyzing(false);
    }
  };

  const handleStartAi = async () => {
    if (!aiResult?.parameters) {
      Alert.alert("Uyarı", "Önce AI analizi yapın.");
      return;
    }
    const p = aiResult.parameters;
    const ok = await startSession({
      patientName,
      mode: "AI",
      targetCondition: aiTarget,
      frequency: p.freq ?? 50,
      duty: p.duty ?? 25,
      intensity: p.duty ?? 25,
      durationMinutes: Math.round(p.duration ?? 20),
      coilIds: Array.from(selectedCoils),
    });
    if (!ok) Alert.alert("Hata", error ?? "Seans başlatılamadı.");
  };

  // ─── Render ───────────────────────────────────────────────────────────────
  const coils = snapshot.coils ?? [];

  return (
    <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
      {/* ── Active Session Progress ────────────────────────────── */}
      <SessionProgressCard
        isActive={isActive}
        mode={treatment?.mode ?? "Sistem Hazır"}
        elapsedSec={elapsedSec}
        remainingSec={remainingSec}
        durationSec={treatment?.durationSec ?? 0}
        frequencyHz={treatment?.frequencyHz ?? 0}
        intensityMt={treatment?.intensityMt ?? 0}
        onStop={stopSession}
        onEmergencyStop={emergencyStop}
        loading={loading}
      />

      {/* ── Tab bar ───────────────────────────────────────────── */}
      <View style={styles.tabBar}>
        {TABS.map((tab) => (
          <TouchableOpacity
            key={tab.key}
            style={[styles.tab, activeTab === tab.key && styles.tabActive]}
            onPress={() => setActiveTab(tab.key)}
          >
            <Text style={styles.tabIcon}>{tab.icon}</Text>
            <Text style={[styles.tabLabel, activeTab === tab.key && styles.tabLabelActive]}>
              {tab.label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* ── TAB: Otomatik ─────────────────────────────────────── */}
      {activeTab === "automatic" && (
        <View style={styles.section}>
          <SectionTitle text="Otomatik Mod — Hedefe Göre Protokol" />
          <Text style={styles.hint}>
            Hedef durumu seçin, sistem literatür tabanlı parametreleri otomatik ayarlar.
          </Text>

          <FormLabel text="Tedavi Hedefi" />
          <View style={styles.targetGrid}>
            {AUTO_TARGETS.map((t) => (
              <TouchableOpacity
                key={t}
                style={[styles.targetChip, autoTarget === t && styles.targetChipActive]}
                onPress={() => setAutoTarget(t)}
              >
                <Text style={[styles.targetChipText, autoTarget === t && styles.targetChipTextActive]}>
                  {t}
                </Text>
              </TouchableOpacity>
            ))}
          </View>

          <View style={styles.paramRow}>
            <ParamField label="Frekans (Hz)" value={autoFreq} onChangeText={setAutoFreq} />
            <ParamField label="Duty (%)" value={autoDuty} onChangeText={setAutoDuty} />
            <ParamField label="Süre (dk)" value={autoDuration} onChangeText={setAutoDuration} />
          </View>

          <CoilSelector coils={coils} selected={selectedCoils} onToggle={toggleCoil} />

          <StartButton
            label="🤖 Otomatik Seansı Başlat"
            onPress={handleStartAuto}
            disabled={isActive || loading}
          />
        </View>
      )}

      {/* ── TAB: Manuel ───────────────────────────────────────── */}
      {activeTab === "manual" && (
        <View style={styles.section}>
          <SectionTitle text="Manuel Mod — Bobin Bazlı Kontrol" />

          {/* Master controls */}
          <View style={styles.masterCard}>
            <Text style={styles.masterTitle}>📡 Toplu Uygulama</Text>
            <View style={styles.paramRow}>
              <ParamField label="Frekans (Hz)" value={masterFreq} onChangeText={setMasterFreq} />
              <ParamField label="Duty (%)" value={masterDuty} onChangeText={setMasterDuty} />
              <ParamField label="Süre (dk)" value={masterDuration} onChangeText={setMasterDuration} />
            </View>
            <CoilSelector coils={coils} selected={selectedCoils} onToggle={toggleCoil} />
            <StartButton
              label="▶ Seçili Bobinleri Başlat"
              onPress={handleStartManual}
              disabled={isActive || loading}
            />
          </View>

          {/* Per-coil panels */}
          <Text style={styles.subTitle}>Tekil Bobin Kontrolü</Text>
          <View style={styles.coilGrid}>
            {coils.map((coil) => (
              <CoilParameterPanel
                key={coil.id}
                coilId={coil.id}
                connected={coil.connected}
                running={coil.running}
                objectTemp={coil.objectTemp}
                frequencyHz={coil.frequencyHz}
                dutyCycle={coil.dutyCycle}
                magneticMt={coil.magneticMt}
                currentA={coil.currentA}
                defaultFreq={parseFloat(masterFreq) || 50}
                defaultDuty={parseFloat(masterDuty) || 25}
                disabled={isActive}
              />
            ))}
          </View>
        </View>
      )}

      {/* ── TAB: AI ───────────────────────────────────────────── */}
      {activeTab === "ai" && (
        <View style={styles.section}>
          <SectionTitle text="AI Modu — Yapay Zeka Destekli Tedavi" />
          <Text style={styles.hint}>
            AI, hasta durumuna göre optimal frekans, duty ve süre parametrelerini önerir.
          </Text>

          <FormLabel text="Hedef Durum" />
          <View style={styles.targetGrid}>
            {AUTO_TARGETS.map((t) => (
              <TouchableOpacity
                key={t}
                style={[styles.targetChip, aiTarget === t && styles.targetChipActive]}
                onPress={() => setAiTarget(t)}
              >
                <Text style={[styles.targetChipText, aiTarget === t && styles.targetChipTextActive]}>
                  {t}
                </Text>
              </TouchableOpacity>
            ))}
          </View>

          <TouchableOpacity
            style={[styles.btnAnalyze, aiAnalyzing && { opacity: 0.5 }]}
            onPress={handleAiAnalyze}
            disabled={aiAnalyzing}
          >
            <Text style={styles.btnAnalyzeText}>
              {aiAnalyzing ? "🧠 Analiz Ediliyor..." : "🧠 AI Analizi Başlat"}
            </Text>
          </TouchableOpacity>

          {aiResult && (
            <View style={styles.aiResultCard}>
              {aiResult.error ? (
                <Text style={styles.aiError}>{aiResult.error}</Text>
              ) : (
                <>
                  <Text style={styles.aiResultTitle}>✅ AI Önerisi</Text>
                  <View style={styles.paramRow}>
                    <StatChip label="Frekans" value={`${aiResult.parameters?.freq ?? "—"} Hz`} />
                    <StatChip label="Duty" value={`${aiResult.parameters?.duty ?? "—"}%`} />
                    <StatChip label="Süre" value={`${Math.round(aiResult.parameters?.duration ?? 0)} dk`} />
                  </View>
                  <Text style={styles.aiSource}>
                    Kaynak: {aiResult.parameters?.source ?? "Literatür"}
                  </Text>
                </>
              )}
            </View>
          )}

          <CoilSelector coils={coils} selected={selectedCoils} onToggle={toggleCoil} />

          <StartButton
            label="🧠 AI Seansını Başlat"
            onPress={handleStartAi}
            disabled={isActive || loading || !aiResult?.parameters}
            color="#7c3aed"
          />
        </View>
      )}

      {/* ── Emergency Stop (always visible) ──────────────────── */}
      <TouchableOpacity style={styles.emergencyBtn} onPress={emergencyStop}>
        <Text style={styles.emergencyBtnText}>🚨 TÜM BOBİNLERİ ACİL DURDUR</Text>
      </TouchableOpacity>
    </ScrollView>
  );
}

// ─── Sub-components ───────────────────────────────────────────────────────────
function SectionTitle({ text }: { text: string }) {
  return <Text style={styles.sectionTitle}>{text}</Text>;
}

function FormLabel({ text }: { text: string }) {
  return <Text style={styles.formLabel}>{text}</Text>;
}

function ParamField({
  label, value, onChangeText,
}: {
  label: string; value: string; onChangeText: (v: string) => void;
}) {
  return (
    <View style={styles.paramField}>
      <Text style={styles.paramFieldLabel}>{label}</Text>
      <TextInput
        style={styles.paramFieldInput}
        value={value}
        onChangeText={onChangeText}
        keyboardType="numeric"
        selectTextOnFocus
      />
    </View>
  );
}

function CoilSelector({
  coils, selected, onToggle,
}: {
  coils: any[];
  selected: Set<number>;
  onToggle: (id: number) => void;
}) {
  return (
    <View style={styles.coilSelector}>
      <Text style={styles.formLabel}>Bobin Seçimi</Text>
      <View style={styles.coilSelectorGrid}>
        {(coils.length > 0 ? coils : Array.from({ length: 8 }, (_, i) => ({ id: i + 1, connected: false }))).map((c) => (
          <TouchableOpacity
            key={c.id}
            style={[
              styles.coilSelectorBtn,
              selected.has(c.id) && styles.coilSelectorBtnActive,
              !c.connected && styles.coilSelectorBtnOffline,
            ]}
            onPress={() => onToggle(c.id)}
          >
            <Text style={[styles.coilSelectorText, selected.has(c.id) && styles.coilSelectorTextActive]}>
              {c.id}
            </Text>
          </TouchableOpacity>
        ))}
      </View>
    </View>
  );
}

function StartButton({
  label, onPress, disabled, color = "#22c55e",
}: {
  label: string; onPress: () => void; disabled: boolean; color?: string;
}) {
  return (
    <TouchableOpacity
      style={[styles.startBtn, { backgroundColor: color }, disabled && styles.startBtnDisabled]}
      onPress={onPress}
      disabled={disabled}
    >
      <Text style={styles.startBtnText}>{label}</Text>
    </TouchableOpacity>
  );
}

function StatChip({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.statChip}>
      <Text style={styles.statChipLabel}>{label}</Text>
      <Text style={styles.statChipValue}>{value}</Text>
    </View>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────
const styles = StyleSheet.create({
  container: {
    padding: spacing.md,
    gap: spacing.md,
    paddingBottom: spacing.xxl,
  },
  tabBar: {
    flexDirection: "row",
    backgroundColor: "#0f172a",
    borderRadius: 12,
    padding: 4,
    gap: 4,
  },
  tab: {
    flex: 1,
    alignItems: "center",
    padding: spacing.sm,
    borderRadius: 10,
    gap: 2,
  },
  tabActive: { backgroundColor: "#1e3a5f" },
  tabIcon: { fontSize: 18 },
  tabLabel: { color: colors.textMuted, fontSize: typography.small, fontWeight: "600" },
  tabLabelActive: { color: colors.primary, fontWeight: "700" },

  section: { gap: spacing.md },
  sectionTitle: {
    color: colors.text,
    fontSize: typography.subtitle,
    fontWeight: "700",
  },
  subTitle: {
    color: colors.textMuted,
    fontSize: typography.body,
    fontWeight: "600",
    marginTop: spacing.xs,
  },
  hint: {
    color: colors.textMuted,
    fontSize: typography.small,
    lineHeight: 20,
  },
  formLabel: {
    color: colors.textMuted,
    fontSize: typography.small,
    fontWeight: "700",
    marginBottom: spacing.xs,
  },
  targetGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.xs,
  },
  targetChip: {
    backgroundColor: "#1e293b",
    borderRadius: 20,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderWidth: 1,
    borderColor: "#334155",
  },
  targetChipActive: {
    backgroundColor: "#1d4ed8",
    borderColor: "#3b82f6",
  },
  targetChipText: { color: colors.textMuted, fontSize: typography.small },
  targetChipTextActive: { color: "#fff", fontWeight: "700" },

  paramRow: { flexDirection: "row", gap: spacing.sm },
  paramField: { flex: 1 },
  paramFieldLabel: { color: colors.textMuted, fontSize: 11, fontWeight: "600", marginBottom: 4 },
  paramFieldInput: {
    backgroundColor: "#1e293b",
    borderRadius: 8,
    padding: spacing.sm,
    color: colors.text,
    fontSize: typography.body,
    fontWeight: "700",
    borderWidth: 1,
    borderColor: "#334155",
    textAlign: "center",
  },

  masterCard: {
    backgroundColor: "#0f172a",
    borderRadius: 14,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: "#1e3a5f",
    gap: spacing.md,
  },
  masterTitle: { color: colors.text, fontWeight: "700", fontSize: typography.body },

  coilGrid: { gap: spacing.sm },

  coilSelector: { gap: spacing.xs },
  coilSelectorGrid: { flexDirection: "row", gap: spacing.xs, flexWrap: "wrap" },
  coilSelectorBtn: {
    width: 40,
    height: 40,
    borderRadius: 10,
    backgroundColor: "#1e293b",
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: "#334155",
  },
  coilSelectorBtnActive: { backgroundColor: "#1d4ed8", borderColor: "#3b82f6" },
  coilSelectorBtnOffline: { opacity: 0.4 },
  coilSelectorText: { color: colors.textMuted, fontWeight: "700" },
  coilSelectorTextActive: { color: "#fff" },

  startBtn: {
    borderRadius: 12,
    padding: spacing.md,
    alignItems: "center",
    marginTop: spacing.xs,
  },
  startBtnDisabled: { opacity: 0.4 },
  startBtnText: { color: "#fff", fontWeight: "800", fontSize: typography.body },

  btnAnalyze: {
    backgroundColor: "#6d28d9",
    borderRadius: 12,
    padding: spacing.md,
    alignItems: "center",
  },
  btnAnalyzeText: { color: "#fff", fontWeight: "700" },

  aiResultCard: {
    backgroundColor: "#0f172a",
    borderRadius: 14,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: "#7c3aed44",
    gap: spacing.sm,
  },
  aiResultTitle: { color: "#a78bfa", fontWeight: "700", fontSize: typography.body },
  aiError: { color: "#ef4444", fontSize: typography.small },
  aiSource: { color: colors.textMuted, fontSize: typography.small },

  statChip: {
    flex: 1,
    backgroundColor: "#1e293b",
    borderRadius: 8,
    padding: spacing.sm,
    alignItems: "center",
  },
  statChipLabel: { color: colors.textMuted, fontSize: 10, fontWeight: "700" },
  statChipValue: { color: colors.primary, fontSize: typography.body, fontWeight: "800" },

  emergencyBtn: {
    backgroundColor: "#7f1d1d",
    borderRadius: 14,
    padding: spacing.lg,
    alignItems: "center",
    marginTop: spacing.md,
    borderWidth: 2,
    borderColor: "#ef4444",
  },
  emergencyBtnText: { color: "#fff", fontWeight: "800", fontSize: typography.body, letterSpacing: 0.5 },
});
