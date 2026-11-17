/**
 * @jest-environment jsdom
 */
/**
 * KP-8 · src/screens/PatientScreen.tsx kalan dallar (düzenek KP3-PatientScreen-kollari ile AYNI — GERÇEK sağlayıcılar, sahte fetch):
 *  - KİMLİKSİZ eski kayıt (yalnız ad): kart çizilir; "Düzenle" eksik alanları BOŞ yükler ve güncelleme kimliksiz gider (yeni kayıt
 *    gibi DEĞİL — id alanı boş); çoklu seçimde AD anahtardır ve toplu silme isteği adı taşır; sunucu silinen sayısını vermezse seçilen
 *    sayısı söylenir. Adı da kimliği de olmayan kayıt listeyi çökertmez.
 *  - Arama SAHİP adında da eşleşir; hiçbir kayıt eşleşmezse "aramayla eşleşen yok" (boş liste iletisinden farklı).
 */
jest.mock("react-native", () => jest.requireActual("react-native-web"));
jest.mock("@/services/supabaseAuth", () => {
  const aparat = require("../../context/__tests__/operatorAparati");
  return {
    ...aparat.supabaseSahte(""),
    getCurrentSession: async () => ({ access_token: "x", user: { email: "tek@klinik.com", user_metadata: {} } }),
  };
});
const mockToast = jest.fn();
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: mockToast }) }));
jest.mock("expo-haptics", () => ({ impactAsync: jest.fn(), notificationAsync: jest.fn(), selectionAsync: jest.fn(),
  ImpactFeedbackStyle: {}, NotificationFeedbackType: {} }));
jest.mock("expo-linear-gradient", () => {
  const R = require("react");
  const { View } = require("react-native-web");
  return { LinearGradient: ({ children, style }: { children?: unknown; style?: unknown }) => R.createElement(View, { style }, children) };
});

import React, { useEffect } from "react";
import i18n from "i18next";
import { AuthProvider } from "@/context/AuthContext";
import { UserModeProvider, useUserMode } from "@/context/UserModeContext";
import { OperatorProvider } from "@/context/OperatorContext";
import { AppNavProvider, useAppNav } from "@/context/AppNavContext";
import { PatientScreen } from "@/screens/PatientScreen";
import { profilSozlugu } from "@/utils/profilSozlugu";
import { Sahne, sahteSunucu, type Istek } from "../../context/__tests__/operatorAparati";

const T = (k: string, o?: object): string => (i18n.t as unknown as (k: string, o?: object) => string)(k, o);
const SK = () => profilSozlugu({ petOwner: false, researcher: false });
const BEN = "tek@klinik.com";

function Veteriner({ children }: { children: React.ReactNode }) {
  const { setUserMode, userMode } = useUserMode();
  useEffect(() => { setUserMode("veterinarian"); }, [setUserMode]);
  return userMode ? <>{children}</> : null;
}
let mockSecili: unknown = null;
function SeciliIzle() {
  const { selectedPatient } = useAppNav();
  mockSecili = selectedPatient;
  return null;
}

let s: Sahne;
let kayit: Istek[];
let hastalar: Array<Record<string, unknown>>;
let ozel: (yol: string, govde: unknown, yontem: string) => [number, unknown] | undefined;
let gidilen: string[];
let onay: boolean;
beforeEach(() => {
  jest.useFakeTimers();
  s = new Sahne();
  mockToast.mockClear();
  ozel = () => undefined;
  gidilen = [];
  onay = true;
  mockSecili = null;
  hastalar = [
    { id: "p1", name: "Boncuk", species: "Kedi", breed: "Tekir", age: "3", weight: "4.2", owner: "Ali", vet_contact: "", owner_email: "", operator_email: BEN },
    { id: "p2", name: "Karabaş", species: "Köpek", operator_email: "baska@klinik.com" },
  ];
  jest.spyOn(window, "confirm").mockImplementation(() => onay);
});
afterEach(async () => {
  await s.sok();
  jest.restoreAllMocks();
  jest.useRealTimers();
});

