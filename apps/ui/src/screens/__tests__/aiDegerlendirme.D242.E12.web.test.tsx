/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * D2.42 · B-6.21 (+ İG-6.26) ve D2.E12 · İG-6.115 — AI Geçmişi'nde hekim değerlendirmesi.
 * ======================================================================================
 * ÖLÇÜLEN KUSURLAR:
 *  · D2.42 (DENETIM-06 g2a/g2b): `submitReview` `useCallback(..., [session])` — kart açıkken operatör değişince ESKİ hekimin
 *    e-postasıyla imzalıyordu ("bu teşhisi kim onayladı" kaydı önceki hekimi gösteriyor).
 *  · İG-6.26: değerlendirmede kimlik kapısı yoktu (silmede vardı). D2.70 (Y103) kimliksizken listeyi boşalttığı için ekran
 *    yolu bugün o kapıya ulaşamaz — katman: aşağıdaki kol, D2.70 katmanı mutantla indirilince kapının ısırdığını gösterir.
 *  · D2.E12 (aday, gerçek tarayıcı + CDP 500/503): değerlendirme başarısız olunca hekimin yazdığı red/düzeltme gerekçesi
 *    istek DÖNMEDEN siliniyordu (form kapanıyor, metin "" — 0/19, 0/20); kart kapat-aç da taslağı kaybettiriyordu.
 *
 * GERÇEK: AuthProvider, UserModeProvider, OperatorProvider, OperatorSwitcher (PIN), AppNavProvider, AiHistoryScreen,
 * AiReviewControls, apiClient. Sahte yalnız `fetch`, Supabase istemcisi, toast ve cihaz modülleri.
 * Kural 2: operatörsüz tek hekimli klinikte değerlendirme oturum e-postasıyla gider. Taslak YALNIZ bellekte (KVKK).
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
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: jest.fn() }) }));
jest.mock("expo-sharing", () => ({ isAvailableAsync: jest.fn(async () => false), shareAsync: jest.fn() }));
jest.mock("expo-file-system/legacy", () => ({ documentDirectory: "file:///", writeAsStringAsync: jest.fn() }));
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
import { AiHistoryScreen } from "@/screens/AiHistoryScreen";
import { pinleSec, Sahne, sahteSunucu, type Istek, type SahteOperator } from "../../context/__tests__/operatorAparati";

const A = "dr.a@klinik.com";
const B = "dr.b@klinik.com";
const GEREKCE = "Klinik bulgularla uyusmuyor (E12)";

function Mod({ children }: { children: React.ReactNode }) {
  const { setUserMode, userMode } = useUserMode();
  useEffect(() => { setUserMode("veterinarian"); }, [setUserMode]);
  return userMode ? <>{children}</> : null;
}

let s: Sahne;
let kayit: Istek[];
const sunucuDurumu = { review: 200 };

beforeEach(() => {
  jest.useFakeTimers();
  s = new Sahne();
  sunucuDurumu.review = 200;
});
afterEach(async () => {
  await s.sok();
  jest.useRealTimers();
});

async function kur(oturum: string, operatorler: SahteOperator[]) {
  mockOturum.eposta = oturum;
  const analiz = {
    id: 7, created_at: "2026-10-01 10:00:00", mode: "veterinarian", module_id: "m", module_label: "Kedi FGS",
    patient_name: "Pamuk", input_type: "image", result_summary: "Ozet-E12", result_detail: {}, confidence: 0.9,
    operator_email: "", review_status: "",
  };
  const sunucu = sahteSunucu(operatorler, (yol, _g, yontem) => {
    if (yontem === "GET" && yol.startsWith("/ai/log")) {
      return [200, { status: "success", data: yol.includes("before_id") ? [] : [analiz] }];
    }
    if (yontem === "POST" && yol === "/ai/log/review") {
      return sunucuDurumu.review === 200
        ? [200, { status: "success", analysisId: 7 }]
        : [sunucuDurumu.review, { detail: "Sunucu hatası (taklit)" }];
    }
    return undefined;
  });
  kayit = sunucu.kayit;
  global.fetch = sunucu.fetchSahte as unknown as typeof fetch;
  await s.ciz(
    <AuthProvider>
      <UserModeProvider>
        <Mod>
          <OperatorProvider>
            <AppNavProvider navigateTo={() => undefined}>
              <OperatorSwitcher />
              <AiHistoryScreen />
            </AppNavProvider>
          </OperatorProvider>
        </Mod>
      </UserModeProvider>
    </AuthProvider>,
  );
  await s.ilerlet(50);
  await s.bosalt(10);
}

