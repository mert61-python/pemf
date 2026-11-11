/**
 * KP-4 B1 · src/screens/SettingsScreen.tsx (YEREL / telefon yolu, Platform.OS = "ios") — "Ağı Yeniden Tara" keşif merdiveni
 * REDDEDERSE (beklenmeyen hata: depolama / ağ katı istisnası) ekran takılı kalmaz:
 *  - durum "Bağlanamadı", bildirim "Ağ taraması başarısız" (info), WebSocket yeniden BAĞLANMAZ, adres alanı DEĞİŞMEZ;
 *  - "aranıyor" durumu kalkar → düğme yeniden basılabilir ve ikinci basış keşfi YENİDEN çağırır.
 * SAHTE: keşif servisinin `discoverBackend`i (tek sınır; ekranın kendi akışı gerçek) · bildirim · ekran bağlamları (KP2 düzeneği).
 */
const mockToast = jest.fn();
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: mockToast }) }));
jest.mock("@/context/UserModeContext", () => ({
  useUserMode: () => ({ setUserMode: jest.fn(), isExpert: true, isResearcher: false }),
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: null }) }));
const mockReconnect = jest.fn();
jest.mock("@/context/LiveDataContext", () => ({ useLiveData: () => ({ reconnect: mockReconnect, wsConnected: false }) }));
jest.mock("@/hooks/useTeardownGuard", () => ({ useTeardownGuard: () => async () => true }));
jest.mock("@supabase/supabase-js", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({ data: { session: null } }),
      onAuthStateChange: () => ({ data: { subscription: { unsubscribe: () => undefined } } }),
    },
    rpc: async () => ({ data: [], error: null }),
  }),
}));
jest.mock("@react-native-community/netinfo", () => ({
  __esModule: true,
  default: { fetch: async () => ({ type: "wifi", details: { ipAddress: "192.168.1.23" } }) },
}));

import React from "react";
import { Platform } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";
import i18n from "i18next";

import * as kesif from "@/services/discovery";
import { SettingsScreen } from "@/screens/SettingsScreen";
import { updateServiceConfig } from "@/services/config";

const t = (k: string, o?: Record<string, unknown>) => i18n.t(k, o as never) as unknown as string;
const orijinalOS = Platform.OS;
let kesifCasus: jest.SpyInstance;

beforeAll(() => {
  Object.defineProperty(Platform, "OS", { configurable: true, get: () => "ios" });
});
afterAll(() => {
  Object.defineProperty(Platform, "OS", { configurable: true, get: () => orijinalOS });
});
beforeEach(async () => {
  jest.clearAllMocks();
  await AsyncStorage.clear();
  updateServiceConfig("http://127.0.0.1:8000");
  (global as unknown as { fetch: unknown }).fetch = jest.fn(async () => ({
    ok: false, status: 404, headers: { get: () => "application/json" }, text: async () => "{}", json: async () => ({}),
  }));
  kesifCasus = jest.spyOn(kesif, "discoverBackend").mockRejectedValue(new Error("AsyncStorage okunamadı"));
});
afterEach(async () => {
  kesifCasus.mockRestore();
  updateServiceConfig("http://127.0.0.1:8000");
  await AsyncStorage.clear();
});

test("keşif REDDEDERSE: 'Bağlanamadı' + 'tarama başarısız' (info), WS yeniden bağlanmaz, düğme yeniden basılabilir", async () => {
  const u = render(<SettingsScreen />);
  await act(async () => {});
  await act(async () => {});
  const manuel = () => u.getByLabelText(t("ayarlar.baglanti.manuelEtiketi")).props.value;
  const adresOnce = manuel();
  const tara = () => u.getByText(t("ayarlar.baglanti.yenidenTara"));
  kesifCasus.mockClear();
  mockToast.mockClear();

  await act(async () => { fireEvent.press(tara()); });
  await waitFor(() => expect(mockToast).toHaveBeenCalledTimes(2));
  expect(mockToast.mock.calls).toEqual([
    [t("ayarlar.baglanti.taraniyor"), "info"],
    [t("ayarlar.baglanti.taramaBasarisiz"), "info"],
  ]);
  expect(kesifCasus).toHaveBeenCalledTimes(1);
  expect(u.getByText(t("ayarlar.baglanti.durumBaglanamadi"))).toBeTruthy();
  expect(mockReconnect).not.toHaveBeenCalled();
  expect(manuel()).toBe(adresOnce);

  // "aranıyor" kalktı: ikinci basış keşfi YENİDEN çağırır (takılı kalan düğme yok)
  await act(async () => { fireEvent.press(tara()); });
  await waitFor(() => expect(kesifCasus).toHaveBeenCalledTimes(2));
  await waitFor(() => expect(mockToast).toHaveBeenCalledTimes(4));
  expect(mockToast.mock.calls[3]).toEqual([t("ayarlar.baglanti.taramaBasarisiz"), "info"]);
});
