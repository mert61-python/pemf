// Author: mertaygn, cglrgrkn
/**
 * Launcher "Beni hatırla" ↔ pencere oturumu (sahip kararları 2026-10-18; auth_session.bin kaybı).
 * =====================================================================================================================
 * Ölçülen (10-13 → 10-17): pencerede çıkış + yeniden giriş yapıldı; pencere launcher'a YALNIZ `TOKEN_REFRESHED`'i geri
 * yazıyordu → yeni giriş (`SIGNED_IN`) launcher'a hiç gitmedi, launcher sunucuda silinmiş oturumun jetonuyla kaldı ve sonraki
 * açılışta "Beni hatırla" kaydı sessizce silindi. Kararlar: (1) launcher pencerenin SON hesabını hatırlar → `SIGNED_IN` de
 * geri yazılır; (2) pencerede "Çıkış Yap" launcher'ı da çıkışa geçirir → `logout` devri siler (backend çıkış işareti bırakır);
 * S-SGI.7: hesap GEÇİŞİ (etkin hesaptan çıkıp diğerine geçme) devri SİLMEZ — yeni hesap `SIGNED_IN` ile devre yazılır.
 * Harness `AuthContext.SGI_1_3`ünki: supabase-js olay akışı ve masaüstü devir uçları en alt erişilebilir katta sahte; ürün
 * `AuthContext` + `hesapDeposu` GERÇEK.
 */
const mockDepo = new Map<string, string>();
let mockDinleyici: ((e: string, s: unknown) => void) | null = null;
let mockEtkin: { access_token: string; refresh_token: string; user: { email: string }; expires_at?: number } | null = null;
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
const mockDevir = {
  push: jest.fn(async (_s: unknown) => undefined),
  clear: jest.fn(async () => undefined),
};
jest.mock("@/services/desktopSession", () => ({
  isDesktopHost: jest.fn(() => true),
  hydrateFromDesktopSessionDetayli: jest.fn(async () => ({ durum: "yok" })),
  clearDesktopSession: () => mockDevir.clear(),
  pushDesktopSession: (s: unknown) => mockDevir.push(s),
}));

import React, { ReactNode } from "react";
import { act, renderHook, waitFor } from "@testing-library/react-native";
import { AuthProvider, useAuth } from "@/context/AuthContext";

const oturum = (email: string, n = 1) => ({
  access_token: `AT-${email}-${n}`,
  refresh_token: `RT-${email}-${n}`,
  user: { email },
  expires_at: 1_900_000_000 + n,
});

const setup = async (email = "a@klinik.com") => {
  mockEtkin = oturum(email);
  const h = renderHook(() => useAuth(), {
    wrapper: ({ children }: { children: ReactNode }) => <AuthProvider>{children}</AuthProvider>,
  });
  await act(async () => { mockDinleyici?.("INITIAL_SESSION", mockEtkin); });
  await waitFor(() => expect(h.result.current.session?.email).toBe(email));
  mockDevir.push.mockClear();
  mockDevir.clear.mockClear();
  return h;
};
const yayinla = async (olay: string, s: unknown) => {
  await act(async () => {
    mockEtkin = s as typeof mockEtkin;
    mockDinleyici?.(olay, s);
  });
};
const itilenRT = () => mockDevir.push.mock.calls.map((c) => (c[0] as { refresh_token: string }).refresh_token);

beforeEach(() => {
  mockDepo.clear();
  mockDinleyici = null;
  mockDevir.push.mockClear();
  mockDevir.clear.mockClear();
});

it("KRİTİK: pencerede YENİ giriş (SIGNED_IN, yeni oturum) launcher'a geri yazılır (launcher son hesabı hatırlar)", async () => {
  await setup();
  await yayinla("SIGNED_OUT", null);
  await yayinla("SIGNED_IN", oturum("a@klinik.com", 7)); // çıkış + aynı hesapla yeniden giriş (10-13 olayı)
  expect(itilenRT()).toContain("RT-a@klinik.com-7");
  const s = mockDevir.push.mock.calls.at(-1)![0] as { email: string; expires_at: number };
  expect(s.email).toBe("a@klinik.com");
  expect(s.expires_at).toBe(1_900_000_007);
});

it("KRİTİK: başka hesapla giriş de geri yazılır (karar: pencerenin SON hesabı)", async () => {
  await setup();
  await yayinla("SIGNED_IN", oturum("b@klinik.com", 2));
  expect(itilenRT()).toContain("RT-b@klinik.com-2");
});

it("KRİTİK S-SGI.7: etkin hesaptan çıkıp diğer açık hesaba GEÇMEK devri SİLMEZ; yeni hesap devre yazılır", async () => {
  const h = await setup("a@klinik.com");
  await act(async () => { await h.result.current.hesapEkle!(); });
  await yayinla("SIGNED_IN", oturum("b@klinik.com")); // B eklendi (A parkta)
  await waitFor(() => expect(h.result.current.hesapEkleniyor).toBe(false));
  mockDevir.push.mockClear();
  mockDevir.clear.mockClear();
  await act(async () => { await h.result.current.hesaptanCik!("b@klinik.com"); }); // etkin B'den çık → A'ya geç
  await waitFor(() => expect(h.result.current.session?.email).toBe("a@klinik.com"));
  expect(mockDevir.clear).not.toHaveBeenCalled();
  expect(itilenRT()).toContain("RT-a@klinik.com-1");
});

it("KARŞIT: tam çıkış (logout) devri SİLER → backend çıkış işareti → launcher kaydını temizler", async () => {
  const h = await setup();
  await act(async () => { await h.result.current.logout(); });
  expect(mockDevir.clear).toHaveBeenCalledTimes(1);
});

it("KARŞIT: jeton yenilemesi (TOKEN_REFRESHED) bugünkü gibi geri yazılır", async () => {
  await setup();
  await yayinla("TOKEN_REFRESHED", oturum("a@klinik.com", 3));
  expect(itilenRT()).toEqual(["RT-a@klinik.com-3"]);
});
