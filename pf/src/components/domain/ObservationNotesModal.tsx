// Author: mertaygn, cglrgrkn
/**
 * ObservationNotesModal — seans-sonrası gözlem notu (PyQt observation_notes_dialog).
 * ==================================================================================
 * Seans bitince açılır: 6 hızlı-tepki chip'i + serbest not. "Kaydet" → seansı notuyla
 * birlikte history'ye yazar (/api/session/notes). "Atla" → kaydetmeden kapatır.
 */
import { useState, useEffect } from "react";
import { KeyboardAvoidingView, Modal, View, Text, StyleSheet, TouchableOpacity, TextInput, ScrollView } from "react-native";
import { KAV_BEHAVIOR_MODAL } from "@/hooks/useKeyboard";
import { Chip, ChipRow } from "@/components/ui/Chip";
import { colors, spacing, typography, rs } from "@/theme/tokens";
import { apiPost, platformAlert } from "@/services/apiClient";
import { useSafeAreaInsets } from "react-native-safe-area-context";

const REACTIONS = ["Sakinleşti", "Hareket etti", "Uyudu", "Endişeli", "Tepki yok", "Rahatsızlık"];

export interface ObsSession {
  patientName?: string;
  mode?: string;
  frequency?: number;
  intensity?: number;
  durationMinutes?: number;
  /** Denetim 2. tur [4.1]: SEANS kimliği (ControlScreen her seans başında artırır). Sıfırlama
   *  anahtarı yalnız hasta ADI olunca aynı isimli iki hastada ("Boncuk" klinikte gerçekçi)
   *  A'nın kaydedilmemiş notu B'nin modalında duruyor ve B'nin TIBBİ KAYDINA gidebiliyordu. */
  obsKey?: number;
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

  // GÜVENLİK (#48): hedef seans/hasta DEĞİŞİNCE veya sayfa (yeniden) AÇILINCA not+tepkileri SIFIRLA.
  // Aksi halde A hastası için yazılıp kaydedilmemiş not, uzaktan/AI-Pro ile B hastası (farklı hasta)
  // seansı başlayınca modalda kalır → B'nin kaydına YANLIŞ-HASTA notu kontaminasyonu.
  // ⚠️ `visible` DEP DEĞİL (denetim 2026-08-17). Modal, ACİL DURDUR'un üstünü kapatmasın diye
  // herhangi bir bobin `running` raporladığında GİZLENİYOR (`ControlScreen`, koşulsuz render →
  // `visible:false`'da unmount OLMUYOR). Gizlenme "yeni hasta / yeni açılış" DEĞİLDİR; `visible`
  // dep'te olduğu için hekimin yazdığı gözlem notu + seçili tepki chip'leri UYARISIZ siliniyordu.
  // Tetikleyici DIŞSAL: STOP'u kaçırmış bir ESP bobini yeniden bağlanınca `running` yayınlıyor ya
  // da masaüstü istemcisi/ikinci hekim seans başlatıyor. Not hiçbir yere kaydedilmiyordu; donanım
  // durunca modal doğru hasta adıyla ama BOŞ açılıyordu → hekim silindiğini fark etmeyebilir.
  // Modal'ı gizlemek KASITLI ve DOĞRU; kusur gizlenmede de SIFIRLAMA yapılmasıydı. #48'in amacı
  // (A hastasının notu B'ye bulaşmasın) yalnız hasta değişimi + açılış geçişini gerektiriyor:
  //   · gizle→göster: `patientName` değişmez → effect ateşlemez → not KORUNUR,
  //   · açılış: modal kapalıyken `session === null` → dep `undefined→"Rex"` → SIFIRLAR,
  //   · hasta değişimi: dep'te `session?.patientName` DURUYOR → SIFIRLAR.
  // Denetim 2. tur [4.1] (2026-08-20): dep'e SEANS kimliği (obsKey) eklendi. Yalnız isim,
  // AYNI İSİMLİ iki hastada ayırt edemiyordu: modal `running` yüzünden gizliyken (obsSession
  // null'a düşmeden) B'nin seansı bitince setObsSession aynı isimle YENİ nesne atar → isim-dep'i
  // ateşlemez → A'nın notu B'nin modalında kalır ve B'nin tıbbi kaydına gidebilirdi.
  // Aynı seansın gizle→göster'i her iki dep'i de değiştirmez → bulgu-20 koruması aynen sürer.
  useEffect(() => {
    setSelected(new Set());
    setNotes("");
  }, [session?.obsKey, session?.patientName]);

