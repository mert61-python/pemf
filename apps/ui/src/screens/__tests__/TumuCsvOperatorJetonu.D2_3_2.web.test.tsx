/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * D2-3.2 (2-D bağımsız incelemesi, A3) — S-D.1 / O-A3.7 (`844b2d1`) sonrası KİMLİKLİ hekimin "Tümünü Excel/CSV İndir"i 428 alır.
 * =======================================================================================================================
 * ÖLÇÜLEN: backend `export_csv` kimlik listesiz istekte kayıtlı operatörlü klinikte operatör JETONU ister (`X-PEMF-Operator` ya da
 * `?operator_token=`; jetonsuz 428 — 2-D kapısı `test_csv_KIMLIK_LISTESIZ_…_OA37.py` "kimlikli hekim tümünü alır" kolunu jetonla
 * ölçüyor). Arayüzün GERÇEK isteği `services/dosyaIndir.ts:downloadFileWithAuth` ile gider ve YALNIZ `X-API-Key` taşır — operatör
 * jetonu YOK. Sonuç: PIN'le seçilmiş hekim "Tüm Klinik"te düğmeye basınca 428 → tost "Kaydedilemedi (428)." (gerekçe de yok).
 *
 * GERÇEK: AuthProvider, UserModeProvider, OperatorProvider, OperatorSwitcher (PIN), AppNavProvider, TreatmentHistoryScreen,
 * dosyaIndir, apiClient (jetonu `setOperatorToken` ile ürün kurar). Sahte yalnız `fetch` (kaydedici + backend'in jeton kuralının
 * birebir taklidi), Supabase, toast (kaydedici), cihaz modülleri. Harness: B2-3.4 kapısı (`disaAktarimKimliksiz.B23_4.web.test.tsx`).
 * Depo yeri: apps/ui/src/screens/__tests__/TumuCsvOperatorJetonu.D2_3_2.web.test.tsx
 */
jest.mock("react-native", () => jest.requireActual("react-native-web"));
const mockOturum = { eposta: "dr.a@klinik.com" };
const mockTostlar: [string, string | undefined][] = [];
jest.mock("@/services/supabaseAuth", () => {
  const aparat = require("../../context/__tests__/operatorAparati");
  return {
    ...aparat.supabaseSahte(""),
    getCurrentSession: async () => ({ access_token: "x", user: { email: mockOturum.eposta, user_metadata: {} } }),
  };
});
jest.mock("@/components/ui/ToastProvider", () => ({
  useToast: () => ({ showToast: (m: string, t?: string) => { mockTostlar.push([m, t]); } }),
}));
// YS1f (CI Node 22): bu test TARAYICI (LAN) dalını ölçer → dal AÇIKÇA sabitlenir. Eskiden `URL` küreseli expo'nun tembel yükleyicisi
// bozuk kaldığı için yoktu ve `backendBuMakinede()` istisnayla false dönüyordu (yan etki); `URL` çalışınca 127.0.0.1 tabanı masaüstü
// dalına düşüyordu ("Masaüstüne kaydedildi").
jest.mock("@/services/backendKonumu", () => ({ ...jest.requireActual("@/services/backendKonumu"), backendBuMakinede: () => false }));
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
import { UserModeProvider, useUserMode } from "@/context/UserModeContext";
import { OperatorProvider } from "@/context/OperatorContext";
import { AppNavProvider } from "@/context/AppNavContext";
import { OperatorSwitcher } from "@/components/domain/OperatorSwitcher";
import { TreatmentHistoryScreen } from "@/screens/TreatmentHistoryScreen";
import { pinleSec, Sahne, sahteSunucu, type Istek, type SahteOperator } from "../../context/__tests__/operatorAparati";

const A = "dr.a@klinik.com";
const B = "dr.b@klinik.com";
const TARIH = "2026-10-01 10:00:00";
const IKI_HEKIM: SahteOperator[] = [{ email: A, display_name: "Dr. A" }, { email: B, display_name: "Dr. B" }];

function Mod({ children }: { children: React.ReactNode }) {
  const { setUserMode, userMode } = useUserMode();
  useEffect(() => { setUserMode("veterinarian"); }, [setUserMode]);
  return userMode ? <>{children}</> : null;
}

let s: Sahne;
let kayit: Istek[];
beforeEach(() => { jest.useFakeTimers(); s = new Sahne(); mockTostlar.length = 0; });
afterEach(async () => { await s.sok(); jest.useRealTimers(); });

