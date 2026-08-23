// Author: mertaygn, cglrgrkn
/**
 * UpdateBanner — uygulama (APK) güncelleme bildirimi.
 * • Uygulama (APK): "İndir" → yeni APK indirme linki açılır (sideload).
 * Güncelleme yoksa hiçbir şey göstermez. AppShell'de connection banner'ın altına yerleşir.
 *
 * ⚠️ CİHAZ YAZILIMI (EXE) SATIRI KALDIRILDI — 2026-08-09 denetimi, Tier 3 ("tek güncelleme
 * kanalı"). O satır backend'in `/api/update/apply` ucunu çağırıyordu; uç bir Inno installer'ı
 * çalıştırıp PEMF Vet Client'ın (launcher) yönettiği kurulumun YANINA ikinci bir backend + ikinci
 * veri kökü kurardı → seanslar iki ayrı hasta veritabanına bölünür, ikisi de eksiksiz görünürdü.
 * Cihaz yazılımını artık YALNIZ launcher günceller (katmanlı paket + atomik takas + sağlık kapılı
 * geri alma). Uç kapatıldı; buton da kaldırıldı — "dokun ve güncelle" deyip hata veren bir düğme
 * bırakmak, düğmeyi hiç koymamaktan kötüdür.
 */
import { useCallback, useEffect, useState } from "react";
import { View, Text, Pressable, StyleSheet, Linking } from "react-native";
import { colors, spacing, rf, rs } from "@/theme/tokens";
import { useDonanimCalisiyor } from "@/hooks/useDonanimCalisiyor";
import { checkMobileUpdate, type MobileUpdate } from "@/services/updates";

export function UpdateBanner() {
  const [mobile, setMobile] = useState<MobileUpdate>({ available: false });
  // ⚠️ HASTA GÜVENLİĞİ (denetim 2026-08-23, M5): bu bant hiçbir seans/bobin kapısı tanımıyordu.
  // Kardeş bantlarda kapı VARDI ve aynı gün ortak kancaya bağlandı; bu üçüncü yüzey geride
  // kalmıştı — bobin hastanın üzerinde ENERJİLİYKEN çizilebiliyor ve dokunmak operatörü ACİL
  // DURDUR'un bulunduğu uygulamadan TARAYICIYA çıkarıyordu.
  const donanimCalisiyor = useDonanimCalisiyor();

  const refresh = useCallback(async () => {
    try { setMobile(await checkMobileUpdate()); } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 6 * 3600 * 1000); // 6 saatte bir
    return () => clearInterval(id);
  }, [refresh]);

  const downloadMobile = useCallback(() => {
    if (mobile.apkUrl) Linking.openURL(mobile.apkUrl).catch(() => {});
  }, [mobile.apkUrl]);

  if (!mobile.available || donanimCalisiyor) return null;

  return (
    <View style={styles.wrap}>
      <Pressable style={styles.row} onPress={downloadMobile} accessibilityRole="button">
        <Text style={styles.icon}>📲</Text>
        <Text style={styles.txt} numberOfLines={2}>
          Uygulama güncellemesi var (v{mobile.latestVersion}) — Dokun ve İndir
        </Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    backgroundColor: "#0a2740",
    borderBottomColor: colors.border,
    borderBottomWidth: 1,
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.sm,
    gap: spacing.xs,
  },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.sm, minHeight: rs(30) },
  icon: { fontSize: rf(14) },
  txt: { color: "#7dd3fc", fontSize: rf(13), fontWeight: "700", flex: 1 },
});
