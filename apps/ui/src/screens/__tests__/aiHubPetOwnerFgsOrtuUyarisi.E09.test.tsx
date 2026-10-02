// Author: mertaygn, cglrgrkn
/**
 * D1.E09 (İG-5.31) · 1-D inceleme i3-F-2 — örtü uyarısı HAYVAN SAHİBİ (pet_owner) FGS kartında da görünür.
 *
 * Ölçülen kusur: uyarı yalnız hekim/araştırma `VisionModule` kartına eklenmişti; aynı uç (`/ai/vision/landmark`) ve aynı
 * yanıt alanıyla (`nokta_gorunurlugu_dogrulanmadi: true`, FGS 0) hayvan sahibi kartı "Oldukça rahat görünüyor!" diyor,
 * uyarı göstermiyordu — hekimsiz kullanıcıya örtülü yüzde uyarısız "ağrı yok" güvencesi.
 *
 * ⚠️ DAVRANIŞSAL: gerçek ekran akışı (pet_owner → Galeriden Seç → Teşhis Et); yalnız ağ (`fetch`), görsel seçici ve
 * bağlamlar sahte. Kamera AÇILMAZ.
 */
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async () => null),
  apiPost: jest.fn(async () => null),
  authHeaders: jest.fn(() => ({})),
  platformAlert: jest.fn(),
  platformConfirm: jest.fn(async () => true),
  aiHataMesaji: jest.fn(() => "hata"),
  AI_TIMEOUT_MS: 120000,
}));
jest.mock("@/services/config", () => ({ serviceConfig: { apiBaseUrl: "http://127.0.0.1:65530/api" } }));
jest.mock("@/components/ui/ToastProvider", () => {
  const fn = jest.fn();
  return { useToast: () => ({ showToast: fn }), __toast: fn };
});
jest.mock("@/context/UserModeContext", () => ({
  useUserMode: () => ({ userMode: "pet_owner", hasAiHub: false }),
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "s@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({
  useOperator: () => ({ operatorEmail: "s@x.com" }),
  useOperatorOptional: () => ({ operatorEmail: "s@x.com" }),
}));
jest.mock("@/context/EntitlementContext", () => ({ useEntitlement: () => ({ research: false }) }));
jest.mock("@/context/AppNavContext", () => ({
  useAppNav: () => ({ navigate: jest.fn(), selectedPatient: { id: 1, name: "Pamuk" } }),
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
  launchCameraAsync: jest.fn(),
}));
jest.mock("expo-image-manipulator", () => ({
  SaveFormat: { JPEG: "jpeg" },
  manipulateAsync: jest.fn(async (uri: string) => ({ uri, base64: "QUJD" })),
}));

import React from "react";
import { act, fireEvent, render } from "@testing-library/react-native";

import { AiHubScreen } from "@/screens/AiHubScreen";

function duz(d: any): string {
  if (d == null || typeof d === "boolean") return "";
  if (typeof d === "string" || typeof d === "number") return String(d);
  if (Array.isArray(d)) return d.map(duz).join("");
  const ic = (d.children || []).map(duz).join("");
  return d.type === "Text" ? ic : ` ${ic} `;
}

async function sahipAnalizi(ek: object) {
  (global as any).fetch = jest.fn(async () => ({
    ok: true,
    json: async () => ({
      status: "success", detected: true, fgs_total: 0, pain_level: "None",
      raw_fgs: { action_units: {} }, action_units: {}, hw_status: "idle", hw_params: {}, ...ek,
    }),
  }));
  const u = render(<AiHubScreen />);
  // Ekran önceki testin görselini (modül düzeyi önbellek) koruyabilir → "Yeni Fotoğraf" ile girdi temizlenir.
  if (u.queryAllByText("Galeriden Seç").length === 0) {
    await act(async () => { fireEvent.press(u.getAllByText("Yeni Fotoğraf")[0]); });
  }
  await act(async () => { fireEvent.press(u.getAllByText("Galeriden Seç")[0]); });
  await act(async () => { fireEvent.press(u.getByText("Teşhis Et")); });
  await act(async () => {});
  const cagrilar = (global as any).fetch.mock.calls.filter((c: any[]) => String(c[0]).endsWith("/ai/vision/landmark"));
  expect(cagrilar).toHaveLength(1); // ARA DOĞRULAMA: gerçek akış istek attı
  const metin = duz(u.toJSON());
  expect(metin).toMatch(/Ağrı Skoru \(FGS\):/); // ARA DOĞRULAMA: sahip kartı çizildi
  return metin;
}

it("KRİTİK E09: güven kanalı olmayan modelde hayvan sahibi kartı (FGS 0 'ağrı yok') örtü uyarısını gösterir", async () => {
  const metin = await sahipAnalizi({ nokta_gorunurlugu_dogrulanmadi: true });
  expect(metin).toMatch(/Ağrı Skoru \(FGS\):\s*0 \/ 10/);
  expect(metin).toMatch(/görünürlüğünü bildirmiyor/);
});

it("KRİTİK E09: ağrı belirtili skorda (FGS 4) da uyarı görünür", async () => {
  const metin = await sahipAnalizi({ fgs_total: 4, pain_level: "Moderate", nokta_gorunurlugu_dogrulanmadi: true });
  expect(metin).toMatch(/görünürlüğünü bildirmiyor/);
});

it("KARŞIT E09: güven kanalı olan modelde hayvan sahibi kartında uyarı YOK", async () => {
  const metin = await sahipAnalizi({ nokta_gorunurlugu_dogrulanmadi: false });
  expect(metin).not.toMatch(/görünürlüğünü bildirmiyor/);
});

it("KARŞIT E09: yüz tespit edilemediyse (skor '—') örtü uyarısı gösterilmez", async () => {
  const metin = await sahipAnalizi({ detected: false, fgs_total: null, nokta_gorunurlugu_dogrulanmadi: false });
  expect(metin).not.toMatch(/görünürlüğünü bildirmiyor/);
});
