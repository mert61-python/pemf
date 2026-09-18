// Author: mertaygn, cglrgrkn
import { useEffect, useState } from "react";
import { ActivityIndicator, Modal, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { Link2, MonitorSmartphone, RefreshCcw, ShieldAlert, Wifi, X } from "lucide-react-native";

import { Button } from "@/components/ui/Button";
import { useToast } from "@/components/ui/ToastProvider";
import { useLiveData } from "@/context/LiveDataContext";
import { agTanisiYap, taniMesaji, type AgTanisi } from "@/services/agTanisi";
import { cihazaBaglan, eslesmeMesaji, KOD_MAX_UZUNLUK } from "@/services/pairing";
import { colors, radius, rf, rs, spacing } from "@/theme/tokens";

/**
 * CİHAZA BAĞLANMA REHBERİ (2026-08-13, sahip bildirimi).
 *
 * ARIZA: telefon ve cihaz AYNI AĞDA DEĞİLKEN bağlantı kurulamıyordu — bu beklenen bir
 * durum — ama kullanıcı ne olduğunu ve NE YAPACAĞINI öğrenemiyordu. Ekranda yalnız
 * "Cihaza bağlanılamıyor — dokunup yeniden bağlan" şeridi vardı ve dokunmak AYNI keşfi
 * tekrarlıyordu; farklı ağda o keşif cihazı bulamaz. Eşleştirme alanı vardı ama Ayarlar →
 * "Uzaktan Erişim Bağlantısı" içinde gömülüydü; bağlantı kuramamış bir kullanıcının oraya
 * kendiliğinden gitmesi beklenemez.
 *
 * ⚠️ İLK TASARIM YANLIŞTI ve saha bunu gösterdi (2026-08-13, ikinci bildirim). Şerit
 * "daha önce eşleşilmiş mi" diye `getStoredDeviceId()`e bakıyor, yalnız kimlik YOKSA rehberi
 * açıyordu. Ama `checkHealth` HER başarılı bağlantıda kimliği saklar (`discovery.ts`) — yani
 * aynı ağda bir kez bağlanmış HERKESTE kimlik vardır. Sonuç: güncel APK'da bile rehber hiç
 * açılmadı, kullanıcı eski metni görmeye devam etti.
 *
 * ÇÖZÜM: kullanıcının hangi durumda olduğunu TAHMİN ETME. Çevrimdışıyken tek bir kapı açılır
 * ve İKİ yolu da sunar: (a) "Yeniden Dene" — aynı ağdaki geçici kopma için, (b) kodun cihazda
 * nerede yazdığı + giriş alanı — farklı ağ için. Hangisinin geçerli olduğunu kullanıcı bilir.
 *
 * ⚠️ Bağlanma kararını KENDİ İÇİNDE vermez: `services/pairing.cihazaBaglan` çağrılır — Ayarlar
 * ekranıyla AYNI yol. Güvenlik değişmezleri (health + kimlik doğrulama, token takası) tek
 * yerde durur; ikinci bir kopya onların birinde eskimesi demekti.
 */
export function DevicePairingGuide({ visible, onClose }: { visible: boolean; onClose: () => void }) {
  const { showToast } = useToast();
  const { reconnect } = useLiveData();
  const [kod, setKod] = useState("");
  const [baglaniyor, setBaglaniyor] = useState(false);
  const [tani, setTani] = useState<AgTanisi | null>(null);

  // ⚠️ Rehber AÇILDIĞINDA sebebi araştır (2026-08-14 saha bildirimi: modemde istemci izolasyonu
  // açıktı; ekran yalnız "cihaz bulunamadı" diyordu ve kullanıcının bunu bulma şansı yoktu).
  // Tanı ağ isteği yapar → yalnız görünürken ve bir kez; sonuç yoksa hiçbir şey gösterilmez.
  useEffect(() => {
    if (!visible) return;
    let iptal = false;
    agTanisiYap()
      .then((t) => { if (!iptal) setTani(t); })
      .catch(() => { /* tanı BAŞARISIZ olsa da rehber çalışır — sessiz geç */ });
    // ⚠️ Sıfırlama TEMİZLEMEDE: kapanışta eski teşhis silinmezse kullanıcı modemi düzeltip
    // rehberi yeniden açtığında BAYAT teşhisi görür (yeni tanı gelene kadar yanlış yönlendirme).
    return () => { iptal = true; setTani(null); };
  }, [visible]);

  const taniKutusu = tani ? taniMesaji(tani) : null;

  const bagla = async () => {
    const girdi = kod.trim();
    if (!girdi) return;
    setBaglaniyor(true);
    try {
      const sonuc = await cihazaBaglan(girdi);
      if (sonuc.durum === "ok") {
        reconnect(); // yeni adresle WS'i hemen tazele
        showToast(eslesmeMesaji(sonuc), "success");
        setKod("");
        onClose();
      } else {
        showToast(eslesmeMesaji(sonuc), "error");
      }
    } finally {
      setBaglaniyor(false);
    }
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={styles.backdrop}>
        <View style={styles.sheet}>
          <View style={styles.header}>
            <Link2 size={20} color={colors.primary} />
            <Text style={styles.title}>Cihaza bağlanın</Text>
            <Pressable
              onPress={onClose}
              style={styles.close}
              accessibilityRole="button"
              accessibilityLabel="Kapat"
              hitSlop={10}
            >
              <X size={20} color={colors.textMuted} />
            </Pressable>
          </View>

          <ScrollView contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
            <Text style={styles.lead}>
              Cihaz bulunamadı. Telefonunuz cihazla <Text style={styles.bold}>aynı Wi-Fi&apos;de değilse</Text>{" "}
              (mobil veri ya da başka bir ağ) bu normaldir.
            </Text>

            {/* SEBEP KUTUSU — yalnız KANIT varken çıkar (bkz. services/agTanisi). Tanı
                "bilinmiyor" ise hiçbir şey gösterilmez: yanlış teşhis, teşhissizlikten kötüdür. */}
            {taniKutusu && (
              <View style={styles.tani} testID="tani-kutusu">
                <ShieldAlert size={16} color={colors.warning} />
                <View style={styles.taniIcerik}>
                  <Text style={styles.taniBaslik}>{taniKutusu.baslik}</Text>
                  <Text style={styles.taniMetin}>{taniKutusu.metin}</Text>
                </View>
              </View>
            )}

            {/* ⚠️ İKİ YOL DA BURADA. Şerit artık kullanıcının hangi durumda olduğunu TAHMİN
                ETMİYOR (ilk tasarım "daha önce eşleşilmiş mi" diye bakıyordu ve o sinyal
                yanlıştı — bkz. AppShell notu). Aynı ağdaki geçici kopma için "yeniden dene",
                farklı ağ için kod girişi; kullanıcı hangisinin geçerli olduğunu kendisi bilir. */}
            <View style={styles.hizli}>
              <Text style={styles.hizliBaslik}>Aynı Wi-Fi&apos;de misiniz?</Text>
              <Text style={styles.hizliMetin}>
                Bağlantı geçici koptuysa yeniden aramak yeterlidir — kod gerekmez.
              </Text>
              <Button
                label="Yeniden Dene"
                variant="secondary"
                onPress={() => {
                  reconnect();
                  onClose();
                }}
                icon={<RefreshCcw size={16} color={colors.primary} />}
              />
            </View>

            <View style={styles.ayirac}>
              <View style={styles.ayiracCizgi} />
              <Text style={styles.ayiracMetin}>farklı ağdaysanız</Text>
              <View style={styles.ayiracCizgi} />
            </View>

            <View style={styles.adim}>
              <View style={styles.adimNo}>
                <Text style={styles.adimNoText}>1</Text>
              </View>
              <View style={styles.adimIcerik}>
                <Text style={styles.adimBaslik}>Cihazın ekranına bakın</Text>
                <Text style={styles.adimMetin}>
                  PEMF Vet uygulamasında <Text style={styles.bold}>Daha Fazla → Uzaktan Erişim Bağlantısı</Text>{" "}
                  bölümünde <Text style={styles.bold}>6 haneli eşleştirme kodu</Text> yazar.
                </Text>
              </View>
            </View>

            <View style={styles.adim}>
              <View style={styles.adimNo}>
                <Text style={styles.adimNoText}>2</Text>
              </View>
              <View style={styles.adimIcerik}>
                <Text style={styles.adimBaslik}>Kodu buraya girin</Text>
                <TextInput
                  value={kod}
                  onChangeText={(t) => setKod(t.toUpperCase())}
                  placeholder="ÖRN: A3F9K2"
                  placeholderTextColor={colors.textMuted}
                  autoCapitalize="characters"
                  autoCorrect={false}
                  maxLength={64}
                  style={styles.input}
                  accessibilityLabel="Eşleştirme kodu"
                  onSubmitEditing={bagla}
                  returnKeyType="go"
                />
                <Text style={styles.ipucu}>
                  Kod yerine cihaz kimliğini de yapıştırabilirsiniz ({KOD_MAX_UZUNLUK} karakterden uzun).
                </Text>
              </View>
            </View>

            <Button
              label={baglaniyor ? "Bağlanıyor…" : "Cihaza Bağlan"}
              onPress={bagla}
              disabled={baglaniyor || !kod.trim()}
              icon={baglaniyor ? <ActivityIndicator size="small" color={colors.white} /> : <Link2 size={16} color={colors.white} />}
            />

            <View style={styles.altBilgi}>
              <Wifi size={14} color={colors.textMuted} />
              <Text style={styles.altBilgiText}>
                Cihazla aynı Wi-Fi&apos;ye bağlanırsanız kod hiç gerekmez; uygulama cihazı kendi bulur.
              </Text>
            </View>
            <View style={styles.altBilgi}>
              <MonitorSmartphone size={14} color={colors.textMuted} />
              <Text style={styles.altBilgiText}>
                Bir kez eşleştikten sonra bu ekran bir daha çıkmaz — sonraki açılışlarda otomatik bağlanır.
              </Text>
            </View>
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.6)", justifyContent: "flex-end" },
  sheet: {
    backgroundColor: colors.panel,
    borderTopLeftRadius: radius.lg,
    borderTopRightRadius: radius.lg,
    maxHeight: "88%",
    borderTopWidth: 1,
    borderColor: colors.border,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.lg,
    paddingBottom: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  title: { flex: 1, color: colors.text, fontSize: rf(18), fontWeight: "800" },
  close: { padding: rs(4) },
  body: { padding: spacing.lg, gap: spacing.md },
  lead: { color: colors.textMuted, fontSize: rf(14), lineHeight: rf(21) },
  bold: { color: colors.text, fontWeight: "800" },
  adim: { flexDirection: "row", gap: spacing.md, alignItems: "flex-start" },
  adimNo: {
    width: rs(26),
    height: rs(26),
    borderRadius: rs(13),
    backgroundColor: colors.primarySoft,
    alignItems: "center",
    justifyContent: "center",
  },
  adimNoText: { color: colors.primary, fontWeight: "800", fontSize: rf(13) },
  adimIcerik: { flex: 1, gap: spacing.xs },
  adimBaslik: { color: colors.text, fontSize: rf(15), fontWeight: "700" },
  adimMetin: { color: colors.textMuted, fontSize: rf(13), lineHeight: rf(20) },
  input: {
    marginTop: spacing.xs,
    backgroundColor: colors.bg,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    color: colors.text,
    paddingHorizontal: spacing.md,
    paddingVertical: rs(12),
    fontSize: rf(18),
    letterSpacing: rs(2),
  },
  ipucu: { color: colors.textMuted, fontSize: rf(11) },
  tani: {
    flexDirection: "row",
    gap: spacing.sm,
    alignItems: "flex-start",
    backgroundColor: colors.warningSoft,
    borderWidth: 1,
    borderColor: colors.warning,
    borderRadius: radius.md,
    padding: spacing.md,
  },
  taniIcerik: { flex: 1, gap: spacing.xs },
  taniBaslik: { color: colors.text, fontSize: rf(14), fontWeight: "800" },
  taniMetin: { color: colors.textMuted, fontSize: rf(12), lineHeight: rf(18) },
  hizli: {
    backgroundColor: colors.bg,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.md,
    gap: spacing.sm,
  },
  hizliBaslik: { color: colors.text, fontSize: rf(14), fontWeight: "700" },
  hizliMetin: { color: colors.textMuted, fontSize: rf(12), lineHeight: rf(18) },
  ayirac: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  ayiracCizgi: { flex: 1, height: 1, backgroundColor: colors.border },
  ayiracMetin: { color: colors.textSubtle, fontSize: rf(11) },
  altBilgi: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-start" },
  altBilgiText: { flex: 1, color: colors.textMuted, fontSize: rf(12), lineHeight: rf(18) },
});
