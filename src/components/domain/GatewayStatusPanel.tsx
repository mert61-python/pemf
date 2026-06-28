/**
 * GatewayStatusPanel — Python gateway_status_widget.py'nin React karşılığı.
 * Mosquitto broker, MQTT, Network, Bridge durumunu gösterir.
 */
import { StyleSheet, Text, View, TouchableOpacity } from "react-native";
import { useState, useEffect, useCallback } from "react";
import { colors, spacing, typography } from "@/theme/tokens";
import { useLiveData } from "@/context/LiveDataContext";
import { apiGet } from "@/services/apiClient";
import type { ConnectionState } from "@/types/domain";

interface GatewayInfo {
  mqttConnected: boolean;
  brokerRunning: boolean;
  bridgeConnected: boolean;
  networkOnline: boolean;
  hotspotActive: boolean;
  gatewayState?: ConnectionState;
}

export function GatewayStatusPanel() {
  const { snapshot, wsConnected } = useLiveData();
  const [gwInfo, setGwInfo] = useState<GatewayInfo>({
    mqttConnected: false,
    brokerRunning: false,
    bridgeConnected: false,
    networkOnline: false,
    hotspotActive: false,
  });

  const refresh = useCallback(async () => {
    const data = await apiGet<GatewayInfo>("/gateway/status", gwInfo, { silent: true });
    setGwInfo(data);
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 8000);
    return () => clearInterval(id);
  }, [refresh]);

  const mqttState: ConnectionState = snapshot.mqtt ?? "offline";
  const gatewayState: ConnectionState = snapshot.gateway ?? "offline";

  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <Text style={styles.title}>🌐 Ağ Geçidi Durumu</Text>
        <TouchableOpacity onPress={refresh} style={styles.refreshBtn}>
          <Text style={styles.refreshText}>↻</Text>
        </TouchableOpacity>
      </View>

      <GatewayRow label="WebSocket Bağlantısı" state={wsConnected ? "online" : "offline"} />
      <GatewayRow label="MQTT Broker" state={mqttState} />
      <GatewayRow label="Gateway Köprüsü" state={gatewayState} />
      <GatewayRow label="STM32 Sürücüsü" state={snapshot.stm ?? "warning"} />
      <GatewayRow label="Ağ Bağlantısı" state={gwInfo.networkOnline ? "online" : "offline"} />
    </View>
  );
}

function GatewayRow({ label, state }: { label: string; state: ConnectionState | boolean }) {
  let resolvedState: ConnectionState;
  if (typeof state === "boolean") {
    resolvedState = state ? "online" : "offline";
  } else {
    resolvedState = state;
  }

  const cfg = {
    online:  { color: "#22c55e", text: "Aktif",     dot: "#22c55e" },
    warning: { color: "#f59e0b", text: "Uyarı",     dot: "#f59e0b" },
    offline: { color: "#ef4444", text: "Kapalı",    dot: "#ef4444" },
    error:   { color: "#ef4444", text: "Hata",      dot: "#ef4444" },
  }[resolvedState] ?? { color: "#475569", text: "Bilinmiyor", dot: "#475569" };

  return (
    <View style={styles.row}>
      <Text style={styles.rowLabel}>{label}</Text>
      <View style={styles.rowRight}>
        <View style={[styles.dot, { backgroundColor: cfg.dot }]} />
        <Text style={[styles.rowValue, { color: cfg.color }]}>{cfg.text}</Text>
      </View>
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
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: spacing.xs },
  title: { color: colors.text, fontWeight: "700", fontSize: typography.body },
  refreshBtn: { padding: spacing.xs },
  refreshText: { color: colors.primary, fontSize: 18, fontWeight: "700" },
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
  rowRight: { flexDirection: "row", alignItems: "center", gap: 6 },
  dot: { width: 8, height: 8, borderRadius: 4 },
  rowValue: { fontSize: typography.small, fontWeight: "700" },
});
