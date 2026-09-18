// Author: mertaygn, cglrgrkn
/**
 * EntitlementContext — bu denetimde düzeltilen iki davranış.
 *
 * ⚠️ BİLİNÇLİ KARAR: `ENTITLEMENT_ENFORCED=false` (ödeme öncesi açık erişim). Bu testler
 *    gating AÇMAZ; yalnız hakkın DOĞRU kullanıcıya ait olmasını ve çevrimdışıyken kaybolmamasını
 *    kilitler.
 *
 *   #47 Nesil guard'ı: uçuştaki `refresh`, çıkıştan/hesap değişiminden SONRA çözülünce önceki
 *       kullanıcının tier'ını ve X-PEMF-Tier header'ını geri yüklüyordu.
 *   #98 Supabase erişilemezse hak SIFIRLANMAZ (internetsiz klinikte ücretli kullanıcı her
 *       açılışta "Deneme · 14 gün kaldı"ya düşüyordu).
 */
// NOT: jest.mock fabrikaları import'ların ÜSTÜNE hoist edilir → fabrika içinde dış bir `const`a
// atıfta bulunmak (o const henüz başlatılmamış olduğundan) mock'u `undefined` yapar. Bu yüzden
// sahte nesne fabrikanın İÇİNDE kurulur, referansı sonra import ile alınır.
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
import { render, act, waitFor } from "@testing-library/react-native";
import { Text } from "react-native";
import { setEntitlementHeaders } from "@/services/apiClient";
import { supabaseAuth } from "@/services/supabaseAuth";
import { EntitlementProvider, useEntitlement } from "@/context/EntitlementContext";

const mockSb = supabaseAuth as unknown as {
  auth: { getUser: jest.Mock; getSession: jest.Mock };
  from: jest.Mock;
};
const mockHeaders = setEntitlementHeaders as jest.Mock;

function Probe() {
  const { tier } = useEntitlement();
  return <Text testID="tier">{tier}</Text>;
}
const setup = () => render(<EntitlementProvider><Probe /></EntitlementProvider>);

/** `supabase.from(...).select(...).eq(...).maybeSingle()` zincirini taklit et. */
const mockRow = (data: unknown, error: unknown = null) => {
  mockSb.from.mockReturnValue({
    select: () => ({ eq: () => ({ maybeSingle: async () => ({ data, error }) }) }),
  });
};

beforeEach(() => {
  jest.clearAllMocks();
  mockSession = { email: "vet@klinik.com" };
  mockSb.auth.getUser.mockResolvedValue({ data: { user: { id: "u1", created_at: new Date().toISOString() } } });
  mockSb.auth.getSession.mockResolvedValue({ data: { session: { access_token: "jwt" } } });
  mockRow({ tier: "pro_plus", status: "active", addons: ["research"], trial_ends_at: null, current_period_end: null });
});

it("abonelik satırı okunur ve tier uygulanır", async () => {
  const { getByTestId } = setup();
  await waitFor(() => expect(getByTestId("tier").props.children).toBe("pro_plus"));
  expect(mockHeaders).toHaveBeenCalledWith("pro_plus", ["research"]);
});

it("KRİTİK #98: Supabase ERİŞİLEMEZSE ücretli tier SIFIRLANMAZ (internetsiz klinik)", async () => {
  const { getByTestId } = setup();
  await waitFor(() => expect(getByTestId("tier").props.children).toBe("pro_plus"));

  // Ağ koptu → sonraki refresh patlıyor.
  mockSb.auth.getUser.mockRejectedValue(new Error("network"));
  mockSession = { email: "vet@klinik.com" };          // aynı oturum, yeniden tetikle
  await act(async () => { await Promise.resolve(); });

  expect(getByTestId("tier").props.children).toBe("pro_plus"); // "baslangic"a DÜŞMEDİ
});

it("KRİTİK #47: ÇIKIŞ sonrası çözülen bayat refresh önceki kullanıcının hakkını GERİ YÜKLEMEZ", async () => {
  // İlk okuma asılı kalsın; biz bu arada çıkış yapacağız.
  let release: (v: unknown) => void = () => undefined;
  mockSb.auth.getUser.mockReturnValue(new Promise((r) => { release = r; }));

  const { getByTestId, rerender } = setup();

  // Çıkış: session null → provider varsayılana döner ve header'ları temizler.
  mockSession = null;
  rerender(<EntitlementProvider><Probe /></EntitlementProvider>);
  await waitFor(() => expect(getByTestId("tier").props.children).toBe("baslangic"));
  mockHeaders.mockClear();

  // Şimdi ESKİ istek çözülüyor (pro_plus). Nesil guard'ı bunu yok saymalı.
  await act(async () => {
    release({ data: { user: { id: "u1", created_at: new Date().toISOString() } } });
    await Promise.resolve(); await Promise.resolve();
  });

  expect(getByTestId("tier").props.children).toBe("baslangic");        // hak geri gelmedi
  expect(mockHeaders).not.toHaveBeenCalledWith("pro_plus", expect.anything()); // header sızmadı
});

it("bilinmeyen tier/status güvenli varsayılana düşer (savunmacı şekil doğrulaması)", async () => {
  mockRow({ tier: "altin_paket", status: "kim_bilir", addons: "dizi-degil", trial_ends_at: null, current_period_end: null });
  const { getByTestId } = setup();
  await waitFor(() => expect(getByTestId("tier").props.children).toBe("baslangic"));
});
