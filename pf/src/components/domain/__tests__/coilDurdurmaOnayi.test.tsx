// Author: mertaygn, cglrgrkn
/**
 * BOBİN KOMUT TEYİDİ — denetim 2. tur [1.1] (2026-08-20).
 *
 * Panelin kendi notu "yalnız TEYİTLİ başarıda 'durduruldu' de" derken yüklem `status !== "error"`
 * idi. Backend, publish broker'a ulaşamayınca HTTP 200 + {status:"mqtt_unavailable"} döner
 * (servers/api_server.py — ESP tek-bobin STOP yolu); eski yüklem bunu TEYİT sayıyordu.
 * En ağır yüzeyi aşırı-ısınma interlock'u: yanık riski anında durdurma komutu hiç ulaşmamışken
 * panel "bobin otomatik durduruldu" diyordu — sahte güvence, korumasızlıktan tehlikelidir.
 *
 * ⚠️ Testler DAVRANIŞSAL: gerçek bileşen çizilir, apiPost'un backend-gerçeği yanıtlarıyla
 * interlock'un hangi metni bastığı ölçülür.
 */
jest.mock("@/services/apiClient", () => ({ apiPost: jest.fn() }));
jest.mock("@/services/therapyLimits", () => ({
  clampTherapyParams: (p: unknown) => p,
}));

import { act, render } from "@testing-library/react-native";
import { CoilParameterPanel } from "@/components/domain/CoilParameterPanel";

const { apiPost } = jest.requireMock("@/services/apiClient");
const mockApiPost = apiPost as jest.Mock;

// ESP bobini (7), çalışıyor, sıcaklık kesme eşiğinin (48) ÜSTÜNDE → interlock tetiklenir.
const asiriIsinan = {
  coilId: 7,
  connected: true,
  running: true,
  objectTemp: 50.2,
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

async function ciz() {
  const u = render(<CoilParameterPanel {...asiriIsinan} />);
  await act(async () => {}); // interlock'un async sendCommand'i tamamlansın
  return u;
}

it("KRİTİK: durdurma yanıtı mqtt_unavailable → 'DURDURMA ONAYLANAMADI' (sahte 'durduruldu' YOK)", async () => {
  // Backend'in GERÇEK broker-ölü yanıtı: HTTP 200 + mqtt_unavailable (apiPost bunu aynen döndürür).
  mockApiPost.mockResolvedValue({ status: "mqtt_unavailable", transport: "mqtt" });

  const u = await ciz();

  expect(u.queryByText(/otomatik durduruldu/)).toBeNull();
  expect(u.getByText(/DURDURMA ONAYLANAMADI/)).toBeTruthy();
});

it("KARŞIT-KANIT: teyitli başarıda 'otomatik durduruldu' denir (yanlış alarm üretme)", async () => {
  mockApiPost.mockResolvedValue({ status: "success", transport: "mqtt" });

  const u = await ciz();

  expect(u.getByText(/otomatik durduruldu/)).toBeTruthy();
  expect(u.queryByText(/DURDURMA ONAYLANAMADI/)).toBeNull();
});

it("mevcut davranış korunur: yanıt null (ağ hatası) → yine 'DURDURMA ONAYLANAMADI'", async () => {
  mockApiPost.mockResolvedValue(null);

  const u = await ciz();

  expect(u.getByText(/DURDURMA ONAYLANAMADI/)).toBeTruthy();
});
