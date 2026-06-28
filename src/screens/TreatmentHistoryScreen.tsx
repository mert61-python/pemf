import { useEffect, useState } from "react";
import { StyleSheet, Text, View, TouchableOpacity, ScrollView, ActivityIndicator, Linking, TextInput, Platform } from "react-native";
import { Edit3, Trash2, Share2 } from "lucide-react-native";
import * as FileSystem from "expo-file-system/legacy";
import * as Sharing from "expo-sharing";
import { Card } from "@/components/ui/Card";
import { StatusPill } from "@/components/ui/StatusPill";
import { colors, spacing, typography } from "@/theme/tokens";
import { serviceConfig } from "@/services/config";
import { apiGet, apiPost, platformConfirm } from "@/services/apiClient";
import { useToast } from "@/components/ui/ToastProvider";
import { ResponsiveGrid } from "@/components/ui/ResponsiveGrid";
import { useAppNav } from "@/context/AppNavContext";
import { SessionDetailModal } from "@/components/domain/SessionDetailModal";

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
  // Hastalar tabından "geçmiş"e gelindiyse aramayı o hastayla önceden doldur.
  const [searchQuery, setSearchQuery] = useState(selectedPatient?.name || "");
  // Seans BOBİN-DETAYI modalı için seçili seans (null → kapalı).
  const [selectedSessionId, setSelectedSessionId] = useState<string | number | null>(null);

  const fetchHistory = async () => {
    setLoading(true);
    setLoadError(false);
    const data = await apiGet<any[] | null>("/history/", null);
    if (data === null) {
      setLoadError(true);
      setSessions([]);
    } else {
      setSessions(data);
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchHistory();
  }, []);

  const downloadAllPdf = () => {
    if (sessions.length === 0) return;
    const sessionIds = sessions.map(s => s.id).join(",");
    Linking.openURL(`${serviceConfig.apiBaseUrl}/history/export_pdf?session_ids=${sessionIds}`);
  };

  const downloadCsv = () => {
    Linking.openURL(`${serviceConfig.apiBaseUrl}/history/export_csv`);
  };

  const filteredSessions = sessions.filter((s) => {
    const q = searchQuery.toLowerCase();
    const patientName = (s.patient_name || "").toLowerCase();
    const notes = (s.patient_notes || "").toLowerCase();
    const date = (s.session_date || "").toLowerCase();
    return patientName.includes(q) || notes.includes(q) || date.includes(q);
  });



  return (
    <ScrollView contentContainerStyle={{ paddingBottom: spacing.xxl, width: "100%", maxWidth: 1100, alignSelf: "center" }}>
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
    Linking.openURL(`${serviceConfig.apiBaseUrl}/history/export_pdf?session_ids=${session.id}`);
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
          <Text style={styles.title}>{session.patient_name || "Bilinmeyen Hasta"}</Text>
          <Text style={styles.muted}>{session.session_date} {session.start_time}</Text>
          <Text style={styles.detailsHint}>Bobin detayını gör ›</Text>
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
    minWidth: 200
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
    minWidth: 100,
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
    minHeight: 60,
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
