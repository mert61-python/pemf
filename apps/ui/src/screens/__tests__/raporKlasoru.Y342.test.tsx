// Author: mertaygn, cglrgrkn
/**
 * Y342 (sahip 27-11; istem 63 YS3 e): PDF / CSV "İndir" düğmelerinin dosyası artık Masaüstü yerine (OneDrive'a bağlıysa buluta
 * gidiyordu) bulut eşitlemesi DIŞINDAKİ "PEMF Vet\Raporlar" klasöründe — Seans Geçmişi'nde klasörü açan eylem (TR + EN), Y331'in
 * "Seans CSV klasörü" eylemiyle AYNI yol (ortak `klasoruAc`). Yalnız backend bu bilgisayardayken çizilir; sunucu da yalnız cihazın
 * kendi ekranından açar, uzak istemciye yolu söyler. Sonuç operatöre söylenir (sessiz başarı / sessiz hata yok).
 */
jest.mock("react-native", () => {
  const RN = jest.requireActual("react-native");
  RN.Platform.OS = "web";
  return RN;
});
let mockYanit: unknown = null;
const mockApiPost = jest.fn(async () => mockYanit);
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async () => []),
  apiPost: (...a: unknown[]) => (mockApiPost as unknown as (...b: unknown[]) => Promise<unknown>)(...a),
  platformConfirm: jest.fn(async () => false),
  platformAlert: jest.fn(),
  authHeaders: jest.fn(() => ({})),
}));
jest.mock("@/services/config", () => ({ serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api" } }));
const mockToast = jest.fn();
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: mockToast }) }));
jest.mock("@/context/AppNavContext", () => ({ useAppNav: () => ({ selectedPatient: null }) }));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "a@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({
  useOperatorOptional: () => ({ operatorEmail: "a@x.com", operators: [], kimlikDbOkunamiyor: false }),
}));
jest.mock("@/context/UserModeContext", () => ({ useUserMode: () => ({ isExpert: true, isResearcher: false }) }));
jest.mock("@/services/dosyaIndir", () => ({ downloadFileWithAuth: jest.fn() }));
let mockBuMakine = true;
jest.mock("@/services/backendKonumu", () => ({ backendBuMakinede: () => mockBuMakine }));
jest.mock("expo-file-system/legacy", () => ({ cacheDirectory: "file:///", downloadAsync: jest.fn(), deleteAsync: jest.fn() }));
jest.mock("expo-sharing", () => ({ isAvailableAsync: jest.fn(async () => false), shareAsync: jest.fn() }));

import { act, fireEvent, render } from "@testing-library/react-native";
import React from "react";

import { TreatmentHistoryScreen } from "@/screens/TreatmentHistoryScreen";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";

const depo = { setItem: async () => undefined };
const YOL = "C:\\Users\\vet\\PEMF Vet\\Raporlar";

beforeEach(() => {
  mockBuMakine = true;
  mockYanit = null;
  mockApiPost.mockClear();
  mockToast.mockReset();
});
afterEach(async () => {
  __bayrakTestiAyarla(null);
  await act(async () => {
    await dilSec("tr", depo);
  });
});

async function ekran() {
  const u = render(<TreatmentHistoryScreen />);
  await act(async () => {});
  return u;
}

it("KRİTİK Y342: masaüstünde 'Raporlar klasörü' eylemi RAPORLAR klasörünü açtırır (CSV klasörünü değil) ve yolu söyler", async () => {
  mockYanit = { status: "success", yol: YOL };
  const u = await ekran();
  const d = u.getByTestId("gecmis-rapor-klasoru");
  expect(u.getByText("📂 Raporlar klasörü")).toBeTruthy();
  expect(d.props.accessibilityLabel).toBe("İndirilen PDF / CSV raporlarının klasörünü bu bilgisayarda aç");
  await act(async () => { fireEvent.press(d); });
  expect(mockApiPost).toHaveBeenCalledTimes(1);
  expect(mockApiPost).toHaveBeenCalledWith("/history/raporlar_klasoru/ac", {}, null);
  expect(mockToast).toHaveBeenLastCalledWith(`Raporlar klasörü açıldı: ${YOL}`, "success");
});

it("uzak yanıt → yol bilgi olarak; yanıt yok → hata söylenir; yolsuz yanıt 'undefined' yazmaz", async () => {
  mockYanit = { status: "uzak", yol: YOL };
  const u = await ekran();
  await act(async () => { fireEvent.press(u.getByTestId("gecmis-rapor-klasoru")); });
  expect(mockToast).toHaveBeenLastCalledWith(`Raporlar cihaz bilgisayarında: ${YOL}`, "info");
  mockYanit = null;
  await act(async () => { fireEvent.press(u.getByTestId("gecmis-rapor-klasoru")); });
  expect(mockToast).toHaveBeenLastCalledWith("Raporlar klasörü açılamadı.", "error");
  mockYanit = { status: "success" };
  await act(async () => { fireEvent.press(u.getByTestId("gecmis-rapor-klasoru")); });
  expect(mockToast).toHaveBeenLastCalledWith("Raporlar klasörü açıldı: ", "success");
  mockYanit = { status: "uzak" };
  await act(async () => { fireEvent.press(u.getByTestId("gecmis-rapor-klasoru")); });
  expect(mockToast).toHaveBeenLastCalledWith("Raporlar cihaz bilgisayarında: ", "info");
});

it("KARŞIT: Y331 'Seans CSV klasörü' eylemi ortak yoldan sonra da KENDİ klasörünü açar", async () => {
  mockYanit = { status: "success", yol: "C:\\Users\\vet\\PEMF Vet\\Seans CSV" };
  const u = await ekran();
  await act(async () => { fireEvent.press(u.getByTestId("gecmis-csv-klasoru")); });
  expect(mockApiPost).toHaveBeenCalledWith("/history/seans_csv_klasoru/ac", {}, null);
  expect(mockToast).toHaveBeenLastCalledWith("Seans CSV klasörü açıldı: C:\\Users\\vet\\PEMF Vet\\Seans CSV", "success");
});

it("KARŞIT: backend bu bilgisayarda değilse (telefon / tarayıcı) eylem ÇİZİLMEZ", async () => {
  mockBuMakine = false;
  const u = await ekran();
  expect(u.queryByTestId("gecmis-rapor-klasoru")).toBeNull();
});

it("EN: etiket ve bildirim İngilizce", async () => {
  __bayrakTestiAyarla(true);
  await act(async () => {
    await dilSec("en", depo);
  });
  mockYanit = { status: "success", yol: YOL };
  const u = await ekran();
  expect(u.getByText("📂 Reports folder")).toBeTruthy();
  await act(async () => { fireEvent.press(u.getByTestId("gecmis-rapor-klasoru")); });
  expect(mockToast).toHaveBeenLastCalledWith(`Reports folder opened: ${YOL}`, "success");
});
