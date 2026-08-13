// Author: mertaygn, cglrgrkn
/**
 * HASTA KAPISI — AI analizinden / tedaviden ÖNCE hasta seçimi (2026-08-07)
 *
 * NEDEN: AI sonuçları `ai_analyses`'e, seanslar tedavi geçmişine HASTA ADIYLA yazılır. Hasta
 * seçilmeden yapılan işlem geçmişte SAHİPSİZ görünür; "bu sonuç/tedavi hangi hayvana aitti?"
 * sorusu sonradan cevaplanamaz.
 *
 * AKIŞ (üç profilde de aynı, terimler profile göre değişir):
 *   1. Hasta seçili değilse → seçim kartı çıkar (sert kipte modüller gizlenir).
 *   2. Kayıtlı hasta varsa → listeden seç (arama ile).
 *   3. Kayıtlı hasta YOKSA ya da yeni eklenecekse → **Hastalar sekmesine yönlendirilir**
 *      (2026-08-08 sahip kararı; satır-içi mini form KALDIRILDI — hasta yönetimi TEK yerde
 *      olsun, iki ayrı ekleme yüzeyi tutarsızlık üretiyordu). Ev sahibi profiline de
 *      "patients" rotası eklendiği için üç profilde de bu ekran mevcuttur.
 *   4. Seçim oturum boyunca korunur (AppNavContext) → her modülde yeniden sorulmaz.
 */
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from "react-native";
import { ChevronDown, PawPrint, Plus, Search, X } from "lucide-react-native";

import { Card } from "@/components/ui/Card";
import { useAppNav } from "@/context/AppNavContext";
import { useUserMode } from "@/context/UserModeContext";
import { apiGet } from "@/services/apiClient";
import { colors, radius, rf, rs, spacing } from "@/theme/tokens";

interface Hasta { id: string; name: string; species?: string }

/** Profile göre terimler — ev sahibi "hasta" demez, "evcil hayvanım" der. */
function sozluk(petOwner: boolean, researcher: boolean) {
  if (researcher) {
    return { tekil: "Örnek / Denek", secKisa: "Örnek seçin", bos: "Kayıtlı örnek yok.",
             ekle: "Örnek Ekle",
             uyari: "Analiz için önce bir örnek seçin — sonuç o kayda işlenecek." };
  }
  if (petOwner) {
    return { tekil: "Evcil Hayvanım", secKisa: "Hayvanınızı seçin",
             bos: "Henüz kayıtlı hayvanınız yok.", ekle: "Hayvan Ekle",
             uyari: "Analiz için önce hayvanınızı seçin — sonuç onun geçmişine işlenecek." };
  }
  return { tekil: "Hasta", secKisa: "Hasta seçin", bos: "Kayıtlı hasta yok.",
           ekle: "Hasta Ekle",
           uyari: "İşlem için önce hasta seçin — sonuç hasta geçmişine işlenecek." };
}

/**
 * @param soft `true` → çocuklar HER ZAMAN render edilir; seçim kartı yalnız üstte uyarı olarak
 *   durur. **Kontrol ekranı için ZORUNLU:** sert kapı orada ACİL DURDUR butonunu da gizlerdi ve
 *   bobinler çalışırken operatör onlara ulaşamazdı. Tedaviyi asıl engelleyen şey `requirePatient`
 *   (başlatma yolundaki sert kontrol); bu bileşen orada yalnız seçimi kolaylaştırır.
 *   `false` (varsayılan) → AI Hub gibi güvenlik-kritik kontrol İÇERMEYEN ekranlarda sert kapı.
 */
