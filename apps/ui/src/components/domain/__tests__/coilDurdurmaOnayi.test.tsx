// Author: mertaygn, cglrgrkn
/**
 * BOBİN KOMUT TEYİDİ — denetim 2. tur [1.1] (2026-08-20).
 *
 * Panelin kendi notu "yalnız TEYİTLİ başarıda 'durduruldu' de" derken yüklem `status !== "error"`
 * idi. Backend, publish broker'a ulaşamayınca HTTP 200 + {status:"mqtt_unavailable"} döner
 * (servers/api_server.py — ESP tek-bobin STOP yolu); eski yüklem bunu TEYİT sayıyordu → durdurma
 * komutu hiç ulaşmamışken panel "durduruldu" der (sahte güvence, korumasızlıktan tehlikelidir).
 *
 * ⚠️ 2026-10-02 (A-47, 1-D): bu dosya eskiden iddiayı 48 °C OTOMATİK durdurması üzerinden ölçüyordu.
 * Sahip kararıyla o otomatik durdurma KALDIRILDI (yalnız görsel uyarı — CoilSicaklikUyarisi.A47.test.tsx).
 * İddia DEĞİŞMEDİ, yalnız tetik operatörün "⏹ Durdur"una taşındı: aynı `sendCommand(false)` yolu.
 *
 * ⚠️ Testler DAVRANIŞSAL: gerçek bileşen çizilir, apiPost'un backend-gerçeği yanıtlarıyla
 * panelin hangi metni bastığı ölçülür.
 */
jest.mock("@/services/apiClient", () => ({ apiPost: jest.fn() }));
jest.mock("@/services/therapyLimits", () => ({
  clampTherapyParams: (p: unknown) => p,
}));

import { act, fireEvent, render } from "@testing-library/react-native";
import { CoilParameterPanel } from "@/components/domain/CoilParameterPanel";

const { apiPost } = jest.requireMock("@/services/apiClient");
const mockApiPost = apiPost as jest.Mock;

// ESP bobini (8), çalışıyor — operatör ⏹ Durdur'a basar.
const calisan = {
  coilId: 8,
  connected: true,
  running: true,
  objectTemp: 30.0,
  frequencyHz: 50,
  dutyCycle: 25,
  magneticMt: 1,
  currentA: 0.3,
  stm32Driven: false,
  stmConnected: true,
};

beforeEach(() => {
  mockApiPost.mockReset();
});

async function durdur() {
  const u = render(<CoilParameterPanel {...calisan} />);
  await act(async () => {
    fireEvent.press(u.getByLabelText("Bobini durdur"));
  });
  expect(mockApiPost).toHaveBeenCalledTimes(1);
  expect(mockApiPost.mock.calls[0][1].start).toBe(false);
  return u;
}

it("KRİTİK: durdurma yanıtı mqtt_unavailable → 'DURDURMA ONAYLANAMADI' (sahte 'durduruldu' YOK)", async () => {
  // Backend'in GERÇEK broker-ölü yanıtı: HTTP 200 + mqtt_unavailable (apiPost bunu aynen döndürür).
  mockApiPost.mockResolvedValue({ status: "mqtt_unavailable", transport: "mqtt" });

  const u = await durdur();

  expect(u.queryByText(/durduruldu/)).toBeNull();
  expect(u.getByText(/DURDURMA ONAYLANAMADI/)).toBeTruthy();
});

it("KARŞIT-KANIT: teyitli başarıda uyarı ÇIKMAZ (yanlış alarm üretme)", async () => {
  mockApiPost.mockResolvedValue({ status: "success", transport: "mqtt" });

  const u = await durdur();

  expect(u.queryByText(/DURDURMA ONAYLANAMADI/)).toBeNull();
});

it("mevcut davranış korunur: yanıt null (ağ hatası) → yine 'DURDURMA ONAYLANAMADI'", async () => {
  mockApiPost.mockResolvedValue(null);

  const u = await durdur();

  expect(u.getByText(/DURDURMA ONAYLANAMADI/)).toBeTruthy();
});
