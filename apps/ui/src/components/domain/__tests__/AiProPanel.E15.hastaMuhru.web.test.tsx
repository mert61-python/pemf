/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * D2.E15 (İG-5.14) arayüz yarısı — AI Pro ÖNERİSİ seçili hastanın kimliğini ve adını taşır; onay penceresi mühürdeki hastayı
 * gösterir.
 * ===========================================================================================================================
 * KUSUR: AiProPanel hastayı yalnız `/ai/pro/start` gövdesinde (`patient_name`) gönderiyordu; backend alanı tanımadığı için ATIYOR,
 * AI Pro seansı hastaya bağlanmıyordu. Düzeltme hastayı MÜHRE koyar (`/propose` gövdesi → `specs.patient_*`; `/start` mühürden
 * okur — backend kapısı `tests/test_ai_pro_seans_HASTAYA_baglanir_ve_KAPANIR_E15_E07.py`).
 * GERÇEK: AuthProvider, UserModeProvider (veterinarian), OperatorProvider (Kural 2), AppNavProvider, PatientGate, AiProPanel,
 * AiSpecApprovalModal, apiClient. Sahte: fetch (öneri yanıtı backend'in mühür davranışını yansıtır: gövdedeki hasta
 * `specs`e yazılır), Supabase, toast, canlı veri akışı (`useLiveData` — WS), kamera modülü, `window.confirm`.
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
          patient_id: String(g.patient_id || ""), patient_name: String(g.patient_name || "") },
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

async function hastaSec(ad: string) {
  await s.tikla("Hasta seçin");
  for (let i = 0; i < 20 && !s.varMi(`Seç: ${ad}`); i++) await s.bosalt();
  await s.tikla(`Seç: ${ad}`);
}

/** Başlat → önizleme lokalize eder (status `localized`) → öneri OTOMATİK istenir (web akışı). */
async function oneriyiAl() {
  await s.tikla("AI Pro otonom seansı başlat");
  durum.localized = true;
  for (let i = 0; i < 4; i++) await s.ilerlet(3000);
}

const oneriGovdeleri = () => kayit.filter((i) => i.yontem === "POST" && i.yol === "/ai/pro/propose").map((i) => i.govde as Record<string, unknown>);
const metaSatiri = (etiket: string, deger: string) =>
  Array.from(document.querySelectorAll("*")).some((e) => (e.textContent || "").trim() === `${etiket}${deger}`);

it("KRİTİK E15: öneri isteği seçili hastanın KİMLİĞİNİ ve ADINI taşır; onay penceresi mühürdeki hastayı gösterir", async () => {
  await kur(false);
  await hastaSec("Mia");
  await oneriyiAl();
  const g = oneriGovdeleri();
  expect(g.length).toBeGreaterThan(0); // ARA: gerçek akış öneriyi istedi
  expect([g[0].patient_id, g[0].patient_name]).toEqual(["u-mia", "Mia"]);
  expect(metaSatiri("Hasta", "Mia")).toBe(true);
});

it("KARŞIT E15: hasta seçilmeden (bilinçli onayla) başlatılan öneri BOŞ hasta taşır; pencere 'seçilmedi' der", async () => {
  await kur(true);
  await oneriyiAl();
  expect(onay).toHaveBeenCalled(); // ARA: "Hasta seçilmedi" onayı soruldu (bugünkü kapı)
  const g = oneriGovdeleri();
  expect(g.length).toBeGreaterThan(0);
  expect([g[0].patient_id, g[0].patient_name]).toEqual(["", ""]);
  expect(metaSatiri("Hasta", "— seçilmedi (sahipsiz kaydedilir)")).toBe(true);
});
