// Author: mertaygn, cglrgrkn
/**
 * D3.39 (B-6.1) — düz-HTTP kapısı (isCleartextAllowed) canlı veri soketini, AI yüklemelerini / AI Pro kare akışını, kabin kamerasını,
 * rapor indirmeyi ve eşleştirme takasını da kapsar; ACİL DURDUR yolu BİLEREK dışarıda (Y8).
 *
 * ÖLÇÜLEN (HEAD): kapı yalnız apiGet / apiPost / apiDelete'teydi; `updateServiceConfig("http://1.2.3.4:8000")` sonrası
 * `connectPemfWebSocket` `ws://1.2.3.4:8000/ws?token=…` açıyor; AiHub'ın 21 ham `fetch`i (X-API-Key) genel http tabanına gidiyordu.
 * Sahte EN ALT katta: `global.WebSocket` (MockWS) ve `global.fetch`. Yapılandırma GERÇEK (`updateServiceConfig`).
 * Ham ağ çağrısı SAYIMI (TypeScript AST): her dosyanın ham çağrısı gerekçeli izin listesinde; yeni ham çağrı → KIRMIZI.
 */
import * as fs from "fs";
import * as path from "path";
import * as ts from "typescript";

import { connectPemfWebSocket } from "../wsClient";
import { serviceConfig, updateServiceConfig } from "../config";
import { GuvensizBaglantiHatasi, korunanFetch, soketAdresiGuvenliMi } from "../duzHttpKapisi";
import { exchangeCodeForToken } from "../discovery";
import { downloadFileWithAuth } from "../dosyaIndir";
import { performEmergencyStop } from "../emergencyStop";

jest.mock("@/services/deviceRegistry", () => ({ getRemoteUrlForDevice: jest.fn(async () => null) }));
const mockDownloadAsync = jest.fn(async () => ({ uri: "/tmp/r.pdf", status: 200 }));
jest.mock("expo-file-system/legacy", () => ({
  cacheDirectory: "/tmp/",
  downloadAsync: (...a: unknown[]) => mockDownloadAsync(...(a as [])),
  deleteAsync: jest.fn(async () => {}),
}));
jest.mock("expo-sharing", () => ({ isAvailableAsync: jest.fn(async () => false), shareAsync: jest.fn() }));

class MockWS {
  static instances: MockWS[] = [];
  url: string;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: ((e: { code: number }) => void) | null = null;
  readyState = 0;
  constructor(url: string) {
    this.url = url;
    MockWS.instances.push(this);
  }
  send() {}
  close() {}
}

const fetchMock = () => (global as unknown as { fetch: jest.Mock }).fetch;

let origWS: unknown;
beforeEach(() => {
  jest.useFakeTimers();
  MockWS.instances = [];
  origWS = (global as unknown as { WebSocket: unknown }).WebSocket;
  (global as unknown as { WebSocket: unknown }).WebSocket = MockWS;
  (global as { fetch: unknown }).fetch = jest.fn(async () => ({ ok: true, status: 200, json: async () => ({}) }));
  jest.spyOn(console, "error").mockImplementation(() => {});
});
afterEach(() => {
  jest.useRealTimers();
  (global as unknown as { WebSocket: unknown }).WebSocket = origWS;
  jest.restoreAllMocks();
});

describe("canlı veri soketi", () => {
  it("KRİTİK: genel http tabanında ws://…?token= AÇILMAZ, durum kopuk bildirilir", () => {
    expect(updateServiceConfig("http://1.2.3.4:8000")).toBe(true);
    serviceConfig.apiToken = "cihaz-jetonu-testte";
    const durum: boolean[] = [];
    const kapat = connectPemfWebSocket(() => {}, (b) => durum.push(b));
    expect(MockWS.instances.map((w) => w.url)).toEqual([]);
    expect(durum).toContain(false);
    kapat();
  });

  it("KARŞIT: yerel ağ (ws) ve TLS tünel (wss) açılır", () => {
    for (const adres of ["http://192.168.1.5:8000", "https://abc-def.trycloudflare.com"]) {
      MockWS.instances = [];
      updateServiceConfig(adres);
      serviceConfig.apiToken = "";
      const kapat = connectPemfWebSocket(() => {});
      expect(MockWS.instances).toHaveLength(1);
      kapat();
    }
    expect(soketAdresiGuvenliMi("wss://ornek.com/ws")).toBe(true);
    expect(soketAdresiGuvenliMi("ws://ornek.com/ws")).toBe(false);
    expect(soketAdresiGuvenliMi("ws://010.0.0.1/ws")).toBe(false); // sekizlik = 8.0.0.1 (D3.17)
  });
});

