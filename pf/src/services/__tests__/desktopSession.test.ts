// Author: mertaygn, cglrgrkn
/**
 * desktopSession — masaüstü client'tan devredilen oturum (E-özelliği sözleşmesi, 2026-08-06).
 *
 * Kilitlenen sözleşme:
 *   1. MOBİLDE hiç istek yok (client yok) — APK'da her açılışta boşa giden çağrı olmaz
 *   2. Loopback DIŞI web host'ta da istek yok (LAN tarayıcısı; backend zaten 403 döner)
 *   3. Oturum yoksa backend `{}` döner — `{}` truthy'dir, TOKEN kontrolü şart → hydrate=false
 *   4. Geçerli devirde setSession TAM OLARAK iki token ile çağrılır
 *   5. setSession hata verirse sessizce false (kullanıcı normal login görür, hata GÖRMEZ)
 *   6. TOKEN HİÇBİR LOG SEVİYESİNDE yazılmaz
 */
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async () => null),
  apiDelete: jest.fn(async () => null),
}));
jest.mock("@/services/supabaseAuth", () => ({
  supabaseAuth: { auth: { setSession: jest.fn(async () => ({ error: null })) } },
}));

import { Platform } from "react-native";
import { apiGet, apiDelete } from "@/services/apiClient";
import { supabaseAuth } from "@/services/supabaseAuth";
import {
  isDesktopHost,
  fetchDesktopSession,
  hydrateFromDesktopSession,
  clearDesktopSession,
} from "@/services/desktopSession";

const mockGet = apiGet as jest.Mock;
const mockDelete = apiDelete as jest.Mock;
const mockSetSession = (supabaseAuth as unknown as { auth: { setSession: jest.Mock } }).auth.setSession;

// Platform.OS düz bir özelliktir (yazılabilir); window jest ortamında global nesnedir ama
// `location` tanımsızdır → varsayılan olarak masaüstü DEĞİL sayılırız (doğru varsayılan).
const setEnv = (os: string, hostname?: string) => {
  (Platform as unknown as { OS: string }).OS = os;
  (global as unknown as { window: { location?: { hostname: string } } }).window =
    hostname === undefined ? {} : { location: { hostname } };
};

const VALID = { access_token: "AT-gizli", refresh_token: "RT-gizli", email: "op@klinik.com", expires_at: 1234 };

beforeEach(() => {
  jest.clearAllMocks();
  mockGet.mockResolvedValue(null);
  mockDelete.mockResolvedValue(null);
  mockSetSession.mockResolvedValue({ error: null });
  setEnv("web", "127.0.0.1");
});

afterAll(() => {
  setEnv("ios");
});

describe("isDesktopHost — platform/host ayrımı", () => {
  it("KRİTİK: MOBİLDE (native) asla masaüstü sayılmaz → hiç istek atılmaz", async () => {
    for (const os of ["ios", "android"]) {
      setEnv(os, "127.0.0.1"); // hostname olsa BİLE native → false
      expect(isDesktopHost()).toBe(false);
    }
    setEnv("android", "127.0.0.1");
    await expect(hydrateFromDesktopSession()).resolves.toBe(false);
    await clearDesktopSession();
    expect(mockGet).not.toHaveBeenCalled();
    expect(mockDelete).not.toHaveBeenCalled();
  });

  it("loopback host'lar masaüstü sayılır (client 127.0.0.1:8000'i açar)", () => {
    for (const h of ["127.0.0.1", "localhost", "LOCALHOST", "::1", "[::1]"]) {
      setEnv("web", h);
      expect(isDesktopHost()).toBe(true);
    }
  });

  it("KRİTİK: LAN/uzak tarayıcıda devir DENENMEZ (yalnız loopback)", async () => {
    setEnv("web", "192.168.1.147");
    expect(isDesktopHost()).toBe(false);
    await expect(hydrateFromDesktopSession()).resolves.toBe(false);
    expect(mockGet).not.toHaveBeenCalled();
  });

  it("window/location yoksa (SSR/native-web karışımı) çökmez", () => {
    setEnv("web", undefined);
    expect(isDesktopHost()).toBe(false);
  });
});

