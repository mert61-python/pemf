// Author: mertaygn, cglrgrkn
/**
 * ODD B-3 (ODK-B keşfi 18-11, kum 13b) — onay penceresi açıkken önizleme durur, konum ölçümü yaşlanır; 2 dk sonra "Yeniden hesapla"
 * 409 alıyordu ve tek çıkış pencereyi kapatıp hazırlığı baştan başlatmaktı (seçilen doz / kip / kuyu kaybolur).
 * SÖZLEŞME: ölçüm KONUM_ESKI_MS'yi geçince pencerede "Konumu tazele ve yeniden hesapla" görünür; basınca önizleme AYNI hedef / model / kiple
 * kısa açılır (`/hazirlik/baslat`), taze konum gelince bırakılır (`/hazirlik/durdur`) ve AYNI doz / kip / kuyuyla yeniden öneri istenir.
 * Taze konum gelmezse pencere hatası (eylem söyler). İstemci saatiyle 409 iletisinin SONUNA eklenen cümle KALKTI (neden sunucu iletisinin
 * başında, `konumBayat`). Düzen `AiProPanel.AP22…` ile aynı (web).
 */
jest.mock("react-native", () => {
  const RN = jest.requireActual("react-native");
  RN.Platform.OS = "web";
  return RN;
});
let mockDurum: Record<string, unknown> = { active: false, localized: false };
let mockOneriRed: { durum: number; detay: string } | null = null;
const ODAK = { kip: "KUYUCUK", doz_mT: 0.6, beklenen_mT: 0.6, tavan_mT: 1.2, pay_yuzde: 5, kuyular: [] };
let mockOneriSayac = 0;
const mockPost = jest.fn(async (yol: string, govde?: Record<string, unknown>, _y?: unknown, sec?: { onHttpError?: (d: number, x: string) => void }): Promise<unknown> => {
  if (yol === "/ai/pro/propose") {
    if (mockOneriRed && govde && govde.doz_mT !== undefined) {
      sec?.onHttpError?.(mockOneriRed.durum, mockOneriRed.detay);
      return null;
    }
    const doz = typeof govde?.doz_mT === "number" ? govde.doz_mT : 0.6;
    const kip = typeof govde?.odak_kip === "string" ? govde.odak_kip : "KUYUCUK";
    return {
      proposalId: `p-${++mockOneriSayac}`,
      specs: { organ_id: 11, duration_minutes: 20, coil_ids: [1, 2, 3, 4, 5, 6, 7], D: [0.2, 0, 0, 0, 0, 0, 0], P: [0, 0, 0, 0, 0, 0, 0],
        e_field: 0, model: "petri", target_label: "Kuyu C6", odak: { ...ODAK, doz_mT: doz, kip } },
      meta: {},
      expiresAt: 0,
    };
  }
  return { status: "success" };
});
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async (yol: string) =>
    yol === "/ai/hazirlik"
      ? { moduller: [{ modul: "em_fantom", hazir: true }, { modul: "em_petri", hazir: true }, { modul: "petri_yolo", hazir: true }] }
      : mockDurum,
  ),
  apiPost: (...a: unknown[]) => (mockPost as unknown as (...b: unknown[]) => unknown)(...a),
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

import { AiProPanel } from "../AiProPanel";

beforeEach(() => {
  jest.useFakeTimers();
  mockDurum = { active: false, localized: false };
  mockOneriRed = null;
  mockPost.mockClear();
});
afterEach(() => jest.useRealTimers());

async function ilerle(ms: number, adim = 1000) {
  for (let t = 0; t < ms; t += adim) await act(async () => { jest.advanceTimersByTime(adim); await Promise.resolve(); });
}
async function oneriPenceresi() {
  const u = render(<AiProPanel patientName="Örnek-1" secilebilirModeller={["fantom", "petri"]} kullaniciKipi="researcher" />);
  await act(async () => {});
  await act(async () => { fireEvent.press(u.getByLabelText(/Petri Kuyu/)); });
  await act(async () => { fireEvent.press(u.getByLabelText("AI Pro otonom seansı başlat")); });
  mockDurum = { active: false, localized: true, hazirlikActive: true, model: "petri" };
  await ilerle(9000, 3000);
  expect(u.getByTestId("odak-ozeti")).toBeTruthy(); // ön-doğrulama: onay penceresi açık
  mockDurum = { active: false, localized: false, model: "petri" }; // pencere açılınca önizleme durdu
  return u;
}
const cagrilar = (yol: string) => mockPost.mock.calls.filter((k: unknown[]) => k[0] === yol);

