// Author: mertaygn, cglrgrkn
/**
 * SessionDetailModal — Geçmiş seans BOBİN-DETAYI görünümü (Aşama-3).
 * ==================================================================================
 * Geçmiş ekranında bir seansa dokununca açılır. Backend'den
 * GET /api/history/{session_id}/details çekerek:
 *   - Seans özeti (tarih, saat, süre, mod, hasta, operatör, durum)
 *   - BOBİN-ÇALIŞMALARI tablosu (hangi bobin, parametre, saat, süre, sıcaklık özeti)
 *   - Bobin-başına SICAKLIK grafiği (sensor_samples → coil_id'ye göre çizgi)
 * gösterir.
 *
 * NOT: STM bobinleri (1-5) gerçek donanımda sıcaklık/akım/alan SENSÖRÜ içermez;
 * bu değerler 0/boş olabilir — yanıltıcı 0 göstermemek için bilgi notu eklenir.
 */
import { useEffect, useState } from "react";
import {
  Modal,
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  ActivityIndicator,
} from "react-native";
import Svg, { Line, Polyline, Rect, Text as SvgText } from "react-native-svg";
import { colors, spacing, typography, rs, layoutMax } from "@/theme/tokens";
import { apiGet } from "@/services/apiClient";

// Grafik/tablo renkleriyle BİREBİR aynı kategorik palet (RealtimeChart COIL_COLORS).
const COIL_COLORS = [
  "#EF4444", "#3B82F6", "#22C55E", "#F97316",
  "#A855F7", "#06B6D4", "#EC4899", "#EAB308",
];

const STATUS_LABELS_TR: Record<string, string> = {
  completed: "Tamamlandı",
  active: "Aktif",
  running: "Çalışıyor",
  in_progress: "Devam Ediyor",
  pending: "Bekliyor",
  stopped: "Durduruldu",
  interrupted: "Kesintiye Uğradı",
  aborted_recovered: "Kurtarıldı",
  cancelled: "İptal Edildi",
  canceled: "İptal Edildi",
  error: "Hata",
  failed: "Başarısız",
  success: "Başarılı",
};

function statusLabelTr(status?: string): string {
  if (!status) return "Bilinmiyor";
  const key = status.toLowerCase();
  if (STATUS_LABELS_TR[key]) return STATUS_LABELS_TR[key];
  return status.charAt(0).toUpperCase() + status.slice(1);
}

// ─── Backend sözleşmesi tipleri ───────────────────────────────────────────────
interface SessionInfo {
  id?: string | number;
  session_date?: string;
  start_time?: string;
  end_time?: string;
  duration_minutes?: number;
  started_epoch?: number;
  ended_epoch?: number;
  treatment_mode?: string;
  target_condition?: string;
  operator_name?: string;
  patient_name?: string;
  patient_notes?: string;
  session_status?: string;
}

interface CoilRunSummary {
  sample_count?: number;
  temp_min?: number;
  temp_max?: number;
  temp_avg?: number;
  current_avg?: number;
  field_avg?: number;
}

interface CoilRun {
  coil_id?: number;
  hw_type?: string;
  started_epoch?: number;
  ended_epoch?: number;
  duration_seconds?: number;
  frequency_hz?: number;
  duty_percent?: number;
  phase?: number;
  intensity_mt?: number;
  summary?: CoilRunSummary | null;
}

interface SensorSample {
  coil_id?: number;
  sample_ts?: number;
  temperature_c?: number;
  ambient_temp_c?: number;
  current_a?: number;
  magnetic_field_mt?: number;
  coil_run_id?: number | string;
  sample_count?: number;
}

interface SessionDetails {
  session?: SessionInfo | null;
  coil_runs?: CoilRun[] | null;
  sensor_samples?: SensorSample[] | null;
}

