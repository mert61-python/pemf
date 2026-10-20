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
 *
 * SG.G7 (sahip, 2026-10-13: "geçiş yap butonuna basılmıyor ne işe yarıyor bu buton mailler arası geçiş yapmıyor mu"): pencerenin
 * başlığı "Kullanıcı Değiştir" e-posta HESABI değiştirmek sanılıyordu; "Geçiş Yap" pasifken ETKİN görünüyordu (stil pasifliği
 * göstermiyordu) ve NEDEN basılmadığı söylenmiyordu; "Bu cihaza kaydol" amacını ve sonucunu anlatmıyordu; ad alanı PIN'in harf
 * aralıklı stilini taşıyordu. Artık: başlık ne yaptığını söyler ("Hekim Değiştir (bu cihaz)" — terim profile göre), tek satır
 * açıklama + mevcut çıkış akışına giden "Başka hesapla giriş yap" (yeni akış YOK: `onBaskaHesap` = AppShell'in teardown korumalı
 * çıkışı), pasif düğme soluk + erişilebilir pasif + neden satırı. Ev Sahibi profilinde cihaz tek kullanıcılıysa (kayıtlı operatör
 * yok) çok-hekimli klinik kavramı (liste / PIN / kaydol) gösterilmez; çip oturum e-postasını göstermeye devam eder. PIN kilidi,
 * kilitlenme (`lock`), Y113 davranışı DEĞİŞMEDİ.
 *
 * CH1 · Y151 (çoklu hesap): "Başka hesapla giriş yap" (çıkış akışı) → "E-posta hesapları" bağlantısı: `onBaskaHesap` artık hesap
 * menüsünü açar (`HesapMenusu` — açık hesaplar, geçiş, ekleme, hesap başına çıkış). Metin hesap (e-posta) ile hekimi (PIN) AYIRIR.
 */
import { useCallback, useEffect, useState } from "react";
import { KeyboardAvoidingView, Modal, StyleSheet, Text, TextInput, TouchableOpacity, View, ScrollView } from "react-native";
import { KAV_BEHAVIOR_MODAL } from "@/hooks/useKeyboard";
import { Lock, LogIn, LogOut, UserCheck, UserPlus } from "lucide-react-native";

import { Card } from "@/components/ui/Card";
import { useAuth } from "@/context/AuthContext";
import { AUTO_LOCK_MS, useOperatorOptional } from "@/context/OperatorContext";
import { KIMLIK_DB_OKUNAMIYOR } from "@/utils/patientScope";
import { colors, radius, rf, rs, spacing, touch } from "@/theme/tokens";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";

const PIN_UZUNLUK = 6;

/** Profile göre kişi terimi (karar #12: araştırmacı bir HEKİM değildir). Varsayılan: klinik (hekim). */
const terimler = (t: TFunction) => ({
  veterinarian: { tekil: t("hesap.terim.hekim.tekil"), cogul: t("hesap.terim.hekim.cogul"), cogulIle: t("hesap.terim.hekim.cogulIle"), baslik: t("hesap.terim.hekim.baslik") },
  researcher: { tekil: t("hesap.terim.arastirmaci.tekil"), cogul: t("hesap.terim.arastirmaci.cogul"), cogulIle: t("hesap.terim.arastirmaci.cogulIle"), baslik: t("hesap.terim.arastirmaci.baslik") },
  pet_owner: { tekil: t("hesap.terim.kisi.tekil"), cogul: t("hesap.terim.kisi.cogul"), cogulIle: t("hesap.terim.kisi.cogulIle"), baslik: t("hesap.terim.kisi.baslik") },
});

type Kip = "veterinarian" | "researcher" | "pet_owner";

