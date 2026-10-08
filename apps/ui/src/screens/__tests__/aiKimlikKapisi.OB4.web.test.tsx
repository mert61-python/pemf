/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * O-B.4 (2-B §6) — AI Geçmişi'nin TEK kimlik kapısı: değerlendirme, tekil silme ve toplu silme `deleteScope(...).izinli`
 * (`kimlikYok`) üzerinden geçer (yapısal pin: tests/test_kapsam_sahipligi.py::test_KRITIK_AI_gecmisi_KIMLIK_kapisi_TEK_kaynak_OB4).
 *
 * ⚠️ KATMAN: kayıtlı operatörlü klinikte kimse seçili değilken liste kart göstermez (Y103 — `kapsamda`); kart yoksa değerlendirme
 * düğmesine ulaşılamaz ve bu kapı ekrandan ÖLÇÜLEMEZ (D2.42 m5 "yalnız birleşik mutantta kırmızı" dersi). Bu dosya YALNIZ o
 * katmanı kaldırır (`kapsamda` → her kayıt) ve kapının KENDİSİNİ ölçer: kimliksiz değerlendirme / tekil silme / toplu silme
 * isteği GİTMEZ, üçü de aynı istemi gösterir. KARŞIT (Kural 2): operatörsüz klinikte istekler gider.
 *
 * GERÇEK: AuthProvider, UserModeProvider, OperatorProvider, OperatorSwitcher, AppNavProvider, AiHistoryScreen, AiReviewControls,
 * apiClient, `patientScope.deleteScope`. Sahte: `fetch`, Supabase, toast, `window.confirm`, cihaz modülleri ve (bilerek) `kapsamda`.
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
jest.mock("@/utils/sonAnaliz", () => ({ ...jest.requireActual("@/utils/sonAnaliz"), kapsamda: () => true }));
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
import { aktifOperator, Sahne, sahteSunucu, type Istek, type SahteOperator } from "../../context/__tests__/operatorAparati";

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

async function kur(oturum: string, operatorler: SahteOperator[]) {
  mockOturum.eposta = oturum;
  // İki kayıt: Kural 2 kolunda tekil silme birini götürür; "Geçmişi Sil" düğmesi (kayıt yokken gizli) görünür kalsın.
  const analizler = [0, 1].map((i) => ({
    id: 300 + i, created_at: "2026-10-01 10:00:00", mode: "veterinarian", module_id: `m${i}`, module_label: `Mod${i}`,
    patient_name: "Ortak", input_type: "image", result_summary: `Ozet${i}`, result_detail: {}, confidence: 0.9, operator_email: oturum,
  }));
  const sunucu = sahteSunucu(operatorler, (yol, _g, yontem) => {
    if (yontem === "GET" && yol.startsWith("/ai/log")) return [200, { status: "success", data: yol.includes("before_id") ? [] : analizler }];
    if (yontem === "POST" && yol.startsWith("/ai/log")) return [200, { status: "success", deleted: 1 }];
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

const aiIstekleri = () => kayit.filter((k) => k.yontem === "POST" && k.yol.startsWith("/ai/log"));

async function ucEylem() {
  await s.tikla("Mod0 kaydi");
  await s.tikla("AI sonucunu onayla");
  await s.bosalt(5);
  await s.tikla("Mod0 kaydını sil");
  await s.bosalt(5);
  await s.tikla("Kendi AI analiz geçmişimi sil");
  await s.bosalt(5);
}

it("KRİTİK: kimliksizken (kayıtlı operatörlü klinik, katman kaldırıldı) değerlendirme, tekil ve toplu silme isteği GİTMEZ; üçü AYNI istemi gösterir", async () => {
  await kur(A, IKI_HEKIM);
  expect(aktifOperator()).toBeNull(); // ARA DOĞRULAMA: kimse seçili değil
  expect(s.metin()).toContain("Ozet0"); // ARA DOĞRULAMA: katman kaldırıldı — kart görünüyor
  await ucEylem();
  expect(aiIstekleri()).toEqual([]);
  expect(onaylar.length).toBe(3);
  expect(onaylar.every((m) => m.startsWith("Operatör seçin"))).toBe(true);
  expect(onaylar.filter((m) => m.includes("Değerlendirme için")).length).toBe(1);
  expect(onaylar.filter((m) => m.includes("Silme işlemi için")).length).toBe(2);
});

it("KARŞIT (Kural 2): operatörsüz klinikte değerlendirme ve silmeler oturum kimliğiyle GİDER", async () => {
  await kur("tek@klinik.com", []);
  await ucEylem();
  const yollar = aiIstekleri().map((k) => k.yol).sort();
  expect(yollar).toEqual(["/ai/log/delete", "/ai/log/delete_all", "/ai/log/review"]);
});
