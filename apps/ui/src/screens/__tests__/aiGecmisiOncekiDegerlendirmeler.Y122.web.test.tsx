/**
 * @jest-environment jsdom
 */
/**
 * Y122 (S-C.4) + Y126 — AI Geçmişi kaydının ayrıntısında "Önceki değerlendirmeler" (karar, metin, hekim, zaman).
 * ===========================================================================================================================
 * ÖLÇÜLEN KUSUR: Y114'ten beri önceki red gerekçeleri / düzeltilmiş teşhisler kaydın şifreli tablosunda duruyor ama ekran hiçbir yerde
 * göstermiyordu; liste ucu ise metinleri LAN'dan jetonsuz taşıyordu. Artık liste yalnız SAYIYI taşır (Y126); ekran kart açılınca
 * ayrıntı ucundan (`GET /api/ai/log/{id}`, kimlikli) metinleri çeker ve gösterir. Çekilemezse "yüklenemedi" der (sessiz boş YOK).
 * GİRDİ: `__fixtures__/aiGecmisiOnceki.Y122.json` — GERÇEK backend'in liste + ayrıntı yanıtları
 * (`tests/test_ai_gecmisi_DEGERLENDIRME_GECMISI_ayrintida_Y122_Y126.py` üretir ve bayatlamayı yakalar).
 * GERÇEK: AuthProvider, UserModeProvider, OperatorProvider (operatörsüz — Kural 2), AppNavProvider, AiHistoryScreen, apiClient.
 * Sahte: fetch, Supabase, toast, cihaz modülleri.
 *
 * 2-F incelemesi §10 #11 (D5 · yardımcı E): "yüklenemedi" metni NEDENİ ayırır — 428 (kimlik gerekli) bugünkü "hekim seçin" metni; 428 +
 * kimlik veritabanı okunamıyor (Y113) arıza + çare ("hekim seçin" DEMEZ); başka HTTP hatası (503 kayıt veritabanı vb.) "şu an okunamıyor —
 * biraz sonra kaydı kapatıp yeniden açın"; yanıt yok (ağ) "cihaza bağlanılamadı". Hata önbellekte KALICI değil: kart kapanıp açılınca yeniden
 * denenir (eskiden "hata" kalıcıydı — eylem metni yalan olurdu). Ağ kolu: `fetch` REDDEDİLİR (en alt kat), `apiGet` 400 ms sonra bir kez
 * daha dener — gerçek zamanla beklenir.
 */
jest.mock("react-native", () => jest.requireActual("react-native-web"));
jest.mock("@/services/supabaseAuth", () => {
  const aparat = require("../../context/__tests__/operatorAparati");
  return {
    ...aparat.supabaseSahte(""),
    getCurrentSession: async () => ({ access_token: "x", user: { email: "tek@klinik.com", user_metadata: {} } }),
  };
});
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: jest.fn() }) }));
jest.mock("expo-sharing", () => ({ isAvailableAsync: jest.fn(async () => false), shareAsync: jest.fn() }));
jest.mock("expo-file-system/legacy", () => ({ documentDirectory: "file:///", writeAsStringAsync: jest.fn() }));
jest.mock("expo-haptics", () => ({ impactAsync: jest.fn(), notificationAsync: jest.fn(), selectionAsync: jest.fn(),
  ImpactFeedbackStyle: {}, NotificationFeedbackType: {} }));
jest.mock("expo-linear-gradient", () => {
  const R = require("react");
  const { View } = require("react-native-web");
  return { LinearGradient: ({ children, style }: { children?: unknown; style?: unknown }) => R.createElement(View, { style }, children) };
});

import React, { act, useEffect } from "react";
import { AuthProvider } from "@/context/AuthContext";
import { UserModeProvider, useUserMode } from "@/context/UserModeContext";
import { OperatorProvider } from "@/context/OperatorContext";
import { AppNavProvider } from "@/context/AppNavContext";
import { AiHistoryScreen } from "@/screens/AiHistoryScreen";
import { KIMLIK_DB_ARIZA_ONEKI } from "@/utils/patientScope";
import { Sahne, sahteSunucu } from "../../context/__tests__/operatorAparati";

