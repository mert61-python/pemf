/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * D2.72 · B-6.26 (+ İG-6.4) · Y92 — Hastalar ve Seans Geçmişi'nde SİLME yalnız KENDİ kayıtlarına.
 * ==============================================================================================
 * ÖLÇÜLEN KUSUR (DENETIM-06 B-6.26; ADAY-DOGRULAMA-D2 İG-6.4): toplu ve tekil silme `deleteScope`/kimlik kapısını
 * kullanmıyordu → "Tüm Klinik → Seç → Tümünü Seç → Sil" başka hekimlerin hasta ve SEANS kayıtlarını silme isteğine koyuyordu;
 * araştırma profili kendisine kapatılan "Tümünü Sil"in işini böyle yapıyordu; kimliksiz ev sahibi ve hareketsizlik
 * kilidinden sonra (önceki hekimin jetonuyla) aynı yol açıktı.
 *
 * KURAL (tek kaynak `patientScope.silinebilir`; sahip kararı Y92): kimlik yoksa istek GİTMEZ; kayıtlı operatörlü cihazda
 * yalnız `operator_email` = aktif operatör olan kayıtlar silinir (sahipsiz de "kendi" değil — backend de 403 der);
 * operatörsüz tek hekimli klinikte (Kural 2) bugünkü gibi — yalnız araştırma profili "Tüm Klinik"te kendi kayıtlarıyla
 * sınırlı (B-6.26). Seçimde silinemeyen kayıt varsa onay penceresi SAYISINI söyler; istek yalnız silinebilenlerle gider.
 *
 * GERÇEK: AuthProvider, UserModeProvider, OperatorProvider (gerçek hareketsizlik zamanlayıcısı), OperatorSwitcher (PIN),
 * AppNavProvider, PatientScreen / TreatmentHistoryScreen, useCokluSecim, SecimCubugu, apiClient.
 * Sahte yalnız `fetch` (kaydedici), Supabase istemcisi, toast, `window.confirm` (onay "evet") ve cihaz modülleri.
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
import { AuthProvider } from "@/context/AuthContext";
import { UserModeProvider, useUserMode, type UserMode } from "@/context/UserModeContext";
import { AUTO_LOCK_MS, OperatorProvider } from "@/context/OperatorContext";
import { AppNavProvider } from "@/context/AppNavContext";
import { OperatorSwitcher } from "@/components/domain/OperatorSwitcher";
import { PatientScreen } from "@/screens/PatientScreen";
import { TreatmentHistoryScreen } from "@/screens/TreatmentHistoryScreen";
import { BASKA_HEKIM_SILME } from "@/utils/patientScope";
import { ZATEN_SILINMIS_SEANS } from "@/screens/TreatmentHistoryScreen";
import { aktifOperator, pinleSec, Sahne, sahteSunucu, type Istek, type SahteOperator } from "../../context/__tests__/operatorAparati";

const A = "dr.a@klinik.com";
const B = "dr.b@klinik.com";
const TARIH = "2026-10-01 10:00:00";
const IKI_HEKIM: SahteOperator[] = [{ email: A, display_name: "Dr. A" }, { email: B, display_name: "Dr. B" }];

function veri(sahipler: Record<string, string>) {
  const hastalar = Object.entries(sahipler).map(([ad, e], i) => ({
    id: `p${i}`, name: `Hasta${ad}`, species: "Kedi", breed: "", age: 3, weight: 4, owner_name: "", owner_phone: "",
    operator_email: e, created_at: TARIH,
  }));
  const seanslar = Object.entries(sahipler).map(([ad, e], i) => ({
    id: 100 + i, patient_name: `Seans${ad}`, session_date: TARIH, start_time: TARIH, end_time: TARIH,
    duration_minutes: 5, treatment_mode: "Manuel", status: "completed", operator_email: e,
  }));
  return { hastalar, seanslar };
}

function Mod({ mod, children }: { mod: UserMode; children: React.ReactNode }) {
  const { setUserMode, userMode } = useUserMode();
  useEffect(() => { setUserMode(mod); }, [mod, setUserMode]);
  return userMode ? <>{children}</> : null;
}

