// Author: mertaygn, cglrgrkn
/**
 * AuthContext — MASAÜSTÜ OTURUM DEVRİ (E-özelliği, 2026-08-06).
 *
 * Kilitlenen sözleşme:
 *   1. Devir başarılıysa login ekranı ATLANIR (client'ta giriş yapıldı → çift giriş YOK)
 *   2. Uç boş/hatalı dönerse ya da HİÇ YOKSA (mobil, eski backend) NORMAL login akışına düşülür
 *      ve kullanıcı HİÇBİR hata görmez
 *   3. Devir sürerken `loading` TRUE kalır → AuthGate splash'te durur, AuthScreen "yanıp sönmez"
 *      (onAuthStateChange abone olur olmaz INITIAL_SESSION yayınlar; tek başına `loading` yetmez)
 *   4. Mobilde devir HİÇ denenmez
 *   5. Çıkışta ÖNCE backend devir oturumu silinir, SONRA Supabase signOut — aksi halde sayfa
 *      yenilenince uygulama kendini tekrar hydrate eder ve masaüstünde çıkış İŞLEMEZ
 */
jest.mock("@/services/supabaseAuth", () => ({
  supabaseAuth: { auth: { onAuthStateChange: jest.fn(() => ({ data: { subscription: { unsubscribe: jest.fn() } } })) } },
  getCurrentSession: jest.fn(async () => null),
  signOutUser: jest.fn(async () => undefined),
}));
jest.mock("@/services/desktopSession", () => ({
  isDesktopHost: jest.fn(() => true),
  hydrateFromDesktopSession: jest.fn(async () => false),
  clearDesktopSession: jest.fn(async () => undefined),
}));

import React, { ReactNode } from "react";
import { renderHook, waitFor, act } from "@testing-library/react-native";
import { getCurrentSession, signOutUser, supabaseAuth } from "@/services/supabaseAuth";
import { isDesktopHost, hydrateFromDesktopSession, clearDesktopSession } from "@/services/desktopSession";
import { AuthProvider, useAuth } from "@/context/AuthContext";

const mockGetSession = getCurrentSession as jest.Mock;
const mockSignOut = signOutUser as jest.Mock;
const mockIsDesktop = isDesktopHost as jest.Mock;
const mockHydrate = hydrateFromDesktopSession as jest.Mock;
const mockClear = clearDesktopSession as jest.Mock;
const mockOnAuthStateChange = (supabaseAuth as unknown as { auth: { onAuthStateChange: jest.Mock } }).auth.onAuthStateChange;

const SUPA_SESSION = { access_token: "AT", user: { email: "op@klinik.com", user_metadata: { first_name: "Op" } } };

/** AuthGate'in gördüğü üç durumu tek kelimeye indir: splash / login / uygulama. */
const durum = (v: { loading: boolean; session: { email: string } | null }) =>
  v.loading ? "splash" : v.session ? `app:${v.session.email}` : "login";

const setup = () =>
  renderHook(() => useAuth(), {
    wrapper: ({ children }: { children: ReactNode }) => <AuthProvider>{children}</AuthProvider>,
  });

beforeEach(() => {
  jest.clearAllMocks();
  mockIsDesktop.mockReturnValue(true);
  mockHydrate.mockResolvedValue(false);
  mockGetSession.mockResolvedValue(null);
  mockOnAuthStateChange.mockReturnValue({ data: { subscription: { unsubscribe: jest.fn() } } });
});

