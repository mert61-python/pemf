/**
 * KP-3 C · AuthContext — masaüstü devrinde (D1.87 / A-70) devir kaydında e-posta YOKSA çevrimdışı oturumun e-postası erişim jetonunun
 * (JWT) gövdesinden okunur; jeton çözülemezse (bozuk) ve e-posta da yoksa çevrimdışı oturum KURULMAZ → giriş ekranı (kimliksiz oturum
 * açılmaz). AuthContext.D187.cevrimdisiDevir.test.tsx düzeneğinin aynısı (Supabase'e ulaşılamıyor senaryosu).
 * SAHTE (en alt kat): apiClient (devir kaydı), supabaseAuth istemcisi; Platform.OS = web, pencere loopback.
 */
jest.mock("react-native", () => {
  const RN = jest.requireActual("react-native");
  RN.Platform.OS = "web";
  return RN;
});
const _b64 = (o: unknown) => Buffer.from(JSON.stringify(o)).toString("base64").replace(/=+$/, "");
const mockDevir: { access_token: string; refresh_token: string; email: string; expires_at: number } = {
  access_token: "",
  refresh_token: "yenileme",
  email: "",
  expires_at: 1,
};
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async () => mockDevir),
  apiPost: jest.fn(async () => null),
  apiDelete: jest.fn(async () => null),
}));
const mockSetSession = jest.fn();
jest.mock("@/services/supabaseAuth", () => ({
  supabaseAuth: {
    auth: {
      setSession: (...a: unknown[]) => mockSetSession(...a),
      onAuthStateChange: () => ({ data: { subscription: { unsubscribe: jest.fn() } } }),
    },
  },
  getCurrentSession: jest.fn(async () => null),
  signOutUser: jest.fn(async () => undefined),
}));

import React, { ReactNode } from "react";
import { renderHook, waitFor } from "@testing-library/react-native";
import { AuthRetryableFetchError } from "@supabase/supabase-js";
import { AuthProvider, useAuth } from "@/context/AuthContext";

const durum = (v: { loading: boolean; session: { email: string; cevrimdisi?: boolean } | null }) =>
  v.loading ? "splash" : v.session ? `app:${v.session.email}:${v.session.cevrimdisi ? "cevrimdisi" : "cevrimici"}` : "login";
const kur = () =>
  renderHook(() => useAuth(), { wrapper: ({ children }: { children: ReactNode }) => <AuthProvider>{children}</AuthProvider> });

beforeAll(() => {
  (global as any).window = (global as any).window ?? {};
  (global as any).window.location = { hostname: "127.0.0.1" };
});
beforeEach(() => {
  mockSetSession.mockReset();
  mockSetSession.mockResolvedValue({ data: { session: null }, error: new AuthRetryableFetchError("Failed to fetch", 0) });
});

it("devirde e-posta yoksa çevrimdışı oturumun e-postası JWT gövdesinden okunur", async () => {
  mockDevir.email = "";
  mockDevir.access_token = [_b64({ alg: "none" }), _b64({ email: "jwt@klinik.com", exp: 1 }), "sahte"].join(".");
  const { result } = kur();
  await waitFor(() => expect(durum(result.current)).not.toBe("splash"));
  expect(durum(result.current)).toBe("app:jwt@klinik.com:cevrimdisi");
});

it("JWT çözülemez ve e-posta yoksa çevrimdışı oturum KURULMAZ → giriş ekranı", async () => {
  mockDevir.email = "";
  mockDevir.access_token = "bozuk-jeton.%%%.x";
  const { result } = kur();
  await waitFor(() => expect(durum(result.current)).not.toBe("splash"));
  expect(durum(result.current)).toBe("login");
});
