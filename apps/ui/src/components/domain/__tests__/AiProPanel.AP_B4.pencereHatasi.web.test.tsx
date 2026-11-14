// Author: mertaygn, cglrgrkn
/**
 * AP · B4 (istem 48, tezgâh 13 Kasım 2026): onay penceresinde "Yeniden hesapla" hatası (ör. `dozSapmasi`) pencerenin ARKASINDA kırmızı
 * balon olarak çıkıyordu (genel hata balonu uygulama kökünde çizilir, RN Modal üstte). Artık:
 *  · yeniden hesap / onay / başlatma hatası pencerenin İÇİNDE (her zaman görünen alt şerit, düğmelerin üstünde) — istek SESSİZ;
 *  · sunucunun eylem söyleyen gerekçesi aynen; ölçüm 2 dk'dan eskiyse "pencereyi kapatıp hazırlığı yeniden başlatın" eki;
 *  · pencere kapatılınca hata temizlenir.
 */
jest.mock("react-native", () => {
  const RN = jest.requireActual("react-native");
  RN.Platform.OS = "web";
  return RN;
});
let mockDurum: Record<string, unknown> = { active: false, localized: false };
let mockProposeSayac = 0;
let mockHesapRet: { durum: number; detay: string } | null = null;
let mockStartRet: { durum: number; detay: string } | null = null;
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

import { apiPost } from "@/services/apiClient";

import { AiProPanel } from "../AiProPanel";

beforeEach(() => {
  jest.useFakeTimers();
  mockDurum = { active: false, localized: false };
  mockProposeSayac = 0;
  mockHesapRet = null;
  mockStartRet = null;
  (apiPost as jest.Mock).mockClear();
});
afterEach(() => jest.useRealTimers());

async function oneriPenceresi() {
  const u = render(<AiProPanel patientName="Örnek-1" secilebilirModeller={["fantom", "petri"]} kullaniciKipi="researcher" />);
  await act(async () => {});
  await act(async () => { fireEvent.press(u.getByLabelText(/Petri Kuyu/)); });
  await act(async () => { fireEvent.press(u.getByLabelText("AI Pro otonom seansı başlat")); });
  mockDurum = { active: false, localized: true, hazirlikActive: true, model: "petri" };
  for (let i = 0; i < 3; i++) await act(async () => { jest.advanceTimersByTime(3000); await Promise.resolve(); });
  expect(u.getByTestId("odak-ozeti")).toBeTruthy(); // ön-doğrulama: onay penceresi açık
  return u;
}
const sonOpts = (yol: string) => (apiPost as jest.Mock).mock.calls.filter((k) => k[0] === yol).pop()?.[3];

it("KRİTİK B4: 'Yeniden hesapla' reddi (dozSapmasi) pencerenin İÇİNDE, eylem metniyle; istek SESSİZ (arkada balon yok)", async () => {
  mockHesapRet = { durum: 409, detay: "Model bu konumda istenen dozu tutturamadı (beklenen 0,61 mT, istenen 0,55 mT; sınır %10) — sürülmedi. Dozu biraz değiştirip yeniden hesaplayın ya da numuneyi hafifçe kaydırın." };
  const u = await oneriPenceresi();
  await act(async () => { fireEvent.press(u.getByTestId("odak-yeniden-hesapla")); });
  expect(sonOpts("/ai/pro/propose")).toMatchObject({ silent: true });
  const hata = u.getByTestId("ai-onay-hata");
  expect(String(hata.props.children)).toContain("Dozu biraz değiştirip yeniden hesaplayın");
  expect(u.getByTestId("odak-ozeti")).toBeTruthy(); // pencere AÇIK, önceki öneri duruyor
});

it("B4: konum ölçümü 2 dk'dan eskiyse yeniden hesap hatasına 'pencereyi kapatıp hazırlığı yeniden başlatın' eklenir", async () => {
  mockHesapRet = { durum: 409, detay: "Kuyu henüz konumlandırılmadı." };
  const u = await oneriPenceresi();
  await act(async () => { jest.advanceTimersByTime(115000); });
  await act(async () => { fireEvent.press(u.getByTestId("odak-yeniden-hesapla")); });
  expect(String(u.getByTestId("ai-onay-hata").props.children)).toContain("pencereyi kapatıp hazırlığı yeniden başlatın");
});

it("B4: başlatma reddi de pencerenin İÇİNDE; pencere kapatılınca hata temizlenir", async () => {
  mockStartRet = { durum: 409, detay: "Kabin kalibrasyonu yok — Kabin kalibrasyonu bölümünde plakayı iki konumda ölçerek kalibre edin." };
  const u = await oneriPenceresi();
  await act(async () => { fireEvent.press(u.getByLabelText("Öneriyi onayla ve seansı başlat")); });
  expect(sonOpts("/ai/pro/start")).toMatchObject({ silent: true });
  expect(String(u.getByTestId("ai-onay-hata").props.children)).toContain("Kabin kalibrasyonu yok");
  await act(async () => { fireEvent.press(u.getByLabelText("Kapat")); });
  expect(u.queryByTestId("ai-onay-hata")).toBeNull();
});
