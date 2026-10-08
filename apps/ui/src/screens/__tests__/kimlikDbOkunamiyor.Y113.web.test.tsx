/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * Y113 (S-B2.5 · 2-B incelemesi) — CİHAZIN KİMLİK VERİTABANI OKUNAMAZKEN arayüz "operatörünüzü seçin" DEMEZ; arızayı ve
 * çareyi söyler. Kapılar KAPALI kalır (B2-3.1: liste bilinmiyorken kimlik yok — istek gitmez).
 * ===========================================================================================================================
 * ÖLÇÜLEN KUSUR: arka uç auth DB'yi okuyamayınca `/api/operators` 503 döner (`be3e6ee`); arayüz bunu "liste bilinmiyor" sayıp
 * (B2-3.1) üç listede "Kayıtları görmek için operatörünüzü seçin", eklemede "Hasta eklemek için operatörünüzü seçin",
 * değerlendirmede "Operatör seçin" diyordu, çip "Operatör seçin" gösteriyordu ve pencere "Bu cihazda kayıtlı operatör yok"
 * diyordu — operatör listesi OKUNAMIYORKEN operatör seçmek imkânsız; operatör yanlış eyleme yönlendiriliyordu.
 * SAHİP KARARI Y113: ileti, günlük ve arayüz "Cihazın kimlik veritabanı okunamıyor — …" der ve çareyi söyler.
 *
 * GERÇEK: AuthProvider, UserModeProvider, OperatorProvider, OperatorSwitcher, AppNavProvider, PatientScreen,
 * TreatmentHistoryScreen, AiHistoryScreen, AiReviewControls, apiClient. Sahte yalnız `fetch` (kaydedici; `/operators` yanıtı
 * ayarlanabilir), Supabase istemcisi, toast, `window.confirm` ve cihaz modülleri. Beklenen metin bu dosyada SABİT yazılır
 * (mutasyon hedefi `utils/patientScope`'tan okunmaz); arka ucun 503 gövdesi de sabit (arka uç metninin başı).
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
const mockToast = jest.fn();
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: mockToast }) }));
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
import { View } from "react-native";
import { AuthProvider } from "@/context/AuthContext";
import { UserModeProvider, useUserMode, type UserMode } from "@/context/UserModeContext";
import { OperatorProvider } from "@/context/OperatorContext";
import { AppNavProvider } from "@/context/AppNavContext";
import { OperatorSwitcher } from "@/components/domain/OperatorSwitcher";
import { PatientScreen } from "@/screens/PatientScreen";
import { TreatmentHistoryScreen } from "@/screens/TreatmentHistoryScreen";
import { AiHistoryScreen } from "@/screens/AiHistoryScreen";
import { Sahne, sahteSunucu, type Istek, type SahteOperator } from "../../context/__tests__/operatorAparati";

const A = "dr.a@klinik.com";
const B = "dr.b@klinik.com";
const TARIH = "2026-10-01 10:00:00";
const IKI_HEKIM: SahteOperator[] = [{ email: A, display_name: "Dr. A" }, { email: B, display_name: "Dr. B" }];
// Arka ucun (servers.auth.KIMLIK_DB_OKUNAMIYOR) 503 gövdesi — yalnız baş kısmı bu sözleşmenin parçası.
const ARKA_UC_ARIZA = "Cihazın kimlik veritabanı okunamıyor — kayıtların hangi hekime ait olduğu doğrulanamıyor; (arka uç).";
const ARIZA = "Cihazın kimlik veritabanı okunamıyor —";
const CARE = "uygulamayı kapatıp yeniden açın";
const LISTE_ISTEMI = "Kayıtları görmek için operatörünüzü seçin";
const EKLEME_ISTEMI = "Hasta eklemek için operatörünüzü seçin";

function veri(sahipler: Record<string, string>) {
  const hastalar = Object.entries(sahipler).map(([ad, e], i) => ({
    id: `p${i}`, name: `Hasta${ad}`, species: "Kedi", breed: "", age: 3, weight: 4, owner_name: "", owner_phone: "",
    operator_email: e, created_at: TARIH,
  }));
  const seanslar = Object.entries(sahipler).map(([ad, e], i) => ({
    id: 100 + i, patient_name: `Seans${ad}`, session_date: TARIH, start_time: TARIH, end_time: TARIH,
    duration_minutes: 5, treatment_mode: "Manuel", status: "completed", operator_email: e,
  }));
  const analizler = Object.entries(sahipler).map(([ad, e], i) => ({
    id: 200 + i, created_at: TARIH, timestamp: TARIH, mode: "veterinarian", module_id: "m", module_label: `Modul${ad}`,
    patient_name: "Ortak", input_type: "image", result_summary: `Ozet${ad}`, result_detail: {}, confidence: 0.9,
    operator_email: e, review_status: "",
  }));
  return { hastalar, seanslar, analizler };
}

