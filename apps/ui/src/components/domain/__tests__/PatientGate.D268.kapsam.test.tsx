// Author: mertaygn, cglrgrkn
/**
 * D2.68 · B-6.12 — PatientGate hasta listesini KVKK kapsam tek kaynağından (`inScope`) süzer.
 * =========================================================================================
 * ÖLÇÜLEN KUSUR (DENETIM-06 g3a/g3b): seçici `/patients`ın TAMAMINI listeliyordu (yalnız arama süzgeci) → ev sahibi
 * başka hekimin/sahibin hayvanını seçip ona AI analizi yazdırabiliyordu (yanlış hastaya yazma; `/ai/log` gövdesinde
 * başkasının `patient_id`'si — ölçüldü).
 *
 * GERÇEK: AuthProvider, UserModeProvider (ev sahibi), OperatorProvider, AppNavProvider, PatientGate, TAM AiHubScreen,
 * apiClient. Sahte yalnız `fetch` (ağ sınırı), Supabase istemcisi, kamera/görsel seçici/ses (cihaz), canlı veri bağlamı
 * (WS) ve toast. Klinik profilleri tüm kliniği seçebilir (A-01/A-28 açık model); ev sahibi HER ZAMAN "benim".
 * ⚠️ Kayıtlı operatörü olan klinikte ev sahibinin kimliği '' → bugünkü `inScope` fail-open; tam kapanış D2.70 (B-6.19).
 */
jest.mock("@/services/supabaseAuth", () => require("../../../context/__tests__/operatorAparati").supabaseSahte("sahip@ev.com"));
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: jest.fn() }) }));
jest.mock("@/context/EntitlementContext", () => ({ useEntitlement: () => ({ research: false }) }));
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: null, wsConnected: true, aiVisionFresh: false }),
}));
jest.mock("expo-camera", () => ({ CameraView: () => null, useCameraPermissions: () => [{ granted: true }, jest.fn()] }));
jest.mock("expo-audio", () => ({
  useAudioRecorder: () => ({ record: jest.fn(), stop: jest.fn(), uri: null }),
  RecordingPresets: { HIGH_QUALITY: {} },
  setAudioModeAsync: jest.fn(),
  requestRecordingPermissionsAsync: jest.fn(async () => ({ granted: true })),
}));
jest.mock("expo-image-picker", () => ({
  MediaTypeOptions: { Images: "Images" },
  launchImageLibraryAsync: jest.fn(async () => ({ canceled: false, assets: [{ uri: "file:///kedi.jpg" }] })),
  launchCameraAsync: jest.fn(),
}));
jest.mock("expo-image-manipulator", () => ({
  SaveFormat: { JPEG: "jpeg" },
  manipulateAsync: jest.fn(async (uri: string) => ({ uri, base64: "QUJD" })),
}));

import React, { useEffect } from "react";
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";
import { AuthProvider } from "@/context/AuthContext";
import { UserModeProvider, useUserMode, type UserMode } from "@/context/UserModeContext";
import { OperatorProvider } from "@/context/OperatorContext";
import { AppNavProvider } from "@/context/AppNavContext";
import { AiHubScreen } from "@/screens/AiHubScreen";
import { sahteSunucu, type Istek } from "../../../context/__tests__/operatorAparati";

const HASTALAR = [
  { id: "p-kendi", name: "Benimki", species: "Kedi", operator_email: "sahip@ev.com" },
  { id: "p-b", name: "BaskasininB", species: "Kedi", operator_email: "dr.b@klinik.com" },
  { id: "p-c", name: "BaskasininC", species: "Kedi", operator_email: "dr.c@klinik.com" },
];
const FGS = { status: "success", detected: true, fgs_total: 1, pain_level: "None", raw_fgs: { action_units: {} },
  action_units: {}, hw_status: "idle", hw_params: {} };

let kayit: Istek[];

function Mod({ mod, children }: { mod: UserMode; children: React.ReactNode }) {
  const { setUserMode, userMode } = useUserMode();
  useEffect(() => { setUserMode(mod); }, [mod, setUserMode]);
  return userMode ? <>{children}</> : null;
}