export function PatientGate({ children, soft = false }: { children: React.ReactNode; soft?: boolean }) {
  const { selectedPatient, setSelectedPatient, navigateTo } = useAppNav();
  const { isExpert, isResearcher } = useUserMode();
  const S = sozluk(!isExpert && !isResearcher, isResearcher);

  const [acik, setAcik] = useState(false);
  const [liste, setListe] = useState<Hasta[] | null>(null);
  const [ara, setAra] = useState("");

  const yukle = useCallback(async () => {
    const r = await apiGet<{ data?: Hasta[] } | null>("/patients", null, { silent: true });
    setListe(r?.data ?? []);
  }, []);

  useEffect(() => { if (acik && liste === null) void yukle(); }, [acik, liste, yukle]);

  const sec = (h: Hasta) => {
    setSelectedPatient({ id: h.id, name: h.name });
    setAcik(false);
    setAra("");
  };

  /** SAHİP KARARI 2026-08-08: "Hasta Ekle" satır-içi form AÇMAZ → Hastalar sekmesine götürür.
   *  Hasta yönetimi tek yerde toplanır ve orada sahip/yaş/kilo gibi alanlar da doldurulabilir. */
  const hastalaraGit = () => { setAcik(false); navigateTo("patients"); };

  const suzulmus = (liste ?? []).filter(
    (h) => !ara.trim() || h.name.toLowerCase().includes(ara.trim().toLowerCase()));

  const secici = (
    <View style={{ gap: spacing.sm }}>
      <View style={styles.secHead}>
        <Text style={styles.secTitle}>{S.secKisa}</Text>
        <TouchableOpacity onPress={() => setAcik(false)} accessibilityRole="button" accessibilityLabel="Kapat">
          <X color={colors.textMuted} size={rs(17)} />
        </TouchableOpacity>
      </View>

      {liste === null ? (
        <ActivityIndicator color={colors.primary} />
      ) : (
        <>
          {(liste.length > 0) && (
            <TextInput style={styles.input} value={ara} onChangeText={setAra}
              placeholder="Ara…" placeholderTextColor={colors.textSubtle}
              accessibilityLabel="Kayıtlarda ara" />
          )}
          {suzulmus.length === 0 ? (
            <Text style={styles.not}>{ara.trim() ? "Eşleşme yok." : S.bos}</Text>
          ) : (
            <ScrollView style={styles.listeKutu} nestedScrollEnabled>
              {suzulmus.map((h) => (
                <TouchableOpacity key={h.id} style={styles.satirOge} onPress={() => sec(h)}
                  accessibilityRole="button" accessibilityLabel={`Seç: ${h.name}`}>
                  <Text style={styles.ogeAd} numberOfLines={1}>{h.name}</Text>
                  {h.species ? <Text style={styles.ogeTur}>{h.species}</Text> : null}
                </TouchableOpacity>
              ))}
            </ScrollView>
          )}
          <TouchableOpacity style={styles.ghostBtn} onPress={hastalaraGit}
            accessibilityRole="button" accessibilityLabel={`${S.ekle} — Hastalar sekmesine git`}>
            <Plus color={colors.primary} size={rs(14)} />
            <Text style={[styles.ghostText, { color: colors.primary }]}>{S.ekle}</Text>
          </TouchableOpacity>
        </>
      )}
    </View>
  );

  // ── Seçili hasta yok → KAPI (soft kipte çocuklar yine render edilir) ────────
  if (!selectedPatient?.name) {
    return (
      <>
        <Card style={styles.gate}>
          <View style={styles.gateHead}>
            <PawPrint color={colors.primary} size={rs(20)} />
            <Text style={styles.gateTitle}>{S.secKisa}</Text>
          </View>
          <Text style={styles.gateHint}>{S.uyari}</Text>
          {acik ? secici : (
            <View style={styles.satir}>
              <TouchableOpacity style={styles.primaryBtn} onPress={() => setAcik(true)}
                accessibilityRole="button" accessibilityLabel={S.secKisa}>
                <Search color="#04121F" size={rs(15)} />
                <Text style={styles.primaryText}>{S.secKisa}</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.ghostBtn} onPress={hastalaraGit}
                accessibilityRole="button" accessibilityLabel={`${S.ekle} — Hastalar sekmesine git`}>
                <Plus color={colors.primary} size={rs(14)} />
                <Text style={[styles.ghostText, { color: colors.primary }]}>{S.ekle}</Text>
              </TouchableOpacity>
            </View>
          )}
        </Card>
        {soft ? children : null}
      </>
    );
  }

  // ── Seçili hasta var → üstte ince şerit + içerik ────────────────────────────
  return (
    <>
      <TouchableOpacity style={styles.bar} onPress={() => setAcik((v) => !v)}
        accessibilityRole="button" accessibilityLabel={`${S.tekil}: ${selectedPatient.name}. Değiştir.`}>
        <PawPrint color={colors.primary} size={rs(15)} />
        <Text style={styles.barLabel}>{S.tekil}:</Text>
        <Text style={styles.barValue} numberOfLines={1}>{selectedPatient.name}</Text>
        <ChevronDown color={colors.textMuted} size={rs(15)} />
      </TouchableOpacity>
      {acik ? <Card style={styles.gate}>{secici}</Card> : null}
      {children}
    </>
  );
}

const styles = StyleSheet.create({
  gate: { gap: spacing.sm },
  gateHead: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  gateTitle: { color: colors.text, fontSize: rf(15), fontWeight: "800" },
  gateHint: { color: colors.textMuted, fontSize: rf(12), lineHeight: rf(18) },
  bar: { flexDirection: "row", alignItems: "center", gap: rs(7), backgroundColor: colors.panel,
         borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
         paddingVertical: rs(8), paddingHorizontal: spacing.md, marginBottom: spacing.sm },
  barLabel: { color: colors.textMuted, fontSize: rf(12) },
  barValue: { flex: 1, color: colors.text, fontSize: rf(13), fontWeight: "700" },
  secHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  secTitle: { color: colors.text, fontSize: rf(14), fontWeight: "700" },
  input: { backgroundColor: colors.bg, borderWidth: 1, borderColor: colors.border,
           borderRadius: radius.md, color: colors.text, padding: spacing.sm, fontSize: rf(13) },
  listeKutu: { maxHeight: rs(190), borderWidth: 1, borderColor: colors.border, borderRadius: radius.md },
  satirOge: { flexDirection: "row", alignItems: "center", justifyContent: "space-between",
              paddingVertical: rs(9), paddingHorizontal: spacing.md,
              borderBottomWidth: 1, borderBottomColor: colors.border },
  ogeAd: { flex: 1, color: colors.text, fontSize: rf(13), fontWeight: "600" },
  ogeTur: { color: colors.textSubtle, fontSize: rf(11) },
  satir: { flexDirection: "row", gap: spacing.sm, alignItems: "center", flexWrap: "wrap" },
  primaryBtn: { flexDirection: "row", alignItems: "center", gap: rs(6), backgroundColor: colors.cyan,
                borderRadius: radius.md, paddingVertical: rs(10), paddingHorizontal: spacing.md },
  primaryText: { color: "#04121F", fontWeight: "800", fontSize: rf(13) },
  ghostBtn: { flexDirection: "row", alignItems: "center", gap: rs(6), borderWidth: 1,
              borderColor: colors.border, borderRadius: radius.md,
              paddingVertical: rs(9), paddingHorizontal: spacing.md },
  ghostText: { color: colors.textMuted, fontWeight: "700", fontSize: rf(12) },
  not: { color: colors.textSubtle, fontSize: rf(11) },
});
