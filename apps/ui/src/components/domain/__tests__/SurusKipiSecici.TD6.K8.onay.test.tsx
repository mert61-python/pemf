// Author: mertaygn, cglrgrkn
/**
 * TD6 · K8 (tezgâh Oturum 13 "Kullanıcı geri bildirimi") — SÜRÜŞ KİPİ değişikliği onay + SONUÇ cümlesi.
 *
 * ÖLÇÜLEN: "Sürüş Kipi" kutusuna tek dokunuş, tam köprülü bobini (1–5) tek yönlü — DC bileşenli — sürüşe KALICI geçiriyordu; ekranda
 * yalnız "Kaydedildi — bir sonraki başlatmada uygulanır." yazıyordu (neyin değiştiği yok).
 * SÖZLEŞME: yetenekli bir bobin çift yönlüden TEK YÖNLÜYE geçerken onay ("Tek yönlü sürüş bobinde DC bileşen oluşturur ve alan
 * değerlerini değiştirir. Emin misiniz?"); vazgeçilirse hiçbir şey gönderilmez ve kip DEĞİŞMEZ. Ters yön (varsayılana dönüş) onaysız.
 * Başarıda sonuç cümlesi neyin değiştiğini söyler. Testler ÇİZİLEN metni ve GÖNDERİLEN gövdeyi ölçer.
 */
const mockApiPost = jest.fn(async (..._a: unknown[]) => ({ status: "success" }) as unknown);
const mockConfirm = jest.fn(async (..._a: unknown[]) => true);
jest.mock("@/services/apiClient", () => ({
  apiPost: (...a: unknown[]) => mockApiPost(...a),
  platformConfirm: (...a: unknown[]) => mockConfirm(...a),
}));

import { fireEvent, render, waitFor } from "@testing-library/react-native";
import { SurusKipiSecici } from "@/components/domain/SurusKipiSecici";
import type { CoilStatus } from "@/types/domain";

const bobinler = (): CoilStatus[] =>
  Array.from({ length: 7 }, (_, i) => ({
    id: i + 1,
    connected: true,
    running: false,
    frequencyHz: 0,
    dutyCycle: 0,
    magneticMt: 0,
    objectTemp: 0,
    ambientTemp: 0,
    currentA: 0,
    bipolarYetenek: i < 5,
  }));

const ciz = () => render(<SurusKipiSecici coils={bobinler()} stmConnected />);
const K8 = "Tek yönlü sürüş bobinde DC bileşen oluşturur ve alan değerlerini değiştirir. Emin misiniz?";

beforeEach(() => {
  mockApiPost.mockReset().mockResolvedValue({ status: "success" });
  mockConfirm.mockReset().mockResolvedValue(true);
});

test("KRITIK K8: tek yönlüye geçiş ONAY ister; onayla gönderilir ve SONUÇ cümlesi neyin değiştiğini söyler", async () => {
  const u = ciz();
  fireEvent.press(u.getByLabelText(/^Bobin 3, bipolar/));
  await waitFor(() => expect(mockApiPost).toHaveBeenCalledTimes(1));
  expect(mockConfirm).toHaveBeenCalledTimes(1);
  expect(String(mockConfirm.mock.calls[0][1])).toBe(K8);
  expect(await u.findByText("Bobin 3 tek yönlü (Unipolar) sürüşe alındı — bir sonraki başlatmada uygulanır.")).toBeTruthy();
  expect(u.queryByText(/^Kaydedildi/)).toBeNull();
});

test("KRITIK K8: onay VERİLMEZSE hiçbir şey gönderilmez ve kip DEĞİŞMEZ", async () => {
  mockConfirm.mockResolvedValue(false);
  const u = ciz();
  fireEvent.press(u.getByLabelText("Tüm bobinleri unipolar sür"));
  await waitFor(() => expect(mockConfirm).toHaveBeenCalledTimes(1));
  expect(mockApiPost).not.toHaveBeenCalled();
  expect(u.getByLabelText(/^Bobin 1, bipolar/)).toBeTruthy();
});

test("K8: çift yönlüye DÖNÜŞ onay istemez; sonuç cümlesi dönüşü söyler", async () => {
  const u = ciz();
  fireEvent.press(u.getByLabelText(/^Bobin 2, bipolar/));
  await waitFor(() => expect(mockApiPost).toHaveBeenCalledTimes(1));
  fireEvent.press(u.getByLabelText(/^Bobin 2, unipolar/));
  await waitFor(() => expect(mockApiPost).toHaveBeenCalledTimes(2));
  expect(mockConfirm).toHaveBeenCalledTimes(1);
  expect(await u.findByText("Bobin 2 çift yönlü (Bipolar) sürüşe alındı — bir sonraki başlatmada uygulanır.")).toBeTruthy();
});

test("K8: değişmeyen istek 'Kip değişmedi' der (Hepsi Bipolar varsayılandayken)", async () => {
  const u = ciz();
  fireEvent.press(u.getByLabelText("Yetenekli tüm bobinleri bipolar sür"));
  await waitFor(() => expect(mockApiPost).toHaveBeenCalledTimes(1));
  expect(mockConfirm).not.toHaveBeenCalled();
  expect(await u.findByText("Kip değişmedi — kaydedildi.")).toBeTruthy();
});
