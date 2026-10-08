/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * D2.E11 (İG-6.59) · SAHİP KARARI A-62 — `sonAnaliz`'in AD YEDEĞİ, kimliği olan hastada KALKAR: aynı adlı ikinci hayvan birincinin
 * analizini görmez.
 * ===========================================================================================================================
 * ÖLÇÜLEN KUSUR (ADAY İG-6.59, gerçek backend + Chrome): Mia/Kedi (A, analizi "A-ANALIZI"), Mia/Köpek (B, analizi YOK), Miami (C):
 * Hastalar ekranında B'nin kartı "Son analiz: … A-ANALIZI", Akıllı Teşhis'te B seçiliyken "Mia · son analiz … A-ANALIZI".
 * Kök: `hastayaGoreSonAnaliz` kimlikli kaydı ad anahtarına da yazıyor, `hastaAnahtarlari` kimlik bulunamayınca ada düşüyordu.
 * A-62'nin bilinen bedeli: kimliksiz ESKİ kayıtlar kimlikli hastanın kart/şeridinde görünmez (AI Geçmişi'nde kalır).
 * GİRDİ: `__fixtures__/sonAnaliz.E11.json` — GERÇEK backend yanıtları (`tests/test_son_analiz_UI_fiksturu_GERCEK_backend_E11.py`).
 * GERÇEK: AuthProvider, UserModeProvider, OperatorProvider (Kural 2), AppNavProvider, PatientScreen, PatientGate, AiHubScreen,
 * apiClient. Sahte: fetch, Supabase, toast, `window.confirm`, cihaz modülleri, abonelik gösterimi.
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
import { PatientScreen } from "@/screens/PatientScreen";
import { hastaninSonAnalizi, hastayaGoreSonAnaliz } from "@/utils/sonAnaliz";
import { cihazSahteleriniKur, cihazSahteleriniSok, hastaSec, kurAiHub } from "./aiHubAparati";
import { Sahne, sahteSunucu } from "../../context/__tests__/operatorAparati";

// eslint-disable-next-line @typescript-eslint/no-var-requires
const GERCEK: Record<string, unknown> = require("./__fixtures__/sonAnaliz.E11.json");
const gercekYanit = (yol: string, _g: unknown, yontem: string): [number, unknown] | undefined =>
  (yontem === "GET" && yol in GERCEK ? [200, GERCEK[yol]] : undefined);

// ── (a) SAF BİRİM ───────────────────────────────────────────────────────────────────────────────────────────────────────────
it("KRİTİK E11/A-62 (birim): kimliği olan B, aynı adlı A'nın kimlikli kaydını AD üzerinden BULAMAZ", () => {
  const harita = hastayaGoreSonAnaliz([{ id: 1, patient_uuid: "A", patient_name: "Mia", result_summary: "R1" }]);
  expect(hastaninSonAnalizi(harita, { id: "B", name: "Mia" })).toBeUndefined();
  expect(hastaninSonAnalizi(harita, { id: "A", name: "Mia" })?.result_summary).toBe("R1"); // KARŞIT: kendi kaydı
});

it("KRİTİK E11/A-62 (birim, bilinen bedel): kimlikli B aynı adlı KİMLİKSİZ eski kaydı da ad yedeğiyle GÖRMEZ", () => {
  const harita = hastayaGoreSonAnaliz([{ id: 1, patient_uuid: "", patient_name: "Mia", result_summary: "ESKI" }]);
  expect(hastaninSonAnalizi(harita, { id: "B", name: "Mia" })).toBeUndefined();
});

it("KARŞIT E11/A-62 (birim): kimliği OLMAYAN hasta kimliksiz eski kaydı adla bulmaya DEVAM eder; kimlikli kaydı bulmaz", () => {
  const harita = hastayaGoreSonAnaliz([
    { id: 1, patient_uuid: "", patient_name: "Mia", result_summary: "ESKI" },
    { id: 2, patient_uuid: "A", patient_name: "Mia", result_summary: "A-KAYDI", created_at: "2099-01-01" },
  ]);
  expect(hastaninSonAnalizi(harita, { name: "Mia" })?.result_summary).toBe("ESKI");
});

// ── (b) EKRAN: Hastalar kartı ─────────────────────────────────────────────────────────────────────────────────────────────
function Mod({ mod, children }: { mod: UserMode; children: React.ReactNode }) {
  const { setUserMode, userMode } = useUserMode();
  useEffect(() => { setUserMode(mod); }, [mod, setUserMode]);
  return userMode ? <>{children}</> : null;
}

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

const kart = (kimlik: string) => document.querySelector(`[data-testid="hasta-son-analiz-${kimlik}"]`);

it("KRİTİK E11/A-62 (Hastalar ekranı): B'nin kartında A'nın analizi YOK; A ve Miami (C) kendi analizlerini gösterir", async () => {
  const sunucu = sahteSunucu([], gercekYanit);
  global.fetch = sunucu.fetchSahte as unknown as typeof fetch;
  await s.ciz(
    <AuthProvider>
      <UserModeProvider>
        <Mod mod="veterinarian">
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
  expect(kart("kimlik-A")?.textContent).toContain("A-ANALIZI"); // ARA + KARŞIT: kendi kaydı görünür
  expect(kart("kimlik-C")?.textContent).toContain("C-ANALIZI");
  expect(kart("kimlik-B")).toBeNull();
});

// ── (c) EKRAN: Akıllı Teşhis "kaldığın yerden" şeridi (ev sahibi) ─────────────────────────────────────────────────────────
it("KRİTİK E11/A-62 (Akıllı Teşhis şeridi): Mia/Köpek (B) seçiliyken Mia/Kedi'nin (A) analizi şeritte GÖRÜNMEZ", async () => {
  await kurAiHub(s, { mod: "pet_owner", hastalar: [], ozel: gercekYanit });
  await hastaSec(s, "Mia", "Köpek");
  expect(s.metin()).toContain("Evcil Hayvanım:Mia"); // ARA: B seçildi
  await s.bosalt(10);
  expect(document.querySelector('[data-testid="pet-son-analiz"]')).toBeNull();
});

it("KARŞIT E11/A-62 (Akıllı Teşhis şeridi): Mia/Kedi (A) seçiliyken KENDİ analizi şeritte görünür", async () => {
  await kurAiHub(s, { mod: "pet_owner", hastalar: [], ozel: gercekYanit });
  await hastaSec(s, "Mia", "Kedi");
  await s.bosalt(10);
  expect(document.querySelector('[data-testid="pet-son-analiz"]')?.textContent).toContain("A-ANALIZI");
});
