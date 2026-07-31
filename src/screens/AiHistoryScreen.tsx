import { useEffect, useState, useCallback, useMemo } from "react";
import { StyleSheet, Text, View, TouchableOpacity, ScrollView, ActivityIndicator } from "react-native";
import { Card } from "@/components/ui/Card";
import { colors, spacing, typography, radius, rf, rs } from "@/theme/tokens";
import { apiGet } from "@/services/apiClient";
import { useAuth } from "@/context/AuthContext";
import { detailRows, INPUT_LABELS } from "@/utils/aiDetail";
import { Brain, ChevronDown, ChevronRight, RefreshCcw } from "lucide-react-native";

/** Şifreli ai_analyses tablosundan bir kayıt (backend get_ai_log). result_detail = tam ham sonuç. */
interface AiAnalysis {
  id: number;
  created_at: string;
  mode: string;
  module_id: string;
  module_label: string;
  patient_name: string;
  operator_email: string;  // analizi yapan hekim (klinik-içi "Benim/Tüm Klinik" filtresi)
  input_type: string;
  result_summary: string;
  result_detail: unknown;
  confidence: number | null;
}

const MODE_LABEL: Record<string, string> = {
  pet_owner: "Evcil Sahibi",
  veterinarian: "Veteriner",
  researcher: "Araştırma",
};
const AI_HISTORY_LIMIT = 300; // sayfa başına çekilen maks. kayıt (backend before_id keyset-pagination'a hazır)

function fmtDate(iso: unknown): string {
  // YÜKSEK fix: created_at her zaman ISO string OLMAYABİLİR (backend epoch/number dönebilir). Ham `.replace`
  // çağrısı string olmayan değerde TypeError fırlatıp TÜM sekmeyi ErrorBoundary'e düşürüyordu. Güvenli çöz:
  if (iso == null || iso === "") return "";
  if (typeof iso === "number" || /^\d+$/.test(String(iso))) {
    const n = Number(iso);
    const d = new Date(n < 1e12 ? n * 1000 : n); // 10-haneli epoch = saniye → ms
    if (!isNaN(d.getTime())) {
      const p = (x: number) => String(x).padStart(2, "0");
      return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
    }
  }
  return String(iso).replace("T", " ").slice(0, 16);
}

