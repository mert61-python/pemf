/**
 * @jest-environment jsdom
 */
/**
 * KP-8 · PatientScreen + AiHistoryScreen — operatör bağlamı (OperatorProvider) YOKKEN kimlik (KP3-PatientScreen-kollari düzeneği;
 * GERÇEK AuthProvider / UserModeProvider / AppNavProvider + ekranlar; sahte: Supabase oturumu, fetch, toast):
 *  - Kimlik OTURUMUN e-postasından gelir: "Benim" kapsamı oturum sahibinin kayıtlarını sayar (kayıtlı operatör listesi yok sayılır).
 *  - Oturum YOKSA kimlik boştur: liste GÖSTERİLMEZ, "operatörünüzü seçin" istemi çıkar; silme isteği gitmez.
 *  - AI Geçmişi de sağlayıcısız çizilir ve oturum sahibinin analizlerini "benim" kapsamında gösterir.
 */
jest.mock("react-native", () => jest.requireActual("react-native-web"));
const mockOturum: { eposta: string | null } = { eposta: "tek@klinik.com" };
jest.mock("@/services/supabaseAuth", () => {
  const aparat = require("../../context/__tests__/operatorAparati");
  return {
    ...aparat.supabaseSahte(""),
    getCurrentSession: async () =>
      mockOturum.eposta ? { access_token: "x", user: { email: mockOturum.eposta, user_metadata: {} } } : null,
  };
});
const mockToast = jest.fn();
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: mockToast }) }));
jest.mock("expo-haptics", () => ({ impactAsync: jest.fn(), notificationAsync: jest.fn(), selectionAsync: jest.fn(),
  ImpactFeedbackStyle: {}, NotificationFeedbackType: {} }));
jest.mock("expo-sharing", () => ({ isAvailableAsync: jest.fn(async () => false), shareAsync: jest.fn() }));
jest.mock("expo-file-system/legacy", () => ({ documentDirectory: "file:///", writeAsStringAsync: jest.fn() }));
jest.mock("expo-linear-gradient", () => {
  const R = require("react");
  const { View } = require("react-native-web");
  return { LinearGradient: ({ children, style }: { children?: unknown; style?: unknown }) => R.createElement(View, { style }, children) };
});

import React, { useEffect } from "react";
import i18n from "i18next";
import { AuthProvider } from "@/context/AuthContext";
import { UserModeProvider, useUserMode } from "@/context/UserModeContext";
import { AppNavProvider } from "@/context/AppNavContext";
import { PatientScreen } from "@/screens/PatientScreen";
import { AiHistoryScreen } from "@/screens/AiHistoryScreen";
import { profilSozlugu } from "@/utils/profilSozlugu";
import { Sahne, sahteSunucu, type Istek } from "../../context/__tests__/operatorAparati";

const T = (k: string, o?: object): string => (i18n.t as unknown as (k: string, o?: object) => string)(k, o);
const SK = () => profilSozlugu({ petOwner: false, researcher: false });

function Veteriner({ children }: { children: React.ReactNode }) {
  const { setUserMode, userMode } = useUserMode();
  useEffect(() => { setUserMode("veterinarian"); }, [setUserMode]);
  return userMode ? <>{children}</> : null;
}

let s: Sahne;
let kayit: Istek[];
const HASTALAR = [
  { id: "p1", name: "Boncuk", species: "Kedi", operator_email: "tek@klinik.com" },
  { id: "p2", name: "Karabaş", species: "Köpek", operator_email: "baska@klinik.com" },
];
const ANALIZLER = [
  { id: 11, created_at: "2026-11-01 10:00", mode: "veterinarian", module_id: "m-benim", module_label: "Benim modülüm", patient_name: "Boncuk",
    operator_email: "tek@klinik.com", input_type: "image", result_summary: "", result_detail: {}, confidence: null, review_status: "" },
  { id: 12, created_at: "2026-11-01 11:00", mode: "veterinarian", module_id: "m-baska", module_label: "Başka modül", patient_name: "Karabaş",
    operator_email: "baska@klinik.com", input_type: "image", result_summary: "", result_detail: {}, confidence: null, review_status: "" },
];

beforeEach(() => {
  jest.useFakeTimers();
  s = new Sahne();
  mockToast.mockClear();
  mockOturum.eposta = "tek@klinik.com";
  silmeYaniti = undefined;
  jest.spyOn(window, "confirm").mockImplementation(() => true);
});
afterEach(async () => {
  await s.sok();
  jest.restoreAllMocks();
  jest.useRealTimers();
});

