// Author: mertaygn, cglrgrkn
/**
 * HEKİM DEĞERLENDİRMESİ KONTROLLERİ (2026-08-06, sahip isteği: "veteriner red/onay/düzeltme")
 *
 * AI çıktısı bir ÖNERİdir; klinik karar hekimindir. Bu kontroller kararı kaydın YANINA yazar —
 * AI'ın sonucu DEĞİŞMEZ, böylece sonradan "model ne demişti?" sorusu cevaplanabilir.
 *
 * KURALLAR:
 *  * Red ve düzeltme GEREKÇE ister (boş bir "reddedildi" denetim izinde işe yaramaz).
 *  * Onay notsuz olabilir — hekimi gereksiz yere yormamak için.
 *  * Karar verilmiş kayıt yeniden değerlendirilebilir (klinik görüş güncellenebilir), ama her
 *    seferinde KİM ve NE ZAMAN yeniden yazılır.
 */
import { useState } from "react";
import { StyleSheet, Text, TextInput, TouchableOpacity, View } from "react-native";
import { CheckCircle2, PencilLine, XCircle } from "lucide-react-native";

import { colors, radius, rf, rs, spacing } from "@/theme/tokens";

export type ReviewStatus = "" | "approved" | "rejected" | "corrected";

export const REVIEW_LABEL: Record<string, string> = {
  approved: "Hekim onayladı",
  rejected: "Hekim reddetti",
  corrected: "Hekim düzeltti",
};

const REVIEW_COLOR: Record<string, string> = {
  approved: colors.success,
  rejected: colors.danger,
  corrected: colors.warning,
};

/** Kart başlığında gösterilen küçük durum rozeti. Değerlendirilmemişse HİÇBİR ŞEY göstermez —
 *  "değerlendirilmedi" rozeti her kartta gürültü yapar; asıl bilgi karar VERİLMİŞ olmasıdır. */
export function ReviewBadge({ status }: { status?: ReviewStatus }) {
  if (!status) return null;
  return (
    <Text style={[s.badge, { color: REVIEW_COLOR[status], borderColor: REVIEW_COLOR[status] }]}>
      {REVIEW_LABEL[status]}
    </Text>
  );
}

/** Yarım kalmış değerlendirme taslağı (red/düzeltme formu + gerekçe). YALNIZ BELLEKTE tutulur — diske yazılmaz (KVKK). */
export interface DegerlendirmeTaslagi {
  mode: null | "rejected" | "corrected";
  text: string;
}

/** D2.E12: sunucu değerlendirmeyi kaydedemeyince formda gösterilen metin (gerekçe silinmez). */
export const KAYDEDILEMEDI_METNI = "Değerlendirme kaydedilemedi — gerekçeniz korunuyor. Tekrar deneyin.";

