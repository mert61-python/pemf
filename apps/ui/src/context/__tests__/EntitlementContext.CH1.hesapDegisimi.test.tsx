// Author: mertaygn, cglrgrkn
/**
 * CH1 · Y151 — e-posta hesabı A → B DOĞRUDAN değişince (çoklu hesap geçişi; arada çıkış YOK) A'nın aboneliği B'ye TAŞINMAZ.
 * =========================================================================================================================
 * ÖLÇÜLEN KUSUR (taban `2f1ccb84`): sağlayıcı yalnız `session === null`da sıfırlıyordu. A'nın hakkı "bilinen hak" (D1.63) olarak
 * kalıyor; B'nin okuması sürerken ya da düşünce (çevrimdışı / Supabase yavaş) B'nin ekranında A'nın tier'ı ve isteklerinde A'nın
 * X-PEMF-Tier başlığı KALIYORDU.
 * SÖZLEŞME: e-posta değişir değişmez hak varsayılana döner, abonelik başlıkları ve Bearer düşer; B'nin okuması düşerse A'nın hakkı
 * GERİ GELMEZ. KARŞIT: AYNI hesapta çevrimdışı okuma bilinen hakkı korur (D1.63 / #98 aynen).
 */
jest.mock("@/services/supabaseAuth", () => ({
  supabaseAuth: {
    auth: { getUser: jest.fn(), getSession: jest.fn() },
    from: jest.fn(),
  },
}));
jest.mock("@/services/apiClient", () => ({
  setEntitlementHeaders: jest.fn(),
  setAuthBearer: jest.fn(),
}));
let mockSession: { email: string } | null = null;
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: mockSession }) }));

import React from "react";
import { act, render, waitFor } from "@testing-library/react-native";
import { Text } from "react-native";
import { setAuthBearer, setEntitlementHeaders } from "@/services/apiClient";
import { supabaseAuth } from "@/services/supabaseAuth";
import { EntitlementProvider, useEntitlement } from "@/context/EntitlementContext";

const mockSb = supabaseAuth as unknown as { auth: { getUser: jest.Mock; getSession: jest.Mock }; from: jest.Mock };
const mockHeaders = setEntitlementHeaders as jest.Mock;
const mockBearer = setAuthBearer as jest.Mock;

function Probe() {
  const { tier } = useEntitlement();
  return <Text testID="tier">{tier}</Text>;
}
const agac = () => <EntitlementProvider><Probe /></EntitlementProvider>;

beforeEach(() => {
  jest.clearAllMocks();
  mockSession = { email: "a@klinik.com" };
  mockSb.auth.getUser.mockResolvedValue({ data: { user: { id: "uA", created_at: new Date().toISOString() } } });
  mockSb.auth.getSession.mockResolvedValue({ data: { session: { access_token: "jwt-A" } } });
  mockSb.from.mockReturnValue({
    select: () => ({ eq: () => ({ maybeSingle: async () => ({ data: { tier: "pro_plus", status: "active", addons: ["research"] }, error: null }) }) }),
  });
});

it("KRİTİK: A → B geçişte A'nın hakkı ANINDA düşer (B'nin okuması sürerken bile); başlıklar ve Bearer düşer", async () => {
  const u = render(agac());
  await waitFor(() => expect(u.getByTestId("tier").props.children).toBe("pro_plus"));
  mockSb.auth.getUser.mockImplementation(() => new Promise(() => {})); // B'nin okuması asılı
  mockHeaders.mockClear();
  mockBearer.mockClear();
  mockSession = { email: "b@klinik.com" };
  await act(async () => { u.rerender(agac()); });
  expect(u.getByTestId("tier").props.children).toBe("baslangic");
  expect(mockHeaders).toHaveBeenCalledWith(null);
  expect(mockBearer).toHaveBeenCalledWith(null);
  expect(mockHeaders).not.toHaveBeenCalledWith("pro_plus", expect.anything());
});

it("KRİTİK: B'nin okuması DÜŞERSE (çevrimdışı) A'nın hakkı GERİ GELMEZ", async () => {
  const u = render(agac());
  await waitFor(() => expect(u.getByTestId("tier").props.children).toBe("pro_plus"));
  mockSb.auth.getUser.mockRejectedValue(new Error("network"));
  mockSession = { email: "b@klinik.com" };
  await act(async () => { u.rerender(agac()); });
  await waitFor(() => expect(mockSb.auth.getUser.mock.calls.length).toBeGreaterThanOrEqual(2));
  await act(async () => { await Promise.resolve(); });
  expect(u.getByTestId("tier").props.children).not.toBe("pro_plus");
});

it("KARŞIT (D1.63 / #98 aynen): AYNI hesapta çevrimdışı okuma bilinen hakkı KORUR", async () => {
  const u = render(agac());
  await waitFor(() => expect(u.getByTestId("tier").props.children).toBe("pro_plus"));
  mockSb.auth.getUser.mockRejectedValue(new Error("network"));
  const once = mockSb.auth.getUser.mock.calls.length;
  mockSession = { email: "a@klinik.com" }; // aynı hesap, yeni nesne (jeton yenilendi)
  await act(async () => { u.rerender(agac()); });
  await waitFor(() => expect(mockSb.auth.getUser.mock.calls.length).toBeGreaterThan(once));
  await act(async () => { await Promise.resolve(); });
  expect(u.getByTestId("tier").props.children).toBe("pro_plus");
});
