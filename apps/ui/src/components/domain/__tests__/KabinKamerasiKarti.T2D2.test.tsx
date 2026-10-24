/**
 * T2D-2 (Tezgâh-2 #3) — Ayarlar ▸ Kabin kamerası: seçim yoksa EYLEM söyleyen uyarı (AI Pro kamerası açılmaz); tarama küçük önizlemeli
 * aday listesi getirir; "Bunu seç" seçimi cihaza yazar (`POST /settings/kabin-kamerasi {indeks}`) ve seçili gösterilir. TR + EN.
 */
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";
import i18n from "i18next";

// T3 · Y190: bölüm bildirimi `toastBridge` ile verir (AI Pro panelinde ToastProvider yok) — aynı sözleşme, köprü sahtesi.
jest.mock("@/services/toastBridge", () => ({ emitToast: (...a: unknown[]) => mockToast(...a) }));
jest.mock("@/services/apiClient", () => ({
  apiGet: (...a: unknown[]) => mockGet(...a),
  apiPost: (...a: unknown[]) => mockPost(...a),
}));
const mockToast = jest.fn();
const mockGet = jest.fn();
const mockPost = jest.fn();

import { KabinKamerasiKarti } from "@/components/domain/KabinKamerasiKarti";

const ADAYLAR = [
  { indeks: 0, genislik: 1280, yukseklik: 720, onizleme: "QUJD" },
  { indeks: 1, genislik: 1920, yukseklik: 1080, onizleme: "REVG" },
];

beforeEach(() => {
  mockToast.mockClear();
  mockGet.mockReset();
  mockPost.mockReset();
});
afterEach(async () => {
  await act(async () => {
    await i18n.changeLanguage("tr");
  });
});

it("KRİTİK: seçim yokken uyarı EYLEM söyler (kamera açılmaz, tarayıp seçin)", async () => {
  mockGet.mockResolvedValue({ secili: null, istenenCozunurluk: [1920, 1080] });
  const ekran = render(<KabinKamerasiKarti />);
  const uyari = await ekran.findByTestId("kabin-kamerasi-secilmedi");
  expect(uyari.props.children).toBe(i18n.t("ayarlar.kabinKamerasi.secilmedi"));
  expect(uyari.props.children).toMatch(/açılmaz.*tarayıp/);
  expect(mockGet).toHaveBeenCalledWith("/settings/kabin-kamerasi", null, { silent: true });
});

it("KRİTİK: tara → adaylar önizlemeyle; 'Bunu seç' indeksi POST eder ve seçili gösterir", async () => {
  mockGet.mockResolvedValue({ secili: null });
  mockPost.mockImplementation(async (yol: string, govde: { indeks?: number }) =>
    yol === "/settings/kabin-kamerasi/tara"
      ? { kameralar: ADAYLAR, secili: null }
      : { status: "success", secili: { indeks: govde.indeks, kaynak: "ayar" } }
  );
  const ekran = render(<KabinKamerasiKarti />);
  await ekran.findByTestId("kabin-kamerasi-secilmedi");
  fireEvent.press(ekran.getByTestId("kabin-kamerasi-tara"));
  await ekran.findByTestId("kabin-kamerasi-aday-1");
  expect(ekran.getByText("1920×1080")).toBeTruthy();
  fireEvent.press(ekran.getByTestId("kabin-kamerasi-sec-1"));
  await waitFor(() => expect(ekran.getByTestId("kabin-kamerasi-secili")).toBeTruthy());
  expect(mockPost).toHaveBeenLastCalledWith("/settings/kabin-kamerasi", { indeks: 1 }, null);
  expect(ekran.getByTestId("kabin-kamerasi-secili").props.children).toBe(i18n.t("ayarlar.kabinKamerasi.seciliKamera", { indeks: 1 }));
  expect(mockToast).toHaveBeenCalledWith(i18n.t("ayarlar.kabinKamerasi.secildi", { indeks: 1 }), "success");
});

it("EN: başlık ve uyarı İngilizce", async () => {
  await act(async () => {
    await i18n.changeLanguage("en");
  });
  mockGet.mockResolvedValue({ secili: null });
  const ekran = render(<KabinKamerasiKarti />);
  const uyari = await ekran.findByTestId("kabin-kamerasi-secilmedi");
  expect(uyari.props.children).toMatch(/No cabin camera selected/);
  expect(ekran.getByText("Cabin camera")).toBeTruthy();
});
