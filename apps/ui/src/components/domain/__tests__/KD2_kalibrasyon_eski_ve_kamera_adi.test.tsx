// Author: mertaygn, cglrgrkn
/**
 * KD-2 (sahip kararları 2026-11-10) — (1) "kalibre etmeden devam" edildiyse analiz sonucundaki PEMF kapısı kutusunda SUNUCUNUN kalıcı
 * "kalibrasyon eski" uyarısı görünür (alan yoksa satır YOK); (2) kabin kamerası taramasında ve seçimde kameranın Windows ADI + VID/PID
 * görünür (seçim kimliğe bağlı — MSMF sırası değişse de aynı kamera). Sahte yalnız ağ sınırında.
 */
import { act, fireEvent, render } from "@testing-library/react-native";
import i18n from "i18next";
import React from "react";

jest.mock("@/services/toastBridge", () => ({ emitToast: jest.fn() }));
jest.mock("@/services/apiClient", () => ({
  apiGet: (...a: unknown[]) => mockGet(...a),
  apiPost: (...a: unknown[]) => mockPost(...a),
  KAMERA_TIMEOUT_MS: 120000,
}));
const mockGet = jest.fn();
const mockPost = jest.fn();

import { KabinKamerasiKarti } from "@/components/domain/KabinKamerasiKarti";
import { PemfKapisiKutusu } from "@/components/domain/PemfKapisiKutusu";
import { EN, TR } from "@/i18n/__tests__/kaynakMetni";

const KAPI = { surulebilir: true, pemf_gecerli: true, nedenler: [], mesajlar: [], varsayimlar: [] };

beforeEach(() => {
  mockGet.mockReset();
  mockPost.mockReset();
});
afterEach(async () => {
  await act(async () => {
    await i18n.changeLanguage("tr");
  });
});

it("KRİTİK: kalibrasyon ESKİ uyarısı sunucu metniyle görünür; alan yoksa satır yok", () => {
  const u = render(<PemfKapisiKutusu model="petri" kapi={KAPI} kalibrasyonUyarisi="SUNUCU: kalibrasyon eski" />);
  expect(u.getByTestId("pemf-kapisi-kalibrasyon-eski").props.children).toEqual(["⚠ ", "SUNUCU: kalibrasyon eski"]);
  const y = render(<PemfKapisiKutusu model="petri" kapi={KAPI} />);
  expect(y.queryByTestId("pemf-kapisi-kalibrasyon-eski")).toBeNull();
});

it("KRİTİK: tarama ve seçim kameranın ADINI + VID/PID'ini gösterir (adsız aday eski metinle)", async () => {
  mockGet.mockResolvedValue({ secili: { indeks: 0, kaynak: "ayar", kimlik: { ad: "FHD Camera", vidpid: "VID_1BCF&PID_28C4" } } });
  mockPost.mockResolvedValue({
    kameralar: [
      { indeks: 0, genislik: 1920, yukseklik: 1080, onizleme: null, ad: "FHD Camera", vidpid: "VID_1BCF&PID_28C4" },
      { indeks: 1, genislik: 640, yukseklik: 480, onizleme: null, ad: null, vidpid: null },
    ],
    secili: { indeks: 0 },
  });
  const u = render(<KabinKamerasiKarti />);
  expect((await u.findByTestId("kabin-kamerasi-secili")).props.children).toBe(
    i18n.t("ayarlar.kabinKamerasi.seciliKameraAdli", { indeks: 0, ad: "FHD Camera", vidpid: "VID_1BCF&PID_28C4" })
  );
  fireEvent.press(u.getByText(TR["ayarlar.kabinKamerasi.tara"]));
  expect(await u.findByText(i18n.t("ayarlar.kabinKamerasi.kameraAdiTam", { indeks: 0, ad: "FHD Camera", vidpid: "VID_1BCF&PID_28C4" }))).toBeTruthy();
  expect(u.getByText(i18n.t("ayarlar.kabinKamerasi.kameraAdi", { indeks: 1 }))).toBeTruthy();
  expect(EN["ayarlar.kabinKamerasi.kameraAdiTam"]).toMatch(/Camera \{\{indeks\}\} — \{\{ad\}\}/);
});
