/**
 * @jest-environment jsdom
 * @jest-environment-options {"url": "http://192.168.1.50:8000/"}
 */
// Author: mertaygn, cglrgrkn
/**
 * Y112 (S-B2.4) — AI Geçmişi "Tüm Klinik" silmesi CİHAZ DIŞINDAN (LAN / telefon / tünel) yalnız KENDİ + SAHİPSİZ kayıtları siler
 * (backend: tests/test_ai_gecmisi_TUM_KLINIK_silme_kapsami_Y112.py); başka hekimlerinki dahil TAMAMI yalnız cihazın kendi
 * ekranından. Arayüz onay penceresi bunu SÖYLEMELİ: cihaz dışında "Kliniğin TÜM AI analiz geçmişi silinecek" demek yanlıştır
 * (operatör yapılmayacak bir silmeye onay verir ya da başka hekimlerin kayıtlarının gittiğini sanır).
 * Bu dosya sayfayı LAN adresinden açar (`@jest-environment-options` url — gerçek `window.location`; cihazın kendisi
 * `isDesktopHost()` = loopback host). KARŞIT (cihazın kendisi, localhost): aiTumKlinikSilme.Y112.cihaz.web.test.tsx.
 *
 * GERÇEK: AuthProvider, UserModeProvider, OperatorProvider, OperatorSwitcher (PIN), AppNavProvider, AiHistoryScreen, apiClient.
 * Sahte yalnız `fetch` (kaydedici), Supabase istemcisi, toast, `window.confirm` ve cihaz modülleri.
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
const IKI_HEKIM: SahteOperator[] = [{ email: A, display_name: "Dr. A" }, { email: "dr.b@klinik.com", display_name: "Dr. B" }];

function Mod({ children }: { children: React.ReactNode }) {
  const { setUserMode, userMode } = useUserMode();
  useEffect(() => { setUserMode("veterinarian"); }, [setUserMode]);
  return userMode ? <>{children}</> : null;
}

let s: Sahne;
let kayit: Istek[];
let onaylar: string[];
beforeEach(() => {
  jest.useFakeTimers();
  s = new Sahne();
  onaylar = [];
  jest.spyOn(window, "confirm").mockImplementation((m?: string) => { onaylar.push(String(m)); return true; });
});
afterEach(async () => {
  await s.sok();
  (window.confirm as jest.Mock).mockRestore?.();
  jest.useRealTimers();
});

async function kurAi(s_: Sahne, oturum: string, operatorler: SahteOperator[]) {
  mockOturum.eposta = oturum;
  const analizler = [A, "dr.b@klinik.com", ""].map((e, i) => ({
    id: 300 + i, created_at: "2026-10-01 10:00:00", mode: "veterinarian", module_id: `m${i}`, module_label: `Mod${i}`,
    patient_name: "Ortak", input_type: "image", result_summary: `Ozet${i}`, result_detail: {}, confidence: 0.9, operator_email: e,
  }));
  const sunucu = sahteSunucu(operatorler, (yol, _g, yontem) => {
    if (yontem === "GET" && yol.startsWith("/ai/log")) return [200, { status: "success", data: yol.includes("before_id") ? [] : analizler }];
    if (yontem === "POST" && yol === "/ai/log/delete_all") return [200, { status: "success", deleted: 2 }];
    return undefined;
  });
  global.fetch = sunucu.fetchSahte as unknown as typeof fetch;
  await s_.ciz(
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
  await s_.ilerlet(50);
  await s_.bosalt(10);
  return sunucu.kayit;
}

describe("Y112 — cihaz DIŞINDAN 'Tüm Klinik' AI silmesi", () => {
  it("ARAÇ KANITI: sayfa LAN adresinden açık (cihazın kendisi DEĞİL)", () => {
    expect(window.location.hostname).toBe("192.168.1.50");
  });

  it("KRİTİK: onay penceresi 'kendi ve sahipsiz' der, 'Kliniğin TÜM' DEMEZ; istek yine 'Tüm Klinik' niyetiyle gider", async () => {
    kayit = await kurAi(s, A, IKI_HEKIM);
    await pinleSec(s, "Dr. A");
    await s.bosalt(10);
    await s.tikla("Tüm klinik analizleri");
    await s.tikla("Kliniğin tüm AI analiz geçmişini sil");
    await s.bosalt(10);
    expect(onaylar.length).toBe(1);
    expect(onaylar[0]).toContain("Kendi ve sahipsiz AI analiz kayıtlarınız");
    expect(onaylar[0]).toContain("yalnız cihazın kendi ekranından");
    expect(onaylar[0]).not.toContain("Kliniğin TÜM AI analiz geçmişi");
    const t = kayit.filter((k) => k.yontem === "POST" && k.yol === "/ai/log/delete_all");
    expect(t.length).toBe(1);
    expect(t[0].govde).toMatchObject({ confirm: "DELETE_ALL", all_operators: true });
    expect(t[0].operator).toBe(`JETON-${A}`);
  });

  it("KARŞIT (Kural 2): operatörsüz klinikte cihaz dışından da 'Kliniğin TÜM' der (kayıtlı başka hekim yok — kapsam fiilen tamamı)", async () => {
    kayit = await kurAi(s, "tek@klinik.com", []);
    await s.tikla("Tüm klinik analizleri");
    await s.tikla("Kliniğin tüm AI analiz geçmişini sil");
    await s.bosalt(10);
    expect(onaylar.join("\n")).toContain("Kliniğin TÜM AI analiz geçmişi");
  });
});
