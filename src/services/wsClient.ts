// Author: mertaygn, cglrgrkn
import { serviceConfig } from "@/services/config";

// ─── Message types from the bridge ───────────────────────────────────────────
export type WsMessageType =
  | "snapshot"
  | "sensor_data"
  | "coil_status"
  | "stm_coil_update"
  | "esp_event"
  | "alarm"
  | "notification"
  | "gateway_status"
  | "stm_status"
  | "session_update"
  | "session_control"
  | "session_tick"
  | "emergency_stop"
  | "ai_vision"
  | "pong";  // heartbeat yanıtı (backend ping'e döner)

export interface WsMessage {
  type: WsMessageType;
  coilId?: number;
  data?: any;
  eventType?: string;
  timestamp?: number;
}

export type WsMessageHandler = (message: WsMessage) => void;

// ─── Güçlü reconnect ayarları ────────────────────────────────────────────────
const PING_INTERVAL_MS = 15000; // her 15sn ping
const STALE_TIMEOUT_MS = 25000; // bu süre mesaj gelmezse half-open say → kapat
const REDISCOVER_AFTER_FAILS = 4; // bu kadar başarısız denemeden sonra yeniden keşif iste
const CONNECT_TIMEOUT_MS = 10000; // CONNECTING aşaması bu sürede açılmazsa soket ölü sayılır

