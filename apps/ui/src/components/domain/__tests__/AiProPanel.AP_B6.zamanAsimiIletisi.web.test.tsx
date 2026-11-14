// Author: mertaygn, cglrgrkn
/**
 * AP · B6 (istem 48, tezgâh 13 Kasım 2026): hazırlıkta 2 dk konum bulunamayınca petri / kabin kamerasında da KEDİ + TELEFON iletisi
 * ("Hayvan iki dakikadır kadrajda bulunamadı … telefonu 1-2 metre") çıkıyordu. Artık ileti model + kamera türüne göre:
 *  · araştırma (petri / fantom) → kabin kamerası + modelin yerleşim ipucu + son kapı NEDENİ (varsa);
 *  · kedi + web (sunucu / kabin kamerası) → kabin dili; kedi + telefon → eski metin (AiProPanel.Y142 / mobil testler).
 *  · 45 sn gecikme ipucu da aynı ayrımla; kapının fiziksel olmayan nedeni şeritte NEDEN + EYLEM (S-AP.6, koşulsuz önerilmez).
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

import { apiPost, platformAlert } from "@/services/apiClient";

import { AiProPanel } from "../AiProPanel";

beforeEach(() => {
  jest.useFakeTimers();
  mockDurum = { active: false, localized: false };
  (apiPost as jest.Mock).mockClear();
  (platformAlert as jest.Mock).mockClear();
});
afterEach(() => jest.useRealTimers());

async function ilerle(sn: number) {
  for (let i = 0; i < sn; i++) await act(async () => { jest.advanceTimersByTime(1000); await Promise.resolve(); });
}
async function petriHazirlik() {
  const u = render(<AiProPanel patientName="Örnek-1" secilebilirModeller={["fantom", "petri"]} kullaniciKipi="researcher" />);
  await act(async () => {});
  await act(async () => { fireEvent.press(u.getByLabelText(/Petri Kuyu/)); });
  await act(async () => { fireEvent.press(u.getByLabelText("AI Pro otonom seansı başlat")); });
  return u;
}
const govde = () => (platformAlert as jest.Mock).mock.calls.find((k) => k[0] === "Konumlandırma tamamlanamadı")?.[1] as string;

it("KRİTİK B6: petri 2 dk → kabin kamerası iletisi + kapı nedeni; 'Hayvan' / 'telefon' YOK", async () => {
  mockDurum = { active: false, localized: false, hazirlikActive: true, model: "petri", kapiUyari: "Kuyu ızgarası doğrulanamadı — kuyular görünür olsun." };
  await petriHazirlik();
  await ilerle(122);
  const g = govde();
  expect(g).toContain("kabin kamerasında");
  expect(g).toContain("Kuyu ızgarası doğrulanamadı");
  expect(g).not.toMatch(/Hayvan|telefon/);
});

it("B6: kapı nedeni şeritte NEDEN + EYLEM (aranıyor değil); 45 sn ipucu kabin dilinde", async () => {
  mockDurum = { active: false, localized: false, hazirlikActive: true, model: "petri", kapiUyari: "Kuyu ızgarası doğrulanamadı — kuyular görünür olsun." };
  const u = await petriHazirlik();
  await ilerle(47);
  const serit = String(u.getByText(/Kuyu konumu doğrulanamadı/).props.children);
  expect(serit).toContain("Kuyu konumu doğrulanamadı — Kuyu ızgarası doğrulanamadı");
  expect(serit).toContain("Hâlâ bulunamadı");
  expect(serit).not.toContain("1-2 metre");
});

it("B6: kedi + web (kabin / sunucu kamerası) 2 dk → kabin iletisi, telefon YOK", async () => {
  const u = render(<AiProPanel patientName="Tekir" />);
  await act(async () => {});
  await act(async () => { fireEvent.press(u.getByLabelText("AI Pro otonom seansı başlat")); });
  await ilerle(122);
  const g = govde();
  expect(g).toContain("kabin kamerasında");
  expect(g).not.toMatch(/telefon/);
});
