/**
 * KP-4 B1 · src/screens/AiHistoryScreen.tsx — KP-3'ten kalan iki kol:
 *  - Hasta çipiyle süzülen liste, hasta şeridindeki "tüm liste" çipiyle GERİ gelir (başka hastanın kaydı yeniden görünür).
 *  - "Paylaş" kaydın kendi PDF'ini ister (kayıt kimliğiyle, hasta adlı dosya) ve indiricinin bildirimini sağlayıcısız ekranda bile toast
 *    KÖPRÜSÜNE iletir.
 * SAHTE: apiClient (ağ sınırı) · dosya indirme servisi (aldığı argümanlar kaydedilir) · kimlik / profil bağlamları (sabit girdi).
 * GERÇEK: AiHistoryScreen, toast köprüsü (dinleyici bu testte kayıtlı).
 */
const mockApiGet = jest.fn();
jest.mock("@/services/apiClient", () => ({
  apiGet: (...a: unknown[]) => mockApiGet(...a),
  apiPost: jest.fn(async () => ({ status: "success" })),
  platformConfirm: jest.fn(async () => true),
}));
const mockIndir = jest.fn();
jest.mock("@/services/dosyaIndir", () => ({ downloadFileWithAuth: (...a: unknown[]) => mockIndir(...a), backendBuMakinede: () => false }));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "a@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({ useOperatorOptional: () => ({ operatorEmail: "a@x.com" }) }));
jest.mock("@/context/UserModeContext", () => ({
  useUserMode: () => ({ userMode: "veterinarian", isExpert: true, isResearcher: false }),
}));

import { act, fireEvent, render } from "@testing-library/react-native";
import React from "react";
import i18n from "i18next";
import { AiHistoryScreen } from "@/screens/AiHistoryScreen";
import { serviceConfig } from "@/services/config";
import { setToastHandler } from "@/services/toastBridge";
import { profilSozlugu } from "@/utils/profilSozlugu";

const T = (k: string, o?: object): string => (i18n.t as unknown as (k: string, o?: object) => string)(k, o);
const kayit = (id: number, ek: Record<string, unknown> = {}) => ({
  id, created_at: "2026-09-09T11:53:00", mode: "veterinarian", module_id: "landmark", module_label: "Ağrı Analizi (FGS)",
  patient_name: "Mia", operator_email: "a@x.com", input_type: "image", result_summary: `özet-${id}`, ...ek,
});

async function ekran(kayitlar: unknown[]) {
  mockApiGet.mockImplementation(async (yol: string, fb: unknown) =>
    (String(yol).startsWith("/ai/log") ? { status: "success", data: kayitlar } : fb));
  const u = render(<AiHistoryScreen />);
  await act(async () => {});
  return u;
}
const filtre = (label: string) => T("ai.gecmis.filtreEtiketi", { label });

beforeEach(() => {
  mockApiGet.mockReset();
  mockIndir.mockReset();
});
afterEach(() => setToastHandler(null));

it("KRİTİK: hasta çipiyle süzülen liste 'tüm liste' çipiyle geri gelir", async () => {
  const u = await ekran([kayit(1, { result_summary: "mia-1" }), kayit(2, { patient_name: "Boncuk", result_summary: "boncuk-2" })]);
  await act(async () => { fireEvent.press(u.getByLabelText(filtre("Boncuk"))); });
  expect(u.getByText("boncuk-2")).toBeTruthy();
  expect(u.queryByText("mia-1")).toBeNull();
  await act(async () => { fireEvent.press(u.getByLabelText(filtre(profilSozlugu({}).tumListeCipi))); });
  expect(u.getByText("mia-1")).toBeTruthy();
  expect(u.getByText("boncuk-2")).toBeTruthy();
});

it("KRİTİK: 'Paylaş' kaydın PDF'ini kimliğiyle ister; indiricinin bildirimi toast köprüsüne gider", async () => {
  const bildirimler: Array<[string, string | undefined]> = [];
  setToastHandler((m, tur) => { bildirimler.push([m, tur]); });
  const u = await ekran([kayit(7, { result_summary: "mia-7" })]);
  if (!u.queryByTestId("ai-paylas-7")) await act(async () => { fireEvent.press(u.getByText("mia-7")); });
  await act(async () => { fireEvent.press(u.getByTestId("ai-paylas-7")); });
  expect(mockIndir).toHaveBeenCalledTimes(1);
  const [url, ad, bildir] = mockIndir.mock.calls[0] as [string, string, (m: string, t: string) => void];
  expect(url).toBe(`${serviceConfig.apiBaseUrl}/ai/log/7/pdf`);
  expect(ad).toBe("PEMF_AI_Mia_7.pdf");
  bildir("PDF kaydedildi", "success");
  expect(bildirimler).toEqual([["PDF kaydedildi", "success"]]);
});
