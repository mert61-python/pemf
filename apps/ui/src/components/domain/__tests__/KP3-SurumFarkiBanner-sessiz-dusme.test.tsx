/**
 * KP-3 C · SurumFarkiBanner "sessiz düşme" kolları — her test bir DAVRANIŞ iddiası:
 *  - Uygulama sürümü okunamazsa (yerel sabitler modülü yok) başlık "bu sürüm → yeni" der (boş / "undefined" değil).
 *  - Kapatma kaydı OKUNAMAZSA (depolama arızası) bant yine gösterilir — "kapatılmamış" varsayılır (ertelenen güncelleme gizlenmez).
 *  - Güncelleme bilgisi alınamazsa (ağ yok) bant üretilmez ve çökmez.
 * SAHTE: canlı veri (seans yok) · AsyncStorage · expo-constants · mobileUpdate (girdi). GERÇEK: SurumFarkiBanner + i18n.
 * ⚠️ Sıra önemli: "sabitler okunamaz" İLK test (modül bir kez yüklenince önbelleğe alınır).
 */
import React from "react";
import { act, fireEvent, render } from "@testing-library/react-native";
import i18n from "i18next";

jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: { activeTreatment: { isActive: false } }, haveRealData: true }),
}));
let mockDepoAtar = false;
jest.mock("@react-native-async-storage/async-storage", () => ({
  getItem: jest.fn(async () => { if (mockDepoAtar) throw new Error("depo okunamadı (aparat)"); return null; }),
  setItem: jest.fn(async () => undefined),
}));
let mockSabitlerAtar = true;
jest.mock("expo-constants", () => {
  if (mockSabitlerAtar) throw new Error("yerel sabitler modülü yok (aparat)");
  return { default: { expoConfig: { version: "2.3.21" } } };
});
let mockDurum: () => Promise<unknown> = async () => ({ varMi: false });
jest.mock("@/services/mobileUpdate", () => ({
  guncellemeVarMi: jest.fn(() => mockDurum()),
  atlandiMi: jest.fn(() => true),
  mevcutVersionCode: jest.fn(() => 28),
}));

import { SurumFarkiBanner } from "@/components/domain/SurumFarkiBanner";

const T = (k: string, o?: object): string => (i18n.t as unknown as (k: string, o?: object) => string)(k, o);
const YENI = { version: "2.3.22", versionCode: 29, url: "u", sha256: "s", size: 1 };
async function bosalt() {
  await act(async () => { for (let i = 0; i < 4; i++) await Promise.resolve(); });
}

it("sürüm okunamazsa başlık 'bu sürüm → yeni' der", async () => {
  mockDurum = async () => ({ varMi: true, surum: YENI });
  const u = render(<SurumFarkiBanner />);
  expect(await u.findByText(T("bant.surumFarki.baslik", { mevcut: T("bant.surumFarki.buSurum"), yeni: "2.3.22" }))).toBeTruthy();
  mockSabitlerAtar = false;
});

it("kapatma kaydı okunamazsa bant yine gösterilir", async () => {
  mockDepoAtar = true;
  mockDurum = async () => ({ varMi: true, surum: YENI });
  const u = render(<SurumFarkiBanner />);
  expect(await u.findByText(/2\.3\.22/)).toBeTruthy();
  mockDepoAtar = false;
});

// KP-7 B (işlev ölçüsü): kapatma kaydı YAZILAMAZSA (depolama arızası) bant yine bu oturumda kapanır — dokunuş boşa gitmez, işlenmemiş
// ret yok (bir sonraki açılışta bant yeniden görünebilir: kayıt yok sayılır).
it("kapatma kaydı yazılamasa da bant bu oturumda kapanır", async () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const AS = require("@react-native-async-storage/async-storage") as { setItem: jest.Mock };
  AS.setItem.mockRejectedValueOnce(new Error("depo yazılamadı (aparat)"));
  mockDurum = async () => ({ varMi: true, surum: YENI });
  const u = render(<SurumFarkiBanner />);
  expect(await u.findByText(/2\.3\.22/)).toBeTruthy();
  await act(async () => {
    fireEvent.press(u.getByLabelText(T("bant.surumFarki.kapatEtiketi")));
  });
  await bosalt();
  expect(AS.setItem).toHaveBeenCalled();
  expect(u.queryByText(/2\.3\.22/)).toBeNull();
});

it("güncelleme bilgisi alınamazsa bant yok, çökme yok", async () => {
  mockDurum = async () => { throw new TypeError("Network request failed"); };
  const u = render(<SurumFarkiBanner />);
  await bosalt();
  expect(u.toJSON()).toBeNull();
});
