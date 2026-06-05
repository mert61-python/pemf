/**
 * LiveDataContext — uygulama genelinde canlı MQTT verisi.
 *
 * WebSocket üzerinden Python bridge'e bağlanır.
 * Bağlantı kesilirse HTTP snapshot ile yedek polling yapar.
 * Tüm ekranlar bu context'ten veri okur — polling kodu kaldırılabilir.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { serviceConfig } from "@/services/config";
import { connectPemfWebSocket, WsMessage } from "@/services/wsClient";
import { mockSnapshot } from "@/services/mockData";
import type {
  ActiveTreatment,
  AppNotification,
  CoilSensorHistory,
  CoilStatus,
  ConnectionState,
  DashboardSnapshot,
  SystemInfo,
} from "@/types/domain";

// ─── History max length ────────────────────────────────────────────────────
const MAX_HISTORY = 2000;

// ─── Context shape ─────────────────────────────────────────────────────────
export interface LiveDataContextValue {
  /** Full snapshot (for backward compat with existing screens) */
  snapshot: DashboardSnapshot;
  /** Per-coil time-series sensor history for charts */
  sensorHistory: CoilSensorHistory;
  /** Is the WebSocket connected? */
  wsConnected: boolean;
  /** Unread notification count */
  unreadCount: number;
  /** Mark all notifications as read */
  markAllRead: () => void;
  /** Clear all notifications */
  clearNotifications: () => void;
  /** Manually refresh snapshot (HTTP fallback) */
  refresh: () => Promise<void>;
  /** Live AI Vision data for Closed-Loop mode */
  aiVisionData?: { imageBase64: string; fgs_total: number; fgs_raw: any };
}

const LiveDataContext = createContext<LiveDataContextValue>({
  snapshot: mockSnapshot as any,
  sensorHistory: {},
  wsConnected: false,
  unreadCount: 0,
  markAllRead: () => {},
  clearNotifications: () => {},
  refresh: async () => {},
});

