// Author: mertaygn, cglrgrkn
/**
 * OPERATÖR HIZLI GEÇİŞİ — tek makine, çoklu veteriner (2026-08-08).
 *
 * Üst barda "Aktif: Dr. X" çipi; dokununca cihazdaki operatörler listelenir, PIN ile saniyeler
 * içinde geçilir. İlk kullanımda giriş yapmış kişi kendini kaydeder (6 haneli PIN belirler).
 *
 * ⚠️ Bu ekran KİMLİK doğrular ama uygulamayı KİLİTLEMEZ: tam ekran bir kilit, seans sırasında
 * ACİL DURDUR'a erişimi geciktirirdi. Kimlik düşerse yalnız yazma yolları (hasta/seans/AI kaydı)
 * operatör seçilmesini ister — hasta güvenliği kontrolleri her zaman erişilebilir kalır.
 */
import { useCallback, useEffect, useState } from "react";
import { KeyboardAvoidingView, Modal, StyleSheet, Text, TextInput, TouchableOpacity, View, ScrollView } from "react-native";
import { KAV_BEHAVIOR_MODAL } from "@/hooks/useKeyboard";
import { Lock, LogOut, UserCheck, UserPlus } from "lucide-react-native";

import { Card } from "@/components/ui/Card";
import { useAuth } from "@/context/AuthContext";
import { useOperatorOptional } from "@/context/OperatorContext";
import { colors, radius, rf, rs, spacing } from "@/theme/tokens";

const PIN_UZUNLUK = 6;

