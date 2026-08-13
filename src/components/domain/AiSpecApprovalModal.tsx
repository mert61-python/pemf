// Author: mertaygn, cglrgrkn
/**
 * AI ÖNERİSİ ONAY MODALI (2026-08-06, sahip kararı: "sert kapı — onaysız tedavi başlamaz")
 *
 * AI Pro artık doğrudan başlamaz: önce `/api/ai/pro/propose` ile ne uygulanacağını hesaplar,
 * bu modal hekime GÖSTERİR, hekim onaylarsa `/api/ai/pro/start` onay kimliğiyle çağrılır.
 * Onay tek kullanımlık + süreli; uygulanacak parametreler backend'de MÜHÜRLÜdür (istemci
 * onaydan sonra başka değer gönderemez — bkz. servers/ai_approval.py).
 *
 * TASARIM:
 *  * "Onayla" birincil ama otomatik-odaklı DEĞİL — kazara Enter'la otonom tedavi başlamasın.
 *  * "Reddet" GEREKÇE ister: hem denetim izi hem model iyileştirmesi için gerçek veri.
 *  * Kapatma (X / dışa tıklama) = REDDETME DEĞİL, sadece ertelemedir; öneri açık kalır ve
 *    süresi dolunca kendiliğinden geçersizleşir. Sessizce "reddedildi" saymak yanıltıcı olurdu.
 *  * Duty'ler yüzde olarak gösterilir (model 0-1 üretir) — hekim klinik birimde okur.
 */
