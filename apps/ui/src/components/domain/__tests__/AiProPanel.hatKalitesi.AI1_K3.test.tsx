/**
 * AI1.K3 — AI Pro güven dökümü kedi organ hattının KALİTE ara çıktılarını da söyler (hoca kedi organ v2 `ara_ciktilar`).
 *
 * Backend (`ai_router._hat_dokumu`) güven dökümüne poz türü, PnP (keypoint) uyum hatası, ayna uyarısı ve anatomik kontrol
 * sonucunu ekler. Panel bunları Türkçe gösterir; sorun varsa operatöre NE YAPACAĞINI söyler. Eski backend alanları göndermez →
 * döküm cümlesi eskisi gibi kalır. Yalnız gösterim: güven/sürüş değişmez.
 *
 * ⚠️ Platform.OS="web" mock'lanır (IS_WEB import anında hesaplanır → mock ÖNCE olmalı). Kurulum AiProPanelWeb.test.tsx ile aynı.
 */
jest.mock("react-native", () => {
  const RN = jest.requireActual("react-native");
  RN.Platform.OS = "web";
  return RN;
});

let mockDurum: Record<string, unknown> = { active: false, localized: false };
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async () => mockDurum),
  apiPost: jest.fn(async () => ({ status: "success" })),
  authHeaders: jest.fn(() => ({})),
  platformAlert: jest.fn(),
  platformConfirm: jest.fn(async () => true),
  AI_TIMEOUT_MS: 120000,
}));
jest.mock("@/services/config", () => ({
  serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api" },
  getClientInstanceId: jest.fn(async () => "web-id"),
}));
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: null, wsConnected: true, aiVisionData: null, aiVisionFresh: false }),
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "v@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({ useOperator: () => ({ operatorEmail: "v@x.com" }) }));
jest.mock("expo-camera", () => {
  const React2 = require("react");
  return {
    CameraView: React2.forwardRef((_p: unknown, _ref: unknown) => null),
    useCameraPermissions: () => [{ granted: true }, jest.fn()],
  };
});

import { act, render } from "@testing-library/react-native";
import React from "react";

import { AiProPanel } from "../AiProPanel";

const BILESENLER = { pose_confidence: 0.7, depth_factor: 0.95, mask_factor: 1.0, uncertainty_factor: 0.93, calibration_cap: null };

beforeEach(() => {
  jest.useFakeTimers();
});
afterEach(() => {
  jest.useRealTimers();
});

async function dokumSatiri(guvenDokumu: Record<string, unknown>) {
  mockDurum = { active: false, localized: true, reliability: 0.62, guvenDokumu };
  const u = render(<AiProPanel patientName="Tekir" />);
  await act(async () => {});
  for (let i = 0; i < 2; i++) {
    await act(async () => {
      jest.advanceTimersByTime(3000);
      await Promise.resolve();
    });
  }
  return String(u.getByText(/Güven dökümü:/).props.children);
}

it("KRİTİK K3: poz türü Türkçe, PnP uyum hatası, ayna ve anatomik tutarsızlık EYLEMİYLE gösterilir", async () => {
  const s = await dokumSatiri({
    ...BILESENLER,
    poz_turu: "sphinx",
    pnp_hata_px: 119.2,
    pnp_hata_cm: 2.58,
    ayna_uyarisi: true,
    anatomik_gecti: false,
    anatomik_skor: 0.667,
  });
  expect(s).toContain("poz %70");
  expect(s).toContain("poz türü Sfenks (oturmuş, önden)");
  // AII-2.7: çözünürlükten bağımsız ≈ cm; px (kamerayı ölçen sayı) gösterilmez.
  expect(s).toContain("PnP uyum hatası ≈ 2,6 cm");
  expect(s).not.toContain("px");
  expect(s).toContain("sağ-sol (ayna) belirsizliği — kamerayı biraz çevirip açıyı değiştirin");
  expect(s).toContain("anatomik tutarsızlık — organ yerleşimi doğrulanamadı; açıyı değiştirip yeniden konumlayın");
});

it("KARŞIT K3: anatomik kontrol geçti ve ayna yok → uyarı/eylem metni YOK", async () => {
  const s = await dokumSatiri({ ...BILESENLER, poz_turu: "lateral", pnp_hata_px: 42.0, ayna_uyarisi: false, anatomik_gecti: true });
  expect(s).toContain("poz türü Yandan (lateral)");
  expect(s).toContain("anatomik kontrol geçti");
  expect(s).not.toContain("tutarsızlık");
  expect(s).not.toContain("ayna");
});

it("KARŞIT AII-2.7: ölçek yoksa (yalnız px — eski GPU servisi) PnP sayısı GÖSTERİLMEZ, diğer hat metinleri kalır", async () => {
  const s = await dokumSatiri({ ...BILESENLER, poz_turu: "lateral", pnp_hata_px: 231.2, pnp_hata_cm: null, anatomik_gecti: true });
  expect(s).toContain("poz türü Yandan (lateral)");
  expect(s).toContain("anatomik kontrol geçti");
  expect(s).not.toContain("PnP");
  expect(s).not.toContain("231");
});

it("KARŞIT K3: eski backend (hat alanları YOK) → döküm cümlesi eskisi gibi", async () => {
  const s = await dokumSatiri({ ...BILESENLER });
  expect(s).toContain("poz %70");
  expect(s).not.toContain("poz türü");
  expect(s).not.toContain("PnP");
  expect(s).not.toContain("anatomik");
});
