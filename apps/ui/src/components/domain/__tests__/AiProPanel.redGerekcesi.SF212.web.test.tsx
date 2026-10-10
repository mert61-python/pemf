/**
 * @jest-environment jsdom
 */
// Author: 2-F incelemesi orkestratörü (E10 aparatından)
/**
 * S-F2-1.2 (2-F incelemesi A1 · Y123 · C2-1.14) arayüz yarısı — AI Pro öneri reddinde sunucu gerekçeyi KAYDEDEMEDİYSE hekim UYARILIR.
 * ===========================================================================================================================
 * KUSUR: onay penceresi "Red gerekçesi (kayda geçer)" diyor; karar tablosu yazılamazsa ret yine 200 dönüyor (doğru — tedavi başlamaz)
 * ama panel yanıtı OKUMUYORDU → hekim gerekçenin kaydedildiğini sanıyordu. Sunucu artık `gerekceKaydedildi: bool` döndürüyor
 * (GERÇEK uç: tests/test_ai_pro_red_GEREKCE_KAYDEDILDI_mi_soyler_SF212.py, arıza GERÇEK SQLite hatası); panel `false`ta uyarır.
 * GERÇEK sağlayıcılar + PatientGate + AiProPanel + AiSpecApprovalModal + apiClient (E10 aparatı). Sahte: fetch, Supabase, toast,
 * canlı veri, kamera, `window.confirm`; `window.alert` gözlenir (web'de `platformAlert`).
 */
jest.mock("react-native", () => jest.requireActual("react-native-web"));
jest.mock("@/services/supabaseAuth", () => {
  const aparat = require("../../../context/__tests__/operatorAparati");
  return aparat.supabaseSahte("dr.a@klinik.com");
});
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: jest.fn() }) }));
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: null, wsConnected: true, aiVisionData: null, aiVisionFresh: false }),
}));
jest.mock("expo-camera", () => {
  const R = require("react");
  return { CameraView: R.forwardRef((_p: unknown, _r: unknown) => null), useCameraPermissions: () => [{ granted: true }, jest.fn()] };
});
jest.mock("react-native-safe-area-context", () => {
  const R = require("react");
  const { View } = require("react-native-web");
  return {
    useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
    SafeAreaProvider: ({ children }: { children?: unknown }) => children,
    SafeAreaView: ({ children, style }: { children?: unknown; style?: unknown }) => R.createElement(View, { style }, children),
  };
});
jest.mock("expo-haptics", () => ({ impactAsync: jest.fn(), notificationAsync: jest.fn(), selectionAsync: jest.fn(),
  ImpactFeedbackStyle: {}, NotificationFeedbackType: {} }));
jest.mock("expo-linear-gradient", () => {
  const R = require("react");
  const { View } = require("react-native-web");
  return { LinearGradient: ({ children, style }: { children?: unknown; style?: unknown }) => R.createElement(View, { style }, children) };
});

import React, { act, useEffect } from "react";
import { AuthProvider } from "@/context/AuthContext";
import { UserModeProvider, useUserMode, type UserMode } from "@/context/UserModeContext";
import { OperatorProvider } from "@/context/OperatorContext";
import { AppNavProvider } from "@/context/AppNavContext";
import { PatientGate } from "@/components/domain/PatientGate";
import { AiProPanel } from "@/components/domain/AiProPanel";
import { Sahne, sahteSunucu, type Istek } from "../../../context/__tests__/operatorAparati";

function Mod({ mod, children }: { mod: UserMode; children: React.ReactNode }) {
  const { setUserMode, userMode } = useUserMode();
  useEffect(() => { setUserMode(mod); }, [mod, setUserMode]);
  return userMode ? <>{children}</> : null;
}

let s: Sahne;
let kayit: Istek[];
let onay: jest.SpyInstance;
let uyari: jest.SpyInstance;
const durum = { localized: false, oneriNo: 0, kaydedildi: true };
beforeEach(() => {
  jest.useFakeTimers();
  s = new Sahne();
  durum.localized = false;
  durum.oneriNo = 0;
  durum.kaydedildi = true;
  uyari = jest.spyOn(window, "alert").mockImplementation(() => undefined);
  onay = jest.spyOn(window, "confirm").mockImplementation(() => true);
});
afterEach(async () => {
  await s.sok();
  onay.mockRestore();
  uyari.mockRestore();
  jest.useRealTimers();
});