// ─── Connection ──────────────────────────────────────────────────────────────
export function connectPemfWebSocket(
  onMessage: WsMessageHandler,
  onState?: (connected: boolean) => void,
  onNeedRediscovery?: () => void
): () => void {
  if (typeof WebSocket === "undefined") {
    onState?.(false);
    return () => undefined;
  }

  let socket: WebSocket | null = null;
  let closedByCaller = false;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let pingTimer: ReturnType<typeof setInterval> | null = null;
  let reconnectDelay = 1000;
  let consecutiveFails = 0;
  let lastMessageTs = Date.now();

  const stopHeartbeat = () => {
    if (pingTimer) {
      clearInterval(pingTimer);
      pingTimer = null;
    }
  };

  const startHeartbeat = () => {
    stopHeartbeat();
    lastMessageTs = Date.now();
    pingTimer = setInterval(() => {
      // Half-open tespiti: uzun süredir hiç mesaj yok. YÜKSEK fix: sadece socket.close() çağırıp
      // reconnect'i onclose'a bırakmak YETMEZ — half-open sokette onclose bazen HİÇ tetiklenmez →
      // kalıcı SESSİZ kopukluk (UI "CANLI/bağlı" kalır, veri donuk). Burada PROAKTİF reconnect yap:
      // ölü soketin handler'larını sök (onclose çift-tetiklemesin) + kapat + durum-bildir + reconnect.
      if (Date.now() - lastMessageTs > STALE_TIMEOUT_MS) {
        const dead = socket;
        socket = null;
        stopHeartbeat();
        if (dead) {
          try {
            dead.onclose = null as any;
            dead.onmessage = null as any;
            dead.onerror = null as any;
            dead.close();
          } catch { /* ignore */ }
        }
        onState?.(false);
        scheduleReconnect();
        return;
      }
      try {
        socket?.send(JSON.stringify({ type: "ping" }));
      } catch {
        /* ignore */
      }
    }, PING_INTERVAL_MS);
  };

  const handleMessage = (event: MessageEvent) => {
    lastMessageTs = Date.now();
    // AYRIM: JSON ayrıştırma hatası ile İŞLEYİCİ hatası aynı catch'te yutuluyordu. Bir reducer
    // hatası (ör. beklenmedik alan) "geçersiz JSON" sayılıp sessizce düşüyor, telemetri hiç
    // uygulanmıyor ama soket canlı olduğu için UI "CANLI" kalıyordu — donmuş değerler canlı gibi.
    let msg: WsMessage;
    try {
      msg = JSON.parse(event.data);
    } catch {
      return; // gerçekten JSON değil (captive portal / ping metni) — yut
    }
    if (msg?.type === "pong") return; // heartbeat yanıtı — yut
    try {
      onMessage(msg);
    } catch (err) {
      // İşleyici hatası YUTULMAZ: en azından iz bırak (client_errors'a global handler taşır).
      console.error("WS mesaj işleyicisi hata verdi:", msg?.type, err);
    }
  };

  const scheduleReconnect = () => {
    if (closedByCaller) return;
    consecutiveFails += 1;
    // Adres değişmiş olabilir (DHCP / ağ geçişi / tünel URL rotasyonu) → yeniden keşif iste.
    // TEK-SEFER değil HER REDISCOVER_AFTER_FAILS denemede: uzun kesintide tünel URL'si bağlıyken
    // rotasyona uğrarsa tek denemede bulunamayıp kalıcı kopuk kalıyordu (audit P1).
    if (onNeedRediscovery && consecutiveFails % REDISCOVER_AFTER_FAILS === 0) {
      try {
        onNeedRediscovery();
      } catch {
        /* ignore */
      }
    }
    reconnectTimer = setTimeout(() => {
      reconnectDelay = Math.min(reconnectDelay * 1.5, 15000);
      openSocket();
    }, reconnectDelay);
  };

  const openSocket = () => {
    if (closedByCaller) return;
    try {
      // serviceConfig.websocketUrl her seferinde taze okunur — keşif sonrası yeni URL'yi alır.
      const wsBase = serviceConfig.websocketUrl;
      const wsUrl = serviceConfig.apiToken
        ? wsBase + (wsBase.includes("?") ? "&" : "?") + "token=" + encodeURIComponent(serviceConfig.apiToken)
        : wsBase;
      socket = new WebSocket(wsUrl);
      // KURULUM (CONNECTING) ZAMAN AŞIMI: half-open denetimi yalnız soket AÇILDIKTAN SONRA
      // (startHeartbeat) devreye giriyordu. TCP el sıkışması asılı kalırsa (captive portal, düşen
      // tünel, filtreleyen ağ) ne `onopen` ne `onclose` tetiklenir → reconnect ZİNCİRİ HİÇ
      // başlamaz ve uygulama sessizce sonsuza dek "bağlanıyor" durumunda kalırdı.
      const connecting = socket;
      const openTimer = setTimeout(() => {
        if (closedByCaller || connecting !== socket) return;
        if (connecting.readyState === 0 /* CONNECTING */) {
          try {
            connecting.onclose = null as any;
            connecting.onmessage = null as any;
            connecting.onerror = null as any;
            connecting.close();
          } catch { /* ignore */ }
          socket = null;
          onState?.(false);
          scheduleReconnect();
        }
      }, CONNECT_TIMEOUT_MS);
      socket.onopen = () => {
        clearTimeout(openTimer);
        // DÜŞÜK fix: CONNECTING sokette unmount olduysa (closedByCaller) heartbeat başlatma → kapat + çık
        // (aksi halde temizlenmemiş interval + kapanmış-context setState).
        if (closedByCaller) { try { socket?.close(); } catch { /* ignore */ } return; }
        reconnectDelay = 1000; // backoff sıfırla
        consecutiveFails = 0;
        onState?.(true);
        startHeartbeat();
      };
      socket.onerror = () => onState?.(false);
      socket.onmessage = handleMessage;
      socket.onclose = (event) => {
        clearTimeout(openTimer);
        stopHeartbeat();
        // YARIŞ: epoch değişiminde (keşif yeni adres bulunca) önce disconnect() çağrılır, hemen
        // ardından YENİ soket kurulur. Eski soketin onclose'u SONRA tetiklendiğinde aynı setter'ı
        // `false` ile çağırıp CANLI olan yeni bağlantıyı "Çevrimdışı" işaretliyordu (banner yanıp
        // sönüyor, kullanıcı gereksiz "yeniden bağlan"a basıyordu). Çağıran kapattıysa sus.
        if (closedByCaller) return;
        onState?.(false);
        // 1008 = policy violation (auth/token). Token ASLA SİLİNMEZ (kullanıcı bir kez bağlandıysa
        // tekrar uğraştırılmaz). HOT-LOOP YAPMA: uzun backoff + yeniden keşif iste. Yanlış/eski
        // token LAN'da provisionToken ile otomatik tazelenir → epoch bump ile hemen bağlanır.
        if (event?.code === 1008) {
          reconnectDelay = 30000;
          if (onNeedRediscovery) { try { onNeedRediscovery(); } catch { /* ignore */ } }
        }
        scheduleReconnect();
      };
    } catch {
      onState?.(false);
      scheduleReconnect();
    }
  };

  openSocket();

  return () => {
    closedByCaller = true;
    if (reconnectTimer) clearTimeout(reconnectTimer);
    stopHeartbeat();
    try {
      socket?.close();
    } catch {
      /* ignore */
    }
    socket = null;
  };
}
