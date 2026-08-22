// Author: mertaygn, cglrgrkn
/**
 * SURUM FARKI BANDI davranis kilidi (2026-08-22).
 *
 * Uc pazarlik-edilemez davranis:
 *  1. Telefon/cihaz surumu FARKLIYSA bant gorunur (fark artik sessiz degil).
 *  2. SEANS SURERKEN bant GOSTERILMEZ (bobinler hastanin uzerindeyken operatorun ekrani
 *     yonetimsel uyariyla bolunemez — RecoveryCodeBanner ilkesi).
 *  3. Gercek veri yokken (cihaz surumu bilinmiyor) sahte "fark var" uyarisi URETILMEZ.
 */
import React from "react";
import { act, render, waitFor } from "@testing-library/react-native";

let mockSnapshot: Record<string, unknown> = {};
let mockHaveRealData = true;
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: mockSnapshot, haveRealData: mockHaveRealData }),
}));
jest.mock("@react-native-async-storage/async-storage", () => ({
  getItem: jest.fn(async () => null),
  setItem: jest.fn(async () => undefined),
}));
jest.mock("expo-constants", () => ({ default: { expoConfig: { version: "2.3.20" } } }));

import { SurumFarkiBanner } from "@/components/domain/SurumFarkiBanner";

function kur(cihazSurumu: string, seansAktif: boolean, gercekVeri = true) {
  mockSnapshot = {
    system: { softwareVersion: cihazSurumu },
    activeTreatment: { isActive: seansAktif },
  };
  mockHaveRealData = gercekVeri;
  return render(<SurumFarkiBanner />);
}

it("KRITIK: surumler farkliyken bant gorunur ve iki surumu de soyler", async () => {
  const { findByText } = kur("1.9.18", false);
  const baslik = await findByText(/2\.3\.20.*1\.9\.18/);
  expect(baslik).toBeTruthy();
});

// ⚠️ NEGATIF TESTLERDE ONCE YUKLEME BITIRILIR (mutasyon M85 ilk yazimda KACTI): bant,
// AsyncStorage yuklemesi bitene kadar ZATEN null cizer; `waitFor(toJSON()===null)` daha
// yukleme baslamadan trivially geciyordu. Once async yuklemeyi bosalt, SONRA null oldugunu olc.
async function yuklemeyiBitir() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

it("KRITIK: SEANS SURERKEN bant GOSTERILMEZ (ekran bolunmez)", async () => {
  const { queryByText, toJSON } = kur("1.9.18", true);
  await yuklemeyiBitir();
  expect(toJSON()).toBeNull();
  expect(queryByText(/Sürümler farklı/)).toBeNull();
});

it("KARSIT-KANIT: gercek veri yokken sahte uyari URETILMEZ", async () => {
  const { toJSON } = kur("", false, false);
  await yuklemeyiBitir();
  expect(toJSON()).toBeNull();
});
