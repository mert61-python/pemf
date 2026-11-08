/**
 * KP-3 C · TreatmentHistoryScreen toplu silmenin KİMLİK kapıları (tıbbi kayıt) — her test bir DAVRANIŞ iddiası:
 *  (Kimliksiz silme kapısı arayüzden ULAŞILAMAZ: kimlik yokken / düşünce liste kayıt göstermez — KP-4 notu.)
 *  - Kayıtlı operatörlü klinikte "Tümünü seç" yalnız BAŞKA hekimin seanslarını kapsıyorsa istek gitmez, onay sorulmaz ve "başka
 *    hekimin kaydı silinemez" denir (D2.72 · Y92).
 * SAHTE: apiClient (ağ sınırı) · bildirim · bağlamlar (oturum / operatör / profil — girdi) · detay modalı. GERÇEK: ekran + silinebilir
 * kuralı (utils/patientScope) + çoklu seçim kancası.
 * ⚠️ Ürün kodu (silme / kimlik) DEĞİŞMEDİ — yalnız test.
 */
const mockConfirm = jest.fn(async (..._a: unknown[]) => true);
const mockApiGet = jest.fn();
const mockApiPost = jest.fn();
jest.mock("@/services/apiClient", () => ({
  apiGet: (...a: unknown[]) => mockApiGet(...a),
  apiPost: (...a: unknown[]) => mockApiPost(...a),
  platformAlert: jest.fn(),
  platformConfirm: (...a: unknown[]) => mockConfirm(...a),
  authHeaders: jest.fn(() => ({})),
}));
jest.mock("@/services/config", () => ({ serviceConfig: { apiBaseUrl: "http://192.168.1.5:18080/api" } }));
jest.mock("@/services/dosyaIndir", () => ({ downloadFileWithAuth: jest.fn(), backendBuMakinede: () => false }));
const mockToast = jest.fn();
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: mockToast }) }));
jest.mock("@/components/domain/SessionDetailModal", () => ({ SessionDetailModal: () => null }));
jest.mock("@/context/UserModeContext", () => ({ useUserMode: () => ({ userMode: "veterinarian", isExpert: true, isResearcher: false }) }));
let mockOturum: { email: string } | null = null;
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: mockOturum }) }));
let mockOp: Record<string, unknown> | null = null;
jest.mock("@/context/OperatorContext", () => ({ useOperatorOptional: () => mockOp }));

import React from "react";
import { act, fireEvent, render } from "@testing-library/react-native";
import i18n from "i18next";
import { TreatmentHistoryScreen } from "@/screens/TreatmentHistoryScreen";
import { profilSozlugu } from "@/utils/profilSozlugu";
import { baskaHekimSilmeMetni } from "@/utils/patientScope";

const T = (k: string, o?: object): string => (i18n.t as unknown as (k: string, o?: object) => string)(k, o);
const seans = (id: number, eposta: string) => ({
  id, patient_name: `Hasta-${id}`, session_status: "completed", operator_email: eposta, patient_notes: "",
  session_date: "2026-11-01", treatment_mode: "Manuel", duration_minutes: 20, frequency_hz: 50,
});

async function tumunuSecipSil(liste: unknown[]) {
  mockApiGet.mockImplementationOnce(async () => liste);
  const u = render(<TreatmentHistoryScreen />);
  await act(async () => {});
  await act(async () => {
    // Kimlik yokken kapsam düğmesi ÇİZİLMEZ (yalnız sahipsiz kayıtlar listelenir) → varsa basılır.
    const tum = u.queryByLabelText(T("seans.gecmis.tumKapsamEtiketi", { tumKapsamKucuk: profilSozlugu({ researcher: false }).tumKapsamKucuk }));
    if (tum) fireEvent.press(tum);
  });
  await act(async () => { fireEvent.press(u.getByLabelText(T("seans.gecmis.secimKipiEtiketi"))); });
  await act(async () => { fireEvent.press(u.getByTestId("gecmis-secim-cubugu-tumunu")); });
  await act(async () => { fireEvent.press(u.getByTestId("gecmis-secim-cubugu-sil")); });
  return u;
}

beforeEach(() => {
  mockConfirm.mockClear();
  mockApiGet.mockReset();
  mockApiGet.mockResolvedValue([]);
  mockApiPost.mockReset();
  mockToast.mockReset();
});

it("kayıtlı operatörlü klinikte yalnız başka hekimin seansları seçiliyse istek gitmez; 'başka hekim' denir", async () => {
  mockOturum = { email: "klinik@ortak.com" };
  mockOp = { operatorEmail: "v@x.com", operators: [{ email: "v@x.com" }, { email: "baska@x.com" }], kimlikDbOkunamiyor: false };
  await tumunuSecipSil([seans(2, "baska@x.com"), seans(3, "baska@x.com")]);
  expect(mockConfirm).not.toHaveBeenCalled();
  expect(mockApiPost).not.toHaveBeenCalled();
  expect(mockToast).toHaveBeenLastCalledWith(baskaHekimSilmeMetni(), "error");
});
