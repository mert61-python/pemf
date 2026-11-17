/**
 * @jest-environment jsdom
 */
/**
 * KP-8 · src/screens/AiHistoryScreen.tsx kalan dallar (düzenek aiGecmisiOncekiDegerlendirmeler.Y122 ile AYNI — GERÇEK sağlayıcılar +
 * apiClient; sahte fetch / Supabase / toast / cihaz modülleri; PDF indirme sınırı `dosyaIndir` sahte):
 *  ALANLARI EKSİK eski kayıt ekranı ÇÖKERTMEZ ve eksik alan uydurulmaz:
 *  - modül adı / kimliği yoksa "AI"; özet ve hasta adı yoksa satırları YOK; tanınmayan kip / girdi tipi HAM değeriyle; sayısal ama
 *    geçersiz tarih ham metinden (ilk 16 karakter).
 *  - önceki değerlendirmede tanınmayan karar HAM, hekim yoksa "imzasız", zaman / not yoksa satırı yok.
 *  - hasta adı olmayan kaydın PDF'i "analiz" adıyla iner; önceki değerlendirmeler ucu gerekçesiz 503 dönerse "şu an okunamıyor".
 */
jest.mock("react-native", () => jest.requireActual("react-native-web"));
jest.mock("@/services/supabaseAuth", () => {
  const aparat = require("../../context/__tests__/operatorAparati");
  return {
    ...aparat.supabaseSahte(""),
    getCurrentSession: async () => ({ access_token: "x", user: { email: "tek@klinik.com", user_metadata: {} } }),
  };
});
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: jest.fn() }) }));
jest.mock("@/services/dosyaIndir", () => ({ downloadFileWithAuth: jest.fn(async () => undefined) }));
jest.mock("expo-sharing", () => ({ isAvailableAsync: jest.fn(async () => false), shareAsync: jest.fn() }));
jest.mock("expo-file-system/legacy", () => ({ documentDirectory: "file:///", writeAsStringAsync: jest.fn() }));
jest.mock("expo-haptics", () => ({ impactAsync: jest.fn(), notificationAsync: jest.fn(), selectionAsync: jest.fn(),
  ImpactFeedbackStyle: {}, NotificationFeedbackType: {} }));
jest.mock("expo-linear-gradient", () => {
  const R = require("react");
  const { View } = require("react-native-web");
  return { LinearGradient: ({ children, style }: { children?: unknown; style?: unknown }) => R.createElement(View, { style }, children) };
});

import React, { act, useEffect } from "react";
import { AuthProvider } from "@/context/AuthContext";
import { UserModeProvider, useUserMode } from "@/context/UserModeContext";
import { OperatorProvider } from "@/context/OperatorContext";
import { AppNavProvider } from "@/context/AppNavContext";
import { AiHistoryScreen } from "@/screens/AiHistoryScreen";
import i18n from "i18next";
import { downloadFileWithAuth } from "@/services/dosyaIndir";
import { Sahne, sahteSunucu } from "../../context/__tests__/operatorAparati";


function Mod({ children }: { children: React.ReactNode }) {
  const { setUserMode, userMode } = useUserMode();
  useEffect(() => { setUserMode("veterinarian"); }, [setUserMode]);
  return userMode ? <>{children}</> : null;
}

let s: Sahne;
let ayrintiCagrisi: number;
beforeEach(() => {
  s = new Sahne();
  ayrintiCagrisi = 0;
});
afterEach(async () => {
  await s.sok();
});

/** Ayrıntı ucunun yanıtı: [durum, gövde] · "ag" = bağlantı yok (`fetch` REDDEDİLİR — en alt kat) · işlev = çağrı sırasına göre. */
type Ayrinti = [number, unknown] | "ag";

async function kur(liste: unknown, ayrinti: Ayrinti | ((n: number) => Ayrinti)) {
  const sunucu = sahteSunucu([], (yol, _g, yontem) => {
    if (yontem === "GET" && /^\/ai\/log\/\d+/.test(yol)) {
      ayrintiCagrisi += 1;
      const y = typeof ayrinti === "function" ? ayrinti(ayrintiCagrisi) : ayrinti;
      if (y === "ag") throw new TypeError("Failed to fetch (sahte: cihaza bağlantı yok)");
      return y;
    }
    if (yontem === "GET" && yol.startsWith("/ai/log")) {
      return [200, yol.includes("before_id") ? { status: "success", data: [] } : liste];
    }
    return undefined;
  });
  global.fetch = sunucu.fetchSahte as unknown as typeof fetch;
  await s.ciz(
    <AuthProvider>
      <UserModeProvider>
        <Mod>
          <OperatorProvider>
            <AppNavProvider navigateTo={() => undefined}>
              <AiHistoryScreen />
            </AppNavProvider>
          </OperatorProvider>
        </Mod>
      </UserModeProvider>
    </AuthProvider>,
  );
  await s.bosalt(10);
}


const T = (k: string, o?: object): string => (i18n.t as unknown as (k: string, o?: object) => string)(k, o);
const ESKI = {
  id: 7, created_at: "99999999999999999999", mode: "garip-kip", module_id: "", module_label: "", patient_name: "", patient_uuid: "",
  operator_email: "", input_type: "garip-girdi", result_summary: "", result_detail: {}, confidence: null, review_status: "",
  review_note: "", reviewed_by: "", reviewed_at: "", review_history_count: 1,
};

test("alanları eksik eski kayıt: 'AI' adı, özet / hasta satırı yok, ham kip / girdi / tarih; önceki değerlendirme ham karar + imzasız; PDF 'analiz'", async () => {
  await kur({ status: "success", data: [ESKI] }, [200, { status: "success", data: { ...ESKI, review_history: [
    { status: "garip-karar", note: "", reviewed_by: "", reviewed_at: "" },
  ] } }]);
  const once = s.metin();
  expect(once).toContain("AI");
  expect(once).toContain("garip-kip");
  expect(once).toContain("9999999999999999");
  expect(once).not.toContain("· ");
  await s.tikla(T("ai.gecmis.kayitEtiketi", { ad: "AI", acik: "" }));
  await s.bosalt(10);
  const acik = s.metin();
  expect(acik).toContain(T("ai.gecmis.girdiTipi", { tip: "garip-girdi" }));
  expect(acik).toContain(`garip-karar · ${T("ai.gecmis.imzasiz")}`);
  await s.testIdTikla("ai-paylas-7");
  await s.bosalt(4);
  expect((downloadFileWithAuth as jest.Mock).mock.calls[0][1]).toBe("PEMF_AI_analiz_7.pdf");
});

test("önceki değerlendirmeler ucu GEREKÇESİZ 503 dönerse 'şu an okunamıyor' (gerekçe boş, 'undefined' yazmaz)", async () => {
  await kur({ status: "success", data: [ESKI] }, [503, {}]);
  await s.tikla(T("ai.gecmis.kayitEtiketi", { ad: "AI", acik: "" }));
  await s.bosalt(10);
  const m = s.metin();
  expect(m).toMatch(/okunamıyor/);
  expect(m).not.toContain("undefined");
});
