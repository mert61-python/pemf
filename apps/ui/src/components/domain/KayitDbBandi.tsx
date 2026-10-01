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

/** Sağlık ucunun bu banda gereken alanları. */
export interface KayitDbSagligi {
  dbReady?: boolean;
  dbSebep?: string | null;
}

/** Yoklama aralığı: göç ancak yeniden başlatmayla denenir — sık yoklamaya gerek yok. */
export const KAYIT_DB_YOKLAMA_MS = 30_000;

const VARSAYILAN_SEBEP = "Tıbbi kayıt veritabanı hazır değil; yeni seans başlatılamaz.";

/** Gösterilecek metin; bant gerekmiyorsa null. YALNIZ `dbReady === false` iken (alan yok/okunamadı → sessiz). */
export function kayitDbBandiMetni(s: KayitDbSagligi | null): { baslik: string; aciklama: string } | null {
  if (!s || s.dbReady !== false) return null;
  const sebep = typeof s.dbSebep === "string" && s.dbSebep.trim() ? s.dbSebep.trim() : VARSAYILAN_SEBEP;
  return {
    baslik: "Tıbbi kayıt veritabanı hazır değil — yeni seans BAŞLATILAMAZ",
    aciklama: `${sebep}\nACİL DURDUR ve bobin durdurma çalışır.`,
  };
}

export function KayitDbBandi() {
  const [saglik, setSaglik] = useState<KayitDbSagligi | null>(null);

  useEffect(() => {
    let iptal = false;
    const yokla = async () => {
      // `silent`: cihaz kapalıyken hata balonu çıkmasın (bağlantı bandı durumu zaten söyler).
      const r = await apiGet<KayitDbSagligi | null>("/health", null, { silent: true });
      if (!iptal) setSaglik(r);
    };
    void yokla();
    const t = setInterval(() => void yokla(), KAYIT_DB_YOKLAMA_MS);
    return () => {
      iptal = true;
      clearInterval(t);
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