export function AiReviewControls({
  status, note, reviewedBy, reviewedAt, busy, onSubmit, taslak, onTaslakDegis,
}: {
  status?: ReviewStatus;
  note?: string;
  reviewedBy?: string;
  reviewedAt?: string;
  busy?: boolean;
  /** `false` (ya da `false` çözen söz) = KAYDEDİLEMEDİ → form ve gerekçe korunur; diğer her dönüş başarı sayılır. */
  onSubmit: (status: Exclude<ReviewStatus, "">, note: string) => void | boolean | Promise<boolean | void>;
  /** Verilirse taslak ÜST bileşende tutulur (kart kapanıp açılınca da kaybolmaz — D2.E12). */
  taslak?: DegerlendirmeTaslagi;
  onTaslakDegis?: (t: DegerlendirmeTaslagi) => void;
}) {
  const [yerel, setYerel] = useState<DegerlendirmeTaslagi>({ mode: null, text: "" });
  const t = taslak ?? yerel;
  const taslakYaz = (yeni: DegerlendirmeTaslagi) => (onTaslakDegis ? onTaslakDegis(yeni) : setYerel(yeni));
  const { mode, text } = t;
  const setMode = (m: DegerlendirmeTaslagi["mode"]) => taslakYaz({ mode: m, text: m === null ? "" : text });
  const setText = (x: string) => taslakYaz({ mode, text: x });
  const [hata, setHata] = useState("");

  /** ⚠️ D2.E12 (İG-6.115): gerekçe sunucu BAŞARI dönene dek KORUNUR. Eskiden form istek dönmeden kapanıp metin
   *  siliniyordu — 500/503'te hekimin yazdığı red/düzeltme gerekçesi kayboluyordu (ölçüldü). */
  const gonder = async (st: Exclude<ReviewStatus, "">, nt: string) => {
    setHata("");
    const sonuc = await Promise.resolve(onSubmit(st, nt));
    if (sonuc === false) {
      setHata(KAYDEDILEMEDI_METNI);
      return;
    }
    taslakYaz({ mode: null, text: "" });
  };

  const gerekceZorunlu = mode !== null;
  const gonderilebilir = !busy && (!gerekceZorunlu || text.trim().length > 0);

  return (
    <View style={s.wrap}>
      {status ? (
        <View style={s.existing}>
          <Text style={[s.existingTitle, { color: REVIEW_COLOR[status] }]}>
            {REVIEW_LABEL[status]}
          </Text>
          {note ? <Text style={s.existingNote}>{note}</Text> : null}
          <Text style={s.existingMeta}>
            {[reviewedBy, reviewedAt].filter(Boolean).join(" · ")}
          </Text>
        </View>
      ) : (
        <Text style={s.prompt}>
          Bu AI sonucu değerlendirilmedi. Klinik karar hekimindir.
        </Text>
      )}

      {mode ? (
        <View style={s.form}>
          <Text style={s.formLabel}>
            {mode === "rejected" ? "Red gerekçesi" : "Doğru teşhis / düzeltme"}
          </Text>
          <TextInput
            style={s.input}
            value={text}
            onChangeText={setText}
            multiline
            placeholder={mode === "rejected"
              ? "Örn. klinik bulgularla uyuşmuyor"
              : "Örn. gerçek teşhis: idiyopatik sistit"}
            placeholderTextColor={colors.textSubtle}
            accessibilityLabel={mode === "rejected" ? "Red gerekçesi" : "Düzeltme açıklaması"}
          />
          {hata ? <Text style={s.hata} accessibilityRole="alert">{hata}</Text> : null}
          <View style={s.row}>
            <TouchableOpacity style={[s.btn, s.ghost]} onPress={() => { setHata(""); setMode(null); }}>
              <Text style={s.ghostText}>Vazgeç</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[s.btn, mode === "rejected" ? s.danger : s.warn, !gonderilebilir && s.disabled]}
              disabled={!gonderilebilir}
              onPress={() => { void gonder(mode, text.trim()); }}
              accessibilityRole="button"
              accessibilityLabel={mode === "rejected" ? "Reddi kaydet" : "Düzeltmeyi kaydet"}
            >
              <Text style={s.solidText}>Kaydet</Text>
            </TouchableOpacity>
          </View>
        </View>
      ) : (
        <View style={s.row}>
          {hata ? <Text style={s.hata} accessibilityRole="alert">{hata}</Text> : null}
          <TouchableOpacity
            style={[s.btn, s.ghost, busy && s.disabled]}
            disabled={!!busy}
            onPress={() => { void gonder("approved", ""); }}
            accessibilityRole="button"
            accessibilityLabel="AI sonucunu onayla"
          >
            <CheckCircle2 size={rs(14)} color={colors.success} />
            <Text style={[s.ghostText, { color: colors.success }]}>Onayla</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[s.btn, s.ghost, busy && s.disabled]}
            disabled={!!busy}
            onPress={() => setMode("rejected")}
            accessibilityRole="button"
            accessibilityLabel="AI sonucunu reddet"
          >
            <XCircle size={rs(14)} color={colors.danger} />
            <Text style={[s.ghostText, { color: colors.danger }]}>Reddet</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[s.btn, s.ghost, busy && s.disabled]}
            disabled={!!busy}
            onPress={() => setMode("corrected")}
            accessibilityRole="button"
            accessibilityLabel="AI sonucunu düzelt"
          >
            <PencilLine size={rs(14)} color={colors.warning} />
            <Text style={[s.ghostText, { color: colors.warning }]}>Düzelt</Text>
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { marginTop: spacing.sm, paddingTop: spacing.sm, borderTopWidth: 1, borderTopColor: colors.border, gap: spacing.xs },
  prompt: { color: colors.textSubtle, fontSize: rf(11) },
  existing: { backgroundColor: colors.bgAlt, borderRadius: radius.md, padding: spacing.sm, gap: rs(2) },
  existingTitle: { fontSize: rf(12), fontWeight: "800" },
  existingNote: { color: colors.text, fontSize: rf(12) },
  existingMeta: { color: colors.textSubtle, fontSize: rf(10) },
  row: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" },
  btn: { flexDirection: "row", alignItems: "center", gap: rs(5), paddingVertical: rs(7), paddingHorizontal: spacing.sm, borderRadius: radius.md },
  ghost: { borderWidth: 1, borderColor: colors.border },
  ghostText: { color: colors.textMuted, fontSize: rf(12), fontWeight: "700" },
  danger: { backgroundColor: colors.danger },
  warn: { backgroundColor: colors.warning },
  solidText: { color: "#0B1220", fontSize: rf(12), fontWeight: "800" },
  disabled: { opacity: 0.5 },
  hata: { color: colors.danger, fontSize: rf(11), fontWeight: "700", width: "100%" },
  form: { gap: spacing.xs },
  formLabel: { color: colors.textMuted, fontSize: rf(11) },
  input: { minHeight: rs(56), backgroundColor: colors.bg, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, color: colors.text, padding: spacing.sm, fontSize: rf(12), textAlignVertical: "top" },
  badge: { fontSize: rf(10), fontWeight: "800", borderWidth: 1, borderRadius: rs(6), paddingHorizontal: rs(6), paddingVertical: rs(2) },
});
