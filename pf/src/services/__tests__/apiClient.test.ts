// Author: mertaygn, cglrgrkn
/**
 * apiClient kritik davranışları (audit B-3.2): auth header (X-API-Key) gönderimi + hata
 * dayanıklılığı (bağlantı kopması/HTTP hatası BLOKLAMAZ, fallback döner). fetch mock'lanır.
 */
// Zaman aşımı bildirimi toastBridge üzerinden gider (showError → emitToast).
jest.mock("@/services/toastBridge", () => ({ emitToast: jest.fn(() => true) }));

import { apiGet, apiPost, apiDelete, authHeaders, isSafeBackendBase, isPrivateHost, setAuthBearer, setEntitlementHeaders, AI_TIMEOUT_MS } from "@/services/apiClient";
import { emitToast } from "@/services/toastBridge";

const mockEmitToast = emitToast as jest.Mock;
import { serviceConfig } from "@/services/config";

// Modül-DÜZEYİ durum (_authBearer / _entitlementHeaders) testler arası sızıyordu: authHeaders'ın
// `toEqual` iddiaları yalnız bu değişkenler tesadüfen boş olduğu için geçiyordu.
beforeEach(() => { mockEmitToast.mockClear(); });
afterEach(() => {
  serviceConfig.apiToken = "";
  setAuthBearer(null);
  setEntitlementHeaders(null);
});

// ── Bearer güvenlik geçidi (hiç test edilmiyordu) ────────────────────────────
describe("isPrivateHost / isSafeBackendBase", () => {
  it("RFC1918 IP + localhost özel sayılır", () => {
    for (const h of ["127.0.0.1", "10.0.0.5", "192.168.1.147", "172.16.0.1", "172.31.255.254", "localhost"]) {
      expect(isPrivateHost(h)).toBe(true);
    }
  });

  it("KRİTİK: '10.' ile BAŞLAYAN hostname özel ağ SAYILMAZ (ön-ek testi ankor hatası)", () => {
    expect(isPrivateHost("10.evil.com")).toBe(false);
    expect(isPrivateHost("192.168.attacker.net")).toBe(false);
    expect(isPrivateHost("172.20.example.org")).toBe(false);
  });

  it("172.32 / 172.15 özel aralık DIŞINDA", () => {
    expect(isPrivateHost("172.32.0.1")).toBe(false);
    expect(isPrivateHost("172.15.0.1")).toBe(false);
  });

  it("KRİTİK: rastgele https host'a Supabase JWT GÖNDERİLMEZ", () => {
    expect(isSafeBackendBase("https://evil.example.com")).toBe(false);
    expect(isSafeBackendBase("https://pemf-vet.attacker.io")).toBe(false);
  });

  it("tanınan Cloudflare tüneli ve LAN güvenli sayılır", () => {
    expect(isSafeBackendBase("https://abcd-xyz.trycloudflare.com")).toBe(true);
    expect(isSafeBackendBase("http://192.168.1.147:8000/api")).toBe(true);
  });

  it("Bearer YALNIZ güvenli tabana eklenir; X-API-Key her yere gider", () => {
    serviceConfig.apiToken = "device-token";
    setAuthBearer("supabase-jwt");

    serviceConfig.apiBaseUrl = "https://evil.example.com/api";
    expect(authHeaders().Authorization).toBeUndefined();
    expect(authHeaders()["X-API-Key"]).toBe("device-token");

    serviceConfig.apiBaseUrl = "http://192.168.1.147:8000/api";
    expect(authHeaders().Authorization).toBe("Bearer supabase-jwt");
  });
});

