// Author: mertaygn, cglrgrkn
/**
 * GA (istem 53) B3 — Kontrol sekmesi MODÜL SEÇİCİSİ + PANEL YUVASI (Y298 / Y299).
 * =================================================================================
 * - Geliştirici modülleri GİZLİYKEN (varsayılan) seçici HİÇ çizilmez; Kontrol sekmesi bugünkü gibi.
 * - "PEMF cihazı (7 bobin)" + her geliştiricinin modülü (kişinin adıyla); bozuk modül (`modul.json` hatası) seçilemez, nedeni yazılır.
 * - Bir anda TEK modül: modül seçilince sunucu sürücüyü AYRI SÜREÇTE başlatır ve kartına bağlanır; "PEMF cihazı" seçilince bırakılır.
 * - Panel yalnız SEÇİLİNCE yüklenir (`moduller/kayit.ts`, tembel) — açılışı geciktirmez.
 * - Büyük ACİL DURDUR düğmesi bu bileşenin DIŞINDA ve ÖNÜNDE (Kontrol ekranı); modül ona dokunamaz, ACİL DURDUR modüllere de gider.
 */
import { Suspense, useEffect, useState } from "react";
import { StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useTranslation } from "react-i18next";
import { PANELLER } from "@/moduller/kayit";
import { modulAdi, modulApi, modulHataMetni, type ModulHata, type ModulListesi } from "@/services/moduller";
import { colors, rf, rs, spacing, touch } from "@/theme/tokens";

export function ModulSecici({ etkin, onSec }: { etkin: string | null; onSec: (kimlik: string | null) => void }) {
  const { t, i18n } = useTranslation();
  const [liste, setListe] = useState<ModulListesi | null>(null);
  const [hata, setHata] = useState<ModulHata | null>(null);
  const [mesgul, setMesgul] = useState(false);

  useEffect(() => {
    let canli = true;
    void modulApi.listele().then((r) => {
      if (!canli || !r.tamam) return;
      setListe(r.veri);
      if (r.veri.gorunur && r.veri.etkin) onSec(r.veri.etkin);
    });
    return () => {
      canli = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!liste?.gorunur) return null;

  const sec = async (kimlik: string | null) => {
    if (mesgul || kimlik === etkin) return;
    setMesgul(true);
    const r = kimlik === null ? await modulApi.birak() : await modulApi.sec(kimlik);
    setMesgul(false);
    if (r.tamam) {
      setHata(null);
      onSec(kimlik);
    } else {
      setHata(r.hata);
    }
  };

  return (
    <View style={styles.kutu} testID="modul-secici">
      <Text style={styles.baslik}>{t("kontrol.modul.secici.baslik")}</Text>
      <View style={styles.cipler}>
        <TouchableOpacity
          style={[styles.cip, etkin === null && styles.cipAktif]}
          onPress={() => void sec(null)}
          accessibilityRole="button"
          accessibilityState={{ selected: etkin === null }}
          testID="modul-sec-pemf"
        >
          <Text style={[styles.cipMetin, etkin === null && styles.cipMetinAktif]}>{t("kontrol.modul.secici.pemf")}</Text>
        </TouchableOpacity>
        {liste.moduller.map((m) => (
          <TouchableOpacity
            key={m.kimlik}
            style={[styles.cip, etkin === m.kimlik && styles.cipAktif, !!m.hata && styles.cipBozuk]}
            disabled={!!m.hata}
            onPress={() => void sec(m.kimlik)}
            accessibilityRole="button"
            accessibilityState={{ selected: etkin === m.kimlik, disabled: !!m.hata }}
            testID={`modul-sec-${m.kimlik}`}
          >
            <Text style={[styles.cipMetin, etkin === m.kimlik && styles.cipMetinAktif]}>{modulAdi(m, i18n.language)}</Text>
          </TouchableOpacity>
        ))}
      </View>
      {liste.moduller
        .filter((m) => m.hata)
        .map((m) => (
          <Text key={m.kimlik} style={styles.uyari} testID={`modul-bozuk-${m.kimlik}`}>
            {t("kontrol.modul.secici.bozuk", { kimlik: m.kimlik, hata: m.hata })}
          </Text>
        ))}
      {hata && (
        <Text style={styles.uyari} testID="modul-secici-hata">
          {modulHataMetni(t, hata)}
        </Text>
      )}
    </View>
  );
}

/** Seçili modülün paneli (tembel yüklenir). Kayıtta paneli olmayan modül için eylem söyleyen metin. */
export function ModulPaneli({ kimlik }: { kimlik: string }) {
  const { t } = useTranslation();
  const Panel = PANELLER[kimlik];
  if (!Panel) {
    return (
      <Text style={styles.uyari} testID="modul-panel-yok">
        {t("kontrol.modul.panel.yok")}
      </Text>
    );
  }
  return (
    <View style={styles.kutu} testID={`modul-panel-${kimlik}`}>
      <Suspense fallback={<Text style={styles.baslik}>{t("kontrol.modul.panel.yukleniyor")}</Text>}>
        <Panel />
      </Suspense>
    </View>
  );
}

const styles = StyleSheet.create({
  kutu: {
    backgroundColor: colors.panel,
    borderRadius: rs(14),
    padding: rs(14),
    gap: rs(8),
    borderWidth: 1,
    borderColor: colors.border,
    marginTop: spacing.md,
  },
  baslik: { color: colors.textMuted, fontSize: rf(12), fontWeight: "700" },
  cipler: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  cip: {
    minHeight: touch.sm,
    justifyContent: "center",
    paddingHorizontal: rs(12),
    borderRadius: rs(12),
    borderWidth: 1,
    borderColor: colors.border,
  },
  cipAktif: { backgroundColor: colors.primarySoft, borderColor: colors.primary },
  cipBozuk: { opacity: 0.5 },
  cipMetin: { color: colors.textMuted, fontSize: rf(13) },
  cipMetinAktif: { color: colors.text, fontWeight: "700" },
  uyari: { color: colors.warning, fontSize: rf(12), fontWeight: "700" },
});
