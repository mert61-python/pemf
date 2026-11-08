/**
 * KP-3 C · WelcomeScreen profil kartları — DAVRANIŞ iddiası: her kart KENDİ profilini seçer (ev sahibi → pet_owner, veteriner →
 * veterinarian, araştırma → researcher); yanlış profile geçiş, o profile ait olmayan ekranları (ör. bobin kontrolü) açardı.
 * SAHTE: bağlamlar (girdi: profil seçici kaydedilir), görsel süsler (aurora / ACİL DURDUR bandı / dil seçici — bu dosyanın konusu
 * değil), güvenli alan, kurulu profiller (hepsi kurulu). GERÇEK: WelcomeScreen.
 */
const mockSec = jest.fn();
jest.mock("@/context/UserModeContext", () => ({ useUserMode: () => ({ setUserMode: mockSec }) }));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "dr@klinik.com" }, logout: jest.fn() }) }));
jest.mock("@/context/EntitlementContext", () => ({
  useEntitlement: () => ({ tier: "pro", trialing: false, trialDaysLeft: 0, realtime: true, research: true, dogrulanamadi: false }),
}));
jest.mock("@/services/installedProfiles", () => ({ installedModes: () => null }));
jest.mock("@/hooks/useTeardownGuard", () => ({ useTeardownGuard: () => (f: () => unknown) => f }));
jest.mock("@/components/ui/AuroraBackground", () => ({ AuroraBackground: () => null }));
jest.mock("@/components/ui/EstopMandalBandi", () => ({ EstopMandalBandi: () => null }));
jest.mock("@/components/ui/GlobalEmergencyStop", () => ({ GlobalEmergencyStop: () => null }));
jest.mock("@/components/domain/DilSecici", () => ({ DilSecici: () => null }));
jest.mock("react-native-safe-area-context", () => ({ useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }) }));
jest.mock("@/hooks/useResponsive", () => ({
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  useResponsive: () => require("@/hooks/__tests__/responsiveMock").sahteMasaustu(),
}));

import React from "react";
import { fireEvent, render } from "@testing-library/react-native";
import i18n from "i18next";
import { WelcomeScreen } from "@/screens/WelcomeScreen";

const T = (k: string): string => (i18n.t as unknown as (k: string) => string)(k);

it("her profil kartı kendi profilini seçer", () => {
  const u = render(<WelcomeScreen />);
  fireEvent.press(u.getByLabelText(T("giris.hosGeldin.sahipProfilEtiketi")));
  fireEvent.press(u.getByLabelText(T("giris.hosGeldin.veterinerProfilEtiketi")));
  fireEvent.press(u.getByLabelText(T("giris.hosGeldin.arastirmaProfilEtiketi")));
  expect(mockSec.mock.calls.map((c) => c[0])).toEqual(["pet_owner", "veterinarian", "researcher"]);
});
