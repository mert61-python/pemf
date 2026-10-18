// Author: mertaygn, cglrgrkn
/**
 * E-POSTA HESAPLARI — çoklu hesap menüsü (CH1 · Y151 / S-SG.6, sahip 2026-10-14: "ikisi de şimdi").
 *
 * Bu cihazda AÇIK e-posta hesapları (etkin işaretli) · başka hesaba tek dokunuşla geçiş · "Hesap ekle" · hesap başına "Çıkış" ·
 * "Tüm hesaplardan çık". Profil çipi menüsünden ve "Hekim Değiştir (bu cihaz)" penceresindeki bağlantıdan açılır.
 *
 * ⚠️ HESAP ≠ HEKİM (metin bunu ayırır): hesap = giriş yapılan E-POSTA (jeton, abonelik, AI geçmişi); hekim = bu cihazı paylaşan, PIN'le
 * seçilen kişi ("Hekim Değiştir (bu cihaz)"). Hesap geçişi hekim kilidini ATLATMAZ: çok kullanıcılı cihazda geçmeden ÖNCE seçili hekim
 * kilitlenir (sunucuda da), yeni hesapta yeniden seçilir.
 * ⚠️ HASTA GÜVENLİĞİ: seans sürerken / bobinler çalışırken / donanım belirsizken geçiş, ekleme ve ETKİN hesaptan çıkış KAPALI ve
 * nedeni yazılı (`hesapGecisiEngeli`, teardown koruması ile AYNI koşullar — A-59 / Y55). ACİL DURDUR bu pencerede de erişilebilir:
 * RN `Modal` kabuğun kayan düğmesini ÖRTER → pencere kendi `GlobalEmergencyStop`'unu çizer (Giriş / Karşılama ekranlarıyla aynı desen).
 * "Tüm hesaplardan çık" kabuğun MEVCUT teardown korumalı çıkışını çağırır (yeni akış yok).
 */
