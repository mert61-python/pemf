/**
 * T-e (Tezgâh-2 #8, Y195) — Sistem Durumu: "İnternet Bağlantısı" ölçülmemişken "Bilinmiyor" (kırmızı "Kapalı" DEĞİL); ESP BİLİNÇLİ
 * kapalıyken "Cihaz Köprüsü" "Devre dışı" (gri). TR + EN.
 *
 * ÖLÇÜLEN KUSUR (Tezgâh-2): ağ izleme servisi yokken İnternet "Kapalı" (kırmızı), ESP kapalıyken Cihaz Köprüsü "Kapalı" (kırmızı) —
 * ölçülmemiş / bilinçli kapalı şey arıza gibi gösteriliyordu. Testler ÇİZİLEN değeri ölçer.
 */
import { act, render, waitFor } from "@testing-library/react-native";
import i18n from "i18next";

const mockGet = jest.fn();
let mockCanli: { snapshot: Record<string, unknown>; wsConnected: boolean };
jest.mock("@/services/apiClient", () => ({ apiGet: (...a: unknown[]) => mockGet(...a) }));
jest.mock("@/context/LiveDataContext", () => ({ useLiveData: () => mockCanli }));

import { GatewayStatusPanel } from "@/components/domain/GatewayStatusPanel";

const durum = (ek: Record<string, unknown> = {}) => ({
  mqttConnected: false,
  brokerRunning: false,
  bridgeConnected: false,
  networkOnline: false,
  hotspotActive: false,
  ...ek,
});

beforeEach(() => {
  mockGet.mockReset();
  mockCanli = { snapshot: { mqtt: "online", gateway: "offline", stm: "online" }, wsConnected: true };
});
afterEach(async () => {
  await act(async () => {
    await i18n.changeLanguage("tr");
  });
});

const deger = async (ekran: ReturnType<typeof render>, id: string) =>
  waitFor(() => ekran.getByTestId(id).props.children as string);

test("KRITIK: uc yanit vermezse (servis yok) Internet 'Bilinmiyor' — 'Kapalı' DEGIL", async () => {
  mockGet.mockResolvedValue(null);
  const ekran = render(<GatewayStatusPanel />);
  await waitFor(() => expect(mockGet).toHaveBeenCalled());
  expect(await deger(ekran, "sistem-durumu-internet")).toBe("Bilinmiyor");
});

test("KRITIK: backend 'olculmedi' derse Internet 'Bilinmiyor'", async () => {
  mockGet.mockResolvedValue(durum({ internetBilinmiyor: true }));
  const ekran = render(<GatewayStatusPanel />);
  await waitFor(() => expect(mockGet).toHaveBeenCalled());
  expect(await deger(ekran, "sistem-durumu-internet")).toBe("Bilinmiyor");
});

test("KARSIT: olculmus internet yok → 'Kapalı', var → 'Aktif'", async () => {
  mockGet.mockResolvedValue(durum({ internetBilinmiyor: false, networkOnline: false }));
  const ekran = render(<GatewayStatusPanel />);
  await waitFor(() => expect(ekran.getByTestId("sistem-durumu-internet").props.children).toBe("Kapalı"));
  mockGet.mockResolvedValue(durum({ internetBilinmiyor: false, networkOnline: true }));
  const ekran2 = render(<GatewayStatusPanel />);
  await waitFor(() => expect(ekran2.getByTestId("sistem-durumu-internet").props.children).toBe("Aktif"));
});

test("KRITIK: ESP bilincli kapaliyken Cihaz Koprusu 'Devre dışı' (kirmizi 'Kapalı' DEGIL)", async () => {
  mockGet.mockResolvedValue(durum({ espEtkin: false }));
  const ekran = render(<GatewayStatusPanel />);
  await waitFor(() => expect(mockGet).toHaveBeenCalled());
  await waitFor(() => expect(ekran.getByTestId("sistem-durumu-kopru").props.children).toBe("Devre dışı"));
});

test("KRITIK: eski backend (espEtkin yok) — canli durum mqtt=devre_disi da ESP kapali demektir", async () => {
  mockCanli = { snapshot: { mqtt: "devre_disi", gateway: "offline", stm: "online" }, wsConnected: true };
  mockGet.mockResolvedValue(durum());
  const ekran = render(<GatewayStatusPanel />);
  expect(await deger(ekran, "sistem-durumu-kopru")).toBe("Devre dışı");
});

test("KARSIT: ESP etkinken kopru kapaliysa 'Kapalı'; acikken 'Aktif'", async () => {
  mockGet.mockResolvedValue(durum({ espEtkin: true }));
  const ekran = render(<GatewayStatusPanel />);
  await waitFor(() => expect(mockGet).toHaveBeenCalled());
  await waitFor(() => expect(ekran.getByTestId("sistem-durumu-kopru").props.children).toBe("Kapalı"));
  mockCanli = { snapshot: { mqtt: "devre_disi", gateway: "online", stm: "online" }, wsConnected: true };
  const ekran2 = render(<GatewayStatusPanel />);
  expect(await deger(ekran2, "sistem-durumu-kopru")).toBe("Aktif");
});

test("EN: 'Unknown' / 'Disabled'", async () => {
  await act(async () => {
    await i18n.changeLanguage("en");
  });
  mockGet.mockResolvedValue(durum({ espEtkin: false, internetBilinmiyor: true }));
  const ekran = render(<GatewayStatusPanel />);
  await waitFor(() => expect(ekran.getByTestId("sistem-durumu-kopru").props.children).toBe("Disabled"));
  expect(ekran.getByTestId("sistem-durumu-internet").props.children).toBe("Unknown");
});