describe("masaüstü devri", () => {
  it("KRİTİK: devir başarılıysa LOGIN ATLANIR (çift giriş yok)", async () => {
    mockHydrate.mockResolvedValue(true);
    mockGetSession.mockResolvedValue(SUPA_SESSION); // devir sonrası supabase oturumu kuruldu
    const { result } = setup();
    await waitFor(() => expect(durum(result.current)).toBe("app:op@klinik.com"));
    expect(mockHydrate).toHaveBeenCalledTimes(1);
  });

  it("KRİTİK: uç BOŞ dönerse normal login gösterilir (hata YOK)", async () => {
    mockHydrate.mockResolvedValue(false);
    const { result } = setup();
    await waitFor(() => expect(durum(result.current)).toBe("login"));
  });

  it("KRİTİK: uç HATA fırlatsa da uygulama açılır (uç hiç yoksa da normal)", async () => {
    mockHydrate.mockRejectedValue(new Error("uç yok"));
    const { result } = setup();
    await waitFor(() => expect(durum(result.current)).toBe("login"));
  });

  it("KRİTİK: MOBİLDE devir HİÇ denenmez", async () => {
    mockIsDesktop.mockReturnValue(false);
    const { result } = setup();
    await waitFor(() => expect(durum(result.current)).toBe("login"));
    expect(mockHydrate).not.toHaveBeenCalled();
  });

  it("KRİTİK: devir sürerken SPLASH'te kalınır — INITIAL_SESSION(null) olayı login ekranını AÇMAZ", async () => {
    let devriBitir: (v: boolean) => void = () => {};
    mockHydrate.mockReturnValue(new Promise<boolean>((res) => { devriBitir = res; }));
    // supabase-js abone olur olmaz INITIAL_SESSION yayınlar → eski kodda loading hemen false olurdu.
    mockOnAuthStateChange.mockImplementation((cb: (e: string, s: unknown) => void) => {
      cb("INITIAL_SESSION", null);
      return { data: { subscription: { unsubscribe: jest.fn() } } };
    });
    mockGetSession.mockResolvedValue(SUPA_SESSION);

    const { result } = setup();
    expect(durum(result.current)).toBe("splash"); // <-- login "yanıp sönmez"
    await act(async () => { devriBitir(true); });
    await waitFor(() => expect(durum(result.current)).toBe("app:op@klinik.com"));
  });

  it("KRİTİK: devir/oturum-okuma ASILI kalsa da splash sonsuza dek sürmez (masaüstü kilitlenmesi)", async () => {
    // Gerçek senaryo: supabase-js'in `setSession`'ı ağ çağrısı yapar ve İÇ KİLİDİ tutar; o çağrının
    // zaman aşımı YOKTUR (yarı-açık tünel / captive portal). Ardından gelen `getCurrentSession()`
    // kilidin arkasında bekler → `hydrating` hiç kapanmaz ve operatör uygulamaya (ACİL DURDUR'a)
    // giremezdi. Bütçe yalnız BEKLENEN sonucu sınırlar, arka plandaki çağrıyı değil.
    jest.useFakeTimers();
    mockHydrate.mockReturnValue(new Promise(() => {}));    // devir hiç çözülmüyor
    mockGetSession.mockReturnValue(new Promise(() => {})); // supabase kilidi asılı
    mockOnAuthStateChange.mockImplementation((cb: (e: string, s: unknown) => void) => {
      cb("INITIAL_SESSION", null);
      return { data: { subscription: { unsubscribe: jest.fn() } } };
    });

    const { result } = setup();
    expect(durum(result.current)).toBe("splash");
    await act(async () => { jest.advanceTimersByTime(10000); });
    expect(durum(result.current)).toBe("login"); // <-- donmuş spinner DEĞİL
    jest.useRealTimers();
  });

  it("abonelik hidrasyondan ÖNCE kurulur (setSession olayı kaçmasın)", async () => {
    const sira: string[] = [];
    mockOnAuthStateChange.mockImplementation(() => {
      sira.push("subscribe");
      return { data: { subscription: { unsubscribe: jest.fn() } } };
    });
    mockHydrate.mockImplementation(async () => { sira.push("hydrate"); return false; });
    setup();
    await waitFor(() => expect(sira).toEqual(["subscribe", "hydrate"]));
  });
});

describe("çıkış", () => {
  it("KRİTİK: ÖNCE backend devir oturumu silinir, SONRA Supabase signOut", async () => {
    const sira: string[] = [];
    mockClear.mockImplementation(async () => { sira.push("clear"); });
    mockSignOut.mockImplementation(async () => { sira.push("signOut"); });
    mockHydrate.mockResolvedValue(true);
    mockGetSession.mockResolvedValue(SUPA_SESSION);

    const { result } = setup();
    await waitFor(() => expect(durum(result.current)).toBe("app:op@klinik.com"));
    await act(async () => { await result.current.logout(); });

    expect(sira).toEqual(["clear", "signOut"]);
    await waitFor(() => expect(durum(result.current)).toBe("login"));
  });
});