// ── Cleartext kapısı ─────────────────────────────────────────────────────────
// Android manifest'inde uygulama GENELİNDE `usesCleartextTraffic=true` ve bunu manifest'ten
// daraltmak MÜMKÜN DEĞİL (networkSecurityConfig DNS adıyla çalışır, DHCP ile değişen LAN IP'sini
// ifade edemez). Kısıt bu yüzden uygulama katmanında: düz HTTP yalnız ÖZEL AĞA izinli.
describe("isCleartextAllowed — düz HTTP yalnız yerel ağa", () => {
  // `serviceConfig` MODÜL-DÜZEYİ paylaşımlı durumdur: burada değiştirip geri koymazsak sonraki
  // describe'lar public-http tabanıyla çalışır ve cleartext kapısına takılır (denetimdeki #55
  // "test durumu sızıyor" bulgusunun aynısı — bu kez kendi testimizde yakalandı).
  const original = serviceConfig.apiBaseUrl;
  afterAll(() => { serviceConfig.apiBaseUrl = original; });

  const call = async (base: string) => {
    serviceConfig.apiBaseUrl = base;
    global.fetch = jest.fn().mockResolvedValue({ ok: true, text: async () => '{"ok":1}' }) as unknown as typeof fetch;
    const res = await apiGet<{ ok?: number } | null>("/health", null, { silent: true });
    return { res, fetched: (global.fetch as jest.Mock).mock.calls.length };
  };

  it("LAN üzerinden düz HTTP'ye İZİN VERİR (klinik cihazı, TLS'siz güven sınırı)", async () => {
    const { res, fetched } = await call("http://192.168.1.147:8000/api");
    expect(fetched).toBe(1);
    expect(res).toEqual({ ok: 1 });
  });

  it("KRİTİK: PUBLIC host'a düz HTTP isteği HİÇ GÖNDERİLMEZ (token + hasta verisi şifresiz gitmesin)", async () => {
    const { res, fetched } = await call("http://pemf.example.com/api");
    expect(fetched).toBe(0);      // ağa hiç çıkılmadı
    expect(res).toBeNull();       // çağıranın fallback'i
  });

  it("public host'a HTTPS ile izin verir (tünel)", async () => {
    const { fetched } = await call("https://abcd.trycloudflare.com/api");
    expect(fetched).toBe(1);
  });

  it("apiPost da aynı kapıya tabi (mutasyon isteği şifresiz sızmasın)", async () => {
    serviceConfig.apiBaseUrl = "http://pemf.example.com/api";
    global.fetch = jest.fn() as unknown as typeof fetch;
    const res = await apiPost<null>("/coil/1/control", { start: true }, null, { silent: true });
    expect(global.fetch).not.toHaveBeenCalled();
    expect(res).toBeNull();
  });

  it("apiDelete da aynı kapıya tabi (oturum silme isteği şifresiz sızmasın)", async () => {
    serviceConfig.apiBaseUrl = "http://pemf.example.com/api";
    global.fetch = jest.fn() as unknown as typeof fetch;
    const res = await apiDelete<null>("/auth/desktop-session", null, { silent: true });
    expect(global.fetch).not.toHaveBeenCalled();
    expect(res).toBeNull();
  });
});

// ── apiDelete (masaüstü oturum-devri sözleşmesi DELETE dayatıyor) ─────────────
describe("apiDelete", () => {
  const original = serviceConfig.apiBaseUrl;
  const realFetch = global.fetch;
  beforeEach(() => { serviceConfig.apiBaseUrl = "http://127.0.0.1:8000/api"; });
  afterEach(() => { global.fetch = realFetch; jest.restoreAllMocks(); });
  afterAll(() => { serviceConfig.apiBaseUrl = original; });

  it("DELETE metodu + auth başlığı gönderir, gövde YOLLAMAZ", async () => {
    serviceConfig.apiToken = "tok";
    const fetchMock = jest.fn().mockResolvedValue({ ok: true, text: async () => "" });
    global.fetch = fetchMock as unknown as typeof fetch;

    await apiDelete<null>("/auth/desktop-session", null, { silent: true });
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.method).toBe("DELETE");
    expect(init.body).toBeUndefined();
    expect((init.headers as Record<string, string>)["X-API-Key"]).toBe("tok");
  });

  it("HTTP hatası ve bağlantı kopması fallback döner (çıkış akışı BLOKLANMAZ)", async () => {
    jest.spyOn(console, "error").mockImplementation(() => {});
    global.fetch = jest.fn().mockResolvedValue({ ok: false, status: 403 }) as unknown as typeof fetch;
    await expect(apiDelete<null>("/auth/desktop-session", null, { silent: true })).resolves.toBeNull();

    global.fetch = jest.fn().mockRejectedValue(new Error("kapalı")) as unknown as typeof fetch;
    await expect(apiDelete<null>("/auth/desktop-session", null, { silent: true })).resolves.toBeNull();
  });

  it("zaman aşımı UYGULANIR (asılı bağlantı çıkışı dondurmasın) ve TEKRAR DENENMEZ", async () => {
    jest.spyOn(console, "error").mockImplementation(() => {});
    jest.useFakeTimers();
    let aborted = false;
    const fetchMock = jest.fn((_u: unknown, init: RequestInit) =>
      new Promise((_res, rej) => {
        (init.signal as AbortSignal).addEventListener("abort", () => {
          aborted = true;
          rej(Object.assign(new Error("aborted"), { name: "AbortError" }));
        });
      }));
    global.fetch = fetchMock as unknown as typeof fetch;

    const p = apiDelete<null>("/auth/desktop-session", null, { timeoutMs: 3000, silent: true });
    jest.advanceTimersByTime(3001);
    expect(aborted).toBe(true);
    jest.useRealTimers();
    await expect(p).resolves.toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(1); // GET'teki gibi 2. deneme YOK
  });
});

