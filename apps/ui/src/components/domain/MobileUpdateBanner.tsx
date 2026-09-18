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

import { useApkGuncelleme } from "@/hooks/useApkGuncelleme";
import { useDonanimCalisiyor } from "@/hooks/useDonanimCalisiyor";
import { atlandiMi, guncellemeVarMi, type MobilSurum } from "@/services/mobileUpdate";
import { colors, radius, rf, rs, spacing, touch } from "@/theme/tokens";
import { useResponsive } from "@/hooks/useResponsive";

export function MobileUpdateBanner() {
  const { width } = useResponsive();
  const dar = width < 360;
  // ⚠️ Ölçü `useDonanimCalisiyor`: seans kaydı açık olmasa da çalışan bobin bandı susturur
  // (bobinler seanssız da sürülebilir — denetim bulgusu M4, 2026-08-23).
  const seansAktif = useDonanimCalisiyor();
  const [surum, setSurum] = useState<MobilSurum | null>(null);
  const [gizli, setGizli] = useState(false);

  // İndirme/kurulum akışı açılış kapısıyla ORTAK (tek kaynak) — bkz. useApkGuncelleme.
  const { oran, eta, hata, bilgi, kurulumAcildi, guncelle } = useApkGuncelleme(surum);

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
    // [S6 adım 8 / kapsam-7] Dar telefonda (< 360 px) ve büyük yazı ölçeğinde ikon + iki satır
    // metin + "Güncelle" + X aynı satıra sığmıyor, düğme metni kırpılıyordu. Dar ekranda bant
    // sütuna iner ve eylemler alta, tam genişlikte yerleşir.
    <View style={[styles.bant, dar && styles.bantDar]}>
      <Download color={colors.primary} size={rs(16)} />
      <View style={{ flex: 1 }}>
        <Text style={styles.baslik}>Yeni sürüm hazır: {surum.version}</Text>
        {/* ⚠️ KIRPMA YOK (denetim 2026-08-23, M12): `numberOfLines={3}` kancanın ~180-200
            karakterlik mesajlarını kesiyordu ve kesilen kısım tam da kullanıcıya NE YAPACAĞINI
            söyleyen cümleydi ("Bobinler durduktan sonra 'Güncelle'ye dokunun; paket hazır,
            yeniden indirilmeyecek"). Aynı metin kapıda (MobileUpdateGate) kırpılmadan
            gösteriliyordu — iki yüzey aynı durumda farklı şey söylüyordu. Bant kendi
            yüksekliğini alsın; bilgi kaybı, birkaç piksel yükseklikten pahalıdır. */}
        <Text style={[styles.alt, hata ? styles.altHata : null]}>
          {hata || bilgi ||
            (oran !== null
              // Yüzdenin yanında MB: 128 MB'lık pakette kullanıcı kotasını görsün.
              // Kalan süre anlık hızdan (launcher paritesi, 2026-08-27) — ölçülemediyse gizli.
              ? `İndiriliyor… %${Math.round(oran * 100)} · ${Math.round((oran * surum.size) / 1_000_000)} / ${Math.round(surum.size / 1_000_000)} MB${eta ? ` · ${eta}` : ""}`
              : surum.notes || "Güncellemek için dokunun.")}
        </Text>
      </View>
      {oran === null ? (
        <View style={dar ? styles.eylemlerDar : undefined}>
          <TouchableOpacity style={[styles.btn, dar && { flex: 1 }]} onPress={guncelle}
            accessibilityRole="button" accessibilityLabel={`Sürüm ${surum.version} güncellemesini indir ve kur`}>
            {/* Kurulum bir kez açıldıysa ikinci dokunuş İNDİRMEZ (dosya diskte tam),
                doğrudan yükleyiciyi tekrar açar. */}
            <Text style={styles.btnText}>{kurulumAcildi ? "Kur" : "Güncelle"}</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={() => setGizli(true)}
            accessibilityRole="button" accessibilityLabel="Güncelleme bildirimini kapat">
            <X color={colors.textMuted} size={rs(15)} />
          </TouchableOpacity>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  bant: { flexDirection: "row", alignItems: "center", gap: spacing.sm,
          backgroundColor: colors.panel, borderWidth: 1, borderColor: colors.border,
          borderRadius: radius.md, padding: spacing.sm, margin: spacing.sm },
  baslik: { color: colors.text, fontSize: rf(13), fontWeight: "800" },
  // 11 px 320 px'te 9 px'e düşüyordu; bant metni EYLEM anlatıyor, okunur kalmalı.
  alt: { color: colors.textMuted, fontSize: Math.max(12, rf(11)), marginTop: rs(2) },
  bantDar: { flexDirection: "column", alignItems: "stretch" },
  eylemlerDar: { flexDirection: "row", alignItems: "center", gap: spacing.sm, justifyContent: "flex-end" },
  altHata: { color: colors.warning },
  btn: { backgroundColor: colors.cyan, borderRadius: radius.md,
         paddingVertical: rs(9), paddingHorizontal: spacing.md, minHeight: touch.min, justifyContent: "center" },
  btnText: { color: "#04121F", fontWeight: "800", fontSize: rf(12) },
});
