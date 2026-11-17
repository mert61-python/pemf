/**
 * KP-3 C · WebSocket istemcisi (services/wsClient) + yazı tipi enjeksiyonu (theme/fonts) kapsanmayan kolları — her test bir DAVRANIŞ iddiası:
 *  - WebSocket hiç yoksa (eski WebView / test ortamı) bağlantı "yok" bildirilir, kapatıcı zararsızdır.
 *  - Soket kurulumu (yapıcı) patlarsa "yok" + yeniden deneme; soket hatası (onerror) "yok" bildirir.
 *  - Arka plandan dönüş doğrulaması (dogrula): AÇIK sokete ping; süre içinde yanıt yoksa soket half-open sayılır — işleyiciler sökülür,
 *    kapatılır, yeniden kurulur. Art arda iki doğrulama TEK zamanlayıcı bırakır. Kapatıldıktan sonra doğrulama hiçbir şey bildirmez.
 *  - Kuruluyorken kapatılan soket sonra açılırsa kapatılır, "bağlı" BİLDİRİLMEZ.
 *  - injectFont: props yoksa aynen; italik stil SÖKÜLÜR (Inter'in italik kesimi yüklü değil); ağırlık → kesim adı.
 *  - applyGlobalInter: JSX çalışma zamanı BİR KEZ sarılır (Text'e Inter kesimi enjekte edilir), ikinci çağrı yeniden sarmaz; forwardRef
 *    `render`i olan bileşen de yamalanır, çizim hatası olmayan öğe korunur.
 * SAHTE (en alt kat): global WebSocket (MockWS), sahte zamanlayıcı; JSX çalışma zamanı modülü (jest.isolateModules — sızıntı yok).
 */
import { connectPemfWebSocket } from "../wsClient";
import { serviceConfig } from "../config";

class MockWS {
  static instances: MockWS[] = [];
  static patla = false;
  url: string;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: ((e: { code: number }) => void) | null = null;
  sent: string[] = [];
  closed = false;
  readyState = 0;
  constructor(url: string) {
    if (MockWS.patla) throw new Error("SecurityError: ws engellendi");
    this.url = url;
    MockWS.instances.push(this);
  }
  send(d: string) {
    this.sent.push(d);
  }
  close() {
    this.closed = true;
  }
  static last() {
    return MockWS.instances[MockWS.instances.length - 1];
  }
}

