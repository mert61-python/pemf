/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * D2.20 · B-3.38 · A-10 · Y83 — AI Geçmişi'nde tekil "Kaydı sil" kimlikle ve YALNIZ kendi kaydına.
 * ==============================================================================================
 * ÖLÇÜLEN KUSUR: "Tüm Klinik" görünümünde tekil silme `operator_email: ""` gönderiyordu (backend bunu "sahip filtresi yok"
 * sayıp HER kaydı siliyordu); "Benim" görünümünde sahipsiz kayıtlar da silinebiliyordu. Backend kapsamı artık jetondan alır
 * (tests/test_ai_gecmisi_SILME_KAPSAMI_jetondan_D220.py); arayüz de: tekil silme kimliği HER kapsamda gönderir, başka
 * hekimin ve SAHİPSİZ kaydı için istek göndermez (Y83 — sahipsizler yalnız "Tüm Klinik" toplu silmesinden gider).
 *
 * GERÇEK: AuthProvider, UserModeProvider, OperatorProvider, OperatorSwitcher (PIN), AppNavProvider, AiHistoryScreen,
 * apiClient. Sahte yalnız `fetch` (kaydedici), Supabase istemcisi, toast, `window.confirm` ve cihaz modülleri.
 * Kural 2: operatörsüz tek hekimli klinikte kimlik oturum e-postasıdır.
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
const B = "dr.b@klinik.com";
const IKI_HEKIM: SahteOperator[] = [{ email: A, display_name: "Dr. A" }, { email: B, display_name: "Dr. B" }];

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

async function kur(oturum: string, operatorler: SahteOperator[], sahipler: Record<string, string>) {
  mockOturum.eposta = oturum;
  const analizler = Object.entries(sahipler).map(([ad, e], i) => ({
    id: 300 + i, created_at: "2026-10-01 10:00:00", mode: "veterinarian", module_id: `m${ad}`, module_label: `Mod${ad}`,
    patient_name: "Ortak", input_type: "image", result_summary: `Ozet${ad}`, result_detail: {}, confidence: 0.9,
    operator_email: e,
  }));
  const sunucu = sahteSunucu(operatorler, (yol, _g, yontem) => {
    if (yontem === "GET" && yol.startsWith("/ai/log")) {
      return [200, { status: "success", data: yol.includes("before_id") ? [] : analizler }];
    }
    if (yontem === "POST" && yol === "/ai/log/delete") return [200, { status: "success", deleted: 1 }];
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
}

async function kaydiSil(ad: string) {
  await s.tikla(`Mod${ad} kaydi`);
  await s.tikla(`Mod${ad} kaydını sil`);
  await s.bosalt(10);
}
const silmeler = () => kayit.filter((k) => k.yontem === "POST" && k.yol === "/ai/log/delete");

describe("D2.20 · A-10 · Y83 — AI Geçmişi tekil silme", () => {
  it("KRİTİK: 'Tüm Klinik'te kendi kaydını silerken istek KİMLİKLE gider (boş e-posta 'herkesinki' demekti)", async () => {
    await kur(A, IKI_HEKIM, { A, B, S: "" });
    await pinleSec(s, "Dr. A");
    await s.bosalt(10);
    await s.tikla("Tüm klinik analizleri");
    await kaydiSil("A");
    const t = silmeler();
    expect(t.length).toBe(1);
    expect((t[0].govde as { operator_email?: string }).operator_email).toBe(A);
    expect(t[0].operator).toBe(`JETON-${A}`);
  });

  it("KRİTİK (Y83): SAHİPSİZ kaydın tekil silinmesi istek GÖNDERMEZ ('Benim' görünümünde görünür ama silinmez)", async () => {
    await kur(A, IKI_HEKIM, { A, B, S: "" });
    await pinleSec(s, "Dr. A");
    await s.bosalt(10);
    await kaydiSil("S");
    expect(silmeler()).toEqual([]);
    expect(onaylar.join("\n")).toContain("Yalnız kendi kayıtlarınızı silebilirsiniz");
  });

  it("KRİTİK: 'Tüm Klinik'te başka hekimin kaydı için istek GÖNDERİLMEZ", async () => {
    await kur(A, IKI_HEKIM, { A, B, S: "" });
    await pinleSec(s, "Dr. A");
    await s.bosalt(10);
    await s.tikla("Tüm klinik analizleri");
    await kaydiSil("B");
    expect(silmeler()).toEqual([]);
  });

  it("KARŞIT (Kural 2): operatörsüz tek hekimli klinikte kendi kaydı oturum kimliğiyle silinir", async () => {
    const T = "tek@klinik.com";
    await kur(T, [], { T, S: "" });
    await kaydiSil("T");
    const t = silmeler();
    expect(t.length).toBe(1);
    expect((t[0].govde as { operator_email?: string }).operator_email).toBe(T);
  });
});
