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
