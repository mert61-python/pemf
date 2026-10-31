// Author: mertaygn, cglrgrkn
/**
 * BE 3b · Y231 — Sistem Durumu'ndaki hotspot satırının adı NE olduğunu söyler: "Cihaz Wi-Fi'si (PEMF-Gateway)" (telefonların bağlandığı PC
 * hotspot'u). Sahip 31.10: "kablosuz bağlantı neden kırmızı yanıyor her şey bağlı" — satır doğruydu (Windows PEMF-Gateway'i ~4 dk'da kapatıyordu),
 * ama adı ("Kablosuz Bağlantı") neyin kapalı olduğunu söylemiyordu (PC'nin kendi Wi-Fi'si sanıldı). TR + EN; değer gösterimi aynen.
 */
import { act, render, waitFor } from "@testing-library/react-native";
import i18n from "i18next";

const mockGet = jest.fn();
jest.mock("@/services/apiClient", () => ({ apiGet: (...a: unknown[]) => mockGet(...a) }));
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: { mqtt: "devre_disi", gateway: "online", stm: "online", espEtkin: false }, wsConnected: true }),
}));

import { GatewayStatusPanel } from "@/components/domain/GatewayStatusPanel";

afterEach(async () => {
  await act(async () => {
    await i18n.changeLanguage("tr");
  });
});

test.each([
  ["tr", "Cihaz Wi-Fi'si (PEMF-Gateway)", "Kablosuz Bağlantı"],
  ["en", "Device Wi-Fi (PEMF-Gateway)", "Wireless Connection"],
])("Y231: hotspot satırının adı (%s) = %s; eski belirsiz ad (%s) YOK", async (dil, yeni, eski) => {
  await act(async () => {
    await i18n.changeLanguage(dil);
  });
  mockGet.mockResolvedValue({ mqttConnected: false, brokerRunning: false, bridgeConnected: false, networkOnline: false, hotspotActive: false });
  const ekran = render(<GatewayStatusPanel />);
  await waitFor(() => expect(mockGet).toHaveBeenCalled());
  expect(ekran.queryByText(yeni)).not.toBeNull();
  expect(ekran.queryByText(eski)).toBeNull();
});
