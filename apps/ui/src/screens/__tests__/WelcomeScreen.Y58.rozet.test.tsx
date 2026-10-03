// Author: mertaygn, cglrgrkn
/**
 * Y58 (sahip, S-E5) — Karşılama ekranı: hak DOĞRULANAMADIYSA rozet "Abonelik doğrulanamadı (internet yok)" der; yer tutucu
 * hakka dayalı "Başlangıç"/deneme, "Gerçek-zamanlı" rozeti ve "Araştırma eklentisi gerektirir" notu GÖSTERİLMEZ.
 * Bağlam tarafı (gerçek sağlayıcı): `context/__tests__/EntitlementContext.Y58.dogrulanamadi.test.tsx`.
 */
jest.mock("@/services/apiClient", () => ({
  platformAlert: jest.fn(),
  platformConfirm: jest.fn(async () => true),
  apiGet: jest.fn(async () => null),
  apiPost: jest.fn(async () => null),
}));
jest.mock("@/services/emergencyStop", () => ({
  performEmergencyStop: jest.fn(async () => ({ confirmed: true })),
  EMERGENCY_STOP_UNCONFIRMED_TITLE: "UYARI",
  EMERGENCY_STOP_UNCONFIRMED_BODY: "govde",
}));
jest.mock("@/components/ui/AuroraBackground", () => ({ AuroraBackground: () => null }));
jest.mock("@/components/ui/GlobalEmergencyStop", () => ({ GlobalEmergencyStop: () => null }));
jest.mock("@/components/ui/EstopMandalBandi", () => ({ EstopMandalBandi: () => null }));
jest.mock("expo-blur", () => ({ BlurView: () => null }));
jest.mock("expo-linear-gradient", () => ({ LinearGradient: () => null }));
jest.mock("react-native-safe-area-context", () => ({
  useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
}));
jest.mock("@/hooks/useResponsive", () => ({
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  useResponsive: () => require("@/hooks/__tests__/responsiveMock").sahteMasaustu(),
}));
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: { coils: [], activeTreatment: { isActive: false } }, donanimBelirsiz: false }),
}));
jest.mock("@/context/UserModeContext", () => ({ useUserMode: () => ({ userMode: null, setUserMode: jest.fn() }) }));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "op@klinik.com" }, logout: jest.fn() }) }));
let mockHak: Record<string, unknown> = {};
jest.mock("@/context/EntitlementContext", () => ({ useEntitlement: () => mockHak }));

import React from "react";
import { render } from "@testing-library/react-native";
import { WelcomeScreen } from "@/screens/WelcomeScreen";

const YER_TUTUCU = { tier: "baslangic", trialing: true, trialDaysLeft: 14, realtime: true, research: false };

it("KRİTİK: hak doğrulanamadıysa rozet 'Abonelik doğrulanamadı (internet yok)'; Başlangıç/deneme/gerçek-zamanlı/eklenti notu YOK", () => {
  mockHak = { ...YER_TUTUCU, dogrulanamadi: true };
  const u = render(<WelcomeScreen />);
  expect(u.getByText("Abonelik doğrulanamadı (internet yok)")).toBeTruthy();
  expect(u.queryByText(/Deneme · |Başlangıç/)).toBeNull();
  expect(u.queryByText("Gerçek-zamanlı")).toBeNull();
  expect(u.queryByText("Araştırma eklentisi gerektirir")).toBeNull();
});

it("KARŞIT: hak BİLİNİYORSA rozet bugünkü gibi (deneme / tier) ve notlar görünür", () => {
  mockHak = { ...YER_TUTUCU, dogrulanamadi: false };
  const u = render(<WelcomeScreen />);
  expect(u.getByText("Deneme · 14 gün kaldı")).toBeTruthy();
  expect(u.getByText("Gerçek-zamanlı")).toBeTruthy();
  expect(u.getByText("Araştırma eklentisi gerektirir")).toBeTruthy();
});
