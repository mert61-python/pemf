// Author: mertaygn, cglrgrkn
/**
 * SystemInfoPanel — Python'daki "Sistem Bilgileri" panelinin React karşılığı.
 * Yazılım sürümü, donanım sürümü, cihaz ID, uptime, toplam seans.
 */
import { StyleSheet, Text, View } from "react-native";
import { useState, useEffect } from "react";
import { colors, spacing, typography, rs, radius } from "@/theme/tokens";
import { useLiveData } from "@/context/LiveDataContext";
import { formatUptime } from "@/utils/uptime";

export function SystemInfoPanel() {
  const { snapshot, connectionQuality, haveRealData } = useLiveData();
  const sysInfo = snapshot.system;
  const [uptime, setUptime] = useState("00:00:00");
  // ORTA fix: STM32 durumunu mount'ta BİR KEZ REST yerine CANLI snapshot.stm'den türet → seans sırasında
  // STM kablosu çıkar/koparsa panel bayat "Bağlı ✅" göstermesin. snapshot.stm WS ile sürekli güncellenir.
  // #69: bağlantı bayat/çevrimdışıyken (connectionQuality!='live') snapshot.stm de BAYAT olur → "Bağlı"
  // gösterme, "Bilinmiyor" de (yanlış-güvence yok).
  const stale = connectionQuality !== "live";
  const stmConnected = !stale && snapshot.stm === "online";

  // Çalışma süresi: WS snapshot'taki startTime'dan (process başlangıcı) her saniye hesaplanır.
  // (/api/system/info `uptime` DÖNDÜRMÜYOR → eski `d.uptime` hep undefined idi, panel "00:00:00"
  //  takılıydı. bkz. utils/uptime.ts + guii/REFACTOR_BUGS.md Faz F.)
  // YANLIŞ GÜVENCE: mockData'daki başlangıç snapshot'ında `system.startTime = new Date()` (modül
  // yükleme anı = UYGULAMANIN açılışı) var. Cihaza HİÇ bağlanılmamışken bile sayaç işliyor, panel
  // "Çalışma Süresi 00:03:21" diyordu — operatör cihazın ayakta olduğunu sanıyordu. Gerçek veri
  // gelmeden (haveRealData) ya da bağlantı yokken süre GÖSTERME.
  const uptimeKnown = haveRealData && !stale && !!sysInfo?.startTime;
  useEffect(() => {
    if (!uptimeKnown) { setUptime("—"); return; }
    const tick = () => setUptime(formatUptime(sysInfo?.startTime, Date.now()));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [sysInfo?.startTime, uptimeKnown]);

  return (
    <View style={styles.card}>
      <Text style={styles.title}>💻 Sistem Bilgileri</Text>

      <InfoRow label="Yazılım Sürümü" value={`v${sysInfo?.softwareVersion ?? "1"}`} accent />
      <InfoRow label="Cihaz ID" value={sysInfo?.deviceId ?? "PEMF-001"} />
      <InfoRow label="Çalışma Süresi" value={uptime} />
      <InfoRow label="Toplam Seans" value={`${sysInfo?.totalSessions ?? 0} seans`} />
      <InfoRow
        label="STM32 Bağlantısı"
        value={stale ? "Bilinmiyor ⚠️" : stmConnected ? "Bağlı ✅" : "Bekleniyor ⏳"}
        valueColor={stale ? "#94a3b8" : stmConnected ? "#22c55e" : "#f59e0b"}
      />
    </View>
  );
}

function InfoRow({
  label, value, accent = false, valueColor,
}: {
  label: string; value: string; accent?: boolean; valueColor?: string;
}) {
  return (
    <View style={styles.row}>
      <Text style={styles.rowLabel}>{label}</Text>
      <Text style={[styles.rowValue, accent && styles.rowValueAccent, valueColor ? { color: valueColor } : {}]}>
        {value}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: "#0a0f1e",
    borderRadius: 14,
    padding: spacing.md,
    gap: spacing.xs,
    borderWidth: 1,
    borderColor: "#1e293b",
  },
  title: { color: colors.text, fontWeight: "700", fontSize: typography.body, marginBottom: spacing.xs },
  row: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    gap: spacing.sm,
    paddingVertical: rs(6),
    paddingHorizontal: spacing.sm,
    backgroundColor: "#0f172a",
    borderRadius: radius.md,
  },
  rowLabel: { flexShrink: 1, color: colors.textMuted, fontSize: typography.small },
  rowValue: { flexShrink: 0, color: colors.text, fontSize: typography.small, fontWeight: "700", textAlign: "right" },
  rowValueAccent: { color: colors.primary },
});
