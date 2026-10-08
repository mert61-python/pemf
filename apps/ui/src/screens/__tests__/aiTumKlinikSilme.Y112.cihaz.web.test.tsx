/**
 * @jest-environment jsdom
 * @jest-environment-options {"url": "http://127.0.0.1:8000/"}
 */
// Author: mertaygn, cglrgrkn
/**
 * Y112 KARŞIT — CİHAZIN KENDİ ekranında (loopback: launcher'ın açtığı 127.0.0.1:8000) kimlikli hekimin "Tüm Klinik" AI silmesi
 * kliniğin TAMAMINI siler; onay penceresi bunu söyler. Cihaz dışı kol: aiTumKlinikSilme.Y112.lan.web.test.tsx.
 *
 * GERÇEK: AuthProvider, UserModeProvider, OperatorProvider, OperatorSwitcher (PIN), AppNavProvider, AiHistoryScreen, apiClient.
 * Sahte yalnız `fetch` (kaydedici), Supabase istemcisi, toast, `window.confirm` ve cihaz modülleri.
 */
jest.mock("react-native", () => jest.requireActual("react-native-web"));
const mockOturum = { eposta: "dr.a@klinik.com" };
jest.mock("@/services/supabaseAuth", () => {
  const aparat = require("../../context/__tests__/operatorAparati");
  return {
    ...aparat.supabaseSahte(""),
    getCurrentSession: async () => ({ access_token: "x", user: { email: mockOturum.eposta, user_metadata: {} } }),
  };
});
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: jest.fn() }) }));
jest.mock("expo-sharing", () => ({ isAvailableAsync: jest.fn(async () => false), shareAsync: jest.fn() }));
jest.mock("expo-file-system/legacy", () => ({ documentDirectory: "file:///", writeAsStringAsync: jest.fn() }));
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
import { OperatorSwitcher } from "@/components/domain/OperatorSwitcher";
import { AiHistoryScreen } from "@/screens/AiHistoryScreen";
import { pinleSec, Sahne, sahteSunucu, type Istek, type SahteOperator } from "../../context/__tests__/operatorAparati";

const A = "dr.a@klinik.com";
const IKI_HEKIM: SahteOperator[] = [{ email: A, display_name: "Dr. A" }, { email: "dr.b@klinik.com", display_name: "Dr. B" }];

function Mod({ children }: { children: React.ReactNode }) {
  const { setUserMode, userMode } = useUserMode();
  useEffect(() => { setUserMode("veterinarian"); }, [setUserMode]);
  return userMode ? <>{children}</> : null;
}

let s: Sahne;
let kayit: Istek[];
let onaylar: string[];
beforeEach(() => {
  jest.useFakeTimers();
  s = new Sahne();
  onaylar = [];
  jest.spyOn(window, "confirm").mockImplementation((m?: string) => { onaylar.push(String(m)); return true; });
});
afterEach(async () => {
  await s.sok();
  (window.confirm as jest.Mock).mockRestore?.();
  jest.useRealTimers();
});

it("ARAÇ KANITI: sayfa cihazın kendisinden (loopback) açık", () => {
  expect(window.location.hostname).toBe("127.0.0.1");
});

it("KARŞIT (Y112): cihaz ekranında kimlikli hekim 'Tüm Klinik' → onay 'Kliniğin TÜM AI analiz geçmişi' der, istek jetonla gider", async () => {
  mockOturum.eposta = A;
  const analizler = [A, "dr.b@klinik.com", ""].map((e, i) => ({
    id: 300 + i, created_at: "2026-10-01 10:00:00", mode: "veterinarian", module_id: `m${i}`, module_label: `Mod${i}`,
    patient_name: "Ortak", input_type: "image", result_summary: `Ozet${i}`, result_detail: {}, confidence: 0.9, operator_email: e,
  }));
  const sunucu = sahteSunucu(IKI_HEKIM, (yol, _g, yontem) => {
    if (yontem === "GET" && yol.startsWith("/ai/log")) return [200, { status: "success", data: yol.includes("before_id") ? [] : analizler }];
    if (yontem === "POST" && yol === "/ai/log/delete_all") return [200, { status: "success", deleted: 3 }];
    return undefined;
  });
  kayit = sunucu.kayit;
  global.fetch = sunucu.fetchSahte as unknown as typeof fetch;
  await s.ciz(
    <AuthProvider>
      <UserModeProvider>
        <Mod>
          <OperatorProvider>
            <AppNavProvider navigateTo={() => undefined}>
              <OperatorSwitcher />
              <AiHistoryScreen />
            </AppNavProvider>
          </OperatorProvider>
        </Mod>
      </UserModeProvider>
    </AuthProvider>,
  );
  await s.ilerlet(50);
  await s.bosalt(10);
  await pinleSec(s, "Dr. A");
  await s.bosalt(10);
  await s.tikla("Tüm klinik analizleri");
  await s.tikla("Kliniğin tüm AI analiz geçmişini sil");
  await s.bosalt(10);
  expect(onaylar.length).toBe(1);
  expect(onaylar[0]).toContain("Kliniğin TÜM AI analiz geçmişi");
  const t = kayit.filter((k) => k.yontem === "POST" && k.yol === "/ai/log/delete_all");
  expect(t.length).toBe(1);
  expect(t[0].govde).toMatchObject({ confirm: "DELETE_ALL", all_operators: true });
  expect(t[0].operator).toBe(`JETON-${A}`);
});
