// Author: mertaygn, cglrgrkn
/**
 * I18NI-A3.5 — APK güncelleme bandı ve zorunlu güncelleme kapısı yayın manifest'inin TEK DİLLİ `notes` alanını (elle yazılan Türkçe sürüm
 * notu) İngilizce arayüzde de AYNEN basıyordu → İngilizce kullanıcı bantta / açılışta ekranı kaplayan kapıda Türkçe cümle görür.
 *
 * GERÇEK: MobileUpdateBanner / MobileUpdateGate + useApkGuncelleme + i18n (bayrak test anahtarıyla açık). Sahte: yalnız manifest okuması
 * (`guncellemeVarMi`). TR: not bugünkü gibi (birebir). EN: Türkçe not GÖSTERİLMEZ — manifest `notes_en` varsa o, yoksa katalog metni.
 * Orkestratör (14): ajan sondası yalnız bandı ve "EN not yok" dalını ölçüyordu; kapı ve `notes_en` dalı eklendi.
 */
jest.mock("expo-file-system/legacy", () => ({
  cacheDirectory: "file:///cache/",
  createDownloadResumable: jest.fn(),
  getInfoAsync: jest.fn(),
  deleteAsync: jest.fn(),
}));
jest.mock("@/services/mobileUpdate", () => {
  const gercek = jest.requireActual("@/services/mobileUpdate");
  return { ...gercek, guncellemeVarMi: jest.fn(), apkIndir: jest.fn(), kurulumuBaslat: jest.fn() };
});
jest.mock("@/context/LiveDataContext", () => ({ useLiveData: () => ({ snapshot: {} }) }));

import React from "react";
import { render, act, waitFor } from "@testing-library/react-native";
import { Platform, Text } from "react-native";
import i18n from "i18next";
import { MobileUpdateBanner } from "@/components/domain/MobileUpdateBanner";
import { MobileUpdateGate } from "@/components/domain/MobileUpdateGate";
import {
  guncellemeVarMi,
  surumNotu,
  _atlamayiSifirla,
  _indirmeyiSifirla,
  _kurulumErtelemesiniSifirla,
  type MobilSurum,
} from "@/services/mobileUpdate";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";

const TR_NOT = "Bobinler durduktan sonra güncelleyin; bu sürüm bağlantı hatalarını düzeltir.";
const EN_NOT = "Update after the coils have stopped; this version fixes connection errors.";
const SURUM = {
  version: "2.4.0",
  versionCode: 30,
  url: "https://github.com/o/r/releases/download/t/PEMF_Vet_Mobil.apk",
  sha256: "a".repeat(64),
  size: 128_000_000,
  notes: TR_NOT,
} as MobilSurum;
const depo = { setItem: async () => undefined };

async function enYap() {
  __bayrakTestiAyarla(true);
  await act(async () => {
    await dilSec("en", depo);
  });
}

const kapiyiCiz = () =>
  render(
    <MobileUpdateGate>
      <Text>UYGULAMA</Text>
    </MobileUpdateGate>,
  );

beforeEach(() => {
  jest.clearAllMocks();
  _atlamayiSifirla();
  _indirmeyiSifirla();
  _kurulumErtelemesiniSifirla();
  (Platform as { OS: string }).OS = "android";
  (guncellemeVarMi as jest.Mock).mockResolvedValue({ varMi: true, surum: SURUM });
});

afterEach(async () => {
  __bayrakTestiAyarla(null);
  await act(async () => {
    await dilSec("tr", depo);
  });
});

it("surumNotu: TR → notes; EN → yalnız notes_en (yoksa boş → çağıran katalog metnine düşer)", () => {
  expect(surumNotu(SURUM, "tr")).toBe(TR_NOT);
  expect(surumNotu(SURUM, "en")).toBe("");
  expect(surumNotu({ ...SURUM, notes_en: EN_NOT }, "en")).toBe(EN_NOT);
  expect(surumNotu({ ...SURUM, notes_en: EN_NOT }, "tr")).toBe(TR_NOT);
  expect(surumNotu(null, "en")).toBe("");
});

it("bant TR: sürüm notu bugünkü gibi (birebir)", async () => {
  const { getByText } = render(<MobileUpdateBanner />);
  await waitFor(() => expect(getByText(TR_NOT)).toBeTruthy());
});

it("bant EN: Türkçe not GÖSTERİLMEZ, EN not yoksa katalog metni", async () => {
  await enYap();
  const { queryByText, getByText } = render(<MobileUpdateBanner />);
  await waitFor(() => expect(getByText(i18n.t("guncelleme.hazir", { version: "2.4.0" }))).toBeTruthy());
  expect(queryByText(TR_NOT)).toBeNull();
  expect(getByText(i18n.t("guncelleme.dokunun"))).toBeTruthy();
});

it("bant EN: manifest notes_en varsa o gösterilir", async () => {
  (guncellemeVarMi as jest.Mock).mockResolvedValue({ varMi: true, surum: { ...SURUM, notes_en: EN_NOT } });
  await enYap();
  const { queryByText, getByText } = render(<MobileUpdateBanner />);
  await waitFor(() => expect(getByText(EN_NOT)).toBeTruthy());
  expect(queryByText(TR_NOT)).toBeNull();
});

it("kapı TR: sürüm notu bugünkü gibi (birebir)", async () => {
  const { getByText } = kapiyiCiz();
  await waitFor(() => expect(getByText(TR_NOT)).toBeTruthy());
});

it("kapı EN: Türkçe not GÖSTERİLMEZ — EN not yoksa katalog önerisi, varsa EN not", async () => {
  await enYap();
  const u = kapiyiCiz();
  await waitFor(() => expect(u.getByText(i18n.t("guncelleme.kapiOneri"))).toBeTruthy());
  expect(u.queryByText(TR_NOT)).toBeNull();
  u.unmount();
  _atlamayiSifirla();
  (guncellemeVarMi as jest.Mock).mockResolvedValue({ varMi: true, surum: { ...SURUM, notes_en: EN_NOT } });
  const v = kapiyiCiz();
  await waitFor(() => expect(v.getByText(EN_NOT)).toBeTruthy());
  expect(v.queryByText(TR_NOT)).toBeNull();
});