function Mod({ mod, children }: { mod: UserMode; children: React.ReactNode }) {
  const { setUserMode, userMode } = useUserMode();
  useEffect(() => { setUserMode(mod); }, [mod, setUserMode]);
  return userMode ? <>{children}</> : null;
}

type OpDurum = "ariza" | "hazir_degil" | 200;
const ag = { operatorler: 200 as OpDurum };

let s: Sahne;
let kayit: Istek[];
let onay: jest.SpyInstance;
beforeEach(() => {
  jest.useFakeTimers();
  s = new Sahne();
  ag.operatorler = 200;
  onay = jest.spyOn(window, "confirm").mockImplementation(() => true);
});
afterEach(async () => {
  await s.sok();
  onay.mockRestore();
  jest.useRealTimers();
});

async function kur(oturum: string, operatorler: SahteOperator[], sahipler: Record<string, string>,
                   ekranlar: Array<"hasta" | "seans" | "ai"> = ["hasta", "seans", "ai"]) {
  mockOturum.eposta = oturum;
  mockToast.mockClear();
  const { hastalar, seanslar, analizler } = veri(sahipler);
  const sunucu = sahteSunucu(operatorler, (yol, _g, yontem) => {
    if (yontem === "GET" && yol === "/operators" && ag.operatorler === "ariza") return [503, { detail: ARKA_UC_ARIZA }];
    if (yontem === "GET" && yol === "/operators" && ag.operatorler === "hazir_degil") return [503, { detail: "hazir degil (taklit)" }];
    if (yontem === "GET" && yol === "/patients") return [200, { status: "success", data: hastalar }];
    if (yontem === "GET" && yol.startsWith("/history/")) return [200, yol.includes("cursor=") ? [] : seanslar];
    if (yontem === "GET" && yol.startsWith("/ai/log")) {
      return [200, { status: "success", data: yol.includes("before_id") ? [] : analizler }];
    }
    if (yontem === "POST" && yol === "/ai/log/review") return [200, { status: "success" }];
    if (yontem === "POST" && /delete/.test(yol)) return [200, { status: "success", silinen: 1 }];
    if (yontem === "POST" && yol === "/patients") return [200, { status: "success" }];
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
              <OperatorSwitcher />
              {ekranlar.includes("hasta") ? <View><PatientScreen /></View> : null}
              {ekranlar.includes("seans") ? <View><TreatmentHistoryScreen /></View> : null}
              {ekranlar.includes("ai") ? <View><AiHistoryScreen /></View> : null}
            </AppNavProvider>
          </OperatorProvider>
        </Mod>
      </UserModeProvider>
    </AuthProvider>,
  );
  await s.ilerlet(50);
  await s.bosalt(10);
}

const say = (metin: string) => s.metin().split(metin).length - 1;
const istekler = (yontem: string, yol: string) => kayit.filter((k) => k.yontem === yontem && k.yol === yol);
const gorunen = () =>
  ["HastaA", "HastaB", "HastaS", "SeansA", "SeansB", "SeansS", "OzetA", "OzetB", "OzetS"].filter((ad) => s.metin().includes(ad));
const cip = () => document.querySelector('[aria-label="Operatör seç"], [aria-label^="Aktif operatör:"], [aria-label^="Kimlik veritabanı okunamıyor"]');

describe("Y113 — kimlik veritabanı okunamazken arayüz arızayı ve çareyi söyler", () => {
  it("KRİTİK: üç liste kayıt GÖSTERMEZ ve ARIZA + ÇARE der (×3); 'operatörünüzü seçin' DEMEZ; çip 'Operatör seçin' DEMEZ", async () => {
    ag.operatorler = "ariza";
    await kur(A, IKI_HEKIM, { A, B, S: "" });
    expect(gorunen()).toEqual([]); // kapı KAPALI (B2-3.1)
    expect(say(ARIZA)).toBe(3);
    expect(say(CARE)).toBe(3);
    expect(say(LISTE_ISTEMI)).toBe(0);
    expect(s.metin()).not.toContain("Operatör seçin");
    expect(cip()?.getAttribute("aria-label")).toMatch(/^Kimlik veritabanı okunamıyor/);
  });

  it("KRİTİK: operatör penceresi 'kayıtlı operatör yok' DEMEZ, arızayı ve çareyi söyler", async () => {
    ag.operatorler = "ariza";
    await kur(A, IKI_HEKIM, {}, []);
    await s.tikla(cip()!.getAttribute("aria-label")!);
    await s.bosalt(5);
    const uyari = document.querySelector('[role="alert"]');
    expect(uyari?.textContent || "").toContain(ARIZA);
    expect(uyari?.textContent || "").toContain(CARE);
    expect(s.metin()).not.toContain("Bu cihazda kayıtlı operatör yok");
  });

  it("KRİTİK: kimliksiz hasta ekleme isteği GİTMEZ; toast ARIZA + ÇARE der", async () => {
    ag.operatorler = "ariza";
    await kur(A, IKI_HEKIM, {}, ["hasta"]);
    await s.metneTikla("Yeni Hasta Kayıt");
    await s.yaz("Hasta adı", "YeniKedi");
    await s.yaz("Hayvan türü", "Kedi");
    await s.metneTikla("Kaydet");
    expect(istekler("POST", "/patients")).toEqual([]);
    const tostlar = mockToast.mock.calls.map((c) => String(c[0]));
    expect(tostlar.some((t) => t.startsWith(ARIZA) && t.includes(CARE))).toBe(true);
    expect(tostlar).not.toContain(EKLEME_ISTEMI);
  });

  it("KRİTİK: kimliksiz AI geçmişi silme isteği GİTMEZ; onay penceresi ARIZA + ÇARE der, 'Operatör seçin' DEMEZ", async () => {
    // Not: kimliksizken AI Geçmişi kart göstermez (Y103) → değerlendirme düğmesine ulaşılamaz; aynı kimlik kapısının ekran
    // yüzü "Geçmişi Sil"dir (ham liste doluyken görünür).
    ag.operatorler = "ariza";
    await kur(A, IKI_HEKIM, { A }, ["ai"]);
    await s.tikla("Kendi AI analiz geçmişimi sil");
    await s.bosalt(5);
    const metinler = onay.mock.calls.map((c) => String(c[0]));
    expect(metinler.length).toBe(1);
    expect(metinler[0].startsWith("Kimlik veritabanı okunamıyor")).toBe(true);
    expect(metinler[0]).toContain(ARIZA);
    expect(metinler[0]).toContain(CARE);
    expect(metinler[0]).not.toContain("Operatör seçin");
    expect(kayit.filter((k) => k.yontem === "POST" && /\/ai\/log\/delete/.test(k.yol))).toEqual([]);
  });
});

describe("Y113 — KARŞIT", () => {
  it("KARŞIT (B2-3.1 korunur): /operators başka nedenle 503 (hazır değil) → 'operatörünüzü seçin' (arıza denmez)", async () => {
    ag.operatorler = "hazir_degil";
    await kur(A, IKI_HEKIM, { A, B, S: "" });
    expect(gorunen()).toEqual([]);
    expect(say(LISTE_ISTEMI)).toBe(3);
    expect(say(ARIZA)).toBe(0);
  });

  it("KARŞIT (toparlanma): arıza kalkınca (200) en geç 30 sn içinde arıza metni kalkar, Kural 2 kliniği kayıtlarını görür", async () => {
    ag.operatorler = "ariza";
    await kur("tek@klinik.com", [], { T: "tek@klinik.com", S: "" });
    expect(say(ARIZA)).toBe(3);
    ag.operatorler = 200;
    for (let t = 0; t < 30_000; t += 5_000) await s.ilerlet(5_000);
    await s.bosalt(10);
    expect(say(ARIZA)).toBe(0);
    for (const ad of ["HastaT", "SeansT", "OzetT"]) expect(s.metin()).toContain(ad);
  });

  it("KARŞIT (kayıtlı klinik toparlanma): arıza kalkınca arıza metni ve çip uyarısı kalkar, istem yine 'operatörünüzü seçin'", async () => {
    ag.operatorler = "ariza";
    await kur(A, IKI_HEKIM, { A, B, S: "" });
    expect(say(ARIZA)).toBe(3);
    ag.operatorler = 200;
    for (let t = 0; t < 30_000; t += 5_000) await s.ilerlet(5_000);
    await s.bosalt(10);
    expect(gorunen()).toEqual([]); // kimse seçili değil → kapı kapalı (Y103)
    expect(say(ARIZA)).toBe(0);
    expect(say(LISTE_ISTEMI)).toBe(3);
    expect(cip()?.getAttribute("aria-label")).toBe("Operatör seç");
  });

  it("KARŞIT (Kural 2): operatörsüz klinik, liste okunuyor → kayıtlar görünür, istem/arıza yok", async () => {
    await kur("tek@klinik.com", [], { T: "tek@klinik.com", S: "" });
    for (const ad of ["HastaT", "SeansT", "OzetT"]) expect(s.metin()).toContain(ad);
    expect(say(ARIZA)).toBe(0);
    expect(say(LISTE_ISTEMI)).toBe(0);
  });
});
