// Author: mertaygn, cglrgrkn
/**
 * D1.E08 · İG-5.27 (İNCELEME-2 i5-F-2) — kabin yapılandırması yüklenemediğinde AI Hub Kedi Organ sonucu bunu SÖYLER.
 *
 * Backend (gömülü uç + GPU servisi) `kabin_uyarisi` döndürüyordu ama ekran alanı hiç okumuyordu: ölçüldü — yanıt uyarıyı
 * taşırken sonuç kutusu "3 organ bulundu … Organlar konumlandı" ve "(1.0, 2.0, 3.0) cm" gösteriyor, uyarı YOK.
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
jest.mock("@/services/config", () => ({ serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api" } }));
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
// Canlı döngü kare almasın: cameraRef hiç dolmaz (CameraView null) → capture erken döner.
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

import { AiHubScreen } from "@/screens/AiHubScreen";

const UYARI =
  "Kabin yapılandırması yüklenemedi — organ konumları KALİBRASYONSUZ (kabin koordinatı yok, güven sınırlı). " +
  "Kabin yapılandırma dosyasını (kurulum) kontrol edin ya da teknik desteğe başvurun.";

function yanit(uyari: string | null) {
  return {
    status: "success",
    n_organs: 3,
    pose_type: "lateral",
    pnp_residual_px: 2.1,
    image_base64: "OVERLAY",
    kabin_uyarisi: uyari,
    organs: Array.from({ length: 3 }, (_, i) => ({ name: `organ_${i}`, coord_3d_cm: [1, 2, 3], reliability: 0.25, calibrated: uyari === null })),
  };
}

async function analiz(uyari: string | null) {
  (global as any).fetch = jest.fn(async () => ({ ok: true, json: async () => yanit(uyari) }));
  const u = render(<AiHubScreen />);
  fireEvent.press(u.getAllByLabelText(/Kedi Organ/i)[0]);
  await act(async () => { fireEvent.press(u.getByRole("button", { name: "Galeriden Seç" })); });
  await act(async () => { fireEvent.press(u.getByRole("button", { name: "Organ Analizini Başlat" })); });
  await waitFor(() => expect(u.getByText(/3 organ bulundu/)).toBeTruthy());
  return u;
}

it("KRİTİK: kabin yapılandırması yüklenemediyse sonuç kutusu uyarıyı GÖSTERİR", async () => {
  const u = await analiz(UYARI);
  expect(u.getByText(new RegExp("Kabin yapılandırması yüklenemedi — organ konumları KALİBRASYONSUZ"))).toBeTruthy();
});

it("KARŞIT: alan yoksa (yapılandırma yüklendi) uyarı YOK", async () => {
  const u = await analiz(null);
  expect(u.queryByText(/Kabin yapılandırması yüklenemedi/)).toBeNull();
});
