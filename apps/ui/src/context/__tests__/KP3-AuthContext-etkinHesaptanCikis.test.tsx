/**
 * KP-3 C · AuthContext — ETKİN hesaptan hesap başına çıkışın kalan iki kolu (her test bir DAVRANIŞ iddiası; CH1 düzeneği):
 *  - Cihazda açık BAŞKA hesap yoksa etkin hesaptan çıkış = bugünkü tam çıkış (oturum kapanır, `signOutUser`).
 *  - Diğer açık hesaba geçiş SUNUCUDA düşerse (ağ hatası — kalıcı değil): hata metni döner, çıkılan hesap ETKİN kalır ve SİLİNMEZ
 *    (diğer hesap da açık kalır) — yarım çıkış yok.
 * SAHTE (en alt kat): Supabase istemcisi (`supabaseAuth` — ağ YOK) · masaüstü devri. GERÇEK: AuthProvider + hesapGecisi + hesapDeposu.
 * ⚠️ Ürün kodu (kimlik doğrulama) DEĞİŞMEDİ — yalnız test.
 */
const mockDepo = new Map<string, string>();
let mockDinleyici: ((e: string, s: unknown) => void) | null = null;
let mockEtkin: { access_token: string; refresh_token: string; user: { email: string } } | null = null;
const mockAuth = {
  onAuthStateChange: jest.fn((cb: (e: string, s: unknown) => void) => {
    mockDinleyici = cb;
    return { data: { subscription: { unsubscribe: jest.fn() } } };
  }),
  getSession: jest.fn(async () => ({ data: { session: mockEtkin } })),
  setSession: jest.fn(async ({ access_token, refresh_token }: { access_token: string; refresh_token: string }) => {
    const email = access_token.replace(/^AT-/, "").replace(/-\d+$/, "");
    mockEtkin = { access_token, refresh_token, user: { email } };
    mockDinleyici?.("SIGNED_IN", mockEtkin);
    return { data: { session: mockEtkin }, error: null };
  }),
  admin: { signOut: jest.fn(async () => ({ data: null, error: null })) },
};
jest.mock("@/services/supabaseAuth", () => ({
  supabaseAuth: { get auth() { return mockAuth; } },
  oturumDeposu: {
    getItem: async (k: string) => (mockDepo.has(k) ? mockDepo.get(k)! : null),
    setItem: async (k: string, v: string) => { mockDepo.set(k, v); },
    removeItem: async (k: string) => { mockDepo.delete(k); },
  },
  getCurrentSession: jest.fn(async () => mockEtkin),
  signOutUser: jest.fn(async () => {
    mockEtkin = null;
    mockDinleyici?.("SIGNED_OUT", null);
  }),
}));
jest.mock("@/services/desktopSession", () => ({
  isDesktopHost: jest.fn(() => false),
  hydrateFromDesktopSessionDetayli: jest.fn(async () => ({ durum: "yok" })),
  clearDesktopSession: jest.fn(async () => undefined),
  pushDesktopSession: jest.fn(async () => undefined),
}));

import React, { ReactNode } from "react";
import { act, renderHook, waitFor } from "@testing-library/react-native";
import i18n from "i18next";
import { signOutUser } from "@/services/supabaseAuth";
import { parkHesaplari } from "@/services/hesapDeposu";
import { AuthProvider, useAuth } from "@/context/AuthContext";

const T = (k: string, o?: object): string => (i18n.t as unknown as (k: string, o?: object) => string)(k, o);
const oturum = (email: string, n = 1) => ({ access_token: `AT-${email}-${n}`, refresh_token: `RT-${email}-${n}`, user: { email } });
const setup = async (email = "a@klinik.com") => {
  mockEtkin = oturum(email);
  const h = renderHook(() => useAuth(), {
    wrapper: ({ children }: { children: ReactNode }) => <AuthProvider>{children}</AuthProvider>,
  });
  await act(async () => { mockDinleyici?.("INITIAL_SESSION", mockEtkin); });
  await waitFor(() => expect(h.result.current.session?.email).toBe(email));
  return h;
};
const parkta = async () => (await parkHesaplari()).map((h) => h.email);

beforeEach(() => {
  mockDepo.clear();
  mockDinleyici = null;
  jest.clearAllMocks();
});

it("başka açık hesap yokken etkin hesaptan çıkış = tam çıkış", async () => {
  const h = await setup();
  let r: { ok: boolean } | undefined;
  await act(async () => { r = await h.result.current.hesaptanCik!("a@klinik.com"); });
  expect(r).toEqual({ ok: true });
  expect(signOutUser).toHaveBeenCalledTimes(1);
  await waitFor(() => expect(h.result.current.session).toBeNull());
});

it("diğer hesaba geçiş sunucuda düşerse hata döner; çıkılan hesap etkin kalır ve silinmez", async () => {
  const h = await setup();
  await act(async () => { await h.result.current.hesapEkle!(); });
  await act(async () => {
    mockEtkin = oturum("b@klinik.com");
    mockDinleyici?.("SIGNED_IN", mockEtkin);
  });
  await waitFor(() => expect(h.result.current.hesaplar).toHaveLength(2));
  // b etkin, a parkta. b'den çıkış → a'ya geçiş denenir; a'nın oturumu ağ hatasıyla KURULAMAZ (kalıcı değil).
  mockAuth.setSession.mockImplementationOnce(async () => ({ data: { session: null }, error: { name: "AuthRetryableFetchError", message: "Failed to fetch", status: 0 } }) as never);
  let r: { ok: boolean; hata?: string } | undefined;
  await act(async () => { r = await h.result.current.hesaptanCik!("b@klinik.com"); });
  expect(r).toEqual({ ok: false, hata: T("hesap.gecis.degistirilemediSunucu") });
  await waitFor(() => expect(h.result.current.session?.email).toBe("b@klinik.com"));
  expect(await parkta()).toEqual(["a@klinik.com"]);
  expect(mockAuth.admin.signOut).not.toHaveBeenCalled(); // çıkılmak istenen hesabın belirteci İPTAL EDİLMEDİ
  expect(signOutUser).not.toHaveBeenCalled();
});
