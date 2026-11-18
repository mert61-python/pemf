/**
 * ODD B-4 (ODK-B keşfi 18-11, kum 21_gecmis): adı olmayan (sahipsiz) seans kaydı araştırma profilinde "Bilinmeyen Hasta" görünüyordu
 * (petri / fantom seansı bir hasta değil, bir ÖRNEKTİR). Araştırmada "Sahipsiz örnek" / "Unowned sample"; veteriner / ev sahibi
 * profillerinde "Bilinmeyen Hasta" AYNEN. Düzen `KP8-TreatmentHistory-kollari` ile aynı; profil `useUserMode` sahtesiyle.
 */
const mockApiGet = jest.fn();
jest.mock("@/services/apiClient", () => ({
  apiGet: (...a: unknown[]) => mockApiGet(...a),
  apiPost: jest.fn(async () => ({ status: "success" })),
  platformAlert: jest.fn(),
  platformConfirm: jest.fn(async () => true),
  authHeaders: jest.fn(() => ({})),
}));
jest.mock("@/services/config", () => ({ serviceConfig: { apiBaseUrl: "http://192.168.1.5:8000/api" } }));
jest.mock("@/services/dosyaIndir", () => ({ downloadFileWithAuth: jest.fn(), backendBuMakinede: () => false }));
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: jest.fn() }) }));
jest.mock("@/components/domain/SessionDetailModal", () => ({ SessionDetailModal: () => null }));
let mockArastirmaci = true;
jest.mock("@/context/UserModeContext", () => ({
  useUserMode: () => ({ userMode: mockArastirmaci ? "researcher" : "veterinarian", isExpert: true, isResearcher: mockArastirmaci }),
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "v@x.com" } }) }));

import React from "react";
import { act, render } from "@testing-library/react-native";
import i18n from "i18next";
import { TreatmentHistoryScreen } from "@/screens/TreatmentHistoryScreen";

const seans = (id: number, ek: Record<string, unknown> = {}) => ({
  id, patient_name: undefined, session_status: "stopped", operator_email: "v@x.com", patient_notes: "",
  session_date: "2026-11-18", start_time: "14:47:52", treatment_mode: "AI Pro · Petri Kuyu", duration_minutes: 3, frequency_hz: 100, ...ek,
});

async function ekran(liste: unknown[]) {
  mockApiGet.mockImplementationOnce(async () => liste);
  const u = render(<TreatmentHistoryScreen />);
  await act(async () => {});
  return u;
}

beforeEach(() => {
  mockApiGet.mockReset();
  mockApiGet.mockResolvedValue([]);
  mockArastirmaci = true;
});
afterEach(async () => {
  await act(async () => {
    await i18n.changeLanguage("tr");
  });
});

it("KRİTİK B-4: araştırmada adsız kayıt 'Sahipsiz örnek' (Bilinmeyen Hasta DEĞİL); silme etiketi de", async () => {
  const u = await ekran([seans(1)]);
  expect(u.getByText("Sahipsiz örnek")).toBeTruthy();
  expect(u.queryByText("Bilinmeyen Hasta")).toBeNull();
});

it("KRİTİK B-4: İngilizce 'Unowned sample'", async () => {
  await act(async () => {
    await i18n.changeLanguage("en");
  });
  const u = await ekran([seans(1)]);
  expect(u.getByText("Unowned sample")).toBeTruthy();
});

it("KARŞIT B-4: veteriner profilinde 'Bilinmeyen Hasta' AYNEN; adı olan kayıt adıyla", async () => {
  mockArastirmaci = false;
  const u = await ekran([seans(1), seans(2, { patient_name: "Plaka-7" })]);
  expect(u.getByText("Bilinmeyen Hasta")).toBeTruthy();
  expect(u.getByText("Plaka-7")).toBeTruthy();
  expect(u.queryByText("Sahipsiz örnek")).toBeNull();
});
