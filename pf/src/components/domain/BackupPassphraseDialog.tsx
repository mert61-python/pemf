// Author: mertaygn, cglrgrkn
/**
 * YEDEK PAROLASI DİYALOĞU (2026-08-09 denetimi, Tier 1).
 *
 * ARIZA: parola `window.prompt` ile TEK KEZ soruluyordu.
 *   • Yazım hatası fark edilmiyordu → dosya KALICI OLARAK açılamaz hâle geliyor ve bu, ancak
 *     yedeğe ihtiyaç duyulan gün (eski makine ölmüş, geri dönüş yok) anlaşılıyordu.
 *   • Asgari politika yoktu → tek karakterlik parola kabul ediliyordu; oysa bu dosya kliniğin
 *     TÜM hasta geçmişini taşır ve kopyası off-site'a gider, oradaki tek koruma paroladır.
 *   • `window.prompt` parolayı DÜZ METİN gösterir ve mobil/native'de hiç çalışmaz.
 *
 * Kural `MIN_PAROLA`da tek yerde; backend AYNI kuralı `utils/data_export.parola_gecerli_mi`
 * ile ayrıca uygular (istemci kontrolü kolaylıktır, kapı sunucudadır).
 */
import { useEffect, useState } from "react";
import { KeyboardAvoidingView, Modal, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from "react-native";
import { KAV_BEHAVIOR_MODAL } from "@/hooks/useKeyboard";
import { Eye, EyeOff } from "lucide-react-native";

import { Card } from "@/components/ui/Card";
import { colors, radius, rf, rs, spacing, touch } from "@/theme/tokens";

/** Backend `utils/data_export.MIN_PAROLA` ile AYNI olmalı. */
export const MIN_PAROLA = 12;

export type ParolaKipi = "olustur" | "gir";

export function BackupPassphraseDialog({
  visible, kip, onCancel, onSubmit,
}: {
  visible: boolean;
  /** "olustur" → iki kez sorulur (yazım hatası yedeği kurtarılamaz kılar); "gir" → tek alan. */
  kip: ParolaKipi;
  onCancel: () => void;
  onSubmit: (parola: string) => void;
}) {
  const [p1, setP1] = useState("");
  const [p2, setP2] = useState("");
  const [gizli, setGizli] = useState(true);

  useEffect(() => {
    if (visible) { setP1(""); setP2(""); setGizli(true); }
  }, [visible]);

  const olustur = kip === "olustur";
  const kisa = olustur && p1.length > 0 && p1.length < MIN_PAROLA;
  const uyusmuyor = olustur && p2.length > 0 && p1 !== p2;
  const gecerli = olustur
    ? p1.length >= MIN_PAROLA && p1 === p2
    : p1.length > 0;

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onCancel}>
      {/* [S4 adım 5] Perde KAV oldu (yalnız iOS 'padding'; Android Modal kendi penceresini daraltır)
          ve kart yüksekliği %92 ile sınırlandı. Yatay telefonda (yükseklik 360-430) parola alanları
          klavye açılınca ekran dışında kalıyordu; kart içeriği artık kaydırılabiliyor. */}
      <KeyboardAvoidingView style={styles.perde} behavior={KAV_BEHAVIOR_MODAL}>
        <Card style={styles.kart}>
          <ScrollView
            contentContainerStyle={styles.govde}
            keyboardShouldPersistTaps="handled"
            showsVerticalScrollIndicator={false}
          >
          <Text style={styles.baslik}>
            {olustur ? "Yedek parolası belirleyin" : "Yedek parolasını girin"}
          </Text>
          <Text style={styles.not}>
            {olustur
              ? `Bu parola olmadan yedek dosyası AÇILAMAZ ve kurtarılamaz. En az ${MIN_PAROLA} karakter olmalı; bir parola yöneticisine kaydedin.`
              : "Yedek oluşturulurken belirlediğiniz parolayı girin."}
          </Text>

          <View style={styles.girisSatiri}>
            <TextInput style={styles.giris} value={p1} onChangeText={setP1}
              placeholder={olustur ? `Parola (en az ${MIN_PAROLA} karakter)` : "Parola"}
              placeholderTextColor={colors.textSubtle}
              secureTextEntry={gizli} autoCapitalize="none" autoCorrect={false}
              accessibilityLabel="Yedek parolası" />
            <TouchableOpacity onPress={() => setGizli((g) => !g)} style={styles.goz}
              accessibilityRole="button"
              accessibilityLabel={gizli ? "Parolayı göster" : "Parolayı gizle"}>
              {gizli ? <Eye color={colors.textMuted} size={rs(16)} />
                     : <EyeOff color={colors.textMuted} size={rs(16)} />}
            </TouchableOpacity>
          </View>

          {olustur ? (
            <TextInput style={styles.giris} value={p2} onChangeText={setP2}
              placeholder="Parolayı tekrar girin" placeholderTextColor={colors.textSubtle}
              secureTextEntry={gizli} autoCapitalize="none" autoCorrect={false}
              accessibilityLabel="Yedek parolası tekrar" />
          ) : null}

          {kisa ? <Text style={styles.hata}>En az {MIN_PAROLA} karakter olmalı.</Text> : null}
          {uyusmuyor ? <Text style={styles.hata}>Parolalar aynı değil.</Text> : null}

          <View style={styles.satirBtn}>
            <TouchableOpacity style={[styles.birincil, !gecerli && styles.pasif]}
              disabled={!gecerli} onPress={() => onSubmit(p1)}
              accessibilityRole="button" accessibilityLabel={olustur ? "Yedeği oluştur" : "Devam et"}>
              <Text style={styles.birincilText}>{olustur ? "Yedeği Oluştur" : "Devam"}</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.ikincil} onPress={onCancel}
              accessibilityRole="button" accessibilityLabel="Vazgeç">
              <Text style={styles.ikincilText}>Vazgeç</Text>
            </TouchableOpacity>
          </View>
          </ScrollView>
        </Card>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  perde: { flex: 1, backgroundColor: "rgba(0,0,0,0.55)", alignItems: "center",
           justifyContent: "center", padding: spacing.md },
  // gap karttan ScrollView içeriğine taşındı: kart artık yalnız kaydırıcıyı barındırıyor.
  kart: { width: "100%", maxWidth: rs(440), maxHeight: "92%" },
  govde: { gap: spacing.sm },
  baslik: { color: colors.text, fontSize: rf(16), fontWeight: "800" },
  not: { color: colors.textMuted, fontSize: rf(12), lineHeight: rf(18) },
  girisSatiri: { flexDirection: "row", alignItems: "center", gap: spacing.xs },
  giris: { flex: 1, backgroundColor: colors.bg, borderWidth: 1, borderColor: colors.border,
           borderRadius: radius.md, color: colors.text, padding: spacing.sm,
           fontSize: rf(14), minHeight: touch.min },
  goz: { padding: spacing.sm, minHeight: touch.min, justifyContent: "center" },
  hata: { color: colors.danger, fontSize: rf(12) },
  satirBtn: { flexDirection: "row", gap: spacing.sm },
  birincil: { flex: 1, backgroundColor: colors.cyan, borderRadius: radius.md,
              paddingVertical: rs(11), alignItems: "center", minHeight: touch.min,
              justifyContent: "center" },
  pasif: { opacity: 0.5 },
  birincilText: { color: "#04121F", fontWeight: "800", fontSize: rf(13) },
  ikincil: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
             paddingVertical: rs(11), paddingHorizontal: spacing.md, minHeight: touch.min,
             justifyContent: "center" },
  ikincilText: { color: colors.textMuted, fontWeight: "700", fontSize: rf(12) },
});
