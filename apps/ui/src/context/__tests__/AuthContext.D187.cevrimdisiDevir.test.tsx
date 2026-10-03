// Author: mertaygn, cglrgrkn
/**
 * D1.87 · B-6.5 + İG-6.17 · A-70 (sahip: çevrimdışı açılış GEREKSİNİM) — masaüstü devri ağ hatasını RETTEN ayırır.
 * =============================================================================================================
 * ÖLÇÜLEN KUSUR (aday İG-6.17, gerçek web paketi + Chrome, Supabase CDP ile kesildi): launcher'ın devrettiği oturum —
 * geçerli ya da süresi dolmuş — internet yokken `setSession` ağ hatası verince arayüz GİRİŞ ekranına düşüyordu ("ulaşamadım"
 * = "hayır"); internetsiz klinikte seans kontrolüne ve uygulama içi ACİL DURDUR'a erişilemiyordu. Launcher'ın kendi kararı
 * "ULAŞAMADIM ≠ HAYIR" (main.rs OFFLINE KARARI). A-70: bu makinede daha önce doğrulanmış hesap (launcher devri) internetsiz
 * yerel olarak açılır; Supabase'in AÇIK reddi (400/401) yine giriş ekranıdır.
 *
 * GERÇEK: `desktopSession` (devir okuma + sınıflama), `AuthProvider`, supabase-js'in GERÇEK hata sınıfları
 * (`AuthRetryableFetchError` = ağ, `AuthApiError` = ret). Sahte: devir ucunun yanıtı (`apiGet`) ve `setSession` sonucu.
 * ⚠️ MUTASYON: ağ hatası dalı yeniden `false`a indirilirse KRİTİK; ret de kabul edilirse KARŞIT KIRMIZI.
 * ⚠️ Profil kalıcılığı geri EKLENMEZ (Ö.4): yalnız auth oturumu; userMode diske yazılmaz (bu dosya ona dokunmaz).
 */
jest.mock("react-native", () => {
  const RN = jest.requireActual("react-native");
  RN.Platform.OS = "web";
  return RN;
});
// Sahte JWT ÇALIŞMA ANINDA kurulur (sır taraması literal jetonu sır sanmasın; imza yok, süresi dolmuş: exp=1).
const _b64 = (o: unknown) => Buffer.from(JSON.stringify(o)).toString("base64").replace(/=+$/, "");
const mockDevir = {
  access_token: [_b64({ alg: "none" }), _b64({ email: "op@klinik.com", exp: 1 }), "sahte"].join("."),
  refresh_token: "yenileme",
  email: "op@klinik.com",
  expires_at: 1,
};
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async () => mockDevir),
  apiPost: jest.fn(async () => null),
  apiDelete: jest.fn(async () => null),
}));
const mockOlay: { cb?: (e: string, s: unknown) => void } = {};
const mockSetSession = jest.fn();
jest.mock("@/services/supabaseAuth", () => ({
  supabaseAuth: {
    auth: {
      setSession: (...a: unknown[]) => mockSetSession(...a),
      onAuthStateChange: (cb: (e: string, s: unknown) => void) => {
        mockOlay.cb = cb;
        return { data: { subscription: { unsubscribe: jest.fn() } } };
      },
    },
  },
  getCurrentSession: jest.fn(async () => null),
  signOutUser: jest.fn(async () => undefined),
}));

import React, { ReactNode } from "react";
import { act, renderHook, waitFor } from "@testing-library/react-native";
import { AuthApiError, AuthRetryableFetchError } from "@supabase/supabase-js";
import { AuthProvider, useAuth } from "@/context/AuthContext";

const durum = (v: { loading: boolean; session: { email: string } | null }) =>
  v.loading ? "splash" : v.session ? `app:${v.session.email}` : "login";
const kur = () =>
  renderHook(() => useAuth(), {
    wrapper: ({ children }: { children: ReactNode }) => <AuthProvider>{children}</AuthProvider>,
  });

beforeAll(() => {
  (global as any).window = (global as any).window ?? {};
  (global as any).window.location = { hostname: "127.0.0.1" };
});
beforeEach(() => {
  mockSetSession.mockReset();
});

describe("D1.87 / A-70 — masaüstü devri: ulaşamadım ≠ hayır", () => {
  it("KRİTİK: Supabase'e ULAŞILAMAZSA (AuthRetryableFetchError) devralınan oturumla uygulamaya girilir", async () => {
    mockSetSession.mockResolvedValue({ data: { session: null }, error: new AuthRetryableFetchError("Failed to fetch", 0) });
    const { result } = kur();
    await waitFor(() => expect(durum(result.current)).not.toBe("splash"));
    expect(durum(result.current)).toBe("app:op@klinik.com");
  });

  it("KRİTİK: istek FIRLATIRSA da (TypeError: Network request failed) çevrimdışı açılış", async () => {
    mockSetSession.mockRejectedValue(new TypeError("Network request failed"));
    const { result } = kur();
    await waitFor(() => expect(durum(result.current)).not.toBe("splash"));
    expect(durum(result.current)).toBe("app:op@klinik.com");
  });

  it("KARŞIT: Supabase AÇIKÇA REDDEDERSE (AuthApiError 400) giriş ekranı KALIR", async () => {
    mockSetSession.mockResolvedValue({
      data: { session: null },
      error: new AuthApiError("Invalid Refresh Token: Refresh Token Not Found", 400, "refresh_token_not_found"),
    });
    const { result } = kur();
    await waitFor(() => expect(durum(result.current)).not.toBe("splash"));
    expect(durum(result.current)).toBe("login");
  });

  it("KARŞIT: çevrimdışı oturum INITIAL_SESSION(null) olayıyla DÜŞMEZ; SIGNED_OUT ile düşer", async () => {
    mockSetSession.mockResolvedValue({ data: { session: null }, error: new AuthRetryableFetchError("Failed to fetch", 0) });
    const { result } = kur();
    await waitFor(() => expect(durum(result.current)).toBe("app:op@klinik.com"));
    act(() => mockOlay.cb?.("INITIAL_SESSION", null));
    expect(durum(result.current)).toBe("app:op@klinik.com");
    act(() => mockOlay.cb?.("SIGNED_OUT", null));
    expect(durum(result.current)).toBe("login");
  });
});
