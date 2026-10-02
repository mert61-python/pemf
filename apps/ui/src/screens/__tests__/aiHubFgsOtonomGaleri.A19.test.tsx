// Author: mertaygn, cglrgrkn
/**
 * D1.88 · B-6.30 · A-19 (+ D1.E09 · İG-5.31) — FGS ekranı galeri fotoğrafıyla cihazı SÜRDÜRMEZ.
 *
 * Eski akış: "Otonom Biofeedback" açık + Galeriden Seç + Analiz → `platformConfirm("Cihaz otonom sürülsün mü?")` →
 * "Evet" → gövdede `auto_adjust=true` → backend 30 dk 8 bobinli seans açıyordu. Onay penceresi hekim onayı → AI Pro
 * mühür akışı DEĞİLDİR (sahip kararı A-19). Artık: istek her zaman `auto_adjust=false`, onay penceresi yok, kullanıcı
 * Kontrol → AI Pro'ya yönlendirilir. D1.E09: güven kanalı olmayan modelde sonuç kartı bunu söyler.
 *
 * ⚠️ DAVRANIŞSAL: gerçek ekran ve akış; yalnız ağ (`fetch`), görsel seçici ve onay penceresi sahte. Kamera AÇILMAZ.
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
jest.mock("@/services/config", () => ({
  serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api" },
}));
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
  launchCameraAsync: jest.fn(),
}));
jest.mock("expo-image-manipulator", () => ({
  SaveFormat: { JPEG: "jpeg" },
  manipulateAsync: jest.fn(async (uri: string) => ({ uri, base64: "QUJD" })),
}));

import React from "react";
import { act, fireEvent, render } from "@testing-library/react-native";

import { platformConfirm } from "@/services/apiClient";
import { AiHubScreen } from "@/screens/AiHubScreen";

// eslint-disable-next-line @typescript-eslint/no-require-imports
const { __toast: showToast } = require("@/components/ui/ToastProvider");

function yanit(ek: object = {}) {
  return {
    status: "success",
    detected: true,
    fgs_total: 3,
    pain_level: "Mild",
    raw_fgs: { action_units: {} },
    action_units: {},
    hw_status: "idle",
    hw_params: {},
    ...ek,
  };
}

function govdeAlani(fd: any, ad: string): unknown {
  if (typeof fd?.get === "function") return fd.get(ad); // standart FormData (jest/node)
  const parcalar: any[] = typeof fd?.getParts === "function" ? fd.getParts() : fd?._parts || [];
  const p = parcalar.find((x: any) => (Array.isArray(x) ? x[0] : x?.fieldName) === ad);
  return Array.isArray(p) ? p[1] : p?.string;
}

async function galeridenAnaliz(otonom: boolean, ek: object = {}) {
  (global as any).fetch = jest.fn(async () => ({ ok: true, json: async () => yanit(ek) }));
  const u = render(<AiHubScreen />);
  fireEvent.press(u.getAllByLabelText("Yüz Ağrısı (FGS)")[0]);
  if (otonom) {
    const anahtar = u.getByLabelText("Otonom biofeedback");
    fireEvent.press(anahtar);
    expect(anahtar.props.accessibilityState?.checked).toBe(true); // ARA DOĞRULAMA: doğru anahtar
  }
  await act(async () => {
    fireEvent.press(u.getByText("Galeriden Seç"));
  });
  await act(async () => {
    fireEvent.press(u.getByText("AI Analizini Başlat"));
  });
  await act(async () => {});
  const cagrilar = (global as any).fetch.mock.calls.filter((c: any[]) => String(c[0]).endsWith("/ai/vision/landmark"));
  expect(cagrilar).toHaveLength(1); // ARA DOĞRULAMA: gerçek akış istek attı
  return { u, govde: cagrilar[0][1].body };
}

/** Ekranda görünen metin: iç içe <Text> parçaları bitişik birleşir. */
function duz(d: any): string {
  if (d == null || typeof d === "boolean") return "";
  if (typeof d === "string" || typeof d === "number") return String(d);
  if (Array.isArray(d)) return d.map(duz).join("");
  const ic = (d.children || []).map(duz).join("");
  return d.type === "Text" ? ic : ` ${ic} `;
}

beforeEach(() => {
  (platformConfirm as jest.Mock).mockClear();
  showToast.mockClear();
});

it("KRİTİK: Otonom açık + galeri fotoğrafı → onay penceresi YOK, gövdede auto_adjust 'true' YOK, AI Pro'ya yönlendirir", async () => {
  const { u, govde } = await galeridenAnaliz(true);
  expect(govdeAlani(govde, "auto_adjust")).toBe("false");
  expect(platformConfirm).not.toHaveBeenCalled();
  const metinler = showToast.mock.calls.map((c: unknown[]) => String(c[0]));
  expect(metinler.some((m: string) => /AI Pro/.test(m) && /onay/i.test(m))).toBe(true);
  expect(u.getByLabelText("Otonom biofeedback").props.accessibilityState?.checked).toBe(false);
  expect(duz(u.toJSON())).not.toMatch(/otonom olarak sürülüyor/);
});

it("KARŞIT: Otonom kapalı salt analiz aynen çalışır (gövde false, skor görünür)", async () => {
  const { u, govde } = await galeridenAnaliz(false);
  expect(govdeAlani(govde, "auto_adjust")).toBe("false");
  expect(duz(u.toJSON())).toMatch(/FGS Skoru: 3 \/ 10/);
});

it("KRİTİK E09: güven kanalı olmayan modelde sonuç kartı örtü uyarısını gösterir", async () => {
  const { u } = await galeridenAnaliz(false, { nokta_gorunurlugu_dogrulanmadi: true });
  expect(duz(u.toJSON())).toMatch(/görünürlüğünü bildirmiyor/);
});

it("KARŞIT E09: güven kanalı olan modelde uyarı YOK", async () => {
  const { u } = await galeridenAnaliz(false, { nokta_gorunurlugu_dogrulanmadi: false });
  expect(duz(u.toJSON())).not.toMatch(/görünürlüğünü bildirmiyor/);
});

it("KRİTİK E09 (1-D inceleme i3-F-6): FGS 0 ('ağrı yok') iken de örtü uyarısı görünür", async () => {
  // Örtü en yanıltıcı olduğu yerde: örtülü kulak/göz skoru DÜŞÜRÜR → 0 / 10 "ağrı yok" güvencesi. Uyarı skora bağlanmaz.
  const { u } = await galeridenAnaliz(false, { fgs_total: 0, pain_level: "None", nokta_gorunurlugu_dogrulanmadi: true });
  const metin = duz(u.toJSON());
  expect(metin).toMatch(/FGS Skoru: 0 \/ 10/); // ARA DOĞRULAMA: kart çizildi
  expect(metin).toMatch(/görünürlüğünü bildirmiyor/);
});
