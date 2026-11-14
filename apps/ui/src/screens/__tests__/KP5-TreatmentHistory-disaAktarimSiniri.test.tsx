/**
 * KP-5 · 8 · src/screens/TreatmentHistoryScreen.tsx — görünen kayıtların CSV dışa aktarımında ÜST SINIR (eskiden ZAMAN yüzünden
 * kapsanmıyordu: 1001 kart çizimi 22–25 sn, jest 20 sn sınırı). Sınırlar küçük sabit modülüne taşındı (`treatmentHistorySinirlari`);
 * bu dosya onu KÜÇÜK değerlerle sahteler (CSV 3 · PDF 2) — ekranın kuralı aynı:
 *  - sınırı AŞAN listede kullanıcı uyarılır ("çok kayıt" + kaç kayıt / en çok kaç) ve YALNIZ ilk N kimlik gider;
 *  - sınırda (= N) uyarı YOK, hepsi gider.
 * SAHTE: apiClient (ağ sınırı) · dosya indirme servisi · bildirim · sınır modülü. Gerçek değerler (200 / 1000) KP3 dosyasında ölçülür.
 */
const mockAlert = jest.fn();
const mockApiGet = jest.fn();
jest.mock("@/services/apiClient", () => ({
  apiGet: (...a: unknown[]) => mockApiGet(...a),
  apiPost: jest.fn(async () => ({ status: "success" })),
  platformAlert: (...a: unknown[]) => mockAlert(...a),
  platformConfirm: jest.fn(async () => true),
  authHeaders: jest.fn(() => ({})),
}));
jest.mock("@/services/config", () => ({ serviceConfig: { apiBaseUrl: "http://192.168.1.5:8000/api" } }));
const mockIndir = jest.fn();
jest.mock("@/services/dosyaIndir", () => ({
  downloadFileWithAuth: (...a: unknown[]) => mockIndir(...a),
  backendBuMakinede: () => false,
}));
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: jest.fn() }) }));
jest.mock("@/components/domain/SessionDetailModal", () => ({ SessionDetailModal: () => null }));
jest.mock("@/context/UserModeContext", () => ({ useUserMode: () => ({ userMode: "veterinarian", isExpert: true, isResearcher: false }) }));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "v@x.com" } }) }));
jest.mock("@/screens/treatmentHistorySinirlari", () => ({ CSV_MAX: 3, PDF_MAX: 2 }));

import React from "react";
import { act, fireEvent, render } from "@testing-library/react-native";
import i18n from "i18next";
import { TreatmentHistoryScreen } from "@/screens/TreatmentHistoryScreen";

const T = (k: string, o?: object): string => (i18n.t as unknown as (k: string, o?: object) => string)(k, o);
const seans = (id: number) => ({
  id, patient_name: `Hasta-${id}`, session_status: "completed", operator_email: "v@x.com", patient_notes: "",
  session_date: "2026-11-01", treatment_mode: "Manuel", duration_minutes: 20, frequency_hz: 50,
});
const liste = (adet: number) => Array.from({ length: adet }, (_, i) => seans(i + 1));

async function ekran(adet: number) {
  mockApiGet.mockImplementationOnce(async () => liste(adet));
  const u = render(<TreatmentHistoryScreen />);
  await act(async () => {});
  return u;
}
const kimlikler = () => String(mockIndir.mock.calls[0][0]).split("session_ids=")[1].split(",");

beforeEach(() => {
  mockAlert.mockReset();
  mockApiGet.mockReset();
  mockApiGet.mockResolvedValue([]);
  mockIndir.mockReset();
});

it("KRİTİK: görünen CSV sınırı AŞINCA uyarı (kaç kayıt / en çok kaç) + YALNIZ ilk N kimlik gider", async () => {
  const u = await ekran(5);
  await act(async () => { fireEvent.press(u.getByText(T("seans.gecmis.csvGorunen"))); });
  expect(mockAlert).toHaveBeenCalledWith(T("seans.gecmis.cokKayit"), T("seans.gecmis.csvSinir", { adet: 5, enCok: 3 }));
  expect(String(mockIndir.mock.calls[0][0])).toMatch(/\/history\/export_csv\?session_ids=/);
  expect(kimlikler()).toEqual(["1", "2", "3"]);
});

it("KARŞIT: sınırda (= N) uyarı YOK, hepsi gider", async () => {
  const u = await ekran(3);
  await act(async () => { fireEvent.press(u.getByText(T("seans.gecmis.csvGorunen"))); });
  expect(mockAlert).not.toHaveBeenCalled();
  expect(kimlikler()).toEqual(["1", "2", "3"]);
});

it("PDF de AYNI modülün sınırını kullanır (sahte 2): uyarı + ilk 2", async () => {
  const u = await ekran(3);
  await act(async () => { fireEvent.press(u.getByText(T("seans.gecmis.pdfGorunen"))); });
  expect(mockAlert).toHaveBeenCalledWith(T("seans.gecmis.cokKayit"), T("seans.gecmis.pdfSinir", { adet: 3, enCok: 2 }));
  expect(kimlikler()).toEqual(["1", "2"]);
});
