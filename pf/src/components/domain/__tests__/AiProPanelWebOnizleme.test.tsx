// Author: mertaygn, cglrgrkn
/**
 * B3 — AI PRO WEB HAZIRLIK "SİYAH EKRAN" (2026-09-03).
 *
 * ÖLÇÜLEN: web'de Başlat → hazırlık; kamera kutusu "AI Pro durdu." (placeholder `hazirlik`i yok
 * sayıyordu), şerit "Hayvan aranıyor…" (yalnız WS'ten okunuyordu; sunucu önizlemesi WS'e hiç kare
 * atmıyordu, /status `catDetected:true` dese bile), düğme 120 sn "Hazırlanıyor…" (sunucu kamerası
 * açılamayınca panel bunu öğrenemiyordu). Üçü AYNI ANDA ekrandaydı.
 *
 * ⚠️ Platform.OS="web" mock'lanır (IS_WEB import anında hesaplanır → mock ÖNCE olmalı).
 */
jest.mock("react-native", () => {
  const RN = jest.requireActual("react-native");
  RN.Platform.OS = "web";
  return RN;
});
let mockDurum: Record<string, unknown> = { active: false, localized: false };
let mockHazirlikYaniti: unknown = { status: "success" };
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async () => mockDurum),
  apiPost: jest.fn(async (yol: string) => (yol === "/ai/pro/hazirlik/baslat" ? mockHazirlikYaniti : { status: "success" })),
  authHeaders: jest.fn(() => ({})),
  platformAlert: jest.fn(),
  platformConfirm: jest.fn(async () => true),
  AI_TIMEOUT_MS: 120000,
}));
jest.mock("@/services/config", () => ({
  serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api" },
  getClientInstanceId: jest.fn(async () => "web-id"),
}));
let mockVision: unknown = undefined;
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: null, wsConnected: true, aiVisionData: mockVision, aiVisionFresh: false }),
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "v@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({ useOperator: () => ({ operatorEmail: "v@x.com" }) }));
jest.mock("expo-camera", () => {
  const React2 = require("react");
  return { CameraView: React2.forwardRef(() => null), useCameraPermissions: () => [{ granted: true }, jest.fn()] };
});

import { act, fireEvent, render } from "@testing-library/react-native";
import React from "react";

import { platformAlert } from "@/services/apiClient";

import { AiProPanel } from "../AiProPanel";

beforeEach(() => {
  jest.useFakeTimers();
  mockDurum = { active: false, localized: false };
  mockHazirlikYaniti = { status: "success" };
  mockVision = undefined;
  (platformAlert as jest.Mock).mockClear();
});
afterEach(() => { jest.useRealTimers(); });

async function baslat() {
  const u = render(<AiProPanel patientName="Tekir" />);
  await act(async () => {});
  await act(async () => { fireEvent.press(u.getByLabelText("AI Pro otonom seansı başlat")); });
  return u;
}
async function poll(u: ReturnType<typeof render>, n = 2) {
  for (let i = 0; i < n; i++) await act(async () => { jest.advanceTimersByTime(3000); await Promise.resolve(); });
  return u;
}

it("KRİTİK: hazırlıkta kamera kutusu 'AI Pro durdu.' DEMEZ (durdu ≠ aranıyor çelişkisi)", async () => {
  const u = await baslat();
  expect(u.queryByText("AI Pro durdu.")).toBeNull();
  expect(u.getByText(/Sunucu kamerası açılıyor/)).toBeTruthy();
  expect(u.getByText(/Hazırlanıyor/)).toBeTruthy();
});

it("KRİTİK: /status catDetected:true → şerit WS olmadan da 'Hayvan görünüyor, organ aranıyor'", async () => {
  const u = await baslat();
  mockDurum = { active: false, localized: false, catDetected: true };
  await poll(u);
  expect(u.queryByText(/Hayvan aranıyor/)).toBeNull();
  expect(u.getByText(/Hayvan görünüyor, Karaciğer|Hayvan görünüyor, Tüm Vücut/)).toBeTruthy();
});

it("KRİTİK: WS önizleme karesi (preview) gelince kutu GÖRÜNTÜ gösterir", async () => {
  mockVision = { imageBase64: "AAAA", preview: true, detected: false, catDetected: false };
  const u = await baslat();
  expect(u.queryByText("AI Pro durdu.")).toBeNull();
  expect(u.queryByText(/Sunucu kamerası açılıyor/)).toBeNull();
});

it("KRİTİK: sunucu kamerası AÇILAMAZSA (status hazirlikHata) hazırlık biter + NEDEN görünür + uyarı", async () => {
  const u = await baslat();
  expect(u.getByText(/Hazırlanıyor/)).toBeTruthy();
  mockDurum = { active: false, localized: false, hazirlikActive: false, hazirlikHata: "Sunucu kamerası açılamadı (VideoCapture(0))." };
  await poll(u);
  expect(u.queryByText(/Hazırlanıyor/)).toBeNull();               // düğme takılı değil
  expect(u.getByText(/AI Pro Başlat/)).toBeTruthy();
  expect(u.getByText(/Sunucu kamerası açılamadı/)).toBeTruthy();  // kamera kutusunda neden
  expect(platformAlert).toHaveBeenCalledWith("Sunucu kamerası başlatılamadı", expect.stringMatching(/kamera/));
});

it("KARŞIT-KANIT: salt hazirlikActive:false (hata metni YOK) hazırlığı KESMEZ (propose→durdur arası poll)", async () => {
  const u = await baslat();
  mockDurum = { active: false, localized: false, hazirlikActive: false, hazirlikHata: "" };
  await poll(u);
  expect(u.getByText(/Hazırlanıyor/)).toBeTruthy();
  expect(platformAlert).not.toHaveBeenCalled();
});

it("KARŞIT-KANIT: eski backend (alan yok) → eski davranış, hazırlık sürer", async () => {
  const u = await baslat();
  mockDurum = { active: false, localized: false };
  await poll(u, 3);
  expect(u.getByText(/Hazırlanıyor/)).toBeTruthy();
});

it("KRİTİK: /hazirlik/baslat sunucuya ULAŞMAZSA hazırlığa girilmez, neden kutuda", async () => {
  mockHazirlikYaniti = null;
  const u = await baslat();
  expect(u.queryByText(/Hazırlanıyor/)).toBeNull();
  expect(u.getByText(/Hazırlık komutu sunucuya ulaşmadı/)).toBeTruthy();
});
