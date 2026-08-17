// Author: mertaygn, cglrgrkn
/**
 * UYGULAMA İÇİ MOBİL GÜNCELLEME BANDI — açılış kapısıyla birlikte (2026-08-16).
 *
 * Bant, kapı atlandığında/zaman aşımına uğradığında güncellemeyi yakalayan İKİNCİ yoldur; bu
 * yüzden kapı eklenirken KALDIRILMADI. Buradaki testler iki şeyi birden kilitler:
 *   - kapıda "şimdilik devam et" denen sürüm bu açılışta bantla YENİDEN DAYATILMAZ,
 *   - ertelenmemiş her sürüm için bant ÇALIŞMAYA devam eder (kapı bandı öldürmedi),
 *   - ⚠️ HASTA GÜVENLİĞİ: seans sürerken bant gösterilmez (indirme/kurulum ekranı böler).
 *
 * ⚠️ `useApkGuncelleme` ortaklaştırması sonrası bandın indirme/kurulum davranışının bozulmadığı
 * da burada sınanır (refaktörün sessizce özellik düşürmediğinin kanıtı).
 */
jest.mock("expo-file-system/legacy", () => ({
  cacheDirectory: "file:///cache/",
  createDownloadResumable: jest.fn(),
  getInfoAsync: jest.fn(),
  deleteAsync: jest.fn(),
}));

jest.mock("@/services/mobileUpdate", () => {
  const gercek = jest.requireActual("@/services/mobileUpdate");
  return {
    ...gercek, // guncellemeyiAtla/atlandiMi GERÇEK — susturma gerçekten sınansın
    guncellemeVarMi: jest.fn(),
    apkIndir: jest.fn(),
    kurulumuBaslat: jest.fn(),
  };
});

const mockSnapshot: { activeTreatment?: { isActive: boolean } } = {};
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: mockSnapshot }),
}));

import { render, act, fireEvent, waitFor } from "@testing-library/react-native";
import { Platform } from "react-native";

import { MobileUpdateBanner } from "@/components/domain/MobileUpdateBanner";
import {
  apkIndir,
  guncellemeVarMi,
  guncellemeyiAtla,
  kurulumuBaslat,
  _atlamayiSifirla,
  type MobilSurum,
} from "@/services/mobileUpdate";

const mockVarMi = guncellemeVarMi as jest.Mock;
const mockIndir = apkIndir as jest.Mock;
const mockKur = kurulumuBaslat as jest.Mock;

const SURUM: MobilSurum = {
  version: "2.4.0",
  versionCode: 30,
  url: "https://github.com/o/r/releases/download/t/PEMF_Vet_Mobil.apk",
  sha256: "a".repeat(64),
  size: 128_000_000,
};

beforeEach(() => {
  jest.clearAllMocks();
  _atlamayiSifirla();
  delete mockSnapshot.activeTreatment;
  (Platform as { OS: string }).OS = "android";
  mockVarMi.mockResolvedValue({ varMi: true, surum: SURUM });
  mockIndir.mockResolvedValue({ ok: true, dosyaUri: "file:///cache/x.apk" });
  mockKur.mockResolvedValue(true);
});

it("güncelleme varsa bant ÇİZİLİR (kapı bandı öldürmedi)", async () => {
  const { getByText } = render(<MobileUpdateBanner />);
  await waitFor(() => expect(getByText(/Yeni sürüm hazır: 2\.4\.0/)).toBeTruthy());
});

it("🔴 kapıda ERTELENEN sürüm bantla YENİDEN DAYATILMAZ", async () => {
  guncellemeyiAtla(SURUM.versionCode);
  const { queryByText } = render(<MobileUpdateBanner />);
  await act(async () => {});
  expect(queryByText(/Yeni sürüm hazır/)).toBeNull();
});

it("BAŞKA bir sürüm ertelenmişse bant yine çıkar (susturma sürüme özgü)", async () => {
  guncellemeyiAtla(SURUM.versionCode - 1);
  const { getByText } = render(<MobileUpdateBanner />);
  await waitFor(() => expect(getByText(/Yeni sürüm hazır/)).toBeTruthy());
});

it("🔴 HASTA GÜVENLİĞİ: seans sürerken bant gösterilmez", async () => {
  mockSnapshot.activeTreatment = { isActive: true };
  const { queryByText } = render(<MobileUpdateBanner />);
  await act(async () => {});
  expect(queryByText(/Yeni sürüm hazır/)).toBeNull();
});

it("Android DIŞI platformda bant hiç çizilmez", async () => {
  (Platform as { OS: string }).OS = "web";
  const { queryByText } = render(<MobileUpdateBanner />);
  await act(async () => {});
  expect(queryByText(/Yeni sürüm hazır/)).toBeNull();
});

it("REFAKTÖR KANITI: 'Güncelle' hâlâ indirip kurulumu açıyor", async () => {
  const { getByText } = render(<MobileUpdateBanner />);
  await waitFor(() => expect(getByText("Güncelle")).toBeTruthy());
  await act(async () => { fireEvent.press(getByText("Güncelle")); });
  await waitFor(() => expect(mockKur).toHaveBeenCalledWith("file:///cache/x.apk"));
});

it("REFAKTÖR KANITI: eksik inen paket mesajı bantta da AYNI", async () => {
  mockIndir.mockResolvedValue({ ok: false, hata: "boyut" });
  const { getByText } = render(<MobileUpdateBanner />);
  await waitFor(() => expect(getByText("Güncelle")).toBeTruthy());
  await act(async () => { fireEvent.press(getByText("Güncelle")); });
  await waitFor(() => expect(getByText(/İndirme eksik kaldı/)).toBeTruthy());
});
