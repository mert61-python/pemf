import { useEffect, useState } from "react";
import { StyleSheet, Text, View, TouchableOpacity, ScrollView, ActivityIndicator, Linking, TextInput, Platform } from "react-native";
import { Edit3, Trash2, Share2 } from "lucide-react-native";
import * as FileSystem from "expo-file-system/legacy";
import * as Sharing from "expo-sharing";
import { Card } from "@/components/ui/Card";
import { StatusPill } from "@/components/ui/StatusPill";
import { colors, spacing, typography, rs } from "@/theme/tokens";
import { serviceConfig } from "@/services/config";
import { apiGet, apiPost, platformConfirm, platformAlert } from "@/services/apiClient";
import { useToast } from "@/components/ui/ToastProvider";
import { ResponsiveGrid } from "@/components/ui/ResponsiveGrid";
import { useAppNav } from "@/context/AppNavContext";
import { SessionDetailModal } from "@/components/domain/SessionDetailModal";

// P1 audit 2026-06-28: PEMF_REQUIRE_AUTH=1 iken /history/export_* auth-muaf DEĞİL; Linking.openURL
// header gönderemediği için 401 ile sessizce başarısız oluyordu. Backend ?token= query'sini kabul
// ediyor (auth middleware) → token varsa URL'e ekle.
const withToken = (url: string): string =>
  serviceConfig.apiToken
    ? `${url}${url.includes("?") ? "&" : "?"}token=${encodeURIComponent(serviceConfig.apiToken)}`
    : url;

// Backend ham seans durumlarını (İngilizce) görüntüleme için Türkçeye çevirir.
// NOT: Yalnızca gösterim amaçlıdır; backend ham değerleri (renk/durum mantığı) değiştirilmez.
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
  success: "Başarılı"
};

function statusLabelTr(status?: string): string {
  if (!status) return "Bilinmiyor";
  const key = status.toLowerCase();
  if (STATUS_LABELS_TR[key]) return STATUS_LABELS_TR[key];
  // Bilinmeyen durumu en azından okunaklı göster (ilk harf büyük).
  return status.charAt(0).toUpperCase() + status.slice(1);
}