const kartiAcKapa = async () => s.tikla(document.querySelector('[aria-label^="Kedi FGS kaydi"]')!.getAttribute("aria-label")!);
const degerlendirmeler = () => kayit.filter((k) => k.yol === "/ai/log/review" && k.yontem === "POST");
const gerekceAlani = () => document.querySelector('[aria-label="Red gerekçesi"]') as HTMLTextAreaElement | null;

describe("D2.42 · B-6.21 — değerlendirme O ANKİ aktif operatörle imzalanır", () => {
  it("KRİTİK: kart açıkken vet1 → vet2 geçişinden sonra 'Onayla' vet2 adına (gövde + jeton)", async () => {
    await kur(A, [{ email: A, display_name: "Dr. A" }, { email: B, display_name: "Dr. B" }]);
    await pinleSec(s, "Dr. A");
    await s.bosalt(10);
    await kartiAcKapa();
    await pinleSec(s, "Dr. B");
    await s.bosalt(10);
    await s.tikla("AI sonucunu onayla");
    const d = degerlendirmeler();
    expect(d.length).toBe(1);
    expect((d[0].govde as { reviewed_by?: string }).reviewed_by).toBe(B);
    expect(d[0].operator).toBe(`JETON-${B}`);
  });

  it("KRİTİK (İG-6.26): operatör KAYITLI, kimse seçili değil → değerlendirme isteği 0, imzasız 'Hekim onayladı' YOK", async () => {
    const onay = jest.spyOn(window, "confirm").mockImplementation(() => false);
    try {
      await kur(A, [{ email: A, display_name: "Dr. A" }, { email: B, display_name: "Dr. B" }]);
      // KATMANLI: (1) D2.70 · Y103 kimliksizken kaydı LİSTELEMEZ; (2) `submitReview` kimlik kapısı, kart bir yoldan
      // görünse bile isteği GÖNDERMEZ. Bugün (1) kartı gizler; (2)'nin ısırdığı mutantla gösterilir (D2.70 katmanı
      // indirilince kart görünür, bu dal koşar ve kapı "Operatör seçin" der — ikisi birden indirilince KIRMIZI).
      if (document.querySelector('[aria-label^="Kedi FGS kaydi"]')) {
        await kartiAcKapa();
        await s.tikla("AI sonucunu onayla");
        expect(onay).toHaveBeenCalledWith(expect.stringContaining("Operatör seçin"));
      }
      expect(degerlendirmeler().length).toBe(0);
      expect(s.metin()).not.toContain("Hekim onayladı");
    } finally {
      onay.mockRestore();
    }
  });

  it("KARŞIT (Kural 2): operatörsüz tek hekimli klinikte değerlendirme oturum e-postasıyla gider", async () => {
    const T = "tek@klinik.com";
    await kur(T, []);
    await kartiAcKapa();
    await s.tikla("AI sonucunu onayla");
    const d = degerlendirmeler();
    expect(d.length).toBe(1);
    expect((d[0].govde as { reviewed_by?: string }).reviewed_by).toBe(T);
  });
});

describe("D2.E12 · İG-6.115 — gerekçe sunucu BAŞARI dönene dek korunur", () => {
  async function reddetVeYaz() {
    await s.tikla("AI sonucunu reddet");
    await s.yaz("Red gerekçesi", GEREKCE);
    await s.tikla("Reddi kaydet");
    await s.bosalt(10);
  }

  it("KRİTİK: sunucu 500 → form AÇIK, gerekçe DURUR, hata satırı görünür; kart kapat-aç sonrası da durur", async () => {
    await kur("tek@klinik.com", []);
    await kartiAcKapa();
    sunucuDurumu.review = 500;
    await reddetVeYaz();
    expect(degerlendirmeler().length).toBe(1); // ARA DOĞRULAMA: istek gitti, sunucu reddetti
    expect(gerekceAlani()?.value).toBe(GEREKCE);
    expect(s.metin()).toContain("Değerlendirme kaydedilemedi — gerekçeniz korunuyor");
    await kartiAcKapa(); // kapat
    await kartiAcKapa(); // aç
    expect(gerekceAlani()?.value).toBe(GEREKCE);
  });

  it("KRİTİK: sunucu 503 sonrası yeniden deneme BAŞARILI olunca form kapanır ve kayıt 'Hekim reddetti' olur", async () => {
    await kur("tek@klinik.com", []);
    await kartiAcKapa();
    sunucuDurumu.review = 503;
    await reddetVeYaz();
    expect(gerekceAlani()?.value).toBe(GEREKCE);
    sunucuDurumu.review = 200;
    await s.tikla("Reddi kaydet");
    await s.bosalt(10);
    expect(gerekceAlani()).toBeNull();
    expect(s.metin()).toContain("Hekim reddetti");
    expect((degerlendirmeler().pop()!.govde as { note?: string }).note).toBe(GEREKCE);
  });
});
