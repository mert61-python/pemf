// Author: mertaygn, cglrgrkn
/**
 * B1-organ-canli-kalinti — Kedi Organ modülünde galeri-fotoğrafı analizi sonrası "Canlı Kamera"ya
 * geçince ESKİ fotoğrafın sonucu (overlay image_base64 + "10 ORGAN" rozeti + organ listesi)
 * canlı kadrajın üstünde KALIYORDU. Kök: `toggleLive` yalnız DURDURURKEN (`!next`) sıfırlıyordu;
 * başlatırken hiçbir state'e dokunmuyordu (AiHubScreen.tsx CatOrganModule.toggleLive).
 *
 * ⚠️ Test DAVRANIŞSAL: gerçek akış (galeri → analiz → canlı) sürülür, kaynakta desen aranmaz.
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

const ORGAN_YANITI = {
  status: "success",
  n_organs: 10,
  pose_type: "lateral",
  pnp_residual_px: 2.1,
  image_base64: "ESKI_FOTO_OVERLAY",
  organs: Array.from({ length: 10 }, (_, i) => ({ name: `organ_${i}`, coord_3d_cm: [1, 2, 3], reliability: 0.8 })),
};

let fetchMock: jest.Mock;
beforeEach(() => {
  fetchMock = jest.fn(async () => ({ ok: true, json: async () => ORGAN_YANITI }));
  (global as any).fetch = fetchMock;
});

/** Gerçek akış: modülü aç → galeriden seç → analiz → sonuç gelsin. */
async function fotoAnaliziYap() {
  const u = render(<AiHubScreen />);
  fireEvent.press(u.getAllByLabelText(/Kedi Organ/i)[0]);
  await act(async () => { fireEvent.press(u.getByRole("button", { name: "Galeriden Seç" })); });
  await act(async () => { fireEvent.press(u.getByRole("button", { name: "Organ Analizini Başlat" })); });
  await waitFor(() => expect(u.getByText(/10 organ bulundu/)).toBeTruthy());
  expect(fetchMock).toHaveBeenCalledTimes(1);
  return u;
}

it("B1: Canlı Kamera'ya geçiş, önceki fotoğrafın sonucunu (rozet + overlay + liste) SIFIRLAR", async () => {
  const u = await fotoAnaliziYap();

  await act(async () => { fireEvent.press(u.getByRole("button", { name: "Canlı Kamera" })); });

  // Rozet taze olmalı: "ORGAN ARANIYOR…" (eski "10 ORGAN" DEĞİL)
  expect(u.queryByText("10 ORGAN")).toBeNull();
  expect(u.getByText("ORGAN ARANIYOR…")).toBeTruthy();
  // Eski overlay canlı kadrajın üstüne çizilmemeli
  const eskiOverlay = u.UNSAFE_queryAllByType(require("react-native").Image)
    .filter((n: any) => String(n.props?.source?.uri || "").includes("ESKI_FOTO_OVERLAY"));
  expect(eskiOverlay).toHaveLength(0);
  // Eski sonuç kutusu (organ listesi) da gitmeli
  expect(u.queryByText(/10 organ bulundu/)).toBeNull();
  // Canlı döngü henüz kare üretmedi → backend'e YENİ çağrı yok (kalıntı taze analizden gelemez)
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

it("B1-tutarlılık: Canlıyı Durdur → statik ekran boş başlar (önceki fotoğraf geri gelmez)", async () => {
  const u = await fotoAnaliziYap();
  await act(async () => { fireEvent.press(u.getByRole("button", { name: "Canlı Kamera" })); });
  await act(async () => { fireEvent.press(u.getByRole("button", { name: "Canlıyı Durdur" })); });
  expect(u.getByText("Görüntü seçilmedi")).toBeTruthy();
  expect(u.queryByText(/10 organ bulundu/)).toBeNull();
});
