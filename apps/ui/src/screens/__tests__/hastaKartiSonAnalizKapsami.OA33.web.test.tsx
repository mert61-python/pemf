/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * O-A3.3 (2-B incelemesi) — Hastalar ekranı kartının "Son analiz" satırı KAPSAMA uyar (davranış kapısı).
 * ===========================================================================================================================
 * KÖR KAPI (ölçüldü, 2-B incelemesi o8): `PatientScreen`'in son analiz süzgecini `kapsamda(k, "all", …)` yapan mutant TÜM
 * kapılarda YEŞİL kalıyordu — yalnız yapısal pin (`kapsamda(` geçiyor mu) vardı. Süzgeç kalkarsa "Benim Hastalarım"daki kartın
 * altında BAŞKA hekimin analiz özeti, ev sahibinin kendi hayvanının kartında hekimin analiz özeti görünür.
 * Kayıtlar gerçek `/api/ai/log` kaydının biçimindedir (`__fixtures__/aiLog.D271.json` — gerçek backend'den üretilir ve
 * bayatlaması `tests/test_ai_log_UI_fiksturu_GERCEK_backend_D271.py` ile yakalanır).
 * GERÇEK: AuthProvider, UserModeProvider, OperatorProvider (Kural 2), AppNavProvider, PatientScreen, apiClient.
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
import { PatientScreen } from "@/screens/PatientScreen";
import { Sahne, sahteSunucu } from "../../context/__tests__/operatorAparati";

// eslint-disable-next-line @typescript-eslint/no-var-requires
const GERCEK_KAYIT = require("./__fixtures__/aiLog.D271.json").data[0];

const KIMLIK = "6f1c2a90-0b3e-4d55-9a71-3c0d5e8b4a11";
const kayit = (id: number, operator_email: string, result_summary: string, created_at: string) => ({
  ...GERCEK_KAYIT, id, operator_email, result_summary, created_at, patient_name: "Mia", patient_uuid: KIMLIK,
});

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

/** Mia (kaydı `sahip`'e ait) + iki analiz: sahibinki (ESKİ) ve başka birininki (YENİ). */
async function kur(mod: UserMode, oturum: string, sahip: string, baskasi: string) {
  mockOturum.eposta = oturum;
  const hastalar = [{ id: KIMLIK, name: "Mia", species: "Kedi", breed: "", age: 3, weight: 4, owner_name: "", owner_phone: "",
    operator_email: sahip, created_at: "2026-10-01 10:00:00" }];
  const analizler = [
    kayit(2, baskasi, "BASKASININ-ANALIZI", "2026-10-05 10:00:00"),
    kayit(1, sahip, "KENDI-ANALIZIM", "2026-10-01 10:00:00"),
  ];
  const sunucu = sahteSunucu([], (yol, _g, yontem) => {
    if (yontem === "GET" && yol === "/patients") return [200, { status: "success", data: hastalar }];
    if (yontem === "GET" && yol.startsWith("/ai/log")) return [200, { status: "success", data: analizler }];
    return undefined;
  });
  global.fetch = sunucu.fetchSahte as unknown as typeof fetch;
  await s.ciz(
    <AuthProvider>
      <UserModeProvider>
        <Mod mod={mod}>
          <OperatorProvider>
            <AppNavProvider navigateTo={() => undefined}>
              <PatientScreen />
            </AppNavProvider>
          </OperatorProvider>
        </Mod>
      </UserModeProvider>
    </AuthProvider>,
  );
  await s.bosalt(10);
}

const kartMetni = () => document.querySelector(`[data-testid="hasta-son-analiz-${KIMLIK}"]`)?.textContent || "";

it("KRİTİK O-A3.3 (hekim, 'Benim Hastalarım'): kendi hastasının kartında BAŞKA hekimin (daha yeni) analizi GÖRÜNMEZ", async () => {
  await kur("veterinarian", "dr.a@klinik.com", "dr.a@klinik.com", "dr.b@klinik.com");
  expect(kartMetni()).toContain("KENDI-ANALIZIM"); // ARA: kart çizildi, kendi analizi var
  expect(kartMetni()).not.toContain("BASKASININ-ANALIZI");
});

it("KRİTİK O-A3.3 (ev sahibi — kapsam HEP 'mine'): kendi hayvanının kartında hekimin analiz özeti GÖRÜNMEZ", async () => {
  await kur("pet_owner", "sahip@ev.com", "sahip@ev.com", "dr.b@klinik.com");
  expect(kartMetni()).toContain("KENDI-ANALIZIM");
  expect(kartMetni()).not.toContain("BASKASININ-ANALIZI");
});

it("KARŞIT O-A3.3: hekim 'Tüm Klinik'e geçince kart kliniğin EN YENİ analizini gösterir (A-01/A-28 açık model)", async () => {
  await kur("veterinarian", "dr.a@klinik.com", "dr.a@klinik.com", "dr.b@klinik.com");
  await s.tikla("Tüm klinik hastaları");
  expect(kartMetni()).toContain("BASKASININ-ANALIZI");
});
