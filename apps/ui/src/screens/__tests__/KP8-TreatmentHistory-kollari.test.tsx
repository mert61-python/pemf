/**
 * KP-8 · src/screens/TreatmentHistoryScreen.tsx kalan dallar (düzenek KP3-TreatmentHistory-kollari ile AYNI — apiClient / indirme /
 * bildirim / detay modalı sahte):
 *  - Arama hasta NOTUNDA ve seans TARİHİNDE de eşleşir.
 *  - Eşleşme yokken: yüklenmemiş sayfa VARSA "yüklenenlerde eşleşme yok" (daha fazlası olabilir), YOKSA "aramayla eşleşen yok".
 *  - Hasta adı / mod / notu olmayan eski seans: mod "-", not boş, PDF "hasta" adıyla iner (çökmez).
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
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "v@x.com" } }) }));

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


const araKutusu = (u: U) => u.getByPlaceholderText(T("seans.gecmis.araPlaceholder"));
async function ara(u: U, q: string) { await act(async () => { fireEvent.changeText(araKutusu(u), q); }); }

it("arama hasta notunda ve seans tarihinde de eşleşir", async () => {
  const u = await ekran([
    seans(1, { patient_name: "Boncuk", patient_notes: "kontrol-kp8-not" }),
    seans(2, { patient_name: "Pamuk", session_date: "2026-10-05" }),
  ]);
  await ara(u, "kp8-not");
  expect(u.queryByText("Boncuk")).toBeTruthy();
  expect(u.queryByText("Pamuk")).toBeNull();
  await ara(u, "2026-10-05");
  expect(u.queryByText("Pamuk")).toBeTruthy();
  expect(u.queryByText("Boncuk")).toBeNull();
});

it("eşleşme yok: yüklenmemiş sayfa varsa 'yüklenenlerde yok', yoksa 'aramayla eşleşen yok'", async () => {
  const u = await ekran(sayfa(1, 50));
  await ara(u, "zzz-kp8-yok");
  expect(u.getByText(T("seans.gecmis.eslesmeYok"))).toBeTruthy();
  u.unmount();
  const u2 = await ekran(sayfa(1, 3));
  await ara(u2, "zzz-kp8-yok");
  expect(u2.getByText(T("hasta.liste.aramaBos"))).toBeTruthy();
});

it("adı / modu / notu olmayan eski seans: mod '-', PDF 'hasta' adıyla iner", async () => {
  const u = await ekran([seans(9, { patient_name: undefined, treatment_mode: undefined, patient_notes: undefined })]);
  expect(u.getAllByText("-").length).toBeGreaterThan(0);
  await bas(u, T("seans.gecmis.pdfEtiketi"));
  expect(mockIndir.mock.calls[0][1]).toBe("PEMF_Rapor_hasta_9.pdf");
});
