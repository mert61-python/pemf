// Author: mertaygn, cglrgrkn
/**
 * D1.63 · B-6.7 — çevrimdışı hak koruması GERÇEK supabase-js davranışıyla çalışır; kapı refresh'i GERÇEKTEN koşturur.
 * ==================================================================================================================
 * ÖLÇÜLEN KUSUR (06 §B-6.7, 06-2 §3 — iki bağımsız mutasyon kör): `getUser()` ağ hatasında FIRLATMAZ,
 * `{data:{user:null}, error: AuthRetryableFetchError}` DÖNER. `if (!user) return defaultEntitlement()` bunu "kullanıcı yok"
 * sayıyordu → `catch` (UNKNOWN) gerçek istemcide hiç koşmuyor, internetsiz açılışta ücretli kullanıcı "Başlangıç/deneme"ye
 * düşüyordu. Eski kapı (`#98`) fırlatan sahte getUser kullanıyor ve yeniden render etmeden `mockSession` değiştiriyordu —
 * refresh hiç koşmadığı için her mutantta yeşildi. C1b-78: D1.87 çevrimdışı açılışı bu dalı ilk kez koşturur.
 *
 * GERÇEK: `EntitlementProvider`, supabase-js hata sınıfları (`AuthRetryableFetchError` ağ, `AuthApiError` / `AuthSessionMissingError`
 * ret). Sahte: Supabase istemcisinin yanıtları (postgrest ağ reddi = `status: 0`, kütüphanenin kendi biçimi).
 * ⚠️ MUTASYON: `e === UNKNOWN ? null : e` → `defaultEntitlement()`; `return UNKNOWN` → `defaultEntitlement()` → KIRMIZI.
 * `ENTITLEMENT_ENFORCED=false` — bu kapı gating AÇMAZ.
 */
jest.mock("@/services/supabaseAuth", () => ({
  supabaseAuth: {
    auth: { getUser: jest.fn(), getSession: jest.fn() },
    rpc: jest.fn(),
    from: jest.fn(),
  },
}));
jest.mock("@/services/apiClient", () => ({ setEntitlementHeaders: jest.fn(), setAuthBearer: jest.fn() }));
let mockSession: { email: string; cevrimdisi?: boolean } | null = null;
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: mockSession }) }));

import React from "react";
import { act, render, waitFor } from "@testing-library/react-native";
import { Text } from "react-native";
import { AuthApiError, AuthRetryableFetchError, AuthSessionMissingError } from "@supabase/supabase-js";
import { setEntitlementHeaders } from "@/services/apiClient";
import { supabaseAuth } from "@/services/supabaseAuth";
import { EntitlementProvider, useEntitlement } from "@/context/EntitlementContext";

const sb = supabaseAuth as unknown as { auth: { getUser: jest.Mock; getSession: jest.Mock }; rpc: jest.Mock; from: jest.Mock };
const basliklar = setEntitlementHeaders as jest.Mock;
let yenile: () => Promise<void> = async () => undefined;

function Probe() {
  const { tier, refresh } = useEntitlement();
  yenile = refresh;
  return <Text testID="tier">{tier}</Text>;
}
const kur = () => render(<EntitlementProvider><Probe /></EntitlementProvider>);
const KULLANICI = { data: { user: { id: "u1", created_at: new Date().toISOString() } }, error: null };
const satir = (yanit: { data: unknown; error: unknown; status: number }) =>
  sb.rpc.mockReturnValue({ maybeSingle: async () => yanit });
const UCRETLI = { tier: "pro_plus", status: "active", addons: ["research"], trial_ends_at: null, current_period_end: null };

beforeEach(() => {
  jest.clearAllMocks();
  mockSession = { email: "vet@klinik.com" };
  sb.auth.getUser.mockResolvedValue(KULLANICI);
  sb.auth.getSession.mockResolvedValue({ data: { session: { access_token: "jwt" } } });
  satir({ data: UCRETLI, error: null, status: 200 });
});

/** Çevrimiçi ilk okuma (pro_plus) → ağ düşer → refresh GERÇEKTEN koşar (getUser çağrı sayısıyla kanıt). */
async function ucretliSonraYenile(kur_: () => void) {
  const u = kur();
  await waitFor(() => expect(u.getByTestId("tier").props.children).toBe("pro_plus"));
  const once = sb.auth.getUser.mock.calls.length;
  kur_();
  await act(async () => {
    await yenile();
  });
  expect(sb.auth.getUser.mock.calls.length).toBe(once + 1); // aparat: refresh koştu (kör kapı değil)
  return u;
}

it("KRİTİK: getUser ağ hatasını DÖNDÜRÜNCE (AuthRetryableFetchError, fırlatmaz) ücretli tier KORUNUR", async () => {
  const u = await ucretliSonraYenile(() =>
    sb.auth.getUser.mockResolvedValue({ data: { user: null }, error: new AuthRetryableFetchError("Failed to fetch", 0) })
  );
  expect(u.getByTestId("tier").props.children).toBe("pro_plus");
  expect(basliklar).not.toHaveBeenCalledWith("baslangic", expect.anything());
});

it("KRİTİK: abonelik sorgusu ağda düşerse (postgrest status 0) ücretli tier KORUNUR", async () => {
  const u = await ucretliSonraYenile(() =>
    satir({ data: null, error: { message: "TypeError: Failed to fetch", details: "", hint: "", code: "" }, status: 0 })
  );
  expect(u.getByTestId("tier").props.children).toBe("pro_plus");
});

it("KRİTİK (D1.87/A-70): çevrimdışı açılan oturumda hak SORGULANMAZ, bilinen son hak korunur", async () => {
  const u = kur();
  await waitFor(() => expect(u.getByTestId("tier").props.children).toBe("pro_plus"));
  const once = sb.auth.getUser.mock.calls.length;
  sb.auth.getUser.mockResolvedValue({ data: { user: null }, error: new AuthSessionMissingError() });
  mockSession = { email: "vet@klinik.com", cevrimdisi: true };
  u.rerender(<EntitlementProvider><Probe /></EntitlementProvider>);
  await act(async () => {
    await yenile();
  });
  expect(sb.auth.getUser.mock.calls.length).toBe(once);
  expect(u.getByTestId("tier").props.children).toBe("pro_plus");
});

it.each([
  ["AuthApiError 401 (oturum geçersiz)", () => new AuthApiError("invalid JWT", 401, "bad_jwt")],
  ["AuthSessionMissingError (oturum yok)", () => new AuthSessionMissingError()],
])("KARŞIT: Supabase AÇIKÇA reddederse — %s — varsayılan hak", async (_ad, hata) => {
  const u = await ucretliSonraYenile(() => sb.auth.getUser.mockResolvedValue({ data: { user: null }, error: hata() }));
  expect(u.getByTestId("tier").props.children).toBe("baslangic");
});

it("KARŞIT: abonelik satırı YOKSA (ağ sağlam, status 200) varsayılan deneme hakkı", async () => {
  const u = await ucretliSonraYenile(() => satir({ data: null, error: null, status: 200 }));
  expect(u.getByTestId("tier").props.children).toBe("baslangic");
});