// ─── Yardımcılar ──────────────────────────────────────────────────────────────
function fmtClock(epoch?: number): string {
  if (!epoch || !Number.isFinite(epoch)) return "—";
  try {
    return new Date(epoch * 1000).toLocaleTimeString("tr-TR", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return "—";
  }
}

function fmtDuration(seconds?: number): string {
  if (!seconds || !Number.isFinite(seconds) || seconds <= 0) return "—";
  const total = Math.round(seconds);
  const m = Math.floor(total / 60);
  const s = total % 60;
  if (m > 0) return `${m}dk ${s}sn`;
  return `${s}sn`;
}

function fmtNum(v?: number, digits = 1): string {
  if (v === undefined || v === null || !Number.isFinite(v)) return "—";
  return v.toFixed(digits);
}

function hwLabel(hw?: string): string {
  const t = (hw || "").toLowerCase();
  if (t === "stm") return "STM";
  if (t === "esp") return "ESP";
  return hw ? hw.toUpperCase() : "—";
}

/**
 * [S6 adım 6 / ilkel-18] TABLO HÜCRESİ sözleşmesi: tek satır + sistem yazı ölçeği 1,1 tavanı.
 * Sabit sütun genişliklerinde ölçek 1,3'te "Başlangıç"/"12:04:31" iki satıra bölünüp başlık ile
 * hücre hizası kayıyordu (yanlış sütunda okuma riski). Yatay kaydırma zaten var.
 */
const BASLIK_HUCRE = { numberOfLines: 1 as const, maxFontSizeMultiplier: 1.1 };
const VERI_HUCRE = { ...BASLIK_HUCRE, adjustsFontSizeToFit: true, minimumFontScale: 0.75 };

export function SessionDetailModal({
  visible,
  sessionId,
  onClose,
}: {
  visible: boolean;
  sessionId: string | number | null;
  onClose: () => void;
}) {
  const [loading, setLoading] = useState(false);
  const [details, setDetails] = useState<SessionDetails | null>(null);

  useEffect(() => {
    if (!visible || sessionId === null || sessionId === undefined) return;
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setDetails(null);
      const data = await apiGet<SessionDetails | null>(
        `/history/${sessionId}/details`,
        null
      );
      if (!cancelled) {
        setDetails(data);
        setLoading(false);
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [visible, sessionId]);

  // ORTA fix (yanlış-hasta flash): sessionId değişince effect setDetails(null)'ı fetch ÖNCESİ değil
  // render-SONRASI yaptığından, bir render ESKİ seansın (başka hastanın) adı/notunu çizebiliyordu.
  // Yalnız yüklenen detay GÜNCEL sessionId'ye aitse göster (session.id eşleşmesi); stale ise null →
  // render yükleniyor/boş gösterir, başka hastanın PII'si SIZMAZ.
  const rawSession = details?.session ?? null;
  const isCurrent = rawSession != null && String(rawSession.id) === String(sessionId);
  const session = isCurrent ? rawSession : null;
  const coilRuns = isCurrent ? (details?.coil_runs ?? []) : [];
  const sensorSamples = isCurrent ? (details?.sensor_samples ?? []) : [];

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={styles.backdrop}>
        <View style={styles.card}>
          {/* Başlık + Kapat */}
          <View style={styles.headerRow}>
            <Text style={styles.title} numberOfLines={1}>
              Seans Detayı
            </Text>
            <TouchableOpacity style={styles.closeBtn} onPress={onClose} accessibilityLabel="Kapat">
              <Text style={styles.closeBtnText}>Kapat</Text>
            </TouchableOpacity>
          </View>

          {loading ? (
            <View style={styles.centerBox}>
              <ActivityIndicator size="large" color={colors.primary} />
              <Text style={styles.mutedText}>Detaylar yükleniyor…</Text>
            </View>
          ) : details === null ? (
            <View style={styles.centerBox}>
              <Text style={styles.mutedText}>Seans detayları yüklenemedi.</Text>
            </View>
          ) : (
            <ScrollView contentContainerStyle={styles.scrollBody}>
              <SummarySection session={session} />
              <CoilRunsSection coilRuns={coilRuns} />
              <TemperatureSection samples={sensorSamples} />
            </ScrollView>
          )}
        </View>
      </View>
    </Modal>
  );
}

// ─── Seans özeti ──────────────────────────────────────────────────────────────
function SummarySection({ session }: { session: SessionInfo | null }) {
  if (!session) {
    return <Text style={styles.mutedText}>Seans bilgisi yok.</Text>;
  }
  const timeRange =
    session.start_time || session.end_time
      ? `${session.start_time || "—"} – ${session.end_time || "—"}`
      : "—";
  return (
    <View style={styles.section}>
      <Text style={styles.patientName}>{session.patient_name || "Bilinmeyen Hasta"}</Text>
      <View style={styles.summaryGrid}>
        <SummaryItem label="Tarih" value={session.session_date || "—"} />
        <SummaryItem label="Saat" value={timeRange} />
        <SummaryItem
          label="Süre"
          value={session.duration_minutes ? `${session.duration_minutes} dk` : "—"}
        />
        <SummaryItem label="Mod" value={session.treatment_mode || "—"} />
        <SummaryItem label="Hedef" value={session.target_condition || "—"} />
        <SummaryItem label="Operatör" value={session.operator_name || "—"} />
        <SummaryItem label="Durum" value={statusLabelTr(session.session_status)} />
      </View>
      {session.patient_notes ? (
        <View style={styles.notesBox}>
          <Text style={styles.itemLabel}>Notlar</Text>
          <Text style={styles.notesText}>{session.patient_notes}</Text>
        </View>
      ) : null}
    </View>
  );
}

function SummaryItem({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.summaryItem}>
      <Text style={styles.itemLabel}>{label}</Text>
      <Text style={styles.itemValue} numberOfLines={2}>
        {value}
      </Text>
    </View>
  );
}

// ─── Bobin çalışmaları tablosu ────────────────────────────────────────────────
function CoilRunsSection({ coilRuns }: { coilRuns: CoilRun[] }) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>Bobin Çalışmaları</Text>
      {coilRuns.length === 0 ? (
        <Text style={styles.mutedText}>Bu seansta bobin çalışma kaydı yok.</Text>
      ) : (
        <ScrollView horizontal showsHorizontalScrollIndicator>
          <View>
            {/* Tablo başlığı */}
            <View style={[styles.tableRow, styles.tableHeaderRow]}>
              <Text style={[styles.th, styles.colCoil]} {...BASLIK_HUCRE}>Bobin</Text>
              <Text style={[styles.th, styles.colTime]} {...BASLIK_HUCRE}>Başlangıç</Text>
              <Text style={[styles.th, styles.colDur]} {...BASLIK_HUCRE}>Süre</Text>
              <Text style={[styles.th, styles.colNum]} {...BASLIK_HUCRE}>Frekans</Text>
              <Text style={[styles.th, styles.colNum]} {...BASLIK_HUCRE}>Duty</Text>
              <Text style={[styles.th, styles.colNum]} {...BASLIK_HUCRE}>Şiddet</Text>
              <Text style={[styles.th, styles.colHw]} {...BASLIK_HUCRE}>Donanım</Text>
              <Text style={[styles.th, styles.colNum]} {...BASLIK_HUCRE}>Ort. °C</Text>
              <Text style={[styles.th, styles.colNum]} {...BASLIK_HUCRE}>Maks. °C</Text>
            </View>
            {coilRuns.map((run, idx) => {
              const coilId = run.coil_id ?? 0;
              const color = COIL_COLORS[(coilId - 1) % COIL_COLORS.length] || colors.textMuted;
              const summary = run.summary ?? null;
              return (
                <View
                  key={`${coilId}-${run.started_epoch ?? idx}`}
                  style={[styles.tableRow, idx % 2 === 1 && styles.tableRowAlt]}
                >
                  <View style={[styles.colCoil, styles.coilCell]}>
                    <View style={[styles.coilDot, { backgroundColor: color }]} />
                    <Text style={[styles.td, { color, fontWeight: "700" }]} {...VERI_HUCRE}>
                      Bobin {coilId || "—"}
                    </Text>
                  </View>
                  <Text style={[styles.td, styles.colTime]} {...VERI_HUCRE}>{fmtClock(run.started_epoch)}</Text>
                  <Text style={[styles.td, styles.colDur]} {...VERI_HUCRE}>{fmtDuration(run.duration_seconds)}</Text>
                  <Text style={[styles.td, styles.colNum]} {...VERI_HUCRE}>
                    {run.frequency_hz != null ? `${run.frequency_hz} Hz` : "—"}
                  </Text>
                  <Text style={[styles.td, styles.colNum]} {...VERI_HUCRE}>
                    {run.duty_percent != null ? `%${run.duty_percent}` : "—"}
                  </Text>
                  <Text style={[styles.td, styles.colNum]} {...VERI_HUCRE}>
                    {run.intensity_mt != null ? `${run.intensity_mt} mT` : "—"}
                  </Text>
                  <Text style={[styles.td, styles.colHw]} {...VERI_HUCRE}>{hwLabel(run.hw_type)}</Text>
                  <Text style={[styles.td, styles.colNum]} {...VERI_HUCRE}>
                    {summary ? `${fmtNum(summary.temp_avg)}` : "—"}
                  </Text>
                  <Text style={[styles.td, styles.colNum]} {...VERI_HUCRE}>
                    {summary ? `${fmtNum(summary.temp_max)}` : "—"}
                  </Text>
                </View>
              );
            })}
          </View>
        </ScrollView>
      )}
      <Text style={styles.hwNote}>
        Not: STM bobinleri (1-5) gerçek donanımda sıcaklık/akım/alan sensörü içermez; bu
        değerler boş (—) görünebilir.
      </Text>
    </View>
  );
}

