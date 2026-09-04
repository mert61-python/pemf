// Author: mertaygn, cglrgrkn
/**
 * KURTARMA KODU BANDI (2026-08-09 denetimi, ENGEL).
 *
 * Hasta kayıtları SQLCipher ile şifreli ve anahtar bu MAKİNEYE bağlı (DPAPI). Anakart/disk
 * ölürse — off-site yedek olsa bile — yedekler açılamaz. Bunun tek çaresi `KURTARMA-KODU.txt`
 * dosyasındaki 150-bit koddur.
 *
 * ⚠️ ASIL SORUN ŞUYDU: kod üretiliyor, dosyaya yazılıyor ve YALNIZCA log'a bir uyarı düşüyordu.
 * Veteriner log okumaz. Kod da şifreli veritabanıyla AYNI diskte duruyor → disk ölürse ikisi de
 * gider. Yani kurtarma mekanizması vardı ama operatör varlığını hiç öğrenmediği için pratikte
 * HİÇBİR ŞEY korumuyordu.
 *
 * Bant, operatör "makine dışına kopyaladım" diyene kadar KALICI kalır (kapatma düğmesi YOK):
 * bu, ertelenirse maliyeti tüm klinik geçmişi olan tek seferlik bir iştir.
 *
 * ⚠️ HASTA GÜVENLİĞİ: seans sürerken gösterilmez — bobinler hastanın üzerindeyken operatörün
 * ekranını yönetimsel bir uyarıyla bölmek kabul edilemez (MobileUpdateBanner ile aynı ilke).
 */
import { useCallback, useEffect, useState } from "react";
import { StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { ShieldAlert } from "lucide-react-native";

import { useLiveData } from "@/context/LiveDataContext";
import { apiGet, apiPost } from "@/services/apiClient";
import { colors, radius, rf, rs, spacing, touch } from "@/theme/tokens";

interface KurtarmaDurumu {
  warn?: boolean;
  codeFilePath?: string;
}

export function RecoveryCodeBanner() {
  const { snapshot } = useLiveData();
  const seansAktif = !!snapshot?.activeTreatment?.isActive;
  const [durum, setDurum] = useState<KurtarmaDurumu | null>(null);
  const [mesgul, setMesgul] = useState(false);

  useEffect(() => {
    let iptal = false;
    void (async () => {
      // `silent`: bu bir bilgilendirmedir; cihaz kapalıyken hata balonu çıkarmamalı.
      const r = await apiGet<KurtarmaDurumu | null>("/system/recovery-status", null, { silent: true });
      if (!iptal && r) setDurum(r);
    })();
    return () => { iptal = true; };
  }, []);

  const onayla = useCallback(async () => {
    setMesgul(true);
    const r = await apiPost<{ status?: string } | null>("/system/recovery-ack", {}, null,
      { silent: true });
    setMesgul(false);
    if (r?.status === "success") setDurum({ warn: false });
  }, []);

  if (!durum?.warn || seansAktif) return null;

  return (
    <View style={styles.bant} accessibilityRole="alert">
      <ShieldAlert color={colors.warning} size={rs(16)} />
      <View style={{ flex: 1 }}>
        <Text style={styles.baslik}>Kurtarma kodunuzu makine dışına kaydedin</Text>
        <Text style={styles.alt}>
          Hasta kayıtları bu bilgisayara bağlı bir anahtarla şifreli. Bilgisayar bozulursa
          yedekleri açmanın tek yolu kurtarma kodudur — ve kod şu an yalnızca bu bilgisayarda:
          {"\n"}{durum.codeFilePath || "KURTARMA-KODU.txt"}
        </Text>
      </View>
      <TouchableOpacity style={styles.btn} onPress={onayla} disabled={mesgul}
        accessibilityRole="button"
        accessibilityLabel="Kurtarma kodunu makine dışına kaydettiğimi onaylıyorum">
        <Text style={styles.btnText}>{mesgul ? "…" : "Kaydettim"}</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  bant: { flexDirection: "row", alignItems: "center", gap: spacing.sm,
          backgroundColor: colors.panel, borderWidth: 1, borderColor: colors.warning,
          borderRadius: radius.md, padding: spacing.sm, margin: spacing.sm },
  baslik: { color: colors.text, fontSize: rf(13), fontWeight: "800" },
  alt: { color: colors.textMuted, fontSize: rf(11), marginTop: rs(2), lineHeight: rf(16) },
  btn: { backgroundColor: colors.cyan, borderRadius: radius.md,
         paddingVertical: rs(9), paddingHorizontal: spacing.md, minHeight: touch.min,
         justifyContent: "center" },
  btnText: { color: "#04121F", fontWeight: "800", fontSize: rf(12) },
});
