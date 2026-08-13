// Author: mertaygn, cglrgrkn
import { useState } from "react";
import { ActivityIndicator, Modal, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { Link2, MonitorSmartphone, Wifi, X } from "lucide-react-native";

import { Button } from "@/components/ui/Button";
import { useToast } from "@/components/ui/ToastProvider";
import { useLiveData } from "@/context/LiveDataContext";
import { cihazaBaglan, eslesmeMesaji, KOD_MAX_UZUNLUK } from "@/services/pairing";
import { colors, radius, rf, rs, spacing } from "@/theme/tokens";

/**
 * CİHAZA BAĞLANMA REHBERİ (2026-08-13, sahip bildirimi).
 *
 * ARIZA: telefon ve cihaz AYNI AĞDA DEĞİLKEN ilk açılışta bağlantı kurulamıyordu — bu
 * beklenen bir durum — ama kullanıcı ne olduğunu ve NE YAPACAĞINI öğrenemiyordu. Ekranda
 * yalnız "Cihaza bağlanılamıyor — dokunup yeniden bağlan" şeridi vardı ve dokunmak AYNI
 * keşfi tekrarlıyordu. Oysa keşif merdiveninin uzaktan adımı KAYITLI bir `device_id` ister
 * (`discovery._discoverBackendImpl` adım 3); ilk açılışta o kimlik henüz yoktur. Yani farklı
 * ağdaki yeni kullanıcı için o düğme SONSUZA KADAR başarısız olacak bir işi tekrarlıyordu.
 *
 * Eşleştirme alanı vardı ama Ayarlar → "Uzaktan Erişim Bağlantısı" içinde gömülüydü; bağlantı
 * kuramamış bir kullanıcının oraya kendiliğinden gitmesi beklenemez.
 *
 * ÇÖZÜM: bağlanamama anında, olduğu yerde bir rehber. Kullanıcıya (a) neden bağlanamadığını,
 * (b) kodu cihazda TAM OLARAK nerede bulacağını, (c) girdiği yeri aynı ekranda verir.
 * Bir kez eşleşince kimlik saklanır → sonraki açılışlar merdivenin uzaktan adımıyla KENDİ
 * KENDİNE bağlanır; bu rehber bir daha çıkmaz.
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
              Cihaz bu ağda bulunamadı. Telefonunuz cihazla <Text style={styles.bold}>aynı Wi-Fi'de değilse</Text>{" "}
              (mobil veri ya da başka bir ağ) bu normaldir — aşağıdaki kodla bağlanabilirsiniz.
            </Text>

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

            {/* Aynı ağdaysa kod GEREKMEZ: bunu söylemek, gereksiz yere kod aramasını önler. */}
            <View style={styles.altBilgi}>
              <Wifi size={14} color={colors.textMuted} />
              <Text style={styles.altBilgiText}>
                Cihazla aynı Wi-Fi'ye bağlanırsanız kod gerekmez; uygulama cihazı kendi bulur.
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
  altBilgi: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-start" },
  altBilgiText: { flex: 1, color: colors.textMuted, fontSize: rf(12), lineHeight: rf(18) },
});
