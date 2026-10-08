/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * Y115 (S-B2.7 · 2-B incelemesi S-A3.2) — kayıtlı operatörlü (çok kullanıcılı) cihazda EV SAHİBİ profilinin "Benim" kapsamı
 * SAHİPSİZ hayvanları İÇERMEZ; operatörsüz cihazda bugünkü gibi.
 * ===========================================================================================================================
 * KUSUR: `inScope("mine")` = kendi VEYA sahipsiz — kayıtlı operatörlü klinikte ev sahibi, operatörler kurulmadan önce ortak
 * girişle yazılmış (sahipsiz) klinik hastalarını kendi hayvanı gibi seçebiliyor ve onlara AI analizi yazdırabiliyordu.
 * Hekimin "Benim"i sahipsizleri GÖRMEYE devam eder (Y104: kimlikli her hekim sahipsiz kaydı yönetir).
 * GERÇEK: AuthProvider, UserModeProvider, OperatorProvider, OperatorSwitcher (PIN akışı), AppNavProvider, PatientGate,
 * AiHubScreen, PatientScreen, AiHistoryScreen, apiClient. Sahte: fetch, Supabase, toast, `window.confirm`, cihaz modülleri.
 */
jest.mock("react-native", () => jest.requireActual("react-native-web"));
jest.mock("@/services/supabaseAuth", () => {
  const aparat = require("../../context/__tests__/operatorAparati");
  return aparat.supabaseSahte("sahip@ev.com");
});
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: jest.fn() }) }));
jest.mock("@/context/EntitlementContext", () => ({
  useEntitlement: () => ({ research: false, realtime: false }),
  EntitlementProvider: ({ children }: { children: unknown }) => children,
}));
// Abonelik penceresi (UpgradeModal) yerel safe-area modülünü ister (jest-expo YEREL çözer) — kapının konusu değil.
jest.mock("@/components/UpgradeModal", () => ({ UpgradeModal: () => null }));
jest.mock("expo-camera", () => ({ CameraView: () => null, useCameraPermissions: () => [{ granted: true }, jest.fn()] }));
jest.mock("expo-audio", () => ({
  useAudioRecorder: () => ({ record: jest.fn(), stop: jest.fn(), prepareToRecordAsync: jest.fn(), uri: null }),
  RecordingPresets: { HIGH_QUALITY: {} },
  setAudioModeAsync: jest.fn(),
  requestRecordingPermissionsAsync: jest.fn(async () => ({ granted: true })),
}));
jest.mock("expo-image-picker", () => ({ MediaTypeOptions: { Images: "Images" }, launchImageLibraryAsync: jest.fn(),
  launchCameraAsync: jest.fn() }));
jest.mock("expo-image-manipulator", () => ({ SaveFormat: { JPEG: "jpeg" }, manipulateAsync: jest.fn() }));
jest.mock("expo-document-picker", () => ({ getDocumentAsync: jest.fn() }));
jest.mock("expo-sharing", () => ({ isAvailableAsync: jest.fn(async () => false), shareAsync: jest.fn() }));
jest.mock("expo-file-system/legacy", () => ({ readAsStringAsync: jest.fn(), documentDirectory: "file:///", writeAsStringAsync: jest.fn() }));
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
import { OperatorSwitcher } from "@/components/domain/OperatorSwitcher";
import { PatientScreen } from "@/screens/PatientScreen";
import { AiHistoryScreen } from "@/screens/AiHistoryScreen";
import { cihazSahteleriniKur, cihazSahteleriniSok, kurAiHub } from "./aiHubAparati";
import { aktifOperator, pinleSec, Sahne, sahteSunucu } from "../../context/__tests__/operatorAparati";

// eslint-disable-next-line @typescript-eslint/no-var-requires
const GERCEK_KAYIT = require("./__fixtures__/aiLog.D271.json").data[0];

const S = "sahip@ev.com";
const A = "dr.a@klinik.com";
const KAYITLI = [{ email: A, display_name: "Dr. A" }, { email: S, display_name: "Ev Sahibi" }];
const HASTALAR = [
  { id: "u-mia", name: "Mia", operator_email: S, species: "Kedi" },
  { id: "u-pamuk", name: "Pamuk", operator_email: A, species: "Kedi" },
  { id: "u-boncuk", name: "Boncuk", operator_email: "", species: "Köpek" }, // sahipsiz (operatörler kurulmadan önce)
];
const ANALIZLER = [
  { ...GERCEK_KAYIT, id: 3, patient_name: "Boncuk", patient_uuid: "u-boncuk", operator_email: "", result_summary: "SAHIPSIZ-ANALIZ" },
  { ...GERCEK_KAYIT, id: 2, patient_name: "Mia", patient_uuid: "u-mia", operator_email: S, result_summary: "KENDI-ANALIZ" },
];

let s: Sahne;
let onay: jest.SpyInstance;
beforeEach(() => {
  s = new Sahne();
  cihazSahteleriniKur();
  onay = jest.spyOn(window, "confirm").mockImplementation(() => true);
});
afterEach(async () => {
  await s.sok();
  cihazSahteleriniSok();
  onay.mockRestore();
});

