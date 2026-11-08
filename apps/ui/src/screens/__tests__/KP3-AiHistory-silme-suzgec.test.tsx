/**
 * KP-3 C · AiHistoryScreen tekil silme + hasta süzgeci — her test bir DAVRANIŞ iddiası (C13 düzeneği):
 *  - Tekil silme sunucuda DÜŞERSE kayıt listede KALIR (silinmiş gibi görünmez); başarılıysa yerinde çıkar.
 *  - Hasta süzgecinde seçili hastanın SON kaydı silinince süzgeç "Tüm hastalar"a döner (boş listeye kilitli kalmaz) — diğer
 *    hastaların kayıtları yeniden görünür.
 * SAHTE: apiClient (ağ sınırı) · kimlik / profil bağlamları (sabit girdi).
 */
const mockApiGet = jest.fn();
const mockApiPost = jest.fn(async (..._a: unknown[]) => ({ status: "success" }) as unknown);
jest.mock("@/services/apiClient", () => ({
  apiGet: (...a: unknown[]) => mockApiGet(...a),
  apiPost: (...a: unknown[]) => mockApiPost(...a),
  platformConfirm: jest.fn(async () => true),
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "a@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({ useOperatorOptional: () => ({ operatorEmail: "a@x.com" }) }));
jest.mock("@/context/UserModeContext", () => ({
  useUserMode: () => ({ userMode: "veterinarian", isExpert: true, isResearcher: false }),
}));

import { act, fireEvent, render } from "@testing-library/react-native";
import React from "react";
import i18n from "i18next";
import { AiHistoryScreen } from "@/screens/AiHistoryScreen";

const T = (k: string, o?: object): string => (i18n.t as unknown as (k: string, o?: object) => string)(k, o);
const kayit = (id: number, ek: Record<string, unknown> = {}) => ({
  id, created_at: "2026-09-09T11:53:00", mode: "veterinarian", module_id: "landmark", module_label: "Ağrı Analizi (FGS)",
  patient_name: "Mia", operator_email: "a@x.com", input_type: "image", result_summary: `özet-${id}`, ...ek,
});
const LISTE = () => ({ status: "success", data: [kayit(1), kayit(2, { patient_name: "Boncuk", module_label: "Yara" })] });

async function ekran() {
  mockApiGet.mockImplementation(async (yol: string, fb: unknown) => (String(yol).startsWith("/ai/log") ? LISTE() : fb));
  const u = render(<AiHistoryScreen />);
  await act(async () => {});
  return u;
}
async function yarayiSil(u: ReturnType<typeof render>) {
  await act(async () => { fireEvent.press(u.getByLabelText(T("ai.gecmis.kayitEtiketi", { ad: "Yara", acik: "" }))); });
  await act(async () => { fireEvent.press(u.getByLabelText(T("ai.gecmis.kaydiSilEtiketi", { ad: "Yara" }))); });
}

beforeEach(() => { mockApiGet.mockReset(); mockApiPost.mockClear(); });

it("tekil silme düşerse kayıt kalır; başarılıysa yerinde çıkar", async () => {
  const u = await ekran();
  mockApiPost.mockResolvedValueOnce(null);
  await yarayiSil(u);
  expect(mockApiPost).toHaveBeenCalledWith("/ai/log/delete", { id: 2, operator_email: "a@x.com" }, null);
  expect(u.getByText("özet-2")).toBeTruthy();
  await act(async () => { fireEvent.press(u.getByLabelText(T("ai.gecmis.kaydiSilEtiketi", { ad: "Yara" }))); });
  expect(u.queryByText("özet-2")).toBeNull();
  expect(u.getByText("özet-1")).toBeTruthy();
});

it("seçili hastanın son kaydı silinince süzgeç 'Tüm hastalar'a döner; diğer kayıtlar görünür", async () => {
  const u = await ekran();
  await act(async () => { fireEvent.press(u.getAllByText("Boncuk")[0]); });
  expect(u.queryByText("özet-1")).toBeNull(); // süzgeç: yalnız Boncuk
  await yarayiSil(u);
  expect(u.queryByText("özet-2")).toBeNull();
  expect(u.getByText("özet-1")).toBeTruthy(); // süzgeç "Tüm hastalar"a döndü
});
