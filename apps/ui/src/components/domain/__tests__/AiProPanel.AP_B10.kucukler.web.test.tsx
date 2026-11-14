// Author: mertaygn, cglrgrkn
/**
 * AP · B10 (istem 48): küçük düzeltmeler —
 *  · AP-10: seans sürerken hedef halkaları / listesi KİLİTLİ ve nedeni yazar (13-11 15:01:55 "onaylı 2, istenen 10" 409'u);
 *  · AP-12 (S-AP.7): kedi başlat düğmesi SEÇİLİ frekansı yazar ("100 Hz DDS" sabiti ODK8'den beri yanlıştı);
 *  · AP-21 (D ekran görüntüsü 14-11): uzun kapı nedeninde hazırlık şeridinin "Vazgeç" düğmesi şeridin DIŞINA taşıyordu —
 *    `GenisletilebilirMetin` sarmalayıcısı satırda esnemiyordu (stil yalnız içteki metne gidiyor).
 * Düzen `AiProPanel.AP_B4.pencereHatasi.web.test.tsx` ile aynı.
 */
jest.mock("react-native", () => {
  const RN = jest.requireActual("react-native");
  RN.Platform.OS = "web";
  return RN;
});
let mockDurum: Record<string, unknown> = { active: false, localized: false };
let mockProposeSayac = 0;
let mockHesapRet = null as { durum: number; detay: string } | null; // `as`: hiç atanmasa da tür daralmaz (tsc)
let mockStartRet = null as { durum: number; detay: string } | null;
const ODAK = { kip: "KUYUCUK", doz_mT: 0.6, beklenen_mT: 0.6, tavan_mT: 1.2, pay_yuzde: 5, kuyular: [] };
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async (yol: string) =>
    yol === "/ai/hazirlik"
      ? { moduller: [{ modul: "em_fantom", hazir: true }, { modul: "em_petri", hazir: true }, { modul: "petri_yolo", hazir: true }] }
      : mockDurum,
  ),
  apiPost: jest.fn(async (yol: string, _g: unknown, _f: unknown, opts?: { onHttpError?: (d: number, x?: string) => void }) => {
    if (yol === "/ai/pro/propose") {
      mockProposeSayac += 1;
      if (mockProposeSayac > 1 && mockHesapRet) {
        opts?.onHttpError?.(mockHesapRet.durum, mockHesapRet.detay);
        return null;
      }
      return {
        proposalId: `p${mockProposeSayac}`,
        specs: { organ_id: 11, duration_minutes: 20, coil_ids: [1, 2, 3, 4, 5, 6, 7], D: [0.2, 0, 0, 0, 0, 0, 0], P: [0, 0, 0, 0, 0, 0, 0],
          e_field: 0, model: "petri", target_label: "Kuyu C6", odak: ODAK },
        meta: {},
        expiresAt: 0,
      };
    }
    if (yol === "/ai/pro/start" && mockStartRet) {
      opts?.onHttpError?.(mockStartRet.durum, mockStartRet.detay);
      return null;
    }
    return { status: "success" };
  }),
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
jest.mock("@/context/OperatorContext", () => ({ useOperator: () => ({ operatorEmail: "a@x.com" }) }));
jest.mock("expo-camera", () => {
  const React2 = require("react");
  return { CameraView: React2.forwardRef(() => null), useCameraPermissions: () => [{ granted: true }, jest.fn()] };
});

import { act, fireEvent, render } from "@testing-library/react-native";
import React from "react";
import { StyleSheet } from "react-native";

import { apiPost } from "@/services/apiClient";

import { AiProPanel } from "../AiProPanel";

beforeEach(() => {
  jest.useFakeTimers();
  mockDurum = { active: false, localized: false };
  (apiPost as jest.Mock).mockClear();
});
afterEach(() => jest.useRealTimers());

const C6 = { id: 11, label: "Kuyu C6", etiketGosterim: "Kuyu C6", pxn: [0.6, 0.5], reliability: 0.9 };

it("KRİTİK AP-10: seans sürerken hedef satırı KİLİTLİ, /organ GİTMEZ, nedeni yazar", async () => {
  mockDurum = { active: true, ownerClientId: "web-id", model: "petri", organId: 11, targetsModel: "petri", targets: [C6] };
  const u = render(<AiProPanel patientName="Örnek-1" secilebilirModeller={["fantom", "petri"]} kullaniciKipi="researcher" />);
  await act(async () => { jest.advanceTimersByTime(3000); await Promise.resolve(); });
  const satir = u.getByTestId("hedef-satir-11");
  expect(satir.props.accessibilityState?.disabled).toBe(true);
  await act(async () => { fireEvent.press(satir); });
  expect((apiPost as jest.Mock).mock.calls.filter((k) => k[0] === "/ai/pro/organ")).toHaveLength(0);
  expect(u.getByTestId("ai-pro-hedef-kilit").props.children).toBe(
    "Seans onaylanan hedefle sürüyor — hedefi değiştirmek için seansı durdurup yeni öneri alın.",
  );
});

it("AP-12: kedi başlat düğmesi seçili frekansı yazar", async () => {
  const u = render(<AiProPanel patientName="Tekir" />);
  await act(async () => {});
  expect(u.getByText("🚀 AI Pro Başlat (100 Hz)")).toBeTruthy();
  await act(async () => { fireEvent.press(u.getByTestId("aipro-frek-147")); });
  expect(u.getByText("🚀 AI Pro Başlat (147 Hz)")).toBeTruthy();
});

it("AP-21: hazırlık şeridinde metin kabı ESNER (flex 1, minWidth 0) — uzun kapı nedeni Vazgeç'i şeritten taşırmaz", async () => {
  mockDurum = { active: false, localized: false, hazirlikActive: true, model: "petri", hazirlikGecenSn: 5, kosulsuz: false,
    kapiUyari: "Kuyu ızgarası doğrulanamadı — kuyular görünür olsun (sensör ya da kablo üstlerini örtmesin), plaka düz dursun ve kabin ışığı açık olsun." };
  const u = render(<AiProPanel patientName="Örnek-1" secilebilirModeller={["fantom", "petri"]} kullaniciKipi="researcher" />);
  await act(async () => { jest.advanceTimersByTime(3000); await Promise.resolve(); });
  expect(u.getByTestId("aipro-hazirlik-metni")).toBeTruthy();
  const kap = StyleSheet.flatten(u.getByTestId("aipro-hazirlik-metin-kap").props.style);
  expect(kap.flex).toBe(1);
  expect(kap.minWidth).toBe(0);
  const vazgec = StyleSheet.flatten(u.getByLabelText("Hazırlığı iptal et").props.style);
  expect(vazgec.flexShrink).toBe(0);
});