export function OperatorSwitcher({ onBaskaHesap, kip }: {
  /** CH1: e-posta hesapları menüsünü aç (AppShell → `HesapMenusu`) — "E-posta hesapları" bağlantısı onu çağırır. */
  onBaskaHesap?: () => void;
  /** Etkin arayüz profili (yalnız metin ve Ev Sahibi tek-kullanıcı sadeleştirmesi için; erişim kapısı DEĞİL). */
  kip?: Kip | null;
} = {}) {
  const { t } = useTranslation();
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

  // ⚠️ 2-B B2B-1: bağımlılık `ctx` DEĞİL, kararlı `refresh`. `refresh` her çağrıda yeni bir liste kurar → bağlam değeri
  // değişir → `[acik, ctx]` effect'i yeniden koşup yine `refresh` çağırıyordu: pencere açıkken `/operators` istek fırtınası
  // (ölçüldü: 5 ms ağ gecikmesiyle saniyede 30). Kapı: __tests__/OperatorSwitcher.B2B1.istekFirtinasi.web.test.tsx.
  const yenile = ctx?.refresh;
  useEffect(() => { if (acik) void yenile?.(); }, [acik, yenile]);

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
      ? t("hesap.operator.cokHataliKilitli")
      : r.error === "net" ? t("hesap.operator.cihazaUlasilamadi") : t("hesap.operator.pinHatali"));
  }, [pin, secili, ctx, kapat, t]);

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
      setHata(t("hesap.operator.zatenKayitli"));
      return;
    }
    if (r.error === "locked") {
      setEskiPin("");
      setHata(t("hesap.operator.cokHataliKilitli"));
      return;
    }
    setPin("");
    setHata(r.error === "net" ? t("hesap.operator.cihazaUlasilamadi") : t("hesap.operator.kayitYapilamadi"));
  }, [pin, ad, eskiPin, eskiPinGerek, ctx, kapat, t]);

  if (!ctx) return null;
  const { operators, active, multiUser, lock, kimlikDbOkunamiyor } = ctx;
  // Y113: kimlik veritabanı okunamıyorsa çip "Operatör seçin" DEMEZ (liste okunamıyor, seçmek imkânsız) — arızayı adlandırır;
  // dokununca açılan pencere arızayı ve çareyi tam metinle söyler.
  const etiket = active?.display_name
    || (kimlikDbOkunamiyor ? t("hesap.operator.kimlikDbOkunamiyor") : (multiUser ? t("hesap.operator.operatorSecin") : (session?.email || "")));
  const TERIM = terimler(t);
  const terim = TERIM[(kip && kip in TERIM ? kip : "veterinarian") as Kip];
  // SG.G7: Ev Sahibi + tek kullanıcılı cihaz → pencere yalnız hesap bilgisi (çok-hekimli klinik kavramı gösterilmez). Cihazda
  // kayıtlı operatör VARSA (çok kullanıcılı kip) tam pencere kalır: yazma yolları seçili kişi ister (Y103 / Y110 / Y116).
  const yalnizHesap = kip === "pet_owner" && !multiUser && !active && !kimlikDbOkunamiyor;
  const dakika = Math.round(AUTO_LOCK_MS / 60000);
  // SG.G7: pasif düğmenin NEDENİ (etiket gerçeği söylesin) — gösterilen ile `disabled` AYNI koşullardan.
  const gecisPasif = mesgul || !secili || pin.length !== PIN_UZUNLUK;
  const kaydolPasif = mesgul || !ad.trim() || pin.length !== PIN_UZUNLUK || (eskiPinGerek && eskiPin.length !== PIN_UZUNLUK);
  const pasifNedeni = mesgul ? "" : kayitKipi
    ? (!ad.trim() ? t("hesap.operator.pasifAdPin")
      : (eskiPinGerek && eskiPin.length !== PIN_UZUNLUK) ? t("hesap.operator.pasifMevcutPin")
      : pin.length !== PIN_UZUNLUK ? t("hesap.operator.pasifPinBelirle") : "")
    : (operators.length === 0 ? (kimlikDbOkunamiyor ? "" : t("hesap.operator.pasifKayitliYok", { tekil: terim.tekil }))
      : !secili ? t("hesap.operator.pasifListedenSec", { tekil: terim.tekil })
      : pin.length !== PIN_UZUNLUK ? t("hesap.operator.pasifPinGir") : "");

  return (
    <>
      <TouchableOpacity style={styles.cip} onPress={() => setAcik(true)}
        accessibilityRole="button"
        accessibilityLabel={active ? t("hesap.operator.aktifOperatorEtiketi", { display_name: active.display_name })
          : kimlikDbOkunamiyor ? t("hesap.operator.kimlikDbEtiketi") : t("hesap.operator.operatorSecEtiketi")}>
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
            <Text style={styles.baslik}>
              {kayitKipi ? t("hesap.operator.buCihazaKaydol") : yalnizHesap ? t("hesap.operator.hesap") : t("hesap.operator.baslikDegistir", { baslik: terim.baslik })}
            </Text>

            {yalnizHesap ? (
              <Text style={styles.not} testID="operator-aciklama">
                {session?.email ? t("hesap.operator.girisYapilanHesap", { email: session.email }) : ""}{t("hesap.operator.baskaHesapAciklama")}
              </Text>
            ) : kayitKipi ? (
              <>
                <Text style={styles.not} testID="operator-aciklama">
                  {t("hesap.operator.kayitAciklama", { email: session?.email ?? "", cogulIle: terim.cogulIle, cogul: terim.cogul, tekil: terim.tekil, dakika })}
                </Text>
                <TextInput style={styles.girisAd} value={ad} onChangeText={setAd}
                  placeholder={t("hesap.operator.gorunenAdYer")} placeholderTextColor={colors.textSubtle}
                  accessibilityLabel={t("hesap.operator.gorunenAd")} />
                {eskiPinGerek ? (
                  <TextInput style={styles.giris} value={eskiPin}
                    onChangeText={(v) => setEskiPin(v.replace(/\D/g, "").slice(0, PIN_UZUNLUK))}
                    placeholder={t("hesap.operator.mevcutPinYer")} placeholderTextColor={colors.textSubtle}
                    keyboardType="number-pad" secureTextEntry maxLength={PIN_UZUNLUK}
                    accessibilityLabel={t("hesap.operator.mevcutPin")} />
                ) : null}
              </>
            ) : (
              <>
              <Text style={styles.not} testID="operator-aciklama">
                {t("hesap.operator.ortakKullanimAciklama", { cogul: terim.cogul })}
              </Text>
              <ScrollView style={styles.liste} nestedScrollEnabled>
                {/* Y113: kimlik DB'si okunamıyorsa "kayıtlı operatör yok" DENMEZ — arıza + çare. */}
                {kimlikDbOkunamiyor ? (
                  <Text style={[styles.not, { color: colors.warning }]} accessibilityRole="alert">{KIMLIK_DB_OKUNAMIYOR}</Text>
                ) : null}
                {operators.length === 0 ? (
                  kimlikDbOkunamiyor ? null : <Text style={styles.not}>{t("hesap.operator.kayitliYok", { tekil: terim.tekil })}</Text>
                ) : operators.map((o) => (
                  <TouchableOpacity key={o.email}
                    style={[styles.satir, secili === o.email && styles.satirSecili]}
                    onPress={() => { setSecili(o.email); setPin(""); setHata(""); }}
                    accessibilityRole="button" accessibilityLabel={t("hesap.operator.secEtiketi", { ad: o.display_name || o.email })}>
                    <Text style={styles.satirAd} numberOfLines={1}>{o.display_name || o.email}</Text>
                    {o.locked ? <Lock color={colors.danger} size={rs(13)} /> : null}
                  </TouchableOpacity>
                ))}
              </ScrollView>
              </>
            )}

            {!yalnizHesap && (secili || kayitKipi) ? (
              <TextInput style={styles.giris} value={pin} onChangeText={(v) => setPin(v.replace(/\D/g, "").slice(0, PIN_UZUNLUK))}
                placeholder={eskiPinGerek ? t("hesap.operator.yeniPinYer") : t("hesap.operator.pinYer")}
                placeholderTextColor={colors.textSubtle}
                keyboardType="number-pad" secureTextEntry maxLength={PIN_UZUNLUK}
                accessibilityLabel={t("hesap.operator.pin")} />
            ) : null}

            {hata ? <Text style={styles.hata}>{hata}</Text> : null}
            {/* SG.G7: pasif düğmenin NEDENİ — düğme basılmıyorsa neden basılmadığı söylenir. */}
            {!yalnizHesap && pasifNedeni ? <Text style={styles.not} testID="operator-pasif-nedeni">{pasifNedeni}</Text> : null}

            <View style={styles.satirBtn}>
              {yalnizHesap ? (
                onBaskaHesap ? (
                  <TouchableOpacity style={styles.birincil} onPress={() => { kapat(); onBaskaHesap(); }}
                    accessibilityRole="button" accessibilityLabel={t("kabuk.profil.epostaHesaplari")}>
                    <Text style={styles.birincilText}>{t("kabuk.profil.epostaHesaplari")}</Text>
                  </TouchableOpacity>
                ) : null
              ) : kayitKipi ? (
                <TouchableOpacity style={[styles.birincil, kaydolPasif && styles.birincilPasif]} onPress={kaydet}
                  disabled={kaydolPasif}
                  accessibilityRole="button" accessibilityState={{ disabled: kaydolPasif }} aria-disabled={kaydolPasif}
                  accessibilityLabel={eskiPinGerek ? t("hesap.operator.pinDegistirEtiketi") : t("hesap.operator.kaydol")}>
                  <Text style={[styles.birincilText, kaydolPasif && styles.birincilTextPasif]}>
                    {mesgul ? t("hesap.operator.kaydediliyor") : eskiPinGerek ? t("hesap.operator.pinDegistir") : t("hesap.operator.kaydol")}
                  </Text>
                </TouchableOpacity>
              ) : (
                <TouchableOpacity style={[styles.birincil, gecisPasif && styles.birincilPasif]} disabled={gecisPasif}
                  onPress={gecisYap} accessibilityRole="button" accessibilityState={{ disabled: gecisPasif }}
                  aria-disabled={gecisPasif} accessibilityLabel={t("hesap.operator.gecisYapEtiketi")}>
                  <Text style={[styles.birincilText, gecisPasif && styles.birincilTextPasif]}>{mesgul ? t("hesap.operator.dogrulaniyor") : t("hesap.operator.gecisYap")}</Text>
                </TouchableOpacity>
              )}
              <TouchableOpacity style={styles.ikincil} onPress={kapat}
                accessibilityRole="button" accessibilityLabel={t("ortak.kapat")}>
                <Text style={styles.ikincilText}>{t("ortak.kapat")}</Text>
              </TouchableOpacity>
            </View>

            {!yalnizHesap && !kayitKipi && onBaskaHesap ? (
              <TouchableOpacity style={[styles.metinBtn, { minHeight: touch.min }]} onPress={() => { kapat(); onBaskaHesap(); }}
                accessibilityRole="button" accessibilityLabel={t("kabuk.profil.epostaHesaplari")}>
                <LogIn color={colors.primary} size={rs(13)} />
                <Text style={styles.metinBtnText}>{t("hesap.operator.epostaHesaplariDegistirEkle")}</Text>
              </TouchableOpacity>
            ) : null}

            <View style={styles.altSatir}>
              {yalnizHesap ? <View /> : !kayitKipi ? (
                <TouchableOpacity style={styles.metinBtn}
                  onPress={() => { setKayitKipi(true); setPin(""); setHata(""); setEskiPin(""); setEskiPinGerek(false); }}
                  accessibilityRole="button" accessibilityLabel={t("hesap.operator.buCihazaKaydol")}>
                  <UserPlus color={colors.primary} size={rs(13)} />
                  <Text style={styles.metinBtnText}>{t("hesap.operator.buCihazaKaydol")}</Text>
                </TouchableOpacity>
              ) : (
                <TouchableOpacity style={styles.metinBtn}
                  onPress={() => { setKayitKipi(false); setPin(""); setHata(""); setEskiPin(""); setEskiPinGerek(false); }}
                  accessibilityRole="button" accessibilityLabel={t("hesap.operator.listeyeDonEtiketi")}>
                  <Text style={styles.metinBtnText}>{t("hesap.operator.listeyeDon")}</Text>
                </TouchableOpacity>
              )}
              {active ? (
                <TouchableOpacity style={styles.metinBtn} onPress={() => { lock(); kapat(); }}
                  accessibilityRole="button" accessibilityLabel={t("hesap.operator.kilitleEtiketi")}>
                  <LogOut color={colors.textMuted} size={rs(13)} />
                  <Text style={[styles.metinBtnText, { color: colors.textMuted }]}>{t("hesap.operator.kilitle")}</Text>
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
           borderBottomWidth: 1, borderBottomColor: colors.border, minHeight: touch.min },
  satirSecili: { backgroundColor: colors.panel },
  satirAd: { flex: 1, color: colors.text, fontSize: rf(13), fontWeight: "600" },
  giris: { backgroundColor: colors.bg, borderWidth: 1, borderColor: colors.border,
           borderRadius: radius.md, color: colors.text, padding: spacing.sm, fontSize: rf(14),
           letterSpacing: rs(2), minHeight: touch.min },
  // SG.G7: ad alanı PIN'in harf aralıklı stilini TAŞIMAZ ("G ö r ü n e n …" görünüyordu).
  girisAd: { backgroundColor: colors.bg, borderWidth: 1, borderColor: colors.border,
             borderRadius: radius.md, color: colors.text, padding: spacing.sm, fontSize: rf(14), minHeight: touch.min },
  hata: { color: colors.danger, fontSize: rf(12) },
  satirBtn: { flexDirection: "row", gap: spacing.sm },
  birincil: { flex: 1, backgroundColor: colors.cyan, borderRadius: radius.md,
              paddingVertical: rs(11), alignItems: "center", minHeight: touch.min, justifyContent: "center" },
  birincilText: { color: "#04121F", fontWeight: "800", fontSize: rf(13) },
  // SG.G7: pasif durum GÖRÜNÜR (eskiden etkin düğmeyle aynıydı → "basılmıyor").
  birincilPasif: { backgroundColor: colors.border, opacity: 0.6 },
  birincilTextPasif: { color: colors.textMuted },
  ikincil: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
             paddingVertical: rs(11), paddingHorizontal: spacing.md, minHeight: touch.min, justifyContent: "center" },
  ikincilText: { color: colors.textMuted, fontWeight: "700", fontSize: rf(12) },
  altSatir: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  metinBtn: { flexDirection: "row", alignItems: "center", gap: rs(5), paddingVertical: rs(6) },
  metinBtnText: { color: colors.primary, fontSize: rf(12), fontWeight: "700" },
});