type EkranAdi = "hasta" | "seans";
const EKRAN = {
  hasta: {
    Bilesen: PatientScreen,
    tumKlinik: "Tüm klinik hastaları",
    cubuk: "hasta-secim-cubugu",
    toplu: "/patients/delete_bulk",
    alan: "patient_ids",
    kimlik: (sira: number) => `p${sira}`,
    tekilEtiket: (ad: string) => `Hasta${ad} kaydını sil`,
    tekilMi: (k: Istek) => /^\/patients\/[^/]+\/delete$/.test(k.yol),
  },
  seans: {
    Bilesen: TreatmentHistoryScreen,
    tumKlinik: "Tüm klinik seansları",
    cubuk: "gecmis-secim-cubugu",
    toplu: "/history/delete_bulk",
    alan: "session_ids",
    kimlik: (sira: number) => 100 + sira,
    tekilEtiket: (ad: string) => `Seans${ad} kaydını sil`,
    tekilMi: (k: Istek) => k.yol === "/history/delete",
  },
} as const;

let s: Sahne;
let onaylar: string[];
let kayit: Istek[];
/** D2.43: tekil seans silmesinin sunucu yanıt kodu (404 = zaten silinmiş). */
let tekilDurum = 200;
beforeEach(() => {
  jest.useFakeTimers();
  s = new Sahne();
  onaylar = [];
  tekilDurum = 200;
  jest.spyOn(window, "confirm").mockImplementation((m?: string) => { onaylar.push(String(m)); return true; });
});
afterEach(async () => {
  await s.sok();
  (window.confirm as jest.Mock).mockRestore?.();
  jest.useRealTimers();
});

async function kur(ekran: EkranAdi, mod: UserMode, oturum: string, operatorler: SahteOperator[], sahipler: Record<string, string>) {
  mockOturum.eposta = oturum;
  mockToast.mockClear();
  const { hastalar, seanslar } = veri(sahipler);
  const sunucu = sahteSunucu(operatorler, (yol, _g, yontem) => {
    if (yontem === "GET" && yol === "/patients") return [200, { status: "success", data: hastalar }];
    if (yontem === "GET" && yol.startsWith("/history/")) return [200, yol.includes("cursor=") ? [] : seanslar];
    if (yontem === "GET" && yol.startsWith("/ai/log")) return [200, { status: "success", data: [] }];
    if (yontem === "POST" && yol === "/history/delete" && tekilDurum !== 200) {
      return [tekilDurum, { detail: "Seans bulunamadı — zaten silinmiş olabilir; listeyi yenileyin." }];
    }
    if (yontem === "POST" && /delete/.test(yol)) return [200, { status: "success", silinen: 1 }];
    return undefined;
  });
  kayit = sunucu.kayit;
  global.fetch = sunucu.fetchSahte as unknown as typeof fetch;
  const { Bilesen } = EKRAN[ekran];
  await s.ciz(
    <AuthProvider>
      <UserModeProvider>
        <Mod mod={mod}>
          <OperatorProvider>
            <AppNavProvider navigateTo={() => undefined}>
              <OperatorSwitcher />
              <Bilesen />
            </AppNavProvider>
          </OperatorProvider>
        </Mod>
      </UserModeProvider>
    </AuthProvider>,
  );
  await s.ilerlet(50);
  await s.bosalt(10);
}

async function secimKipi(ekran: EkranAdi) {
  if (ekran === "hasta") await s.metneTikla("Seç");
  else await s.tikla("Toplu seçim kipini aç veya kapat");
}

async function tumunuSecVeSil(ekran: EkranAdi) {
  const e = EKRAN[ekran];
  await secimKipi(ekran);
  await s.testIdTikla(`${e.cubuk}-tumunu`);
  await s.testIdTikla(`${e.cubuk}-sil`);
  await s.bosalt(10);
}

const silmeler = (ekran: EkranAdi) =>
  kayit.filter((k) => k.yontem === "POST" && (k.yol === EKRAN[ekran].toplu || EKRAN[ekran].tekilMi(k)));
