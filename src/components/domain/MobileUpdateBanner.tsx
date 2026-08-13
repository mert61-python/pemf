// Author: mertaygn, cglrgrkn
/**
 * MOBİL GÜNCELLEME BANDI (2026-08-08) — "kullanıcı siteden tekrar indirmesin".
 *
 * Açılışta yeni APK var mı bakar; varsa tek dokunuşla indirip kurulum onayını açar.
 *
 * ⚠️ ASLA ENGELLEMEZ: ağ yoksa, manifest bozuksa ya da indirme düşerse bant sessizce kaybolur —
 * internetsiz klinikte uygulama normal çalışmalı. Güncelleme bir kolaylıktır, kapı değil.
 * ⚠️ HASTA GÜVENLİĞİ: seans sürerken gösterilmez — kurulum uygulamayı yeniden başlatır ve
 * bobinler hastanın üzerindeyken operatörün ekranını elinden almak kabul edilemez.
 */
import { useCallback, useEffect, useState } from "react";
import { Platform, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { Download, X } from "lucide-react-native";

import { useLiveData } from "@/context/LiveDataContext";
import { apkIndir, guncellemeVarMi, kurulumuBaslat, type MobilSurum } from "@/services/mobileUpdate";
import { colors, radius, rf, rs, spacing } from "@/theme/tokens";

export function MobileUpdateBanner() {
  const { snapshot } = useLiveData();
  const seansAktif = !!snapshot?.activeTreatment?.isActive;
  const [surum, setSurum] = useState<MobilSurum | null>(null);
  const [gizli, setGizli] = useState(false);
  const [oran, setOran] = useState<number | null>(null);
  const [hata, setHata] = useState("");

  useEffect(() => {
    if (Platform.OS !== "android") return;
    let iptal = false;
    void (async () => {
      const r = await guncellemeVarMi();
      if (!iptal && r.varMi && r.surum) setSurum(r.surum);
    })();
    return () => { iptal = true; };
  }, []);

  const guncelle = useCallback(async () => {
    if (!surum) return;
    setHata(""); setOran(0);
    const ind = await apkIndir(surum, setOran);
    setOran(null);
    if (!ind.ok || !ind.dosyaUri) {
      setHata(ind.hata === "boyut"
        ? "İndirme eksik kaldı. Bağlantınızı kontrol edip tekrar deneyin."
        : "Güncelleme indirilemedi.");
      return;
    }
    const acildi = await kurulumuBaslat(ind.dosyaUri);
    if (!acildi) setHata("Kurulum açılamadı. Ayarlar'dan bu uygulamaya 'bilinmeyen kaynak' izni verin.");
  }, [surum]);

  if (Platform.OS !== "android" || !surum || gizli || seansAktif) return null;

  return (
    <View style={styles.bant}>
      <Download color={colors.primary} size={rs(16)} />
      <View style={{ flex: 1 }}>
        <Text style={styles.baslik}>Yeni sürüm hazır: {surum.version}</Text>
        <Text style={styles.alt} numberOfLines={2}>
          {hata || (oran !== null ? `İndiriliyor… %${Math.round(oran * 100)}` : (surum.notes || "Güncellemek için dokunun."))}
        </Text>
      </View>
      {oran === null ? (
        <>
          <TouchableOpacity style={styles.btn} onPress={guncelle}
            accessibilityRole="button" accessibilityLabel={`Sürüm ${surum.version} güncellemesini indir ve kur`}>
            <Text style={styles.btnText}>Güncelle</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={() => setGizli(true)}
            accessibilityRole="button" accessibilityLabel="Güncelleme bildirimini kapat">
            <X color={colors.textMuted} size={rs(15)} />
          </TouchableOpacity>
        </>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  bant: { flexDirection: "row", alignItems: "center", gap: spacing.sm,
          backgroundColor: colors.panel, borderWidth: 1, borderColor: colors.border,
          borderRadius: radius.md, padding: spacing.sm, margin: spacing.sm },
  baslik: { color: colors.text, fontSize: rf(13), fontWeight: "800" },
  alt: { color: colors.textMuted, fontSize: rf(11), marginTop: rs(2) },
  btn: { backgroundColor: colors.cyan, borderRadius: radius.md,
         paddingVertical: rs(9), paddingHorizontal: spacing.md, minHeight: rs(44), justifyContent: "center" },
  btnText: { color: "#04121F", fontWeight: "800", fontSize: rf(12) },
});
