/**
 * KD madde 0 (istem 44 · sahip 2026-11-10) — "Kameraları tara" istemcide genel 8 sn sınırıyla "İşlem zaman aşımına uğradı … model
 * yüklemesi" diyordu (sahip: "istemcideki 8 saniye sınırını kaldıralım, kamera bağlı değil zanneder kullanıcı"). Tarama artık
 * KAMERAYA özgü uzun süreyle (`KAMERA_TIMEOUT_MS`, ≥ 30 sn) ve KAMERAYA özgü zaman aşımı metniyle istenir; tarama sürerken "kameralar
 * açılıyor" durumu görünür. TR + EN.
 */
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";
import i18n from "i18next";

jest.mock("@/services/toastBridge", () => ({ emitToast: jest.fn() }));
jest.mock("@/services/apiClient", () => ({
  apiGet: (...a: unknown[]) => mockGet(...a),
  apiPost: (...a: unknown[]) => mockPost(...a),
  KAMERA_TIMEOUT_MS: 120000,
}));
const mockGet = jest.fn();
const mockPost = jest.fn();

import { KabinKamerasiKarti } from "@/components/domain/KabinKamerasiKarti";
import { EN, TR } from "@/i18n/__tests__/kaynakMetni";

beforeEach(() => {
  mockGet.mockReset().mockResolvedValue({ secili: null, istenenCozunurluk: null });
  mockPost.mockReset();
});
afterEach(async () => {
  await act(async () => {
    await i18n.changeLanguage("tr");
  });
});

it("KRİTİK: ürün sabiti genel 8 sn'nin ÜSTÜNDE (≥ 30 sn — istem 44 0-c)", () => {
  const gercek = jest.requireActual("@/services/apiClient") as { KAMERA_TIMEOUT_MS: number };
  expect(gercek.KAMERA_TIMEOUT_MS).toBeGreaterThanOrEqual(30000);
});

it("KRİTİK: tarama KAMERA süresiyle ve KAMERAYA özgü zaman aşımı metniyle istenir ('model yüklemesi' DEĞİL)", async () => {
  mockPost.mockResolvedValue({ kameralar: [], secili: null });
  const ekran = render(<KabinKamerasiKarti />);
  await ekran.findByTestId("kabin-kamerasi-secilmedi");
  fireEvent.press(ekran.getByTestId("kabin-kamerasi-tara"));
  await waitFor(() => expect(mockPost).toHaveBeenCalled());
  const [yol, govde, yedek, secenek] = mockPost.mock.calls[0];
  expect([yol, govde, yedek]).toEqual(["/settings/kabin-kamerasi/tara", {}, null]);
  expect(secenek.timeoutMs).toBe(120000);
  expect(secenek.zamanAsimiMesaji).toBe(i18n.t("ayarlar.kabinKamerasi.taramaZamanAsimi"));
  expect(secenek.zamanAsimiMesaji).toMatch(/[Kk]amera/);
  expect(secenek.zamanAsimiMesaji).not.toMatch(/model/i);
});

it("tarama sürerken 'kameralar açılıyor' durumu görünür, bitince kalkar", async () => {
  let bitir: (v: unknown) => void = () => undefined;
  mockPost.mockReturnValue(new Promise((r) => (bitir = r)));
  const ekran = render(<KabinKamerasiKarti />);
  await ekran.findByTestId("kabin-kamerasi-secilmedi");
  fireEvent.press(ekran.getByTestId("kabin-kamerasi-tara"));
  const durum = await ekran.findByTestId("kabin-kamerasi-taraniyor");
  expect(durum.props.children).toBe(TR["ayarlar.kabinKamerasi.taraniyor"]);
  await act(async () => {
    bitir({ kameralar: [], secili: null });
  });
  await waitFor(() => expect(ekran.queryByTestId("kabin-kamerasi-taraniyor")).toBeNull());
});

it("TR metinleri birebir; açıklama artık sabit 1920×1080 DEMEZ (en yüksek / kalibrasyon çözünürlüğü)", () => {
  expect(TR["ayarlar.kabinKamerasi.taramaZamanAsimi"]).toBe(
    "Kamera taraması zamanında bitmedi — kameralar açılırken yanıt vermedi. Kamera kablosunu kontrol edin, kamerayı kullanan başka bir " +
      "uygulama (ör. Windows Kamera) açıksa kapatın ve yeniden tarayın."
  );
  expect(TR["ayarlar.kabinKamerasi.taraniyor"]).toBe("Kameralar açılıyor — bu birkaç saniye sürebilir.");
  expect(TR["ayarlar.kabinKamerasi.aciklama"]).not.toMatch(/1920×1080/);
  expect(TR["ayarlar.kabinKamerasi.aciklama"]).toMatch(/en yüksek çözünürlüğünde \(kabin kalibrasyonu varsa onun çözünürlüğünde\)/);
});

it("EN: durum ve zaman aşımı metni İngilizce", async () => {
  await act(async () => {
    await i18n.changeLanguage("en");
  });
  let bitir: (v: unknown) => void = () => undefined;
  mockPost.mockReturnValue(new Promise((r) => (bitir = r)));
  const ekran = render(<KabinKamerasiKarti />);
  await ekran.findByTestId("kabin-kamerasi-secilmedi");
  fireEvent.press(ekran.getByTestId("kabin-kamerasi-tara"));
  const durum = await ekran.findByTestId("kabin-kamerasi-taraniyor");
  expect(durum.props.children).toBe(EN["ayarlar.kabinKamerasi.taraniyor"]);
  expect(mockPost.mock.calls[0][3].zamanAsimiMesaji).toBe(EN["ayarlar.kabinKamerasi.taramaZamanAsimi"]);
  expect(EN["ayarlar.kabinKamerasi.taramaZamanAsimi"]).toMatch(/camera scan did not finish in time/);
  await act(async () => {
    bitir({ kameralar: [], secili: null });
  });
});
