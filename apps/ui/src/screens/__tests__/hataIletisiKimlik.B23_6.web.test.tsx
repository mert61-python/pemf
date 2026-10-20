/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * B2-3.6 (2-B bağımsız incelemesi, A3) — B2B-2 taslağı düşürür ama D2.E12 "gerekçeniz korunuyor" iletisi YENİ KİMLİĞE taşınır.
 * =======================================================================================================================
 * ÖLÇÜLEN: Dr. A'nın reddi sunucuda düşer (500) → form "Değerlendirme kaydedilemedi — gerekçeniz korunuyor. Tekrar deneyin."
 * der. Dr. B'ye geçilince B2B-2 taslağı (A'nın gerekçesi) doğru biçimde siler, ama ileti `AiReviewControls`'ün YEREL `hata`
 * durumunda kaldığı için B'nin ekranında "gerekçeniz korunuyor" yazmaya devam eder — korunan bir gerekçe yok (yanıltıcı).
 * Aynısı istek UÇUŞTAYKEN geçişte de olur (A'nın gerekçesi düşer, ileti B'de görünür).
 * KARŞIT: aynı hekimde 500 sonrası ileti ve gerekçe birlikte durur (D2.E12).
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
import { kaydedilemediMetni } from "@/components/domain/AiReviewControls";
import { aktifOperator, pinleSec, Sahne, sahteSunucu, type SahteOperator } from "../../context/__tests__/operatorAparati";

const A = "dr.a@klinik.com";
const B = "dr.b@klinik.com";
const IKI: SahteOperator[] = [{ email: A, display_name: "Dr. A" }, { email: B, display_name: "Dr. B" }];
const GEREKCE = "Klinik bulgularla uyusmuyor (B2-3.6)";
const sunucu = { review: 200, gecikmeMs: 0 };

function Mod({ children }: { children: React.ReactNode }) {
  const { setUserMode, userMode } = useUserMode();
  useEffect(() => { setUserMode("veterinarian"); }, [setUserMode]);
  return userMode ? <>{children}</> : null;
}
let s: Sahne;
beforeEach(() => { jest.useFakeTimers(); s = new Sahne(); sunucu.review = 200; sunucu.gecikmeMs = 0; });
afterEach(async () => { await s.sok(); jest.useRealTimers(); });

async function kur() {
  mockOturum.eposta = A;
  const analiz = { id: 7, created_at: "2026-10-01 10:00:00", mode: "veterinarian", module_id: "m", module_label: "Kedi FGS",
    patient_name: "Pamuk", input_type: "image", result_summary: "Ozet", result_detail: {}, confidence: 0.9,
    operator_email: "", review_status: "" };
  const ss = sahteSunucu(IKI, (yol, _g, yontem) => {
    if (yontem === "GET" && yol.startsWith("/ai/log")) return [200, { status: "success", data: yol.includes("before_id") ? [] : [analiz] }];
    if (yontem === "POST" && yol === "/ai/log/review") {
      return sunucu.review === 200 ? [200, { status: "success" }] : [sunucu.review, { detail: "taklit" }];
    }
    return undefined;
  });
  global.fetch = (async (url: unknown, init?: { method?: string }) => {
    const yol = String(url).replace(/^[a-z]+:\/\/[^/]+/i, "").replace(/^\/api/, "");
    if (yol === "/ai/log/review" && sunucu.gecikmeMs) await new Promise((r) => setTimeout(r, sunucu.gecikmeMs));
    return ss.fetchSahte(url, init as never);
  }) as unknown as typeof fetch;
  await s.ciz(
    <AuthProvider><UserModeProvider><Mod><OperatorProvider><AppNavProvider navigateTo={() => undefined}>
      <OperatorSwitcher />
      <AiHistoryScreen />
    </AppNavProvider></OperatorProvider></Mod></UserModeProvider></AuthProvider>,
  );
  await s.ilerlet(50);
  await s.bosalt(10);
  await pinleSec(s, "Dr. A");
  await s.bosalt(10);
  await s.tikla(document.querySelector('[aria-label^="Kedi FGS kaydi"]')!.getAttribute("aria-label")!);
  await s.tikla("AI sonucunu reddet");
  await s.yaz("Red gerekçesi", GEREKCE);
}
const alan = () => (document.querySelector('[aria-label="Red gerekçesi"]') as HTMLTextAreaElement | null)?.value ?? null;

describe("B2-3.6 — kimlik değişince 'gerekçeniz korunuyor' iletisi de düşer", () => {
  it("KRİTİK: A'nın reddi 500 → B'ye geçiş → B'nin ekranında 'gerekçeniz korunuyor' YOK", async () => {
    await kur();
    sunucu.review = 500;
    await s.tikla("Reddi kaydet");
    await s.bosalt(10);
    expect(s.metin()).toContain(kaydedilemediMetni()); // ARA DOĞRULAMA: A için ileti + gerekçe duruyor
    expect(alan()).toBe(GEREKCE);
    await pinleSec(s, "Dr. B");
    await s.bosalt(10);
    expect(aktifOperator()).toBe("Dr. B");
    expect(s.metin()).not.toContain(GEREKCE); // B2B-2 (2-B): taslak taşınmaz
    expect(s.metin()).not.toContain(kaydedilemediMetni());
  });

  it("KRİTİK: istek UÇUŞTAYKEN B'ye geçiş, sunucu 500 → B'de 'gerekçeniz korunuyor' YOK", async () => {
    await kur();
    sunucu.review = 500;
    sunucu.gecikmeMs = 2000;
    await s.tikla("Reddi kaydet");
    await pinleSec(s, "Dr. B");
    await s.bosalt(5);
    await s.ilerlet(2500);
    await s.bosalt(10);
    expect(aktifOperator()).toBe("Dr. B");
    expect(s.metin()).not.toContain(kaydedilemediMetni());
  });

  it("KARŞIT (D2.E12): aynı hekimde 500 sonrası ileti ve gerekçe birlikte durur", async () => {
    await kur();
    sunucu.review = 500;
    await s.tikla("Reddi kaydet");
    await s.bosalt(10);
    expect(alan()).toBe(GEREKCE);
    expect(s.metin()).toContain(kaydedilemediMetni());
  });
});
