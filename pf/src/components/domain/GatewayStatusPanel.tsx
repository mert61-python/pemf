// Author: mertaygn, cglrgrkn
/**
 * GatewayStatusPanel — Python gateway_status_widget.py'nin React karşılığı.
 * Mosquitto broker, MQTT, Network, Bridge durumunu gösterir.
 */
import { StyleSheet, Text, View, TouchableOpacity } from "react-native";
import { useState, useEffect, useCallback } from "react";
import { colors, spacing, typography, rf, rs, radius } from "@/theme/tokens";
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

/** Satır durumu: bağlantı yokken bayat değeri yeşil göstermemek için "unknown" eklendi. */
type RowState = ConnectionState | "unknown";

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
    // exhaustive-deps + hata-dayanıklılık: fallback null → başarısız poll SON İYİ değeri korur
    // (eskiden yakalanan ilk gwInfo'ya set ediyordu = hatada başlangıca sıfırlama). refresh stable kalır.
    const data = await apiGet<GatewayInfo | null>("/gateway/status", null, { silent: true });
    if (data) setGwInfo(data);
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 8000);
    return () => clearInterval(id);
  }, [refresh]);

  // YANLIŞ GÜVENCE: aşağıdaki satırların hepsi BAYAT snapshot'tan/son başarılı poll'den okunuyor.
  // WS koptuğunda bunlar son bilinen (genelde yeşil "Aktif") değerde donuyordu → operatör sistemi
  // sağlıklı sanıyordu. SystemInfoPanel'de bu koruma (#69) vardı, burada YOKTU. Bağlantı yokken
  // hiçbir alt-bileşen durumu "online" gösterilmez, "Bilinmiyor"a düşer.
  const stale = !wsConnected;
  const gated = (s: ConnectionState | undefined, dflt: ConnectionState): RowState =>
    stale ? "unknown" : (s ?? dflt);

  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <Text style={styles.title}>🌐 Sistem Durumu</Text>
        <TouchableOpacity
          onPress={refresh}
          style={styles.refreshBtn}
          accessibilityRole="button"
          accessibilityLabel="Sistem durumunu yenile"
        >
          <Text style={styles.refreshText}>↻</Text>
        </TouchableOpacity>
      </View>

      <GatewayRow label="Uygulama Bağlantısı" state={wsConnected ? "online" : "offline"} />
      <GatewayRow label="Sistem Bağlantısı" state={gated(snapshot.mqtt, "offline")} />
      <GatewayRow label="Cihaz Köprüsü" state={gated(snapshot.gateway, "offline")} />
      <GatewayRow label="Donanım Sürücüsü" state={gated(snapshot.stm, "warning")} />
      {/* gwInfo ayrı bir poll'den gelir; başarısız poll SON İYİ değeri korur (bilinçli) → bağlantı
          yokken o değeri de "Bilinmiyor" olarak göster, yeşil "Aktif" bırakma. */}
      <GatewayRow label="İnternet Bağlantısı" state={stale ? "unknown" : gwInfo.networkOnline ? "online" : "offline"} />
      {/* ⚠️ KABLOSUZ BAĞLANTI (2026-08-10). `hotspotActive` zaten çekiliyordu ama HİÇ
          GÖSTERİLMİYORDU — yani PEMF-Gateway kapalıyken 6-8 numaralı bobinler sessizce
          bağlanamıyor, operatör sebebini hiçbir yerden göremiyordu. Backend hotspot'u açılışta
          otomatik başlatır (backend_service._start_hotspot_safe); bu satır sonucu görünür kılar. */}
      <GatewayRow
        label="Kablosuz Bağlantı"
        state={stale ? "unknown" : gwInfo.hotspotActive ? "online" : "offline"}
      />
    </View>
  );
}

function GatewayRow({ label, state }: { label: string; state: RowState | boolean }) {
  let resolvedState: RowState;
  if (typeof state === "boolean") {
    resolvedState = state ? "online" : "offline";
  } else {
    resolvedState = state;
  }

  const cfg = {
    online:  { color: "#22c55e", text: "Aktif",      dot: "#22c55e" },
    warning: { color: "#f59e0b", text: "Uyarı",      dot: "#f59e0b" },
    offline: { color: "#ef4444", text: "Kapalı",     dot: "#ef4444" },
    error:   { color: "#ef4444", text: "Hata",       dot: "#ef4444" },
    unknown: { color: "#94a3b8", text: "Bilinmiyor", dot: "#94a3b8" },
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
  refreshText: { color: colors.primary, fontSize: rf(18), fontWeight: "700" },
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
  rowRight: { flexShrink: 0, flexDirection: "row", alignItems: "center", gap: rs(6) },
  dot: { width: rs(8), height: rs(8), borderRadius: 4 },
  rowValue: { fontSize: typography.small, fontWeight: "700" },
});
