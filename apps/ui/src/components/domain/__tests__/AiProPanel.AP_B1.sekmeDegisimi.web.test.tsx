// Author: mertaygn, cglrgrkn
/**
 * AP · B1 (istem 48, tezgâh 13 Kasım 2026 16:18:18) — S-AP.1 sahip kararı "Seans sürsün": AI Pro sürerken Sensörler'e (ya da Kontrol'deki
 * başka sekmeye) geçmek seansı KESMEZ; dönünce panel durumu geri gelir.
 *  · WEB / masaüstü: panel sökülünce kendi seansımıza `/ai/pro/stop` ve önizlemeye `/hazirlik/durdur` GİTMEZ (kayan ACİL DURDUR her
 *    rotada var — eski "başsız bobin" gerekçesi geçersiz).
 *  · Yeniden açılınca: sürmekte olan web önizlemesi hazırlık olarak (model, hedef, kip, geçen süre) sunucudan; frekans / süre / model
 *    seçimi Kontrol belleğinden (AppNavProvider — uygulama oturumu, kalıcı değil).
 *  · MOBİL eski kuralda kalır (kare akışı paneldedir) — `AiProPanelSahiplik.test.tsx`.
 */
jest.mock("react-native", () => {
  const RN = jest.requireActual("react-native");
  RN.Platform.OS = "web";
  return RN;
});
let mockDurum: Record<string, unknown> = { active: false, localized: false };
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async (yol: string) =>
    yol === "/ai/hazirlik"
      ? { moduller: [{ modul: "em_fantom", hazir: true }, { modul: "em_petri", hazir: true }, { modul: "petri_yolo", hazir: true }] }
      : mockDurum,
  ),
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
  useLiveData: () => ({ snapshot: null, wsConnected: true, aiVisionData: undefined, aiVisionFresh: false }),
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "a@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({
  useOperator: () => ({ operatorEmail: "a@x.com" }),
  useOperatorOptional: () => ({ operatorEmail: "a@x.com" }),
}));
jest.mock("expo-camera", () => {
  const React2 = require("react");
  return { CameraView: React2.forwardRef(() => null), useCameraPermissions: () => [{ granted: true }, jest.fn()] };
});

import { act, fireEvent, render } from "@testing-library/react-native";
import React from "react";

import { AppNavProvider } from "@/context/AppNavContext";
import { apiPost } from "@/services/apiClient";

import { AiProPanel } from "../AiProPanel";

beforeEach(() => {
  jest.useFakeTimers();
  mockDurum = { active: false, localized: false };
  (apiPost as jest.Mock).mockClear();
});
afterEach(() => jest.useRealTimers());

const cagrilar = (yol: string) => (apiPost as jest.Mock).mock.calls.filter((k) => k[0] === yol);
const panelOgesi = () => <AiProPanel patientName="Örnek-1" secilebilirModeller={["fantom", "petri"]} kullaniciKipi="researcher" />;
/** Kontrol ekranı gibi: sağlayıcı (bellek) yerinde kalır, panel sökülüp yeniden takılır. */
function Kabuk({ goster }: { goster: boolean }) {
  return <AppNavProvider navigateTo={() => {}}>{goster ? panelOgesi() : null}</AppNavProvider>;
}
async function bekle(n = 1) {
  for (let i = 0; i < n; i++) await act(async () => { jest.advanceTimersByTime(3000); await Promise.resolve(); });
}

it("KRİTİK S-AP.1: web'de KENDİ seansı sürerken panel sökülünce /ai/pro/stop GÖNDERİLMEZ (seans sürer)", async () => {
  mockDurum = { active: true, ownerClientId: "web-id", model: "petri", organId: 11 };
  const u = render(<Kabuk goster />);
  await bekle();
  expect(u.queryByLabelText("AI Pro otonom seansı durdur")).toBeTruthy(); // ön-doğrulama: seans benimsendi
  await act(async () => { u.rerender(<Kabuk goster={false} />); });
  expect(cagrilar("/ai/pro/stop")).toHaveLength(0);
});