  const save = async () => {
    setSaving(true);
    const reactionText = Array.from(selected).join(", ");
    const full = [reactionText, notes.trim()].filter(Boolean).join(" — ");
    // DÜŞÜK fix: apiPost throw ETMEZ (null döner). Eskiden yanıt yutuluyordu → kaydetme başarısız olsa da
    // modal kapanıp gözlem-notu SESSİZCE kayboluyordu. Yanıtı doğrula; başarısızsa modalı AÇIK tut + uyar.
    const res = await apiPost<{ status?: string } | null>(
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
    );
    setSaving(false);
    if (!res || res.status === "error") {
      platformAlert("Not kaydedilemedi", "Gözlem notu sunucuya ulaşmadı. Bağlantıyı kontrol edip tekrar deneyin.");
      return;
    }
    reset();
    onClose();
  };

  const skip = () => {
    reset();
    onClose();
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={skip}>
      {/* [S4 adım 4] Perde KeyboardAvoidingView oldu. Android'de RN Modal KENDİ penceresini açar ve
          adjustResize ile zaten daralır → padding eklemek ÇİFT boşluk yapar; bu yüzden davranış
          yalnız iOS'ta 'padding' (KAV_BEHAVIOR_MODAL, tek kaynak). */}
      <KeyboardAvoidingView style={styles.backdrop} behavior={KAV_BEHAVIOR_MODAL}>
        <View style={styles.card}>
          <ScrollView
            contentContainerStyle={{ padding: spacing.lg, gap: spacing.md }}
            keyboardShouldPersistTaps="handled"
            showsVerticalScrollIndicator={false}
            style={styles.govde}
          >
          <Text style={styles.title}>📝 Seans Gözlem Notu</Text>
          {session?.patientName ? <Text style={styles.sub}>{session.patientName}</Text> : null}

          <Text style={styles.label}>Hasta tepkisi</Text>
          {/* [S3 adım 5] Ortak çip: eski gövde paddingVertical spacing.xs ile 320 px'te 26 px
              yükseklikteydi ve aralık 4 px'ti — hekim komşu tepkiyi işaretliyordu. */}
          <ChipRow>
            {REACTIONS.map((r) => (
              <Chip
                key={r}
                label={r}
                active={selected.has(r)}
                onPress={() => toggle(r)}
                style={styles.chip}
                activeStyle={styles.chipActive}
                textStyle={styles.chipText}
                activeTextStyle={styles.chipTextActive}
              />
            ))}
          </ChipRow>

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

          </ScrollView>

          {/* [S4 adım 4] Atla/Kaydet ScrollView'ın DIŞINDA: yatay telefonda (sheet ≈160 px) ve klavye
              açıkken düğmeler kaydırma alanının altında kalıp görünmüyordu. Artık kartın sabit alt
              şeridi; güvenli alan dolgusu da buraya taşındı. */}
          <View style={[styles.btnRow, { paddingBottom: insets.bottom + spacing.lg }]}>
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
      </KeyboardAvoidingView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.6)", justifyContent: "flex-end" },
  card: {
    backgroundColor: "#0f172a",
    borderTopLeftRadius: rs(20),
    borderTopRightRadius: rs(20),
    borderWidth: 1,
    borderColor: "#1e3a5f",
    width: "100%",
    maxWidth: rs(560),
    alignSelf: "center",
    maxHeight: "90%",
  },
  title: { color: colors.text, fontSize: typography.subtitle, fontWeight: "800" },
  sub: { color: colors.primary, fontSize: typography.small, fontWeight: "700" },
  label: { color: colors.textMuted, fontSize: typography.small, fontWeight: "700" },
  // Satır boşluğu ve yükseklik ChipRow/Chip'ten; burada yalnız RENK ve çerçeve kalır.
  chip: {
    backgroundColor: "#1e293b",
    borderRadius: 18,
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
  // Gövde kaydırılır, düğme şeridi kartın altında SABİT kalır (flexShrink/flexGrow ile).
  govde: { flexShrink: 1, flexGrow: 0 },
  btnRow: {
    flexDirection: "row", gap: spacing.sm,
    paddingHorizontal: spacing.lg, paddingTop: spacing.sm,
    borderTopWidth: 1, borderTopColor: "#1e3a5f",
  },
  btn: { flex: 1, borderRadius: 12, padding: spacing.md, alignItems: "center" },
  btnSkip: { backgroundColor: "#334155" },
  btnSave: { backgroundColor: "#22c55e" },
  btnText: { color: "#fff", fontWeight: "800", fontSize: typography.body },
});
