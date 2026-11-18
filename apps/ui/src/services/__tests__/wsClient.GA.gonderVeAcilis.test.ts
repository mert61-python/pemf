// Author: mertaygn, cglrgrkn
/**
 * GA (istem 53) — `WsKontrol.gonder` (açık sokete ileti: alan haritası aboneliği) ve `WsKontrol.acilinca` (her yeniden açılışta
 * aboneliği yenile — sunucudaki abonelik soket başınadır). Kapalı / kurulan / kapatılmış sokete gönderim false; gönderim hatası
 * yutulup false; açılış kancasının hatası bağlantıyı düşürmez.
 */
import { connectPemfWebSocket, type WsKontrol } from "../wsClient";
import { serviceConfig } from "../config";

class MockWS {
  static instances: MockWS[] = [];
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: ((e: { code: number }) => void) | null = null;
  sent: string[] = [];
  readyState = 0;
  patlat = false;
  constructor(public url: string) {
    MockWS.instances.push(this);
  }
  send(d: string) {
    if (this.patlat) throw new Error("kapalı");
    this.sent.push(d);
  }
  close() {}
  static last() {
    return MockWS.instances[MockWS.instances.length - 1];
  }
}

describe("GA wsClient gonder / acilinca", () => {
  let origWS: unknown;
  beforeEach(() => {
    jest.useFakeTimers();
    MockWS.instances = [];
    origWS = (global as unknown as { WebSocket: unknown }).WebSocket;
    (global as unknown as { WebSocket: unknown }).WebSocket = MockWS;
    serviceConfig.websocketUrl = "ws://192.168.1.5:8000/ws";
    serviceConfig.apiToken = "";
  });
  afterEach(() => {
    jest.clearAllTimers();
    jest.useRealTimers();
    (global as unknown as { WebSocket: unknown }).WebSocket = origWS;
  });

  it("gonder: yalnız AÇIK sokete; hata → false; kapatınca false", () => {
    const kontrol: WsKontrol = {};
    const disconnect = connectPemfWebSocket(jest.fn(), jest.fn(), undefined, kontrol);
    const ws = MockWS.last();
    expect(kontrol.gonder!({ type: "alan_abone", acik: true })).toBe(false); // CONNECTING
    expect(ws.sent).toEqual([]);
    ws.readyState = 1;
    ws.onopen!();
    expect(kontrol.gonder!({ type: "alan_abone", acik: true })).toBe(true);
    expect(JSON.parse(ws.sent[ws.sent.length - 1])).toEqual({ type: "alan_abone", acik: true });
    ws.patlat = true;
    expect(kontrol.gonder!({ type: "alan_abone", acik: false })).toBe(false);
    ws.patlat = false;
    disconnect();
    expect(kontrol.gonder!({ type: "alan_abone", acik: true })).toBe(false);
  });

  it("acilinca: her (yeniden) açılışta çağrılır; hatası bağlantıyı düşürmez; kancasız kontrol de çalışır", () => {
    const acilinca = jest.fn();
    const kontrol: WsKontrol = { acilinca };
    const onState = jest.fn();
    const disconnect = connectPemfWebSocket(jest.fn(), onState, undefined, kontrol);
    const ws1 = MockWS.last();
    ws1.readyState = 1;
    ws1.onopen!();
    expect(acilinca).toHaveBeenCalledTimes(1);
    ws1.onclose!({ code: 1006 });
    jest.advanceTimersByTime(1500);
    const ws2 = MockWS.last();
    expect(ws2).not.toBe(ws1);
    acilinca.mockImplementation(() => {
      throw new Error("abone yenilenemedi");
    });
    ws2.readyState = 1;
    ws2.onopen!();
    expect(acilinca).toHaveBeenCalledTimes(2);
    expect(onState).toHaveBeenLastCalledWith(true);
    disconnect();
    const yalin: WsKontrol = {};
    const d2 = connectPemfWebSocket(jest.fn(), jest.fn(), undefined, yalin);
    MockWS.last().onopen!();
    d2();
    connectPemfWebSocket(jest.fn())(); // kontrolsüz bağlantı (eski çağıranlar)
  });
});
