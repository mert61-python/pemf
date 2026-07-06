/**
 * apiClient kritik davranışları (audit B-3.2): auth header (X-API-Key) gönderimi + hata
 * dayanıklılığı (bağlantı kopması/HTTP hatası BLOKLAMAZ, fallback döner). fetch mock'lanır.
 */
import { apiGet, apiPost, authHeaders } from "@/services/apiClient";
import { serviceConfig } from "@/services/config";

describe("authHeaders", () => {
  afterEach(() => {
    serviceConfig.apiToken = "";
  });

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
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: "online" }),
    });
    global.fetch = fetchMock as unknown as typeof fetch;

    const res = await apiGet("/api/health", { status: "offline" });
    expect(res).toEqual({ status: "online" });
    // İkinci arg headers → X-API-Key taşımalı
    const headers = (fetchMock.mock.calls[0][1] as RequestInit).headers as Record<string, string>;
    expect(headers["X-API-Key"]).toBe("tok");
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
    const fetchMock = jest.fn().mockResolvedValue({ ok: true, json: async () => ({ status: "success" }) });
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
