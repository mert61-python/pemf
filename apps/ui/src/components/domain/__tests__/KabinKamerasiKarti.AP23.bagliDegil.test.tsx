// Author: mertaygn, cglrgrkn
/**
 * AP-23 (ev denemesi 14 Kasım) — seçili kabin kamerası TAKILI DEĞİLKEN kart "Seçili kamera: FHD Camera — şu an kamera 0; sıra değişse de
 * bu kamera açılır" diyordu (hazırlık ise kamerayı bulamıyordu). Sunucu `bagli: false` derse kart "BAĞLI DEĞİL" + eylem (kırmızı);
 * `bagli: true` ise GÜNCEL indeks; alan yoksa (eski sunucu / bilinmiyor) eski satır AYNEN. Sahte yalnız ağ sınırında.
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
import { EN, TR } from "@/i18n/__tests__/kaynakMetni";
import { colors } from "@/theme/tokens";

const SECILI = { indeks: 0, kaynak: "ayar", kimlik: { ad: "FHD Camera", vidpid: "VID_1BCF&PID_28C4" } };
const KIMLIK = { ad: "FHD Camera", vidpid: "VID_1BCF&PID_28C4" };

beforeEach(() => {
  mockGet.mockReset();
  mockPost.mockReset();
});
afterEach(async () => {
  await act(async () => {
    await i18n.changeLanguage("tr");
  });
});

it("KRİTİK: sunucu bagli:false derse kart 'BAĞLI DEĞİL' + eylem söyler (şu an kamera N DEMEZ), TR ve EN", async () => {
  mockGet.mockResolvedValue({ secili: SECILI, bagli: false, guncelIndeks: null });
  const u = render(<KabinKamerasiKarti />);
  const satir = await u.findByTestId("kabin-kamerasi-secili");
  expect(satir.props.children).toBe(i18n.t("ayarlar.kabinKamerasi.seciliKameraBagliDegil", KIMLIK));
  expect(satir.props.children).not.toMatch(/şu an kamera/);
  expect(TR["ayarlar.kabinKamerasi.seciliKameraBagliDegil"]).toMatch(/BAĞLI DEĞİL/);
  expect(EN["ayarlar.kabinKamerasi.seciliKameraBagliDegil"]).toMatch(/NOT CONNECTED/);
  expect(EN["ayarlar.kabinKamerasi.seciliKameraBagliDegil"]).not.toMatch(/petri/i);
  expect([satir.props.style].flat(3)).toEqual(expect.arrayContaining([expect.objectContaining({ color: colors.danger })]));
  await act(async () => {
    await i18n.changeLanguage("en");
  });
  expect(u.getByTestId("kabin-kamerasi-secili").props.children).toMatch(/NOT CONNECTED/);
});

it("KRİTİK: bagli:true ise 'şu an kamera' GÜNCEL indeksi gösterir (saklı değil)", async () => {
  mockGet.mockResolvedValue({ secili: SECILI, bagli: true, guncelIndeks: 2 });
  const u = render(<KabinKamerasiKarti />);
  expect((await u.findByTestId("kabin-kamerasi-secili")).props.children).toBe(
    i18n.t("ayarlar.kabinKamerasi.seciliKameraAdli", { indeks: 2, ...KIMLIK })
  );
});

it("KARŞIT: alan yoksa (eski sunucu / bilinmiyor) eski satır AYNEN", async () => {
  mockGet.mockResolvedValue({ secili: SECILI });
  const u = render(<KabinKamerasiKarti />);
  expect((await u.findByTestId("kabin-kamerasi-secili")).props.children).toBe(
    i18n.t("ayarlar.kabinKamerasi.seciliKameraAdli", { indeks: 0, ...KIMLIK })
  );
});

it("KRİTİK: kamera takılıp 'Kameraları tara' denince kart BAĞLI DEĞİL'den çıkar (tarama yanıtının bağlantı durumu)", async () => {
  mockGet.mockResolvedValue({ secili: SECILI, bagli: false, guncelIndeks: null });
  mockPost.mockResolvedValue({ kameralar: [], secili: SECILI, bagli: true, guncelIndeks: 1 });
  const u = render(<KabinKamerasiKarti />);
  expect((await u.findByTestId("kabin-kamerasi-secili")).props.children).toMatch(/BAĞLI DEĞİL/);
  await act(async () => {
    fireEvent.press(u.getByText(TR["ayarlar.kabinKamerasi.tara"]));
  });
  expect(u.getByTestId("kabin-kamerasi-secili").props.children).toBe(i18n.t("ayarlar.kabinKamerasi.seciliKameraAdli", { indeks: 1, ...KIMLIK }));
  expect(mockGet).toHaveBeenCalledTimes(1); // yeniden GET YOK — durum tarama yanıtından
});
