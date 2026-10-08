/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * Y108 (S-B.5 · O-B.8) — var olmayan hastanın silinmesi: sunucu 404 → arayüz "zaten silinmiş" der ve listeyi YENİLER (seans
 * kartındaki D2.43 deseni). Eskiden 404 / `{"status":"error"}` genel "Hasta silinemedi." hatasıydı — başka cihazda zaten silinmiş
 * hasta için operatör "silme çalışmıyor" sanıyordu. Gerçek hata (500) "zaten silinmiş" DENMEZ; sunucunun gerekçesi gösterilir.
 *
 * GERÇEK: AuthProvider, UserModeProvider (veteriner), OperatorProvider (operatörsüz — Kural 2), AppNavProvider, PatientScreen,
 * apiClient. Sahte yalnız `fetch` (kaydedici; tekil silme yanıtı ayarlanabilir), Supabase istemcisi, toast, `window.confirm`.
 */
jest.mock("react-native", () => jest.requireActual("react-native-web"));
jest.mock("@/services/supabaseAuth", () => {
  const aparat = require("../../context/__tests__/operatorAparati");
  return {
    ...aparat.supabaseSahte(""),
    getCurrentSession: async () => ({ access_token: "x", user: { email: "tek@klinik.com", user_metadata: {} } }),
  };
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

const ZATEN = "Bu hasta zaten silinmiş — liste yenilendi.";

function Veteriner({ children }: { children: React.ReactNode }) {
  const { setUserMode, userMode } = useUserMode();
  useEffect(() => { setUserMode("veterinarian"); }, [setUserMode]);
  return userMode ? <>{children}</> : null;
}

let s: Sahne;
let kayit: Istek[];
let tekil: [number, unknown] = [200, { status: "success" }];
beforeEach(() => {
  jest.useFakeTimers();
  s = new Sahne();
  mockToast.mockClear();
  jest.spyOn(window, "confirm").mockImplementation(() => true);
});
afterEach(async () => {
  await s.sok();
  (window.confirm as jest.Mock).mockRestore?.();
  jest.useRealTimers();
});

async function kur() {
  const sunucu = sahteSunucu([], (yol, _g, yontem) => {
    if (yontem === "GET" && yol === "/patients") {
      return [200, { status: "success", data: [{ id: "p0", name: "HastaT", species: "Kedi", operator_email: "tek@klinik.com" }] }];
    }
    if (yontem === "POST" && yol === "/patients/p0/delete") return tekil;
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
}

const listeOkumalari = () => kayit.filter((k) => k.yontem === "GET" && k.yol === "/patients").length;
const tostlar = () => mockToast.mock.calls.map((c) => [String(c[0]), c[1]]);

describe("Y108 — olmayan hastanın silinmesi", () => {
  it("KRİTİK: sunucu 404 → 'zaten silinmiş' (bilgi) ve liste YENİDEN okunur", async () => {
    tekil = [404, { detail: "Hasta bulunamadı — zaten silinmiş olabilir; listeyi yenileyin." }];
    await kur();
    const once = listeOkumalari();
    await s.tikla("HastaT kaydını sil");
    await s.bosalt(10);
    expect(tostlar()).toContainEqual([ZATEN, "info"]);
    expect(listeOkumalari()).toBeGreaterThan(once);
  });

  it("KARŞIT: sunucu 500 → 'zaten silinmiş' DENMEZ, sunucunun gerekçesi hata olarak gösterilir", async () => {
    tekil = [500, { detail: "Hasta silinemedi — kayıt duruyor; birkaç saniye sonra yeniden deneyin." }];
    await kur();
    await s.tikla("HastaT kaydını sil");
    await s.bosalt(10);
    expect(tostlar().map(([m]) => m)).not.toContain(ZATEN);
    expect(tostlar()).toContainEqual(["Hasta silinemedi — kayıt duruyor; birkaç saniye sonra yeniden deneyin.", "error"]);
  });

  it("KARŞIT: başarılı silme 'Hasta silindi.'", async () => {
    tekil = [200, { status: "success" }];
    await kur();
    await s.tikla("HastaT kaydını sil");
    await s.bosalt(10);
    expect(tostlar()).toContainEqual(["Hasta silindi.", "success"]);
  });
});