async function kur() {
  const sunucu = sahteSunucu([], (yol, govde, yontem) => {
    if (yontem === "GET" && yol === "/patients") {
      return [200, { status: "success", data: [{ id: "u-mia", name: "Mia", operator_email: "dr.a@klinik.com", species: "Kedi" }] }];
    }
    if (yontem === "GET" && yol.startsWith("/ai/pro/status")) return [200, { active: false, localized: durum.localized }];
    if (yontem === "POST" && yol === "/ai/pro/propose") {
      durum.oneriNo += 1;
      return [200, {
        status: "success", proposalId: `p${durum.oneriNo}`, expiresAt: 0, meta: {},
        specs: { organ_id: 2, duration_minutes: 20, coil_ids: [1, 2, 3, 4, 5, 6, 7], D: [0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3],
          P: [0, 0, 0, 0, 0, 0, 0], e_field: 0.07, model: "kedi", patient_id: "u-mia", patient_name: "Mia" },
      }];
    }
    if (yontem === "POST" && yol === "/ai/pro/reject") {
      durum.localized = false; // red → hazırlık biter; yeni deneme yeniden lokalize eder
      return [200, {
        status: "success", proposalId: (govde as { proposal_id?: string })?.proposal_id, gerekceKaydedildi: durum.kaydedildi,
      }];
    }
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
              <PatientGate>
                <AiProPanel patientName="" secilebilirModeller={["kedi"]} kullaniciKipi="veterinarian" />
              </PatientGate>
            </AppNavProvider>
          </OperatorProvider>
        </Mod>
      </UserModeProvider>
    </AuthProvider>,
  );
  await s.tikla("Hasta seçin");
  for (let i = 0; i < 20 && !s.varMi("Seç: Mia"); i++) await s.bosalt();
  await s.tikla("Seç: Mia");
}

/** Başlat → önizleme lokalize eder → öneri OTOMATİK istenir (web akışı). Ürünün çift-tık koruması (400 ms, `Date.now`)
 *  sahte zamanlayıcıyla ilerletilir. */
async function oneriyiAl() {
  await act(async () => { jest.setSystemTime(Date.now() + 1000); });
  await s.tikla("AI Pro otonom seansı başlat");
  durum.localized = true;
  for (let i = 0; i < 4; i++) await s.ilerlet(3000);
}

const redler = () => kayit.filter((i) => i.yontem === "POST" && i.yol === "/ai/pro/reject").map((i) => i.govde as Record<string, unknown>);

const kayitUyarisi = () => uyari.mock.calls.map((c) => String(c[0])).filter((m) => m.startsWith("Gerekçe kaydedilemedi"));

it("KRİTİK S-F2-1.2: sunucu gerekçeyi KAYDEDEMEDİYSE (gerekceKaydedildi=false) hekim UYARILIR; ret yine gönderilir", async () => {
  durum.kaydedildi = false;
  await kur();
  await oneriyiAl();
  await s.tikla("Öneriyi reddet");
  await s.yaz("Red gerekçesi", "duty çok yüksek");
  await s.tikla("Reddi onayla");
  await s.bosalt(5);
  expect(redler()).toEqual([{ proposal_id: "p1", operator_email: "dr.a@klinik.com", reason: "duty çok yüksek" }]);
  expect(kayitUyarisi()).toHaveLength(1);
  expect(kayitUyarisi()[0]).toMatch(/tedavi BAŞLAMADI/);
});

it("KARŞIT S-F2-1.2: gerekçe kaydedildiyse (true) uyarı YOK", async () => {
  await kur();
  await oneriyiAl();
  await s.tikla("Öneriyi reddet");
  await s.yaz("Red gerekçesi", "duty çok yüksek");
  await s.tikla("Reddi onayla");
  await s.bosalt(5);
  expect(redler()).toHaveLength(1);
  expect(kayitUyarisi()).toEqual([]);
});