export function OperatorSwitcher() {
  const { session } = useAuth();
  // Sağlayıcı yoksa (ör. AppShell'i tek başına render eden testler) çip HİÇ çizilmez —
  // uygulamayı çökertmek yerine görünmez olur. Kayıt yazan tüketiciler `useOperator` kullanır
  // ve orada sağlayıcı ZORUNLUDUR (bkz. OperatorContext).
  const ctx = useOperatorOptional();
  const [acik, setAcik] = useState(false);
  const [secili, setSecili] = useState<string>("");
  const [pin, setPin] = useState("");
  const [ad, setAd] = useState("");
  const [kayitKipi, setKayitKipi] = useState(false);
  // PIN DEĞİŞTİRME (2026-08-09): e-posta zaten kayıtlıysa backend mevcut PIN'i ister.
  const [eskiPin, setEskiPin] = useState("");
  const [eskiPinGerek, setEskiPinGerek] = useState(false);
  const [hata, setHata] = useState("");
  const [mesgul, setMesgul] = useState(false);

  useEffect(() => { if (acik) void ctx?.refresh(); }, [acik, ctx]);

  const kapat = useCallback(() => {
    setAcik(false); setPin(""); setHata(""); setSecili(""); setKayitKipi(false);
    setEskiPin(""); setEskiPinGerek(false);
  }, []);

  const gecisYap = useCallback(async () => {
    if (pin.length !== PIN_UZUNLUK || !secili) return;
    setMesgul(true); setHata("");
    const r = await ctx!.switchTo(secili, pin);
    setMesgul(false);
    if (r.ok) { kapat(); return; }
    setPin("");
    // ⚠️ Kilitliyken "PIN hatalı" DEME: kullanıcı boşuna denemeye devam eder.
    setHata(r.error === "locked"
      ? "Çok fazla hatalı deneme — bu operatör geçici olarak kilitlendi. Birkaç dakika bekleyin."
      : r.error === "net" ? "Cihaza ulaşılamadı." : "PIN hatalı.");
  }, [pin, secili, ctx, kapat]);

  const kaydet = useCallback(async () => {
    if (pin.length !== PIN_UZUNLUK || !ad.trim()) return;
    if (eskiPinGerek && eskiPin.length !== PIN_UZUNLUK) return;
    setMesgul(true); setHata("");
    const r = await ctx!.enroll(ad.trim(), pin, eskiPin);
    setMesgul(false);
    if (r.ok) { kapat(); return; }
    if (r.error === "need_old_pin") {
      // ⚠️ 2026-08-09: e-posta zaten kayıtlı. Bu bir hata değil, PIN DEĞİŞTİRME akışıdır —
      // sahipliği kanıtlamak için mevcut PIN istenir (bkz. auth_db.enroll_operator).
      setEskiPinGerek(true); setEskiPin("");
      setHata("Bu e-posta bu cihazda zaten kayıtlı. PIN'i değiştirmek için mevcut PIN'inizi girin.");
      return;
    }
    if (r.error === "locked") {
      setEskiPin("");
      setHata("Çok fazla hatalı deneme — bu operatör geçici olarak kilitlendi. Birkaç dakika bekleyin.");
      return;
    }
    setPin("");
    setHata(r.error === "net" ? "Cihaza ulaşılamadı." : "Kayıt yapılamadı. PIN 6 haneli olmalı.");
  }, [pin, ad, eskiPin, eskiPinGerek, ctx, kapat]);

  if (!ctx) return null;
  const { operators, active, multiUser, lock } = ctx;
  const etiket = active?.display_name || (multiUser ? "Operatör seçin" : (session?.email || ""));

  return (
    <>
      <TouchableOpacity style={styles.cip} onPress={() => setAcik(true)}
        accessibilityRole="button"
        accessibilityLabel={active ? `Aktif operatör: ${active.display_name}. Değiştir.` : "Operatör seç"}>
        <UserCheck color={active ? colors.primary : colors.warning} size={rs(14)} />
        <Text style={[styles.cipText, !active && { color: colors.warning }]} numberOfLines={1}>{etiket}</Text>
      </TouchableOpacity>

      <Modal visible={acik} transparent animationType="fade" onRequestClose={kapat}>
        {/* [S4 adım 5] Perde KAV (yalnız iOS 'padding'; Android Modal kendi penceresini daraltır),
            kart yüksekliği %92. PIN alanı klavye açılınca yatay telefonda ekran dışında kalıyordu. */}
        <KeyboardAvoidingView style={styles.perde} behavior={KAV_BEHAVIOR_MODAL}>
          <Card style={styles.kart}>
            <ScrollView
              contentContainerStyle={styles.govde}
              keyboardShouldPersistTaps="handled"
              showsVerticalScrollIndicator={false}
            >
            <Text style={styles.baslik}>{kayitKipi ? "Bu cihaza kaydol" : "Kullanıcı Değiştir"}</Text>

            {kayitKipi ? (
              <>
                <Text style={styles.not}>
                  {session?.email} olarak kaydolacaksınız. Belirlediğiniz 6 haneli PIN ile bundan
                  sonra internet olmadan da hızlıca geçiş yapabilirsiniz.
                </Text>
                <TextInput style={styles.giris} value={ad} onChangeText={setAd}
                  placeholder="Görünen adınız (ör. Dr. Ayşe Yılmaz)" placeholderTextColor={colors.textSubtle}
                  accessibilityLabel="Görünen ad" />
                {eskiPinGerek ? (
                  <TextInput style={styles.giris} value={eskiPin}
                    onChangeText={(t) => setEskiPin(t.replace(/\D/g, "").slice(0, PIN_UZUNLUK))}
                    placeholder="Mevcut PIN'iniz" placeholderTextColor={colors.textSubtle}
                    keyboardType="number-pad" secureTextEntry maxLength={PIN_UZUNLUK}
                    accessibilityLabel="Mevcut PIN" />
                ) : null}
              </>
            ) : (
              <ScrollView style={styles.liste} nestedScrollEnabled>
                {operators.length === 0 ? (
                  <Text style={styles.not}>Bu cihazda kayıtlı operatör yok.</Text>
                ) : operators.map((o) => (
                  <TouchableOpacity key={o.email}
                    style={[styles.satir, secili === o.email && styles.satirSecili]}
                    onPress={() => { setSecili(o.email); setPin(""); setHata(""); }}
                    accessibilityRole="button" accessibilityLabel={`Seç: ${o.display_name || o.email}`}>
                    <Text style={styles.satirAd} numberOfLines={1}>{o.display_name || o.email}</Text>
                    {o.locked ? <Lock color={colors.danger} size={rs(13)} /> : null}
                  </TouchableOpacity>
                ))}
              </ScrollView>
            )}

            {(secili || kayitKipi) ? (
              <TextInput style={styles.giris} value={pin} onChangeText={(t) => setPin(t.replace(/\D/g, "").slice(0, PIN_UZUNLUK))}
                placeholder={eskiPinGerek ? "Yeni 6 haneli PIN" : "6 haneli PIN"}
                placeholderTextColor={colors.textSubtle}
                keyboardType="number-pad" secureTextEntry maxLength={PIN_UZUNLUK}
                accessibilityLabel="PIN" />
            ) : null}

            {hata ? <Text style={styles.hata}>{hata}</Text> : null}

            <View style={styles.satirBtn}>
              {kayitKipi ? (
                <TouchableOpacity style={styles.birincil} onPress={kaydet}
                  disabled={mesgul || !ad.trim() || pin.length !== PIN_UZUNLUK
                            || (eskiPinGerek && eskiPin.length !== PIN_UZUNLUK)}
                  accessibilityRole="button" accessibilityLabel={eskiPinGerek ? "PIN'i değiştir" : "Kaydol"}>
                  <Text style={styles.birincilText}>
                    {mesgul ? "Kaydediliyor…" : eskiPinGerek ? "PIN'i Değiştir" : "Kaydol"}
                  </Text>
                </TouchableOpacity>
              ) : (
                <TouchableOpacity style={styles.birincil} disabled={mesgul || !secili || pin.length !== PIN_UZUNLUK}
                  onPress={gecisYap} accessibilityRole="button" accessibilityLabel="Geçiş yap">
                  <Text style={styles.birincilText}>{mesgul ? "Doğrulanıyor…" : "Geçiş Yap"}</Text>
                </TouchableOpacity>
              )}
              <TouchableOpacity style={styles.ikincil} onPress={kapat}
                accessibilityRole="button" accessibilityLabel="Kapat">
                <Text style={styles.ikincilText}>Kapat</Text>
              </TouchableOpacity>
            </View>

            <View style={styles.altSatir}>
              {!kayitKipi ? (
                <TouchableOpacity style={styles.metinBtn}
                  onPress={() => { setKayitKipi(true); setPin(""); setHata(""); setEskiPin(""); setEskiPinGerek(false); }}
                  accessibilityRole="button" accessibilityLabel="Bu cihaza kaydol">
                  <UserPlus color={colors.primary} size={rs(13)} />
                  <Text style={styles.metinBtnText}>Bu cihaza kaydol</Text>
                </TouchableOpacity>
              ) : (
                <TouchableOpacity style={styles.metinBtn}
                  onPress={() => { setKayitKipi(false); setPin(""); setHata(""); setEskiPin(""); setEskiPinGerek(false); }}
                  accessibilityRole="button" accessibilityLabel="Listeye dön">
                  <Text style={styles.metinBtnText}>Listeye dön</Text>
                </TouchableOpacity>
              )}
              {active ? (
                <TouchableOpacity style={styles.metinBtn} onPress={() => { lock(); kapat(); }}
                  accessibilityRole="button" accessibilityLabel="Oturumu kilitle">
                  <LogOut color={colors.textMuted} size={rs(13)} />
                  <Text style={[styles.metinBtnText, { color: colors.textMuted }]}>Kilitle</Text>
                </TouchableOpacity>
              ) : null}
            </View>
            </ScrollView>
          </Card>
        </KeyboardAvoidingView>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  cip: { flexDirection: "row", alignItems: "center", gap: rs(5), paddingVertical: rs(5),
         paddingHorizontal: spacing.sm, borderRadius: radius.md, borderWidth: 1,
         borderColor: colors.border, backgroundColor: colors.panel, maxWidth: rs(190) },
  cipText: { color: colors.text, fontSize: rf(11), fontWeight: "700", flexShrink: 1 },
  perde: { flex: 1, backgroundColor: "rgba(0,0,0,0.55)", alignItems: "center", justifyContent: "center",
           padding: spacing.md },
  kart: { width: "100%", maxWidth: rs(420), maxHeight: "92%" },
  govde: { gap: spacing.sm },
  baslik: { color: colors.text, fontSize: rf(16), fontWeight: "800" },
  not: { color: colors.textMuted, fontSize: rf(12), lineHeight: rf(18) },
  // [S4 adım 5] Sabit rs(200) yatay telefonda kartın tamamını yiyordu; kart zaten %92 ile
  // sınırlı ve gövde kaydırılıyor → iç liste tavanı düşürüldü, nestedScrollEnabled kalıyor.
  liste: { maxHeight: rs(160), borderWidth: 1, borderColor: colors.border, borderRadius: radius.md },
  satir: { flexDirection: "row", alignItems: "center", justifyContent: "space-between",
           paddingVertical: rs(11), paddingHorizontal: spacing.md,
           borderBottomWidth: 1, borderBottomColor: colors.border, minHeight: rs(44) },
  satirSecili: { backgroundColor: colors.panel },
  satirAd: { flex: 1, color: colors.text, fontSize: rf(13), fontWeight: "600" },
  giris: { backgroundColor: colors.bg, borderWidth: 1, borderColor: colors.border,
           borderRadius: radius.md, color: colors.text, padding: spacing.sm, fontSize: rf(14),
           letterSpacing: rs(2), minHeight: rs(44) },
  hata: { color: colors.danger, fontSize: rf(12) },
  satirBtn: { flexDirection: "row", gap: spacing.sm },
  birincil: { flex: 1, backgroundColor: colors.cyan, borderRadius: radius.md,
              paddingVertical: rs(11), alignItems: "center", minHeight: rs(44), justifyContent: "center" },
  birincilText: { color: "#04121F", fontWeight: "800", fontSize: rf(13) },
  ikincil: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
             paddingVertical: rs(11), paddingHorizontal: spacing.md, minHeight: rs(44), justifyContent: "center" },
  ikincilText: { color: colors.textMuted, fontWeight: "700", fontSize: rf(12) },
  altSatir: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  metinBtn: { flexDirection: "row", alignItems: "center", gap: rs(5), paddingVertical: rs(6) },
  metinBtnText: { color: colors.primary, fontSize: rf(12), fontWeight: "700" },
});
