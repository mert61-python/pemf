/**
 * KP-4 B1 · src/components/domain/PatientGate.tsx — hasta seçicinin "Kapat" düğmesi seçiciyi SEÇİM YAPMADAN kapatır: hasta paylaşılmaz,
 * kapı yeniden "Hasta seçin" der, sert kipte modüller gizli kalır.
 * GERÇEK: PatientGate, apiClient (hasta listesi). SAHTE (en alt kat): fetch; bağlamlar sabit girdi (gezinme / seçim çağrıları gözlenir).
 */
const mockNav = { selectedPatient: null as null | { id: string; name: string }, setSelectedPatient: jest.fn(), navigateTo: jest.fn() };
jest.mock("@/context/AppNavContext", () => ({ useAppNav: () => mockNav }));
jest.mock("@/context/UserModeContext", () => ({ useUserMode: () => ({ isExpert: true, isResearcher: false }) }));
jest.mock("@/context/OperatorContext", () => ({ useOperatorOptional: () => ({ operatorEmail: "vet@klinik.com" }) }));

import React from "react";
import { Text } from "react-native";
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";
import i18n from "i18next";

import { PatientGate } from "../PatientGate";

const T = (k: string, o?: object): string => (i18n.t as unknown as (k: string, o?: object) => string)(k, o);
const HASTALAR = [{ id: "7", name: "Boncuk", species: "Kedi", operator_email: "vet@klinik.com" }];

beforeEach(() => {
  mockNav.selectedPatient = null;
  mockNav.setSelectedPatient.mockClear();
  (global as unknown as { fetch: unknown }).fetch = jest.fn(async () => ({
    ok: true, status: 200, json: async () => ({ status: "success", data: HASTALAR }),
    text: async () => JSON.stringify({ status: "success", data: HASTALAR }), headers: { get: () => "application/json" },
  }));
});

it("KRİTİK: seçicideki 'Kapat' seçim yapmadan kapatır — hasta paylaşılmaz, modüller gizli kalır", async () => {
  const u = render(<PatientGate><Text>MODULLER</Text></PatientGate>);
  await act(async () => { fireEvent.press(u.getByLabelText("Hasta seçin")); });
  await waitFor(() => expect(u.getByLabelText("Seç: Boncuk")).toBeTruthy());
  await act(async () => { fireEvent.press(u.getByLabelText(T("ortak.kapat"))); });
  expect(u.queryByLabelText("Seç: Boncuk")).toBeNull();
  expect(u.getByLabelText("Hasta seçin")).toBeTruthy();
  expect(mockNav.setSelectedPatient).not.toHaveBeenCalled();
  expect(u.queryByText("MODULLER")).toBeNull();
});
