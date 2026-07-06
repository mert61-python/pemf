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
  useMemo,
  useRef,
  useState,
} from "react";
import { serviceConfig, loadStoredApiToken } from "@/services/config";
import { apiGet, apiPost } from "@/services/apiClient";
import { connectPemfWebSocket, WsMessage } from "@/services/wsClient";
import { discoverBackend } from "@/services/discovery";
import { mockSnapshot } from "@/services/mockData";
import { useNetworkReachability } from "@/hooks/useNetworkReachability";
import { useForegroundReconnect } from "@/hooks/useForegroundReconnect";
import type {
  ActiveTreatment,
  AppNotification,
  CoilSensorHistory,
  CoilStatus,
  ConnectionState,
  DashboardSnapshot,
} from "@/types/domain";

// ─── History max length ────────────────────────────────────────────────────
const MAX_HISTORY = 2000;
const STM_COIL_MAX_ID = 5;

// AI Pro kapalı-döngü canlı telemetrisi (backend ai_router._ai_pro_loop yayını).
export interface AiVisionData {
  imageBase64?: string;
  /** Organ lokalize edildi mi — AI Pro cat_organ pipeline'ı (el-takibi söküldü). */
  detected?: boolean;
  /** Organ lokalizasyon güveni [0,1]. */
  reliability?: number;
  /** Eski FGS alanları (artık AI Pro yayını göndermiyor; geriye uyumluluk için opsiyonel). */
  fgs_total?: number | null;
  fgs_raw?: unknown;  // eski/legacy alan — artık gönderilmiyor, hiçbir yerde okunmuyor
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
  /** Bağlantı kalitesi: live=WS canlı, stale=veri gecikmeli/donmuş riski, offline=GERÇEK veri YOK. */
  connectionQuality: "live" | "stale" | "offline";
  /** En az bir kez GERÇEK veri alındı mı (false iken ekrandaki değerler mock/örnek). */
  haveRealData: boolean;
  /** Elle yeniden bağlan: WS'i yeniden kur + keşif merdivenini çalıştır. */
  reconnect: () => void;
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
  connectionQuality: "offline",
  haveRealData: false,
  reconnect: () => {},
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
  // Faz3 medikal-güvenlik: GERÇEK veri geldi mi + son veri zamanı → donmuş/örnek veriyi 'canlı' gösterme.
  const [haveRealData, setHaveRealData] = useState(false);
  const lastDataTsRef = useRef(0);
  const [, setTick] = useState(0); // WS düşükken connectionQuality'yi zamanla tazelemek için hafif re-render
  const markRealData = useCallback(() => {
    lastDataTsRef.current = Date.now();
    setHaveRealData(true); // React aynı değerde bail eder → ilk seferden sonra ekstra render yok
  }, []);

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
    // apiGet üzerinden: X-API-Key (uzaktan auth) + zaman aşımı + 401'de token temizleme.
    // (Audit: ham fetch tokensiz/timeout'suzdu → tünelde her 5sn 401, fallback hiç çalışmıyordu.)
    const data = await apiGet<DashboardSnapshot | null>("/dashboard-snapshot", null, { silent: true });
    if (!data) return;
    const normalized = normalizeStmCoils(data);
    snapshotRef.current = normalized;
    setSnapshot(normalized);
    markRealData(); // HTTP fallback başarılı → gerçek veri var
  }, [markRealData]);

  // ── WebSocket message handler ──────────────────────────────────────────
  const handleWsMessage = useCallback((msg: WsMessage) => {
    markRealData(); // GERÇEK veri akıyor → 'canlı' say (mock/donmuş veri ayrımı için)
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
  }, [updateSnapshot, markRealData]);

  // ── Bağlantı orkestrasyonu: keşif + WebSocket + güçlü yeniden-bağlanma ──
  const wsConnectedRef = useRef(wsConnected);
  useEffect(() => {
    wsConnectedRef.current = wsConnected;
  }, [wsConnected]);

  // connectionEpoch artınca WS, güncel serviceConfig.websocketUrl ile yeniden kurulur.
  const [connectionEpoch, setConnectionEpoch] = useState(0);
  const discoveringRef = useRef(false);
  const pendingDiscoverRef = useRef(false);

  const runDiscovery = useCallback(async (forceReconnect: boolean) => {
    // Keşif sürüyorsa AT-MA, BEKLET → mevcut bitince bir kez daha çalışır. (Audit P1: WiFi↔mobil-veri
    // geçişinde, devam eden uzun keşif yüzünden NetInfo tetiği düşüp uzun süre kopuk kalıyordu.)
    if (discoveringRef.current) { pendingDiscoverRef.current = true; return; }
    discoveringRef.current = true;
    try {
      do {
        pendingDiscoverRef.current = false;
        const prevWs = serviceConfig.websocketUrl; // adres GERÇEKTEN değişti mi?
        try {
          const res = await discoverBackend();
          // SADECE adres değişince WS'i yeniden kur (sağlıklı WS'i boşuna yıkıp telemetri boşluğu yaratma).
          if (res && forceReconnect && serviceConfig.websocketUrl !== prevWs) {
            setConnectionEpoch((e) => e + 1);
          }
        } catch {
          /* keşif hatası — mevcut bağlantıyla devam */
        }
      } while (pendingDiscoverRef.current); // keşif sırasında yeni istek geldiyse (ağ değişti) tekrarla
    } finally {
      discoveringRef.current = false;
    }
  }, []);

  // 1) Açılışta: ÖNCE saklı api_token'ı serviceConfig'e yükle (uzaktan auth için ZORUNLU —
  //    yoksa cold-start'ta WS/REST 401), SONRA keşif. Keşif yeni adresi uygulayıp connectionEpoch'u
  //    bump'layınca WS token'la (yeniden) açılır. (Audit P0: loadStoredApiToken yalnız Ayarlar'da idi.)
  useEffect(() => {
    let cancelled = false;
    (async () => {
      await loadStoredApiToken();
      if (!cancelled) runDiscovery(true);
    })();
    return () => { cancelled = true; };
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

  // 3+4) Ağ değişimi (WiFi geçişi) + ön-plana dönüş → keşfi/yeniden-bağlanmayı tetikle.
  //      (audit B-2.4: NetInfo + AppState mantığı tiplenmiş, test-edilebilir hook'lara çıkarıldı →
  //      god-context küçüldü; `any`'ler giderildi. Public API/davranış AYNI.)
  const triggerReconnect = useCallback(() => runDiscovery(true), [runDiscovery]);
  useNetworkReachability(triggerReconnect);
  useForegroundReconnect(triggerReconnect);

  // Faz3: elle yeniden bağlan (gösterge/banner'a dokununca) — WS yeniden kur + keşif merdiveni.
  const reconnect = useCallback(() => {
    setConnectionEpoch((e) => e + 1);
    runDiscovery(true);
  }, [runDiscovery]);

  // WS düşükken connectionQuality'nin 'stale'→'offline'a geçebilmesi için hafif ticker (4sn).
  useEffect(() => {
    if (wsConnected) return;
    const id = setInterval(() => setTick((t) => t + 1), 4000);
    return () => clearInterval(id);
  }, [wsConnected]);

  // Bağlantı kalitesi: WS canlıysa live; değilse son gerçek veri 15sn içindeyse stale (gecikmeli),
  // yoksa offline (hiç gerçek veri yok / donmuş). Ekran böylece mock/donmuş veriyi 'canlı' göstermez.
  const connectionQuality: "live" | "stale" | "offline" =
    wsConnected ? "live"
      : haveRealData && Date.now() - lastDataTsRef.current < 15000 ? "stale"
      : "offline";

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
    // apiPost: uzaktan auth header'ı + zaman aşımı (ham fetch tokensiz tünelde 401'liyordu).
    await apiPost("/notifications/clear", {}, null, { silent: true });
  }, []);

  // value'yu memoize et → sağlayıcı parent nedeniyle (state değişmeden) yeniden render
  // olduğunda tüketiciler gereksiz render OLMASIN. (Not: snapshot/sensorHistory yüksek
  // frekansta değiştiğinden telemetri sırasındaki render'ları tam elemek için ileride
  // context'i canlı-veri / durağan-API olarak İKİYE bölmek gerekir — bu ayrı bir refactor.)
  const value = useMemo(
    () => ({
      snapshot,
      sensorHistory,
      wsConnected,
      unreadCount,
      markAllRead,
      clearNotifications,
      refresh,
      connectionQuality,
      haveRealData,
      reconnect,
      aiVisionData,
    }),
    [snapshot, sensorHistory, wsConnected, unreadCount, markAllRead,
     clearNotifications, refresh, connectionQuality, haveRealData, reconnect, aiVisionData]
  );

  return <LiveDataContext.Provider value={value}>{children}</LiveDataContext.Provider>;
}

// ─── Hook ─────────────────────────────────────────────────────────────────
export function useLiveData(): LiveDataContextValue {
  return useContext(LiveDataContext);
}