// eslint-disable-next-line @typescript-eslint/no-var-requires
const FIKSTUR = require("./__fixtures__/aiGecmisiOnceki.Y122.json");
const GEREKCE = "Lezyon sinirlari yanlis-Y122-gizli-gerekce";

function Mod({ children }: { children: React.ReactNode }) {
  const { setUserMode, userMode } = useUserMode();
  useEffect(() => { setUserMode("veterinarian"); }, [setUserMode]);
  return userMode ? <>{children}</> : null;
}

let s: Sahne;
let ayrintiCagrisi: number;
beforeEach(() => {
  s = new Sahne();
  ayrintiCagrisi = 0;
});
afterEach(async () => {
  await s.sok();
});

/** Ayrıntı ucunun yanıtı: [durum, gövde] · "ag" = bağlantı yok (`fetch` REDDEDİLİR — en alt kat) · işlev = çağrı sırasına göre. */
type Ayrinti = [number, unknown] | "ag";

async function kur(liste: unknown, ayrinti: Ayrinti | ((n: number) => Ayrinti)) {
  const sunucu = sahteSunucu([], (yol, _g, yontem) => {
    if (yontem === "GET" && /^\/ai\/log\/\d+/.test(yol)) {
      ayrintiCagrisi += 1;
      const y = typeof ayrinti === "function" ? ayrinti(ayrintiCagrisi) : ayrinti;
      if (y === "ag") throw new TypeError("Failed to fetch (sahte: cihaza bağlantı yok)");
      return y;
    }
    if (yontem === "GET" && yol.startsWith("/ai/log")) {
      return [200, yol.includes("before_id") ? { status: "success", data: [] } : liste];
    }
    return undefined;
  });
  global.fetch = sunucu.fetchSahte as unknown as typeof fetch;
  await s.ciz(
    <AuthProvider>
      <UserModeProvider>
        <Mod>
          <OperatorProvider>
            <AppNavProvider navigateTo={() => undefined}>
              <AiHistoryScreen />
            </AppNavProvider>
          </OperatorProvider>
        </Mod>
      </UserModeProvider>
    </AuthProvider>,
  );
  await s.bosalt(10);
}

test("KRİTİK: kart açılınca önceki değerlendirme (karar · hekim + metin) ayrıntı ucundan GÖSTERİLİR; liste metni taşımaz", async () => {
  expect(FIKSTUR.liste.durum).toBe(200);
  expect(JSON.stringify(FIKSTUR.liste.govde)).not.toContain(GEREKCE);
  await kur(FIKSTUR.liste.govde, [FIKSTUR.ayrinti.durum, FIKSTUR.ayrinti.govde]);
  expect(s.metin()).not.toContain(GEREKCE);
  await s.tikla("m kaydi");
  await s.bosalt(10);
  const metin = s.metin();
  expect(metin).toMatch(/Önceki değerlendirmeler \(1\)/);
  expect(metin).toContain(GEREKCE);
  expect(metin).toMatch(/Hekim reddetti · tek@klinik\.com/); // karar etiketi ReviewBadge ile aynı (REVIEW_LABEL)
  expect(ayrintiCagrisi).toBe(1);
});

const HEKIM_SECIN = /Önceki değerlendirmeler yüklenemedi — kayıtlı hekimli cihazda üst bardan hangi hekim olduğunuzu seçin\./;

test("KARŞIT: ayrıntı ucu reddederse (428) 'yüklenemedi' denir, metin YOK", async () => {
  await kur(FIKSTUR.liste.govde, [428, { detail: "Operatör seçin" }]);
  await s.tikla("m kaydi");
  await s.bosalt(10);
  expect(s.metin()).toMatch(HEKIM_SECIN); // 2-F §10 #11: 428'de bugünkü metin AYNEN
  expect(s.metin()).not.toContain(GEREKCE);
});