describe("fetchDesktopSession — yanıt doğrulama", () => {
  it("uç doğru yol + sessiz + SERT zaman aşımı ile çağrılır (splash'te asılı kalma)", async () => {
    mockGet.mockResolvedValue(VALID);
    await fetchDesktopSession();
    expect(mockGet).toHaveBeenCalledTimes(1);
    expect(mockGet.mock.calls[0][0]).toBe("/auth/desktop-session");
    const opts = mockGet.mock.calls[0][2];
    expect(opts.silent).toBe(true);
    expect(opts.timeoutMs).toBeLessThanOrEqual(3000);
  });

  it("KRİTİK: oturum yokken backend `{}` döner — truthy TUZAĞI, null sayılmalı", async () => {
    mockGet.mockResolvedValue({});
    await expect(fetchDesktopSession()).resolves.toBeNull();
  });

  it("token'lardan biri eksik/boş/yanlış tipse REDDEDİLİR", async () => {
    for (const bad of [
      { access_token: "AT" },
      { refresh_token: "RT" },
      { access_token: "", refresh_token: "RT" },
      { access_token: "AT", refresh_token: 42 },
      null,
    ]) {
      mockGet.mockResolvedValue(bad);
      await expect(fetchDesktopSession()).resolves.toBeNull();
    }
  });

  it("geçerli yanıtta alanlar taşınır", async () => {
    mockGet.mockResolvedValue(VALID);
    await expect(fetchDesktopSession()).resolves.toEqual({
      access_token: "AT-gizli", refresh_token: "RT-gizli", email: "op@klinik.com", expires_at: 1234,
    });
  });
});

describe("hydrateFromDesktopSession", () => {
  it("KRİTİK: geçerli devirde setSession TAM OLARAK iki token ile çağrılır", async () => {
    mockGet.mockResolvedValue(VALID);
    await expect(hydrateFromDesktopSession()).resolves.toBe(true);
    expect(mockSetSession).toHaveBeenCalledWith({ access_token: "AT-gizli", refresh_token: "RT-gizli" });
  });

  it("boş oturumda setSession HİÇ çağrılmaz (boş token'la anlamsız hata üretme)", async () => {
    mockGet.mockResolvedValue({});
    await expect(hydrateFromDesktopSession()).resolves.toBe(false);
    expect(mockSetSession).not.toHaveBeenCalled();
  });

  it("KRİTİK: süresi geçmiş/iptal token → false (sessizce normal login akışı)", async () => {
    mockGet.mockResolvedValue(VALID);
    mockSetSession.mockResolvedValue({ error: { message: "Invalid Refresh Token" } });
    await expect(hydrateFromDesktopSession()).resolves.toBe(false);
  });

  it("uç hata fırlatsa da çökmez (uç hiç yoksa da NORMAL kabul edilir)", async () => {
    mockGet.mockRejectedValue(new Error("boom"));
    await expect(hydrateFromDesktopSession()).resolves.toBe(false);
  });

  it("KRİTİK: uç ASILI kalırsa bütçe dolunca vazgeçilir (açılış splash'inde kilitlenme yok)", async () => {
    jest.useFakeTimers();
    mockGet.mockReturnValue(new Promise(() => {})); // hiç çözülmeyen istek (yarı-açık bağlantı)
    const p = hydrateFromDesktopSession();
    jest.advanceTimersByTime(3600);
    await expect(p).resolves.toBe(false);
    jest.useRealTimers();
  });

  it("KRİTİK: token HİÇBİR log seviyesinde yazılmaz", async () => {
    const spies = [
      jest.spyOn(console, "log").mockImplementation(() => {}),
      jest.spyOn(console, "info").mockImplementation(() => {}),
      jest.spyOn(console, "warn").mockImplementation(() => {}),
      jest.spyOn(console, "error").mockImplementation(() => {}),
      jest.spyOn(console, "debug").mockImplementation(() => {}),
    ];
    mockGet.mockResolvedValue(VALID);
    mockSetSession.mockResolvedValue({ error: { message: "Invalid Refresh Token" } }); // hata yolu da denensin
    await hydrateFromDesktopSession();
    const yazilan = spies.flatMap((s) => s.mock.calls.flat()).map((a) => JSON.stringify(a)).join(" ");
    expect(yazilan).not.toContain("AT-gizli");
    expect(yazilan).not.toContain("RT-gizli");
    spies.forEach((s) => s.mockRestore());
  });
});

describe("clearDesktopSession — çıkış", () => {
  it("KRİTİK: masaüstünde DELETE gönderilir (yoksa yenilemede oturum geri gelir)", async () => {
    await clearDesktopSession();
    expect(mockDelete).toHaveBeenCalledTimes(1);
    expect(mockDelete.mock.calls[0][0]).toBe("/auth/desktop-session");
    expect(mockDelete.mock.calls[0][2].silent).toBe(true);
  });

  it("backend kapalıysa hata YUTULUR (çıkış yine tamamlanmalı)", async () => {
    mockDelete.mockRejectedValue(new Error("bağlantı yok"));
    await expect(clearDesktopSession()).resolves.toBeUndefined();
  });
});
