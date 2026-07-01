/**
 * UpdateBanner — uzaktan güncelleme bildirimi (vet-dostu, tek-tık).
 * • Cihaz yazılımı (EXE): "Güncelle" → backend kendini indirir+doğrular+kurar (aktif tedavi yokken).
 * • Uygulama (APK): "İndir" → yeni APK indirme linki açılır (sideload).
 * Güncelleme yoksa hiçbir şey göstermez. AppShell'de connection banner'ın altına yerleşir.
 */
import { useCallback, useEffect, useState } from "react";
import { View, Text, Pressable, ActivityIndicator, StyleSheet, Linking } from "react-native";
import { colors, spacing } from "@/theme/tokens";
import {
  checkBackendUpdate, applyBackendUpdate, checkMobileUpdate,
  type BackendUpdate, type MobileUpdate,
} from "@/services/updates";

export function UpdateBanner() {
  const [backend, setBackend] = useState<BackendUpdate>({ available: false });
  const [mobile, setMobile] = useState<MobileUpdate>({ available: false });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

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
    setBusy(true); setMsg("İndiriliyor + doğrulanıyor…");
    const r = await applyBackendUpdate();
    setMsg(r.ok ? (r.message || "Kurulum başladı — cihaz birazdan yeniden başlar.") : ("⚠ " + (r.error || "Güncelleme başarısız")));
    setBusy(false);
    // Başarılıysa birazdan backend yeniden başlar; durumu tazele.
    if (r.ok) setTimeout(refresh, 15000);
  }, [busy, refresh]);

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
  row: { flexDirection: "row", alignItems: "center", gap: spacing.sm, minHeight: 30 },
  icon: { fontSize: 14 },
  txt: { color: "#7dd3fc", fontSize: 13, fontWeight: "700", flex: 1 },
  msg: { color: colors.textMuted, fontSize: 11 },
});