export function TreatmentHistoryScreen() {
  const { selectedPatient } = useAppNav();
  const [sessions, setSessions] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  // audit B-8.2: keyset (cursor) pagination — ilk sayfa + "Daha Fazla" ile büyük geçmişe eriş.
  const PAGE_SIZE = 50;
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  // Hastalar tabından "geçmiş"e gelindiyse aramayı o hastayla önceden doldur.
  const [searchQuery, setSearchQuery] = useState(selectedPatient?.name || "");
  // Seans BOBİN-DETAYI modalı için seçili seans (null → kapalı).
  const [selectedSessionId, setSelectedSessionId] = useState<string | number | null>(null);

  const fetchHistory = async () => {
    setLoading(true);
    setLoadError(false);
    const data = await apiGet<any[] | null>(`/history/?limit=${PAGE_SIZE}`, null);
    if (data === null) {
      setLoadError(true);
      setSessions([]);
      setHasMore(false);
    } else {
      setSessions(data);
      setHasMore(data.length === PAGE_SIZE);  // tam sayfa → daha fazlası olabilir
    }
    setLoading(false);
  };

  // audit B-8.2: sonraki sayfa — cursor = yüklü SON seansın id'si (keyset). Büyük geçmişte yalnız
  // en yeni sayfayla sınırlı kalmadan tüm kayıtlara sayfalayarak eriş (offset yavaşlığı/kayması yok).
  const loadMore = async () => {
    if (loadingMore || !hasMore || sessions.length === 0) return;
    setLoadingMore(true);
    const lastId = sessions[sessions.length - 1]?.id;
    const data = await apiGet<any[] | null>(`/history/?limit=${PAGE_SIZE}&cursor=${lastId}`, null);
    if (data && data.length > 0) {
      setSessions((prev) => [...prev, ...data]);
      setHasMore(data.length === PAGE_SIZE);
    } else {
      setHasMore(false);
    }
    setLoadingMore(false);
  };

  useEffect(() => {
    fetchHistory();
  }, []);

  const filteredSessions = sessions.filter((s) => {
    const q = searchQuery.toLowerCase();
    const patientName = (s.patient_name || "").toLowerCase();
    const notes = (s.patient_notes || "").toLowerCase();
    const date = (s.session_date || "").toLowerCase();
    return patientName.includes(q) || notes.includes(q) || date.includes(q);
  });

  // "Tümünü PDF İndir" EKRANDA GÖRÜNEN (aktif filtre) kayıtları verir — eskiden filtreyi yok
  // sayıp tüm seansları alıyordu. Ayrıca çok kayıtta uzun URL 414 vermesin diye üst sınır.
  const PDF_MAX = 200;
  const downloadAllPdf = () => {
    const list = filteredSessions;
    if (list.length === 0) return;
    if (list.length > PDF_MAX) {
      platformAlert("Çok fazla kayıt", `${list.length} seans var; ilk ${PDF_MAX} tanesi PDF'e aktarılacak. Aramayı daraltın.`);
    }
    const sessionIds = list.slice(0, PDF_MAX).map(s => s.id).join(",");
    Linking.openURL(withToken(`${serviceConfig.apiBaseUrl}/history/export_pdf?session_ids=${sessionIds}`));
  };

  const downloadCsv = () => {
    Linking.openURL(withToken(`${serviceConfig.apiBaseUrl}/history/export_csv`));
  };



  return (
    <ScrollView contentContainerStyle={{ paddingBottom: spacing.xxl, width: "100%", maxWidth: rs(1100), alignSelf: "center" }}>
      <View style={styles.headerRow}>
        <Text style={styles.intro}>Hastalarınıza ait geçmiş tedavi kayıtları ve raporlamalar.</Text>
        <View style={{flexDirection: 'row', gap: spacing.sm}}>
          <TouchableOpacity style={styles.btnOutline} onPress={downloadCsv}>
            <Text style={styles.btnOutlineText}>Excel/CSV İndir</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.btnPrimary} onPress={downloadAllPdf}>
            <Text style={styles.btnPrimaryText}>Tümünü PDF İndir</Text>
          </TouchableOpacity>
        </View>
      </View>

      <View style={styles.searchBox}>
        <TextInput 
          style={styles.searchInput} 
          placeholder="Hasta, Not veya Tarih ara..." 
          placeholderTextColor={colors.textMuted}
          value={searchQuery}
          onChangeText={setSearchQuery}
        />
      </View>
      
      {loading ? (
        <ActivityIndicator size="large" color={colors.primary} style={{ marginTop: spacing.xl }} />
      ) : loadError ? (
        <View style={{ alignItems: "center", gap: spacing.md, marginTop: spacing.xl }}>
          <Text style={[styles.intro, { flex: undefined }]}>Geçmiş yüklenemedi. Bağlantıyı kontrol edin.</Text>
          <TouchableOpacity style={styles.btnOutline} onPress={fetchHistory}>
            <Text style={styles.btnOutlineText}>Tekrar Dene</Text>
          </TouchableOpacity>
        </View>
      ) : filteredSessions.length === 0 ? (
        <Text style={[styles.intro, { marginTop: spacing.md, flex: undefined }]}>
          {searchQuery ? "Aramayla eşleşen kayıt yok." : "Geçmiş tedavi kaydı bulunamadı."}
        </Text>
      ) : (
        <ResponsiveGrid minItemWidth={360}>
          {filteredSessions.map((session) => (
            <SessionCard
              key={session.id}
              session={session}
              onRefresh={fetchHistory}
              onOpenDetails={() => setSelectedSessionId(session.id)}
            />
          ))}
        </ResponsiveGrid>
      )}

      {hasMore && (
        <TouchableOpacity
          style={styles.loadMoreBtn}
          onPress={loadMore}
          disabled={loadingMore}
          accessibilityRole="button"
          accessibilityLabel="Daha fazla geçmiş yükle"
        >
          {loadingMore
            ? <ActivityIndicator color={colors.primary} />
            : <Text style={styles.loadMoreText}>Daha Fazla Yükle</Text>}
        </TouchableOpacity>
      )}

      <SessionDetailModal
        visible={selectedSessionId !== null}
        sessionId={selectedSessionId}
        onClose={() => setSelectedSessionId(null)}
      />
    </ScrollView>
  );
}

