/**
 * ControlScreen — Tam Tedavi Kontrol Ekranı
 *
 * Python unified_control_window.py'nin React karşılığı.
 * 3 sekme: Otomatik Mod | Manuel Mod | AI Modu
 */
import { useState, useCallback, useEffect, useRef } from "react";
import {
  Text,
  View,
  StyleSheet,
  TouchableOpacity,
  TextInput,
} from "react-native";
import { colors, spacing, typography, rf, rs } from "@/theme/tokens";
import type { CoilStatus } from "@/types/domain";
import { useLiveData } from "@/context/LiveDataContext";
import { useSessionControl } from "@/hooks/useSessionControl";
import { SessionProgressCard } from "@/components/domain/SessionProgressCard";
import { CoilParameterPanel } from "@/components/domain/CoilParameterPanel";
import { apiPost, platformAlert } from "@/services/apiClient";
import { clampTherapyParams } from "@/services/therapyLimits";
import { useAppNav } from "@/context/AppNavContext";
import { useAuth } from "@/context/AuthContext";
import { AiProPanel } from "@/components/domain/AiProPanel";
import { ObservationNotesModal } from "@/components/domain/ObservationNotesModal";
import { ResponsiveGrid } from "@/components/ui/ResponsiveGrid";

// ─── Tab types ────────────────────────────────────────────────────────────────
type TabKey = "automatic" | "manual" | "ai" | "aipro";

const TABS: { key: TabKey; label: string; icon: string }[] = [
  { key: "automatic", label: "Otomatik", icon: "🤖" },
  { key: "manual",    label: "Manuel",   icon: "🎛" },
  { key: "ai",        label: "AI Modu",  icon: "🧠" },
  { key: "aipro",     label: "AI Pro",   icon: "🎯" },
];

// ─── Target conditions ─────────────────────────────────────────────────────
const AUTO_TARGETS = [
  "Doku İyileşmesi", "Eklem Ağrısı", "Kas Spazmı",
  "Kırık İyileşmesi", "Enflamasyon Azaltma", "Sinir Rejenerasyonu",
  "Bağ Dokusu Tamiri", "Ödem Azaltma",
];

