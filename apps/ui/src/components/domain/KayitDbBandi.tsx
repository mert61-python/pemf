// Author: mertaygn, cglrgrkn
/**
 * KAYIT VERİTABANI BANDI (D1.37 · plan başlığı "sağlık ucu VE ARAYÜZ 'göç bekliyor' desin"; 1-B inceleme i2).
 *
 * Backend açılışta hasta/tedavi DB'sini açamazsa (at-rest şifreleme göçü bekliyor, bozuk dosya, anahtar
 * yok) artık ÖLMEZ: DB'siz (kısıtlı) kipte açılır, ACİL DURDUR ve STOP çalışır, yeni seans 503 alır.
 * `/api/health` bunu `dbReady: false` + `dbSebep` ile söyler. ⚠️ ASIL SORUN: arayüz bu alanları HİÇ
 * okumuyordu — operatör "göç bekliyor"u ancak seans başlatınca (503 detayı), yani HASTA MASADAYKEN
 * görüyordu. Bant, durumu seanstan ÖNCE, her ekranda gösterir.
 *
 * Metin backend'den AYNEN gelir (`dbSebep`: yol / istisna ayrıntısı içermez, eylemi söyler). Kapatma
 * düğmesi YOK: durum düzelince (`dbReady: true`) bant kendiliğinden kalkar. FAIL-QUIET: sağlık ucu
 * okunamazsa ya da alan yoksa (eski backend) bant YOK — sahte uyarı üretilmez. Bant hiçbir şeyi
 * KAPILAMAZ (Ö.4-Y8: ACİL DURDUR her koşulda erişilebilir kalır).
 */
import { useEffect, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { DatabaseZap } from "lucide-react-native";

import { apiGet } from "@/services/apiClient";
import { colors, radius, rf, rs, spacing } from "@/theme/tokens";
import i18n from "i18next";
import { useTranslation } from "react-i18next";

/** Sağlık ucunun bu banda gereken alanları. */
export interface KayitDbSagligi {
  dbReady?: boolean;
  dbSebep?: string | null;
}

/** Yoklama aralığı: backend açılamayan DB'yi arka planda 5 sn → 30 sn → 2 dk aralıkla yeniden dener (Y43);
 *  açılınca bant en geç bu aralıkta kalkar. */
export const KAYIT_DB_YOKLAMA_MS = 30_000;

const varsayilanSebep = (): string => i18n.t("bant.kayitDb.varsayilanSebep");

/** Gösterilecek metin; bant gerekmiyorsa null. YALNIZ `dbReady === false` iken (alan yok/okunamadı → sessiz). */
export function kayitDbBandiMetni(s: KayitDbSagligi | null): { baslik: string; aciklama: string } | null {
  if (!s || s.dbReady !== false) return null;
  const sebep = typeof s.dbSebep === "string" && s.dbSebep.trim() ? s.dbSebep.trim() : varsayilanSebep();
  return {
    baslik: i18n.t("bant.kayitDb.baslik"),
    aciklama: i18n.t("bant.kayitDb.aciklama", { sebep }),
  };
}

export function KayitDbBandi() {
  useTranslation(); // bant metni çağrı anında çevrilir (`kayitDbBandiMetni`) → dil değişince yeniden çiz
  const [saglik, setSaglik] = useState<KayitDbSagligi | null>(null);

  useEffect(() => {
    let iptal = false;
    const yokla = async () => {
      // `silent`: cihaz kapalıyken hata balonu çıkmasın (bağlantı bandı durumu zaten söyler).
      const r = await apiGet<KayitDbSagligi | null>("/health", null, { silent: true });
      if (!iptal) setSaglik(r);
    };
    void yokla();
    const zamanlayici = setInterval(() => void yokla(), KAYIT_DB_YOKLAMA_MS);
    return () => {
      iptal = true;
      clearInterval(zamanlayici);
    };
  }, []);

  const metin = kayitDbBandiMetni(saglik);
  if (!metin) return null;

  return (
    <View style={styles.bant} accessibilityRole="alert">
      <DatabaseZap color={colors.danger} size={rs(16)} />
      <View style={{ flex: 1 }}>
        <Text style={styles.baslik}>{metin.baslik}</Text>
        <Text style={styles.alt}>{metin.aciklama}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  bant: { flexDirection: "row", alignItems: "center", gap: spacing.sm,
          backgroundColor: colors.dangerSoft, borderWidth: 1, borderColor: colors.danger,
          borderRadius: radius.md, padding: spacing.sm, margin: spacing.sm },
  baslik: { color: colors.text, fontSize: rf(13), fontWeight: "800" },
  alt: { color: colors.textMuted, fontSize: rf(11), marginTop: rs(2), lineHeight: rf(16) },
});
