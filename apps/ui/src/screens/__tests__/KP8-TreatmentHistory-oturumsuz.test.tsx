/**
 * KP-8 · src/screens/TreatmentHistoryScreen.tsx — OTURUM YOKKEN (operatör bağlamı da yok) kimlik boştur (düzenek KP3-TreatmentHistory-
 * kollari ile AYNI; yalnız oturum `null`): liste yerine kimlik istemi; tekil silme düğmesi kimlik istemiyle engellenir, istek GİTMEZ.
 */
const mockAlert = jest.fn();
const mockConfirm = jest.fn(async (..._a: unknown[]) => true);
const mockApiGet = jest.fn();
const mockApiPost = jest.fn();
jest.mock("@/services/apiClient", () => ({
  apiGet: (...a: unknown[]) => mockApiGet(...a),
  apiPost: (...a: unknown[]) => mockApiPost(...a),
  platformAlert: (...a: unknown[]) => mockAlert(...a),
  platformConfirm: (...a: unknown[]) => mockConfirm(...a),
  authHeaders: jest.fn(() => ({})),
}));
jest.mock("@/services/config", () => ({ serviceConfig: { apiBaseUrl: "http://192.168.1.5:8000/api" } }));
const mockIndir = jest.fn();
jest.mock("@/services/dosyaIndir", () => ({
  downloadFileWithAuth: (...a: unknown[]) => mockIndir(...a),
  backendBuMakinede: () => false,
}));
const mockToast = jest.fn();
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: mockToast }) }));
let mockDetay: { visible: boolean; sessionId: unknown; onClose: () => void } | null = null;
jest.mock("@/components/domain/SessionDetailModal", () => ({
  SessionDetailModal: (p: { visible: boolean; sessionId: unknown; onClose: () => void }) => { mockDetay = p; return null; },
}));
jest.mock("@/context/UserModeContext", () => ({ useUserMode: () => ({ userMode: "veterinarian", isExpert: true, isResearcher: false }) }));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: null }) }));

import React from "react";
import { act, fireEvent, render } from "@testing-library/react-native";
import { Edit3 } from "lucide-react-native";
import i18n from "i18next";
import { TreatmentHistoryScreen } from "@/screens/TreatmentHistoryScreen";
import { StatusPill } from "@/components/ui/StatusPill";
import { profilSozlugu } from "@/utils/profilSozlugu";

const T = (k: string, o?: object): string => (i18n.t as unknown as (k: string, o?: object) => string)(k, o);
const seans = (id: number, ek: Record<string, unknown> = {}) => ({
  id, patient_name: `Hasta-${id}`, session_status: "completed", operator_email: "v@x.com", patient_notes: "",
  session_date: "2026-11-01", treatment_mode: "Manuel", duration_minutes: 20, frequency_hz: 50, ...ek,
});
const sayfa = (bas: number, adet: number) => Array.from({ length: adet }, (_, i) => seans(bas + i));

type U = ReturnType<typeof render>;
async function ekran(ilk: unknown[]) {
  mockApiGet.mockImplementationOnce(async () => ilk);
  const u = render(<TreatmentHistoryScreen />);
  await act(async () => {});
  return u;
}
async function bas(u: U, etiket: string) { await act(async () => { fireEvent.press(u.getByLabelText(etiket)); }); }
async function metin(u: U, m: string) { await act(async () => { fireEvent.press(u.getByText(m)); }); }

beforeEach(() => {
  mockAlert.mockReset();
  mockConfirm.mockReset();
  mockConfirm.mockImplementation(async () => true);
  mockApiGet.mockReset();
  mockApiGet.mockResolvedValue([]);
  mockApiPost.mockReset();
  mockApiPost.mockResolvedValue({ status: "success" });
  mockIndir.mockReset();
  mockToast.mockReset();
  mockDetay = null;
});


it("oturum yokken liste yerine kimlik istemi; silme isteği gitmez", async () => {
  const u = await ekran([seans(1, { patient_name: "Boncuk", operator_email: "" })]);
  expect(u.queryByText("Boncuk")).toBeNull();
  expect(u.getByText(T("hasta.kimlik.istem"))).toBeTruthy();
  expect(mockApiPost).not.toHaveBeenCalled();
});
