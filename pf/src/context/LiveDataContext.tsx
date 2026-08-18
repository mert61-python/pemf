// Author: mertaygn, cglrgrkn
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

// #73: WS'ten gelen `any` sayısal alanlar string/undefined/NaN olabilir → .toFixed() RUNTIME CRASH
// (CoilCard/CoilParameterPanel/KPI-tablosu). Tek-noktada Number'a zorla → downstream formatlar
// crash-proof. Geçersiz → 0.
const _num = (v: unknown, d = 0): number => {
  const n = typeof v === "number" ? v : parseFloat(String(v));
  return Number.isFinite(n) ? n : d;
};

function normalizeStmCoils(snapshot: DashboardSnapshot): DashboardSnapshot {
  const stmOnline = snapshot.stm === "online";
  const coils = (snapshot.coils ?? []).map((coil) => {
    // Sayısal alanları TÜM coil'ler için (ESP dahil) güvene al.
    const base = {
      ...coil,
      frequencyHz: _num(coil.frequencyHz),
      dutyCycle: _num(coil.dutyCycle),
      magneticMt: _num(coil.magneticMt),
      objectTemp: _num(coil.objectTemp),
      ambientTemp: _num(coil.ambientTemp),
      currentA: _num(coil.currentA),
    };
    if (!isStmCoil(coil.id)) return base;
    return {
      ...base,
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
  /** Bağlantı DURUMU (salt backend bağlantısı): live=çevrimiçi (WS bağlı), offline=çevrimdışı.
   *  Kullanıcı-mantığı: backend'e bağlı olduğu sürece çevrimiçi. "Veri gecikmeli" GLOBAL durum olarak
   *  KALDIRILDI (boşta/AI'da yanlış-alarmdı); telemetri-tazeliği artık ayrı `telemetryStale`'de. */
  connectionQuality: "live" | "offline";
  /** TIBBİ GÜVENLİK: yalnız AKTİF TEDAVİ/bobin çalışırken beklenen canlı telemetri donduysa (WS kopuk
   *  VEYA veri ≥20sn eski) true → tedavi kartı (SessionProgressCard) "VERİ DOĞRULANMADI" uyarısı verir.
   *  Global bağlantı durumunu KİRLETMEZ (uyarı yalnız tedaviyle ilgili yerde görünür). */
  telemetryStale: boolean;
  /** En az bir kez GERÇEK veri alındı mı (false iken ekrandaki değerler mock/örnek). */
  haveRealData: boolean;
  /** Elle yeniden bağlan: WS'i yeniden kur + keşif merdivenini çalıştır. */
  reconnect: () => void;
  /** Live AI Vision data for Closed-Loop mode */
  aiVisionData?: AiVisionData;
  /** AI Pro kare yayını GERÇEKTEN akıyor mu (son kare <6sn). aiVisionData tek başına yeterli DEĞİL:
   *  son kare kalıcıdır → yayın dursa bile "canlı" görünürdü. Yalnız otonom panelde kullanılır. */
  aiVisionFresh: boolean;
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
  telemetryStale: false,
  haveRealData: false,
  reconnect: () => {},
  aiVisionFresh: false,
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
  // ORTA fix (E-stop sticky): acil-durdurma sonrası kısa pencere — soket-tamponundaki GEÇ gelen tick/coil-update
  // acil-durdurmayı görsel GERİ ALMASIN (donanım durmuşken UI "tedavi sürüyor/bobin çalışıyor" göstermesin).
  const emergencyStopTsRef = useRef(0);
  // AI Pro kare yayınının SON geliş zamanı — aiVisionData kalıcı olduğundan tazelik ayrı izlenir.
  const aiVisionTsRef = useRef(0);
  const [, setTick] = useState(0); // WS düşükken connectionQuality'yi zamanla tazelemek için hafif re-render
  // Backend'de "okundu" ucu YOK (yalnız /notifications/clear var) → okundu işareti İSTEMCİ-YEREL.
  // Bu yüzden yeniden bağlanmada gelen snapshot okunmamış rozetini geri diriltiyordu. Yerel olarak
  // okunmuş id'leri hatırla ve her snapshot'ta yeniden uygula (oturum boyu; kalıcılık gerekmiyor).
  const readIdsRef = useRef<Set<string>>(new Set());
  const applyLocalReads = useCallback((list: AppNotification[] | undefined): AppNotification[] => {
    const arr = list ?? [];
    if (readIdsRef.current.size === 0) return arr;
    return arr.map((n) => (readIdsRef.current.has(String((n as any)?.id)) ? { ...n, read: true } : n));
  }, []);

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
    // GÜVENLİK (#53): ping/pong KONTROL mesajları GERÇEK TELEMETRİ SAYILMAZ. Aksi halde backend'in
    // telemetri yayıncısı (MQTT köprüsü/session-tick) ölse bile yalnız pong dönerken lastDataTsRef
    // taze kalır → connectionQuality yanlışça 'live' der ve donmuş sıcaklık/bobin canlı gösterilir.
    // GÜVENLİK (#12): "taze veri" sayılacak mesajlar SENSÖR/BOBİN telemetrisiyle SINIRLI. Eskiden
    // ping/pong dışındaki HER mesaj tazelik damgası atıyordu; oysa `notification`, `gateway_status`,
    // `ai_vision` ve `session_tick` telemetri yayıncısından BAĞIMSIZ üretilir. MQTT köprüsü/sensör
    // akışı ölse bile bunlar akmaya devam ettiğinden lastDataTs taze kalıyor → aktif tedavide DONMUŞ
    // sıcaklık/akım değerleri `telemetryStale` ile YAKALANAMIYOR, SessionProgressCard "VERİ
    // DOĞRULANMADI" uyarısını hiç göstermiyordu. Artık yalnız gerçek telemetri sayılır.
    const TELEMETRY_TYPES = ["snapshot", "sensor_data", "coil_status", "stm_coil_update", "stm_status"];
    if (TELEMETRY_TYPES.includes(msg.type as string)) {
      markRealData(); // GERÇEK telemetri akıyor → 'canlı' say (mock/donmuş veri ayrımı için)
    }
    switch (msg.type) {
      // Full snapshot on connect
      case "snapshot": {
        const raw = normalizeStmCoils(msg.data as DashboardSnapshot);
        // Yerel "okundu" işaretlerini koru → yeniden bağlanmada rozet geri dirilmesin.
        const data = { ...raw, notifications: applyLocalReads(raw.notifications) };
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
          // #73 (D1): WS `any` alanları string/NaN olabilir → _num ile Number'a zorla (nullish `?? 0`
          // yetmez: "44.5" string kalır ve KPI tablosunda .toFixed() CRASH eder).
          const point = {
            magneticMt: _num(d.magneticMt),
            objectTemp: _num(d.objectTemp),
            ambientTemp: _num(d.ambientTemp),
            currentA: _num(d.currentA),
            timestamp: _num(msg.timestamp, Date.now() / 1000),
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
        let d = msg.data as CoilStatus;
        if ((d as any)?.running && Date.now() - emergencyStopTsRef.current < 3000) d = { ...d, running: false };
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
        aiVisionTsRef.current = Date.now();
        setAiVisionData(msg.data);
        break;
      }

      // Active treatment update
      case "session_update":
      // Session timer tick (elapsed/remaining güncelleme)
      case "session_tick": {
        let d = msg.data as ActiveTreatment;
        // E-stop sticky: acil-durdurmadan hemen sonra gelen geç tick, isActive'i yeniden true yapmasın.
        if (d?.isActive && Date.now() - emergencyStopTsRef.current < 3000) d = { ...d, isActive: false };
        updateSnapshot({ activeTreatment: d });
        break;
      }

      // STM32 USB CDC'den gelen gerçek zamanlı coil verisi
      case "stm_coil_update": {
        if (!msg.coilId || !msg.data) break;
        const coilId = msg.coilId;
        let d = msg.data as CoilStatus;
        // E-stop sticky: geç coil-update bobini yeniden running:true göstermesin (donanım durmuş).
        if ((d as any)?.running && Date.now() - emergencyStopTsRef.current < 3000) d = { ...d, running: false };
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
        emergencyStopTsRef.current = Date.now();
        // AI Pro kapalı-döngüsü de durdu → son kareyi ve tazelik damgasını TEMİZLE. Aksi halde
        // AI Hub'daki "OTONOM BİOFEEDBACK AKTİF" rozeti donmuş kareyle açık kalıyordu.
        aiVisionTsRef.current = 0;
        setAiVisionData(undefined);
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

  // Bir keşif turu BAŞARISIZ bittiğinde bir sonrakine kadar beklenecek en kısa süre.
  // NEDEN: `pendingDiscoverRef` döngüsü + WS'in her 4 başarısız denemede `onNeedRediscovery`
  // çağırması birleşince, cihaz erişilemezken uygulama kesintisiz tam /24 subnet taraması
  // döngüsüne giriyordu (her tur ~35sn, sub-ağ başına 40 eşzamanlı fetch). Klinikte gün boyu
  // açık kalan tablette bu, pil ve CPU'yu boşuna tüketiyordu. Başarılı turdan sonra bekleme YOK.
  const DISCOVERY_COOLDOWN_MS = 20000;
  const lastFailedDiscoveryRef = useRef(0);

  const runDiscovery = useCallback(async (forceReconnect: boolean) => {
    // Keşif sürüyorsa AT-MA, BEKLET → mevcut bitince bir kez daha çalışır. (Audit P1: WiFi↔mobil-veri
    // geçişinde, devam eden uzun keşif yüzünden NetInfo tetiği düşüp uzun süre kopuk kalıyordu.)
    if (discoveringRef.current) { pendingDiscoverRef.current = true; return; }
    discoveringRef.current = true;
    try {
      do {
        pendingDiscoverRef.current = false;
        const sinceFail = Date.now() - lastFailedDiscoveryRef.current;
        if (sinceFail < DISCOVERY_COOLDOWN_MS) break; // soğuma: art arda tam tarama yapma
        const prevWs = serviceConfig.websocketUrl; // adres GERÇEKTEN değişti mi?
        try {
          const res = await discoverBackend();
          if (res) {
            lastFailedDiscoveryRef.current = 0; // bulundu → soğutmayı sıfırla
            // SADECE adres değişince WS'i yeniden kur (sağlıklı WS'i boşuna yıkıp telemetri boşluğu yaratma).
            if (forceReconnect && serviceConfig.websocketUrl !== prevWs) {
              setConnectionEpoch((e) => e + 1);
            }
          } else {
            lastFailedDiscoveryRef.current = Date.now();
          }
        } catch {
          lastFailedDiscoveryRef.current = Date.now();
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
  // WS efekti bu bayrak true olmadan soket AÇMAZ (aşağıdaki nedene bak).
  const [tokenLoaded, setTokenLoaded] = useState(false);
  useEffect(() => {
    let cancelled = false;
    (async () => {
      await loadStoredApiToken();
      if (cancelled) return;
      setTokenLoaded(true);
      runDiscovery(true);
    })();
    return () => { cancelled = true; };
  }, [runDiscovery]);

  // 2) WebSocket — connectionEpoch değişince güncel URL ile yeniden bağlanır.
  //    YARIŞ: bu efekt mount'ta ÇALIŞIYOR, `loadStoredApiToken()` ise henüz çözülmemiş oluyordu →
  //    ilk soket TOKENSİZ açılıyordu. Uzaktan (tünel) soğuk açılışta backend 1008 (policy violation)
  //    ile kapatıyor, wsClient bunu görüp backoff'u 30 saniyeye çıkarıyordu; saklı adres değişmediği
  //    için keşif de epoch bump'lamıyordu → uygulama açılışta ~30sn boyunca canlı telemetrisiz
  //    kalıyordu. Artık token belleğe alınmadan soket açılmaz.
  useEffect(() => {
    if (!tokenLoaded) return;
    const disconnect = connectPemfWebSocket(
      handleWsMessage,
      (connected) => setWsConnected(connected),
      () => runDiscovery(true) // tekrarlayan kopmada adres değişmiş olabilir → yeniden keşif
    );

    refresh();

    // Yedek HTTP poll'ü. apiGet 8sn timeout'lu, poll aralığı 5sn → çevrimdışıyken (her istek
    // timeout'a kadar asılı kalır) istekler ÜST ÜSTE biniyordu; her yeni tur bir öncekiler
    // bitmeden ekleniyor, mobilde soket havuzu ve pil boşuna tükeniyordu. Uçuşta istek varken atla.
    let pollInFlight = false;
    const pollId = setInterval(() => {
      if (wsConnectedRef.current || pollInFlight) return;
      pollInFlight = true;
      refresh().finally(() => { pollInFlight = false; });
    }, 5000);

    return () => {
      disconnect();
      clearInterval(pollId);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connectionEpoch, tokenLoaded]);

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

  // telemetryStale veri-YAŞINA bağlı (tedavi sırasında WS canlı olsa bile donmuş telemetriyi yakalar),
  // bu yüzden ticker çalışır: data-frozen-but-socket-alive geçişini re-render'la tetikler. (Boştayken
  // telemetryStale daima false → memo bail eder, tüketiciler render OLMAZ; yalnız hafif provider tick'i.)
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 4000);
    return () => clearInterval(id);
  }, []);

  // (Bağlantı durumu + telemetri-tazeliği ayrımı hemen aşağıda; connectionQuality=salt-bağlantı,
  //  telemetryStale=aktif-tedavide-donmuş-veri. Detay: pemf-connection-status-2state.)
  const _dataAge = Date.now() - lastDataTsRef.current;
  // Beklenen canlı-telemetri var mı: yalnız AKTİF TEDAVİ ya da bir bobin çalışırken izlenecek
  // değişen değer (sıcaklık/akım/alan) VARDIR; boştayken (seans yok) yoktur.
  const _expectLiveTelemetry =
    (snapshot as any)?.activeTreatment?.isActive === true ||
    (snapshot?.coils ?? []).some((c) => (c as any)?.running === true);
  // GLOBAL bağlantı DURUMU = SALT backend bağlantısı: bağlıysa çevrimiçi, değilse çevrimdışı.
  // (Eski 3-durumlu 'veri gecikmeli' KALDIRILDI — boşta/AI'da yanlış-alarm + sinir bozucuydu;
  // kullanıcı-mantığı: backend'e bağlı olduğu sürece çevrimiçi.)
  const connectionQuality: "live" | "offline" = wsConnected ? "live" : "offline";
  // TIBBİ GÜVENLİK: yalnız beklenen-canlı-telemetri varken (tedavi/bobin) donmuş/kayıp veriyi işaretle
  // → tedavi kartı "VERİ DOĞRULANMADI" der. WS kopuk VEYA telemetri ≥20sn eskiyse stale. Boştayken
  // (izlenecek canlı değer yok) DAİMA false → global durum temiz kalır.
  const telemetryStale =
    _expectLiveTelemetry && (!wsConnected || !haveRealData || _dataAge >= 20000);
  // AI Pro kare yayını canlı mı (yayın ~1 Hz → 6sn cömert bir eşik). Yalnız AI Hub otonom panelinde
  // kullanılır; GLOBAL bağlantı durumunu KİRLETMEZ (kaldırılan 3-durumlu gösterge geri gelmez).
  // Üstteki 4sn'lik ticker bu değerin zamanla tazelenmesini sağlar.
  const aiVisionFresh = !!aiVisionData && wsConnected && Date.now() - aiVisionTsRef.current < 6000;

  const markAllRead = useCallback(() => {
    setUnreadCount(0);
    setSnapshot((prev) => {
      // Okunan id'leri hatırla → sonraki snapshot bunları "okunmamış"a geri döndürmesin.
      for (const n of prev.notifications ?? []) readIdsRef.current.add(String((n as any)?.id));
      const notifications = (prev.notifications ?? []).map((n) => ({ ...n, read: true }));
      const updated = { ...prev, notifications };
      snapshotRef.current = updated;
      return updated;
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
      telemetryStale,
      haveRealData,
      reconnect,
      aiVisionData,
      aiVisionFresh,
    }),
    [snapshot, sensorHistory, wsConnected, unreadCount, markAllRead,
     clearNotifications, refresh, connectionQuality, telemetryStale, haveRealData, reconnect,
     aiVisionData, aiVisionFresh]
  );

  return <LiveDataContext.Provider value={value}>{children}</LiveDataContext.Provider>;
}

// ─── Hook ─────────────────────────────────────────────────────────────────
export function useLiveData(): LiveDataContextValue {
  return useContext(LiveDataContext);
}
