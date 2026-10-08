/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * D2.57 (B-3.109) — "Tümünü Sil"de DELETE gerçekleşip VACUUM düşerse ekran "silindi" der, listeyi YENİLER ve disk temizliğinin
 * tamamlanamadığını AYRICA söyler.
 * ===========================================================================================================================
 * ÖLÇÜLEN KUSUR: backend VACUUM düşünce (kayıtlar SİLİNMİŞKEN) `{"status": "error"}` dönüyordu → ekran "Toplu silme işlemi
 * başarısız." deyip listeyi yenilemiyordu; operatör verinin durduğunu sanıyordu. `/patients/delete_all` yanıtı GERÇEK backend'den
 * üretilen fikstürdür (`tests/test_toplu_silme_VACUUM_duserse_SILINDI_der_D257.py`, VACUUM'u en alt katta düşen GERÇEK uç).
 * GERÇEK: AuthProvider, UserModeProvider (veteriner), OperatorProvider (operatörsüz klinik — Kural 2), AppNavProvider,
 * PatientScreen, apiClient. Sahte: fetch (kaydedici), Supabase istemcisi, toast, `window.confirm`, cihaz modülleri.
 */
jest.mock("react-native", () => jest.requireActual("react-native-web"));
jest.mock("@/services/supabaseAuth", () => {
  const aparat = require("../../context/__tests__/operatorAparati");
  return aparat.supabaseSahte("dr.a@klinik.com");
});
const mockToast = jest.fn();
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: mockToast }) }));
jest.mock("expo-haptics", () => ({ impactAsync: jest.fn(), notificationAsync: jest.fn(), selectionAsync: jest.fn(),
  ImpactFeedbackStyle: {}, NotificationFeedbackType: {} }));
jest.mock("expo-linear-gradient", () => {
  const R = require("react");
  const { View } = require("react-native-web");
  return { LinearGradient: ({ children, style }: { children?: unknown; style?: unknown }) => R.createElement(View, { style }, children) };
});

import React, { useEffect } from "react";
import { AuthProvider } from "@/context/AuthContext";
import { UserModeProvider, useUserMode } from "@/context/UserModeContext";
import { OperatorProvider } from "@/context/OperatorContext";
import { AppNavProvider } from "@/context/AppNavContext";
import { PatientScreen } from "@/screens/PatientScreen";
import { Sahne, sahteSunucu, type Istek } from "../../context/__tests__/operatorAparati";
import VACUUM_DUSTU from "./__fixtures__/hastaTumunuSil.D257.json";

const A = "dr.a@klinik.com";
const HASTALAR = [{ id: "p0", name: "HastaA", species: "Kedi", operator_email: A, created_at: "2026-10-01 10:00:00" }];

function Veteriner({ children }: { children: React.ReactNode }) {
  const { setUserMode, userMode } = useUserMode();
  useEffect(() => { setUserMode("veterinarian"); }, [setUserMode]);
  return userMode ? <>{children}</> : null;
}

let s: Sahne;
let kayit: Istek[];
let onay: jest.SpyInstance;
beforeEach(() => {
  jest.useFakeTimers();
  s = new Sahne();
  onay = jest.spyOn(window, "confirm").mockImplementation(() => true);
  mockToast.mockClear();
});
afterEach(async () => {
  await s.sok();
  onay.mockRestore();
  jest.useRealTimers();
});

async function tumunuSil(silYaniti: [number, unknown]) {
  let silindi = false;
  const sunucu = sahteSunucu([], (yol, _g, yontem) => {
    if (yontem === "GET" && yol === "/patients") return [200, { status: "success", data: silindi ? [] : HASTALAR }];
    if (yontem === "POST" && yol === "/patients/delete_all") {
      silindi = true;
      return silYaniti;
    }
    return undefined;
  });
  kayit = sunucu.kayit;
  global.fetch = sunucu.fetchSahte as unknown as typeof fetch;
  await s.ciz(
    <AuthProvider>
      <UserModeProvider>
        <Veteriner>
          <OperatorProvider>
            <AppNavProvider navigateTo={() => undefined}>
              <PatientScreen />
            </AppNavProvider>
          </OperatorProvider>
        </Veteriner>
      </UserModeProvider>
    </AuthProvider>,
  );
  await s.ilerlet(50);
  await s.bosalt(10);
  const listeOnce = kayit.filter((k) => k.yontem === "GET" && k.yol === "/patients").length;
  await s.metneTikla("Tümünü Sil");
  await s.bosalt(10);
  expect(kayit.filter((k) => k.yontem === "POST" && k.yol === "/patients/delete_all")).toHaveLength(1); // ARA: istek gitti
  return kayit.filter((k) => k.yontem === "GET" && k.yol === "/patients").length - listeOnce;
}

const bildirimler = () => mockToast.mock.calls.map((c) => [String(c[0]), c[1]]);

it("KRİTİK D2.57: VACUUM düşse de silme GERÇEKLEŞTİ → 'silindi' denir, liste YENİLENİR, disk temizliği uyarısı AYRICA verilir", async () => {
  const yenileme = await tumunuSil([VACUUM_DUSTU.durum, VACUUM_DUSTU.govde]);
  const metin = bildirimler().map((b) => b[0]).join(" | ");
  expect(metin).toContain("Tüm hastalar silindi");
  expect(metin).not.toContain("başarısız");
  expect(metin).toContain("disk temizliği");
  expect(yenileme).toBeGreaterThanOrEqual(1);
});

it("KARŞIT D2.57: VACUUM da başarılıysa yalnız 'silindi', uyarı YOK", async () => {
  await tumunuSil([200, { status: "success", deleted: 1, vacuum_ok: true }]);
  const metin = bildirimler().map((b) => b[0]).join(" | ");
  expect(metin).toContain("Tüm hastalar silindi");
  expect(metin).not.toContain("disk temizliği");
});