/** PatientGate seçicisini açıp listelenen hayvan adlarını döndürür. */
async function seciciListesi(): Promise<string[]> {
  const kapi = Array.from(document.querySelectorAll('[role="button"]')).find((e) =>
    /^(Hasta seçin|Hayvanınızı seçin|Örnek seçin)$/.test(e.getAttribute("aria-label") || "")) as HTMLElement;
  await s.tikla(kapi.getAttribute("aria-label")!);
  for (let i = 0; i < 20 && !document.querySelector('[aria-label^="Seç: "]'); i++) await s.bosalt();
  // ⚠️ Operatör penceresinin satırları da "Seç: <ad>" etiketlidir (OperatorSwitcher) — onlar hasta değil, çıkarılır.
  return Array.from(document.querySelectorAll('[aria-label^="Seç: "]')).map((e) => (e.getAttribute("aria-label") || "").slice(5))
    .filter((ad) => !KAYITLI.some((o) => o.display_name === ad));
}

it("KRİTİK Y115 (seçici): kayıtlı operatörlü cihazda ev sahibi SAHİPSİZ hayvanı seçemez (analiz yazamaz)", async () => {
  await kurAiHub(s, { mod: "pet_owner", hastalar: HASTALAR, operatorler: KAYITLI, operatorCipi: true });
  await pinleSec(s, "Ev Sahibi");
  expect(aktifOperator()).toBe("Ev Sahibi"); // ARA: kimlik kuruldu
  expect(await seciciListesi()).toEqual(["Mia"]);
});

it("KARŞIT Y115 (Kural 2): operatörsüz cihazda ev sahibi sahipsiz hayvanı GÖRMEYE devam eder (bugünkü gibi)", async () => {
  await kurAiHub(s, { mod: "pet_owner", hastalar: HASTALAR });
  expect((await seciciListesi()).sort()).toEqual(["Boncuk", "Mia"]);
});

it("KARŞIT Y115 (hekim — Y104): kayıtlı operatörlü cihazda hekimin seçicisi sahipsiz hastayı GÖSTERİR", async () => {
  await kurAiHub(s, { mod: "veterinarian", hastalar: HASTALAR, operatorler: KAYITLI, operatorCipi: true });
  await pinleSec(s, "Dr. A");
  expect(await seciciListesi()).toContain("Boncuk");
});

function Mod({ mod, children }: { mod: UserMode; children: React.ReactNode }) {
  const { setUserMode, userMode } = useUserMode();
  useEffect(() => { setUserMode(mod); }, [mod, setUserMode]);
  return userMode ? <>{children}</> : null;
}

async function evSahibiEkrani(ekran: React.ReactNode, operatorler: typeof KAYITLI | []) {
  const sunucu = sahteSunucu(operatorler, (yol, _g, yontem) => {
    if (yontem === "GET" && yol === "/patients") return [200, { status: "success", data: HASTALAR }];
    if (yontem === "GET" && yol.startsWith("/ai/log")) return [200, { status: "success", data: yol.includes("before_id") ? [] : ANALIZLER }];
    return undefined;
  });
  global.fetch = sunucu.fetchSahte as unknown as typeof fetch;
  await s.ciz(
    <AuthProvider>
      <UserModeProvider>
        <Mod mod="pet_owner">
          <OperatorProvider>
            <AppNavProvider navigateTo={() => undefined}>
              <OperatorSwitcher />
              {ekran}
            </AppNavProvider>
          </OperatorProvider>
        </Mod>
      </UserModeProvider>
    </AuthProvider>,
  );
  if (operatorler.length) await pinleSec(s, "Ev Sahibi");
  await s.bosalt(10);
}

it("KRİTİK Y115 (Hastalar ekranı): kayıtlı operatörlü cihazda ev sahibinin listesinde sahipsiz hayvan YOK", async () => {
  await evSahibiEkrani(<PatientScreen />, KAYITLI);
  expect(s.metin()).toContain("Mia"); // ARA: kendi hayvanı listede
  expect(s.metin()).not.toContain("Boncuk");
});

it("KRİTİK Y115 (AI Geçmişi): kayıtlı operatörlü cihazda ev sahibi sahipsiz hayvanın analizini GÖRMEZ", async () => {
  await evSahibiEkrani(<AiHistoryScreen />, KAYITLI);
  expect(s.metin()).toContain("KENDI-ANALIZ");
  expect(s.metin()).not.toContain("SAHIPSIZ-ANALIZ");
});

it("KARŞIT Y115 (Kural 2, AI Geçmişi): operatörsüz cihazda ev sahibi sahipsiz analizleri görmeye devam eder", async () => {
  await evSahibiEkrani(<AiHistoryScreen />, []);
  expect(s.metin()).toContain("KENDI-ANALIZ");
  expect(s.metin()).toContain("SAHIPSIZ-ANALIZ");
});
