// Author: mertaygn, cglrgrkn
/**
 * SGI-1.3 (bağımsız inceleme) — "Hesap ekle" kipinde ETKİN hesabın belirteç YENİLEMESİ (supabase-js `TOKEN_REFRESHED`).
 * =====================================================================================================================
 * Ölçülen (549ce2b0): `AuthContext` eklemenin bitişini "farklı erişim belirteci" ile anlıyor; etkin hesabın (A) arka plan yenilemesi de farklı
 * belirteç taşıdığı için giriş ekranı KENDİLİĞİNDEN kapanıyor (kullanıcı başka hesabın şifresini yazarken uygulamaya geri atılır) — CH1'in kendi
 * sözleşmesi "YENİ bir giriş gelince ekleme biter" der.
 * Naif düzeltme (yalnız `SIGNED_IN`'de bitir) İKİNCİ bir kusur açar: park kopyası A'nın HARCANMIŞ yenileme belirtecini tutar; sonra A'ya geçişte o
 * belirteç yeniden kullanılır (GoTrue yeniden kullanım sezgisi aileyi iptal eder — masaüstünde launcher'ın oturumu da ölür; 2026-09-03 saha
 * arızasının sınıfı). Sözleşme: yenilemede ekleme SÜRER ve park kopyası TAZE belirteçle güncellenir; yeni giriş (SIGNED_IN, farklı belirteç)
 * eklemeyi bitirir (KARŞIT).
 * Harness CH1 kapısınınki (`AuthContext.CH1.cokluHesap.test.tsx`): supabase-js olay akışı en alt erişilebilir katta sahte, ürün `AuthContext` +
 * `hesapDeposu` GERÇEK.
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
const yayinla = async (olay: string, s: unknown) => {
  await act(async () => {
    mockEtkin = s as typeof mockEtkin;
    mockDinleyici?.(olay, s);
  });
};
const bekle = async () => { await act(async () => { await new Promise((r) => setTimeout(r, 20)); }); };

beforeEach(() => {
  mockDepo.clear();
  mockDinleyici = null;
  jest.clearAllMocks();
});

it("KRİTİK: 'Hesap ekle' sürerken etkin hesabın belirteç YENİLEMESİ (TOKEN_REFRESHED) giriş ekranını KAPATMAZ", async () => {
  const h = await setup();
  await act(async () => { await h.result.current.hesapEkle!(); });
  expect(h.result.current.hesapEkleniyor).toBe(true);
  await yayinla("TOKEN_REFRESHED", oturum("a@klinik.com", 2)); // supabase-js arka plan yenilemesi (~her saat / ön plana dönüşte)
  await bekle();
  expect(h.result.current.hesapEkleniyor).toBe(true);
});

it("KRİTİK: yenilemeden sonra park kopyası TAZE yenileme belirtecini tutar (harcanmış belirteç yeniden kullanılmaz)", async () => {
  const h = await setup();
  await act(async () => { await h.result.current.hesapEkle!(); });
  await yayinla("TOKEN_REFRESHED", oturum("a@klinik.com", 2));
  await bekle();
  await yayinla("SIGNED_IN", oturum("c@klinik.com")); // kullanıcı ekleme ekranında C ile giriş yapar
  await waitFor(() => expect(h.result.current.hesapEkleniyor).toBe(false));
  await waitFor(() => expect(h.result.current.session?.email).toBe("c@klinik.com"));
  const park = await parkHesaplari();
  const a = park.find((x) => x.email === "a@klinik.com");
  expect(a?.refresh_token).toBe("RT-a@klinik.com-2");
  // A'ya geri geçiş TAZE belirteçle kurulur (harcanmış RT-…-1 GoTrue'ya gitmez).
  await act(async () => { await h.result.current.hesabaGec!("a@klinik.com"); });
  expect(mockAuth.setSession).toHaveBeenLastCalledWith({ access_token: "AT-a@klinik.com-2", refresh_token: "RT-a@klinik.com-2" });
});

it("KRİTİK: yenilenmiş oturumun yeniden yayını (sekme odağı — SIGNED_IN, aynı TAZE belirteç) eklemeyi BİTİRMEZ", async () => {
  const h = await setup();
  await act(async () => { await h.result.current.hesapEkle!(); });
  await yayinla("TOKEN_REFRESHED", oturum("a@klinik.com", 2));
  await bekle();
  await yayinla("SIGNED_IN", oturum("a@klinik.com", 2)); // supabase-js görünürlük kurtarması aynı oturumu yeniden yayınlar
  await bekle();
  expect(h.result.current.hesapEkleniyor).toBe(true);
});

it("KARŞIT: ekleme ekranında YENİ giriş (SIGNED_IN, farklı belirteç — aynı e-posta ile yeniden giriş dahil) eklemeyi BİTİRİR", async () => {
  const h = await setup();
  await act(async () => { await h.result.current.hesapEkle!(); });
  await yayinla("SIGNED_IN", oturum("a@klinik.com", 7));
  await waitFor(() => expect(h.result.current.hesapEkleniyor).toBe(false));
  expect(h.result.current.session?.email).toBe("a@klinik.com");
});
