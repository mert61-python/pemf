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

const PIN_UZUNLUK = 6;

/** Profile göre kişi terimi (karar #12: araştırmacı bir HEKİM değildir). Varsayılan: klinik (hekim). */
const TERIM = {
  veterinarian: { tekil: "hekim", cogul: "hekimler", cogulIle: "hekimlerle", baslik: "Hekim" },
  researcher: { tekil: "araştırmacı", cogul: "araştırmacılar", cogulIle: "araştırmacılarla", baslik: "Araştırmacı" },
  pet_owner: { tekil: "kişi", cogul: "kişiler", cogulIle: "kişilerle", baslik: "Kişi" },
} as const;

type Kip = keyof typeof TERIM;

export function OperatorSwitcher({ onBaskaHesap, kip }: {
  /** Mevcut çıkış akışı (AppShell `handleLogout`: teardown korumalı) — "Başka hesapla giriş yap" onu çağırır. */
  onBaskaHesap?: () => void;
  /** Etkin arayüz profili (yalnız metin ve Ev Sahibi tek-kullanıcı sadeleştirmesi için; erişim kapısı DEĞİL). */
  kip?: Kip | null;
} = {}) {
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
  const { operators, active, multiUser, lock, kimlikDbOkunamiyor } = ctx;
  // Y113: kimlik veritabanı okunamıyorsa çip "Operatör seçin" DEMEZ (liste okunamıyor, seçmek imkânsız) — arızayı adlandırır;
  // dokununca açılan pencere arızayı ve çareyi tam metinle söyler.
  const etiket = active?.display_name
    || (kimlikDbOkunamiyor ? "Kimlik veritabanı okunamıyor" : (multiUser ? "Operatör seçin" : (session?.email || "")));
  const t = TERIM[(kip && kip in TERIM ? kip : "veterinarian") as Kip];
  // SG.G7: Ev Sahibi + tek kullanıcılı cihaz → pencere yalnız hesap bilgisi (çok-hekimli klinik kavramı gösterilmez). Cihazda
  // kayıtlı operatör VARSA (çok kullanıcılı kip) tam pencere kalır: yazma yolları seçili kişi ister (Y103 / Y110 / Y116).
  const yalnizHesap = kip === "pet_owner" && !multiUser && !active && !kimlikDbOkunamiyor;
  const dakika = Math.round(AUTO_LOCK_MS / 60000);
  // SG.G7: pasif düğmenin NEDENİ (etiket gerçeği söylesin) — gösterilen ile `disabled` AYNI koşullardan.
  const gecisPasif = mesgul || !secili || pin.length !== PIN_UZUNLUK;
  const kaydolPasif = mesgul || !ad.trim() || pin.length !== PIN_UZUNLUK || (eskiPinGerek && eskiPin.length !== PIN_UZUNLUK);
  const pasifNedeni = mesgul ? "" : kayitKipi
    ? (!ad.trim() ? "Görünen adınızı yazın ve 6 haneli PIN belirleyin."
      : (eskiPinGerek && eskiPin.length !== PIN_UZUNLUK) ? "Mevcut 6 haneli PIN'inizi girin."
      : pin.length !== PIN_UZUNLUK ? "6 haneli PIN belirleyin." : "")
    : (operators.length === 0 ? (kimlikDbOkunamiyor ? "" : `Bu cihazda kayıtlı ${t.tekil} yok — önce "Bu cihaza kaydol".`)
      : !secili ? `Listeden ${t.tekil} seçin ve 6 haneli PIN'i girin.`
      : pin.length !== PIN_UZUNLUK ? "6 haneli PIN'i girin." : "");

  return (
    <>
      <TouchableOpacity style={styles.cip} onPress={() => setAcik(true)}
        accessibilityRole="button"
        accessibilityLabel={active ? `Aktif operatör: ${active.display_name}. Değiştir.`
          : kimlikDbOkunamiyor ? "Kimlik veritabanı okunamıyor. Ayrıntı için dokunun." : "Operatör seç"}>
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
              {kayitKipi ? "Bu cihaza kaydol" : yalnizHesap ? "Hesap" : `${t.baslik} Değiştir (bu cihaz)`}
            </Text>

            {yalnizHesap ? (
              <Text style={styles.not} testID="operator-aciklama">
                {session?.email ? `Giriş yapılan hesap: ${session.email}. ` : ""}Başka bir e-posta hesabına geçmek için çıkış yapıp
                o hesapla giriş yapın.
              </Text>
            ) : kayitKipi ? (
              <>
                <Text style={styles.not} testID="operator-aciklama">
                  {session?.email} olarak kaydolacaksınız. Bu cihazı başka {t.cogulIle} ortak kullanıyorsanız kaydolun: hasta, seans ve
                  AI kayıtları adınıza işlenir, &quot;Benim …&quot; süzgeçleri sizi gösterir, {t.cogul} arasında PIN&apos;le (internetsiz)
                  geçilir. Kaydolunca cihaz çok kullanıcılı kipe geçer: kayıt yazan işlemler seçili {t.tekil} ister,{" "}
                  {t.tekil} seçilmeden listeler kayıt göstermez ve {dakika} dk hareketsizlikte seçim düşer (seans sürerken düşmez).
                </Text>
                <TextInput style={styles.girisAd} value={ad} onChangeText={setAd}
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
              <>
              <Text style={styles.not} testID="operator-aciklama">
                Bu cihazı ortak kullanan {t.cogul} arasında PIN ile hızlı geçiş. E-posta hesabını değiştirmek için çıkış yapıp diğer
                hesapla giriş yapın.
              </Text>
              <ScrollView style={styles.liste} nestedScrollEnabled>
                {/* Y113: kimlik DB'si okunamıyorsa "kayıtlı operatör yok" DENMEZ — arıza + çare. */}
                {kimlikDbOkunamiyor ? (
                  <Text style={[styles.not, { color: colors.warning }]} accessibilityRole="alert">{KIMLIK_DB_OKUNAMIYOR}</Text>
                ) : null}
                {operators.length === 0 ? (
                  kimlikDbOkunamiyor ? null : <Text style={styles.not}>Bu cihazda kayıtlı {t.tekil} yok.</Text>
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
              </>
            )}

            {!yalnizHesap && (secili || kayitKipi) ? (
              <TextInput style={styles.giris} value={pin} onChangeText={(t) => setPin(t.replace(/\D/g, "").slice(0, PIN_UZUNLUK))}
                placeholder={eskiPinGerek ? "Yeni 6 haneli PIN" : "6 haneli PIN"}
                placeholderTextColor={colors.textSubtle}
                keyboardType="number-pad" secureTextEntry maxLength={PIN_UZUNLUK}
                accessibilityLabel="PIN" />
            ) : null}

            {hata ? <Text style={styles.hata}>{hata}</Text> : null}
            {/* SG.G7: pasif düğmenin NEDENİ — düğme basılmıyorsa neden basılmadığı söylenir. */}
            {!yalnizHesap && pasifNedeni ? <Text style={styles.not} testID="operator-pasif-nedeni">{pasifNedeni}</Text> : null}

            <View style={styles.satirBtn}>
              {yalnizHesap ? (
                onBaskaHesap ? (
                  <TouchableOpacity style={styles.birincil} onPress={() => { kapat(); onBaskaHesap(); }}
                    accessibilityRole="button" accessibilityLabel="Başka hesapla giriş yap">
                    <Text style={styles.birincilText}>Başka hesapla giriş yap</Text>
                  </TouchableOpacity>
                ) : null
              ) : kayitKipi ? (
                <TouchableOpacity style={[styles.birincil, kaydolPasif && styles.birincilPasif]} onPress={kaydet}
                  disabled={kaydolPasif}
                  accessibilityRole="button" accessibilityState={{ disabled: kaydolPasif }} aria-disabled={kaydolPasif}
                  accessibilityLabel={eskiPinGerek ? "PIN'i değiştir" : "Kaydol"}>
                  <Text style={[styles.birincilText, kaydolPasif && styles.birincilTextPasif]}>
                    {mesgul ? "Kaydediliyor…" : eskiPinGerek ? "PIN'i Değiştir" : "Kaydol"}
                  </Text>
                </TouchableOpacity>
              ) : (
                <TouchableOpacity style={[styles.birincil, gecisPasif && styles.birincilPasif]} disabled={gecisPasif}
                  onPress={gecisYap} accessibilityRole="button" accessibilityState={{ disabled: gecisPasif }}
                  aria-disabled={gecisPasif} accessibilityLabel="Geçiş yap">
                  <Text style={[styles.birincilText, gecisPasif && styles.birincilTextPasif]}>{mesgul ? "Doğrulanıyor…" : "Geçiş Yap"}</Text>
                </TouchableOpacity>
              )}
              <TouchableOpacity style={styles.ikincil} onPress={kapat}
                accessibilityRole="button" accessibilityLabel="Kapat">
                <Text style={styles.ikincilText}>Kapat</Text>
              </TouchableOpacity>
            </View>

            {!yalnizHesap && !kayitKipi && onBaskaHesap ? (
              <TouchableOpacity style={[styles.metinBtn, { minHeight: touch.min }]} onPress={() => { kapat(); onBaskaHesap(); }}
                accessibilityRole="button" accessibilityLabel="Başka hesapla giriş yap">
                <LogIn color={colors.primary} size={rs(13)} />
                <Text style={styles.metinBtnText}>Başka hesapla giriş yap</Text>
              </TouchableOpacity>
            ) : null}

            <View style={styles.altSatir}>
              {yalnizHesap ? <View /> : !kayitKipi ? (
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