it("KRİTİK S-AP.1: web önizlemesi sürerken sökülünce /hazirlik/durdur GİTMEZ; yeniden açılınca hazırlık + model geri gelir", async () => {
  const u = render(<Kabuk goster />);
  await act(async () => {});
  await act(async () => { fireEvent.press(u.getByLabelText(/Petri Kuyu/)); });
  await act(async () => { fireEvent.press(u.getByLabelText("AI Pro otonom seansı başlat")); });
  expect(cagrilar("/ai/pro/hazirlik/baslat")).toHaveLength(1);
  mockDurum = { active: false, hazirlikActive: true, model: "petri", organId: 11, hazirlikGecenSn: 30, kosulsuz: false };
  await act(async () => { u.rerender(<Kabuk goster={false} />); });
  expect(cagrilar("/ai/pro/hazirlik/durdur")).toHaveLength(0);
  await act(async () => { u.rerender(<Kabuk goster />); });
  await bekle();
  expect(u.getByText("🔎 Hazırlanıyor…")).toBeTruthy();
  expect(u.getByLabelText(/Petri Kuyu/).props.accessibilityState?.selected).toBe(true);
  expect(cagrilar("/ai/pro/hazirlik/baslat")).toHaveLength(1); // yeniden BAŞLATILMADI — sunucudaki sürer
});

it("S-AP.1: frekans ve süre seçimi panel yeniden açılınca KALIR (Kontrol belleği)", async () => {
  const u = render(<Kabuk goster />);
  await act(async () => {});
  await act(async () => { fireEvent.press(u.getByLabelText(/Petri Kuyu/)); });
  await act(async () => { fireEvent.press(u.getByTestId("aipro-frek-147")); });
  await act(async () => { u.rerender(<Kabuk goster={false} />); });
  await act(async () => { u.rerender(<Kabuk goster />); });
  await bekle();
  expect(u.getByTestId("aipro-frek-147").props.accessibilityState?.checked).toBe(true);
  expect(u.getByLabelText(/Petri Kuyu/).props.accessibilityState?.selected).toBe(true);
});

it("bellek sağlayıcısı yoksa (tek başına çizim) eski davranış: araştırmada model seçilmemiş açılır", async () => {
  const u = render(panelOgesi());
  await bekle();
  expect(u.getByLabelText(/Petri Kuyu/).props.accessibilityState?.selected).toBeFalsy();
});

it("S-AP.1: bellek BOŞKEN (yeni açılış / başka masaüstü penceresi) sunucuda süren önizleme modeliyle benimsenir", async () => {
  mockDurum = { active: false, hazirlikActive: true, model: "petri", organId: 11, hazirlikGecenSn: 5, kosulsuz: false };
  const u = render(<Kabuk goster />);
  await bekle();
  expect(u.getByLabelText(/Petri Kuyu/).props.accessibilityState?.selected).toBe(true);
  expect(u.getByText("🔎 Hazırlanıyor…")).toBeTruthy();
});

it("S-AP.1: geri açılan hazırlığın saati sunucunun GEÇEN süresinden sürer (120 sn tavanı ikisinde aynı anda)", async () => {
  const { platformAlert } = jest.requireMock("@/services/apiClient") as { platformAlert: jest.Mock };
  platformAlert.mockClear();
  mockDurum = { active: false, hazirlikActive: true, model: "petri", organId: 11, hazirlikGecenSn: 115, kosulsuz: false };
  const u = render(<Kabuk goster />);
  await act(async () => {});
  for (let i = 0; i < 8; i++) await act(async () => { jest.advanceTimersByTime(1000); await Promise.resolve(); });
  expect(platformAlert).toHaveBeenCalledWith("Konumlandırma tamamlanamadı", expect.any(String));
  expect(u.queryByText("🔎 Hazırlanıyor…")).toBeNull();
});