test("KRİTİK (2-F §10 #11): 428 + kimlik veritabanı okunamıyor (Y113) → 'hekim seçin' DENMEZ, arıza + çare söylenir", async () => {
  await kur(FIKSTUR.liste.govde, [428, { detail: `${KIMLIK_DB_ARIZA_ONEKI} — kayıtların hangi hekime ait olduğu doğrulanamıyor` }]);
  await s.tikla("m kaydi");
  await s.bosalt(10);
  const metin = s.metin();
  expect(metin).not.toMatch(/hangi hekim olduğunuzu seçin/);
  expect(metin).toMatch(/Cihazın kimlik veritabanı okunamıyor — .*Çare:/);
});

test("KRİTİK (2-F §10 #11): 503 (kayıt veritabanı) → 'hekim seçin' DENMEZ; 'şu an okunamıyor — biraz sonra yeniden açın'", async () => {
  await kur(FIKSTUR.liste.govde, [503, { detail: "Kayıt veritabanı açılamadı." }]);
  await s.tikla("m kaydi");
  await s.bosalt(10);
  const metin = s.metin();
  expect(metin).not.toMatch(/hangi hekim olduğunuzu seçin/);
  expect(metin).toMatch(/Önceki değerlendirmeler şu an okunamıyor — cihaz kaydı veremedi; biraz sonra kaydı kapatıp yeniden açın\./);
  expect(metin).not.toContain(GEREKCE);
});

test("KARŞIT (2-F §10 #11): YALNIZ 428 kimlik ister — başka 4xx (404 kayıt yok) 'hekim seçin' DEMEZ", async () => {
  await kur(FIKSTUR.liste.govde, [404, { detail: "Analiz kaydı bulunamadı." }]);
  await s.tikla("m kaydi");
  await s.bosalt(10);
  expect(s.metin()).not.toMatch(/hangi hekim olduğunuzu seçin/);
  expect(s.metin()).toMatch(/Önceki değerlendirmeler şu an okunamıyor/);
});

test("KRİTİK (2-F §10 #11): bağlantı yok (fetch reddi) → 'hekim seçin' DENMEZ; 'cihaza bağlanılamadı'", async () => {
  await kur(FIKSTUR.liste.govde, "ag");
  await s.tikla("m kaydi");
  await act(async () => { await new Promise((r) => setTimeout(r, 450)); }); // apiGet'in ikinci denemesi (400 ms) — gerçek zaman
  await s.bosalt(10);
  const metin = s.metin();
  expect(ayrintiCagrisi).toBe(2);
  expect(metin).not.toMatch(/hangi hekim olduğunuzu seçin/);
  expect(metin).toMatch(/Önceki değerlendirmeler yüklenemedi — cihaza bağlanılamadı; bağlantı gelince kaydı kapatıp yeniden açın\./);
});

test("KRİTİK (2-F §10 #11): hata önbellekte KALICI değil — kart kapanıp açılınca YENİDEN denenir, düzelince metin gelir", async () => {
  await kur(FIKSTUR.liste.govde, (n) => (n === 1 ? [503, { detail: "Kayıt veritabanı açılamadı." }] : [FIKSTUR.ayrinti.durum, FIKSTUR.ayrinti.govde]));
  await s.tikla("m kaydi");
  await s.bosalt(10);
  expect(s.metin()).toMatch(/şu an okunamıyor/);
  await s.tikla("m kaydi, acik"); // kapat
  await s.bosalt(5);
  await s.tikla("m kaydi"); // yeniden aç
  await s.bosalt(10);
  expect(ayrintiCagrisi).toBe(2);
  expect(s.metin()).toContain(GEREKCE);
  expect(s.metin()).not.toMatch(/şu an okunamıyor/);
});

test("KARŞIT: önceki değerlendirmesi olmayan kayıtta blok YOK ve ayrıntı ucu ÇAĞRILMAZ", async () => {
  const liste = JSON.parse(JSON.stringify(FIKSTUR.liste.govde));
  liste.data[0].review_history_count = 0;
  await kur(liste, [FIKSTUR.ayrinti.durum, FIKSTUR.ayrinti.govde]);
  await s.tikla("m kaydi");
  await s.bosalt(10);
  expect(s.metin()).not.toMatch(/Önceki değerlendirmeler/);
  expect(ayrintiCagrisi).toBe(0);
});