function SessionCard({ session, onRefresh, onOpenDetails }: { session: any, onRefresh: () => void, onOpenDetails: () => void }) {
  const { showToast } = useToast();
  const [isEditingNotes, setIsEditingNotes] = useState(false);
  const [notes, setNotes] = useState(session.patient_notes || "");
  const s = session.session_status?.toLowerCase();
  let state: "online" | "warning" | "offline" = "offline";
  if (s === "completed") state = "online";
  else if (s === "active" || s === "running") state = "warning";
  else if (s === "interrupted" || s === "error" || s === "aborted_recovered") state = "offline";

  const downloadPdf = () => {
    Linking.openURL(withToken(`${serviceConfig.apiBaseUrl}/history/export_pdf?session_ids=${session.id}`));
  };

  const handleSaveNotes = async () => {
    const res = await apiPost<{status: string}>("/history/update_notes", { session_id: session.id, notes }, { status: "error" });
    if (res.status === "success") {
      setIsEditingNotes(false);
      showToast("Notlar kaydedildi.", "success");
      onRefresh();
    } else {
      showToast("Notlar kaydedilemedi.", "error");
    }
  };

  const handleDelete = async () => {
    const ok = await platformConfirm("Kaydı Sil", "Bu seans kaydını silmek istediğinizden emin misiniz?", "Sil");
    if (!ok) return;
    const res = await apiPost<{status: string}>("/history/delete", { session_id: session.id }, { status: "error" });
    if (res.status === "success") {
      showToast("Seans silindi.", "success");
      onRefresh();
    } else {
      showToast("Silme işlemi başarısız.", "error");
    }
  };

  // Raporu PAYLAŞ: backend'den PDF indir → telefonun native paylaş menüsü (WhatsApp/
  // e-posta/herhangi biri). App Password/SMTP GEREKTİRMEZ — vet kime gönüldüğünü paylaş
  // hedefinde seçer. Web'de native menü yok → PDF'i yeni sekmede açar (kullanıcı paylaşır).
  const handleShareReport = async () => {
    const url = `${serviceConfig.apiBaseUrl}/history/export_pdf?session_ids=${session.id}`;
    if (Platform.OS === "web") {
      Linking.openURL(url);
      return;
    }
    try {
      showToast("Rapor hazırlanıyor...", "info");
      const safeName = `PEMF_Rapor_${session.patient_name || "hasta"}_${session.id}.pdf`.replace(/[^\w.\-]/g, "_");
      const localPath = `${FileSystem.cacheDirectory}${safeName}`;
      // Backend PEMF_REQUIRE_AUTH=1 ise X-API-Key gerekir; token boşsa header gönderilmez.
      const headers: Record<string, string> = serviceConfig.apiToken ? { "X-API-Key": serviceConfig.apiToken } : {};
      const { uri, status } = await FileSystem.downloadAsync(url, localPath, { headers });
      if (status !== 200) {
        showToast("Rapor indirilemedi.", "error");
        return;
      }
      if (!(await Sharing.isAvailableAsync())) {
        showToast("Bu cihazda paylaşım desteklenmiyor.", "error");
        return;
      }
      await Sharing.shareAsync(uri, {
        mimeType: "application/pdf",
        dialogTitle: "Raporu paylaş",
        UTI: "com.adobe.pdf",
      });
    } catch (e) {
      showToast("Paylaşım sırasında hata oluştu.", "error");
    }
  };

  return (
    <Card style={styles.card}>
      <View style={styles.row}>
        <TouchableOpacity
          style={styles.titleArea}
          onPress={onOpenDetails}
          accessibilityLabel="Seans detayını aç"
        >
          <Text style={styles.title} numberOfLines={1} ellipsizeMode="tail">{session.patient_name || "Bilinmeyen Hasta"}</Text>
          <Text style={styles.muted} numberOfLines={1} ellipsizeMode="tail">{session.session_date} {session.start_time}</Text>
          <Text style={styles.detailsHint} numberOfLines={1}>Bobin detayını gör ›</Text>
        </TouchableOpacity>
        <View style={{flexDirection: 'row', alignItems: 'center', gap: spacing.sm}}>
          <StatusPill label={statusLabelTr(session.session_status)} state={state} />
          <TouchableOpacity style={styles.iconBtn} onPress={handleShareReport} accessibilityLabel="Raporu Paylaş">
            <Share2 color={colors.primary} size={18} />
          </TouchableOpacity>
          <TouchableOpacity style={styles.btnOutline} onPress={downloadPdf}>
            <Text style={styles.btnOutlineText}>PDF</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.iconBtn} onPress={handleDelete}>
            <Trash2 color={colors.danger} size={18} />
          </TouchableOpacity>
        </View>
      </View>
      <View style={styles.detailGrid}>
        <Detail label="Mod" value={session.treatment_mode || "-"} />
        <Detail label="Hedef" value={session.target_condition || "-"} />
        <Detail label="Süre" value={`${session.duration_minutes || 0} dk`} />
        <Detail label="Frekans" value={`${session.frequency_hz || 0} Hz`} />
        <Detail label="Yoğunluk" value={`${session.intensity_mt || 0} mT`} />
      </View>
      <View style={styles.notesContainer}>
        <View style={styles.notesHeader}>
          <Text style={styles.detailLabel}>Notlar:</Text>
          {isEditingNotes ? (
             <View style={{flexDirection: 'row', gap: spacing.sm}}>
                <TouchableOpacity onPress={handleSaveNotes}><Text style={{color: colors.success, fontWeight: "bold"}}>Kaydet</Text></TouchableOpacity>
                <TouchableOpacity onPress={() => { setIsEditingNotes(false); setNotes(session.patient_notes || ""); }}><Text style={{color: colors.danger, fontWeight: "bold"}}>İptal</Text></TouchableOpacity>
             </View>
          ) : (
            <TouchableOpacity onPress={() => setIsEditingNotes(true)}><Edit3 color={colors.textMuted} size={14} /></TouchableOpacity>
          )}
        </View>
        
        {isEditingNotes ? (
          <TextInput 
            style={styles.notesInput}
            value={notes}
            onChangeText={setNotes}
            multiline
            placeholder="Tedavi notu..."
            placeholderTextColor={colors.textMuted}
          />
        ) : (
          <Text style={[styles.notesText, !session.patient_notes && {color: colors.textSubtle}]}>
            {session.patient_notes || "Not eklenmemiş."}
          </Text>
        )}
      </View>
    </Card>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.detail}>
      <Text style={styles.detailLabel}>{label}</Text>
      <Text style={styles.detailValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  loadMoreBtn: {
    alignSelf: "center",
    marginTop: spacing.md,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.xl,
    borderRadius: rs(10),
    borderWidth: 1,
    borderColor: colors.border,
    minHeight: rs(44),
    justifyContent: "center",
    alignItems: "center",
  },
  loadMoreText: { color: colors.primary, fontWeight: "700", fontSize: typography.body },
  headerRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: spacing.md,
    flexWrap: 'wrap',
    gap: spacing.sm
  },
  searchBox: {
    marginBottom: spacing.md,
    backgroundColor: colors.bgAlt,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm
  },
  searchInput: {
    color: colors.text,
    fontSize: typography.body,
  },
  intro: {
    color: colors.textMuted,
    fontSize: typography.body,
    flex: 1,
    minWidth: rs(200)
  },
  card: {
    gap: spacing.md,
    marginBottom: spacing.md
  },
  row: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    gap: spacing.md
  },
  titleArea: {
    flex: 1,
    minWidth: rs(0),
    flexShrink: 1
  },
  title: {
    color: colors.text,
    fontSize: typography.subtitle,
    fontWeight: "800"
  },
  detailsHint: {
    color: colors.primary,
    fontSize: typography.small,
    fontWeight: "700",
    marginTop: spacing.xs
  },
  muted: {
    color: colors.textMuted,
    fontSize: typography.caption,
    marginTop: spacing.xs
  },
  detailGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.sm
  },
  detail: {
    backgroundColor: colors.bgAlt,
    borderRadius: 8,
    minWidth: rs(100),
    flex: 1,
    padding: spacing.md
  },
  detailLabel: {
    color: colors.textMuted,
    fontSize: typography.small,
    fontWeight: "700"
  },
  detailValue: {
    color: colors.text,
    fontSize: typography.body,
    fontWeight: "800",
    marginTop: spacing.xs
  },
  notesContainer: {
    marginTop: spacing.xs,
    paddingTop: spacing.sm,
    borderTopWidth: 1,
    borderColor: colors.border
  },
  notesHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center'
  },
  notesText: {
    color: colors.text,
    fontSize: typography.small,
    marginTop: spacing.xs,
    fontStyle: 'italic'
  },
  notesInput: {
    color: colors.text,
    fontSize: typography.small,
    marginTop: spacing.xs,
    backgroundColor: colors.bg,
    borderRadius: 4,
    padding: spacing.xs,
    minHeight: rs(60),
    textAlignVertical: 'top'
  },
  btnPrimary: {
    backgroundColor: colors.primary,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center'
  },
  btnPrimaryText: {
    color: "#fff",
    fontWeight: "bold",
    fontSize: typography.small
  },
  btnOutline: {
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: colors.primary,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: 8
  },
  btnOutlineText: {
    color: colors.primary,
    fontWeight: "bold",
    fontSize: typography.small
  },
  iconBtn: {
    padding: spacing.xs
  }
});