async function kur(oturum: string, operatorler: SahteOperator[]) {
  mockOturum.eposta = oturum;
  const seanslar = [A, B, ""].map((e, i) => ({
    id: 100 + i, patient_name: `Seans${i}`, session_date: TARIH, start_time: TARIH, end_time: TARIH,
    duration_minutes: 5, treatment_mode: "Manuel", status: "completed", operator_email: e,
  }));
  const sunucu = sahteSunucu(operatorler, (yol, _g, yontem, operator) => {
    if (yontem === "GET" && yol.startsWith("/history/export_csv")) {
      // backend `history_router.export_csv` kuralının taklidi (O-A3.7 · S-D.1): kayıtlı operatörlü klinikte kimlik LİSTESİZ istek
      // jeton ister (başlık ya da ?operator_token=). Jeton yoksa 428 + gerekçe.
      const listeli = /session_ids=\d/.test(yol);
      const jeton = operator || (yol.match(/operator_token=([^&]+)/) || [])[1] || null;
      if (operatorler.length > 0 && !listeli && !jeton) {
        return [428, { detail: "Operatör seçin — tüm seans geçmişini dışa aktarmak için önce üst bardan hangi hekim olduğunuzu seçin." }];
      }
      return [200, { status: "success", yol: "C:\\Masaustu\\PEMF_Gecmis.csv", ad: "PEMF_Gecmis.csv" }];
    }
    if (yontem === "GET" && yol.startsWith("/history/")) return [200, yol.includes("cursor=") ? [] : seanslar];
    return undefined;
  });
  kayit = sunucu.kayit;
  // Tarayıcı (LAN) dalı `fetch → blob → <a download>` ister: 200 CSV yanıtına blob + text/csv verilir (kayıt yine sahteSunucu'da).
  const ham = sunucu.fetchSahte;
  global.fetch = (async (url: unknown, init?: Record<string, unknown>) => {
    const r = await ham(url, (init || {}) as never);
    if (String(url).includes("/history/export_csv") && r.status === 200) {
      return { ...r, headers: { get: () => "text/csv; charset=utf-8" }, blob: async () => new Blob(["ID;Hasta"]) };
    }
    return r;
  }) as unknown as typeof fetch;
  // `URL` küreseli ortama göre (expo tembel yükleyicisi / Node sürümü) var ya da yok; tarayıcı dalının iki yöntemi HER durumda sahteyle
  // verilir (expo'nun `URL.createObjectURL`u yerel blob modülü yoksa bilerek atar — tarayıcı davranışı değil).
  const g = globalThis as unknown as { URL?: Record<string, unknown> };
  if (!g.URL) g.URL = {};
  g.URL.createObjectURL = () => "blob:a3";
  g.URL.revokeObjectURL = () => undefined;
  await s.ciz(
    <AuthProvider><UserModeProvider><Mod><OperatorProvider><AppNavProvider navigateTo={() => undefined}>
      <OperatorSwitcher />
      <TreatmentHistoryScreen />
    </AppNavProvider></OperatorProvider></Mod></UserModeProvider></AuthProvider>,
  );
  await s.ilerlet(50);
  await s.bosalt(10);
}

const tumuIstekleri = () =>
  kayit.filter((k) => k.yontem === "GET" && k.yol.startsWith("/history/export_csv") && !/session_ids=\d/.test(k.yol));

async function csvTikla() {
  const metin = ["Tümünü Excel/CSV İndir", "Görünenleri Excel/CSV İndir"].find((m) => s.metin().includes(m));
  if (!metin) throw new Error(`CSV düğmesi yok. Govde: ${s.metin().slice(0, 300)}`);
  await s.metneTikla(metin);
  await s.bosalt(10);
}

describe("D2-3.2 — kimlikli hekimin 'Tümünü' CSV isteği operatör jetonunu taşır (S-D.1 sonrası 428 almaz)", () => {
  it("KRİTİK: PIN'le seçilmiş hekim 'Tüm Klinik' → 'Tümünü Excel/CSV İndir' isteği JETONLU gider ve dosya kaydedilir", async () => {
    await kur(A, IKI_HEKIM);
    await pinleSec(s, "Dr. A");
    await s.bosalt(10);
    await s.tikla("Tüm klinik seansları");
    await csvTikla();
    const t = tumuIstekleri();
    expect(t.length).toBe(1); // ARA DOĞRULAMA: düğme gerçekten kimlik listesiz ("Tümünü") isteği attı
    const jeton = t[0].operator || (t[0].yol.match(/operator_token=([^&]+)/) || [])[1] || null;
    expect({ jeton, tostlar: mockTostlar }).toEqual({
      jeton: `JETON-${A}`,
      tostlar: [["İndirme başlatıldı: PEMF_Gecmis.csv", "success"]],
    });
  });

  it("KARŞIT (Kural 2): operatörsüz tek hekimli klinikte 'Tümünü' CSV jetonsuz da kaydedilir", async () => {
    const T = "tek@klinik.com";
    await kur(T, []);
    await s.tikla("Tüm klinik seansları");
    await csvTikla();
    expect(tumuIstekleri().length).toBe(1);
    expect(mockTostlar).toEqual([["İndirme başlatıldı: PEMF_Gecmis.csv", "success"]]);
  });
});