import { useState } from "react";
import { Modal, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from "react-native";
import { CheckCircle2, X, XCircle } from "lucide-react-native";

import { colors, radius, rf, rs, spacing } from "@/theme/tokens";

export interface AiProposalSpecs {
  organ_id: number;
  duration_minutes: number;
  coil_ids: number[];
  /** Bobin başına duty (0-1) */
  D: number[];
  /** Bobin başına faz (derece) */
  P: number[];
  e_field: number;
}

export interface AiProposalMeta {
  x_mm?: number;
  y_mm?: number;
  z_mm?: number;
  reliability?: number;
}

export function AiSpecApprovalModal({
  visible, specs, meta, organName, busy, onApprove, onReject, onDismiss,
}: {
  visible: boolean;
  specs: AiProposalSpecs | null;
  meta?: AiProposalMeta | null;
  organName?: string;
  busy?: boolean;
  onApprove: () => void;
  onReject: (reason: string) => void;
  onDismiss: () => void;
}) {
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");

  if (!specs) return null;

  const rows = (specs.coil_ids || []).map((cid, i) => ({
    cid,
    duty: Number(specs.D?.[i] ?? 0),
    phase: Number(specs.P?.[i] ?? 0),
  }));
  const surulen = rows.filter((r) => r.duty > 0).length;
  const guven = typeof meta?.reliability === "number" ? meta.reliability : null;
  // Düşük lokalizasyon güveni sessiz kalmamalı — hekim onaylarken bunu bilmeli.
  const dusukGuven = guven !== null && guven < 0.5;

  const kapat = () => { setRejecting(false); setReason(""); onDismiss(); };

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={kapat}>
      <View style={s.backdrop}>
        <View style={s.card} accessibilityLabel="AI seans önerisi onay penceresi">
          <View style={s.head}>
            <Text style={s.title}>AI Seans Önerisi</Text>
            <TouchableOpacity onPress={kapat} accessibilityRole="button" accessibilityLabel="Kapat">
              <X size={rs(20)} color={colors.textMuted} />
            </TouchableOpacity>
          </View>

          <Text style={s.lead}>
            Otonom seans <Text style={s.bold}>onaylanmadan başlamaz</Text>. Aşağıdaki
            parametreleri inceleyip onaylayın veya gerekçesiyle reddedin.
          </Text>

          <View style={s.summary}>
            <Meta label="Organ" value={organName || `#${specs.organ_id}`} />
            <Meta label="Süre" value={`${specs.duration_minutes} dk`} />
            <Meta label="Sürülen bobin" value={`${surulen}/${rows.length}`} />
            <Meta label="E (öngörü)" value={Number(specs.e_field ?? 0).toFixed(4)} />
          </View>

          {guven !== null && (
            <Text style={[s.rel, dusukGuven && s.relWarn]}>
              Lokalizasyon güveni: %{Math.round(guven * 100)}
              {dusukGuven ? " — DÜŞÜK, konumu doğrulayın" : ""}
            </Text>
          )}

          <ScrollView style={s.tableWrap}>
            <View style={[s.tr, s.trHead]}>
              <Text style={[s.th, s.cCoil]}>Bobin</Text>
              <Text style={[s.th, s.cDuty]}>Duty</Text>
              <Text style={[s.th, s.cPhase]}>Faz</Text>
            </View>
            {rows.map((r) => (
              <View key={r.cid} style={s.tr}>
                <Text style={[s.td, s.cCoil]}>{r.cid}</Text>
                <Text style={[s.td, s.cDuty, r.duty > 0 ? s.on : s.off]}>
                  %{(r.duty * 100).toFixed(1)}
                </Text>
                <Text style={[s.td, s.cPhase]}>{r.phase.toFixed(0)}°</Text>
              </View>
            ))}
          </ScrollView>

          {rejecting ? (
            <View style={s.rejectBox}>
              <Text style={s.rejectLabel}>Red gerekçesi (kayda geçer)</Text>
              <TextInput
                style={s.input}
                value={reason}
                onChangeText={setReason}
                placeholder="Örn. lokalizasyon hatalı, duty çok yüksek…"
                placeholderTextColor={colors.textSubtle}
                multiline
                accessibilityLabel="Red gerekçesi"
              />
              <View style={s.actions}>
                <TouchableOpacity style={[s.btn, s.btnGhost]} onPress={() => setRejecting(false)}>
                  <Text style={s.btnGhostText}>Vazgeç</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[s.btn, s.btnDanger, (!reason.trim() || busy) && s.btnDisabled]}
                  disabled={!reason.trim() || !!busy}
                  onPress={() => onReject(reason.trim())}
                  accessibilityRole="button"
                  accessibilityLabel="Reddi onayla"
                >
                  <Text style={s.btnDangerText}>Reddet</Text>
                </TouchableOpacity>
              </View>
            </View>
          ) : (
            <View style={s.actions}>
              <TouchableOpacity
                style={[s.btn, s.btnGhost]}
                onPress={() => setRejecting(true)}
                disabled={!!busy}
                accessibilityRole="button"
                accessibilityLabel="Öneriyi reddet"
              >
                <XCircle size={rs(16)} color={colors.danger} />
                <Text style={s.btnGhostText}>Reddet</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[s.btn, s.btnPrimary, busy && s.btnDisabled]}
                onPress={onApprove}
                disabled={!!busy}
                accessibilityRole="button"
                accessibilityLabel="Öneriyi onayla ve seansı başlat"
              >
                <CheckCircle2 size={rs(16)} color="#04121F" />
                <Text style={s.btnPrimaryText}>{busy ? "Başlatılıyor…" : "Onayla ve Başlat"}</Text>
              </TouchableOpacity>
            </View>
          )}
        </View>
      </View>
    </Modal>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <View style={s.metaCell}>
      <Text style={s.metaLabel}>{label}</Text>
      <Text style={s.metaValue}>{value}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.6)", alignItems: "center", justifyContent: "center", padding: spacing.md },
  card: { width: "100%", maxWidth: rs(520), maxHeight: "88%", backgroundColor: colors.panel, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: spacing.lg, gap: spacing.sm },
  head: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  title: { color: colors.text, fontSize: rf(17), fontWeight: "800" },
  lead: { color: colors.textMuted, fontSize: rf(12), lineHeight: rf(18) },
  bold: { color: colors.text, fontWeight: "800" },
  summary: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.xs },
  metaCell: { minWidth: rs(96), backgroundColor: colors.bgAlt, borderRadius: radius.md, paddingVertical: spacing.xs, paddingHorizontal: spacing.sm },
  metaLabel: { color: colors.textSubtle, fontSize: rf(10) },
  metaValue: { color: colors.text, fontSize: rf(13), fontWeight: "700" },
  rel: { color: colors.textMuted, fontSize: rf(11) },
  relWarn: { color: colors.warning, fontWeight: "700" },
  tableWrap: { maxHeight: rs(200), borderWidth: 1, borderColor: colors.border, borderRadius: radius.md },
  tr: { flexDirection: "row", paddingVertical: rs(6), paddingHorizontal: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border },
  trHead: { backgroundColor: colors.bgAlt },
  th: { color: colors.textSubtle, fontSize: rf(11), fontWeight: "700" },
  td: { color: colors.text, fontSize: rf(12) },
  cCoil: { width: rs(56) },
  cDuty: { flex: 1 },
  cPhase: { width: rs(64), textAlign: "right" },
  on: { color: colors.success, fontWeight: "700" },
  off: { color: colors.textSubtle },
  rejectBox: { gap: spacing.xs },
  rejectLabel: { color: colors.textMuted, fontSize: rf(11) },
  input: { minHeight: rs(64), backgroundColor: colors.bg, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, color: colors.text, padding: spacing.sm, fontSize: rf(12), textAlignVertical: "top" },
  actions: { flexDirection: "row", justifyContent: "flex-end", gap: spacing.sm, marginTop: spacing.xs },
  btn: { flexDirection: "row", alignItems: "center", gap: rs(6), paddingVertical: rs(10), paddingHorizontal: spacing.md, borderRadius: radius.md },
  btnPrimary: { backgroundColor: colors.cyan },
  btnPrimaryText: { color: "#04121F", fontWeight: "800", fontSize: rf(13) },
  btnDanger: { backgroundColor: colors.danger },
  btnDangerText: { color: "#fff", fontWeight: "800", fontSize: rf(13) },
  btnGhost: { borderWidth: 1, borderColor: colors.border },
  btnGhostText: { color: colors.textMuted, fontWeight: "700", fontSize: rf(13) },
  btnDisabled: { opacity: 0.5 },
});
