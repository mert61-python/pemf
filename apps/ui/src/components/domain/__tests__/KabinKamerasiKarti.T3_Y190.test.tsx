// Author: mertaygn, cglrgrkn
/**
 * T3 · Y190 (sahip 2026-10-24: "kamera seçimi de burada olmalı, ayarlar içinde değil") — kabin kamerası seçimi AI Pro panelinde
 * (petri / fantom analiz panelleri: `screens/__tests__/petriFantomCanli.T3_Y190.web.test.tsx`), Ayarlar'dan kalktı
 * (`screens/__tests__/SettingsKabinKamerasiYok.T3_Y190.web.test.tsx`). Bölüm kilitliyken (hazırlık / seans / canlı) tarama ve
 * seçim YAPILMAZ (kamerayı tutan oturumla çakışır); kilitsiz tarama + seçim sunucuya gider (karşıt). Platform.OS="web".
 */
jest.mock("react-native", () => {
  const RN = jest.requireActual("react-native");
  RN.Platform.OS = "web";
  return RN;
});
const mockApiPost = jest.fn(async (yol: string, _g?: unknown) =>
  yol === "/settings/kabin-kamerasi/tara"
    ? { kameralar: [{ indeks: 1, genislik: 1920, yukseklik: 1080, onizleme: null }], secili: null }
    : yol === "/settings/kabin-kamerasi"
      ? { secili: { indeks: 1, kaynak: "ayar" } }
      : { status: "success" },
);
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async (yol: string) =>
    yol === "/ai/hazirlik"
      ? { moduller: [{ modul: "em_fantom", hazir: true }, { modul: "em_petri", hazir: true }, { modul: "petri_yolo", hazir: true }] }
      : yol === "/settings/kabin-kamerasi"
        ? { secili: null }
        : { active: false, localized: false },
  ),
  apiPost: (yol: string, g?: unknown) => mockApiPost(yol, g),
  authHeaders: jest.fn(() => ({})),
  platformAlert: jest.fn(),
  platformConfirm: jest.fn(async () => true),
  AI_TIMEOUT_MS: 120000,
}));
// ⚠️ Adres nesnesi fabrikada (içe aktarımlar fabrikadan ÖNCE değerlendirilir; dışarıdaki bir `const` o anda henüz tanımsızdır →
// `backendBuMakinede()` sessizce false döner ve kapı KÖR kalırdı — ölçüldü). Testler içe aktarılan nesneyi değiştirir.
jest.mock("@/services/config", () => ({
  serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api" },
  getClientInstanceId: jest.fn(async () => "web-id"),
}));
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: jest.fn() }) }));
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: null, wsConnected: true, aiVisionData: undefined, aiVisionFresh: false }),
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "a@x.com" } }) }));
jest.mock("@/context/AppNavContext", () => ({
  useAppNav: () => ({ navigateTo: jest.fn(), selectedPatient: null, setSelectedPatient: jest.fn(), aiProModeli: "", setAiProModeli: jest.fn() }),
}));
jest.mock("@/context/OperatorContext", () => ({ useOperator: () => ({ operatorEmail: "a@x.com" }) }));
jest.mock("expo-camera", () => {
  const React2 = require("react");
  return { CameraView: React2.forwardRef(() => null), useCameraPermissions: () => [{ granted: true }, jest.fn()] };
});

import { act, fireEvent, render, waitFor } from "@testing-library/react-native";
import React from "react";

import { serviceConfig } from "@/services/config";

import { AiProPanel } from "../AiProPanel";
import { KabinKamerasiKarti } from "../KabinKamerasiKarti";

beforeEach(() => {
  mockApiPost.mockClear();
  (serviceConfig as { apiBaseUrl: string }).apiBaseUrl = "http://127.0.0.1:8000/api";
});

it("KRİTİK: AI Pro panelinde (bu makinede) 'Kabin kamerası' bölümü VAR — kedi ekranında da (kamera her modelde kabin kamerası)", async () => {
  const u = render(<AiProPanel patientName="Tekir" />);
  await act(async () => {});
  expect(u.getByTestId("kabin-kamerasi-tara")).toBeTruthy();
  const a = render(<AiProPanel patientName="Örnek-1" secilebilirModeller={["fantom", "petri"]} kullaniciKipi="researcher" />);
  await act(async () => {});
  expect(a.getAllByTestId("kabin-kamerasi-tara").length).toBeGreaterThan(0);
});

it("KARŞIT: backend başka makinedeyse (LAN) AI Pro panelinde kabin kamerası bölümü YOK", async () => {
  (serviceConfig as { apiBaseUrl: string }).apiBaseUrl = "http://192.168.1.50:8000/api";
  const u = render(<AiProPanel patientName="Tekir" />);
  await act(async () => {});
  expect(u.queryByTestId("kabin-kamerasi-tara")).toBeNull();
});

it("KRİTİK: KİLİTLİ bölümde tarama ve seçim sunucuya GİTMEZ; kilitsizde gider (karşıt)", async () => {
  const k = render(<KabinKamerasiKarti kilitli />);
  await act(async () => {});
  await act(async () => { fireEvent.press(k.getByTestId("kabin-kamerasi-tara")); });
  expect(mockApiPost).not.toHaveBeenCalled();
  k.unmount();
  const u = render(<KabinKamerasiKarti />);
  await act(async () => {});
  await act(async () => { fireEvent.press(u.getByTestId("kabin-kamerasi-tara")); });
  await waitFor(() => u.getByTestId("kabin-kamerasi-sec-1"));
  await act(async () => { fireEvent.press(u.getByTestId("kabin-kamerasi-sec-1")); });
  expect(mockApiPost.mock.calls.map((c) => c[0])).toEqual(["/settings/kabin-kamerasi/tara", "/settings/kabin-kamerasi"]);
  expect(String(u.getByTestId("kabin-kamerasi-secili").props.children)).toContain("Kamera 1");
});
