/**
 * UpdateBanner — uzaktan güncelleme bildirimi (vet-dostu, tek-tık).
 * • Cihaz yazılımı (EXE): "Güncelle" → backend kendini indirir+doğrular+kurar (aktif tedavi yokken).
 * • Uygulama (APK): "İndir" → yeni APK indirme linki açılır (sideload).
 * Güncelleme yoksa hiçbir şey göstermez. AppShell'de connection banner'ın altına yerleşir.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { View, Text, Pressable, ActivityIndicator, StyleSheet, Linking } from "react-native";
import { colors, spacing, rf, rs } from "@/theme/tokens";
import {
  checkBackendUpdate, applyBackendUpdate, checkMobileUpdate,
  type BackendUpdate, type MobileUpdate,
} from "@/services/updates";
import { platformConfirm, platformAlert } from "@/services/apiClient";
import { useLiveData } from "@/context/LiveDataContext";

export function UpdateBanner() {
  const { snapshot } = useLiveData();
  const _at = snapshot.activeTreatment;
  const _running = (snapshot.coils ?? []).filter((c) => c.running).length;
  const treatmentActive = !!_at?.isActive || _running > 0;
  const [backend, setBackend] = useState<BackendUpdate>({ available: false });
  const [mobile, setMobile] = useState<MobileUpdate>({ available: false });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  // ORTA fix: başarı-sonrası 15sn refresh timeout'u ref'te tut → unmount'ta temizle (unmounted setState önle).
  const refreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current); }, []);

  const refresh = useCallback(async () => {
    try { setBackend(await checkBackendUpdate()); } catch { /* ignore */ }
    try { setMobile(await checkMobileUpdate()); } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 6 * 3600 * 1000); // 6 saatte bir
    return () => clearInterval(id);
  }, [refresh]);

  const applyBackend = useCallback(async () => {
    if (busy) return;
    // #88/#92: aktif tedavide cihaz-yazılımı güncellemesi YAPILMAZ (installer servisi durdurup EXE'yi
    // değiştirir → bobinler kontrolcüsüz). Client-tarafı da engelle (backend zaten reddeder, ama UX).
    if (treatmentActive) {
      platformAlert("Tedavi aktif", "Cihaz yazılımı güncellemesi aktif tedavi/çalışan bobin sırasında yapılamaz. Önce seansı bitirin.");
      return;
    }
    // Medikal-uygun ONAY: cihaz YENİDEN BAŞLAR — tek-tık yerine açık teyit.
    const ok = await platformConfirm(
      "Cihaz yazılımı güncellemesi",
      `Cihaz güncellenecek ve YENİDEN BAŞLAYACAK (v${backend.latestVersion}). Tedavi olmadığından emin olun. Devam edilsin mi?`,
      "Güncelle",
    );
    if (!ok) return;
    setBusy(true); setMsg("İndiriliyor + doğrulanıyor…");
    try {
      const r = await applyBackendUpdate();
      setMsg(r.ok ? (r.message || "Kurulum başladı — cihaz birazdan yeniden başlar.") : ("⚠ " + (r.error || "Güncelleme başarısız")));
      // Başarılıysa birazdan backend yeniden başlar; durumu tazele (timeout ref → unmount'ta temizlenir).
      if (r.ok) {
        if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
        refreshTimerRef.current = setTimeout(refresh, 15000);
      }
    } finally {
      // ORTA fix: hata olsa da busy kilidini AÇ — yoksa banner kalıcı "İndiriliyor" + disabled kalır (kilit).
      setBusy(false);
    }
  }, [busy, refresh, treatmentActive, backend.latestVersion]);

  const downloadMobile = useCallback(() => {
    if (mobile.apkUrl) Linking.openURL(mobile.apkUrl).catch(() => {});
  }, [mobile.apkUrl]);

  if (!backend.available && !mobile.available) return null;

  return (
    <View style={styles.wrap}>
      {backend.available && (
        <Pressable style={styles.row} onPress={applyBackend} accessibilityRole="button" disabled={busy}>
          {busy ? <ActivityIndicator size="small" color="#7dd3fc" /> : <Text style={styles.icon}>🔄</Text>}
          <Text style={styles.txt} numberOfLines={2}>
            Cihaz yazılımı güncellemesi var (v{backend.latestVersion}) — {busy ? (msg || "Güncelleniyor…") : "Dokun ve Güncelle"}
          </Text>
        </Pressable>
      )}
      {!busy && !!msg && backend.available && <Text style={styles.msg}>{msg}</Text>}
      {mobile.available && (
        <Pressable style={styles.row} onPress={downloadMobile} accessibilityRole="button">
          <Text style={styles.icon}>📲</Text>
          <Text style={styles.txt} numberOfLines={2}>
            Uygulama güncellemesi var (v{mobile.latestVersion}) — Dokun ve İndir
          </Text>
        </Pressable>
      )}
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
  msg: { color: colors.textMuted, fontSize: rf(11) },
});
