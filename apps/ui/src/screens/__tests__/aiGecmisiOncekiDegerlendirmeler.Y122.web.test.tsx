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

import React, { useEffect } from "react";
import { AuthProvider } from "@/context/AuthContext";
import { UserModeProvider, useUserMode } from "@/context/UserModeContext";
import { OperatorProvider } from "@/context/OperatorContext";
import { AppNavProvider } from "@/context/AppNavContext";
import { AiHistoryScreen } from "@/screens/AiHistoryScreen";
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

async function kur(liste: unknown, ayrinti: [number, unknown]) {
  const sunucu = sahteSunucu([], (yol, _g, yontem) => {
    if (yontem === "GET" && /^\/ai\/log\/\d+/.test(yol)) {
      ayrintiCagrisi += 1;
      return ayrinti as [number, unknown];
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

test("KARŞIT: ayrıntı ucu reddederse (428) 'yüklenemedi' denir, metin YOK", async () => {
  await kur(FIKSTUR.liste.govde, [428, { detail: "Operatör seçin" }]);
  await s.tikla("m kaydi");
  await s.bosalt(10);
  expect(s.metin()).toMatch(/Önceki değerlendirmeler yüklenemedi/);
  expect(s.metin()).not.toContain(GEREKCE);
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
