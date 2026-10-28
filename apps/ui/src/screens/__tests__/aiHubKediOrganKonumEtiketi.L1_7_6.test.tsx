// Author: mertaygn, cglrgrkn
/**
 * L1-7.6 (DALGA-1 §7 · 1-D inc. 2 §10 #6) — AI Hub Kedi Organ: organ satırındaki konum KALİBRASYON DURUMUNU ve ÇERÇEVEYİ söyler.
 *
 * ÖLÇÜLEN KUSUR (HEAD `ebf1c3fe`): satır `coord_cabin_cm || coord_3d_cm || [0, 0, 0]` değerini her durumda "(x, y, z) cm" diye yazıyordu.
 * ArUco'suz (kalibrasyonsuz) karede gösterilen sayı GÖVDE-GÖRELİ `coord_3d_cm` idi ama kabin konumundan ayırt edilemiyordu; koordinat
 * yoksa "(0.0, 0.0, 0.0) cm" UYDURULUYORDU. Backend her organda `calibrated` alanını gönderiyor (ai_router `cat_organ` / GPU servisi).
 * SÖZLEŞME: değer AYNI (kabin varsa kabin, yoksa gövde-göreli; AI değeri değişmez); etiket: kabin + kalibre / kabin + kalibrasyon
 * doğrulanmadı (`calibrated` true DEĞİLSE — alan yoksa da) / gövde-göreli + kalibrasyonsuz / konum yok. TR + EN BAYT BAYT pinli.
 * ⚠️ DAVRANIŞSAL: GERÇEK ekran akışı (Kedi Organ → Galeriden Seç → Organ Analizini Başlat), yalnız `fetch` sahte.
 */
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async () => null),
  apiPost: jest.fn(async () => null),
  authHeaders: jest.fn(() => ({})),
  platformAlert: jest.fn(),
  platformConfirm: jest.fn(async () => true),
  AI_TIMEOUT_MS: 120000,
}));
jest.mock("@/services/config", () => ({ serviceConfig: { apiBaseUrl: "http://127.0.0.1:65530/api" } }));
jest.mock("@/components/ui/ToastProvider", () => {
  const fn = jest.fn();
  return { useToast: () => ({ showToast: fn }), __toast: fn };
});
jest.mock("@/context/UserModeContext", () => ({
  useUserMode: () => ({ userMode: "veterinarian", hasAiHub: true }),
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "v@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({ useOperator: () => ({ operatorEmail: "v@x.com" }) }));
jest.mock("@/context/EntitlementContext", () => ({ useEntitlement: () => ({ research: true }) }));
jest.mock("@/context/AppNavContext", () => ({
  useAppNav: () => ({ navigate: jest.fn(), selectedPatient: { id: 1, name: "Test Hasta" } }),
}));
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: null, wsConnected: true, aiVisionFresh: false }),
}));
jest.mock("@/components/domain/PatientGate", () => {
  const React = require("react");
  return { PatientGate: ({ children }: any) => React.createElement(React.Fragment, null, children) };
});
jest.mock("expo-camera", () => ({ CameraView: () => null, useCameraPermissions: () => [{ granted: true }, jest.fn()] }));
jest.mock("expo-audio", () => ({
  useAudioRecorder: () => ({ record: jest.fn(), stop: jest.fn(), uri: null }),
  RecordingPresets: { HIGH_QUALITY: {} },
  setAudioModeAsync: jest.fn(),
  requestRecordingPermissionsAsync: jest.fn(async () => ({ granted: true })),
}));
jest.mock("expo-image-picker", () => ({
  MediaTypeOptions: { Images: "Images" },
  launchImageLibraryAsync: jest.fn(async () => ({ canceled: false, assets: [{ uri: "file:///kedi.jpg" }] })),
  launchCameraAsync: jest.fn(async () => ({ canceled: true })),
}));
jest.mock("expo-image-manipulator", () => ({
  SaveFormat: { JPEG: "jpeg" },
  manipulateAsync: jest.fn(async (uri: string) => ({ uri, base64: "QUJD" })),
}));

import React from "react";
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";

import { AiHubScreen } from "@/screens/AiHubScreen";

const depo = { setItem: async () => undefined };

/** Backend `cat_organ` yanıt şekli (ai_router `organs_list`): her organda coord_3d_cm + calibrated; kabin yalnız perspektif çözümünde. */
const YANIT = {
  status: "success",
  n_organs: 6,
  pose_type: "lateral",
  pnp_residual_px: 2.1,
  image_base64: "OVERLAY",
  organs: [
    { name: "kalp", coord_3d_cm: [9, 9, 9], coord_cabin_cm: [1, 2.2, -3], reliability: 0.8, calibrated: true },
    { name: "dalak", coord_3d_cm: [9, 9, 9], coord_cabin_cm: [4, 5, 6], reliability: 0.7, calibrated: false },
    { name: "bobrek", coord_3d_cm: [-2, 2.5, 3], reliability: 0.25, calibrated: false },
    { name: "mide", reliability: 0.2, calibrated: false },
    // D67 orkestratör kolu: `calibrated` alanı YOK (eski yanıt) → "kalibre" iddia EDİLMEZ (`!== false` mutantı YAŞIYORDU).
    { name: "karaciger", coord_cabin_cm: [7, 8, 9], reliability: 0.6 },
    // D67 orkestratör kolu: boş kabin dizisi → koordinat YOK sayılır ("NaN" / 0 yazılmaz; uzunluk denetimi mutantı YAŞIYORDU).
    { name: "mesane", coord_cabin_cm: [], reliability: 0.5, calibrated: true },
  ],
};

