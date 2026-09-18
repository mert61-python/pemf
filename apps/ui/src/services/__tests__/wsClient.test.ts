// Author: mertaygn, cglrgrkn
/**
 * wsClient dayanıklılık testleri (prod-readiness F-2/T-2): en karmaşık stateful modül testsizdi.
 * Mock WebSocket + fake-timer ile: açılış/state, mesaj/pong-yutma, half-open(25sn)→close,
 * backoff'lu reconnect, 1008(auth) hot-loop-yok, disconnect temizliği.
 */
import { connectPemfWebSocket } from "../wsClient";
import { serviceConfig } from "../config";

class MockWS {
  static instances: MockWS[] = [];
  url: string;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: ((e: { code: number }) => void) | null = null;
  sent: string[] = [];
  closed = false;
  /** Gerçek WebSocket.readyState (0=CONNECTING, 1=OPEN). Kurulum-zaman-aşımı testi bunu okur. */
  readyState = 0;
  constructor(url: string) {
    this.url = url;
    MockWS.instances.push(this);
  }
  send(d: string) {
    this.sent.push(d);
  }
  close() {
    this.closed = true;
  } // gerçek WS gibi: close() onclose'u SENKRON tetiklemez (test acikca simule eder)
  static last() {
    return MockWS.instances[MockWS.instances.length - 1];
  }
}

