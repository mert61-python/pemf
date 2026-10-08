/**
 * @jest-environment jsdom
 */
// Author: A1 (2-C inceleme)
/**
 * C2-1.13 — D2.E10 u3 "EŞDEĞER" iddiası YANLIŞ: açık onay penceresinin üstüne DOĞRUDAN yeni öneri gelebilen yol VAR.
 * 2-C (DUZELTME-D2C.md:254): "öneri yalnız hazırlıkta ve `oneriIstendiRef` korumasıyla istenir … yeni öneriden önce `proposal` her
 * yolda null'a döner → `var/yok` anahtarı da her öneride yeni örnek kurar". Ölçülen yol: p1 isteği ASKIDAYKEN hekim "Yeniden
 * konumla"ya basar (`relocalize` `oneriIstendiRef`i sıfırlar, hazırlık sürer) → p2 istenir; p1 gelir (pencere açılır, hekim red
 * formunu açıp gerekçe yazar), sonra p2 gelir → `setProposal(p2)` AÇIK pencerenin üstüne. Öneri kimliği anahtarı (HEAD) p2'yi
 * TEMİZ açar; `var/yok` anahtarı (u3) aynı örneği korur → p2 RED FORMUNDA ve p1'in gerekçesiyle görünür (tek dokunuş p2'yi p1'in
 * gerekçesiyle reddeder — İG-6.27'nin kusuru). GERÇEK sağlayıcılar + PatientGate + AiProPanel + AiSpecApprovalModal + apiClient.
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
const durum = { localized: false, oneriNo: 0 };
beforeEach(() => {
  jest.useFakeTimers();
  s = new Sahne();
  durum.localized = false;
  durum.oneriNo = 0;
  onay = jest.spyOn(window, "confirm").mockImplementation(() => true);
});
afterEach(async () => {
  await s.sok();
  onay.mockRestore();
  jest.useRealTimers();
});

type Ask = { coz: (v: unknown) => void };
const askidakiOneriler: Ask[] = [];

async function kurAskili() {
  const sunucu = sahteSunucu([], (yol, govde, yontem) => {
    if (yontem === "GET" && yol === "/patients") {
      return [200, { status: "success", data: [{ id: "u-mia", name: "Mia", operator_email: "dr.a@klinik.com", species: "Kedi" }] }];
    }
    if (yontem === "GET" && yol.startsWith("/ai/pro/status")) return [200, { active: false, localized: durum.localized }];
    if (yontem === "POST" && yol === "/ai/pro/reject") {
      return [200, { status: "success", proposalId: (govde as { proposal_id?: string })?.proposal_id }];
    }
    return undefined;
  });
  kayit = sunucu.kayit;
  const yanit = (veri: unknown) => ({ ok: true, status: 200, text: async () => JSON.stringify(veri), json: async () => veri,
    headers: { get: () => "application/json" } });
  global.fetch = (async (url: unknown, init: { method?: string; body?: unknown } = {}) => {
    const yol = String(url).replace(/^[a-z]+:\/\/[^/]+/i, "").replace(/^\/api/, "");
    if ((init.method || "GET") === "POST" && yol === "/ai/pro/propose") {
      await sunucu.fetchSahte(url, init as never); // kayda girsin
      durum.oneriNo += 1;
      const no = durum.oneriNo;
      const veri = { status: "success", proposalId: `p${no}`, expiresAt: 0, meta: {},
        specs: { organ_id: 2, duration_minutes: 20, coil_ids: [1, 2, 3, 4, 5, 6, 7], D: [0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3],
          P: [0, 0, 0, 0, 0, 0, 0], e_field: 0.07, model: "kedi", patient_id: "u-mia", patient_name: "Mia" } };
      return new Promise((coz) => askidakiOneriler.push({ coz: () => coz(yanit(veri)) }));
    }
    return sunucu.fetchSahte(url, init as never);
  }) as unknown as typeof fetch;
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

it("KRİTİK C2-1.13: p1 ASKIDAYKEN 'Yeniden konumla' → p2; p1'in red formu açıkken p2 gelir → p2 TEMİZ açılır", async () => {
  askidakiOneriler.length = 0;
  await kurAskili();
  await act(async () => { jest.setSystemTime(Date.now() + 1000); });
  await s.tikla("AI Pro otonom seansı başlat");
  durum.localized = true;
  for (let i = 0; i < 4 && askidakiOneriler.length < 1; i++) await s.ilerlet(3000);
  expect(askidakiOneriler.length).toBe(1); // ARA: p1 istendi, askıda
  const relok = s.varMi("Hedef organ konumlandırıldı, yeniden konumla")
    ? "Hedef organ konumlandırıldı, yeniden konumla" : "Hedef organı yeniden konumla";
  await s.tikla(relok);
  durum.localized = false; // sunucu yeniden konumlarken önizleme "konumlandı" değil (calibrate)
  await s.ilerlet(3000);
  durum.localized = true;
  for (let i = 0; i < 6 && askidakiOneriler.length < 2; i++) await s.ilerlet(3000);
  expect(askidakiOneriler.length).toBe(2); // ARA: p2 de istendi (p1 hâlâ askıda)
  await act(async () => { askidakiOneriler[0].coz(null); });
  await s.bosalt(10);
  expect(s.varMi("AI seans önerisi onay penceresi")).toBe(true); // ARA: p1 penceresi açık
  await s.tikla("Öneriyi reddet");
  await s.yaz("Red gerekçesi", "P1-GEREKCESI");
  await act(async () => { askidakiOneriler[1].coz(null); });
  await s.bosalt(10);
  expect(s.varMi("AI seans önerisi onay penceresi")).toBe(true);
  expect(s.varMi("Red gerekçesi")).toBe(false);
  expect(s.varMi("Öneriyi onayla ve seansı başlat")).toBe(true);
});