// ─── Sıcaklık grafiği ─────────────────────────────────────────────────────────
function TemperatureSection({ samples }: { samples: SensorSample[] }) {
  // coil_id'ye göre grupla; her bobin için { ts, temp } noktaları (sample_ts ASC varsayımı).
  const byCoil = new Map<number, { ts: number; temp: number }[]>();
  let minTs = Infinity;
  for (const s of samples) {
    const coilId = s.coil_id;
    const ts = s.sample_ts;
    const temp = s.temperature_c;
    if (
      coilId === undefined ||
      ts === undefined ||
      !Number.isFinite(ts) ||
      temp === undefined ||
      !Number.isFinite(temp)
    ) {
      continue;
    }
    if (ts < minTs) minTs = ts;
    const arr = byCoil.get(coilId) ?? [];
    arr.push({ ts, temp });
    byCoil.set(coilId, arr);
  }

  const coilIds = Array.from(byCoil.keys()).sort((a, b) => a - b);
  const hasData = coilIds.some((id) => (byCoil.get(id)?.length ?? 0) >= 1);

  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>Sıcaklık Grafiği</Text>
      {!hasData ? (
        <Text style={styles.mutedText}>
          Bu seansta sensör verisi yok (gerçek STM bobinleri sıcaklık sensörü içermez).
        </Text>
      ) : (
        <>
          <TempChart byCoil={byCoil} coilIds={coilIds} minTs={minTs} />
          {/* Lejant */}
          <View style={styles.legendRow}>
            {coilIds.map((id) => {
              const color = COIL_COLORS[(id - 1) % COIL_COLORS.length] || colors.textMuted;
              return (
                <View key={id} style={styles.legendItem}>
                  <View style={[styles.legendDot, { backgroundColor: color }]} />
                  <Text style={styles.legendText}>Bobin {id}</Text>
                </View>
              );
            })}
          </View>
        </>
      )}
    </View>
  );
}