// ── AI çıkarımı için uzun zaman aşımı ────────────────────────────────────────
// GERÇEK VAKA (2026-08-06): İlk kullanımda "hastalık" ve "ses" analizleri AYNI ANDA başlatıldı,
// İKİSİ DE BOŞ döndü; tekrar denenince anında çalıştı. Ölçüm (soğuk backend, bu makine):
//   /ai/disease    ilk 3.2 sn  → sonraki 0.01 sn
//   /ai/sound/cat  ilk 28.0 sn → sonraki 0.06 sn   (numba/librosa JIT)
// Modeller GECİKMELİ yüklenir; apiPost'un sabit 8sn'si ilk çağrıyı iptal ediyor, üstelik
// AbortError yolunda HİÇBİR bildirim göstermediği için sonuç sessizce boş kalıyordu.
describe("AI zaman aşımı ve sessiz iptal", () => {
  const original = serviceConfig.apiBaseUrl;
  beforeEach(() => { serviceConfig.apiBaseUrl = "http://192.168.1.147:8000/api"; });
  afterAll(() => { serviceConfig.apiBaseUrl = original; });

  it("varsayılan zaman aşımı 8sn'de İPTAL EDER (kontrol/telemetri uçları için doğru davranış)", async () => {
    jest.useFakeTimers();
    let aborted = false;
    // Gerçek fetch gibi: abort sinyalinde REDDET (yalnız bayrak set etmek yetmez — istek asla
    // çözülmezse `await` sonsuza dek asılır ve test zaman aşımına düşer).
    global.fetch = jest.fn((_u: unknown, init: RequestInit) =>
      new Promise((_res, rej) => {
        (init.signal as AbortSignal).addEventListener("abort", () => {
          aborted = true;
          rej(Object.assign(new Error("aborted"), { name: "AbortError" }));
        });
      })) as unknown as typeof fetch;

    const p = apiPost("/coil/1/control", {}, null, { silent: true });
    jest.advanceTimersByTime(7999);
    expect(aborted).toBe(false);   // 8sn dolmadan iptal YOK
    jest.advanceTimersByTime(2);
    expect(aborted).toBe(true);    // 8sn'de iptal VAR (AI dışı uçlar hızlı başarısız olmalı)
    jest.useRealTimers();
    await p;
  });

  it("KRİTİK: timeoutMs verilince istek 8sn'de İPTAL EDİLMEZ", async () => {
    jest.useFakeTimers();
    let aborted = false;
    global.fetch = jest.fn((_u: unknown, init: RequestInit) =>
      new Promise((resolve) => {
        (init.signal as AbortSignal).addEventListener("abort", () => { aborted = true; });
        setTimeout(() => resolve({ ok: true, text: async () => '{"status":"success"}' } as never), 30000);
      })) as unknown as typeof fetch;

    const p = apiPost<{ status?: string } | null>("/ai/disease", {}, null, { timeoutMs: AI_TIMEOUT_MS, silent: true });
    jest.advanceTimersByTime(9000);          // eski sabit sınırın ötesi
    expect(aborted).toBe(false);             // <-- iptal EDİLMEDİ
    jest.advanceTimersByTime(21000);         // yanıt 30. sn'de geliyor
    jest.useRealTimers();
    await expect(p).resolves.toEqual({ status: "success" });
  });

  it("KRİTİK: zaman aşımında SESSİZ kalmaz — kullanıcıya bildirilir", async () => {
    jest.useFakeTimers();
    global.fetch = jest.fn((_u: unknown, init: RequestInit) =>
      new Promise((_res, rej) => {
        (init.signal as AbortSignal).addEventListener("abort", () =>
          rej(Object.assign(new Error("aborted"), { name: "AbortError" })));
      })) as unknown as typeof fetch;

    const p = apiPost("/ai/disease", {}, null, { timeoutMs: 5000 });
    jest.advanceTimersByTime(5001);
    jest.useRealTimers();
    await p;
    expect(mockEmitToast).toHaveBeenCalled();
    expect(String(mockEmitToast.mock.calls[0][0])).toMatch(/zaman aşımı/i);
  });

  it("silent:true iken zaman aşımı bildirimi BASTIRILIR (arka plan poll'leri)", async () => {
    jest.useFakeTimers();
    global.fetch = jest.fn((_u: unknown, init: RequestInit) =>
      new Promise((_res, rej) => {
        (init.signal as AbortSignal).addEventListener("abort", () =>
          rej(Object.assign(new Error("aborted"), { name: "AbortError" })));
      })) as unknown as typeof fetch;

    const p = apiPost("/x", {}, null, { timeoutMs: 5000, silent: true });
    jest.advanceTimersByTime(5001);
    jest.useRealTimers();
    await p;
    expect(mockEmitToast).not.toHaveBeenCalled();
  });
});