describe("korunanFetch", () => {
  it("KRİTİK: genel http adrese istek GİTMEZ (AI yüklemesi / X-API-Key), açık hata fırlatılır", async () => {
    await expect(
      korunanFetch("http://1.2.3.4:8000/api/ai/vision/landmark", { method: "POST", headers: { "X-API-Key": "k" } }),
    ).rejects.toBeInstanceOf(GuvensizBaglantiHatasi);
    expect(fetchMock()).not.toHaveBeenCalled();
  });

  it("KARŞIT: yerel ağ http, https tünel ve yerel URI (blob: / file:) gider", async () => {
    for (const u of [
      "http://192.168.1.5:8000/api/ai/vision/landmark",
      "https://abc-def.trycloudflare.com/api/ai/vision/landmark",
      "blob:http://localhost:8081/1234",
      "file:///data/foto.jpg",
    ]) {
      await korunanFetch(u);
    }
    expect(fetchMock()).toHaveBeenCalledTimes(4);
  });

  it("KRİTİK: eşleştirme takası (kod + dönen jeton) genel http'ye gitmez", async () => {
    await expect(exchangeCodeForToken("http://1.2.3.4:8000", "123456")).resolves.toBe(false);
    expect(fetchMock()).not.toHaveBeenCalled();
  });

  it("KRİTİK: rapor indirme genel http'ye gitmez (X-API-Key + hasta raporu)", async () => {
    const toast = jest.fn();
    mockDownloadAsync.mockClear();
    await downloadFileWithAuth("http://1.2.3.4:8000/api/history/export_pdf?session_ids=1", "r.pdf", toast);
    expect(fetchMock()).not.toHaveBeenCalled();
    expect(mockDownloadAsync).not.toHaveBeenCalled(); // native dal (jest-expo varsayılanı) FileSystem.downloadAsync
    await downloadFileWithAuth("http://192.168.1.5:8000/api/history/export_pdf?session_ids=1", "r.pdf", toast);
    expect(mockDownloadAsync).toHaveBeenCalledTimes(1); // KARŞIT: yerel ağ indirir
  });
});

describe("ACİL DURDUR — Y8 KARŞIT", () => {
  it("genel http tabanında da ACİL DURDUR'un DÖRT isteği GÖNDERİLİR (kapıya bağlanmaz; yedekler azaltılamaz)", async () => {
    updateServiceConfig("http://1.2.3.4:8000");
    fetchMock().mockResolvedValue({ ok: true, status: 200, json: async () => ({ confirmed: true }) });
    const p = performEmergencyStop();
    await jest.runAllTimersAsync();
    await p;
    const urller = fetchMock().mock.calls.map((c) => String(c[0]));
    // ⚠️ D3I-A1.3: eskiden "en az bir E-stop isteği" ölçülüyordu — yedekler (2. E-stop, stop_all_coils, seans durdurma) apiPost'un
    // düz-HTTP kapısında düşerken (4 yerine 1 istek) bu kapı YEŞİLDİ. Artık dördü de sayılır.
    expect(urller.every((u) => u.startsWith("http://1.2.3.4:8000/api/"))).toBe(true);
    expect(urller.map((u) => u.replace("http://1.2.3.4:8000", "")).sort()).toEqual(
      ["/api/hardware/command", "/api/hardware/emergency_stop", "/api/hardware/emergency_stop", "/api/session/stop"],
    );
  });
});

// ── Ham ağ çağrısı sayımı (TypeScript AST) ────────────────────────────────────────────────────────────────────────────────────────
type Sayim = { fetch?: number; ws?: number; fs?: number };
const IZINLI: Record<string, Sayim & { gerekce: string; kapi?: string }> = {
  "services/duzHttpKapisi.ts": { fetch: 1, gerekce: "kapının kendisi (korunanFetch)" },
  "services/apiClient.ts": { fetch: 3, gerekce: "apiGet / apiDelete / apiPost — her biri isCleartextAllowed ile kapılı", kapi: "isCleartextAllowed(serviceConfig.apiBaseUrl)" },
  "services/emergencyStop.ts": { fetch: 1, gerekce: "Y8: ACİL DURDUR BİLEREK kapısız — genel http tabanında da gönderilir" },
  "services/wsClient.ts": { ws: 1, gerekce: "openSocket — soketAdresiGuvenliMi kapısı", kapi: "soketAdresiGuvenliMi(wsBase)" },
  "services/discovery.ts": { fetch: 3, gerekce: "kimliksiz /api/health sondaları (jeton / başlık YOK); jeton ve takas korunanFetch'te" },
  "services/agTanisi.ts": { fetch: 1, gerekce: "kimliksiz /api/health sondası (ağ tanısı)" },
  "screens/SettingsScreen.tsx": { fetch: 2, gerekce: "Test Et / Kaydet öncesi kimliksiz /api/health sondası" },
  "services/updates.ts": { fetch: 1, gerekce: "sabit https manifest (MOBILE_MANIFEST)" },
  "services/mobileUpdate.ts": { fetch: 1, fs: 1, gerekce: "sabit https manifest + kaynakGuvenli pinli APK (D3.19)" },
  "utils/sesYukleme.ts": { fetch: 1, gerekce: "yalnız yerel kayıt URI'si (blob: / file:) — ağ değil" },
  "services/dosyaIndir.ts": { fetch: 2, fs: 1, gerekce: "işlev başında isCleartextAllowed kapısı", kapi: "isCleartextAllowed(url)" },
};

