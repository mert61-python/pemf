// Author: mertaygn, cglrgrkn
/**
 * 22-SON A2.2 · L1-7.11'in İKİZ YERİ — Android açılış kapısında (MobileUpdateGate: "kontrol" ≤ 7 sn, "güncelleme" SINIRSIZ) bobin çalışırken
 * ACİL DURDUR VAR ve basınca STOP isteği GİDER.
 * ================================================================================================================================
 * ÖLÇÜLEN KUSUR (HEAD `8b002fc0`): `app/_layout.tsx` Android'de `MobileUpdateGate`'i AuthGate'ten ÖNCE çizer; kapı `PemfApp`'in
 * `LiveDataProvider`'ının DIŞINDA ve ekranında `GlobalEmergencyStop` YOK. L1-7.11 (C79) yalnız AuthGate splash'ini kapattı.
 * SAĞLAYICI MODELİ: `useLiveData` sağlayıcı DIŞINDA gerçekte varsayılan bağlamı (örnek veri — canlı değil) döndürür; burada sağlayıcı dışında
 * BOŞ anlık görüntü döner → kapı kendi canlı veri sağlayıcısını kurmadan GES'i çizse de düğme GÖRÜNMEZ (sağlayıcısız sahte düzeltme KIRMIZI).
 * GERÇEK: `MobileUpdateGate`, `GlobalEmergencyStop`, `performEmergencyStop`; sahte: güncelleme servisi, `apiPost`, `fetch`, LiveData bağlamı.
 */
jest.mock("expo-file-system/legacy", () => ({
  cacheDirectory: "file:///cache/",
  createDownloadResumable: jest.fn(),
  getInfoAsync: jest.fn(),
  deleteAsync: jest.fn(),
}));
jest.mock("@/services/mobileUpdate", () => {
  const gercek = jest.requireActual("@/services/mobileUpdate");
  return { ...gercek, guncellemeVarMi: jest.fn(), apkIndir: jest.fn(), kurulumuBaslat: jest.fn() };
});
let mockSnap: any;
jest.mock("@/context/LiveDataContext", () => {
  const R = require("react");
  const Ic = R.createContext(false);
  return {
    LiveDataProvider: ({ children }: any) => R.createElement(Ic.Provider, { value: true }, children),
    useLiveData: () => (R.useContext(Ic) ? { snapshot: mockSnap } : { snapshot: { coils: [], activeTreatment: { isActive: false } } }),
  };
});
jest.mock("@/services/config", () => ({
  serviceConfig: { apiBaseUrl: "http://127.0.0.1:65530/api", bridgeBaseUrl: "http://127.0.0.1:65530/api", apiToken: "" },
}));
const mockApiPost = jest.fn(async () => null);
jest.mock("@/services/apiClient", () => ({
  apiPost: (...a: unknown[]) => (mockApiPost as any)(...a),
  apiGet: jest.fn(async () => null),
  authHeaders: () => ({}),
  platformAlert: jest.fn(),
}));
jest.mock("@/services/toastBridge", () => ({ emitToast: jest.fn() }));

import React from "react";
import { act, fireEvent, render } from "@testing-library/react-native";
import { Platform, Text } from "react-native";
import { MobileUpdateGate } from "@/components/domain/MobileUpdateGate";
import { guncellemeVarMi, _atlamayiSifirla, _indirmeyiSifirla, _kurulumErtelemesiniSifirla } from "@/services/mobileUpdate";

void React;
const mockVarMi = guncellemeVarMi as jest.Mock;
const calisan = { stm: "online", coils: [{ id: 1, running: true, connected: true }], activeTreatment: { isActive: false } };
const bosta = { stm: "online", coils: [{ id: 1, running: false, connected: true }], activeTreatment: { isActive: false } };
const SURUM = { version: "2.4.0", versionCode: 30, url: "https://example.invalid/x.apk", sha256: "a".repeat(64), size: 1, notes: "n" };
const UYGULAMA = "UYGULAMA-ICERIGI";
const ciz = () => render(<MobileUpdateGate><Text>{UYGULAMA}</Text></MobileUpdateGate>);
const bekle = async () => { for (let i = 0; i < 4; i++) await act(async () => {}); };
let eskiOS: string;

beforeEach(() => {
  _atlamayiSifirla();
  _indirmeyiSifirla();
  _kurulumErtelemesiniSifirla();
  mockApiPost.mockClear();
  (global as any).fetch = jest.fn(async () => ({ ok: true, status: 200, json: async () => ({ confirmed: true }) }));
  eskiOS = Platform.OS;
  Object.defineProperty(Platform, "OS", { value: "android", configurable: true, writable: true });
});
afterEach(() => {
  Object.defineProperty(Platform, "OS", { value: eskiOS, configurable: true, writable: true });
});

it("KRİTİK SON-A2.2: Android açılış kapısı KONTROL sürerken bobin çalışıyorsa ACİL DURDUR ekranda ve basınca STOP GİDER", async () => {
  mockSnap = calisan;
  mockVarMi.mockReturnValue(new Promise(() => {})); // kontrol sürüyor
  const u = ciz();
  await bekle();
  expect(u.queryByText(UYGULAMA)).toBeNull(); // aparat: gerçekten kapı
  expect(u.getByTestId("mobil-acilis-kapisi")).toBeTruthy();
  expect(u.queryByLabelText("Acil durdur")).not.toBeNull();
  await act(async () => { fireEvent.press(u.getByLabelText("Acil durdur")); });
  for (let i = 0; i < 5; i++) await act(async () => {});
  const yollar = mockApiPost.mock.calls.map((c: any[]) => String(c[0]));
  expect(yollar).toEqual(expect.arrayContaining(["/hardware/emergency_stop", "/hardware/command", "/session/stop"]));
});

it("KRİTİK SON-A2.2: Android GÜNCELLEME ekranında (süresiz, 'Şimdilik devam et'e dek) bobin çalışıyorsa ACİL DURDUR ekranda", async () => {
  mockSnap = calisan;
  mockVarMi.mockResolvedValue({ varMi: true, surum: SURUM });
  const u = ciz();
  await bekle();
  expect(u.queryByText(UYGULAMA)).toBeNull();
  expect(u.queryByText(/2\.4\.0/)).not.toBeNull(); // aparat: gerçekten güncelleme ekranı
  expect(u.queryByLabelText("Acil durdur")).not.toBeNull();
});

it("karşıt: kapıda bobin BOŞTAYKEN ACİL DURDUR çizilmez (gürültü yok) ve kapı açılınca çocuk çizilir", async () => {
  mockSnap = bosta;
  mockVarMi.mockReturnValue(new Promise(() => {}));
  const u = ciz();
  await bekle();
  expect(u.getByTestId("mobil-acilis-kapisi")).toBeTruthy();
  expect(u.queryByLabelText("Acil durdur")).toBeNull();
});