// ─── Provider ─────────────────────────────────────────────────────────────
export function LiveDataProvider({ children }: { children: React.ReactNode }) {
  const [snapshot, setSnapshot] = useState<DashboardSnapshot>(mockSnapshot as any);
  const [sensorHistory, setSensorHistory] = useState<CoilSensorHistory>({});
  const [wsConnected, setWsConnected] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const [aiVisionData, setAiVisionData] = useState<{ imageBase64: string; fgs_total: number; fgs_raw: any }>();

  // Keep a mutable ref of snapshot so WS handlers can read/mutate it without stale closures
  const snapshotRef = useRef<DashboardSnapshot>(mockSnapshot as any);

  const updateSnapshot = useCallback((next: Partial<DashboardSnapshot>) => {
    setSnapshot((prev) => {
      const updated = { ...prev, ...next };
      snapshotRef.current = updated;
      return updated;
    });
  }, []);

  // ── HTTP snapshot fallback ─────────────────────────────────────────────
  const refresh = useCallback(async () => {
    try {
      const resp = await fetch(`${serviceConfig.bridgeBaseUrl}/dashboard-snapshot`);
      if (!resp.ok) return;
      const data: DashboardSnapshot = await resp.json();
      snapshotRef.current = data;
      setSnapshot(data);
    } catch {
      /* bridge not running — keep mock */
    }
  }, []);

  // ── WebSocket message handler ──────────────────────────────────────────
  const handleWsMessage = useCallback((msg: WsMessage) => {
    switch (msg.type) {
      // Full snapshot on connect
      case "snapshot": {
        const data = msg.data as DashboardSnapshot;
        snapshotRef.current = data;
        setSnapshot(data);
        const unread = (data.notifications ?? []).filter((n) => !n.read).length;
        setUnreadCount(unread);
        break;
      }

      // Per-coil live sensor values
      case "sensor_data": {
        if (!msg.coilId || !msg.data) break;
        const coilId = msg.coilId;
        const d = msg.data as CoilStatus;

        // Update coil in snapshot
        setSnapshot((prev) => {
          const coils = prev.coils.map((c) =>
            c.id === coilId ? { ...c, ...d } : c
          );
          const updated = { ...prev, coils };
          snapshotRef.current = updated;
          return updated;
        });

        // Append to history (sliding window)
        setSensorHistory((prev) => {
          const arr = prev[coilId] ?? [];
          const point = {
            magneticMt: d.magneticMt ?? 0,
            objectTemp: d.objectTemp ?? 0,
            ambientTemp: d.ambientTemp ?? 0,
            currentA: d.currentA ?? 0,
            timestamp: msg.timestamp ?? Date.now() / 1000,
          };
          const next = arr.length >= MAX_HISTORY ? [...arr.slice(1), point] : [...arr, point];
          return { ...prev, [coilId]: next };
        });
        break;
      }

      // Coil connection / running state change
      case "coil_status": {
        if (!msg.coilId || !msg.data) break;
        const coilId = msg.coilId;
        const d = msg.data as CoilStatus;
        setSnapshot((prev) => {
          const coils = prev.coils.map((c) =>
            c.id === coilId ? { ...c, ...d } : c
          );
          const updated = { ...prev, coils };
          snapshotRef.current = updated;
          return updated;
        });
        break;
      }

      // Gateway / MQTT connection state
      case "gateway_status": {
        const d = msg.data as { gateway?: ConnectionState };
        if (d.gateway) updateSnapshot({ gateway: d.gateway });
        break;
      }

      // STM32 driver
      case "stm_status": {
        const d = msg.data as { stm?: ConnectionState };
        if (d.stm) updateSnapshot({ stm: d.stm });
        break;
      }

      // -- Control Session --
      case "session_control": {
        const data = msg.data as ActiveTreatment;
        updateSnapshot({ activeTreatment: data });
        break;
      }

      // -- AI Vision Data --
      case "ai_vision": {
        setAiVisionData(msg.data);
        break;
      }

      // Active treatment update
      case "session_update": {
        const d = msg.data as ActiveTreatment;
        updateSnapshot({ activeTreatment: d });
        break;
      }

      // New notification from bridge
      case "notification": {
        const n = msg.data as AppNotification;
        setSnapshot((prev) => {
          const notifications = [n, ...(prev.notifications ?? [])].slice(0, 50);
          const updated = { ...prev, notifications };
          snapshotRef.current = updated;
          return updated;
        });
        setUnreadCount((c) => c + 1);
        break;
      }

      default:
        break;
    }
  }, [updateSnapshot]);

  // ── Connect WebSocket ──────────────────────────────────────────────────
  const wsConnectedRef = useRef(wsConnected);
  useEffect(() => {
    wsConnectedRef.current = wsConnected;
  }, [wsConnected]);

  useEffect(() => {
    const disconnect = connectPemfWebSocket(handleWsMessage, (connected) => {
      setWsConnected(connected);
    });

    // Also load initial snapshot via HTTP in case WS takes time
    refresh();

    // HTTP polling fallback (5s) — only active when WS is disconnected
    const pollId = setInterval(() => {
      if (!wsConnectedRef.current) refresh();
    }, 5000);

    return () => {
      disconnect();
      clearInterval(pollId);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const markAllRead = useCallback(() => {
    setUnreadCount(0);
    setSnapshot((prev) => {
      const notifications = (prev.notifications ?? []).map((n) => ({ ...n, read: true }));
      return { ...prev, notifications };
    });
  }, []);

  const clearNotifications = useCallback(async () => {
    setUnreadCount(0);
    setSnapshot((prev) => ({ ...prev, notifications: [] }));
    try {
      await fetch(`${serviceConfig.bridgeBaseUrl}/notifications/clear`, { method: "POST" });
    } catch {
      /* ignore */
    }
  }, []);

  const value = {
    snapshot,
    sensorHistory,
    wsConnected,
    unreadCount,
    markAllRead,
    clearNotifications,
    refresh,
    aiVisionData,
  };

  return <LiveDataContext.Provider value={value}>{children}</LiveDataContext.Provider>;
}

// ─── Hook ─────────────────────────────────────────────────────────────────
export function useLiveData(): LiveDataContextValue {
  return useContext(LiveDataContext);
}