import { useState } from "react";
import { Modal, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { Check, LogOut, UserPlus } from "lucide-react-native";

import { Card } from "@/components/ui/Card";
import { GlobalEmergencyStop } from "@/components/ui/GlobalEmergencyStop";
import { useAuth } from "@/context/AuthContext";
import { useLiveData } from "@/context/LiveDataContext";
import { useOperatorOptional } from "@/context/OperatorContext";
import { platformConfirm } from "@/services/apiClient";
import { epostaAnahtari } from "@/services/hesapDeposu";
import { hesapGecisiEngeli, onaySonrasiEngel } from "@/services/hesapGecisi";
import { colors, radius, rf, rs, spacing, touch } from "@/theme/tokens";

export const HESAP_MENUSU_ACIKLAMA =
  "Hesap = giriş yaptığınız e-posta (jeton, abonelik, AI geçmişi). Açık hesaplar arasında tek dokunuşla geçebilirsiniz. Bu cihazı ortak " +
  "kullanan hekimler arasında geçmek için \"Hekim Değiştir (bu cihaz)\" (PIN) kullanılır.";

export function HesapMenusu({
  visible,
  onClose,
  onTumundenCik,
}: {
  visible: boolean;
  onClose: () => void;
  /** Kabuğun teardown korumalı çıkışı (AppShell `handleLogout`) — TÜM hesaplardan çıkar. */
  onTumundenCik: () => void;
}) {
  const { session, hesaplar, hesabaGec, hesaptanCik, hesapEkle } = useAuth();
  const { snapshot, donanimBelirsiz } = useLiveData();
  const op = useOperatorOptional();
  const [mesgul, setMesgul] = useState(false);
  const [hata, setHata] = useState("");

  const engel = hesapGecisiEngeli(snapshot, donanimBelirsiz);
  const liste = hesaplar && hesaplar.length > 0 ? hesaplar : session?.email ? [session.email] : [];
  const etkinMi = (e: string) => epostaAnahtari(e) === epostaAnahtari(session?.email);
  // Geçiş hekim kilidini ATLATMAZ: çok kullanıcılı cihazda seçili hekim kilitlenir (jeton sunucuda da iptal — D2.E14).
  const hekimiKilitle = () => {
    if (op?.multiUser && op.active) op.lock();
  };

  const kapat = () => {
    setHata("");
    onClose();
  };

  const gec = async (eposta: string) => {
    if (engel || mesgul || !hesabaGec) return;
    setMesgul(true);
    setHata("");
    hekimiKilitle();
    const r = await hesabaGec(eposta);
    setMesgul(false);
    if (r.ok) kapat();
    else setHata(r.hata || "Hesap değiştirilemedi.");
  };

  const cik = async (eposta: string) => {
    if (mesgul || !hesaptanCik) return;
    const etkin = etkinMi(eposta);
    if (etkin && engel) return; // etkin hesaptan çıkış = geçiş / söküm → seans sürerken kapalı
    const baska = liste.length > 1;
    const ok = await platformConfirm(
      "Hesaptan çık",
      etkin
        ? `${eposta} hesabından çıkılacak.` + (baska ? " Bu cihazda açık diğer hesaba geçilir." : " Tekrar girmek için e-posta ve şifre gerekir.")
        : `${eposta} bu cihazdan çıkarılacak; etkin hesabınız (${session?.email ?? ""}) değişmez.`,
      "Çıkış yap",
    );
    if (!ok) return;
    setMesgul(true);
    setHata("");
    if (etkin) {
      // S-SGI.6: onay penceresi açıkken seans başladıysa etkin hesaptan çıkış (= söküm / geçiş) İPTAL — taze durum backend'den.
      const sonra = await onaySonrasiEngel();
      if (sonra) {
        setMesgul(false);
        setHata(sonra);
        return;
      }
      hekimiKilitle();
    }
    const r = await hesaptanCik(eposta);
    setMesgul(false);
    if (!r.ok) setHata(r.hata || "Hesaptan çıkılamadı.");
  };

  const ekle = async () => {
    if (engel || mesgul || !hesapEkle) return;
    hekimiKilitle();
    kapat();
    await hesapEkle();
  };

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={kapat}>
      <Pressable style={styles.perde} onPress={kapat}>
        <Pressable onPress={() => {}} style={styles.kartKap}>
          <Card style={styles.kart}>
            <ScrollView contentContainerStyle={styles.govde} showsVerticalScrollIndicator={false}>
              <Text style={styles.baslik}>E-posta hesapları (bu cihaz)</Text>
              <Text style={styles.not} testID="hesap-menusu-aciklama">{HESAP_MENUSU_ACIKLAMA}</Text>
              {engel ? (
                <Text style={[styles.not, styles.uyari]} accessibilityRole="alert" testID="hesap-menusu-engel">{engel}</Text>
              ) : null}
              <View style={styles.liste}>
                {liste.map((e) => {
                  const etkin = etkinMi(e);
                  const gecPasif = etkin || !!engel || mesgul;
                  const cikPasif = mesgul || (etkin && !!engel);
                  return (
                    <View key={e} style={[styles.satir, etkin && styles.satirEtkin]} testID={`hesap-satiri-${e}`}>
                      <Pressable
                        style={[styles.satirAna, { minHeight: touch.min }]}
                        onPress={() => void gec(e)}
                        disabled={gecPasif}
                        accessibilityRole="button"
                        accessibilityState={{ disabled: gecPasif, selected: etkin }}
                        aria-disabled={gecPasif}
                        aria-selected={etkin}
                        accessibilityLabel={etkin ? `${e} — etkin hesap` : `${e} hesabına geç`}
                      >
                        {etkin ? <Check size={rs(15)} color={colors.primary} /> : <View style={{ width: rs(15) }} />}
                        <Text style={[styles.eposta, etkin && styles.epostaEtkin]} numberOfLines={1}>{e}</Text>
                        <Text style={etkin ? styles.rozetEtkin : styles.rozetGec}>{etkin ? "Etkin" : "Geç"}</Text>
                      </Pressable>
                      <Pressable
                        style={[styles.cikis, { minHeight: touch.min }, cikPasif && styles.pasif]}
                        onPress={() => void cik(e)}
                        disabled={cikPasif}
                        accessibilityRole="button"
                        accessibilityState={{ disabled: cikPasif }}
                        aria-disabled={cikPasif}
                        accessibilityLabel={`${e} hesabından çık`}
                      >
                        <LogOut size={rs(14)} color={colors.danger} />
                        <Text style={styles.cikisMetni}>Çıkış</Text>
                      </Pressable>
                    </View>
                  );
                })}
              </View>
              {hata ? <Text style={[styles.not, styles.hata]} accessibilityRole="alert" testID="hesap-menusu-hata">{hata}</Text> : null}
              <Pressable
                style={[styles.birincil, { minHeight: touch.min }, (!!engel || mesgul) && styles.pasif]}
                onPress={() => void ekle()}
                disabled={!!engel || mesgul}
                accessibilityRole="button"
                accessibilityState={{ disabled: !!engel || mesgul }}
                aria-disabled={!!engel || mesgul}
                accessibilityLabel="Hesap ekle"
              >
                <UserPlus size={rs(15)} color="#04121F" />
                <Text style={styles.birincilMetin}>Hesap ekle</Text>
              </Pressable>
              <View style={styles.altSatir}>
                <Pressable
                  style={[styles.ikincil, { minHeight: touch.min }]}
                  onPress={() => {
                    kapat();
                    onTumundenCik();
                  }}
                  accessibilityRole="button"
                  accessibilityLabel={liste.length > 1 ? "Tüm hesaplardan çık" : "Çıkış yap"}
                >
                  <Text style={[styles.ikincilMetin, { color: colors.danger }]}>
                    {liste.length > 1 ? "Tüm hesaplardan çık" : "Çıkış yap"}
                  </Text>
                </Pressable>
                <Pressable
                  style={[styles.ikincil, { minHeight: touch.min }]}
                  onPress={kapat}
                  accessibilityRole="button"
                  accessibilityLabel="Kapat"
                >
                  <Text style={styles.ikincilMetin}>Kapat</Text>
                </Pressable>
              </View>
            </ScrollView>
          </Card>
        </Pressable>
      </Pressable>
      {/* Ö.4-Y8: pencere açıkken de ACİL DURDUR erişilebilir (kabuğun kayan düğmesi Modal'ın ALTINDA kalır). */}
      <GlobalEmergencyStop />
    </Modal>
  );
}