async function kur(mod: UserMode = "pet_owner") {
  const sunucu = sahteSunucu([], (yol, _g, yontem) => {
    if (yol === "/patients" && yontem === "GET") return [200, { status: "success", data: HASTALAR }];
    if (yol === "/ai/vision/landmark") return [200, FGS];
    if (yol === "/ai/log" && yontem === "POST") return [200, { status: "success", id: 1 }];
    return undefined;
  });
  kayit = sunucu.kayit;
  global.fetch = sunucu.fetchSahte as unknown as typeof fetch;
  const u = render(
    <AuthProvider>
      <UserModeProvider>
        <Mod mod={mod}>
          <OperatorProvider>
            <AppNavProvider navigateTo={jest.fn()}>
              <AiHubScreen />
            </AppNavProvider>
          </OperatorProvider>
        </Mod>
      </UserModeProvider>
    </AuthProvider>,
  );
  await act(async () => {});
  await act(async () => {});
  return u;
}

async function seciciAc(u: ReturnType<typeof render>, etiket: string) {
  await waitFor(() => u.getByLabelText(etiket));
  await act(async () => { fireEvent.press(u.getByLabelText(etiket)); });
  await waitFor(() => expect(kayit.some((k) => k.yol === "/patients")).toBe(true));
  await act(async () => {});
}

async function sec(u: ReturnType<typeof render>, ad: string) {
  await act(async () => { fireEvent.press(u.getByLabelText(`Seç: ${ad}`)); });
  await act(async () => {});
}

async function fgsKaydet(u: ReturnType<typeof render>) {
  if (u.queryAllByText("Galeriden Seç").length === 0) {
    await act(async () => { fireEvent.press(u.getAllByText("Yeni Fotoğraf")[0]); });
  }
  await act(async () => { fireEvent.press(u.getAllByText("Galeriden Seç")[0]); });
  await act(async () => { fireEvent.press(u.getByText("Teşhis Et")); });
  await act(async () => {});
  await act(async () => {});
}

const aiLogKimlikleri = () =>
  kayit.filter((k) => k.yol === "/ai/log" && k.yontem === "POST").map((k) => (k.govde as { patient_id?: string }).patient_id);

describe("D2.68 · B-6.12 — PatientGate kapsam süzgeci", () => {
  it("KRİTİK: ev sahibinin seçicisi YALNIZ kendi hayvanını listeler", async () => {
    const u = await kur("pet_owner");
    await seciciAc(u, "Hayvanınızı seçin");
    expect(u.queryByLabelText("Seç: Benimki")).not.toBeNull();
    expect(u.queryByLabelText("Seç: BaskasininB")).toBeNull();
    expect(u.queryByLabelText("Seç: BaskasininC")).toBeNull();
  });

  it("KRİTİK: ev sahibinin AI kaydı BAŞKASININ hasta kimliğiyle oluşmaz (yanlış hastaya yazma yok)", async () => {
    const u = await kur("pet_owner");
    await seciciAc(u, "Hayvanınızı seçin");
    // Seçici başkasının hayvanını gösteriyorsa (kusur) onu seçip analiz yapar — gövde ölçülür.
    await sec(u, u.queryByLabelText("Seç: BaskasininB") ? "BaskasininB" : "Benimki");
    await fgsKaydet(u);
    const kimlikler = aiLogKimlikleri();
    expect(kimlikler.length).toBeGreaterThan(0); // ARA DOĞRULAMA: gerçek akış /ai/log yazdı
    expect(kimlikler.filter((k) => k !== "p-kendi")).toEqual([]);
  });

  it("KARŞIT (A-01/A-28): veteriner seçicide kliniğin TÜM hastalarını görür", async () => {
    const u = await kur("veterinarian");
    await seciciAc(u, "Hasta seçin");
    for (const h of HASTALAR) expect(u.queryByLabelText(`Seç: ${h.name}`)).not.toBeNull();
  });
});
