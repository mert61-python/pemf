// Author: mertaygn, cglrgrkn
/**
 * Y58 (sahip, S-E5) — ilk açılış İNTERNETSİZ ve bilinen son hak YOKSA: rozet "Abonelik doğrulanamadı (internet yok)" der;
 * "Başlangıç"/deneme GÖSTERİLMEZ, `X-PEMF-Tier` (baslangic dahil) GÖNDERİLMEZ, cihaza hiçbir şey YAZILMAZ; internet
 * gelince gerçek hak kendiliğinden görünür.
 * ======================================================================================================================
 * ÖLÇÜLEN KUSUR (D1.63 sonrası, `onceki`): bilinen hak yokken ağ hatası (UNKNOWN) varsayılan `defaultEntitlement()`ı yer
 * tutucu olarak bırakıyordu → rozet "Deneme · 14 gün kaldı" (ücretli kullanıcıya uydurma "Başlangıç" denemesi) ve hak bir
 * daha SORGULANMIYORDU (yalnız oturum değişince) — internet gelse de yeniden başlatmaya dek uydurma rozet kalıyordu.
 *
 * GERÇEK: `EntitlementProvider`, `planRozetiMetni`, supabase-js hata sınıfları. Sahte: Supabase istemcisinin yanıtları.
 * `ENTITLEMENT_ENFORCED=false` — yalnız gösterim (gating açılmaz).
 */
jest.mock("@/services/supabaseAuth", () => ({
  supabaseAuth: {
    auth: { getUser: jest.fn(), getSession: jest.fn() },
    rpc: jest.fn(),
    from: jest.fn(),
  },
}));
jest.mock("@/services/apiClient", () => ({ setEntitlementHeaders: jest.fn(), setAuthBearer: jest.fn() }));
const mockDepo = { setItem: jest.fn(async () => undefined), getItem: jest.fn(async () => null) };
jest.mock("@react-native-async-storage/async-storage", () => ({ __esModule: true, default: mockDepo, ...mockDepo }));
let mockSession: { email: string; cevrimdisi?: boolean } | null = null;
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: mockSession }) }));

import React from "react";
import { act, render, waitFor } from "@testing-library/react-native";
import { Text } from "react-native";
import { AuthRetryableFetchError } from "@supabase/supabase-js";
import { setEntitlementHeaders } from "@/services/apiClient";
import { supabaseAuth } from "@/services/supabaseAuth";
import { EntitlementProvider, useEntitlement, HAK_YENIDEN_DENEME_MS } from "@/context/EntitlementContext";
import { planRozetiMetni, abonelikDogrulanamadi } from "@/config/entitlement";

const sb = supabaseAuth as unknown as { auth: { getUser: jest.Mock; getSession: jest.Mock }; rpc: jest.Mock; from: jest.Mock };
const basliklar = setEntitlementHeaders as jest.Mock;

function Rozet() {
  const { tier, trialing, trialDaysLeft, dogrulanamadi } = useEntitlement();
  return <Text testID="rozet">{planRozetiMetni({ dogrulanamadi, trialing, trialDaysLeft, tier })}</Text>;
}
const kur = () =>
  render(
    <EntitlementProvider>
      <Rozet />
    </EntitlementProvider>
  );
const rozet = (u: ReturnType<typeof kur>) => String(u.getByTestId("rozet").props.children);
const AG_HATASI = { data: { user: null }, error: new AuthRetryableFetchError("Failed to fetch", 0) };
const KULLANICI = { data: { user: { id: "u1", created_at: new Date().toISOString() } }, error: null };
const UCRETLI = { tier: "pro", status: "active", addons: [], trial_ends_at: null, current_period_end: null };
const satir = (yanit: { data: unknown; error: unknown; status: number }) =>
  sb.rpc.mockReturnValue({ maybeSingle: async () => yanit });

beforeEach(() => {
  jest.clearAllMocks();
  jest.useRealTimers();
  mockSession = { email: "vet@klinik.com" };
  sb.auth.getSession.mockResolvedValue({ data: { session: null } });
  satir({ data: UCRETLI, error: null, status: 200 });
});

