// Author: mertaygn, cglrgrkn
/**
 * VERİ KLASÖRÜ AĞ PAYLAŞIMINDA BANDI — Y118 (sahip kararı, S-B2B2.3).
 *
 * Veri klasörünün (`PEMF_DATA_DIR` / `%APPDATA%`) bir ağ paylaşımında (UNC ya da eşlenmiş ağ sürücüsü) olması
 * DESTEKLENMEZ: SQLite'ın dosya kilitleri orada güvenilir değil, eşzamanlı yazımda tıbbi kayıt veritabanı bozulabilir.
 * Backend bunu açılışta günlüğe yazar ve sağlık ucunda (`veriKokuAgda`) bildirir; bu bant operatöre söyler. Klasör yolu
 * banda GELMEZ (sağlık ucu auth-muaf) — servis günlüğündedir.
 *
 * Kapatma düğmesi YOK: bir yapılandırma hatasıdır, giderilene kadar görünür kalır.
 * ⚠️ HASTA GÜVENLİĞİ: donanım çalışırken GÖSTERİLMEZ (RecoveryCodeBanner ilkesi; ölçü `useDonanimCalisiyor`).
 * ⚠️ FAIL-QUIET: alan yok (eski backend) / `null` (tünel istemcisi ya da bilinemedi) / sağlık okunamadı → bant YOK.
 */
import { useEffect, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { HardDrive } from "lucide-react-native";

import { useDonanimCalisiyor } from "@/hooks/useDonanimCalisiyor";
import { apiGet } from "@/services/apiClient";
import { colors, radius, rf, rs, spacing } from "@/theme/tokens";
import i18n from "i18next";
import { useTranslation } from "react-i18next";

/** Sağlık ucunun bu banda gereken alanı. */
export interface VeriKokuSagligi {
  veriKokuAgda?: boolean | null;
}

/** Gösterilecek metin; bant gerekmiyorsa null. YALNIZ `veriKokuAgda === true` iken. */
export function veriKokuAgBandiMetni(s: VeriKokuSagligi | null): { baslik: string; aciklama: string } | null {
  if (!s || s.veriKokuAgda !== true) return null;
  return {
    baslik: i18n.t("bant.veriKokuAg.baslik"),
    aciklama:
      i18n.t("bant.veriKokuAg.aciklama"),
  };
}

export function VeriKokuAgBandi() {
  useTranslation(); // bant metni çağrı anında çevrilir (`veriKokuAgBandiMetni`) → dil değişince yeniden çiz
  const donanimCalisiyor = useDonanimCalisiyor();
  const [saglik, setSaglik] = useState<VeriKokuSagligi | null>(null);

  useEffect(() => {
    let iptal = false;
    void (async () => {
      // Veri kökü çalışma süresince değişmez → tek okuma. `silent`: cihaz kapalıyken hata balonu çıkmasın.
      const r = await apiGet<VeriKokuSagligi | null>("/health", null, { silent: true });
      if (!iptal) setSaglik(r);
    })();
    return () => {
      iptal = true;
    };
  }, []);

  const metin = veriKokuAgBandiMetni(saglik);
  if (!metin || donanimCalisiyor) return null;

  return (
    <View style={styles.bant} accessibilityRole="alert">
      <HardDrive color={colors.warning} size={rs(16)} />
      <View style={{ flex: 1 }}>
        <Text style={styles.baslik}>{metin.baslik}</Text>
        <Text style={styles.alt}>{metin.aciklama}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  bant: { flexDirection: "row", alignItems: "center", gap: spacing.sm,
          backgroundColor: colors.panel, borderWidth: 1, borderColor: colors.warning,
          borderRadius: radius.md, padding: spacing.sm, margin: spacing.sm },
  baslik: { color: colors.text, fontSize: rf(13), fontWeight: "800" },
  alt: { color: colors.textMuted, fontSize: rf(11), marginTop: rs(2), lineHeight: rf(16) },
});
