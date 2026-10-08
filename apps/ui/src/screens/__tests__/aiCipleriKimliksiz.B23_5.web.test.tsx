/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * B2-3.5 (2-B bağımsız incelemesi, A3) — KÖR KAPI: D2.70'in "AI Geçmişi hasta adı çipleri kimliksizken boş" iddiasının kapısı yok.
 * ========================================================================================================================
 * 2-B (`AiHistoryScreen.tsx:266-272`) kimliksizken hasta çiplerini boşaltır; ama D2.70 kapısı bütün analizlere ORTAK hasta adı
 * verdiği için çip satırını hiç ölçmüyor → `if (!myEmail) return [];` silinince kapı 62/62 YEŞİL kalıyor (ölçüldü). Çip satırı
 * kimliksizken kliniğin TÜM hasta ADLARINI (kişisel veri) listelerdi — Y103'ün "kayıt göstermez" kararının konusu.
 * GERÇEK: AuthProvider, UserModeProvider, OperatorProvider (gerçek hareketsizlik zamanlayıcısı), OperatorSwitcher (PIN),
 * AppNavProvider, AiHistoryScreen, apiClient. Sahte yalnız `fetch`, Supabase, toast, cihaz modülleri.
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
import { AUTO_LOCK_MS, OperatorProvider } from "@/context/OperatorContext";
import { AppNavProvider } from "@/context/AppNavContext";
import { OperatorSwitcher } from "@/components/domain/OperatorSwitcher";
import { AiHistoryScreen } from "@/screens/AiHistoryScreen";
import { aktifOperator, pinleSec, Sahne, sahteSunucu, type SahteOperator } from "../../context/__tests__/operatorAparati";

const A = "dr.a@klinik.com";
const B = "dr.b@klinik.com";
const IKI_HEKIM: SahteOperator[] = [{ email: A, display_name: "Dr. A" }, { email: B, display_name: "Dr. B" }];
const ADLAR = { A: "Pamuk", B: "Karabas", S: "Minnos" };

function Mod({ children }: { children: React.ReactNode }) {
  const { setUserMode, userMode } = useUserMode();
  useEffect(() => { setUserMode("veterinarian"); }, [setUserMode]);
  return userMode ? <>{children}</> : null;
}
let s: Sahne;
beforeEach(() => { jest.useFakeTimers(); s = new Sahne(); });
afterEach(async () => { await s.sok(); jest.useRealTimers(); });

async function kur(oturum: string, operatorler: SahteOperator[], sahipler: Record<string, string>) {
  mockOturum.eposta = oturum;
  const analizler = Object.entries(sahipler).map(([k, e], i) => ({
    id: 300 + i, created_at: "2026-10-01 10:00:00", mode: "veterinarian", module_id: "m", module_label: "Modul",
    patient_name: ADLAR[k as keyof typeof ADLAR], input_type: "image", result_summary: `Ozet${k}`, result_detail: {},
    confidence: 0.9, operator_email: e,
  }));
  const sunucu = sahteSunucu(operatorler, (yol, _g, yontem) =>
    yontem === "GET" && yol.startsWith("/ai/log")
      ? [200, { status: "success", data: yol.includes("before_id") ? [] : analizler }]
      : undefined);
  global.fetch = sunucu.fetchSahte as unknown as typeof fetch;
  await s.ciz(
    <AuthProvider><UserModeProvider><Mod><OperatorProvider><AppNavProvider navigateTo={() => undefined}>
      <OperatorSwitcher />
      <AiHistoryScreen />
    </AppNavProvider></OperatorProvider></Mod></UserModeProvider></AuthProvider>,
  );
  await s.ilerlet(50);
  await s.bosalt(10);
}
const gorunenAdlar = () => Object.values(ADLAR).filter((ad) => s.metin().includes(ad));

describe("B2-3.5 — kimliksizken AI Geçmişi hasta ADI çipleri de görünmez (Y103)", () => {
  it("KRİTİK: kayıtlı operatörlü cihazda kimse seçili değil → hiçbir hasta adı (çip dahil) görünmez", async () => {
    await kur(A, IKI_HEKIM, { A, B, S: "" });
    expect(aktifOperator()).toBeNull();
    expect(gorunenAdlar()).toEqual([]);
  });

  it("KRİTİK: hareketsizlik kilidinden SONRA hasta adı çipleri kalkar", async () => {
    await kur(A, IKI_HEKIM, { A, B, S: "" });
    await pinleSec(s, "Dr. A");
    await s.bosalt(10);
    expect(gorunenAdlar().length).toBeGreaterThan(0); // ARA DOĞRULAMA: kimlikliyken çip/kayıt var (araç kör değil)
    for (let t = 0; t < AUTO_LOCK_MS + 31_000; t += 30_000) await s.ilerlet(30_000);
    expect(aktifOperator()).toBeNull();
    expect(gorunenAdlar()).toEqual([]);
  });

  it("KARŞIT (Kural 2): operatörsüz tek hekimli klinikte çipler görünür", async () => {
    const T = "tek@klinik.com";
    await kur(T, [], { A: T, S: "" });
    expect(gorunenAdlar()).toEqual(expect.arrayContaining(["Pamuk", "Minnos"]));
  });
});
