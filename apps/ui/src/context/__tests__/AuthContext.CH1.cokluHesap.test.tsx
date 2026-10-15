// Author: mertaygn, cglrgrkn
/**
 * CH1 · Y151 — AuthContext çoklu hesap akışları.
 * ==============================================
 * SÖZLEŞME:
 *  · "Hesap ekle": etkin hesap park edilir; YENİ bir giriş (farklı belirteç) gelince ekleme biter, giriş yapılan hesap etkin, önceki
 *    açık kalır; aynı oturumun yeniden yayını (sekme odağı vb., aynı belirteç) eklemeyi BİTİRMEZ; vazgeçilince önceki hesap etkin ve
 *    park kopyası kalmaz.
 *  · Etkin e-posta DEĞİŞİNCE hesap kuşağı artar ve Bearer düşer (uçuştaki eski hesap yanıtları atılır).
 *  · "Çıkış Yap" = TÜM hesaplardan çık: park edilenler cihazdan silinir (+ sunucuda iptal denemesi), etkin oturum kapanır.
 *  · Hesap başına çıkış: park edilmiş hesap → yalnız o; etkin hesap → açık başka hesaba geçilir, çıkılan hesap silinir + iptal.
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
  // ⚠️ getter: jest.mock fabrikası import'larla birlikte hoist edilir — `mockAuth` o anda henüz başlatılmamıştır.
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
import { signOutUser } from "@/services/supabaseAuth";
import { hesapKusagi } from "@/services/apiClient";
import { parkHesaplari } from "@/services/hesapDeposu";
import { AuthProvider, useAuth } from "@/context/AuthContext";

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
const yayinla = async (olay: string, s: unknown) => {
  await act(async () => {
    mockEtkin = s as typeof mockEtkin;
    mockDinleyici?.(olay, s);
  });
};

beforeEach(() => {
  mockDepo.clear();
  mockDinleyici = null;
  jest.clearAllMocks();
});

it("KRİTİK 'Hesap ekle': A park edilir; B ile giriş → ekleme biter, B etkin, A açık kalır; kuşak artar", async () => {
  const h = await setup();
  await act(async () => { await h.result.current.hesapEkle!(); });
  expect(h.result.current.hesapEkleniyor).toBe(true);
  expect(await parkta()).toEqual(["a@klinik.com"]);
  const kusak = hesapKusagi();
  await yayinla("SIGNED_IN", oturum("b@klinik.com"));
  await waitFor(() => expect(h.result.current.hesapEkleniyor).toBe(false));
  expect(h.result.current.session?.email).toBe("b@klinik.com");
  await waitFor(() => expect(h.result.current.hesaplar).toEqual(["b@klinik.com", "a@klinik.com"]));
  expect(hesapKusagi()).toBeGreaterThan(kusak);
});

it("KRİTİK: ekleme sırasında AYNI oturumun yeniden yayını (aynı belirteç) eklemeyi BİTİRMEZ", async () => {
  const h = await setup();
  await act(async () => { await h.result.current.hesapEkle!(); });
  await yayinla("SIGNED_IN", oturum("a@klinik.com")); // sekme odağı vb. — aynı belirteç
  expect(h.result.current.hesapEkleniyor).toBe(true);
});

it("vazgeç: önceki hesap etkin kalır, park kopyası temizlenir", async () => {
  const h = await setup();
  await act(async () => { await h.result.current.hesapEkle!(); });
  await act(async () => { await h.result.current.hesapEklemeVazgec!(); });
  expect(h.result.current.hesapEkleniyor).toBe(false);
  expect(await parkta()).toEqual([]);
  expect(h.result.current.hesaplar).toEqual(["a@klinik.com"]);
});

it("KRİTİK 'Çıkış Yap' = TÜM hesaplardan çık: park edilenler silinir + sunucuda iptal denenir, etkin oturum kapanır", async () => {
  const h = await setup();
  await act(async () => { await h.result.current.hesapEkle!(); });
  await yayinla("SIGNED_IN", oturum("b@klinik.com"));
  await waitFor(() => expect(h.result.current.hesaplar).toHaveLength(2));
  await act(async () => { await h.result.current.logout(); });
  expect(await parkta()).toEqual([]);
  expect(mockAuth.admin.signOut).toHaveBeenCalledWith("AT-a@klinik.com-1", "local");
  expect(signOutUser).toHaveBeenCalled();
  expect(h.result.current.session).toBeNull();
  expect(h.result.current.hesaplar).toEqual([]);
});

it("KRİTİK hesap başına çıkış — park edilmiş hesap: yalnız o; etkin hesap DEĞİŞMEZ", async () => {
  const h = await setup();
  await act(async () => { await h.result.current.hesapEkle!(); });
  await yayinla("SIGNED_IN", oturum("b@klinik.com"));
  await waitFor(() => expect(h.result.current.hesaplar).toHaveLength(2));
  await act(async () => { await h.result.current.hesaptanCik!("a@klinik.com"); });
  expect(h.result.current.session?.email).toBe("b@klinik.com");
  expect(await parkta()).toEqual([]);
  expect(mockAuth.setSession).not.toHaveBeenCalled();
  expect(signOutUser).not.toHaveBeenCalled();
});

it("KRİTİK hesap başına çıkış — ETKİN hesap: açık diğer hesaba geçilir; çıkılan hesap silinir + iptal", async () => {
  const h = await setup();
  await act(async () => { await h.result.current.hesapEkle!(); });
  await yayinla("SIGNED_IN", oturum("b@klinik.com"));
  await waitFor(() => expect(h.result.current.hesaplar).toHaveLength(2));
  await act(async () => { await h.result.current.hesaptanCik!("b@klinik.com"); });
  await waitFor(() => expect(h.result.current.session?.email).toBe("a@klinik.com"));
  expect(await parkta()).toEqual([]);
  expect(mockAuth.admin.signOut).toHaveBeenCalledWith("AT-b@klinik.com-1", "local");
  expect(signOutUser).not.toHaveBeenCalled(); // tümden çıkış DEĞİL
});