export function AiHistoryScreen() {
  const [items, setItems] = useState<AiAnalysis[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [filter, setFilter] = useState<string>("__all__");
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const { session } = useAuth();
  const myEmail = (session?.email || "").toLowerCase();
  // Klinik-içi: "mine" = benim yaptığım analizler (+ sahipsiz eski), "all" = tüm klinik.
  const [scope, setScope] = useState<"mine" | "all">("mine");

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    const res = await apiGet<{ status: string; data: AiAnalysis[] }>(
      `/ai/log?limit=${AI_HISTORY_LIMIT}`,
      { status: "error", data: [] }
    );
    if (res.status === "success") {
      const data = Array.isArray(res.data) ? res.data : [];
      setItems(data);
      setHasMore(data.length === AI_HISTORY_LIMIT); // tam sayfa → daha fazlası olabilir
    } else setError(true);
    setLoading(false);
  }, []);

  // ORTA fix: before_id keyset ile "Daha Fazla Yükle" → 300'den fazla AI analizi olan (araştırma) kullanıcının
  // ESKİ kayıtları artık erişilebilir (eskiden ilk 300'de takılıydı; filtre çipleri de eksik üretiliyordu).
  const loadMore = useCallback(async () => {
    if (loadingMore || !hasMore || items.length === 0) return;
    setLoadingMore(true);
    const beforeId = items[items.length - 1]?.id;
    const res = await apiGet<{ status: string; data: AiAnalysis[] }>(
      `/ai/log?limit=${AI_HISTORY_LIMIT}&before_id=${beforeId}`,
      { status: "error", data: [] }
    );
    if (res.status === "success") {
      const data = Array.isArray(res.data) ? res.data : [];
      setItems((prev) => [...prev, ...data]);
      setHasMore(data.length === AI_HISTORY_LIMIT);
    }
    setLoadingMore(false);
  }, [loadingMore, hasMore, items]);

  useEffect(() => {
    load();
  }, [load]);

  // Filtre çipleri için benzersiz modül-etiketleri (yüklü kayıtlardan).
  const modules = useMemo(() => {
    const seen = new Set<string>();
    for (const it of items) {
      const lbl = it.module_label || it.module_id;
      if (lbl) seen.add(lbl);
    }
    return Array.from(seen);
  }, [items]);

  const shown = useMemo(
    () => items.filter((it) => {
      // "Benim" = operator_email eşleşen VEYA sahipsiz (eski) → hiçbir analiz kaybolmaz.
      if (scope === "mine" && myEmail) {
        const op = (it.operator_email || "").toLowerCase();
        if (op && op !== myEmail) return false;
      }
      return filter === "__all__" || (it.module_label || it.module_id) === filter;
    }),
    [items, filter, scope, myEmail]
  );

  return (
    <View style={styles.container}>
      <View style={styles.headerRow}>
        <Text style={styles.count}>{shown.length} kayıt{filter !== "__all__" ? " (filtreli)" : ""}</Text>
        <TouchableOpacity style={styles.refreshBtn} onPress={load} accessibilityRole="button" accessibilityLabel="Geçmişi yenile">
          <RefreshCcw color={colors.primary} size={16} />
          <Text style={styles.refreshText}>Yenile</Text>
        </TouchableOpacity>
      </View>

      {myEmail ? (
        <View style={styles.segment}>
          <TouchableOpacity style={[styles.segmentBtn, scope === "mine" && styles.segmentBtnActive]} onPress={() => setScope("mine")} accessibilityLabel="Benim analizlerim">
            <Text style={[styles.segmentText, scope === "mine" && styles.segmentTextActive]} numberOfLines={1}>Benim Analizlerim</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[styles.segmentBtn, scope === "all" && styles.segmentBtnActive]} onPress={() => setScope("all")} accessibilityLabel="Tüm klinik analizleri">
            <Text style={[styles.segmentText, scope === "all" && styles.segmentTextActive]} numberOfLines={1}>Tüm Klinik</Text>
          </TouchableOpacity>
        </View>
      ) : null}

      {modules.length > 0 && (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipsRow}>
          <Chip label="Tümü" active={filter === "__all__"} onPress={() => setFilter("__all__")} />
          {modules.map((m) => (
            <Chip key={m} label={m} active={filter === m} onPress={() => setFilter(m)} />
          ))}
        </ScrollView>
      )}

      {loading ? (
        <ActivityIndicator size="large" color={colors.primary} style={{ marginTop: spacing.xxl }} />
      ) : error ? (
        <Text style={styles.empty}>Geçmiş yüklenemedi. Cihaza bağlı olduğunuzdan emin olun, sonra Yenile'ye dokunun.</Text>
      ) : shown.length === 0 ? (
        <Text style={styles.empty}>
          {filter !== "__all__"
            ? 'Bu filtre için kayıt yok. Farklı bir modül seçin ya da "Tümü"ye dönün.'
            : "Henüz AI analiz kaydı yok. Akıllı Teşhis'ten bir analiz çalıştırın — sonuç burada şifreli, detaylı saklanır."}
        </Text>
      ) : (
        <ScrollView contentContainerStyle={styles.list}>
          {shown.map((it) => {
            const open = expanded === it.id;
            const rows = open ? detailRows(it.result_detail) : [];
            return (
              <TouchableOpacity key={it.id} activeOpacity={0.85} onPress={() => setExpanded(open ? null : it.id)}>
                <Card style={styles.card}>
                  <View style={styles.cardHead}>
                    <Brain color={colors.primary} size={18} />
                    <Text style={styles.module} numberOfLines={1}>{it.module_label || it.module_id || "AI"}</Text>
                    {open ? <ChevronDown color={colors.textMuted} size={16} /> : <ChevronRight color={colors.textMuted} size={16} />}
                  </View>

                  {it.result_summary ? <Text style={styles.summary}>{it.result_summary}</Text> : null}

                  <View style={styles.metaRow}>
                    <Text style={styles.meta}>{fmtDate(it.created_at)}</Text>
                    {it.patient_name ? <Text style={styles.meta} numberOfLines={1}>· {it.patient_name}</Text> : null}
                    {it.mode ? <Text style={styles.badge}>{MODE_LABEL[it.mode] || it.mode}</Text> : null}
                  </View>

                  {open ? (
                    <View style={styles.detail}>
                      {it.input_type ? <Text style={styles.detailLine}>Girdi tipi: {INPUT_LABELS[it.input_type] || it.input_type}</Text> : null}
                      {it.confidence != null ? (
                        <Text style={styles.detailLine}>Güven: %{Math.round(it.confidence * 100)}</Text>
                      ) : null}
                      {rows.length > 0 ? (
                        <View style={styles.detailGrid}>
                          {rows.map((r, i) => (
                            <View key={i} style={styles.detailRow}>
                              <Text style={styles.detailKey}>{r.label}</Text>
                              <Text style={styles.detailValue} selectable>{r.value}</Text>
                            </View>
                          ))}
                        </View>
                      ) : (
                        <Text style={styles.detailLine}>Bu analiz için ek sayısal detay yok.</Text>
                      )}
                    </View>
                  ) : null}
                </Card>
              </TouchableOpacity>
            );
          })}
          {hasMore && (
            <TouchableOpacity
              style={{ marginTop: spacing.md, paddingVertical: spacing.md, alignItems: "center", borderRadius: radius.md, borderWidth: 1, borderColor: colors.border }}
              onPress={loadMore}
              disabled={loadingMore}
              accessibilityRole="button"
              accessibilityLabel="Daha fazla AI analizi yükle"
            >
              {loadingMore ? <ActivityIndicator color={colors.primary} /> : <Text style={{ color: colors.primary, fontWeight: "700" }}>Daha Fazla Yükle</Text>}
            </TouchableOpacity>
          )}
        </ScrollView>
      )}
    </View>
  );
}