async function kur() {
  const sunucu = sahteSunucu([], (yol: string, g: unknown, yontem: string) => {
    const o = ozel(yol, g, yontem);
    if (o) return o;
    if (yontem === "GET" && yol === "/patients") return [200, { status: "success", data: hastalar }];
    if (yontem === "POST" && yol === "/patients") return [200, { status: "success" }];
    return undefined;
  });
  kayit = sunucu.kayit;
  global.fetch = sunucu.fetchSahte as unknown as typeof fetch;
  await s.ciz(
    <AuthProvider>
      <UserModeProvider>
        <Veteriner>
          <OperatorProvider>
            <AppNavProvider navigateTo={(r: string) => { gidilen.push(r); }}>
              <SeciliIzle />
              <PatientScreen />
            </AppNavProvider>
          </OperatorProvider>
        </Veteriner>
      </UserModeProvider>
    </AuthProvider>,
  );
  await s.ilerlet(50);
  await s.bosalt(10);
}
const postlar = (yol: string) => kayit.filter((k) => k.yontem === "POST" && k.yol === yol);
const tostlar = () => mockToast.mock.calls.map((c) => [String(c[0]), c[1]]);
const sonTost = () => tostlar()[tostlar().length - 1];
/** Ürünün Button'ı aynı etiketin 400 ms içindeki ikinci basışını YUTAR (sahte saat) → basmadan önce saat ilerletilir. */
async function bekleBas(f: () => Promise<void>) { await s.ilerlet(500); await f(); await s.bosalt(6); }
const metinVar = (m: string) => (document.body.textContent || "").includes(m);
async function kaydet() { await bekleBas(() => s.metneTikla(T("ayarlar.kaydet"))); }


it("kimliksiz eski kayıt: kart çizilir; düzenle eksik alanları boş yükler; çoklu seçimde AD anahtar; silinen sayısı yoksa seçilen sayısı", async () => {
  hastalar = [
    { name: "Eski", species: "Kedi", operator_email: BEN },
    { species: "Köpek", operator_email: BEN },
  ];
  await kur();
  expect(metinVar("Eski")).toBe(true);
  await s.tikla(T("hasta.liste.duzenleEtiketi", { name: "Eski" }));
  expect((s.etiket(T("hasta.form.adEtiketi")) as HTMLInputElement).value).toBe("Eski");
  for (const alan of ["hasta.form.irkEtiketi", "hasta.form.yasEtiketi", "hasta.form.kiloEtiketi", "hasta.form.sahipEtiketi"]) {
    expect((s.etiket(T(alan)) as HTMLInputElement).value).toBe("");
  }
  await bekleBas(() => s.metneTikla(T("ayarlar.iptal")));
  ozel = (yol, _g, y) => (y === "POST" && yol === "/patients/delete_bulk" ? [200, { status: "success" }] : undefined);
  await bekleBas(() => s.metneTikla(T("hasta.liste.sec")));
  await s.testIdTikla("hasta-secim-Eski");
  await bekleBas(() => s.testIdTikla("hasta-secim-cubugu-sil"));
  const giden = postlar("/patients/delete_bulk");
  expect(giden).toHaveLength(1);
  expect((giden[0].govde as { patient_ids: string[] }).patient_ids).toEqual(["Eski"]);
  expect(tostlar()).toContainEqual([T("hasta.sil.silindiSayi", { count: 1 }), "success"]);
});

it("arama sahip adında da eşleşir; hiçbir kayıt eşleşmezse 'aramayla eşleşen yok'", async () => {
  await kur();
  await s.metneTikla(SK().tumKapsam + " (2)");
  await s.yaz(T("hasta.liste.araEtiketi"), "Ali");
  await s.bosalt(4);
  expect(metinVar("Boncuk")).toBe(true);
  expect(metinVar("Karabaş")).toBe(false);
  await s.yaz(T("hasta.liste.araEtiketi"), "zzz-yok");
  await s.bosalt(4);
  expect(metinVar(T("hasta.liste.aramaBos"))).toBe(true);
  expect(metinVar(T("hasta.liste.bos"))).toBe(false);
});