async function analiz(modul: RegExp, galeri: string, baslat: string, bulundu: RegExp) {
  (global as any).fetch = jest.fn(async () => ({ ok: true, json: async () => YANIT }));
  const u = render(<AiHubScreen />);
  fireEvent.press(u.getAllByLabelText(modul)[0]);
  await act(async () => { fireEvent.press(u.getByRole("button", { name: galeri })); });
  await act(async () => { fireEvent.press(u.getByRole("button", { name: baslat })); });
  await waitFor(() => expect(u.getByText(bulundu)).toBeTruthy());
  return u;
}

afterEach(async () => {
  __bayrakTestiAyarla(null);
  await act(async () => {
    await dilSec("tr", depo);
  });
});

it("KRİTİK TR: ArUco'suz (gövde-göreli) konum 'kalibrasyonsuz' der; kabin konumu kalibre / doğrulanmadı ayrımı; koordinat yoksa 0 UYDURULMAZ", async () => {
  const u = await analiz(/Kedi Organ/i, "Galeriden Seç", "Organ Analizini Başlat", /6 organ bulundu/);
  expect(u.getByText("Kalp (1.0, 2.2, -3.0) cm · kabin konumu (ArUco ile kalibre)")).toBeTruthy();
  expect(u.getByText("Dalak (4.0, 5.0, 6.0) cm · kabin konumu — kalibrasyon doğrulanmadı")).toBeTruthy();
  expect(u.getByText("Böbrek (-2.0, 2.5, 3.0) cm · kedinin gövdesine göre — kalibrasyonsuz (kabin konumu değil)")).toBeTruthy();
  expect(u.getByText("Mide konum yok")).toBeTruthy();
  expect(u.getByText("Karaciğer (7.0, 8.0, 9.0) cm · kabin konumu — kalibrasyon doğrulanmadı")).toBeTruthy();
  expect(u.getByText("Mesane konum yok")).toBeTruthy();
  expect(u.queryAllByText(/NaN/)).toHaveLength(0);
  // Değer kaynağı DEĞİŞMEDİ: kabin varken gövde-göreli (9, 9, 9) gösterilmez; uydurma (0.0, 0.0, 0.0) yok.
  expect(u.queryAllByText(/\(9\.0, 9\.0, 9\.0\)/)).toHaveLength(0);
  expect(u.queryAllByText(/\(0\.0, 0\.0, 0\.0\)/)).toHaveLength(0);
});

it("KRİTİK EN: aynı dört durum İngilizce (çeviri anlamı birebir: uncalibrated / not verified / no position)", async () => {
  __bayrakTestiAyarla(true);
  await act(async () => {
    await dilSec("en", depo);
  });
  const u = await analiz(/Feline Organ/i, "Choose from Gallery", "Start Organ Analysis", /6 organs found/);
  expect(u.getByText("Heart (1.0, 2.2, -3.0) cm · cabin position (calibrated with ArUco)")).toBeTruthy();
  expect(u.getByText("Spleen (4.0, 5.0, 6.0) cm · cabin position — calibration not verified")).toBeTruthy();
  expect(u.getByText("Kidney (-2.0, 2.5, 3.0) cm · relative to the cat's body — uncalibrated (not a cabin position)")).toBeTruthy();
  expect(u.getByText("Stomach no position")).toBeTruthy();
  expect(u.getByText("Liver (7.0, 8.0, 9.0) cm · cabin position — calibration not verified")).toBeTruthy();
  expect(u.getByText("Bladder no position")).toBeTruthy();
});

// TUR 2 (çürütücü kolu): (a) `calibrated` alanı YOK (eski / devredilen yanıt) → kabin konumu "kalibre" İDDİA EDİLMEZ; (b) BOŞ / eksik kabin
// dizisi koordinat DEĞİLDİR → gövde-göreli değere düşer, "(NaN, NaN, NaN) cm · kabin konumu" çizilmez. Mutant `cur176_n2` (`uc` uzunluk
// denetimi silinir) bu dosyada ve aiHubScreen.I18N.P1'de YAŞIYORDU.
it("SINIR TR (tur 2): alan YOK → 'doğrulanmadı'; boş kabin dizisi → gövde-göreli (NaN yok)", async () => {
  const asil = YANIT.organs;
  (YANIT as { organs: unknown[] }).organs = [
    { name: "kalp", coord_3d_cm: [9, 9, 9], coord_cabin_cm: [1, 2.2, -3], reliability: 0.8 },
    { name: "dalak", coord_3d_cm: [-2, 2.5, 3], coord_cabin_cm: [], reliability: 0.7, calibrated: false },
    { name: "bobrek", coord_3d_cm: [4, 5, 6], coord_cabin_cm: [7, 8], reliability: 0.25, calibrated: true },
    { name: "mide", reliability: 0.2, calibrated: false },
  ];
  try {
    const u = await analiz(/Kedi Organ/i, "Galeriden Seç", "Organ Analizini Başlat", /4 organ bulundu/);
    expect(u.getByText("Kalp (1.0, 2.2, -3.0) cm · kabin konumu — kalibrasyon doğrulanmadı")).toBeTruthy();
    expect(u.getByText("Dalak (-2.0, 2.5, 3.0) cm · kedinin gövdesine göre — kalibrasyonsuz (kabin konumu değil)")).toBeTruthy();
    expect(u.getByText("Böbrek (4.0, 5.0, 6.0) cm · kedinin gövdesine göre — kalibrasyonsuz (kabin konumu değil)")).toBeTruthy();
    expect(u.queryAllByText(/NaN/)).toHaveLength(0);
  } finally {
    (YANIT as { organs: unknown[] }).organs = asil;
  }
});
