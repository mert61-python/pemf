import { useEffect, useState } from "react";
import { StyleSheet, Text, View, TouchableOpacity, ScrollView, ActivityIndicator, Linking } from "react-native";
import { Card } from "@/components/ui/Card";
import { StatusPill } from "@/components/ui/StatusPill";
import { colors, spacing, typography } from "@/theme/tokens";
import { serviceConfig } from "@/services/config";
import { apiGet } from "@/services/apiClient";

export function TreatmentHistoryScreen() {
  const [sessions, setSessions] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    const fetchHistory = async () => {
      setLoading(true);
      const data = await apiGet<any[]>("/history/", []);
      if (mounted) {
        setSessions(data);
        setLoading(false);
      }
    };
    fetchHistory();
    return () => {
      mounted = false;
    };
  }, []);

  const downloadAllPdf = () => {
    if (sessions.length === 0) return;
    const sessionIds = sessions.map(s => s.id).join(",");
    Linking.openURL(`${serviceConfig.apiBaseUrl}/history/export_pdf?session_ids=${sessionIds}`);
  };

  return (
    <ScrollView contentContainerStyle={{ paddingBottom: spacing.xxl }}>
      <View style={styles.headerRow}>
        <Text style={styles.intro}>Hastalarınıza ait geçmiş tedavi kayıtları ve raporlamalar.</Text>
        <TouchableOpacity style={styles.btnPrimary} onPress={downloadAllPdf}>
          <Text style={styles.btnPrimaryText}>Tümünü PDF İndir</Text>
        </TouchableOpacity>
      </View>
      
      {loading ? (
        <ActivityIndicator size="large" color={colors.primary} style={{ marginTop: spacing.xl }} />
      ) : sessions.length === 0 ? (
        <Text style={[styles.intro, { marginTop: spacing.md }]}>Geçmiş tedavi kaydı bulunamadı.</Text>
      ) : (
        sessions.map((session) => (
          <SessionCard key={session.id} session={session} />
        ))
      )}
    </ScrollView>
  );
}

function SessionCard({ session }: { session: any }) {
  // Session status mapping
  const s = session.session_status?.toLowerCase();
  let state: "online" | "warning" | "offline" = "offline";
  if (s === "completed") state = "online";
  else if (s === "active" || s === "running") state = "warning";
  else if (s === "interrupted" || s === "error" || s === "aborted_recovered") state = "offline";

  const downloadPdf = () => {
    Linking.openURL(`${serviceConfig.apiBaseUrl}/history/export_pdf?session_ids=${session.id}`);
  };

  return (
    <Card style={styles.card}>
      <View style={styles.row}>
        <View>
          <Text style={styles.title}>{session.patient_name || "Bilinmeyen Hasta"}</Text>
          <Text style={styles.muted}>{session.session_date} {session.start_time}</Text>
        </View>
        <View style={{flexDirection: 'row', alignItems: 'center', gap: spacing.sm}}>
          <StatusPill label={session.session_status || "Bilinmiyor"} state={state} />
          <TouchableOpacity style={styles.btnOutline} onPress={downloadPdf}>
            <Text style={styles.btnOutlineText}>PDF</Text>
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
      {session.patient_notes ? (
        <View style={styles.notesContainer}>
          <Text style={styles.detailLabel}>Notlar:</Text>
          <Text style={styles.notesText}>{session.patient_notes}</Text>
        </View>
      ) : null}
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
  title: {
    color: colors.text,
    fontSize: typography.subtitle,
    fontWeight: "800"
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
  notesText: {
    color: colors.text,
    fontSize: typography.small,
    marginTop: spacing.xs,
    fontStyle: 'italic'
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
  }
});
