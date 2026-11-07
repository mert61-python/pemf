/**
 * KP-3 C · src/screens/AiHistoryScreen.tsx kapsanmayan kolları — her test bir DAVRANIŞ iddiası (aiGecmisiAkordeon düzeneği):
 *  - Tarih: saniye (10 hane) ve milisaniye cinsinden epoch (sayı ya da rakam dizgesi) yerel "YYYY-AA-GG SS:DD" olarak, ISO dizge
 *    "T"siz 16 karakter olarak gösterilir; boş / null tarih boş kalır (ekran çökmez).
 *  - Sayfalama: tam sayfa (300) gelince "Daha fazla" görünür; basınca SON kaydın kimliğiyle (before_id) sonraki sayfa istenir ve
 *    EKLENİR; eksik sayfa gelince düğme kalkar; sunucu hata dönerse liste değişmez.
 *  - Modül filtresi: modül çipi yalnız o modülün kayıtlarını gösterir, "Tümü" geri getirir.
 *  - Liste okunamazsa hata durumu; "Yenile" yeniden okur.
 * SAHTE: apiClient (ağ sınırı) · kimlik / profil bağlamları (sabit girdi).
 */
const mockApiGet = jest.fn();
jest.mock("@/services/apiClient", () => ({
  apiGet: (...a: unknown[]) => mockApiGet(...a),
  apiPost: jest.fn(async () => ({ status: "success" })),
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
const basari = (data: unknown[]) => ({ status: "success", data });

async function ekran(ilk: unknown) {
  mockApiGet.mockImplementation(async (yol: string, fb: unknown) => (String(yol).startsWith("/ai/log") ? ilk : fb));
  const u = render(<AiHistoryScreen />);
  await act(async () => {});
  return u;
}
const p2 = (x: number) => String(x).padStart(2, "0");
const yerel = (ms: number) => {
  const d = new Date(ms);
  return `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())} ${p2(d.getHours())}:${p2(d.getMinutes())}`;
};

beforeEach(() => mockApiGet.mockReset());

it("tarih: saniye / milisaniye epoch (sayı ya da rakam dizgesi) yerel biçimde; ISO 'T'siz; boş tarih boş", async () => {
  const u = await ekran(basari([
    kayit(1, { created_at: 1_700_000_000, result_summary: "s-saniye" }),
    kayit(2, { created_at: "1700000000000", result_summary: "s-ms" }),
    kayit(3, { created_at: "2026-09-09T11:53:42.123", result_summary: "s-iso" }),
    kayit(4, { created_at: null, result_summary: "s-bos" }),
  ]));
  expect(u.getAllByText(yerel(1_700_000_000_000)).length).toBe(2);
  expect(u.getByText("2026-09-09 11:53")).toBeTruthy();
  expect(u.getByText("s-bos")).toBeTruthy(); // çökmeden çizildi
});

it("sayfalama: tam sayfa → 'Daha fazla'; before_id = SON kayıt; EKLENİR; eksik sayfada düğme kalkar; hata dönerse liste aynı", async () => {
  const ilk = Array.from({ length: 300 }, (_, i) => kayit(1000 - i));
  const u = await ekran(basari(ilk));
  expect(u.getByLabelText(T("ai.gecmis.dahaFazlaEtiket"))).toBeTruthy();
  mockApiGet.mockImplementationOnce(async () => ({ status: "error", data: [] }));
  await act(async () => { fireEvent.press(u.getByLabelText(T("ai.gecmis.dahaFazlaEtiket"))); });
  expect(mockApiGet).toHaveBeenLastCalledWith("/ai/log?limit=300&before_id=701", { status: "error", data: [] });
  expect(u.queryByText("özet-1")).toBeNull();
  mockApiGet.mockImplementationOnce(async () => basari([kayit(5), kayit(4)]));
  await act(async () => { fireEvent.press(u.getByLabelText(T("ai.gecmis.dahaFazlaEtiket"))); });
  expect(u.getByText("özet-4")).toBeTruthy();
  expect(u.getByText("özet-1000")).toBeTruthy(); // önceki sayfa KORUNDU
  expect(u.queryByLabelText(T("ai.gecmis.dahaFazlaEtiket"))).toBeNull();
}, 30000);

it("modül çipi yalnız o modülü gösterir; 'Tümü' geri getirir", async () => {
  const u = await ekran(basari([
    kayit(1, { module_label: "Kedi Sesi", module_id: "cat_sound", result_summary: "ses-1" }),
    kayit(2, { result_summary: "fgs-2" }),
  ]));
  await act(async () => { fireEvent.press(u.getByLabelText(T("ai.gecmis.filtreEtiketi", { label: "Kedi Sesi" }))); });
  expect(u.getByText("ses-1")).toBeTruthy();
  expect(u.queryByText("fgs-2")).toBeNull();
  await act(async () => { fireEvent.press(u.getByLabelText(T("ai.gecmis.filtreEtiketi", { label: T("ai.gecmis.tumu") }))); });
  expect(u.getByText("fgs-2")).toBeTruthy();
});

it("liste okunamazsa hata durumu; 'Yenile' yeniden okur ve listeyi getirir", async () => {
  const u = await ekran({ status: "error", data: [] });
  expect(u.queryByText("özet-9")).toBeNull();
  mockApiGet.mockImplementation(async (yol: string, fb: unknown) => (String(yol).startsWith("/ai/log") ? basari([kayit(9)]) : fb));
  await act(async () => { fireEvent.press(u.getByLabelText(T("ai.gecmis.yenileEtiketi"))); });
  expect(u.getByText("özet-9")).toBeTruthy();
});
