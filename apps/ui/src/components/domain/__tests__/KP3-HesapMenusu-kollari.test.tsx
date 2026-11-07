/**
 * KP-3 C · HesapMenusu kapsanmayan kolları — her test bir DAVRANIŞ iddiası (CH1 düzeneğinin aynısı):
 *  - Geçiş düşerse menü AÇIK kalır ve gerekçe (yoksa "değiştirilemedi") yazılır.
 *  - Park edilmiş hesaptan çıkış: onay metni hangi hesaptan çıkıldığını ve ETKİN hesabın kaldığını söyler; onay reddedilirse çıkış YOK;
 *    çıkış düşerse gerekçe (yoksa "çıkılamadı") yazılır.
 *  - Etkin hesaptan çıkış (başka hesap varken): onay "diğer hesaba geçilir" der; düşerse sunucunun gerekçesi yazılır.
 * SAHTE: AuthContext (hesap işlemleri), canlı veri, operatör bağlamı, onay penceresi; ACİL DURDUR çizimi yer tutucu.
 */
let mockAuth: any;
const mockConfirm = jest.fn(async (..._a: unknown[]) => true);
jest.mock("@/context/AuthContext", () => ({ useAuth: () => mockAuth }));
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: { coils: [{ id: 1, running: false }], activeTreatment: { isActive: false } }, donanimBelirsiz: false }),
}));
jest.mock("@/context/OperatorContext", () => ({ useOperatorOptional: () => ({ multiUser: false, active: null, lock: jest.fn() }) }));
jest.mock("@/services/apiClient", () => ({
  platformConfirm: (...a: unknown[]) => mockConfirm(...a),
  apiGet: jest.fn(async () => null),
}));
jest.mock("@/services/supabaseAuth", () => ({
  supabaseAuth: { auth: {} },
  oturumDeposu: { getItem: async () => null, setItem: async () => undefined, removeItem: async () => undefined },
}));
jest.mock("@/components/ui/GlobalEmergencyStop", () => ({ GlobalEmergencyStop: () => null }));

import React from "react";
import { act, fireEvent, render } from "@testing-library/react-native";
import i18n from "i18next";
import { HesapMenusu } from "@/components/domain/HesapMenusu";

const T = (k: string, o?: object): string => (i18n.t as unknown as (k: string, o?: object) => string)(k, o);
const A = "a@klinik.com";
const B = "b@klinik.com";

beforeEach(() => {
  mockConfirm.mockReset();
  mockConfirm.mockImplementation(async () => true);
  mockAuth = {
    session: { email: A },
    hesaplar: [A, B],
    hesabaGec: jest.fn(async () => ({ ok: true })),
    hesaptanCik: jest.fn(async () => ({ ok: true })),
    hesapEkle: jest.fn(async () => undefined),
  };
});
const ciz = () => {
  const kapat = jest.fn();
  return { u: render(<HesapMenusu visible onClose={kapat} onTumundenCik={jest.fn()} />), kapat };
};
const bas = async (u: ReturnType<typeof render>, etiket: string) => { await act(async () => { fireEvent.press(u.getByLabelText(etiket)); }); };

it("geçiş düşerse menü açık kalır; gerekçe, yoksa 'değiştirilemedi' yazılır", async () => {
  mockAuth.hesabaGec = jest.fn()
    .mockResolvedValueOnce({ ok: false, hata: "B hesabının oturumu sona ermiş — yeniden giriş yapın." })
    .mockResolvedValueOnce({ ok: false });
  const { u, kapat } = ciz();
  await bas(u, T("hesap.menu.hesabaGecEtiketi", { e: B }));
  expect(u.getByText("B hesabının oturumu sona ermiş — yeniden giriş yapın.")).toBeTruthy();
  await bas(u, T("hesap.menu.hesabaGecEtiketi", { e: B }));
  expect(u.getByText(T("hesap.menu.degistirilemedi"))).toBeTruthy();
  expect(kapat).not.toHaveBeenCalled();
});

it("park edilmiş hesaptan çıkış: onay metni doğru; reddedilirse çıkış YOK; düşerse 'çıkılamadı'", async () => {
  mockAuth.hesaptanCik = jest.fn(async () => ({ ok: false }));
  const { u } = ciz();
  mockConfirm.mockImplementationOnce(async () => false);
  await bas(u, T("hesap.menu.hesaptanCikEtiketi", { e: B }));
  expect(mockConfirm.mock.calls[0][1]).toBe(T("hesap.menu.cikisGovdeBaska", { eposta: B, etkin: A }));
  expect(mockAuth.hesaptanCik).not.toHaveBeenCalled();
  await bas(u, T("hesap.menu.hesaptanCikEtiketi", { e: B }));
  expect(mockAuth.hesaptanCik).toHaveBeenCalledWith(B);
  expect(u.getByText(T("hesap.menu.cikilamadi"))).toBeTruthy();
});

it("etkin hesaptan çıkış (başka hesap varken): onay 'diğerine geçilir' der; düşerse sunucunun gerekçesi", async () => {
  mockAuth.hesaptanCik = jest.fn(async () => ({ ok: false, hata: "Sunucuya ulaşılamadı; çıkış yerelde tamamlanmadı." }));
  const { u } = ciz();
  await bas(u, T("hesap.menu.hesaptanCikEtiketi", { e: A }));
  expect(mockConfirm.mock.calls[0][1]).toBe(T("hesap.menu.cikisGovdeGecer", { eposta: A }));
  expect(mockAuth.hesaptanCik).toHaveBeenCalledWith(A);
  expect(u.getByText("Sunucuya ulaşılamadı; çıkış yerelde tamamlanmadı.")).toBeTruthy();
});
