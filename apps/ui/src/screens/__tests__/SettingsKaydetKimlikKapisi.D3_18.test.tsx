// Author: mertaygn, cglrgrkn
/**
 * D3.18 (B-6.28) — Ayarlar'daki "Ayarları Kaydet" de PEMF kimlik kapısından (`checkHealth`) geçer; "Test Et"in reddettiği adres taban
 * YAPILMAZ. Ölçülen (HEAD): kapı yalnız "Test Et"te vardı; "Kaydet" doğrulanmamış LAN adresini `updateServiceConfig` + kalıcı
 * `@pemf_server_address` yapıyor ve `/settings/` POST'unu (cihaz anahtarı / jetonlarla) oraya gönderiyordu.
 * GERÇEK SettingsScreen + GERÇEK `updateServiceConfig` / `serviceConfig`; sahte yalnız `checkHealth` sonucu ve istek katmanı.
 */
const mockCheckHealth = jest.fn();
const mockApiPost = jest.fn();
const asla = () => new Promise(() => {});

jest.mock("@/services/pairing", () => ({ cihazaBaglan: jest.fn(), eslesmeMesaji: jest.fn(() => "") }));
jest.mock("@/context/LiveDataContext", () => ({ useLiveData: () => ({ reconnect: jest.fn(), wsConnected: true }) }));
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: jest.fn() }) }));
jest.mock("@/context/UserModeContext", () => ({
  useUserMode: () => ({ setUserMode: jest.fn(), isExpert: true, isResearcher: false }),
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: null }) }));
jest.mock("@/hooks/useTeardownGuard", () => ({ useTeardownGuard: () => (f: unknown) => f }));
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(() => asla()),
  apiPost: (...a: unknown[]) => mockApiPost(...a),
  platformAlert: jest.fn(),
  platformConfirm: jest.fn(),
}));
jest.mock("@/services/discovery", () => ({
  checkHealth: (...a: unknown[]) => mockCheckHealth(...a),
  discoverBackend: jest.fn(() => asla()),
}));
jest.mock("@/services/supabaseAuth", () => ({ updateProfile: jest.fn() }));

import React from "react";
import { Platform } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";

import { SettingsScreen } from "@/screens/SettingsScreen";
import { serviceConfig } from "@/services/config";

const orijinalOS = Platform.OS;
beforeAll(() => { Object.defineProperty(Platform, "OS", { configurable: true, get: () => "ios" }); });
afterAll(() => { Object.defineProperty(Platform, "OS", { configurable: true, get: () => orijinalOS }); });
beforeEach(async () => {
  jest.clearAllMocks();
  await AsyncStorage.clear();
  mockApiPost.mockResolvedValue({ status: "success" });
});

async function kaydet(adres: string) {
  const u = render(<SettingsScreen />);
  await act(async () => {});
  fireEvent.changeText(u.getByLabelText("Manuel sunucu adresi"), adres);
  await act(async () => { fireEvent.press(u.getByText("Ayarları Kaydet")); });
  return u;
}

test("KRİTİK D3.18: kimlik kapısının reddettiği adres Kaydet'te TABAN YAPILMAZ ve /settings/ oraya gitmez", async () => {
  mockCheckHealth.mockResolvedValue(false);
  const once = serviceConfig.apiBaseUrl;
  const u = await kaydet("192.168.1.1");
  await waitFor(() => expect(mockCheckHealth).toHaveBeenCalledWith("192.168.1.1", null));
  expect(serviceConfig.apiBaseUrl).toBe(once);
  expect(await AsyncStorage.getItem("@pemf_server_address")).toBeNull();
  expect(mockApiPost).not.toHaveBeenCalledWith("/settings/", expect.anything(), expect.anything());
  expect(u.getByText("❌ Bu adreste bir PEMF cihazı bulunamadı.")).toBeTruthy();
});

test("KARŞIT D3.18: doğrulanan adres kaydedilir ve ayarlar gönderilir", async () => {
  mockCheckHealth.mockResolvedValue(true);
  await kaydet("192.168.1.50");
  await waitFor(() => expect(mockApiPost).toHaveBeenCalledWith("/settings/", expect.anything(), expect.anything()));
  expect(await AsyncStorage.getItem("@pemf_server_address")).toBe("192.168.1.50");
});