const topluKimlikler = (ekran: EkranAdi) =>
  silmeler(ekran).map((k) => [...((k.govde as Record<string, unknown[]>)[EKRAN[ekran].alan] || [])].sort());
const toastlar = () => mockToast.mock.calls.map((c) => String(c[0]));

describe.each(["hasta", "seans"] as EkranAdi[])("D2.72 · Y92 — %s silme yalnız KENDİ kayıtlarına", (ekran) => {
  const e = EKRAN[ekran];

  it("KRİTİK: kimlikli hekim 'Tüm Klinik → Tümünü Seç → Sil' → istek kendi + SAHİPSİZ kayıtla (Y104), BAŞKA hekiminki YOK; onay söyler", async () => {
    await kur(ekran, "veterinarian", A, IKI_HEKIM, { A, B, S: "", X: "eski@klinik.com" });
    await pinleSec(s, "Dr. A");
    await s.bosalt(10);
    await s.tikla(e.tumKlinik);
    await tumunuSecVeSil(ekran);
    // Y104: sahipsiz (boş) ve cihazda KAYITLI OLMAYAN e-postalı (ortak giriş) kayıt silinebilir; B (kayıtlı hekim) ASLA (Y92).
    expect(topluKimlikler(ekran)).toEqual([[e.kimlik(0), e.kimlik(2), e.kimlik(3)].sort()]);
    expect(silmeler(ekran)[0].operator).toBe(`JETON-${A}`);
    expect(onaylar.join("\n")).toContain("1 kayıt başka bir hekime ait — SİLİNMEYECEK");
  });

  it("KRİTİK: kimlikli hekim BAŞKA (kayıtlı) hekimin kaydında TEKİL 'sil' → istek YOK, uyarı", async () => {
    await kur(ekran, "veterinarian", A, IKI_HEKIM, { A, B, S: "" });
    await pinleSec(s, "Dr. A");
    await s.bosalt(10);
    await s.tikla(e.tumKlinik);
    await s.tikla(e.tekilEtiket("B"));
    expect(silmeler(ekran)).toEqual([]);
    expect(toastlar().filter((t) => t === BASKA_HEKIM_SILME).length).toBe(1);
  });

  it("KRİTİK (Y104): SAHİPSİZ ve ORTAK GİRİŞ (kayıtlı olmayan e-posta) kaydında TEKİL 'sil' → istek gider, aktif hekimin jetonuyla", async () => {
    await kur(ekran, "veterinarian", A, IKI_HEKIM, { A, B, S: "", X: "eski@klinik.com" });
    await pinleSec(s, "Dr. A");
    await s.bosalt(10);
    await s.tikla(e.tumKlinik);
    await s.tikla(e.tekilEtiket("S"));
    await s.bosalt(5);
    await s.tikla(e.tekilEtiket("X"));
    await s.bosalt(5);
    const t = silmeler(ekran);
    expect(t.length).toBe(2);
    expect(t.every((k) => k.operator === `JETON-${A}`)).toBe(true);
    expect(toastlar()).not.toContain(BASKA_HEKIM_SILME);
  });

  it("KARŞIT: kendi kaydında TEKİL 'sil' → istek gider, aktif operatörün jetonuyla", async () => {
    await kur(ekran, "veterinarian", A, IKI_HEKIM, { A, B, S: "" });
    await pinleSec(s, "Dr. A");
    await s.bosalt(10);
    await s.tikla(e.tekilEtiket("A"));
    const t = silmeler(ekran);
    expect(t.length).toBe(1);
    expect(t[0].operator).toBe(`JETON-${A}`);
  });

  it("KRİTİK (B-6.26, Kural 2'de de): araştırma profili 'Tüm Klinik'te Tümünü Seç → Sil → YALNIZ kendi kaydı", async () => {
    const R = "arastirma@klinik.com";
    await kur(ekran, "researcher", R, [], { R, S: "", X: "eski@klinik.com" });
    await s.tikla(e.tumKlinik);
    await tumunuSecVeSil(ekran);
    expect(topluKimlikler(ekran)).toEqual([[e.kimlik(0)]]);
  });

  it("KARŞIT (Kural 2): operatörsüz tek hekimli klinikte hekim 'Tüm Klinik'te seçtiği HER kaydı siler", async () => {
    const T = "tek@klinik.com";
    await kur(ekran, "veterinarian", T, [], { T, S: "", X: "eski@klinik.com" });
    await s.tikla(e.tumKlinik);
    await tumunuSecVeSil(ekran);
    expect(topluKimlikler(ekran)).toEqual([[e.kimlik(0), e.kimlik(1), e.kimlik(2)].sort()]);
    expect(toastlar()).not.toContain(BASKA_HEKIM_SILME);
  });

  it("KRİTİK (İG-6.4 b): seçim yapılmışken hareketsizlik kilidi düşer → silme isteği GİTMEZ (önceki hekimin jetonuyla da)", async () => {
    await kur(ekran, "veterinarian", A, IKI_HEKIM, { A, B, S: "" });
    await pinleSec(s, "Dr. A");
    await s.bosalt(10);
    await s.tikla(e.tumKlinik);
    await secimKipi(ekran);
    await s.testIdTikla(`${e.cubuk}-tumunu`);
    for (let t = 0; t < AUTO_LOCK_MS + 31_000; t += 30_000) await s.ilerlet(30_000);
    expect(aktifOperator()).toBeNull(); // ARA DOĞRULAMA: kilit düştü
    // KATMANLI: D2.70 kimliksizken listeyi (ve seçim çubuğunu) gizler; çubuk bir yoldan görünse bile silme kapısı istek
    // göndermez (mutantla gösterilir).
    if (document.querySelector(`[data-testid="${e.cubuk}-sil"]`)) await s.testIdTikla(`${e.cubuk}-sil`);
    expect(silmeler(ekran)).toEqual([]);
  });

  it("KRİTİK (kimliksiz): kayıtlı operatörlü cihazda kimse seçili değil → silme isteği YOK", async () => {
    await kur(ekran, "veterinarian", A, IKI_HEKIM, { A, B, S: "" });
    // KATMANLI (D2.70 listeyi gizler): kart/çubuk bir yoldan görünürse dene.
    if (s.varMi(e.tekilEtiket("B"))) await s.tikla(e.tekilEtiket("B"));
    if (document.querySelector(`[data-testid="${e.cubuk}-tumunu"]`) || s.metin().includes("Seç")) {
      try { await tumunuSecVeSil(ekran); } catch { /* çubuk yok — D2.70 katmanı */ }
    }
    expect(silmeler(ekran)).toEqual([]);
  });
});