describe("connectPemfWebSocket", () => {
  let origWS: unknown;
  beforeEach(() => {
    jest.useFakeTimers();
    MockWS.instances = [];
    origWS = (global as unknown as { WebSocket: unknown }).WebSocket;
    (global as unknown as { WebSocket: unknown }).WebSocket = MockWS;
    serviceConfig.websocketUrl = "ws://test:8000/ws";
    serviceConfig.apiToken = "";
  });
  afterEach(() => {
    jest.clearAllTimers();
    jest.useRealTimers();
    (global as unknown as { WebSocket: unknown }).WebSocket = origWS;
  });

  it("açılışta socket kurar; onopen'da onState(true); token URL'ye eklenir", () => {
    serviceConfig.apiToken = "tok123";
    const onState = jest.fn();
    const disconnect = connectPemfWebSocket(jest.fn(), onState);
    const ws = MockWS.last();
    expect(ws.url).toContain("token=tok123");
    ws.onopen!();
    expect(onState).toHaveBeenCalledWith(true);
    disconnect();
  });

  it("mesajı parse edip onMessage'a verir; 'pong' YUTULUR", () => {
    const onMessage = jest.fn();
    const disconnect = connectPemfWebSocket(onMessage);
    const ws = MockWS.last();
    ws.onopen!();
    ws.onmessage!({ data: JSON.stringify({ type: "sensor_data", coilId: 1 }) });
    expect(onMessage).toHaveBeenCalledWith(expect.objectContaining({ type: "sensor_data", coilId: 1 }));
    ws.onmessage!({ data: JSON.stringify({ type: "pong" }) });
    expect(onMessage).toHaveBeenCalledTimes(1); // pong onMessage'a GİTMEZ
    ws.onmessage!({ data: "not-json{" }); // bozuk → yutulur, patlamaz
    expect(onMessage).toHaveBeenCalledTimes(1);
    disconnect();
  });

  it("heartbeat: 15sn'de ping; 25sn+ mesaj yoksa half-open → socket.close()", () => {
    const disconnect = connectPemfWebSocket(jest.fn());
    const ws = MockWS.last();
    ws.onopen!(); // startHeartbeat (lastMessageTs=now)
    jest.advanceTimersByTime(15000); // 1. tick: stale değil (15<25) → ping
    expect(ws.sent.some((s) => s.includes("ping"))).toBe(true);
    expect(ws.closed).toBe(false);
    jest.advanceTimersByTime(15000); // toplam 30sn, mesaj yok → 2. tick stale → close
    expect(ws.closed).toBe(true);
    disconnect();
  });

  // Yukarıdaki test YALNIZ ws.closed'ı doğruluyordu: PROAKTİF reconnect kaldırılıp yerine sadece
  // socket.close() bırakılsa bile geçerdi. Oysa half-open sokette onclose HİÇ tetiklenmeyebilir →
  // kalıcı SESSİZ kopukluk (UI "CANLI" kalır, veri donuk). Durum bildirimi + yeni soket ŞART.
  it("KRİTİK: half-open tespitinde onState(false) + PROAKTİF yeni soket kurulur", () => {
    const onState = jest.fn();
    const disconnect = connectPemfWebSocket(jest.fn(), onState);
    MockWS.last().onopen!();
    onState.mockClear();

    jest.advanceTimersByTime(30000); // half-open eşiği aşıldı
    expect(onState).toHaveBeenCalledWith(false); // kullanıcıya "çevrimdışı" bildirildi

    // onclose HİÇ tetiklenmese bile backoff sonrası yeni soket açılmalı.
    const before = MockWS.instances.length;
    jest.advanceTimersByTime(1000);
    expect(MockWS.instances.length).toBe(before + 1);
    disconnect();
  });

  // CONNECTING aşamasında zaman aşımı YOKTU: half-open denetimi yalnız soket AÇILDIKTAN SONRA
  // (heartbeat ile) devreye giriyordu. TCP el sıkışması asılırsa ne onopen ne onclose tetiklenir →
  // reconnect zinciri HİÇ başlamaz, uygulama sessizce sonsuza dek "bağlanıyor"da kalırdı.
  it("KRİTİK: soket AÇILMAZSA (CONNECTING asılı) 10sn sonra kapatılıp yeniden denenir", () => {
    const onState = jest.fn();
    const disconnect = connectPemfWebSocket(jest.fn(), onState);
    const ws = MockWS.last();
    ws.readyState = 0;            // CONNECTING — onopen/onclose HİÇ gelmiyor
    onState.mockClear();

    jest.advanceTimersByTime(10_000);
    expect(ws.closed).toBe(true);
    expect(onState).toHaveBeenCalledWith(false);

    jest.advanceTimersByTime(1000); // backoff
    expect(MockWS.instances.length).toBe(2);
    disconnect();
  });

  it("soket zamanında açılırsa kurulum zamanlayıcısı bağlantıyı KAPATMAZ", () => {
    const disconnect = connectPemfWebSocket(jest.fn());
    const ws = MockWS.last();
    ws.readyState = 1;
    ws.onopen!();
    jest.advanceTimersByTime(11_000); // timeout süresi geçti ama soket AÇIK
    expect(ws.closed).toBe(false);
    disconnect();
  });

  // JSON ayrıştırma hatası ile İŞLEYİCİ hatası aynı catch'te yutuluyordu: bir reducer hatası
  // "geçersiz JSON" sayılıp sessizce düşüyor, soket canlı olduğu için UI "CANLI" kalıyordu.
  it("KRİTİK: mesaj işleyicisi hata atarsa bağlantı ÖLMEZ ve hata sessizce yutulmaz", () => {
    const spy = jest.spyOn(console, "error").mockImplementation(() => undefined);
    // İlk çağrıda atar, sonrasında sessizleşir → "tek hata akışı kilitlemez" iddiası test edilir.
    const boom = jest.fn((_m: unknown): void => { throw new Error("reducer patladı"); });
    const disconnect = connectPemfWebSocket(boom);
    const ws = MockWS.last();
    ws.onopen!();

    expect(() => ws.onmessage!({ data: JSON.stringify({ type: "snapshot", data: {} }) } as any)).not.toThrow();
    expect(spy).toHaveBeenCalled();          // iz bırakıldı
    expect(ws.closed).toBe(false);           // soket ayakta

    // Sonraki mesajlar işlenmeye devam eder (tek hata akışı kilitlemez).
    boom.mockImplementationOnce(() => undefined);
    ws.onmessage!({ data: JSON.stringify({ type: "stm_status", data: { stm: "online" } }) } as any);
    expect(boom).toHaveBeenCalledTimes(2);
    spy.mockRestore();
    disconnect();
  });

  it("gerçekten JSON OLMAYAN mesaj sessizce yutulur (captive portal metni) — işleyici çağrılmaz", () => {
    const onMessage = jest.fn();
    const disconnect = connectPemfWebSocket(onMessage);
    MockWS.last().onopen!();
    MockWS.last().onmessage!({ data: "<html>giriş yapın</html>" } as any);
    expect(onMessage).not.toHaveBeenCalled();
    disconnect();
  });

  // Epoch değişiminde eski soketin GEÇ gelen onclose'u, yeni CANLI bağlantıyı "çevrimdışı"
  // işaretliyordu (banner yanıp sönüyor, kullanıcı boşuna yeniden bağlan'a basıyordu).
  it("KRİTİK: disconnect() sonrası gelen onclose onState(false) ÇAĞIRMAZ", () => {
    const onState = jest.fn();
    const disconnect = connectPemfWebSocket(jest.fn(), onState);
    const ws = MockWS.last();
    ws.onopen!();
    disconnect();
    onState.mockClear();
    ws.onclose?.({ code: 1006 }); // soket kapanışı çağrandan SONRA rapor edildi
    expect(onState).not.toHaveBeenCalled();
  });

  it("beklenmedik kapanışta backoff'lu reconnect (yeni socket)", () => {
    const disconnect = connectPemfWebSocket(jest.fn());
    MockWS.last().onopen!();
    MockWS.last().onclose!({ code: 1006 });
    expect(MockWS.instances.length).toBe(1); // hemen değil (backoff)
    jest.advanceTimersByTime(1000); // reconnectDelay=1000
    expect(MockWS.instances.length).toBe(2); // yeni socket kuruldu
    disconnect();
  });

  it("1008 (auth) → onNeedRediscovery + 30sn backoff (hot-loop YOK)", () => {
    const onRediscover = jest.fn();
    const disconnect = connectPemfWebSocket(jest.fn(), undefined, onRediscover);
    MockWS.last().onopen!();
    MockWS.last().onclose!({ code: 1008 });
    expect(onRediscover).toHaveBeenCalled();
    jest.advanceTimersByTime(29000);
    expect(MockWS.instances.length).toBe(1); // 30sn'den önce reconnect YOK
    jest.advanceTimersByTime(2000);
    expect(MockWS.instances.length).toBe(2);
    disconnect();
  });

  it("disconnect(): socket kapatır + reconnect ETMEZ (closedByCaller)", () => {
    const disconnect = connectPemfWebSocket(jest.fn());
    const ws = MockWS.last();
    ws.onopen!();
    disconnect();
    expect(ws.closed).toBe(true);
    ws.onclose!({ code: 1006 }); // scheduleReconnect erken-return etmeli
    jest.advanceTimersByTime(60000);
    expect(MockWS.instances.length).toBe(1); // yeni socket YOK
  });
});
