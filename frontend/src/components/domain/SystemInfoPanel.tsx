/**
 * SystemInfoPanel — Python'daki "Sistem Bilgileri" panelinin React karşılığı.
 * Yazılım sürümü, donanım sürümü, cihaz ID, uptime, toplam seans.
 */
import { StyleSheet, Text, View, TouchableOpacity } from "react-native";
import { useState, useEffect } from "react";
import { colors, spacing, typography } from "@/theme/tokens";
import { useLiveData } from "@/context/LiveDataContext";
import { apiGet } from "@/services/apiClient";

export function SystemInfoPanel() {
  const { snapshot } = useLiveData();
  const sysInfo = snapshot.system;
  const [uptime, setUptime] = useState("00:00:00");
  const [stmConnected, setStmConnected] = useState(false);

  useEffect(() => {
    apiGet<any>("/system/info", {}).then((d) => {
      if (d?.uptime) setUptime(d.uptime);
      if (typeof d?.stmConnected === "boolean") setStmConnected(d.stmConnected);
    });
    const id = setInterval(() => {
      apiGet<any>("/system/info", {}).then((d) => {
        if (d?.uptime) setUptime(d.uptime);
      });
    }, 10000);
    return () => clearInterval(id);
  }, []);

  return (
    <View style={styles.card}>
      <Text style={styles.title}>💻 Sistem Bilgileri</Text>

      <InfoRow label="Yazılım Sürümü" value={`v${sysInfo?.softwareVersion ?? "1"}`} accent />
      <InfoRow label="Donanım Sürümü" value={sysInfo?.hardwareVersion ?? "HW-2025.1"} accent />
      <InfoRow label="Cihaz ID" value={sysInfo?.deviceId ?? "PEMF-001"} />
      <InfoRow label="Çalışma Süresi" value={uptime} />
      <InfoRow label="Toplam Seans" value={`${sysInfo?.totalSessions ?? 0} seans`} />
      <InfoRow
        label="STM32 Bağlantısı"
        value={stmConnected ? "Bağlı ✅" : "Bekleniyor ⏳"}
        valueColor={stmConnected ? "#22c55e" : "#f59e0b"}
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
    paddingVertical: 6,
    paddingHorizontal: spacing.sm,
    backgroundColor: "#0f172a",
    borderRadius: 8,
  },
  rowLabel: { color: colors.textMuted, fontSize: typography.small },
  rowValue: { color: colors.text, fontSize: typography.small, fontWeight: "700" },
  rowValueAccent: { color: colors.primary },
});
