/**
 * KP-3 C · PatientScreen silmenin KİMLİK kapıları (hasta kaydı) — her test bir DAVRANIŞ iddiası:
 *  (Kart silmenin kimliksiz kapısı arayüzden ULAŞILAMAZ: kimlik yokken / düşünce liste kayıt göstermez — KP-4 notu.)
 *  - "Tümünü sil" onayı REDDEDİLİRSE istek gitmez.
 *  - Kayıtlı operatörlü klinikte "Tümünü seç" yalnız BAŞKA hekimin hastalarını kapsıyorsa toplu silme istek göndermez, onay sormaz ve
 *    "başka hekimin kaydı silinemez" denir (D2.72 · Y92).
 * SAHTE: apiClient (ağ sınırı) · bildirim · bağlamlar (oturum / operatör / profil / gezinme — girdi) · masaüstü ana makine kararı.
 * GERÇEK: ekran + silinebilir kuralı (utils/patientScope) + çoklu seçim kancası. ⚠️ Ürün kodu DEĞİŞMEDİ — yalnız test.
 */
const mockConfirm = jest.fn(async (..._a: unknown[]) => true);
const mockApiGet = jest.fn();
const mockApiPost = jest.fn();
jest.mock("@/services/apiClient", () => ({
  apiGet: (...a: unknown[]) => mockApiGet(...a),
  apiPost: (...a: unknown[]) => mockApiPost(...a),
  platformConfirm: (...a: unknown[]) => mockConfirm(...a),
  platformAlert: jest.fn(),
  authHeaders: jest.fn(() => ({})),
}));
const mockToast = jest.fn();
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: mockToast }) }));
jest.mock("@/context/AppNavContext", () => ({ useAppNav: () => ({ navigateTo: jest.fn(), setSelectedPatient: jest.fn() }) }));
jest.mock("@/context/UserModeContext", () => ({ useUserMode: () => ({ userMode: "veterinarian", isExpert: true, isResearcher: false }) }));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "klinik@ortak.com" } }) }));
let mockOp: Record<string, unknown> | null = null;
jest.mock("@/context/OperatorContext", () => ({ useOperatorOptional: () => mockOp }));
jest.mock("@/services/desktopSession", () => ({ isDesktopHost: () => true }));

import React from "react";
import { act, fireEvent, render } from "@testing-library/react-native";
import i18n from "i18next";
import { PatientScreen } from "@/screens/PatientScreen";
import { profilSozlugu } from "@/utils/profilSozlugu";
import { baskaHekimSilmeMetni } from "@/utils/patientScope";

const T = (k: string, o?: object): string => (i18n.t as unknown as (k: string, o?: object) => string)(k, o);
const SK = profilSozlugu({ petOwner: false, researcher: false });
const OPERATORLER = [{ email: "v@x.com" }, { email: "baska@x.com" }];
const hasta = (id: string, ad: string, eposta: string) => ({
  id, name: ad, species: "Kedi", breed: "", age: "3", weight: "4", owner: "", vet_contact: "", owner_email: "", operator_email: eposta,
});

async function ekran(liste: unknown[]) {
  mockApiGet.mockImplementation(async (yol: string) => (yol === "/patients" ? { status: "success", data: liste } : { status: "success", data: [] }));
  const u = render(<PatientScreen />);
  await act(async () => {});
  await act(async () => {
    // Kimlik yokken kapsam düğmesi ÇİZİLMEZ → varsa basılır.
    const tum = u.queryByLabelText(T("hasta.liste.tumKapsamEtiketi", { tumKapsamKucuk: SK.tumKapsamKucuk, kayitlarAd: SK.kayitlarAd }));
    if (tum) fireEvent.press(tum);
  });
  return u;
}

beforeEach(() => {
  mockConfirm.mockReset();
  mockConfirm.mockImplementation(async () => true);
  mockApiGet.mockReset();
  mockApiPost.mockReset();
  mockApiPost.mockResolvedValue({ status: "success" });
  mockToast.mockReset();
});

it("'Tümünü sil' onayı reddedilirse istek gitmez", async () => {
  mockOp = { operatorEmail: "v@x.com", operators: OPERATORLER, kimlikDbOkunamiyor: false };
  const u = await ekran([hasta("p1", "Boncuk", "v@x.com")]);
  mockConfirm.mockImplementationOnce(async () => false);
  await act(async () => { fireEvent.press(u.getByText(T("hasta.sil.tumunuSil"))); });
  expect(mockConfirm).toHaveBeenCalledTimes(1);
  expect(mockApiPost).not.toHaveBeenCalled();
});

it("yalnız başka hekimin hastaları seçiliyse toplu silme istek göndermez, onay sormaz; 'başka hekim' denir", async () => {
  mockOp = { operatorEmail: "v@x.com", operators: OPERATORLER, kimlikDbOkunamiyor: false };
  const u = await ekran([hasta("p2", "Pamuk", "baska@x.com"), hasta("p3", "Zeytin", "baska@x.com")]);
  await act(async () => { fireEvent.press(u.getByText(T("hasta.liste.sec"))); });
  await act(async () => { fireEvent.press(u.getByTestId("hasta-secim-cubugu-tumunu")); });
  await act(async () => { fireEvent.press(u.getByTestId("hasta-secim-cubugu-sil")); });
  expect(mockConfirm).not.toHaveBeenCalled();
  expect(mockApiPost).not.toHaveBeenCalled();
  expect(mockToast).toHaveBeenLastCalledWith(baskaHekimSilmeMetni(), "error");
});
