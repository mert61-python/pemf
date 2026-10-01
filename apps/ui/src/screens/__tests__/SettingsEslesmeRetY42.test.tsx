// Author: mertaygn, cglrgrkn
/**
 * AYARLAR → UZAK CİHAZA BAĞLAN: kod reddi metni bağlantı durumuna göre (Y42, 2026-10-01).
 *
 * A-52 ("bağlantı önceki cihazda kaldı") Ayarlar'dan bir cihaza BAĞLIYKEN başka cihazın kodu girilince doğrudur;
 * uygulama çevrimdışıyken aynı cümle var olmayan bir bağlantıyı iddia eder. Ekran `eslesmeMesaji`'na GERÇEK
 * bağlantı durumunu (`wsConnected`) geçmeli. Metnin kendisi `services/__tests__/eslesmeRetMetniY42.test.ts`'te.
 */
const mockCihazaBaglan = jest.fn();
const mockMesaj = jest.fn((..._a: unknown[]) => "mesaj");
let mockWsBagli = true;
const mockToast = jest.fn();
const asla = () => new Promise(() => {}); // ekranın açılış istekleri bu testin konusu değil → hiç çözülmez

jest.mock("@/services/pairing", () => ({
  cihazaBaglan: (...a: unknown[]) => mockCihazaBaglan(...a),
  eslesmeMesaji: (...a: unknown[]) => mockMesaj(...a),
}));
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ reconnect: jest.fn(), wsConnected: mockWsBagli }),
}));
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: mockToast }) }));
jest.mock("@/context/UserModeContext", () => ({
  useUserMode: () => ({ setUserMode: jest.fn(), isExpert: true, isResearcher: false }),
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: null }) }));
jest.mock("@/hooks/useTeardownGuard", () => ({ useTeardownGuard: () => (f: unknown) => f }));
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(() => asla()),
  apiPost: jest.fn(() => asla()),
  platformAlert: jest.fn(),
  platformConfirm: jest.fn(),
}));
jest.mock("@/services/discovery", () => ({ checkHealth: jest.fn(() => asla()), discoverBackend: jest.fn(() => asla()) }));
jest.mock("@/services/supabaseAuth", () => ({ updateProfile: jest.fn() }));

import React from "react";
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";

import { SettingsScreen } from "@/screens/SettingsScreen";

const KOD_ALANI = "Uzak cihaza bağlan: eşleştirme kodu veya cihaz kimliği";

async function kodReddet() {
  mockCihazaBaglan.mockResolvedValue({ durum: "kod_reddedildi" });
  const u = render(<SettingsScreen />);
  await act(async () => {});
  fireEvent.changeText(u.getByLabelText(KOD_ALANI), "MVPDDN");
  fireEvent.press(u.getByText("Cihaza Bağlan"));
  await waitFor(() => expect(mockToast).toHaveBeenCalledWith("mesaj", "error"));
  return u;
}

beforeEach(() => {
  jest.clearAllMocks();
  mockWsBagli = true;
});

describe("Y42 — Ayarlar'da kod reddi", () => {
  it("KRİTİK: bir cihaza BAĞLIYKEN A-52 bağlamı geçilir (bağlantı önceki cihazda kaldı)", async () => {
    await kodReddet();
    expect(mockMesaj).toHaveBeenCalledWith({ durum: "kod_reddedildi" }, { oncekiCihazaBagli: true });
  });

  it("KRİTİK: ÇEVRİMDIŞIYKEN 'önceki cihaz' bağlamı geçilmez", async () => {
    mockWsBagli = false;
    await kodReddet();
    expect(mockMesaj).toHaveBeenCalledWith({ durum: "kod_reddedildi" }, { oncekiCihazaBagli: false });
  });
});