describe("D2.43 · B-2.7 — tekil seans silmesi 404 (zaten silinmiş)", () => {
  it("KRİTİK: sunucu 404 → hata değil 'zaten silinmiş' bilgisi ve liste YENİLENİR", async () => {
    await kur("seans", "veterinarian", A, IKI_HEKIM, { A, B, S: "" });
    await pinleSec(s, "Dr. A");
    await s.bosalt(10);
    tekilDurum = 404;
    const once = kayit.filter((k) => k.yontem === "GET" && k.yol.startsWith("/history/")).length;
    await s.tikla(EKRAN.seans.tekilEtiket("A"));
    await s.bosalt(10);
    expect(silmeler("seans").length).toBe(1); // ARA DOĞRULAMA: istek gitti, sunucu 404 dedi
    expect(mockToast.mock.calls).toContainEqual([ZATEN_SILINMIS_SEANS, "info"]);
    expect(kayit.filter((k) => k.yontem === "GET" && k.yol.startsWith("/history/")).length).toBeGreaterThan(once);
  });

  it("KARŞIT: başka bir hata (500) 'zaten silinmiş' DEMEZ, sunucunun gerekçesini gösterir", async () => {
    await kur("seans", "veterinarian", A, IKI_HEKIM, { A, B, S: "" });
    await pinleSec(s, "Dr. A");
    await s.bosalt(10);
    tekilDurum = 500;
    await s.tikla(EKRAN.seans.tekilEtiket("A"));
    await s.bosalt(10);
    expect(toastlar()).not.toContain(ZATEN_SILINMIS_SEANS);
    expect(mockToast.mock.calls.some((c) => c[1] === "error")).toBe(true);
  });
});