it("KRİTİK: internetsiz İLK açılış → rozet 'doğrulanamadı', Başlangıç/deneme YOK, X-PEMF-Tier YOK, cihaza yazım YOK", async () => {
  sb.auth.getUser.mockResolvedValue(AG_HATASI);
  const u = kur();
  await waitFor(() => expect(sb.auth.getUser).toHaveBeenCalled());
  await waitFor(() => expect(rozet(u)).toBe(abonelikDogrulanamadi()));
  expect(rozet(u)).not.toMatch(/Başlangıç|Deneme|gün kaldı/);
  expect(basliklar.mock.calls.filter(([t]) => t)).toEqual([]); // hiçbir tier başlığı (baslangic dahil) kurulmadı
  expect(mockDepo.setItem).not.toHaveBeenCalled();
});

it("KRİTİK: internet GELİNCE gerçek hak kendiliğinden görünür (yeniden başlatma / oturum değişimi olmadan)", async () => {
  jest.useFakeTimers();
  sb.auth.getUser.mockResolvedValue(AG_HATASI);
  const u = kur();
  await act(async () => {
    await Promise.resolve();
  });
  await waitFor(() => expect(rozet(u)).toBe(abonelikDogrulanamadi()));
  sb.auth.getUser.mockResolvedValue(KULLANICI); // internet geldi
  await act(async () => {
    jest.advanceTimersByTime(HAK_YENIDEN_DENEME_MS);
  });
  await act(async () => {
    await Promise.resolve();
  });
  await waitFor(() => expect(rozet(u)).toBe("Pro"));
  expect(basliklar).toHaveBeenLastCalledWith("pro", []);
});

it("KARŞIT: hak BİLİNİYORKEN ağ düşerse bilinen hak korunur (D1.63), 'doğrulanamadı' DENMEZ", async () => {
  sb.auth.getUser.mockResolvedValue(KULLANICI);
  const u = kur();
  await waitFor(() => expect(rozet(u)).toBe("Pro"));
  sb.auth.getUser.mockResolvedValue(AG_HATASI);
  await act(async () => {
    mockSession = { email: "vet@klinik.com" }; // yeni oturum nesnesi → refresh yeniden koşar
    u.rerender(
      <EntitlementProvider>
        <Rozet />
      </EntitlementProvider>
    );
  });
  await waitFor(() => expect(sb.auth.getUser).toHaveBeenCalledTimes(2));
  expect(rozet(u)).toBe("Pro");
});

it("KARŞIT: çevrimiçi ve abonelik satırı YOK → gerçek varsayılan deneme gösterilir (doğrulanamadı değil)", async () => {
  sb.auth.getUser.mockResolvedValue(KULLANICI);
  satir({ data: null, error: null, status: 200 });
  const u = kur();
  await waitFor(() => expect(rozet(u)).toMatch(/Deneme · \d+ gün kaldı/));
});

it("KRİTİK (1-F inceleme): A'nın hakkı BİLİNİYORKEN A ÇIKAR, B internetsiz GİRER → B için 'doğrulanamadı' (deneme DEĞİL)", async () => {
  // Çıkış "bilinen hak" işaretini sıfırlamazsa B'nin ağ hatası "bilinen hak korunur" (D1.63) sayılır; çıkış hakkı zaten
  // varsayılana döndürdüğü için B'ye uydurma "Başlangıç · deneme" gösterilir (Y58'in kapattığı kusur, ikinci yoldan).
  sb.auth.getUser.mockResolvedValue(KULLANICI);
  const u = kur();
  await waitFor(() => expect(rozet(u)).toBe("Pro"));
  await act(async () => {
    mockSession = null; // A çıkış yaptı
    u.rerender(
      <EntitlementProvider>
        <Rozet />
      </EntitlementProvider>
    );
  });
  sb.auth.getUser.mockResolvedValue(AG_HATASI); // B internetsiz
  await act(async () => {
    mockSession = { email: "baska@klinik.com" };
    u.rerender(
      <EntitlementProvider>
        <Rozet />
      </EntitlementProvider>
    );
  });
  await waitFor(() => expect(sb.auth.getUser).toHaveBeenCalledTimes(2));
  await waitFor(() => expect(rozet(u)).toBe(abonelikDogrulanamadi()));
  expect(rozet(u)).not.toMatch(/Başlangıç|Deneme|gün kaldı|Pro/);
});
