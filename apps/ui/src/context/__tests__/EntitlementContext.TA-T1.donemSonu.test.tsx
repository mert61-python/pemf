/**
 * TA T1 (Y292-1) · EntitlementContext uçtan uca: `abonelik_getir` satırındaki `current_period_end` bağlama taşınır ve
 * `useEntitlement().active` iptal / gecikmede ödenmiş dönem sonuna kadar AÇIK, sonra KAPALI. Sahte EN ALT katta: Supabase
 * istemcisi (`rpc().maybeSingle()`), oturum kancası, apiClient başlıkları.
 */
jest.mock("@/services/supabaseAuth", () => ({
  supabaseAuth: { auth: { getUser: jest.fn(), getSession: jest.fn() }, rpc: jest.fn(), from: jest.fn() },
}));
jest.mock("@/services/apiClient", () => ({ setEntitlementHeaders: jest.fn(), setAuthBearer: jest.fn() }));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "vet@klinik.com" } }) }));

import React from "react";
import { render, waitFor } from "@testing-library/react-native";
import { Text } from "react-native";
import { supabaseAuth } from "@/services/supabaseAuth";
import { EntitlementProvider, useEntitlement } from "@/context/EntitlementContext";

const mockSb = supabaseAuth as unknown as { auth: { getUser: jest.Mock; getSession: jest.Mock }; rpc: jest.Mock };

function Probe() {
  const { tier, active, realtime, research } = useEntitlement();
  return <Text testID="durum">{`${tier}|${active}|${realtime}|${research}`}</Text>;
}
const satir = (status: string, current_period_end: string | null) =>
  mockSb.rpc.mockReturnValue({
    maybeSingle: async () => ({
      data: { tier: "pro_plus", status, addons: ["research"], trial_ends_at: null, current_period_end },
      error: null,
      status: 200,
    }),
  });
const gun = (n: number) => new Date(Date.now() + n * 864e5).toISOString();

beforeEach(() => {
  jest.clearAllMocks();
  mockSb.auth.getUser.mockResolvedValue({ data: { user: { id: "u1", created_at: new Date().toISOString() } } });
  mockSb.auth.getSession.mockResolvedValue({ data: { session: { access_token: "jwt" } } });
});

it.each(["canceled", "past_due"])("KRİTİK: %s + dönem sürüyor → bağlam AKTİF (Pro+ gerçek-zamanlı + araştırma)", async (status) => {
  satir(status, gun(5));
  const u = render(<EntitlementProvider><Probe /></EntitlementProvider>);
  await waitFor(() => expect(u.getByTestId("durum").props.children).toBe("pro_plus|true|true|true"));
});

it.each([
  ["dönem bitti", gun(-1)],
  ["NULL", null],
])("KARŞIT: iptal + %s → bağlam KAPALI", async (_ad, son) => {
  satir("canceled", son);
  const u = render(<EntitlementProvider><Probe /></EntitlementProvider>);
  await waitFor(() => expect(u.getByTestId("durum").props.children).toBe("pro_plus|false|false|false"));
});
