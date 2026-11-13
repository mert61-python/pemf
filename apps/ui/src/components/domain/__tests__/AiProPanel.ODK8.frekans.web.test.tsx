/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * ODK8 (sahip 13 Kasım 2026: "ai pro kısmına frekans seçme de koy 76 100 107 147") — AI Pro panelinde FREKANS SEÇİCİ.
 * Varsayılan 100 Hz; seçilen frekans öneri isteğine (`frek_hz`) gider (backend mühüre yazar, `/start` karta o frekansı gönderir —
 * backend kapısı `tests/test_ODK8_AI_Pro_FREKANS_secimi_76_100_107_147.py`); onay penceresi mühürdeki frekansı gösterir.
 * GERÇEK: AuthProvider, UserModeProvider, OperatorProvider, AppNavProvider, PatientGate, AiProPanel, AiSpecApprovalModal + OdakOzeti,
 * apiClient. Sahte: fetch (öneri yanıtı gövdedeki frekansı mühüre yazar), Supabase, toast, canlı veri, kamera, `window.confirm`
 * (aparat: `AiProPanel.E15.hastaMuhru.web.test.tsx` ile aynı).
 */
jest.mock("react-native", () => jest.requireActual("react-native-web"));
jest.mock("@/services/supabaseAuth", () => {
  const aparat = require("../../../context/__tests__/operatorAparati");
  return aparat.supabaseSahte("dr.a@klinik.com");
});
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: jest.fn() }) }));
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: null, wsConnected: true, aiVisionData: null, aiVisionFresh: false }),
}));
jest.mock("expo-camera", () => {
  const R = require("react");
  return { CameraView: R.forwardRef((_p: unknown, _r: unknown) => null), useCameraPermissions: () => [{ granted: true }, jest.fn()] };
});
// Onay penceresinin güvenli alan kancası (çentik/inset — görsel; kapının konusu değil). Kurulum dosyasının sahtesi YEREL
// modülü yükler (jest-expo yerel çözer → "reading 'get'"); dosya düzeyi sahte onu ezer.
jest.mock("react-native-safe-area-context", () => {
  const R = require("react");
  const { View } = require("react-native-web");
  return {
    useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
    SafeAreaProvider: ({ children }: { children?: unknown }) => children,
    SafeAreaView: ({ children, style }: { children?: unknown; style?: unknown }) => R.createElement(View, { style }, children),
  };
});
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
import { PatientGate } from "@/components/domain/PatientGate";
import { AiProPanel } from "@/components/domain/AiProPanel";
import { Sahne, sahteSunucu, type Istek } from "../../../context/__tests__/operatorAparati";

const HASTALAR = [
  { id: "u-mia", name: "Mia", operator_email: "dr.a@klinik.com", species: "Kedi" },
  { id: "u-pamuk", name: "Pamuk", operator_email: "dr.a@klinik.com", species: "Kedi" },
];

function Mod({ mod, children }: { mod: UserMode; children: React.ReactNode }) {
  const { setUserMode, userMode } = useUserMode();
  useEffect(() => { setUserMode(mod); }, [mod, setUserMode]);
  return userMode ? <>{children}</> : null;
}

let s: Sahne;
let kayit: Istek[];
let onay: jest.SpyInstance;
const durum = { localized: false };
beforeEach(() => {
  jest.useFakeTimers();
  s = new Sahne();
  durum.localized = false;
  onay = jest.spyOn(window, "confirm").mockImplementation(() => true);
});
afterEach(async () => {
  await s.sok();
  onay.mockRestore();
  jest.useRealTimers();
});

async function kur(yumusak: boolean) {
  const sunucu = sahteSunucu([], (yol, govde, yontem) => {
    if (yontem === "GET" && yol === "/patients") return [200, { status: "success", data: HASTALAR }];
    if (yontem === "GET" && yol.startsWith("/ai/pro/status")) return [200, { active: false, localized: durum.localized }];
    if (yontem === "POST" && yol === "/ai/pro/propose") {
      const g = (govde || {}) as Record<string, unknown>;
      return [200, {
        status: "success", proposalId: "p1", expiresAt: 0, meta: {},
        specs: { organ_id: 2, duration_minutes: 20, coil_ids: [1, 2, 3, 4, 5, 6, 7], D: [0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3],
          P: [0, 0, 0, 0, 0, 0, 0], e_field: 0.07, model: "kedi",
          patient_id: String(g.patient_id || ""), patient_name: String(g.patient_name || ""),
          odak: { kip: "KEDI_ORGAN", doz_mT: 0.3, beklenen_mT: 0.3, tavan_mT: 0.6, cevre_mT: 0.2, oran: 1.5, pay_yuzde: 8,
            frek_hz: Number(g.frek_hz ?? 100) } },
      }];
    }
    return undefined;
  });
  kayit = sunucu.kayit;
  global.fetch = sunucu.fetchSahte as unknown as typeof fetch;
  await s.ciz(
    <AuthProvider>
      <UserModeProvider>
        <Mod mod="veterinarian">
          <OperatorProvider>
            <AppNavProvider navigateTo={() => undefined}>
              <PatientGate soft={yumusak}>
                <AiProPanel patientName="" secilebilirModeller={["kedi"]} kullaniciKipi="veterinarian" />
              </PatientGate>
            </AppNavProvider>
          </OperatorProvider>
        </Mod>
      </UserModeProvider>
    </AuthProvider>,
  );
}

/** Başlat → önizleme lokalize eder (status `localized`) → öneri OTOMATİK istenir (web akışı). */
async function oneriyiAl() {
  await s.tikla("AI Pro otonom seansı başlat");
  durum.localized = true;
  for (let i = 0; i < 4; i++) await s.ilerlet(3000);
}

const oneriGovdeleri = () => kayit.filter((i) => i.yontem === "POST" && i.yol === "/ai/pro/propose").map((i) => i.govde as Record<string, unknown>);
const metinVar = (m: string) => Array.from(document.querySelectorAll("*")).some((e) => (e.textContent || "").trim() === m);

it("KRİTİK ODK8: frekans SEÇİLMEDEN öneri 100 Hz taşır; onay penceresi 'Frekans: 100 Hz' der", async () => {
  await kur(true);
  await oneriyiAl();
  const g = oneriGovdeleri();
  expect(g.length).toBeGreaterThan(0);
  expect(g[0].frek_hz).toBe(100);
  expect(metinVar("Frekans: 100 Hz (öneri bu frekansın modeli ve kalibrasyonuyla)")).toBe(true);
});

it("KRİTİK ODK8: 147 Hz seçilince öneri isteği frek_hz 147 taşır ve onay penceresi mühürdeki 147 Hz'i gösterir", async () => {
  await kur(true);
  for (const f of [76, 100, 107, 147]) expect(s.varMi(`${f} Hz`)).toBe(true);
  await s.tikla("147 Hz");
  await oneriyiAl();
  const g = oneriGovdeleri();
  expect(g.length).toBeGreaterThan(0);
  expect(g[g.length - 1].frek_hz).toBe(147);
  expect(metinVar("Frekans: 147 Hz (öneri bu frekansın modeli ve kalibrasyonuyla)")).toBe(true);
});