it("KRİTİK B-3: ölçüm taze iken 'Konumu tazele' YOK; 2 dk'yı geçince GÖRÜNÜR", async () => {
  const u = await oneriPenceresi();
  expect(u.queryByTestId("odak-konum-tazele")).toBeNull();
  await ilerle(115000, 5000);
  expect(u.getByTestId("odak-konum-tazele")).toBeTruthy();
  expect(u.getByTestId("odak-konum-eski")).toBeTruthy();
});

it("KRİTİK B-3: tazele → önizleme AYNI hedef / model / kiple açılır, taze konumda bırakılır, AYNI doz / kip ile yeniden öneri", async () => {
  const u = await oneriPenceresi();
  await ilerle(115000, 5000);
  fireEvent.changeText(u.getByTestId("odak-doz-girdi"), "0,8");
  fireEvent.press(u.getByTestId("odak-kip-TUM_PETRI"));
  const once = mockPost.mock.calls.length;
  const oneri0 = cagrilar("/ai/pro/propose").length;
  await act(async () => { fireEvent.press(u.getByTestId("odak-konum-tazele")); });
  const baslat = cagrilar("/ai/pro/hazirlik/baslat").slice(-1)[0];
  expect(baslat[1]).toMatchObject({ organ_id: 0, model: "petri" });
  expect(cagrilar("/ai/pro/hazirlik/durdur").length).toBeGreaterThan(0); // (öneri gelince ilk durdurma)
  const durdurOnce = cagrilar("/ai/pro/hazirlik/durdur").length;
  await ilerle(3000, 1500); // henüz taze değil
  expect(cagrilar("/ai/pro/propose").length).toBe(oneri0); // taze konum yokken öneri istenmez
  mockDurum = { active: false, localized: true, model: "petri" };
  await ilerle(3000, 1500);
  expect(cagrilar("/ai/pro/hazirlik/durdur").length).toBe(durdurOnce + 1);
  const yeni = mockPost.mock.calls.slice(once).filter((k: unknown[]) => k[0] === "/ai/pro/propose");
  expect(yeni).toHaveLength(1);
  expect(yeni[0][1]).toMatchObject({ doz_mT: 0.8, odak_kip: "TUM_PETRI", organ_id: 0 });
  expect(u.queryByTestId("odak-konum-tazele")).toBeNull(); // yeni ölçüm taze
});

it("KRİTİK B-3: taze konum 30 sn'de gelmezse önizleme bırakılır, öneri İSTENMEZ, pencere hatası eylem söyler", async () => {
  const u = await oneriPenceresi();
  await ilerle(115000, 5000);
  const oneriOnce = cagrilar("/ai/pro/propose").length;
  await act(async () => { fireEvent.press(u.getByTestId("odak-konum-tazele")); });
  await ilerle(33000, 1500);
  expect(cagrilar("/ai/pro/propose").length).toBe(oneriOnce);
  expect(u.getByTestId("ai-onay-hata").props.children).toContain("Konum tazelenemedi: kamera 30 sn içinde hedefi yeniden bulamadı.");
});

it("KRİTİK B-3: 409 iletisinin SONUNA istemci saatiyle cümle EKLENMEZ (neden sunucu iletisinin başında)", async () => {
  const u = await oneriPenceresi();
  await ilerle(115000, 5000);
  mockOneriRed = { durum: 409, detay: "Kuyu C6 için konum ölçümü eski (2 dakikadan önce) — X." };
  fireEvent.changeText(u.getByTestId("odak-doz-girdi"), "0,7");
  await act(async () => { fireEvent.press(u.getByTestId("odak-yeniden-hesapla")); });
  const m = String(u.getByTestId("ai-onay-hata").props.children);
  expect(m).toContain("Kuyu C6 için konum ölçümü eski");
  expect(m).not.toContain("pencereyi kapatıp hazırlığı yeniden başlatın, sonra yeniden hesaplayın");
});
