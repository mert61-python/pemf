// Author: mertaygn, cglrgrkn
/**
 * Y339 (istem 69 GY2 bulgusu GY-B6, sahip 26-11): sahip ÜÇ profilde de aynı sayıları görüyordu (2 hasta / 20 seans / 24 AI = veteriner
 * dilimi). ÖLÇÜLEN KÖK NEDEN: istemci profil değişince `X-PEMF-Profil` başlığını DOĞRU güncelliyor (`setUserMode` → `setProfilBasligi`,
 * eşzamanlı) ve sunucu süzgeci başlığı doğru uyguluyor; ama kabuktaki profil menüsü (`AppShell`) profili YERİNDE değiştiriyor ve
 * `MainRouter` ekranı `key={rota}` ile kuruyordu → aynı rotada profil değişince ekran YENİDEN KURULMUYOR, listeler yalnız kurulumda
 * yüklendiği için önceki profilin listesi ekranda KALIYORDU. Düzeltme: ekran anahtarı profil + rota.
 * KAPI: gerçek `UserModeProvider` + gerçek `apiClient` başlığı; profil kabuk menüsünden değişince açık ekran YENİDEN kurulur ve
 * kurulurken giden başlık YENİ profildir (liste o başlıkla yeniden yüklenir). Profil seçimi KALICI DEĞİL kuralı değişmez.
 */
import React from "react";
import { act, fireEvent, render } from "@testing-library/react-native";

let mockAuth: any;
jest.mock("@/context/AuthContext", () => ({
  useAuth: () => mockAuth,
  AuthProvider: ({ children }: any) => children,
}));
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: { activeTreatment: { isActive: false }, coils: [] } }),
  LiveDataProvider: ({ children }: any) => children,
}));
jest.mock("@/context/EntitlementContext", () => ({ EntitlementProvider: ({ children }: any) => children }));
jest.mock("@/context/OperatorContext", () => ({
  useOperatorOptional: () => null,
  OperatorProvider: ({ children }: any) => children,
}));
// Kabuk: profil menüsü (gerçek AppShell'deki `setUserMode(p.mode)` ile AYNI çağrı) + içerik.
jest.mock("@/components/ui/AppShell", () => {
  const R = require("react");
  const { Pressable: P, Text: T, View: V } = require("react-native");
  const { useUserMode } = require("@/context/UserModeContext");
  return {
    AppShell: ({ children }: any) => {
      const { setUserMode } = useUserMode();
      return R.createElement(
        V,
        null,
        R.createElement(P, { onPress: () => setUserMode("researcher"), accessibilityLabel: "Araştırma profiline geç" },
          R.createElement(T, null, "profil-menusu")),
        R.createElement(P, { onPress: () => setUserMode("veterinarian"), accessibilityLabel: "Veteriner profiline geç" },
          R.createElement(T, null, "profil-menusu-vet")),
        children,
      );
    },
  };
});
const mockKurulumlar: (string | undefined)[] = [];
jest.mock("@/screens/DashboardScreen", () => {
  const R = require("react");
  const { Text: T } = require("react-native");
  return {
    DashboardScreen: () => {
      R.useEffect(() => {
        // Ekranın ilk isteği (liste yüklemesi) kurulumda gider — o an hangi profil başlığı gidiyor?
        mockKurulumlar.push(require("@/services/apiClient").authHeaders()["X-PEMF-Profil"]);
      }, []);
      return R.createElement(T, null, "pano");
    },
  };
});
jest.mock("@/screens/WelcomeScreen", () => {
  const R = require("react");
  const { Pressable: P, Text: T } = require("react-native");
  const { useUserMode } = require("@/context/UserModeContext");
  return {
    WelcomeScreen: () => {
      const { setUserMode } = useUserMode();
      return R.createElement(P, { onPress: () => setUserMode("veterinarian"), accessibilityLabel: "Veteriner seç" },
        R.createElement(T, null, "profil-secimi"));
    },
  };
});
jest.mock("@/screens/AuthScreen", () => {
  const R = require("react");
  const { Text: T } = require("react-native");
  return { AuthScreen: () => R.createElement(T, null, "giris-ekrani") };
});

import { AuthGate } from "@/PemfApp";

beforeEach(() => {
  mockKurulumlar.length = 0;
  mockAuth = { session: { email: "a@klinik.com", token: "t" }, loading: false, hesapEkleniyor: false, hesapEklemeVazgec: jest.fn() };
});

async function veterinerde() {
  const u = render(<AuthGate />);
  fireEvent.press(u.getByLabelText("Veteriner seç"));
  await act(async () => {});
  expect(u.queryByText("pano")).not.toBeNull();
  expect(mockKurulumlar).toEqual(["veterinarian"]);
  return u;
}

it("KRİTİK Y339: kabuk menüsünden profil değişince AÇIK ekran yeniden kurulur ve listesini YENİ profil başlığıyla ister", async () => {
  const u = await veterinerde();
  fireEvent.press(u.getByLabelText("Araştırma profiline geç"));
  await act(async () => {});
  expect(mockKurulumlar).toEqual(["veterinarian", "researcher"]);
  fireEvent.press(u.getByLabelText("Veteriner profiline geç"));
  await act(async () => {});
  expect(mockKurulumlar).toEqual(["veterinarian", "researcher", "veterinarian"]);
});

it("KARŞIT Y339: aynı profil yeniden seçilirse ekran yeniden KURULMAZ (gereksiz yükleme yok)", async () => {
  const u = await veterinerde();
  fireEvent.press(u.getByLabelText("Veteriner profiline geç"));
  await act(async () => {});
  expect(mockKurulumlar).toEqual(["veterinarian"]);
});
