/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * D2.71 (B-6.18 · B-6.20 · O-B.2) — AI Geçmişi hasta çipleri KAPSAM İÇİ listeden ve hasta KİMLİĞİYLE kurulur.
 * ===========================================================================================================================
 * KUSUR: çipler ham listeden (`items`) ve ADLA kuruluyordu → (B-6.18 / O-B.2, KVKK) ev sahibi başka hekimin hastasının ADINI
 * çipte görüyordu; (B-6.20) aynı adlı iki hayvan tek "Mia" çipinde birleşiyor, süzme ve takip eğrisi iki hayvanın kayıtlarını
 * karıştırıyordu.
 * GİRDİ: `__fixtures__/aiLog.D271.json` — GERÇEK backend'in `/api/ai/log` yanıtı (`tests/test_ai_log_UI_fiksturu_GERCEK_backend_
 * D271.py` üretir ve bayatlamayı yakalar): ev sahibinin aynı adlı iki "Mia"sı (kimlik …4a11 ×2, …9d22 ×1) + kimliksiz ESKİ "Mia"
 * kaydı + başka hekimin "Pamuk"u.
 * GERÇEK: AuthProvider, UserModeProvider, OperatorProvider (kayıtlı operatörsüz cihaz — Kural 2), AppNavProvider,
 * AiHistoryScreen, apiClient. Sahte: fetch, Supabase, toast, `window.confirm`, cihaz modülleri.
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
jest.mock("expo-haptics", () => ({ impactAsync: jest.fn(), notificationAsync: jest.fn(), selectionAsync: jest.fn(),
  ImpactFeedbackStyle: {}, NotificationFeedbackType: {} }));
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
import { AiHistoryScreen } from "@/screens/AiHistoryScreen";
import { Sahne, sahteSunucu } from "../../context/__tests__/operatorAparati";

// eslint-disable-next-line @typescript-eslint/no-var-requires
const GERCEK_YANIT = require("./__fixtures__/aiLog.D271.json");

function Mod({ mod, children }: { mod: UserMode; children: React.ReactNode }) {
  const { setUserMode, userMode } = useUserMode();
  useEffect(() => { setUserMode(mod); }, [mod, setUserMode]);
  return userMode ? <>{children}</> : null;
}

let s: Sahne;
let onay: jest.SpyInstance;
beforeEach(() => {
  s = new Sahne();
  onay = jest.spyOn(window, "confirm").mockImplementation(() => true);
});
afterEach(async () => {
  await s.sok();
  onay.mockRestore();
});

async function kur(mod: UserMode, oturum: string) {
  mockOturum.eposta = oturum;
  const sunucu = sahteSunucu([], (yol, _g, yontem) => {
    if (yontem === "GET" && yol.startsWith("/ai/log")) {
      return [200, yol.includes("before_id") ? { status: "success", data: [] } : GERCEK_YANIT];
    }
    return undefined;
  });
  global.fetch = sunucu.fetchSahte as unknown as typeof fetch;
  await s.ciz(
    <AuthProvider>
      <UserModeProvider>
        <Mod mod={mod}>
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

/** Hasta çiplerinin etiketleri: "Filtre: Tüm hastalar" ile modül satırının "Filtre: Tümü" çipi ARASINDAKİ çipler (ortak Chip
 *  erişilebilirlik etiketi "Filtre: <etiket>"). */
function hastaCipleri(): string[] {
  const etiketler = Array.from(document.querySelectorAll('[role="button"]')).map((e) => e.getAttribute("aria-label") || "");
  const bas = etiketler.indexOf("Filtre: Tüm hastalar");
  if (bas < 0) return [];
  const son = etiketler.indexOf("Filtre: Tümü", bas);
  return etiketler.slice(bas + 1, son < 0 ? undefined : son).map((a) => a.replace(/^Filtre: /, ""));
}

it("KRİTİK D2.71 (B-6.18 · O-B.2): ev sahibi başka hekimin hastasının ADINI çipte GÖRMEZ", async () => {
  await kur("pet_owner", "sahip@ev.com");
  expect(s.metin()).toContain("FGS 2/10"); // ARA: gerçek yanıt yüklendi, kendi kayıtları görünüyor
  expect(hastaCipleri().length).toBeGreaterThan(0);
  expect(hastaCipleri().some((c) => c.includes("Pamuk"))).toBe(false);
  expect(s.metin()).not.toContain("Pamuk");
});

it("KRİTİK D2.71 (B-6.20): aynı adlı iki hayvan AYRI çip; biri seçilince yalnız ONUN kayıtları (kimlikle süzülür)", async () => {
  await kur("pet_owner", "sahip@ev.com");
  const mia = hastaCipleri().filter((c) => c.startsWith("Mia"));
  expect(new Set(mia).size).toBe(3); // iki kimlik + kimliksiz eski kayıt — üçü ayrı ve ayırt edilebilir
  const m1 = mia.find((c) => c.includes("4a11"));
  expect(m1).toBeDefined();
  await s.tikla(`Filtre: ${m1!}`);
  expect(s.metin()).toContain("2 kayıt (filtreli)");
  expect(s.metin()).toContain("FGS 2/10");
  expect(s.metin()).toContain("FGS 4/10");
  expect(s.metin()).not.toContain("FGS 1/10"); // aynı adlı ÖTEKİ hayvan
  expect(s.metin()).not.toContain("FGS 3/10 (eski)"); // kimliksiz eski kayıt ayrı çipte
});

it("KRİTİK D2.71 (kapsam, hekim): \"Benim\" kapsamında hekim YALNIZ kendi hastasının çipini görür", async () => {
  await kur("veterinarian", "dr.b@klinik.com");
  expect(hastaCipleri()).toEqual(["Pamuk"]);
  await s.tikla("Filtre: Pamuk");
  expect(s.metin()).toContain("1 kayıt (filtreli)");
});

it("KARŞIT D2.71: hekim \"Tüm Klinik\"e geçince kliniğin TÜM hastaları çipte (A-01/A-28 açık model) — aynı adlılar ayrı", async () => {
  await kur("veterinarian", "dr.b@klinik.com");
  await s.tikla("Tüm klinik analizleri");
  const cipler = hastaCipleri();
  expect(cipler).toContain("Pamuk");
  expect(cipler.filter((c) => c.startsWith("Mia"))).toHaveLength(3);
  await s.tikla("Filtre: Pamuk");
  await s.tikla("Benim analizlerim");
  expect(hastaCipleri()).toEqual(["Pamuk"]); // seçili çip kapsamda kalıyor → süzgeç korunur
  expect(s.metin()).toContain("1 kayıt (filtreli)");
});