describe("authHeaders", () => {

  it("token varsa X-API-Key gönderir", () => {
    serviceConfig.apiToken = "secret-token-123";
    expect(authHeaders()).toEqual({ "X-API-Key": "secret-token-123" });
  });

  it("token yoksa boş header (geriye uyumlu)", () => {
    serviceConfig.apiToken = "";
    expect(authHeaders()).toEqual({});
  });
});

describe("apiGet", () => {
  const realFetch = global.fetch;
  afterEach(() => {
    global.fetch = realFetch;
    serviceConfig.apiToken = "";
    jest.restoreAllMocks();
  });

  it("200'de JSON döner + X-API-Key başlığını iletir", async () => {
    serviceConfig.apiToken = "tok";
    // parseJsonSafe gövdeyi response.text() ile okur (boş/JSON-olmayan gövdeyi
    // "Unexpected end of JSON input" fırlatmadan karşılamak için) → mock text() vermeli.
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      text: async () => JSON.stringify({ status: "online" }),
    });
    global.fetch = fetchMock as unknown as typeof fetch;

    const res = await apiGet("/api/health", { status: "offline" });
    expect(res).toEqual({ status: "online" });
    // İkinci arg headers → X-API-Key taşımalı
    const headers = (fetchMock.mock.calls[0][1] as RequestInit).headers as Record<string, string>;
    expect(headers["X-API-Key"]).toBe("tok");
  });

  // parseJsonSafe'in var oluş sebebi (ORTA fix): 2xx gövde BOŞ ya da JSON-OLMAYAN olabilir.
  // DÜZELTİLDİ: boş gövde artık ÇAĞIRANIN fallback'ini döner, sabit `{}` DEĞİL. Eski davranış
  // çağrı sözleşmesini sessizce bozuyordu — `apiGet<T[]|null>(..., null)` boş 200'de `null` yerine
  // `{}` alıyor, `data !== null` kapısını geçiyor ve `.filter`/`.map` TypeError atıyordu
  // (Tedavi Geçmişi beyaz ekran, Ana Ekran'da ACİL DURDUR'un kaybolması).
  it("2xx + BOŞ gövde → ÇAĞIRANIN fallback'i döner (sabit {} DEĞİL), hata sayılmaz", async () => {
    global.fetch = jest.fn().mockResolvedValue({ ok: true, text: async () => "" }) as unknown as typeof fetch;
    const fallback = { status: "error" };
    const res = await apiGet("/api/session/stop", fallback);
    expect(res).toBe(fallback);
  });

  it("REGRESYON: boş gövdede null-fallback'li çağrı `{}` DEĞİL null almalı", async () => {
    global.fetch = jest.fn().mockResolvedValue({ ok: true, text: async () => "" }) as unknown as typeof fetch;
    const res = await apiGet<unknown[] | null>("/api/history/", null);
    expect(res).toBeNull();
  });

  it("2xx + JSON-OLMAYAN gövde (captive-portal HTML) → fallback", async () => {
    const fallback = { status: "offline" };
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      text: async () => "<html>Oturum açmanız gerekiyor</html>",
    }) as unknown as typeof fetch;
    const res = await apiGet("/api/health", fallback);
    expect(res).toBe(fallback);
  });

  it("HTTP hatası (500) → fallback döner, throw ETMEZ", async () => {
    jest.spyOn(console, "error").mockImplementation(() => {});
    global.fetch = jest.fn().mockResolvedValue({ ok: false, status: 500 }) as unknown as typeof fetch;
    const fallback = { data: [] };
    const res = await apiGet("/api/patients", fallback, { silent: true });
    expect(res).toBe(fallback); // aynı fallback referansı
  });

  it("bağlantı kopması (fetch throw) → fallback döner, UI bloklanmaz", async () => {
    jest.spyOn(console, "error").mockImplementation(() => {});
    global.fetch = jest.fn().mockRejectedValue(new Error("Network down")) as unknown as typeof fetch;
    const fallback = { ok: false };
    const res = await apiGet("/api/gateway/status", fallback, { silent: true });
    expect(res).toBe(fallback);
  });
});

