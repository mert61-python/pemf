// Author: mertaygn, cglrgrkn
/**
 * D1.87 · B-6.5 — MOBİLDE süresi dolmuş saklı oturum + ağ yokken açılış splash'i TAVAN içinde biter.
 * ===============================================================================================
 * ÖLÇÜLEN KUSUR (06-2 g1a+g1b): mobilde saklı oturumun yenilemesi ağ reddinde asılı kalınca `getCurrentSession()` dönmüyor,
 * açılış splash'i ~51 sn sürüyordu (supabase-js'in yenileme denemeleri; zaman aşımı yok). Splash tavanı yalnız masaüstü
 * devrinin `hydrating` bayrağını kapatıyordu — mobilde `loading` asılı kalıyordu. Tavan dolunca splash'ten çıkılır (giriş
 * ekranında da kayan ACİL DURDUR vardır — Y23); geç gelen oturum `onAuthStateChange` ile kullanıcıyı içeri alır.
 * ⚠️ MUTASYON: tavan `loading`i kapatmazsa KIRMIZI.
 */
jest.mock("@/services/supabaseAuth", () => ({
  supabaseAuth: { auth: { onAuthStateChange: jest.fn(() => ({ data: { subscription: { unsubscribe: jest.fn() } } })) } },
  getCurrentSession: jest.fn(() => new Promise(() => undefined)), // ağ yok: yenileme ASILI
  signOutUser: jest.fn(async () => undefined),
}));
jest.mock("@/services/desktopSession", () => ({
  isDesktopHost: jest.fn(() => false), // mobil: devir yok
  hydrateFromDesktopSessionDetayli: jest.fn(async () => ({ durum: "yok" })),
  hydrateFromDesktopSession: jest.fn(async () => false),
  clearDesktopSession: jest.fn(async () => undefined),
  pushDesktopSession: jest.fn(async () => undefined),
}));

import React, { ReactNode } from "react";
import { act, renderHook } from "@testing-library/react-native";
import { AuthProvider, useAuth } from "@/context/AuthContext";

beforeEach(() => jest.useFakeTimers());
afterEach(() => jest.useRealTimers());

it("KRİTİK: mobilde asılı oturum okuması splash'i TAVANDA (≤ 6 sn) bitirir — giriş ekranı açılır", async () => {
  const { result } = renderHook(() => useAuth(), {
    wrapper: ({ children }: { children: ReactNode }) => <AuthProvider>{children}</AuthProvider>,
  });
  expect(result.current.loading).toBe(true);
  await act(async () => {
    jest.advanceTimersByTime(6100);
  });
  expect(result.current.loading).toBe(false);
  expect(result.current.session).toBeNull();
});
