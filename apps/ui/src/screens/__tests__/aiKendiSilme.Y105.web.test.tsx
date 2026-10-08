/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * Y105 (S-B.2) — operatörsüz (tek kullanıcılı) cihazda "kendi AI geçmişimi sil" SAHİPSİZ eski kayıtları da siler (backend:
 * tests/test_ai_gecmisi_KENDI_silme_OPERATORSUZ_cihazda_sahipsizi_de_siler_Y105.py). Onay penceresi bunu söylemeli — "Kendi AI
 * analiz kayıtlarınızın TAMAMI" deyip sahipsiz eski kayıtları da silmek operatörü yanıltır. Kayıtlı operatörlü klinikte A-10 aynen
 * (metin değişmez).
 *
 * GERÇEK: AuthProvider, UserModeProvider (ev sahibi / veteriner), OperatorProvider, OperatorSwitcher (PIN), AppNavProvider,
 * AiHistoryScreen, apiClient. Sahte yalnız `fetch` (kaydedici), Supabase istemcisi, toast, `window.confirm` ve cihaz modülleri.
 */
jest.mock("react-native", () => jest.requireActual("react-native-web"));
const mockOturum = { eposta: "sahip@ev.com" };
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
import { UserModeProvider, useUserMode, type UserMode } from "@/context/UserModeContext";
import { OperatorProvider } from "@/context/OperatorContext";
import { AppNavProvider } from "@/context/AppNavContext";
import { OperatorSwitcher } from "@/components/domain/OperatorSwitcher";
import { AiHistoryScreen } from "@/screens/AiHistoryScreen";
import { pinleSec, Sahne, sahteSunucu, type Istek, type SahteOperator } from "../../context/__tests__/operatorAparati";

function Mod({ mod, children }: { mod: UserMode; children: React.ReactNode }) {
  const { setUserMode, userMode } = useUserMode();
  useEffect(() => { setUserMode(mod); }, [mod, setUserMode]);
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

async function kur(mod: UserMode, oturum: string, operatorler: SahteOperator[]) {
  mockOturum.eposta = oturum;
  const analizler = [oturum, ""].map((e, i) => ({
    id: 300 + i, created_at: "2026-10-01 10:00:00", mode: mod, module_id: `m${i}`, module_label: `Mod${i}`,
    patient_name: "Ortak", input_type: "image", result_summary: `Ozet${i}`, result_detail: {}, confidence: 0.9, operator_email: e,
  }));
  const sunucu = sahteSunucu(operatorler, (yol, _g, yontem) => {
    if (yontem === "GET" && yol.startsWith("/ai/log")) return [200, { status: "success", data: yol.includes("before_id") ? [] : analizler }];
    if (yontem === "POST" && yol === "/ai/log/delete_all") return [200, { status: "success", deleted: 2 }];
    return undefined;
  });
  kayit = sunucu.kayit;
  global.fetch = sunucu.fetchSahte as unknown as typeof fetch;
  await s.ciz(
    <AuthProvider>
      <UserModeProvider>
        <Mod mod={mod}>
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
}

const silmeler = () => kayit.filter((k) => k.yontem === "POST" && k.yol === "/ai/log/delete_all");

describe("Y105 — operatörsüz cihazda 'kendi geçmişimi sil' sahipsiz eski kayıtları da siler", () => {
  it.each(["pet_owner", "veterinarian"] as UserMode[])(
    "KRİTİK (%s, operatörsüz cihaz): onay 'kendi ve sahipsiz (eski)' der; istek oturum kimliğiyle gider",
    async (mod) => {
      await kur(mod, "sahip@ev.com", []);
      await s.tikla("Kendi AI analiz geçmişimi sil");
      await s.bosalt(10);
      expect(onaylar.length).toBe(1);
      expect(onaylar[0]).toContain("Kendi ve sahipsiz (eski) AI analiz kayıtlarınızın TAMAMI");
      const t = silmeler();
      expect(t.length).toBe(1);
      expect(t[0].govde).toMatchObject({ confirm: "DELETE_ALL", operator_email: "sahip@ev.com", all_operators: false });
    },
  );

  it("KARŞIT (A-10, kayıtlı operatörlü klinik): onay yalnız 'Kendi AI analiz kayıtlarınızın TAMAMI' der (sahipsiz DEMEZ)", async () => {
    const A = "dr.a@klinik.com";
    await kur("veterinarian", A, [{ email: A, display_name: "Dr. A" }, { email: "dr.b@klinik.com", display_name: "Dr. B" }]);
    await pinleSec(s, "Dr. A");
    await s.bosalt(10);
    await s.tikla("Kendi AI analiz geçmişimi sil");
    await s.bosalt(10);
    expect(onaylar.length).toBe(1);
    expect(onaylar[0]).toContain("Kendi AI analiz kayıtlarınızın TAMAMI");
    expect(onaylar[0]).not.toContain("sahipsiz");
  });
});
