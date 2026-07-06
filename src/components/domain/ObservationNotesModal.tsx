/**
 * ObservationNotesModal — seans-sonrası gözlem notu (PyQt observation_notes_dialog).
 * ==================================================================================
 * Seans bitince açılır: 6 hızlı-tepki chip'i + serbest not. "Kaydet" → seansı notuyla
 * birlikte history'ye yazar (/api/session/notes). "Atla" → kaydetmeden kapatır.
 */
import { useState } from "react";
import { Modal, View, Text, StyleSheet, TouchableOpacity, TextInput } from "react-native";
import { colors, spacing, typography, rs } from "@/theme/tokens";
import { apiPost } from "@/services/apiClient";
import { useSafeAreaInsets } from "react-native-safe-area-context";

const REACTIONS = ["Sakinleşti", "Hareket etti", "Uyudu", "Endişeli", "Tepki yok", "Rahatsızlık"];

export interface ObsSession {
  patientName?: string;
  mode?: string;
  frequency?: number;
  intensity?: number;
  durationMinutes?: number;
}

export function ObservationNotesModal({
  visible, session, onClose,
}: {
  visible: boolean;
  session: ObsSession | null;
  onClose: () => void;
}) {
  const insets = useSafeAreaInsets();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);

  const toggle = (r: string) =>
    setSelected((p) => {
      const n = new Set(p);
      if (n.has(r)) n.delete(r);
      else n.add(r);
      return n;
    });

  const reset = () => {
    setSelected(new Set());
    setNotes("");
  };

  const save = async () => {
    setSaving(true);
    const reactionText = Array.from(selected).join(", ");
    const full = [reactionText, notes.trim()].filter(Boolean).join(" — ");
    await apiPost<any>(
      "/session/notes",
      {
        notes: full,
        patient_name: session?.patientName ?? "",
        mode: session?.mode ?? "Manuel",
        frequency: session?.frequency ?? 0,
        intensity: session?.intensity ?? 0,
        duration_minutes: session?.durationMinutes ?? 0,
      },
      null
    ).catch(() => {});
    setSaving(false);
    reset();
    onClose();
  };

  const skip = () => {
    reset();
    onClose();
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={skip}>
      <View style={styles.backdrop}>
        <View style={[styles.card, { paddingBottom: insets.bottom + spacing.lg }]}>
          <Text style={styles.title}>📝 Seans Gözlem Notu</Text>
          {session?.patientName ? <Text style={styles.sub}>{session.patientName}</Text> : null}

          <Text style={styles.label}>Hasta tepkisi</Text>
          <View style={styles.chips}>
            {REACTIONS.map((r) => (
              <TouchableOpacity
                key={r}
                style={[styles.chip, selected.has(r) && styles.chipActive]}
                onPress={() => toggle(r)}
              >
                <Text style={[styles.chipText, selected.has(r) && styles.chipTextActive]}>{r}</Text>
              </TouchableOpacity>
            ))}
          </View>

          <Text style={styles.label}>Notlar</Text>
          <TextInput
            style={styles.input}
            accessibilityLabel="Gözlem notları"
            value={notes}
            onChangeText={setNotes}
            placeholder="Ek gözlemler…"
            placeholderTextColor={colors.textMuted}
            multiline
            numberOfLines={3}
          />

          <View style={styles.btnRow}>
            <TouchableOpacity style={[styles.btn, styles.btnSkip]} onPress={skip} disabled={saving}>
              <Text style={styles.btnText} numberOfLines={1}>Atla</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.btn, styles.btnSave, saving && { opacity: 0.5 }]}
              onPress={save}
              disabled={saving}
            >
              <Text style={styles.btnText} numberOfLines={1} adjustsFontSizeToFit>{saving ? "Kaydediliyor…" : "💾 Kaydet"}</Text>
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.6)", justifyContent: "flex-end" },
  card: {
    backgroundColor: "#0f172a",
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    padding: spacing.lg,
    gap: spacing.md,
    borderWidth: 1,
    borderColor: "#1e3a5f",
  },
  title: { color: colors.text, fontSize: typography.subtitle, fontWeight: "800" },
  sub: { color: colors.primary, fontSize: typography.small, fontWeight: "700" },
  label: { color: colors.textMuted, fontSize: typography.small, fontWeight: "700" },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs },
  chip: {
    backgroundColor: "#1e293b",
    borderRadius: 18,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderWidth: 1,
    borderColor: "#334155",
  },
  chipActive: { backgroundColor: "#1d4ed8", borderColor: "#3b82f6" },
  chipText: { color: colors.textMuted, fontSize: typography.small },
  chipTextActive: { color: "#fff", fontWeight: "700" },
  input: {
    backgroundColor: "#1e293b",
    borderRadius: 10,
    padding: spacing.md,
    color: colors.text,
    borderWidth: 1,
    borderColor: "#334155",
    textAlignVertical: "top",
    minHeight: rs(70),
  },
  btnRow: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.xs },
  btn: { flex: 1, borderRadius: 12, padding: spacing.md, alignItems: "center" },
  btnSkip: { backgroundColor: "#334155" },
  btnSave: { backgroundColor: "#22c55e" },
  btnText: { color: "#fff", fontWeight: "800", fontSize: typography.body },
});