describe("wsClient", () => {
  let origWS: unknown;
  beforeEach(() => {
    jest.useFakeTimers();
    MockWS.instances = [];
    MockWS.patla = false;
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

  it("WebSocket yoksa 'yok' bildirilir, kapatıcı zararsız", () => {
    (global as unknown as { WebSocket: unknown }).WebSocket = undefined;
    const onState = jest.fn();
    const kapat = connectPemfWebSocket(jest.fn(), onState);
    expect(onState).toHaveBeenCalledWith(false);
    expect(() => kapat()).not.toThrow();
  });

  it("yapıcı patlarsa 'yok' + yeniden deneme; onerror 'yok' bildirir", () => {
    MockWS.patla = true;
    const onState = jest.fn();
    const kapat = connectPemfWebSocket(jest.fn(), onState);
    expect(onState).toHaveBeenLastCalledWith(false);
    expect(MockWS.instances).toHaveLength(0);
    MockWS.patla = false;
    jest.advanceTimersByTime(1500);
    expect(MockWS.instances).toHaveLength(1);
    onState.mockClear();
    MockWS.last().onerror!();
    expect(onState).toHaveBeenCalledWith(false);
    kapat();
  });

  it("dogrula: yanıtsız AÇIK soket half-open sayılır — işleyiciler sökülür, kapatılır, yeniden kurulur; tek zamanlayıcı", () => {
    const onState = jest.fn();
    const kontrol: { dogrula?: () => void } = {};
    const kapat = connectPemfWebSocket(jest.fn(), onState, undefined, kontrol);
    const ws = MockWS.last();
    ws.readyState = 1;
    ws.onopen!();
    onState.mockClear();
    kontrol.dogrula!();
    jest.advanceTimersByTime(3000);
    kontrol.dogrula!(); // ikinci doğrulama ilk zamanlayıcıyı söker
    expect(onState).toHaveBeenCalledWith(false);
    expect(ws.sent.filter((s) => JSON.parse(s).type === "ping")).toHaveLength(2);
    jest.advanceTimersByTime(3000);
    expect(ws.closed).toBe(false); // ilk zamanlayıcı sökülmüştü — 4 sn henüz dolmadı
    jest.advanceTimersByTime(1000);
    expect(ws.closed).toBe(true);
    expect(ws.onclose).toBeNull();
    expect(ws.onmessage).toBeNull();
    expect(ws.onerror).toBeNull();
    jest.advanceTimersByTime(2000);
    expect(MockWS.instances).toHaveLength(2);
    kapat();
    onState.mockClear();
    kontrol.dogrula!();
    expect(onState).not.toHaveBeenCalled();
  });

  it("kuruluyorken kapatılan soket sonra açılsa da 'bağlı' bildirilmez, kalp atışı başlamaz", () => {
    const onState = jest.fn();
    const kapat = connectPemfWebSocket(jest.fn(), onState);
    const ws = MockWS.last();
    const onopen = ws.onopen!;
    kapat();
    expect(ws.closed).toBe(true); // kapatıcı kuruluyor soketi kapatır
    ws.readyState = 1;
    onopen(); // geç gelen açılış olayı
    expect(onState).not.toHaveBeenCalledWith(true);
    jest.advanceTimersByTime(60000);
    expect(ws.sent).toEqual([]); // kalp atışı (ping) başlamadı
    expect(MockWS.instances).toHaveLength(1); // yeniden bağlanma da yok
  });
});

describe("theme/fonts", () => {
  it("injectFont: props yok → aynen; italik sökülür; ağırlık kesime çevrilir", () => {
    const { Text } = require("react-native");
    const { injectFont } = require("@/theme/fonts");
    expect(injectFont(Text, null)).toBeNull();
    const out = injectFont(Text, { style: { fontWeight: "700", fontStyle: "italic", color: "red" } });
    expect(out.style).toEqual({ fontFamily: "Inter_700Bold", color: "red" });
  });

  it("applyGlobalInter: JSX çalışma zamanı BİR KEZ sarılır; forwardRef render yaması öğeyi korur", () => {
    jest.isolateModules(() => {
      const cagri: unknown[] = [];
      const jsxMod = { jsx: (t: unknown, p: unknown) => (cagri.push(p), "el"), jsxs: (t: unknown, p: unknown) => (cagri.push(p), "els") };
      jest.doMock("react/jsx-runtime", () => jsxMod);
      jest.doMock("react/jsx-dev-runtime", () => {
        throw new Error("dev runtime yok");
      });
      const RN = require("react-native");
      const ilkRender = { render: () => ({ type: RN.Text, props: { style: { fontWeight: "600" } } }) };
      const yanlis = { render: () => null };
      const fonts = require("@/theme/fonts");
      RN.Text.render = ilkRender.render;
      RN.TextInput.render = yanlis.render;
      fonts.applyGlobalInter();
      const sarilmis = jsxMod.jsx;
      fonts.applyGlobalInter();
      expect(jsxMod.jsx).toBe(sarilmis);
      expect((jsxMod as { __interPatched?: boolean }).__interPatched).toBe(true);
      jsxMod.jsx(RN.Text, { style: { fontWeight: "800" } });
      expect((cagri[0] as { style: { fontFamily: string } }).style.fontFamily).toBe("Inter_800ExtraBold");
      // KP-7 B (işlev ölçüsü): çok çocuklu JSX (`jsxs`) de sarılır — birden çok çocuklu Text de Inter kesimini alır.
      jsxMod.jsxs(RN.Text, { style: { fontWeight: "700" }, children: ["a", "b"] });
      expect((cagri[1] as { style: { fontFamily: string } }).style.fontFamily).toBe("Inter_700Bold");
      const el = RN.Text.render();
      expect(el.props.style.fontFamily).toBe("Inter_600SemiBold");
      expect(RN.TextInput.render()).toBeNull();
    });
  });
});