function TempChart({
  byCoil,
  coilIds,
  minTs,
}: {
  byCoil: Map<number, { ts: number; temp: number }[]>;
  coilIds: number[];
  minTs: number;
}) {
  /**
   * [S7 adım 1 / ekranC-3] GENİŞLİK ÖLÇÜLÜR, sabit DEĞİL.
   * Eski kod `viewBox="0 0 720 260"` ile çiziyor ve SVG'yi `width="100%"` ile geriyordu: 360 px'lik
   * telefonda tüm grafik 0,5 ölçekle küçülüyor, eksen yazıları 11 px yerine 5-6 px'e düşüp
   * okunmaz oluyordu. Artık viewBox = ölçülen px (1:1) → yazı boyutu gerçek px.
   */
  const [olculenW, setOlculenW] = useState(0);
  const width = olculenW;
  const height = rs(240);
  const dar = width < 420;
  const PAD = { top: 20, right: dar ? 12 : 20, bottom: 36, left: dar ? 36 : 48 };
  const plotW = Math.max(0, width - PAD.left - PAD.right);
  const plotH = Math.max(0, height - PAD.top - PAD.bottom);

  // Aralıkları topla (x = göreli dakika, y = °C).
  let tMin = Infinity;
  let tMax = -Infinity;
  let xMaxMin = 0; // en büyük göreli dakika
  for (const id of coilIds) {
    const pts = byCoil.get(id) ?? [];
    for (const p of pts) {
      if (p.temp < tMin) tMin = p.temp;
      if (p.temp > tMax) tMax = p.temp;
      const relMin = (p.ts - minTs) / 60;
      if (relMin > xMaxMin) xMaxMin = relMin;
    }
  }
  if (!Number.isFinite(tMin) || !Number.isFinite(tMax)) {
    tMin = 0;
    tMax = 1;
  }
  if (tMin === tMax) {
    tMin -= 1;
    tMax += 1;
  }
  const tRange = tMax - tMin || 1;
  const xRange = xMaxMin || 1;

  const xAt = (relMin: number) => PAD.left + (relMin / xRange) * plotW;
  const yAt = (temp: number) => PAD.top + plotH - ((temp - tMin) / tRange) * plotH;

  return (
    <View
      style={styles.chartWrap}
      testID="seans-sicaklik-grafigi"
      onLayout={(e) => {
        const w = Math.round(e.nativeEvent.layout.width);
        setOlculenW((eski) => (Math.abs(w - eski) < 1 ? eski : w));
      }}
    >
      {width <= 0 ? null : (
      <Svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        <Rect x={0} y={0} width={width} height={height} fill="#0a0f1e" />
        {/* Yatay grid + °C ekseni */}
        {Array.from({ length: 5 }, (_, i) => {
          const y = PAD.top + (plotH / 4) * i;
          return (
            <Line
              key={`h${i}`}
              x1={PAD.left}
              y1={y}
              x2={PAD.left + plotW}
              y2={y}
              stroke="#1e293b"
              strokeWidth={1}
            />
          );
        })}
        {Array.from({ length: 5 }, (_, i) => {
          const y = PAD.top + (plotH / 4) * i;
          const val = tMax - (tRange / 4) * i;
          return (
            <SvgText
              key={`yl${i}`}
              x={PAD.left - 6}
              y={y + 4}
              fill="#fb923c"
              fontSize={11}
              textAnchor="end"
            >
              {val.toFixed(1)}
            </SvgText>
          );
        })}
        <SvgText x={PAD.left - 6} y={PAD.top - 6} fill="#fb923c" fontSize={11} textAnchor="end">
          °C
        </SvgText>
        {/* X ekseni etiketleri (dakika) */}
        {Array.from({ length: 5 }, (_, i) => {
          const relMin = (xRange / 4) * i;
          const x = xAt(relMin);
          return (
            <SvgText
              key={`xl${i}`}
              x={x}
              y={PAD.top + plotH + 18}
              fill="#64748b"
              fontSize={10}
              textAnchor="middle"
            >
              {relMin.toFixed(0)}
            </SvgText>
          );
        })}
        <SvgText
          x={PAD.left + plotW / 2}
          y={height - 4}
          fill="#64748b"
          fontSize={10}
          textAnchor="middle"
        >
          Dakika
        </SvgText>
        {/* Çizgiler */}
        {coilIds.map((id) => {
          const pts = byCoil.get(id) ?? [];
          if (pts.length === 0) return null;
          const color = COIL_COLORS[(id - 1) % COIL_COLORS.length] || colors.textMuted;
          if (pts.length === 1) {
            const p = pts[0];
            return (
              <Rect
                key={id}
                x={xAt((p.ts - minTs) / 60) - 2}
                y={yAt(p.temp) - 2}
                width={4}
                height={4}
                fill={color}
              />
            );
          }
          const str = pts
            .map((p) => `${xAt((p.ts - minTs) / 60)},${yAt(p.temp)}`)
            .join(" ");
          return <Polyline key={id} points={str} fill="none" stroke={color} strokeWidth={1.5} />;
        })}
        <Rect
          x={PAD.left}
          y={PAD.top}
          width={plotW}
          height={plotH}
          fill="none"
          stroke="#334155"
          strokeWidth={1}
        />
      </Svg>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.6)",
    justifyContent: "center",
    alignItems: "center",
    padding: spacing.md,
  },
  card: {
    backgroundColor: "#0f172a",
    borderRadius: 16,
    borderWidth: 1,
    borderColor: "#1e3a5f",
    width: "100%",
    maxWidth: layoutMax.modal,
    maxHeight: "92%",
    padding: spacing.lg,
    gap: spacing.md,
  },
  headerRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: spacing.md,
  },
  title: { color: colors.text, fontSize: typography.subtitle, fontWeight: "800", flex: 1 },
  closeBtn: {
    borderWidth: 1,
    borderColor: colors.primary,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: 8,
  },
  closeBtnText: { color: colors.primary, fontWeight: "bold", fontSize: typography.small },
  centerBox: { alignItems: "center", gap: spacing.md, paddingVertical: spacing.xxl },
  mutedText: { color: colors.textMuted, fontSize: typography.body },
  scrollBody: { gap: spacing.lg, paddingBottom: spacing.md },

  section: { gap: spacing.sm },
  sectionTitle: { color: colors.text, fontSize: typography.body, fontWeight: "800" },
  patientName: { color: colors.text, fontSize: typography.subtitle, fontWeight: "800" },

  summaryGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  summaryItem: {
    backgroundColor: colors.bgAlt,
    borderRadius: 8,
    padding: spacing.md,
    minWidth: rs(120),
    flexGrow: 1,
    flexBasis: rs(120),
  },
  itemLabel: { color: colors.textMuted, fontSize: typography.small, fontWeight: "700" },
  itemValue: { color: colors.text, fontSize: typography.body, fontWeight: "700", marginTop: spacing.xs },

  notesBox: {
    backgroundColor: colors.bgAlt,
    borderRadius: 8,
    padding: spacing.md,
    marginTop: spacing.xs,
  },
  notesText: { color: colors.text, fontSize: typography.small, marginTop: spacing.xs, fontStyle: "italic" },

  // Tablo
  tableRow: { flexDirection: "row", alignItems: "center", paddingVertical: spacing.sm },
  tableHeaderRow: {
    borderBottomWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.bgAlt,
    borderTopLeftRadius: 8,
    borderTopRightRadius: 8,
  },
  tableRowAlt: { backgroundColor: "#131b2e" },
  th: {
    color: colors.textMuted,
    fontSize: typography.small,
    fontWeight: "800",
    paddingHorizontal: spacing.sm,
  },
  td: {
    color: colors.text,
    fontSize: typography.small,
    paddingHorizontal: spacing.sm,
  },
  coilCell: { flexDirection: "row", alignItems: "center", gap: spacing.xs, paddingHorizontal: spacing.sm },
  coilDot: { width: rs(8), height: rs(8), borderRadius: 4 },
  colCoil: { width: rs(96) },
  colTime: { width: rs(92) },
  colDur: { width: rs(90) },
  colNum: { width: rs(78) },
  colHw: { width: rs(70) },
  hwNote: {
    color: colors.textSubtle,
    fontSize: typography.small,
    fontStyle: "italic",
    marginTop: spacing.xs,
  },

  // Grafik
  chartWrap: { borderRadius: 8, overflow: "hidden", backgroundColor: "#0a0f1e" },
  legendRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md, marginTop: spacing.sm },
  legendItem: { flexDirection: "row", alignItems: "center", gap: spacing.xs },
  legendDot: { width: rs(10), height: rs(10), borderRadius: 5 },
  legendText: { color: colors.textMuted, fontSize: typography.small, fontWeight: "600" },
});
