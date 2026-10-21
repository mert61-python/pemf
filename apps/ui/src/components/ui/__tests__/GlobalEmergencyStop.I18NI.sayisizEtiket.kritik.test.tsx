// Author: mertaygn, cglrgrkn
/**
 * I18NI-A2.9 KALICI KAPI (14-I18N-INCELEME): ACİL DURDUR düğmesinin SAYISIZ etiketi
 * (seans AKTİF ama çalışan bobin yok — başlatma / duraklama arası; düğme bu hâlde "🚨 ACİL DURDUR" der) hiçbir testte pinli değil. Ölçüldü: GES'in boşta dalı `kritikMetin("…dugme")`
 * yerine BAŞKA bir geçerli kritik anahtarı (`…tumBobinlerDugme`, `…durduruluyor` "🚨 DURDURULUYOR…") gösterse GES'in 9 jest dosyası
 * (34 test) + I18N0.kritik (4) + K-3 + K-5 + test_estop_erisimi YEŞİL kalıyor.
 * Koşum: bash $SP/ky.sh jest --runTestsByPath src/components/ui/__tests__/GlobalEmergencyStop.I18NI.sayisizEtiket.kritik.test.tsx
 */
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: { coils: [{ running: false }, { running: false }], activeTreatment: { isActive: true } } }),
}));
jest.mock("@/hooks/useStmBelirsiz", () => ({ useStmBelirsiz: () => false }));
jest.mock("@/services/emergencyStop", () => ({ performEmergencyStop: async () => ({ confirmed: true, kartReddetti: false }) }));
jest.mock("@/services/apiClient", () => ({ platformAlert: jest.fn() }));
jest.mock("@/services/toastBridge", () => ({ emitToast: jest.fn() }));
jest.mock("@/components/ui/UstKatman", () => ({ UstKatman: ({ children }: { children: unknown }) => children }));

import React from "react";
import { act, render } from "@testing-library/react-native";
import { GlobalEmergencyStop } from "@/components/ui/GlobalEmergencyStop";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";

const depo = { setItem: async () => undefined };

afterEach(async () => {
  __bayrakTestiAyarla(null);
  await act(async () => {
    await dilSec("tr", depo);
  });
});

it("TR (bayrak kapalı) SAYISIZ (seans aktif, 0 bobin): '🚨 ACİL DURDUR' — göç öncesi düz metinle BAYT BAYT aynı", () => {
  const u = render(<GlobalEmergencyStop />);
  expect(u.getByText("🚨 ACİL DURDUR")).toBeTruthy();
  expect(u.queryByText(/DURDURULUYOR|TÜM BOBİNLERİ|teyitsiz|bağlantı yok|bobin\)/)).toBeNull();
});

it("EN (bayrak açık) SAYISIZ (seans aktif, 0 bobin): '🚨 EMERGENCY STOP' (sayı / durum eki YOK)", async () => {
  __bayrakTestiAyarla(true);
  const u = render(<GlobalEmergencyStop />);
  await act(async () => {
    await dilSec("en", depo);
  });
  expect(u.getByText("🚨 EMERGENCY STOP")).toBeTruthy();
});