const styles = StyleSheet.create({
  // Perde ve kart kabı da dokunulabilir (dışına dokununca kapanır / içine dokunuş yutulur) → dokunma tabanı (cırcır).
  perde: {
    flex: 1, minHeight: touch.min, backgroundColor: "rgba(0,0,0,0.55)", alignItems: "center", justifyContent: "center",
    padding: spacing.md,
  },
  kartKap: { width: "100%", minHeight: touch.min, maxWidth: rs(440), maxHeight: "92%" },
  kart: { width: "100%" },
  govde: { gap: spacing.sm },
  baslik: { color: colors.text, fontSize: rf(16), fontWeight: "800" },
  not: { color: colors.textMuted, fontSize: rf(12), lineHeight: rf(18) },
  uyari: { color: colors.warning },
  hata: { color: colors.danger },
  liste: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.md },
  satir: {
    flexDirection: "row", alignItems: "center", borderBottomWidth: 1, borderBottomColor: colors.border, paddingRight: spacing.xs,
  },
  satirEtkin: { backgroundColor: colors.panel },
  satirAna: { flex: 1, flexDirection: "row", alignItems: "center", gap: rs(8), paddingHorizontal: spacing.md },
  eposta: { flex: 1, color: colors.text, fontSize: rf(13), fontWeight: "600" },
  epostaEtkin: { color: colors.primary },
  rozetEtkin: { color: colors.primary, fontSize: rf(11), fontWeight: "800" },
  rozetGec: { color: colors.textMuted, fontSize: rf(11), fontWeight: "700" },
  cikis: { flexDirection: "row", alignItems: "center", gap: rs(4), paddingHorizontal: spacing.sm, justifyContent: "center" },
  cikisMetni: { color: colors.danger, fontSize: rf(12), fontWeight: "700" },
  pasif: { opacity: 0.5 },
  birincil: {
    flexDirection: "row", gap: rs(6), backgroundColor: colors.cyan, borderRadius: radius.md, alignItems: "center",
    justifyContent: "center", paddingVertical: rs(10),
  },
  birincilMetin: { color: "#04121F", fontWeight: "800", fontSize: rf(13) },
  altSatir: { flexDirection: "row", gap: spacing.sm },
  ikincil: {
    flex: 1, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, alignItems: "center", justifyContent: "center",
    paddingHorizontal: spacing.md,
  },
  ikincilMetin: { color: colors.textMuted, fontWeight: "700", fontSize: rf(12) },
});
