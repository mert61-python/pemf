/**
 * KP-4 B1 · src/components/domain/MobileUpdateBanner.tsx — bandın "bildirimi kapat" düğmesi bandı bu açılış için GİZLER ve indirme
 * BAŞLATMAZ (kapatmak güncellemeyi kabul etmek değildir). Ertelemenin sürüme özgü kalıcılığı `MobileUpdateBanner.test` konusu.
 * SAHTE: mobil güncelleme servisinin ağ / dosya uçları (sürüm denetimi, indirme, kurulum) — erteleme bayrağı GERÇEK; canlı veri.
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
import { Platform } from "react-native";
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";
import i18n from "i18next";

import { MobileUpdateBanner } from "@/components/domain/MobileUpdateBanner";
import { apkIndir, guncellemeVarMi, _atlamayiSifirla, _indirmeyiSifirla } from "@/services/mobileUpdate";

const T = (k: string, o?: object): string => (i18n.t as unknown as (k: string, o?: object) => string)(k, o);
const SURUM = { version: "2.5.0", versionCode: 31, url: "https://github.com/o/r/releases/download/t/PEMF_Vet_Mobil.apk",
  sha256: "b".repeat(64), size: 1000 };
let eskiOS: string;

beforeEach(() => {
  jest.clearAllMocks();
  _atlamayiSifirla();
  _indirmeyiSifirla();
  eskiOS = Platform.OS;
  (Platform as { OS: string }).OS = "android";
  (guncellemeVarMi as jest.Mock).mockResolvedValue({ varMi: true, surum: SURUM });
});
afterEach(() => {
  (Platform as { OS: string }).OS = eskiOS;
});

it("KRİTİK: 'bildirimi kapat' bandı gizler ve indirme BAŞLATMAZ", async () => {
  const u = render(<MobileUpdateBanner />);
  await waitFor(() => expect(u.getByText(T("guncelleme.hazir", { version: "2.5.0" }))).toBeTruthy());
  await act(async () => { fireEvent.press(u.getByLabelText(T("guncelleme.bildirimiKapat"))); });
  expect(u.queryByText(T("guncelleme.hazir", { version: "2.5.0" }))).toBeNull();
  expect(apkIndir).not.toHaveBeenCalled();
});
