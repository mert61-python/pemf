/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * Y106 (S-B.3) — cihaz ekranındaki "Tümünü Sil" kayıtlı operatörlü klinikte SEÇİLİ operatör ister.
 * ===========================================================================================================================
 * ÖLÇÜLEN KUSUR: Hastalar ekranının "Tümünü Sil"i kimlik sormadan `/patients/delete_all` gönderiyordu — kayıtlı operatörlü klinikte
 * kimse seçili değilken (ya da kilit sonrası) kliniğin tüm hasta defteri kimliksiz siliniyor, iz sahipsiz kalıyordu. Arka uç
 * artık 428 der (tests/test_hasta_TUMUNU_SIL_KIMLIK_ister_Y106.py); arayüz kimliksizken isteği HİÇ göndermez ve operatör
 * seçmesini söyler (onay penceresi bile açılmaz). Seçili hekimle istek onun jetonuyla gider (iz onun adına).
 * KARŞIT: operatörsüz tek hekimli klinik (Kural 2) etkilenmez.
 *
 * GERÇEK: AuthProvider, UserModeProvider (veteriner), OperatorProvider, OperatorSwitcher (PIN + "Oturumu kilitle"), AppNavProvider,
 * PatientScreen, apiClient. Sahte yalnız `fetch` (kaydedici), Supabase istemcisi, toast, `window.confirm` ve cihaz modülleri.
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
import { PatientScreen } from "@/screens/PatientScreen";
import { cipEtiketi, pinleSec, Sahne, sahteSunucu, type Istek, type SahteOperator } from "../../context/__tests__/operatorAparati";

const A = "dr.a@klinik.com";
const IKI_HEKIM: SahteOperator[] = [{ email: A, display_name: "Dr. A" }, { email: "dr.b@klinik.com", display_name: "Dr. B" }];
const SILME_ISTEMI = "Silmek için operatörünüzü seçin";
const HASTALAR = [{ id: "p0", name: "HastaA", species: "Kedi", operator_email: A, created_at: "2026-10-01 10:00:00" }];

function Veteriner({ children }: { children: React.ReactNode }) {
  const { setUserMode, userMode } = useUserMode();
  useEffect(() => { setUserMode("veterinarian"); }, [setUserMode]);
  return userMode ? <>{children}</> : null;
}

let s: Sahne;
let kayit: Istek[];
let onay: jest.SpyInstance;
beforeEach(() => {
  jest.useFakeTimers();
  s = new Sahne();
  onay = jest.spyOn(window, "confirm").mockImplementation(() => true);
});
afterEach(async () => {
  await s.sok();
  onay.mockRestore();
  jest.useRealTimers();
});

async function kur(oturum: string, operatorler: SahteOperator[]) {
  mockOturum.eposta = oturum;
  mockToast.mockClear();
  const sunucu = sahteSunucu(operatorler, (yol, _g, yontem) => {
    if (yontem === "GET" && yol === "/patients") return [200, { status: "success", data: HASTALAR }];
    if (yontem === "POST" && yol === "/patients/delete_all") return [200, { status: "success", deleted: 1 }];
    return undefined;
  });
  kayit = sunucu.kayit;
  global.fetch = sunucu.fetchSahte as unknown as typeof fetch;
  await s.ciz(
    <AuthProvider>
      <UserModeProvider>
        <Veteriner>
          <OperatorProvider>
            <AppNavProvider navigateTo={() => undefined}>
              <OperatorSwitcher />
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

const silmeIstekleri = () => kayit.filter((k) => k.yontem === "POST" && k.yol === "/patients/delete_all");

describe("Y106 — 'Tümünü Sil' kayıtlı operatörlü klinikte seçili operatör ister", () => {
  it("KRİTİK: kimse seçili değilken istek GİTMEZ, onay penceresi açılmaz, operatör seçmesi söylenir", async () => {
    await kur(A, IKI_HEKIM);
    await s.metneTikla("Tümünü Sil");
    await s.bosalt(10);
    expect(silmeIstekleri()).toEqual([]);
    expect(onay).not.toHaveBeenCalled();
    expect(mockToast.mock.calls.map((c) => c[0])).toContain(SILME_ISTEMI);
  });

  it("KRİTİK: 'Oturumu kilitle'den sonra istek GİTMEZ (önceki hekimin jetonuyla da)", async () => {
    await kur(A, IKI_HEKIM);
    await pinleSec(s, "Dr. A");
    await s.bosalt(10);
    await s.tikla(cipEtiketi());
    await s.tikla("Oturumu kilitle");
    await s.bosalt(10);
    await s.metneTikla("Tümünü Sil");
    await s.bosalt(10);
    expect(silmeIstekleri()).toEqual([]);
  });

  it("KARŞIT: seçili hekimle istek onun JETONUYLA gider (iz onun adına)", async () => {
    await kur(A, IKI_HEKIM);
    await pinleSec(s, "Dr. A");
    await s.bosalt(10);
    await s.metneTikla("Tümünü Sil");
    await s.bosalt(10);
    const t = silmeIstekleri();
    expect(t.length).toBe(1);
    expect(t[0].operator).toBe(`JETON-${A}`);
    expect(t[0].govde).toEqual({ confirm: "DELETE_ALL" });
  });

  it("KARŞIT (Kural 2): operatörsüz klinikte istek gider", async () => {
    await kur("tek@klinik.com", []);
    await s.metneTikla("Tümünü Sil");
    await s.bosalt(10);
    expect(silmeIstekleri().length).toBe(1);
  });
});