describe("apiPost", () => {
  const realFetch = global.fetch;
  afterEach(() => {
    global.fetch = realFetch;
    jest.restoreAllMocks();
  });

  it("POST gövdeyi JSON serialize eder + JSON Content-Type gönderir", async () => {
    const fetchMock = jest.fn().mockResolvedValue({ ok: true, text: async () => JSON.stringify({ status: "success" }) });
    global.fetch = fetchMock as unknown as typeof fetch;

    const res = await apiPost("/api/session/start", { mode: "Manuel", duration_minutes: 20 }, { status: "error" });
    expect(res).toEqual({ status: "success" });
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ mode: "Manuel", duration_minutes: 20 });
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
  });

  it("hata → fallback (throw ETMEZ)", async () => {
    jest.spyOn(console, "error").mockImplementation(() => {});
    global.fetch = jest.fn().mockRejectedValue(new Error("boom")) as unknown as typeof fetch;
    const fallback = { status: "error" };
    const res = await apiPost("/api/session/stop", {}, fallback, { silent: true });
    expect(res).toBe(fallback);
  });
});

/**
 * SUNUCUNUN REDDETME GEREKÇESİ (2026-08-09 denetimi).
 * `apiPost` hata gövdesini okumadan atıyordu → çağıran yalnız durum kodunu görüyor, kullanıcıya
 * genel "Sunucuya veri gönderilirken bir hata oluştu" gösteriliyordu. Somut zarar: tıbbi kayıt
 * DB'si açılamadığında `/api/session/start` 503 + açıklayıcı `detail` döner, ama veteriner hasta
 * masadayken sebebi ANLAYAMIYORDU.
 */
describe("HTTP hata gerekçesi (FastAPI detail)", () => {
  const hataYaniti = (status: number, govde: unknown) => {
    (global as unknown as { fetch: jest.Mock }).fetch = jest.fn().mockResolvedValue({
      ok: false, status, json: async () => govde,
    });
  };

  it("detail onHttpError'a İKİNCİ argüman olarak geçer", async () => {
    hataYaniti(503, { detail: "Tıbbi kayıt veritabanı açılamadı; seans başlatılamaz." });
    const gorulen: [number, string | undefined][] = [];
    await apiPost("/session/start", {}, null,
      { silent: true, onHttpError: (s, d) => { gorulen.push([s, d]); } });
    expect(gorulen).toEqual([[503, "Tıbbi kayıt veritabanı açılamadı; seans başlatılamaz."]]);
  });

  it("detail varsa KULLANICIYA o gösterilir (genel mesaj değil)", async () => {
    hataYaniti(503, { detail: "Tıbbi kayıt veritabanı açılamadı." });
    await apiPost("/session/start", {}, null);
    const [metin] = mockEmitToast.mock.calls[mockEmitToast.mock.calls.length - 1];
    expect(String(metin)).toContain("veritabanı açılamadı");
  });

  it("detail yoksa genel mesaja düşer (davranış korunur)", async () => {
    hataYaniti(500, {});
    await apiPost("/x", {}, null);
    const [metin] = mockEmitToast.mock.calls[mockEmitToast.mock.calls.length - 1];
    expect(String(metin)).toContain("bir hata oluştu");
  });

  it("KRİTİK: gövde JSON DEĞİLSE akış bozulmaz (hata yolunda ikinci hata üretme)", async () => {
    (global as unknown as { fetch: jest.Mock }).fetch = jest.fn().mockResolvedValue({
      ok: false, status: 502, json: async () => { throw new Error("html geldi"); },
    });
    let kod = 0;
    await expect(
      apiPost("/x", {}, "yedek", { silent: true, onHttpError: (s) => { kod = s; } }),
    ).resolves.toBe("yedek");
    expect(kod).toBe(502);
  });

  it("silent:true iken gerekçe TOAST ETMEZ (çağıran kendi gösterir)", async () => {
    hataYaniti(401, { detail: "PIN hatalı." });
    mockEmitToast.mockClear();
    await apiPost("/operators/verify", {}, null, { silent: true });
    expect(mockEmitToast).not.toHaveBeenCalled();
  });
});
