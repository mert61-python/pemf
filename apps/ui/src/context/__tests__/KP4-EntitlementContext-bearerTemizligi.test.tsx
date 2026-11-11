/**
 * KP-4 B1 · src/context/EntitlementContext.tsx — backend isteklerine eklenen Supabase erişim jetonu (Bearer): oturum jetonu OKUNAMAZSA
 * (getSession fırlatır — depolama / istemci hatası) BAYAT jeton isteklerde KALMAZ, Authorization başlığı düşer. Aynı hesabın oturum nesnesi
 * yenilenince (jeton döndü) hak yeniden okunur; hesap DEĞİŞMEDİĞİ için başlığı temizleyen tek yol bu yakalamadır.
 * GERÇEK: EntitlementProvider, apiClient (`authHeaders` / `setAuthBearer`). SAHTE (en alt kat): Supabase istemcisi, cihaz deposu;
 * oturum bağlamı girdi.
 */
jest.mock("@/services/supabaseAuth", () => ({
  supabaseAuth: {
    auth: { getUser: jest.fn(), getSession: jest.fn() },
    rpc: jest.fn(),
    from: jest.fn(),
  },
}));
const mockDepo = { setItem: jest.fn(async () => undefined), getItem: jest.fn(async () => null) };
jest.mock("@react-native-async-storage/async-storage", () => ({ __esModule: true, default: mockDepo, ...mockDepo }));
let mockSession: { email: string } | null = null;
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: mockSession }) }));

import React from "react";
import { Text } from "react-native";
import { render, waitFor } from "@testing-library/react-native";
import { authHeaders, setAuthBearer } from "@/services/apiClient";
import { supabaseAuth } from "@/services/supabaseAuth";
import { EntitlementProvider } from "@/context/EntitlementContext";

const sb = supabaseAuth as unknown as { auth: { getUser: jest.Mock; getSession: jest.Mock }; rpc: jest.Mock };
const KULLANICI = { data: { user: { id: "u1", created_at: new Date().toISOString() } }, error: null };
const UCRETLI = { tier: "pro", status: "active", addons: [], trial_ends_at: null, current_period_end: null };

beforeEach(() => {
  jest.clearAllMocks();
  setAuthBearer(null);
  sb.auth.getUser.mockResolvedValue(KULLANICI);
  sb.rpc.mockReturnValue({ maybeSingle: async () => ({ data: UCRETLI, error: null, status: 200 }) });
});

const agac = () => (
  <EntitlementProvider>
    <Text>x</Text>
  </EntitlementProvider>
);

it("KRİTİK: aynı hesapta oturum yenilenip jeton okunamazsa BAYAT Bearer isteklerde KALMAZ", async () => {
  mockSession = { email: "a@klinik.com" };
  sb.auth.getSession.mockResolvedValue({ data: { session: { access_token: "JWT-A" } } });
  const u = render(agac());
  await waitFor(() => expect(authHeaders().Authorization).toBe("Bearer JWT-A"));

  mockSession = { email: "a@klinik.com" }; // aynı hesap, YENİ oturum nesnesi (jeton döndü)
  sb.auth.getSession.mockRejectedValue(new Error("depolama okunamadı"));
  u.rerender(agac());
  await waitFor(() => expect(sb.auth.getSession).toHaveBeenCalledTimes(2));
  await waitFor(() => expect(authHeaders().Authorization).toBeUndefined());
});
