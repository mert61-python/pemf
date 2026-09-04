// Author: mertaygn, cglrgrkn
import { useEffect, useState, useCallback, useMemo } from "react";
import { StyleSheet, Text, View, TouchableOpacity, ScrollView, ActivityIndicator } from "react-native";
import { Card } from "@/components/ui/Card";
import { colors, spacing, typography, radius, rf, rs, layoutMax, touch } from "@/theme/tokens";
import { Chip as OrtakChip } from "@/components/ui/Chip";
import { apiGet, apiPost, platformConfirm } from "@/services/apiClient";
import { useAuth } from "@/context/AuthContext";
import { detailRows, INPUT_LABELS } from "@/utils/aiDetail";
import { Brain, ChevronDown, ChevronRight, RefreshCcw, Trash2 } from "lucide-react-native";
import { AiReviewControls, ReviewBadge, type ReviewStatus } from "@/components/domain/AiReviewControls";
import { useUserMode } from "@/context/UserModeContext";
import { useOperatorOptional } from "@/context/OperatorContext";
import { canChooseScope, deleteScope, effectiveScope } from "@/utils/patientScope";

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
  // Hekim degerlendirmesi (2026-08-06): AI ciktisi ONERI, karar hekimin.
  review_status?: ReviewStatus;
  review_note?: string;
  reviewed_by?: string;
  reviewed_at?: string;
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
  const [hastaFiltre, setHastaFiltre] = useState<string>("__all__");
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const { session } = useAuth();
  // ⚠️ DENETİM 2026-08-09 (Tier 1) — KİMLİK `session.email` DEĞİL, AKTİF OPERATÖRDÜR.
  // Bir kliniği 3-4 veteriner TEK Supabase hesabıyla paylaşıyor; kayıtlar `operatorEmail` ile
  // yazılıyor ama bu ekran giriş e-postasını kullanıyordu. Sonuç: "kendi kayıtlarımı sil"
  // kimsenin kaydıyla eşleşmiyor AMA `operator_email` SAHİPSİZ kayıtları da kapsadığı için
  // (backend: `IS NULL OR = ''`) BAŞKA bir hekimin eski analizlerini siliyordu.
  // `operatorEmail` tek kaynaktır: aktif operatör, yoksa (kayıtlı operatör yokken) oturum e-postası.
  const op = useOperatorOptional();
  const myEmail = (op ? op.operatorEmail : (session?.email || "")).toLowerCase();
  // Klinik-içi: "mine" = benim yaptığım analizler (+ sahipsiz eski), "all" = tüm klinik.
  const [scope, setScope] = useState<"mine" | "all">("mine");
  // ⚠️ KVKK 2026-08-08: "Tüm Klinik" EV SAHİBİNE KAPALI — hasta ekranındaki kapının AYNISI.
  // Burada eksik kalmıştı: sekme yalnız `myEmail`e bağlıydı, PROFİLE değil → ev sahibi tıklayıp
  // kliniğin tüm AI analizlerini HASTA ADLARIYLA görebiliyordu. Kural utils/patientScope.ts'te
  // TEK yerde; iki ekran da onu kullanır ki bir daha ayrışmasın.
  const { isExpert, isResearcher } = useUserMode();
  const roller = { isExpert, isResearcher };
  const etkinScope = effectiveScope(scope, roller);
  // Hekim değerlendirmesi (2026-08-06): hangi kaydın kararı gönderiliyor.
  const [reviewing, setReviewing] = useState<number | null>(null);
  const [silinen, setSilinen] = useState<number | null>(null);

  /**
   * KVKK SİLME HAKKI (2026-08-08) — bugüne kadar AI geçmişini silmenin HİÇBİR yolu yoktu:
   * uygulamayı kaldırmak da silmiyor (tıbbi kayıt kasıtlı korunuyor), tek yol PowerShell script'iydi.
   *
   * KAPSAM KURALI: klinik profili (veteriner/araştırma) "Tüm Klinik"i silebilir; ev sahibi
   * YALNIZ kendi kayıtlarını — backend `operator_email` ile bunu ayrıca uygular.
   */
  // ⚠️ SİLME KAPSAMI TEK KAYNAKTAN (utils/patientScope.deleteScope). Bu denetimde bulunan arıza
  // tam olarak aynı kuralın ekranlarda ayrı ayrı yazılmasıydı; bir daha ayrışmasın.
  const silmeKapsami = deleteScope(scope, myEmail, roller);
  const kendiKapsami = !silmeKapsami.allOperators;
  const kimlikYok = !silmeKapsami.izinli;

  const kaydiSil = useCallback(async (id: number) => {
    if (kimlikYok) {
      await platformConfirm("Operatör seçin",
        "Silme işlemi için önce üst bardan hangi hekim olduğunuzu seçin.");
      return;
    }
    const onay = await platformConfirm(
      "Kaydı sil",
      "Bu AI analiz kaydı kalıcı olarak silinecek. Bu işlem geri alınamaz.",
    );
    if (!onay) return;
    setSilinen(id);
    const res = await apiPost<{ status?: string } | null>(
      "/ai/log/delete",
      { id, operator_email: silmeKapsami.operatorEmail },
      null,
    );
    setSilinen(null);
    if (!res) return;                                   // hata mesajını apiPost gösterdi
    setItems((prev) => prev.filter((x) => x.id !== id)); // yerinde çıkar (liste yerini kaybetmesin)
  }, [silmeKapsami, kimlikYok]);

  // ⚠️ `load` BURADA tanımlanır (aşağıda değil): `tumunuSil` onu kullanıyor ve bildirimden
  // ÖNCE erişim, React Compiler'ın tüm bileşende iyileştirmeyi bırakmasına yol açıyordu
  // (`react-hooks/immutability` + 6 adet `preserve-manual-memoization` hatası). Çalışma
  // anında zararsızdı (bağımlılıksız, kararlı) ama yakalanan referans bayat kalabilirdi.
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

  const tumunuSil = useCallback(async () => {
    if (kimlikYok) {
      await platformConfirm("Operatör seçin",
        "Silme işlemi için önce üst bardan hangi hekim olduğunuzu seçin.");
      return;
    }
    const kapsamMetni = kendiKapsami ? "Kendi AI analiz kayıtlarınızın TAMAMI" : "Kliniğin TÜM AI analiz geçmişi";
    const onay = await platformConfirm(
      "Geçmişi sil",
      `${kapsamMetni} kalıcı olarak silinecek. Bu işlem geri alınamaz.\n\nHasta kayıtları ve seans geçmişi ETKİLENMEZ.`,
    );
    if (!onay) return;
    const res = await apiPost<{ status?: string; deleted?: number } | null>(
      "/ai/log/delete_all",
      // `all_operators`: klinik-geneli silme NİYETİ açıkça bildirilir (2026-08-09 fail-closed
      // sözleşmesi). Kimliğin boş kalması artık "hepsini sil" anlamına GELMEZ.
      { confirm: "DELETE_ALL", operator_email: silmeKapsami.operatorEmail,
        all_operators: silmeKapsami.allOperators },
      null,
    );
    if (!res) return;
    await load();
  }, [silmeKapsami, kendiKapsami, kimlikYok]);   // eslint-disable-line react-hooks/exhaustive-deps

  /** Onay/red/düzeltme gönder. Başarılıysa kaydı YERİNDE güncelle — tüm listeyi yeniden
   *  çekmek açık kartı kapatır ve hekimin yerini kaybettirir. */
  const submitReview = useCallback(async (id: number, status: string, note: string) => {
    setReviewing(id);
    const res = await apiPost<{ status?: string } | null>(
      "/ai/log/review",
      // Değerlendirmeyi İMZALAYAN kişi de aktif operatördür (giriş hesabı değil) — aksi hâlde
      // "bu teşhisi kim onayladı" sorusunun cevabı klinikte hep aynı paylaşılan hesap olurdu.
      { analysis_id: id, status, note, reviewed_by: myEmail },
      null,
    );
    setReviewing(null);
    if (!res) return;   // apiPost hata mesajını zaten gösterdi; iyimser güncelleme YAPMA
    setItems((prev) => prev.map((x) => x.id === id
      ? { ...x, review_status: status as ReviewStatus, review_note: note,
          reviewed_by: myEmail, reviewed_at: new Date().toISOString() }
      : x));
  }, [session]);


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

  // HASTA FİLTRESİ (2026-08-07): "bu hastaya hangi AI modülü uygulandı, sonucu neydi?"
  // sorusunun cevabı tek dokunuşla görünsün. Liste yüklü kayıtlardan türetilir.
  const hastalar = useMemo(() => {
    const seen = new Set<string>();
    for (const it of items) if (it.patient_name) seen.add(it.patient_name);
    return Array.from(seen).sort((a, b) => a.localeCompare(b, "tr"));
  }, [items]);

  const shown = useMemo(
    () => items.filter((it) => {
      // "Benim" = operator_email eşleşen VEYA sahipsiz (eski) → hiçbir analiz kaybolmaz.
      if (etkinScope === "mine" && myEmail) {
        const op = (it.operator_email || "").toLowerCase();
        if (op && op !== myEmail) return false;
      }
      if (hastaFiltre !== "__all__" && (it.patient_name || "") !== hastaFiltre) return false;
      return filter === "__all__" || (it.module_label || it.module_id) === filter;
    }),
    [items, filter, hastaFiltre, etkinScope, myEmail]
  );

  return (
    <View style={styles.container}>
      <View style={styles.headerRow}>
        <Text style={styles.count}>{shown.length} kayıt{(filter !== "__all__" || hastaFiltre !== "__all__") ? " (filtreli)" : ""}</Text>
        <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
          {/* KVKK silme hakkı: kayıt yokken düğmeyi gösterme (ölü aksiyon). */}
          {items.length > 0 ? (
            <TouchableOpacity style={styles.refreshBtn} onPress={tumunuSil}
              accessibilityRole="button"
              accessibilityLabel={kendiKapsami ? "Kendi AI analiz geçmişimi sil" : "Kliniğin tüm AI analiz geçmişini sil"}>
              <Trash2 color={colors.danger} size={16} />
              <Text style={[styles.refreshText, { color: colors.danger }]}>Geçmişi Sil</Text>
            </TouchableOpacity>
          ) : null}
          <TouchableOpacity style={styles.refreshBtn} onPress={load} accessibilityRole="button" accessibilityLabel="Geçmişi yenile">
            <RefreshCcw color={colors.primary} size={16} />
            <Text style={styles.refreshText}>Yenile</Text>
          </TouchableOpacity>
        </View>
      </View>

      {canChooseScope(myEmail, roller) ? (
        <View style={styles.segment}>
          <TouchableOpacity style={[styles.segmentBtn, scope === "mine" && styles.segmentBtnActive]} onPress={() => setScope("mine")} accessibilityLabel="Benim analizlerim">
            <Text style={[styles.segmentText, scope === "mine" && styles.segmentTextActive]} numberOfLines={1}>Benim Analizlerim</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[styles.segmentBtn, scope === "all" && styles.segmentBtnActive]} onPress={() => setScope("all")} accessibilityLabel="Tüm klinik analizleri">
            <Text style={[styles.segmentText, scope === "all" && styles.segmentTextActive]} numberOfLines={1}>Tüm Klinik</Text>
          </TouchableOpacity>
        </View>
      ) : null}

      {/* HASTA çipleri (2026-08-07): hastaya göre süzülünce, altındaki modül çipleri ve kartlar
          "bu hastaya hangi modül uygulandı, sonucu neydi" sorusunu doğrudan cevaplar. */}
      {hastalar.length > 0 && (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipsRow}>
          <Chip label="Tüm hastalar" active={hastaFiltre === "__all__"} onPress={() => setHastaFiltre("__all__")} />
          {hastalar.map((h) => (
            <Chip key={h} label={h} active={hastaFiltre === h} onPress={() => setHastaFiltre(h)} />
          ))}
        </ScrollView>
      )}

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
        <Text style={styles.empty}>{"Geçmiş yüklenemedi. Cihaza bağlı olduğunuzdan emin olun, sonra Yenile'ye dokunun."}</Text>
      ) : shown.length === 0 ? (
        <Text style={styles.empty}>
          {filter !== "__all__"
            ? 'Bu filtre için kayıt yok. Farklı bir hasta/modül seçin ya da "Tümü"ye dönün.'
            : "Henüz AI analiz kaydı yok. Akıllı Teşhis'ten bir analiz çalıştırın — sonuç burada şifreli, detaylı saklanır."}
        </Text>
      ) : (
        <View style={styles.list}>
  {/* [S4 adım 3] İç dikey ScrollView KALDIRILDI: kabuk (AppShell) zaten tek kaydırıcı ve
  keyboardShouldPersistTaps='handled' taşıyor. İç ScrollView'ın yükseklik sınırı
  olmadığı için kendi kaydırmasını hiç üretmiyordu; ama klavye açıkken dokunuşu
  yutup 'Kaydet/Bağlan' düğmelerini İKİ dokunuş gerektiriyordu. */}
          {shown.map((it) => {
            const open = expanded === it.id;
            const rows = open ? detailRows(it.result_detail) : [];
            return (
              <TouchableOpacity key={it.id} activeOpacity={0.85} onPress={() => setExpanded(open ? null : it.id)}>
                <Card style={styles.card}>
                  <View style={styles.cardHead}>
                    <Brain color={colors.primary} size={18} />
                    <Text style={styles.module} numberOfLines={1}>{it.module_label || it.module_id || "AI"}</Text>
                    <ReviewBadge status={it.review_status} />
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

                      {/* HEKİM DEĞERLENDİRMESİ (2026-08-06): AI çıktısı öneri, klinik karar hekimin.
                          Karar kaydın YANINA yazılır; AI sonucu değişmez. */}
                      <AiReviewControls
                        status={it.review_status}
                        note={it.review_note}
                        reviewedBy={it.reviewed_by}
                        reviewedAt={it.reviewed_at ? fmtDate(it.reviewed_at) : ""}
                        busy={reviewing === it.id}
                        onSubmit={(st, nt) => submitReview(it.id, st, nt)}
                      />

                      {/* KVKK: tek kaydı silme. Kart AÇIKKEN görünür → listede kazara dokunma riski yok. */}
                      <TouchableOpacity
                        style={styles.silBtn}
                        disabled={silinen === it.id}
                        onPress={() => kaydiSil(it.id)}
                        accessibilityRole="button"
                        accessibilityLabel={`${it.module_label || it.module_id} kaydını sil`}>
                        <Trash2 color={colors.danger} size={rs(14)} />
                        <Text style={styles.silText}>
                          {silinen === it.id ? "Siliniyor…" : "Bu kaydı sil"}
                        </Text>
                      </TouchableOpacity>
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
        </View>
      )}
    </View>
  );
}

/**
 * [S3 adım 5] Yerel çip ORTAK `Chip` ilkeline devredildi. Eski gövde `paddingVertical: spacing.xs`
 * ile 320 px'te 26 px yükseklikte kalıyordu (erişilebilirlik tabanı 40). Renkler style/activeStyle
 * ile aynen taşındığı için GÖRSEL DEĞİŞİKLİK YOK; yalnız dokunma alanı büyüdü.
 */
function Chip({ label, active, onPress }: { label: string; active: boolean; onPress: () => void }) {
  return (
    <OrtakChip
      label={label}
      active={active}
      onPress={onPress}
      accessibilityLabel={`Filtre: ${label}`}
      style={styles.chip}
      activeStyle={styles.chipActive}
      textStyle={styles.chipText}
      activeTextStyle={styles.chipTextActive}
    />
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg, width: "100%", maxWidth: layoutMax.icerik, alignSelf: "center" },
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
  silBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: rs(6),
            marginTop: spacing.sm, paddingVertical: rs(10), borderRadius: radius.md,
            borderWidth: 1, borderColor: colors.danger, minHeight: touch.min },
  silText: { color: colors.danger, fontWeight: "700", fontSize: rf(12) },
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
  // [S4 adım 3] Alt boşluk TEK yerde: AppShell içerik ScrollView'ı rs(160)+güvenli alan (mobil) /
  // rs(84) (masaüstü) veriyor. Ekranın kendi paddingBottom'ı bunun ÜSTÜNE binip sayfa sonunda
  // ~200 px ölü alan bırakıyordu.
  list: { padding: spacing.lg, gap: spacing.md },
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
