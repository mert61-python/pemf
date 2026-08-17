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
import { useEffect, useState } from "react";
import { Platform, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { Download, X } from "lucide-react-native";

import { useLiveData } from "@/context/LiveDataContext";
import { useApkGuncelleme } from "@/hooks/useApkGuncelleme";
import { atlandiMi, guncellemeVarMi, type MobilSurum } from "@/services/mobileUpdate";
import { colors, radius, rf, rs, spacing } from "@/theme/tokens";

export function MobileUpdateBanner() {
  const { snapshot } = useLiveData();
  const seansAktif = !!snapshot?.activeTreatment?.isActive;
  const [surum, setSurum] = useState<MobilSurum | null>(null);
  const [gizli, setGizli] = useState(false);

  // İndirme/kurulum akışı açılış kapısıyla ORTAK (tek kaynak) — bkz. useApkGuncelleme.
  const { oran, hata, bilgi, kurulumAcildi, guncelle } = useApkGuncelleme(surum);

  useEffect(() => {
    if (Platform.OS !== "android") return;
    let iptal = false;
    void (async () => {
      const r = await guncellemeVarMi();
      if (!iptal && r.varMi && r.surum) setSurum(r.surum);
    })();
    return () => { iptal = true; };
  }, []);

  // ⚠️ Açılış kapısında "şimdilik devam et" denen sürüm bu açılışta yeniden DAYATILMAZ: kullanıcı
  // az önce erteledi, bir saniye sonra aynı şeyi göstermek erteleme düğmesini bozuk gösterir.
  // Erteleme diske yazılmaz → sonraki soğuk açılışta kapı yeniden sorar.
  if (Platform.OS !== "android" || !surum || gizli || seansAktif || atlandiMi(surum.versionCode))
    return null;

  return (
    <View style={styles.bant}>
      <Download color={colors.primary} size={rs(16)} />
      <View style={{ flex: 1 }}>
        <Text style={styles.baslik}>Yeni sürüm hazır: {surum.version}</Text>
        <Text style={[styles.alt, hata ? styles.altHata : null]} numberOfLines={3}>
          {hata || bilgi ||
            (oran !== null
              // Yüzdenin yanında MB: 128 MB'lık paketde kullanıcı kotasını görsün.
              ? `İndiriliyor… %${Math.round(oran * 100)} · ${Math.round((oran * surum.size) / 1_000_000)} / ${Math.round(surum.size / 1_000_000)} MB`
              : surum.notes || "Güncellemek için dokunun.")}
        </Text>
      </View>
      {oran === null ? (
        <>
          <TouchableOpacity style={styles.btn} onPress={guncelle}
            accessibilityRole="button" accessibilityLabel={`Sürüm ${surum.version} güncellemesini indir ve kur`}>
            {/* Kurulum bir kez açıldıysa ikinci dokunuş İNDİRMEZ (dosya diskte tam),
                doğrudan yükleyiciyi tekrar açar. */}
            <Text style={styles.btnText}>{kurulumAcildi ? "Kur" : "Güncelle"}</Text>
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
  altHata: { color: colors.warning },
  btn: { backgroundColor: colors.cyan, borderRadius: radius.md,
         paddingVertical: rs(9), paddingHorizontal: spacing.md, minHeight: rs(44), justifyContent: "center" },
  btnText: { color: "#04121F", fontWeight: "800", fontSize: rf(12) },
});
