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
import { discoverBackend } from "@/services/discovery";
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
const STM_COIL_MAX_ID = 5;

// AI Pro kapalı-döngü canlı telemetrisi (backend ai_router._ai_pro_loop yayını).
export interface AiVisionData {
  imageBase64: string;
  fgs_total: number;
  fgs_raw: any;
  target?: { x: number; y: number; z: number };
  eField?: number;
  organId?: number;
  organName?: string;
  perCoil?: { id: number; freq: number; duty: number; phase: number }[];
  remainingSec?: number;
  durationMin?: number;
}

function isStmCoil(coilId: number): boolean {
  return coilId >= 1 && coilId <= STM_COIL_MAX_ID;
}

function normalizeStmCoils(snapshot: DashboardSnapshot): DashboardSnapshot {
  const stmOnline = snapshot.stm === "online";
  const coils = (snapshot.coils ?? []).map((coil) => {
    if (!isStmCoil(coil.id)) return coil;
    return {
      ...coil,
      stm32Driven: true,
      connected: stmOnline,
      running: stmOnline ? coil.running : false,
    };
  });
  return { ...snapshot, coils };
}

function mergeCoilIntoSnapshot(
  snapshot: DashboardSnapshot,
  coilId: number,
  data: Partial<CoilStatus>,
  nextRoot: Partial<DashboardSnapshot> = {}
): DashboardSnapshot {
  const coils = snapshot.coils.map((coil) =>
    coil.id === coilId ? { ...coil, ...data } : coil
  );
  return normalizeStmCoils({ ...snapshot, ...nextRoot, coils });
}

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
  aiVisionData?: AiVisionData;
}

const LiveDataContext = createContext<LiveDataContextValue>({
  snapshot: normalizeStmCoils(mockSnapshot as DashboardSnapshot),
  sensorHistory: {},
  wsConnected: false,
  unreadCount: 0,
  markAllRead: () => {},
  clearNotifications: () => {},
  refresh: async () => {},
});

// ─── Provider ─────────────────────────────────────────────────────────────
export function LiveDataProvider({ children }: { children: React.ReactNode }) {
  const [snapshot, setSnapshot] = useState<DashboardSnapshot>(
    normalizeStmCoils(mockSnapshot as DashboardSnapshot)
  );
  const [sensorHistory, setSensorHistory] = useState<CoilSensorHistory>({});
  const [wsConnected, setWsConnected] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const [aiVisionData, setAiVisionData] = useState<AiVisionData>();

  // Keep a mutable ref of snapshot so WS handlers can read/mutate it without stale closures
  const snapshotRef = useRef<DashboardSnapshot>(
    normalizeStmCoils(mockSnapshot as DashboardSnapshot)
  );

  const updateSnapshot = useCallback((next: Partial<DashboardSnapshot>) => {
    setSnapshot((prev) => {
      const updated = normalizeStmCoils({ ...prev, ...next });
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
      const normalized = normalizeStmCoils(data);
      snapshotRef.current = normalized;
      setSnapshot(normalized);
    } catch {
      /* bridge not running — keep mock */
    }
  }, []);

  // ── WebSocket message handler ──────────────────────────────────────────
  const handleWsMessage = useCallback((msg: WsMessage) => {
    switch (msg.type) {
      // Full snapshot on connect
      case "snapshot": {
        const data = normalizeStmCoils(msg.data as DashboardSnapshot);
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
          const updated = mergeCoilIntoSnapshot(prev, coilId, d);
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
          const updated = mergeCoilIntoSnapshot(prev, coilId, d);
          snapshotRef.current = updated;
          return updated;
        });
        break;
      }

      // Gateway / MQTT connection state
      case "gateway_status": {
        const d = msg.data as { gateway?: ConnectionState; mqtt?: ConnectionState };
        const next: Partial<DashboardSnapshot> = {};
        if (d.gateway) next.gateway = d.gateway;
        if (d.mqtt) next.mqtt = d.mqtt;
        if (Object.keys(next).length) updateSnapshot(next);
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

      // Session timer tick (elapsed/remaining güncelleme)
      case "session_tick": {
        const d = msg.data as ActiveTreatment;
        updateSnapshot({ activeTreatment: d });
        break;
      }

      // STM32 USB CDC'den gelen gerçek zamanlı coil verisi
      case "stm_coil_update": {
        if (!msg.coilId || !msg.data) break;
        const coilId = msg.coilId;
        const d = msg.data as CoilStatus;
        setSnapshot((prev) => {
          const updated = mergeCoilIntoSnapshot(
            prev,
            coilId,
            { ...d, stm32Driven: true },
            isStmCoil(coilId) ? { stm: "online" } : {}
          );
          snapshotRef.current = updated;
          return updated;
        });
        break;
      }

      // Acil durdurma sinyali
      case "emergency_stop": {
        setSnapshot((prev) => {
          const coils = prev.coils.map((c) => ({ ...c, running: false }));
          const activeTreatment = {
            ...prev.activeTreatment,
            isActive: false,
            mode: "Acil Durduruldu",
          };
          const updated = normalizeStmCoils({ ...prev, coils, activeTreatment });
          snapshotRef.current = updated;
          return updated;
        });
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

  // ── Bağlantı orkestrasyonu: keşif + WebSocket + güçlü yeniden-bağlanma ──
  const wsConnectedRef = useRef(wsConnected);
  useEffect(() => {
    wsConnectedRef.current = wsConnected;
  }, [wsConnected]);

  // connectionEpoch artınca WS, güncel serviceConfig.websocketUrl ile yeniden kurulur.
  const [connectionEpoch, setConnectionEpoch] = useState(0);
  const discoveringRef = useRef(false);

  const runDiscovery = useCallback(async (forceReconnect: boolean) => {
    if (discoveringRef.current) return;
    discoveringRef.current = true;
    try {
      const res = await discoverBackend();
      // Yeni bir adres bulunduysa (mevcut web origin'i değilse) WS'i yeniden kur.
      if (res && res.source !== "current" && forceReconnect) {
        setConnectionEpoch((e) => e + 1);
      }
    } catch {
      /* keşif hatası — mevcut bağlantıyla devam */
    } finally {
      discoveringRef.current = false;
    }
  }, []);

  // 1) Açılışta otomatik keşif (web'de origin zaten doğru → hızlı geçer).
  useEffect(() => {
    runDiscovery(true);
  }, [runDiscovery]);

  // 2) WebSocket — connectionEpoch değişince güncel URL ile yeniden bağlanır.
  useEffect(() => {
    const disconnect = connectPemfWebSocket(
      handleWsMessage,
      (connected) => setWsConnected(connected),
      () => runDiscovery(true) // tekrarlayan kopmada adres değişmiş olabilir → yeniden keşif
    );

    refresh();

    const pollId = setInterval(() => {
      if (!wsConnectedRef.current) refresh();
    }, 5000);

    return () => {
      disconnect();
      clearInterval(pollId);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connectionEpoch]);

  // 3) Ağ değişiminde (WiFi geçişi / yeniden bağlanma) keşfi tetikle.
  useEffect(() => {
    let NetInfo: any;
    try {
      // @ts-ignore - opsiyonel native modül (npm install sonrası mevcut)
      NetInfo = require("@react-native-community/netinfo").default;
    } catch {
      return; // paket yoksa (ör. web) atla
    }
    const unsub = NetInfo.addEventListener((state: any) => {
      if (state?.isConnected) runDiscovery(true);
    });
    return () => {
      try {
        unsub?.();
      } catch {
        /* ignore */
      }
    };
  }, [runDiscovery]);

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