function Chip({ label, active, onPress }: { label: string; active: boolean; onPress: () => void }) {
  return (
    <TouchableOpacity
      style={[styles.chip, active && styles.chipActive]}
      onPress={onPress}
      accessibilityRole="button"
      accessibilityState={{ selected: active }}
      accessibilityLabel={`Filtre: ${label}`}
    >
      <Text style={[styles.chipText, active && styles.chipTextActive]} numberOfLines={1}>{label}</Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg, width: "100%", maxWidth: rs(1100), alignSelf: "center" },
  headerRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
    paddingBottom: spacing.sm,
  },
  count: { color: colors.textMuted, fontSize: typography.small, fontWeight: "600" },
  refreshBtn: { flexDirection: "row", alignItems: "center", gap: spacing.xs },
  refreshText: { color: colors.primary, fontSize: typography.small, fontWeight: "700" },
  segment: { flexDirection: "row", backgroundColor: colors.bgAlt, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: rs(4), gap: rs(4), marginHorizontal: spacing.lg, marginBottom: spacing.sm },
  segmentBtn: { flex: 1, paddingVertical: spacing.sm, borderRadius: radius.sm, alignItems: "center", justifyContent: "center" },
  segmentBtnActive: { backgroundColor: colors.primary },
  segmentText: { color: colors.textMuted, fontSize: typography.caption, fontWeight: "700" },
  segmentTextActive: { color: colors.white },
  chipsRow: { gap: spacing.sm, paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  chip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.bgAlt,
  },
  chipActive: { borderColor: colors.primary, backgroundColor: colors.primarySoft },
  chipText: { color: colors.textMuted, fontSize: typography.caption, fontWeight: "600", maxWidth: rf(160) },
  chipTextActive: { color: colors.primary },
  list: { padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xxl },
  card: { padding: spacing.md, gap: spacing.xs },
  cardHead: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  module: { flex: 1, color: colors.text, fontSize: typography.subtitle, fontWeight: "800" },
  summary: { color: colors.text, fontSize: typography.body },
  metaRow: { flexDirection: "row", alignItems: "center", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.xs },
  meta: { color: colors.textMuted, fontSize: typography.caption },
  badge: {
    color: colors.primary,
    fontSize: typography.caption,
    fontWeight: "700",
    backgroundColor: colors.primarySoft,
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
    borderRadius: radius.sm,
    overflow: "hidden",
  },
  detail: { marginTop: spacing.sm, gap: spacing.xs, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: spacing.sm },
  detailLine: { color: colors.textSubtle, fontSize: typography.small },
  detailGrid: { marginTop: spacing.xs, gap: 2 },
  detailRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-start",
    gap: spacing.md,
    paddingVertical: 3,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  detailKey: { color: colors.textMuted, fontSize: typography.small, flexShrink: 0 },
  detailValue: { color: colors.text, fontSize: typography.small, fontWeight: "600", flex: 1, textAlign: "right" },
  empty: { color: colors.textMuted, fontSize: typography.body, textAlign: "center", padding: spacing.xxl, lineHeight: rf(22) },
});
