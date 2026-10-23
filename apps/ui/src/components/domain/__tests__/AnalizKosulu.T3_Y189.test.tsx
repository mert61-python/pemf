// Author: mertaygn, cglrgrkn
/**
 * T3 · Y189 (sahip + Çağlar Hoca, 2026-10-23) — koşulsuz kip GÖRÜNÜR: PEMF kapısı kutusu, onay penceresi, AI Pro paneli.
 *
 * Kapı: koşulsuz sonuç "✔ geçerli" ile karışmaz (kutu "KOŞULSUZ — doğrulanmamış" der; atlanan neden uyarı rengi + "(atlandı)");
 * koşulsuz öneri ONAYDAN ÖNCE söylenir; AI Pro'da araştırma modeli seçilince Koşullu | Koşulsuz görünür, seçim hazırlık gövdesinde
 * taşınır (varsayılan false), backend kipi koşulsuzsa hazırlıkta rozet görünür; kedi ekranında seçici YOK.
 * ⚠️ Beklenen metinler BURADA sabittir. Platform.OS="web" (AI Pro paneli IS_WEB'i import anında hesaplar).
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
jest.mock("@/context/AppNavContext", () => ({
  useAppNav: () => ({ navigateTo: jest.fn(), selectedPatient: null, setSelectedPatient: jest.fn(), aiProModeli: "", setAiProModeli: jest.fn() }),
}));
jest.mock("@/context/OperatorContext", () => ({ useOperator: () => ({ operatorEmail: "a@x.com" }) }));
jest.mock("expo-camera", () => {
  const React2 = require("react");
  return { CameraView: React2.forwardRef(() => null), useCameraPermissions: () => [{ granted: true }, jest.fn()] };
});

import { act, fireEvent, render } from "@testing-library/react-native";
import React from "react";

import { apiPost } from "@/services/apiClient";

import { AiProPanel } from "../AiProPanel";
import { AiSpecApprovalModal } from "../AiSpecApprovalModal";
import { PemfKapisiKutusu } from "../PemfKapisiKutusu";

const metin = (el: any): string => {
  const c = el.props.children;
  return Array.isArray(c) ? c.flat(Infinity).filter((x: unknown) => typeof x === "string").join("") : String(c);
};

beforeEach(() => {
  jest.useFakeTimers();
  mockDurum = { active: false, localized: false };
  (apiPost as jest.Mock).mockClear();
});
afterEach(() => {
  jest.useRealTimers();
});

it("KRİTİK: koşulsuz sonuç kutusu 'KOŞULSUZ — doğrulanmamış' der; atlanan neden '(koşulsuz: atlandı)' ile UYARI olarak", () => {
  const u = render(
    <PemfKapisiKutusu
      model="fantom"
      reliable={false}
      kapi={{
        surulebilir: true, pemf_gecerli: true, kosulsuz: true, atlanan: ["guvenilir_degil"], nedenler: ["guvenilir_degil"],
        mesajlar: [{ kod: "guvenilir_degil", metin: "Tümör tespiti güvenilir değil — yeniden çekin." }], varsayimlar: [],
      }}
    />,
  );
  expect(metin(u.getByTestId("pemf-kapisi-kosulsuz"))).toContain("KOŞULSUZ — doğrulanmamış sonuç");
  expect(metin(u.getByTestId("pemf-kapisi-guvenilir_degil"))).toContain("(koşulsuz: atlandı)");
});

it("KARŞIT: koşullu kutuda KOŞULSUZ satırı ve '(atlandı)' YOK (eski backend alanı göndermez)", () => {
  const u = render(
    <PemfKapisiKutusu
      model="petri"
      kapi={{ surulebilir: false, pemf_gecerli: true, nedenler: ["low_resolution"], mesajlar: [{ kod: "low_resolution", metin: "Düşük" }], varsayimlar: [] }}
    />,
  );
  expect(u.queryByTestId("pemf-kapisi-kosulsuz")).toBeNull();
  expect(metin(u.getByTestId("pemf-kapisi-low_resolution"))).not.toContain("atlandı");
});

it("KRİTİK: koşulsuz öneri ONAY penceresinde söylenir; koşulluda satır YOK", () => {
  const specs = { organ_id: 3, duration_minutes: 20, coil_ids: [1, 2, 3, 4, 5, 6, 7], D: [0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3], P: [0, 0, 0, 0, 0, 0, 0], e_field: 0.07, model: "petri" };
  const bos = () => {};
  const k = render(
    <AiSpecApprovalModal visible specs={{ ...specs, kosulsuz: true } as any} meta={{}} organName="A3" onApprove={bos} onReject={bos} onDismiss={bos} />,
  );
  expect(metin(k.getByTestId("ai-onay-kosulsuz"))).toContain("KOŞULSUZ öneri");
  const c = render(<AiSpecApprovalModal visible specs={specs as any} meta={{}} organName="A3" onApprove={bos} onReject={bos} onDismiss={bos} />);
  expect(c.queryByTestId("ai-onay-kosulsuz")).toBeNull();
});

it("KRİTİK: AI Pro'da araştırma modeli seçilince Koşullu | Koşulsuz görünür; seçim hazırlık gövdesinde taşınır", async () => {
  const u = render(<AiProPanel patientName="Örnek-1" secilebilirModeller={["fantom", "petri"]} kullaniciKipi="researcher" />);
  await act(async () => {});
  expect(u.queryByTestId("ai-pro-kosul")).toBeNull();  // model seçilmeden yok
  await act(async () => { fireEvent.press(u.getByLabelText(/Petri Kuyu/)); });
  expect(u.getByTestId("ai-pro-kosul")).toBeTruthy();
  await act(async () => { fireEvent.press(u.getByLabelText("AI Pro otonom seansı başlat")); });
  let c = (apiPost as jest.Mock).mock.calls.filter((k) => k[0] === "/ai/pro/hazirlik/baslat").pop();
  expect(c?.[1]).toMatchObject({ model: "petri", kosulsuz: false });
  // hazırlık sürerken kip KİLİTLİ (mühür karışmasın) → önce Vazgeç yerine yeni panel
  u.unmount();
  (apiPost as jest.Mock).mockClear();
  const u2 = render(<AiProPanel patientName="Örnek-1" secilebilirModeller={["fantom", "petri"]} kullaniciKipi="researcher" />);
  await act(async () => {});
  await act(async () => { fireEvent.press(u2.getByLabelText(/Fantom Tümör/)); });
  await act(async () => { fireEvent.press(u2.getByLabelText("Koşulsuz")); });
  await act(async () => { fireEvent.press(u2.getByLabelText("AI Pro otonom seansı başlat")); });
  c = (apiPost as jest.Mock).mock.calls.filter((k) => k[0] === "/ai/pro/hazirlik/baslat").pop();
  expect(c?.[1]).toMatchObject({ model: "fantom", kosulsuz: true });
  expect(u2.getByLabelText("Koşulsuz").props.accessibilityState?.disabled).toBe(true);
  mockDurum = { active: false, localized: false, hazirlikActive: true, model: "fantom", kosulsuz: true };
  await act(async () => { jest.advanceTimersByTime(3000); await Promise.resolve(); });
  expect(u2.getByTestId("ai-pro-kosulsuz-rozeti")).toBeTruthy();
});

it("KARŞIT: veteriner (kedi) AI Pro ekranında Koşullu | Koşulsuz YOK", async () => {
  const u = render(<AiProPanel patientName="Tekir" />);
  await act(async () => {});
  expect(u.queryByTestId("ai-pro-kosul")).toBeNull();
});
