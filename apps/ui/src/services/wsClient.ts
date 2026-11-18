// Author: mertaygn, cglrgrkn
import { serviceConfig } from "@/services/config";
import { guvensizBaglantiBildir, soketAdresiGuvenliMi } from "@/services/duzHttpKapisi";

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
  | "coil_ack"   // ESP start onayı: data={ok:true|false|null, reason:"ack"|"nack"|"timeout", latencyMs, ts}
  | "estop_mandali" // D1.81 · Y4: acil durdurma mandalı kuruldu/sıfırlandı — data=EstopMandali
  | "estop_teyit" // D1.E04: son acil durdurmanın teyit durumu — data=EstopTeyit
  | "stm_uyum" // TD1: kart ↔ uygulama paket uyumu kararı — data=StmUyum
  | "efield_update" // Y212 · S-D67.13: canlı E-alanı (2 Hz; hesap bitince null) — data=EFieldLive | null
  | "alan_haritasi" // GA (istem 53): canlı 3B alan haritası (1 Hz, YALNIZ abone istemciye) — data=AlanHaritasiVerisi
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
const DOGRULAMA_MS = 4000; // BE 1(d): arka plandan dönüşte ping'e bu sürede yanıt yoksa soket ölü sayılır

/** BE 1(d) · Y229: bağlantıya dışarıdan erişim. `connectPemfWebSocket` kurulurken doldurur (sahte istemcide boş kalır). */
export interface WsKontrol {
  /** Arka plandan dönüş: soket bir ileti (pong dahil) ya da yeni `onopen` ile DOĞRULANANA dek bağlantı "yok" bildirilir. */
  dogrula?: () => void;
  /** GA (istem 53): AÇIK sokete ileti (ör. `alan_abone`). Soket açık değilse / gönderim fırlatırsa false (çağıran açılışta yeniler). */
  gonder?: (ileti: object) => boolean;
  /** GA: her (yeniden) açılışta çağrılır — sunucudaki abonelikler SOKET başınadır, yeniden bağlanınca yenilenmelidir. Çağıran doldurur. */
  acilinca?: () => void;
}

// ─── Connection ──────────────────────────────────────────────────────────────
export function connectPemfWebSocket(
  onMessage: WsMessageHandler,
  onState?: (connected: boolean) => void,
  onNeedRediscovery?: () => void,
  kontrol?: WsKontrol
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
  // BE 1(d): arka plandan dönüşte OS soketi çoktan kesmiş olabilir (Samsung ~6 sn'de keser) ama donuk JS `onclose`u geç alır →
  // nokta ~2 sn YANLIŞ YEŞİL kalıyordu (31.10 ölçüldü). Doğrulama bekleyen soket ilk iletisinde (pong dahil) yeniden "bağlı" olur.
  let dogrulamaBekliyor = false;
  let dogrulamaTimer: ReturnType<typeof setTimeout> | null = null;
  const dogrulamayiBirak = () => {
    dogrulamaBekliyor = false;
    if (dogrulamaTimer) {
      clearTimeout(dogrulamaTimer);
      dogrulamaTimer = null;
    }
  };

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
        dogrulamayiBirak();
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
    if (dogrulamaBekliyor) {
      dogrulamayiBirak();
      onState?.(true); // soket arka plandan döndükten sonra gerçekten konuştu
    }
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
    /* istanbul ignore if -- ULASILAMAZ: çağıranların hepsi aynı korumadan geçer ya da kapatma zamanlayıcılarını temizler */
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
    /* istanbul ignore if -- ULASILAMAZ: kapatma yeniden bağlanma zamanlayıcısını temizler; ilk açılış kapatmadan önce */
    if (closedByCaller) return;
    // serviceConfig.websocketUrl her seferinde taze okunur — keşif sonrası yeni URL'yi alır.
    const wsBase = serviceConfig.websocketUrl;
    // D3.39 (B-6.1): düz-HTTP kapısı canlı veri soketini de kapsar — genel `ws://` adrese cihaz jetonu `?token=` ile ŞİFRESİZ
    // gidiyordu. Soket AÇILMAZ, kullanıcıya bir kez söylenir; yeniden deneme / keşif sürer (adres yerel ağa ya da TLS'ye dönebilir).
    if (!soketAdresiGuvenliMi(wsBase)) {
      guvensizBaglantiBildir(wsBase);
      onState?.(false);
      scheduleReconnect();
      return;
    }
    try {
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
          dogrulamayiBirak();
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
        dogrulamayiBirak(); // yeni soketin açılması doğrulamadır
        onState?.(true);
        startHeartbeat();
        try {
          kontrol?.acilinca?.();
        } catch {
          /* çağıranın aboneliği yenileme hatası bağlantıyı düşürmez */
        }
      };
      socket.onerror = () => onState?.(false);
      socket.onmessage = handleMessage;
      socket.onclose = (event) => {
        clearTimeout(openTimer);
        stopHeartbeat();
        dogrulamayiBirak();
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

  if (kontrol) {
    kontrol.gonder = (ileti) => {
      const s = socket;
      if (closedByCaller || !s || s.readyState !== 1 /* OPEN */) return false;
      try {
        s.send(JSON.stringify(ileti));
        return true;
      } catch {
        return false;
      }
    };
    kontrol.dogrula = () => {
      if (closedByCaller) return;
      onState?.(false);
      const s = socket;
      // Açılmamış soket (kuruluyor / yeniden bağlanıyor): `onopen` doğrular.
      if (!s || s.readyState !== 1 /* OPEN */) return;
      dogrulamaBekliyor = true;
      try {
        s.send(JSON.stringify({ type: "ping" }));
      } catch {
        /* ölü soket — süre dolunca yeniden kurulur */
      }
      if (dogrulamaTimer) clearTimeout(dogrulamaTimer);
      dogrulamaTimer = setTimeout(() => {
        dogrulamaTimer = null;
        if (!dogrulamaBekliyor || closedByCaller || s !== socket) return;
        dogrulamaBekliyor = false;
        // Yanıt yok: soket arka planda ölmüş, `onclose` gelmedi → half-open yolu (handler'ları sök, kapat, yeniden kur).
        socket = null;
        stopHeartbeat();
        try {
          s.onclose = null as any;
          s.onmessage = null as any;
          s.onerror = null as any;
          s.close();
        } catch { /* ignore */ }
        scheduleReconnect();
      }, DOGRULAMA_MS);
    };
  }

  openSocket();

  return () => {
    closedByCaller = true;
    if (reconnectTimer) clearTimeout(reconnectTimer);
    stopHeartbeat();
    dogrulamayiBirak();
    try {
      socket?.close();
    } catch {
      /* ignore */
    }
    socket = null;
  };
}
