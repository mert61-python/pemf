/**
 * @jest-environment jsdom
 */
/**
 * KP-3 C · src/screens/PatientScreen.tsx kapsanmayan kolları — her test bir DAVRANIŞ iddiası (Y108 düzeneğinin aynısı):
 *  - Form doğrulaması: ad / tür boşsa, yaş 0–50, kilo 0–200 dışındaysa, sahip e-postası biçimsizse KAYIT GİTMEZ (uygun ileti); virgüllü
 *    ondalık noktaya çevrilip gider; sunucu reddi "işlem hatası".
 *  - Düzenleme: kart değerleri forma yüklenir ve YALNIZ değişen alan gönderilir (kayıp güncelleme savunması); "İptal" formu sıfırlar.
 *  - Tekil silme: onay reddedilirse istek GİTMEZ. Tümünü sil başarısızsa ileti. "Seans başlat" hastayı seçip Kontrol'e götürür.
 *  - Çoklu seçim (operatörsüz klinik, veteriner — `silinebilir` kuralı: hepsi silinebilir): seçilen kayıtlar TEK istekte gider;
 *    onay reddi → istek yok; sunucu reddi → ileti. "Benim" kapsamı tıklanınca liste yalnız kendi kayıtlarına döner.
 *  - Liste okunamazsa hata + "Tekrar dene" yeniden okur. 60'tan fazla kayıtta "daha fazla" sonraki sayfayı açar.
 * GERÇEK: AuthProvider, UserModeProvider (veteriner), OperatorProvider (operatörsüz — Kural 2), AppNavProvider, PatientScreen, apiClient.
 * SAHTE: fetch (kaydedici), Supabase istemcisi, toast, `window.confirm`.
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
let hastalar: Record<string, unknown>[];
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
async function kaydet() { await bekleBas(() => s.metneTikla(T("ayarlar.kaydet"))); }

describe("form", () => {
  it("ad/tür boş, yaş/kilo aralık dışı, e-posta biçimsiz → kayıt GİTMEZ; virgüllü ondalık noktaya çevrilir; sunucu reddi ileti", async () => {
    await kur();
    await s.metneTikla(SK().yeniKayit);
    await kaydet();
    expect(sonTost()).toEqual([T("hasta.form.doldurun"), "error"]);
    await s.yaz(T("hasta.form.adEtiketi"), "Minnoş");
    await s.yaz(T("hasta.form.turEtiketi"), "Kedi");
    for (const [alan, deger, ileti] of [
      ["hasta.form.yasEtiketi", "51", "hasta.form.yasAraligi"],
      ["hasta.form.kiloEtiketi", "abc", "hasta.form.kiloAraligi"],
      ["hasta.form.sahipEpostaEtiketi", "ali@", "hasta.form.gecersizEposta"],
    ] as const) {
      await s.yaz(T(alan), deger);
      await kaydet();
      expect(sonTost()).toEqual([T(ileti), "error"]);
      await s.yaz(T(alan), alan === "hasta.form.yasEtiketi" ? "2,5" : alan === "hasta.form.kiloEtiketi" ? "3,75" : "ali@ev.com");
    }
    expect(postlar("/patients")).toHaveLength(0);
    await s.yaz(T("hasta.form.irkEtiketi"), "Van");
    await s.yaz(T("hasta.form.sahipEtiketi"), "Ali");
    await s.yaz(T("hasta.form.vetTelEtiketi"), "0232");
    ozel = (yol, _g, y) => (y === "POST" && yol === "/patients" ? [500, { status: "error" }] : undefined);
    await kaydet();
    expect(postlar("/patients")[0].govde).toMatchObject({
      name: "Minnoş", species: "Kedi", breed: "Van", age: "2.5", weight: "3.75", owner: "Ali", vet_contact: "0232",
      owner_email: "ali@ev.com", operator_email: BEN,
    });
    expect(sonTost()).toEqual([T("hasta.form.islemHatasi"), "error"]);
  });

  it("düzenleme: kart değerleri forma yüklenir, YALNIZ değişen alan gider; 'İptal' formu sıfırlar", async () => {
    await kur();
    await s.tikla(T("hasta.liste.duzenleEtiketi", { name: "Boncuk" }));
    expect((s.etiket(T("hasta.form.irkEtiketi")) as HTMLInputElement).value).toBe("Tekir");
    await s.yaz(T("hasta.form.kiloEtiketi"), "4,5");
    await bekleBas(() => s.metneTikla(T("guncelleme.guncelle")));
    const g = postlar("/patients")[0].govde as Record<string, string>;
    expect(g).toMatchObject({ id: "p1", weight: "4.5" });
    expect(g).not.toHaveProperty("breed");
    expect(sonTost()).toEqual([T("hasta.form.guncellendi"), "success"]);
    await s.tikla(T("hasta.liste.duzenleEtiketi", { name: "Boncuk" }));
    await bekleBas(() => s.metneTikla(T("ayarlar.iptal")));
    await bekleBas(() => s.metneTikla(SK().yeniKayit));
    expect((s.etiket(T("hasta.form.adEtiketi")) as HTMLInputElement).value).toBe("");
  });
});

describe("silme + seans", () => {
  it("tekil silmede onay reddi → istek YOK; 'Seans başlat' hastayı seçip Kontrol'e götürür", async () => {
    await kur();
    onay = false;
    await s.tikla(T("hasta.liste.silEtiketi", { name: "Boncuk" }));
    expect(postlar("/patients/p1/delete")).toHaveLength(0);
    await s.tikla(T("hasta.liste.seansBaslatEtiketi", { name: "Boncuk" }));
    expect(mockSecili).toMatchObject({ id: "p1", name: "Boncuk", species: "Kedi" });
    expect(gidilen).toEqual(["control"]);
    expect(sonTost()).toEqual([T("hasta.kontrolePaneli", { name: "Boncuk" }), "success"]);
  });

  it("tümünü sil başarısız → ileti", async () => {
    ozel = (yol, _g, y) => (y === "POST" && yol === "/patients/delete_all" ? [500, { status: "error" }] : undefined);
    await kur();
    await s.metneTikla(T("hasta.sil.tumunuSil"));
    await s.bosalt(6);
    expect(postlar("/patients/delete_all")).toHaveLength(1);
    expect(tostlar()).toContainEqual([T("hasta.sil.topluBasarisiz"), "error"]);
  });

  it("çoklu seçim: seçilenler TEK istekte gider; onay reddi → istek yok; sunucu reddi → ileti; 'Benim' kapsamına dönüş", async () => {
    ozel = (yol, _g, y) => (y === "POST" && yol === "/patients/delete_bulk" ? [500, { status: "error" }] : undefined);
    await kur();
    await s.metneTikla(SK().tumKapsam + " (2)");
    await bekleBas(() => s.metneTikla(T("hasta.liste.sec")));
    await s.testIdTikla("hasta-secim-p2");
    await s.testIdTikla("hasta-secim-p1");
    onay = false;
    await bekleBas(() => s.testIdTikla("hasta-secim-cubugu-sil"));
    expect(postlar("/patients/delete_bulk")).toHaveLength(0);
    onay = true;
    await bekleBas(() => s.testIdTikla("hasta-secim-cubugu-sil"));
    expect(postlar("/patients/delete_bulk").map((k) => (k.govde as { patient_ids: string[] }).patient_ids.slice().sort())).toEqual([["p1", "p2"]]);
    expect(sonTost()).toEqual([T("hasta.sil.topluBasarisizKisa"), "error"]);
    await bekleBas(() => s.metneTikla(T("hasta.liste.secimiKapat")));
    await s.tikla(SK().benimListe.toLocaleLowerCase("tr-TR").replace(/^benim /, "Benim "));
    expect(s.metin()).not.toContain("Karabaş");
  });
});

describe("liste", () => {
  it("KRİTİK (KP-5 · 17): sunucu 503 GEREKÇESİ verirse (erişimsiz Windows hesabı) liste onu gösterir — 'Bağlantıyı kontrol edin' DEĞİL", async () => {
    const ERISIM = "Bu Windows hesabının PEMF verisine erişimi yok — başlatıcıdaki paylaşım kartıyla erişim verin.";
    ozel = (yol, _g, y) => (y === "GET" && yol === "/patients" ? [503, { detail: ERISIM }] : undefined);
    await kur();
    expect(s.metin()).toContain(ERISIM);
    expect(s.metin()).not.toContain(T("hasta.liste.yuklenemedi"));
    expect(s.metin()).toContain(T("ortak.tekrarDene")); // eylem düğmesi yerinde
  });

  it("KARŞIT (KP-5 · 17): gerekçesiz / 503 olmayan hatada genel ileti AYNEN; yeniden okuma başarılıysa ileti kalkar", async () => {
    let ilk = true;
    ozel = (yol, _g, y) => {
      if (y === "GET" && yol === "/patients" && ilk) { ilk = false; return [500, { detail: "db" }]; }
      return undefined;
    };
    await kur();
    expect(s.metin()).toContain(T("hasta.liste.yuklenemedi"));
    await s.metneTikla(T("ortak.tekrarDene"));
    await s.ilerlet(50);
    await s.bosalt(10);
    expect(s.metin()).not.toContain(T("hasta.liste.yuklenemedi"));
    expect(s.metin()).toContain("Boncuk");
  });

  it("okunamazsa hata + 'Tekrar dene' yeniden okur; 60'tan fazla kayıtta 'daha fazla' sonraki sayfayı açar", async () => {
    let ilk = true;
    ozel = (yol, _g, y) => {
      if (y === "GET" && yol === "/patients" && ilk) { ilk = false; return [500, { detail: "db" }]; }
      return undefined;
    };
    hastalar = Array.from({ length: 65 }, (_, i) => ({ id: `h${i}`, name: `Hasta-${String(i).padStart(2, "0")}`, species: "Kedi", operator_email: BEN }));
    await kur();
    await s.metneTikla(T("ortak.tekrarDene"));
    await s.ilerlet(50);
    await s.bosalt(10);
    expect(s.metin()).toContain("Hasta-00");
    expect(s.varMi(T("hasta.liste.dahaFazlaEtiketi", { count: 5 }))).toBe(true);
    await s.tikla(T("hasta.liste.dahaFazlaEtiketi", { count: 5 }));
    expect(s.metin()).toContain("Hasta-64");
  });
});