// ─── Component ────────────────────────────────────────────────────────────────
export function ControlScreen() {
  const { snapshot, telemetryStale } = useLiveData();
  const { selectedPatient } = useAppNav();
  const { session } = useAuth();
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
  const [autoIntensity, setAutoIntensity] = useState("1.0");
  const [autoLoading, setAutoLoading] = useState(false);

  // ── Manuel Mod state ───────────────────────────────────────────────────
  const [masterFreq, setMasterFreq] = useState("100");
  const [masterDuty, setMasterDuty] = useState("25");
  const [masterPhase, setMasterPhase] = useState("0");
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

  const patientName = selectedPatient?.name || snapshot.patient?.name || "";
  const isStmConnected = snapshot.stm === "online";
  const isCoilConnected = useCallback(
    (coil: { id: number; connected?: boolean }) =>
      coil.id <= 5 ? isStmConnected : Boolean(coil.connected),
    [isStmConnected]
  );

  // Güvenlik: parametreleri aralığa çek, düzeltme olduysa kullanıcıyı uyar.
  const clampWithAlert = useCallback((input: Parameters<typeof clampTherapyParams>[0]) => {
    const { values, warnings } = clampTherapyParams(input);
    if (warnings.length) platformAlert("Parametre güvenliği", warnings.join("\n"));
    return values;
  }, []);

  // ORTA fix: süre girişini normalize et — NaN/boş/≤0 (ör. "-5" → parseInt=-5 TRUTHY, `||20`'yi ATLAR →
  // clampTherapyParams min=0'a çeker → süresiz-seans körlüğüne sızar) yerine 20dk varsayılan (backend ge=1).
  const parseDurationMin = (s: string): number => {
    const n = parseInt(s, 10);
    return Number.isFinite(n) && n >= 1 ? n : 20;
  };

  // Hedef seçilince literatür-tabanlı parametreleri backend'den çek (auto_preset).
  const applyAutoPreset = useCallback(async (target: string) => {
    setAutoTarget(target);
    setAutoLoading(true);
    try {
      const rec = await apiPost<any>("/hardware/auto_preset", { target_condition: target }, null);
      const p = rec?.parameters;
      if (p) {
        if (p.freq != null) setAutoFreq(String(p.freq));
        if (p.duty != null) setAutoDuty(String(p.duty));
        if (p.duration != null) setAutoDuration(String(Math.round(p.duration)));
        if (p.intensity != null) setAutoIntensity(String(p.intensity));
      }
    } catch {
      /* öneri alınamadı — kullanıcı elle ayarlar */
    } finally {
      setAutoLoading(false);
    }
  }, []);

  // ─── Session start handlers ───────────────────────────────────────────────
  // YÜKSEK fix: Seçili bobinlerden bağlı OLANLARı döndür (STM 1-5 isStmConnected + ESP 6-8 coil.connected);
  // hiç seçilmemiş/hiçbiri bağlı değilse uyarıp null döner. Manuel + Auto + AI AYNI filtreyi kullansın →
  // offline bobinin seansa girip "sahte aktif tedavi" göstermesi (ve "en az bir bobin" guard eksikliği) önlenir.
  const resolveEffectiveCoils = (): number[] | null => {
    if (selectedCoils.size === 0) {
      platformAlert("Uyarı", "En az bir bobin seçin.");
      return null;
    }
    const requested = Array.from(selectedCoils);
    const coilsById = new Map(snapshot.coils.map((c) => [c.id, c]));
    const effective = requested.filter((id) => isCoilConnected(coilsById.get(id) ?? { id }));
    if (effective.length === 0) {
      platformAlert("Bağlantı yok", "Seçili bobinler için aktif bağlantı yok (STM32/WiFi çevrimdışı).");
      return null;
    }
    if (effective.length < requested.length) {
      platformAlert("Bazı bobinler çevrimdışı", "Bağlı olmayan bobinler atlandı; yalnızca aktif bobinlere komut gönderiliyor.");
    }
    return effective;
  };

  const handleStartAuto = async () => {
    const effective = resolveEffectiveCoils();
    if (!effective) return;
    const p = clampWithAlert({
      freq: parseFloat(autoFreq) || 50,
      duty: parseFloat(autoDuty) || 25,
      intensity: parseFloat(autoIntensity) || 1.0,
      duration: parseDurationMin(autoDuration),
    });
    const ok = await startSession({
      patientId: selectedPatient?.id,
      patientName,
      mode: "Otomatik",
      targetCondition: autoTarget,
      frequency: p.freq,
      duty: p.duty,
      intensity: p.intensity,  // Yoğunluk (mT) — ayrı alan
      durationMinutes: p.duration,
      coilIds: effective,
      operatorEmail: session?.email,
    });
    if (!ok) platformAlert("Hata", error ?? "Seans başlatılamadı.");
  };

  // Manuel "Toplu Uygulama" → SEANS olarak başlat (ilerleme/timer/gözlem-notu/history +
  // 409 interlock kazanır). /session/start STM+ESP'yi faz dahil sürer.
  const handleStartManual = async () => {
    const effective = resolveEffectiveCoils();
    if (!effective) return;
    const p = clampWithAlert({
      freq: parseFloat(masterFreq) || 100,
      duty: parseFloat(masterDuty) || 25,
      phase: parseFloat(masterPhase) || 0,
      duration: parseDurationMin(masterDuration),
    });
    const ok = await startSession({
      patientId: selectedPatient?.id,
      patientName,
      mode: "Manuel",
      frequency: p.freq,
      duty: p.duty,
      intensity: 0, // Manuel'de hedef mT yok (parametre-temelli sürüş)
      phase: p.phase,
      durationMinutes: p.duration,
      coilIds: effective,
      operatorEmail: session?.email,
    });
    if (!ok) platformAlert("Hata", error ?? "Manuel seans başlatılamadı (zaten aktif seans olabilir).");
  };

  // Manuel "Durdur": aktif seansı durdur (timer/not/history) + seçili bobinleri sıfırla.
  const handleStopManual = async () => {
    if (isActive) await stopSession().catch(() => {});
    const stmCoils = Array.from(selectedCoils).filter((id) => id <= 5);
    const espCoils = Array.from(selectedCoils).filter((id) => id >= 6);
    // #74: durdurma yanıtlarını DOĞRULA — apiPost hata/timeout'ta null döner (throw etmez); eskiden
    // yanıt yutuluyordu → STOP düşse bile kullanıcı bobinin durduğunu sanıyordu (per-coil panelle tutarsız).
    let allOk = true;
    if (stmCoils.length > 0) {
      const r = await apiPost<{ status?: string } | null>("/coil/batch", {
        coil_ids: stmCoils, freq: 0, duty: 0, phase: 0, duration: 0, start: false,
      }, null);
      if (!r || r.status === "error") allOk = false;
    }
    for (const coilId of espCoils) {
      const r = await apiPost<{ status?: string } | null>(`/coil/${coilId}/control`, {
        freq: 0, duty: 0, phase: 0, duration: 0, start: false,
      }, null);
      if (!r || r.status === "error") allOk = false;
    }
    if (!allOk && (stmCoils.length > 0 || espCoils.length > 0)) {
      platformAlert(
        "Durdurma onaylanamadı",
        "Bir veya daha fazla bobinin durduğu teyit edilemedi — bobinler HÂLÂ ÇALIŞIYOR olabilir. ACİL DURDUR'a basın.",
      );
    }
  };

  const handleAiAnalyze = async () => {
    setAiAnalyzing(true);
    setAiResult(null);
    try {
      // apiPost ASLA throw etmez: hata/timeout'ta fallback döner. Bu yüzden fallback olarak
      // bir sentinel hata nesnesi veriyoruz (null değil) → başarısızlıkta da kart görünür.
      // silent:true → apiClient'ın jenerik pop-up'ı yerine aiResult.error kartını gösteriyoruz.
      // (AI Pro biofeedback CPU'yu doyurup isteği yavaşlatsa/başarısız etse bile net geri bildirim.)
      const rec = await apiPost<any>(
        "/hardware/auto_preset",
        { target_condition: aiTarget },
        { error: "AI analizi başarısız — sunucuya ulaşılamadı veya zaman aşımı (AI Pro çalışıyorsa tekrar deneyin)." },
        { silent: true },
      );
      if (rec?.parameters) {
        setAiResult(rec);
        setAutoFreq(String(rec.parameters.freq ?? 50));
        setAutoDuty(String(rec.parameters.duty ?? 25));
        setAutoDuration(String(Math.round(rec.parameters.duration ?? 20)));
      } else {
        // Boş/parametresiz yanıt da sessiz kalmasın → net uyarı göster.
        setAiResult(rec?.error ? rec : { error: "AI analizi sonuç döndürmedi. Lütfen tekrar deneyin." });
      }
    } catch {
      setAiResult({ error: "AI analizi başarısız" });
    } finally {
      setAiAnalyzing(false);
    }
  };

  const handleStartAi = async () => {
    if (!aiResult?.parameters) {
      platformAlert("Uyarı", "Önce AI analizi yapın.");
      return;
    }
    const effective = resolveEffectiveCoils();
    if (!effective) return;
    const src = aiResult.parameters;
    const p = clampWithAlert({
      freq: src.freq ?? 50,
      duty: src.duty ?? 25,
      // ORTA fix: AI-önerilen intensity'yi kullan; GÖRÜNMEYEN Otomatik-sekme autoIntensity'sini DEĞİL
      // (AI sekmesinde yoğunluk alanı yok → kullanıcı görmeden başka sekmenin değeriyle başlıyordu).
      intensity: src.intensity ?? 1.0,
      duration: Math.round(src.duration ?? 20),
    });
    const ok = await startSession({
      patientId: selectedPatient?.id,
      patientName,
      mode: "AI",
      targetCondition: aiTarget,
      frequency: p.freq,
      duty: p.duty,
      intensity: p.intensity,
      durationMinutes: p.duration,
      coilIds: effective,
      operatorEmail: session?.email,
    });
    if (!ok) platformAlert("Hata", error ?? "Seans başlatılamadı.");
  };

  // ── Seans-sonrası gözlem notu prompt'u (PyQt observation-notes) ──
  type ObsSess = { patientName?: string; mode?: string; frequency?: number; intensity?: number; durationMinutes?: number };
  const [obsSession, setObsSession] = useState<ObsSess | null>(null);
  const lastSessionRef = useRef<ObsSess | null>(null);
  const prevActiveRef = useRef(isActive);

  useEffect(() => {
    if (isActive && treatment) {
      lastSessionRef.current = {
        patientName,
        mode: treatment.mode,
        frequency: treatment.frequencyHz,
        intensity: treatment.intensityMt,
        durationMinutes: Math.round((treatment.durationSec ?? 0) / 60),
      };
    }
  }, [isActive, treatment, patientName]);

  useEffect(() => {
    if (prevActiveRef.current && !isActive && lastSessionRef.current) {
      setObsSession(lastSessionRef.current);
    }
    prevActiveRef.current = isActive;
  }, [isActive]);

  // ─── Render ───────────────────────────────────────────────────────────────
  const coils = snapshot.coils ?? [];

  return (
    <View style={styles.container}>
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
        stale={isActive && telemetryStale}
      />

      {/* ── Tab bar ───────────────────────────────────────────── */}
      <View style={styles.tabBar}>
        {TABS.map((tab) => (
          <TouchableOpacity
            key={tab.key}
            style={[styles.tab, activeTab === tab.key && styles.tabActive]}
            onPress={() => setActiveTab(tab.key)}
            accessibilityRole="tab"
            accessibilityState={{ selected: activeTab === tab.key }}
            accessibilityLabel={tab.label}
          >
            <Text style={styles.tabIcon}>{tab.icon}</Text>
            <Text style={[styles.tabLabel, activeTab === tab.key && styles.tabLabelActive]} numberOfLines={1} adjustsFontSizeToFit>
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
                onPress={() => applyAutoPreset(t)}
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
            <ParamField label="Yoğunluk (mT)" value={autoIntensity} onChangeText={setAutoIntensity} />
            <ParamField label="Süre (dk)" value={autoDuration} onChangeText={setAutoDuration} />
          </View>
          {autoLoading && <Text style={styles.hint}>Literatür önerisi alınıyor…</Text>}

          <CoilSelector coils={coils} selected={selectedCoils} onToggle={toggleCoil} stmConnected={isStmConnected} />

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
              <ParamField label="Faz (°)" value={masterPhase} onChangeText={setMasterPhase} />
              <ParamField label="Süre (dk)" value={masterDuration} onChangeText={setMasterDuration} />
            </View>
            <CoilSelector coils={coils} selected={selectedCoils} onToggle={toggleCoil} stmConnected={isStmConnected} />
            <View style={styles.manualBtnRow}>
              <View style={{ flex: 1 }}>
                <StartButton
                  label="▶ Başlat"
                  onPress={handleStartManual}
                  disabled={isActive || loading}
                />
              </View>
              <View style={{ flex: 1 }}>
                <StartButton
                  label="⏹ Durdur"
                  onPress={handleStopManual}
                  disabled={loading}
                  color="#ef4444"
                />
              </View>
            </View>
          </View>

          {/* STM32 Bobinler (1-5) */}
          <Text style={styles.subTitle}>🔌 STM32 Bobinler (1–5)</Text>
          <ResponsiveGrid minItemWidth={320}>
            {coils.filter(c => c.id <= 5).map((coil) => (
              <CoilParameterPanel
                key={coil.id}
                coilId={coil.id}
                connected={isCoilConnected(coil)}
                running={coil.running}
                objectTemp={coil.objectTemp}
                frequencyHz={coil.frequencyHz}
                dutyCycle={coil.dutyCycle}
                magneticMt={coil.magneticMt}
                currentA={coil.currentA}
                defaultFreq={parseFloat(masterFreq) || 100}
                defaultDuty={parseFloat(masterDuty) || 25}
                defaultPhase={parseFloat(masterPhase) || 0}
                defaultDuration={parseDurationMin(masterDuration)}
                stm32Driven={true}
                stmConnected={isStmConnected}
                disabled={isActive}
              />
            ))}
          </ResponsiveGrid>

          {/* ESP Bobinler (6-8) */}
          <Text style={styles.subTitle}>📶 WiFi ESP Bobinler (6–8)</Text>
          <ResponsiveGrid minItemWidth={320}>
            {coils.filter(c => c.id >= 6).map((coil) => (
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
                defaultPhase={parseFloat(masterPhase) || 0}
                defaultDuration={parseDurationMin(masterDuration)}
                stm32Driven={false}
                stmConnected={false}
                disabled={isActive}
              />
            ))}
          </ResponsiveGrid>
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

          <CoilSelector coils={coils} selected={selectedCoils} onToggle={toggleCoil} stmConnected={isStmConnected} />

          <StartButton
            label="🧠 AI Seansını Başlat"
            onPress={handleStartAi}
            disabled={isActive || loading || !aiResult?.parameters}
            color="#7c3aed"
          />
        </View>
      )}

      {/* ── TAB: AI Pro ───────────────────────────────────────── */}
      {activeTab === "aipro" && (
        <View style={styles.section}>
          <SectionTitle text="AI Pro — Kamera Kapalı-Döngü" />
          <AiProPanel />
        </View>
      )}

      {/* ── Emergency Stop (always visible) ──────────────────── */}
      <TouchableOpacity style={styles.emergencyBtn} onPress={emergencyStop}
        accessibilityRole="button"
        accessibilityLabel="Tüm bobinleri acil durdur"
        accessibilityHint="Tüm bobinleri anında durdurur ve aktif tedaviyi sonlandırır">
        <Text style={styles.emergencyBtnText} numberOfLines={2} adjustsFontSizeToFit>🚨 TÜM BOBİNLERİ ACİL DURDUR</Text>
      </TouchableOpacity>

      <ObservationNotesModal
        visible={obsSession !== null}
        session={obsSession}
        onClose={() => setObsSession(null)}
      />
    </View>
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
        accessibilityLabel={label}
      />
    </View>
  );
}

function CoilSelector({
  coils, selected, onToggle, stmConnected,
}: {
  coils: CoilStatus[];
  selected: Set<number>;
  onToggle: (id: number) => void;
  stmConnected: boolean;
}) {
  return (
    <View style={styles.coilSelector}>
      <Text style={styles.formLabel}>Bobin Seçimi</Text>
      <View style={styles.coilSelectorGrid}>
        {(coils.length > 0 ? coils : Array.from({ length: 8 }, (_, i) => ({ id: i + 1, connected: false }))).map((c) => {
          const connected = c.id <= 5 ? stmConnected : Boolean(c.connected);
          return (
            <TouchableOpacity
              key={c.id}
              style={[
                styles.coilSelectorBtn,
                selected.has(c.id) && styles.coilSelectorBtnActive,
                !connected && styles.coilSelectorBtnOffline,
              ]}
              onPress={() => onToggle(c.id)}
              hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
              accessibilityRole="button"
              accessibilityState={{ selected: selected.has(c.id) }}
              accessibilityLabel={`Bobin ${c.id}, ${selected.has(c.id) ? "seçili" : "seçili değil"}, ${connected ? "çevrimiçi" : "çevrimdışı"}`}
            >
              <Text style={[styles.coilSelectorText, selected.has(c.id) && styles.coilSelectorTextActive]}>
                {c.id}
              </Text>
            </TouchableOpacity>
          );
        })}
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
      <Text style={styles.startBtnText} numberOfLines={2}>{label}</Text>
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
    width: "100%",
    maxWidth: rs(1100),
    alignSelf: "center",
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
  tabIcon: { fontSize: rf(18) },
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
    lineHeight: rf(20),
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

  paramRow: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" },
  paramField: { flex: 1, minWidth: rs(140) },
  paramFieldLabel: { color: colors.textMuted, fontSize: rf(11), fontWeight: "600", marginBottom: 4 },
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
    width: rs(40),
    height: rs(40),
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
  manualBtnRow: { flexDirection: "row", gap: spacing.sm },
  startBtnText: { color: "#fff", fontWeight: "800", fontSize: typography.body, textAlign: "center", alignSelf: "stretch" },

  btnAnalyze: {
    backgroundColor: "#6d28d9",
    borderRadius: 12,
    padding: spacing.md,
    alignItems: "center",
  },
  btnAnalyzeText: { color: "#fff", fontWeight: "700", fontSize: typography.body, textAlign: "center", alignSelf: "stretch" },

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
  statChipLabel: { color: colors.textMuted, fontSize: rf(10), fontWeight: "700" },
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
  emergencyBtnText: { color: "#fff", fontWeight: "800", fontSize: typography.body, letterSpacing: 0.3, textAlign: "center", alignSelf: "stretch" },
});