const KOK = path.resolve(__dirname, "../..");
function dosyalar(d: string, acc: string[] = []): string[] {
  for (const ad of fs.readdirSync(d)) {
    const tam = path.join(d, ad);
    if (fs.statSync(tam).isDirectory()) {
      if (ad === "__tests__" || ad === "node_modules") continue;
      dosyalar(tam, acc);
    } else if (/\.(ts|tsx)$/.test(ad) && !/\.(test|spec)\.(ts|tsx)$/.test(ad) && !ad.endsWith(".d.ts")) {
      acc.push(tam);
    }
  }
  return acc;
}

function say(kaynak: string, ad: string): Sayim {
  const sf = ts.createSourceFile(ad, kaynak, ts.ScriptTarget.Latest, true, ad.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  const s: Sayim = {};
  const art = (k: keyof Sayim) => (s[k] = (s[k] || 0) + 1);
  const gez = (n: ts.Node) => {
    if (ts.isIdentifier(n) && n.text === "fetch") {
      const p = n.parent;
      const ozellikAdi = ts.isPropertyAccessExpression(p) && p.name === n;
      const kuresel = ozellikAdi && ts.isIdentifier(p.expression) && ["globalThis", "window", "global", "self"].includes(p.expression.text);
      const tipte = ts.isTypeQueryNode(p);
      const bildirim = (ts.isParameter(p) || ts.isVariableDeclaration(p) || ts.isFunctionDeclaration(p)) && (p as ts.NamedDeclaration).name === n;
      const anahtar = (ts.isPropertyAssignment(p) || ts.isMethodDeclaration(p) || ts.isPropertySignature(p)) && p.name === n;
      const ice = ts.isImportSpecifier(p) || ts.isExportSpecifier(p);
      if (kuresel || (!ozellikAdi && !tipte && !bildirim && !anahtar && !ice)) art("fetch");
    }
    if (ts.isNewExpression(n) && ts.isIdentifier(n.expression) && ["WebSocket", "XMLHttpRequest", "EventSource"].includes(n.expression.text)) art("ws");
    if (
      ts.isPropertyAccessExpression(n) &&
      ts.isIdentifier(n.expression) &&
      n.expression.text === "FileSystem" &&
      ["downloadAsync", "uploadAsync", "createDownloadResumable", "createUploadTask"].includes(n.name.text)
    )
      art("fs");
    ts.forEachChild(n, gez);
  };
  gez(sf);
  return s;
}

describe("ham ağ çağrısı sayımı", () => {
  it("KRİTİK: her ham ağ çağrısı gerekçeli izin listesinde — AiHub / AiPro / kabin kamerası ham fetch KULLANMAZ", () => {
    const bulgu: string[] = [];
    let toplam = 0;
    for (const tam of dosyalar(KOK)) {
      const rel = path.relative(KOK, tam).split(path.sep).join("/");
      const kaynak = fs.readFileSync(tam, "utf8");
      const s = say(kaynak, rel);
      const n = (s.fetch || 0) + (s.ws || 0) + (s.fs || 0);
      toplam += n;
      const izin = IZINLI[rel];
      if (!izin) {
        if (n) bulgu.push(`${rel}: izin listesinde YOK ama ${JSON.stringify(s)}`);
        continue;
      }
      for (const k of ["fetch", "ws", "fs"] as const) {
        if ((s[k] || 0) !== (izin[k] || 0)) bulgu.push(`${rel}: ${k} ${s[k] || 0} ≠ izinli ${izin[k] || 0} (${izin.gerekce})`);
      }
      if (izin.kapi && !kaynak.includes(izin.kapi)) bulgu.push(`${rel}: kapı ifadesi YOK: ${izin.kapi}`);
    }
    expect(bulgu).toEqual([]);
    expect(toplam).toBeGreaterThanOrEqual(15); // vakum kapısı: tarayıcı çağrıları görmeli
  });

  it("KARŞIT: sayıcı ham çağrıyı, takma adı ve küresel erişimi görür; NetInfo.fetch / tip / anahtar adı SAYILMAZ", () => {
    expect(say('const r = await fetch("http://x");', "a.ts")).toEqual({ fetch: 1 });
    expect(say("function f(g: typeof fetch = fetch) { return g; }", "a.ts")).toEqual({ fetch: 1 });
    expect(say('globalThis.fetch("u"); window.fetch("u");', "a.ts")).toEqual({ fetch: 2 });
    expect(say("NetInfo.fetch(); const o = { fetch: 1 }; type T = typeof fetch;", "a.ts")).toEqual({});
    expect(say('new WebSocket("ws://x"); FileSystem.downloadAsync(u, p);', "a.ts")).toEqual({ ws: 1, fs: 1 });
  });
});