let silmeYaniti: [number, unknown] | undefined;
async function ciz(ekran: React.ReactNode) {
  const sunucu = sahteSunucu([], (yol: string, _g: unknown, yontem: string) => {
    if (yontem === "POST" && yol.endsWith("/delete") && silmeYaniti) return silmeYaniti;
    if (yontem === "GET" && yol === "/patients") return [200, { status: "success", data: HASTALAR }];
    if (yontem === "GET" && yol.startsWith("/ai/log")) return [200, yol.includes("before_id") ? { status: "success", data: [] } : { status: "success", data: ANALIZLER }];
    return undefined;
  });
  kayit = sunucu.kayit;
  global.fetch = sunucu.fetchSahte as unknown as typeof fetch;
  await s.ciz(
    <AuthProvider>
      <UserModeProvider>
        <Veteriner>
          <AppNavProvider navigateTo={() => undefined}>{ekran}</AppNavProvider>
        </Veteriner>
      </UserModeProvider>
    </AuthProvider>,
  );
  await s.ilerlet(50);
  await s.bosalt(10);
}

it("hasta: sağlayıcısız kimlik OTURUMDAN — 'Benim (1)' oturum sahibinin kaydı", async () => {
  await ciz(<PatientScreen />);
  expect(s.metin()).toContain(`${SK().benimListe} (1)`);
});

it("hasta: tekil silme sunucu gerekçesiz reddederse genel 'silinemedi' iletisi", async () => {
  silmeYaniti = [500, {}];
  await ciz(<PatientScreen />);
  await s.tikla(T("hasta.liste.silEtiketi", { name: "Boncuk" }));
  await s.bosalt(8);
  expect(kayit.filter((k) => k.yontem === "POST" && k.yol === "/patients/p1/delete")).toHaveLength(1);
  expect(mockToast).toHaveBeenCalledWith(T("hasta.sil.silinemedi"), "error");
});

it("hasta: oturum YOKSA liste GÖSTERİLMEZ, kimlik istemi; silme / okuma isteği kimliksiz gitmez", async () => {
  mockOturum.eposta = null;
  await ciz(<PatientScreen />);
  const m = s.metin();
  expect(m).toContain(T("hasta.kimlik.istem"));
  expect(m).not.toContain("Boncuk");
  expect(kayit.filter((k) => k.yontem === "POST" && k.yol.includes("/delete"))).toHaveLength(0);
});

it("AI geçmişi: sağlayıcısız çizilir; 'benim' kapsamında oturum sahibinin analizi var, başkasınınki yok", async () => {
  await ciz(<AiHistoryScreen />);
  const m = s.metin();
  // kart satırları ("· hasta"): yalnız oturum sahibinin analizi (filtre çipleri tüm modülleri listeler)
  expect(m).toContain("· Boncuk");
  expect(m).not.toContain("· Karabaş");
  // başka hekimin modül çipi seçilirse "bu filtrede kayıt yok" (genel "kayıt yok" DEĞİL)
  await s.metneTikla("Başka modül");
  await s.bosalt(4);
  expect(s.metin()).toContain(T("ai.gecmis.filtreKayitYok"));
});

it("AI geçmişi: liste alanı dizi değilse boş liste ('kayıt yok'), çökmez", async () => {
  const sunucu = sahteSunucu([], (yol: string, _g: unknown, yontem: string) =>
    yontem === "GET" && yol.startsWith("/ai/log") ? [200, { status: "success", data: { bozuk: true } }] : undefined);
  global.fetch = sunucu.fetchSahte as unknown as typeof fetch;
  await s.ciz(
    <AuthProvider>
      <UserModeProvider>
        <Veteriner>
          <AppNavProvider navigateTo={() => undefined}><AiHistoryScreen /></AppNavProvider>
        </Veteriner>
      </UserModeProvider>
    </AuthProvider>,
  );
  await s.ilerlet(50);
  await s.bosalt(10);
  expect(s.metin()).toContain(T("ai.gecmis.kayitYok"));
});

it("hasta: adı / türü olmayan kayıt düzenlenince alanlar BOŞ yüklenir", async () => {
  HASTALAR.push({ id: "p9", species: "", operator_email: "tek@klinik.com" } as never);
  try {
    await ciz(<PatientScreen />);
    await s.tikla(T("hasta.liste.duzenleEtiketi", { name: undefined }));
    expect((s.etiket(T("hasta.form.adEtiketi")) as HTMLInputElement).value).toBe("");
    expect((s.etiket(T("hasta.form.turEtiketi")) as HTMLInputElement).value).toBe("");
  } finally {
    HASTALAR.pop();
  }
});
