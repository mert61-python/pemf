// Author: mertaygn, cglrgrkn
/**
 * ARAŞTIRMA AI PRO (Faz 3) — fantom/petri sihirbazı: kedi ekranı YERİNE ne görünür?
 *
 * Sahip isteği: "araştırma modunda AI Pro'ya fantom ve petriyi kedi YERİNE entegre et; kullanıcı
 * dostu olsun." Bu dosya ekranın sözünü tutup tutmadığını ölçer:
 *   · kedi organ çipleri ve "Hayvan aranıyor" araştırmada GÖRÜNMEZ (karar #13, simetrik gizleme),
 *   · model seçilmeden hiçbir istek gitmez,
 *   · seçilen model TÜM isteklerin gövdesinde taşınır (hazırlık, hedef, öneri),
 *   · hedef kare üstünden VE erişilebilir listeden seçilebilir; ikisi de aynı ucu çağırır,
 *   · kabin işareti görünmezse öneri beklemeden ÖNCE sebep yazılır,
 *   · bayrak kapalıyken kart "Deneysel" der ama önizleme yolu kapanmaz (tezgâh ölçümü için).
 *
 * ⚠️ Platform.OS="web" mock'lanır (IS_WEB import anında hesaplanır → mock ÖNCE olmalı).
 */
jest.mock("react-native", () => {
  const RN = jest.requireActual("react-native");
  RN.Platform.OS = "web";
  return RN;
});
let mockDurum: Record<string, unknown> = { active: false, localized: false };
let mockEnvanter: unknown = {
  moduller: [
    { modul: "em_fantom", hazir: true },
    { modul: "em_petri", hazir: true },
    { modul: "petri_yolo", hazir: true },
  ],
};
let mockOneri: unknown = { proposalId: "p1", specs: {}, meta: {} };
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async (yol: string) => (yol === "/ai/hazirlik" ? mockEnvanter : mockDurum)),
  apiPost: jest.fn(async (yol: string) => (yol === "/ai/pro/propose" ? mockOneri : { status: "success" })),
  authHeaders: jest.fn(() => ({})),
  platformAlert: jest.fn(),
  platformConfirm: jest.fn(async () => true),
  AI_TIMEOUT_MS: 120000,
}));
jest.mock("@/services/config", () => ({
  serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api" },
  getClientInstanceId: jest.fn(async () => "web-id"),
}));
let mockVision: unknown = undefined;
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: null, wsConnected: true, aiVisionData: mockVision, aiVisionFresh: false }),
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "a@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({ useOperator: () => ({ operatorEmail: "a@x.com" }) }));
jest.mock("expo-camera", () => {
  const React2 = require("react");
  return { CameraView: React2.forwardRef(() => null), useCameraPermissions: () => [{ granted: true }, jest.fn()] };
});

import { act, fireEvent, render } from "@testing-library/react-native";
import React from "react";

import { apiGet, apiPost, platformAlert } from "@/services/apiClient";

import { AiProPanel } from "../AiProPanel";

const ARASTIRMA = ["fantom", "petri"] as const;

beforeEach(() => {
  jest.useFakeTimers();
  mockDurum = { active: false, localized: false };
  mockOneri = { proposalId: "p1", specs: {}, meta: {} };
  mockVision = undefined;
  mockEnvanter = {
    moduller: [
      { modul: "em_fantom", hazir: true },
      { modul: "em_petri", hazir: true },
      { modul: "petri_yolo", hazir: true },
    ],
  };
  (apiPost as jest.Mock).mockClear();
  (apiGet as jest.Mock).mockClear();
  (platformAlert as jest.Mock).mockClear();
});
afterEach(() => {
  jest.useRealTimers();
});

function ciz(ekstra: Record<string, unknown> = {}) {
  return render(<AiProPanel patientName="Örnek-1" secilebilirModeller={[...ARASTIRMA]} kullaniciKipi="researcher" {...ekstra} />);
}
async function bekle(u: ReturnType<typeof render>, n = 1) {
  for (let i = 0; i < n; i++) await act(async () => { jest.advanceTimersByTime(3000); await Promise.resolve(); });
  return u;
}
/** Gövdesi kontrol edilecek isteği yolundan bul. */
function govde(yol: string): Record<string, unknown> | undefined {
  const c = (apiPost as jest.Mock).mock.calls.filter((k) => k[0] === yol).pop();
  return c?.[1] as Record<string, unknown> | undefined;
}

it("KRİTİK: araştırmada KEDİ ekranı yok — organ çipleri ve 'Hayvan aranıyor' GÖRÜNMEZ", async () => {
  const u = ciz();
  await act(async () => {});
  expect(u.queryByText("🧠 Hedef Organ")).toBeNull();
  expect(u.queryByLabelText(/Hedef organ: Karaciğer/)).toBeNull();
  expect(u.getByText("🔬 Hedef Modeli")).toBeTruthy();
  expect(u.getByText("Fantom Tümör")).toBeTruthy();
  expect(u.getByText("Petri Kuyu")).toBeTruthy();
  // Hazırlık başlatılınca da kedi şeridi ÇIKMAZ (özne fantomdur).
  await act(async () => { fireEvent.press(u.getByLabelText(/Fantom Tümör/)); });
  await act(async () => { fireEvent.press(u.getByLabelText("AI Pro otonom seansı başlat")); });
  expect(u.queryByText(/Hayvan aranıyor/)).toBeNull();
  expect(u.getByText(/fantom aranıyor/)).toBeTruthy();
});

it("KARŞIT-KANIT: veteriner (varsayılan prop) ekranı BİREBİR — model kartı YOK, organ çipi VAR", async () => {
  const u = render(<AiProPanel patientName="Tekir" />);
  await act(async () => {});
  expect(u.queryByText("🔬 Hedef Modeli")).toBeNull();
  expect(u.getByText("🧠 Hedef Organ")).toBeTruthy();
  // Envanter isteği veteriner ekranında HİÇ atılmaz (gereksiz pahalı tarama).
  expect((apiGet as jest.Mock).mock.calls.some((k: unknown[]) => k[0] === "/ai/hazirlik")).toBe(false);
});

it("KRİTİK: model seçilmeden başlatılamaz — düğme PASİF, sebep GÖRÜNÜR, istek gitmez", async () => {
  const u = ciz();
  await act(async () => {});
  const dugme = u.getByLabelText("AI Pro otonom seansı başlat");
  expect(dugme.props.accessibilityState?.disabled).toBe(true);
  // ⚠️ Sebep yalnız a11y ipucunda kalmamalı: ekran okuyucu kullanmayan operatör "düğme bozuk"
  // sanardı (eylem söyleyen hata kuralı).
  expect(u.getByText("Önce Adım 1'de bir hedef modeli seçin.")).toBeTruthy();
  await act(async () => { fireEvent.press(dugme); });
  expect(govde("/ai/pro/hazirlik/baslat")).toBeUndefined();
  // Model seçilince kapı KALKAR (karşıt kanıt: kapı sabit değil, duruma bağlı).
  await act(async () => { fireEvent.press(u.getByLabelText(/Fantom Tümör/)); });
  expect(u.queryByText("Önce Adım 1'de bir hedef modeli seçin.")).toBeNull();
});

it("KRİTİK: seçilen model hazırlık gövdesinde TAŞINIR (fantom)", async () => {
  const u = ciz();
  await act(async () => {});
  await act(async () => { fireEvent.press(u.getByLabelText(/Fantom Tümör/)); });
  await act(async () => { fireEvent.press(u.getByLabelText("AI Pro otonom seansı başlat")); });
  expect(govde("/ai/pro/hazirlik/baslat")).toMatchObject({ model: "fantom", organ_id: 0 });
});

it("KRİTİK: model DEĞİŞİNCE sonraki öneri YENİ modeli taşır (ref güncel)", async () => {
  const u = ciz();
  await act(async () => {});
  await act(async () => { fireEvent.press(u.getByLabelText(/Petri Kuyu/)); });
  await act(async () => { fireEvent.press(u.getByLabelText("AI Pro otonom seansı başlat")); });
  mockDurum = { active: false, localized: true, method: "aruco_pnp" };
  await bekle(u, 2);
  expect(govde("/ai/pro/propose")).toMatchObject({ model: "petri", client_mode: "researcher" });
});

it("KRİTİK: status targets → kare üstü halkalar VE erişilebilir liste; ikisi de /ai/pro/organ çağırır", async () => {
  const u = ciz();
  await act(async () => {});
  await act(async () => { fireEvent.press(u.getByLabelText(/Fantom Tümör/)); });
  await act(async () => { fireEvent.press(u.getByLabelText("AI Pro otonom seansı başlat")); });
  mockDurum = {
    active: false,
    localized: false,
    method: "aruco_pnp",
    subjectDetected: true,
    targets: [
      { id: 1, label: "Tümör 1", pxn: [0.25, 0.4], reliability: 0.82, secili: true },
      { id: 2, label: "Tümör 2", pxn: [0.7, 0.55], reliability: 0.61 },
    ],
  };
  await bekle(u, 2);
  // Liste (halkaların erişilebilir YEDEĞİ) her hâlde çizilir.
  expect(u.getByLabelText(/Hedef 2 \/ 2: Tümör 2, güven yüzde 61/)).toBeTruthy();
  expect(u.queryByTestId("hedef-halka-2")).toBeNull();   // kutu ölçülmeden halka çizilmez
  // ⚠️ Halkalar kutu ÖLÇÜLÜNCE çizilir: onLayout gelmeden `kutu` null'dur.
  await act(async () => {
    fireEvent(u.getByTestId("ai-pro-kamera-kutusu"), "layout", {
      nativeEvent: { layout: { width: 400, height: 300 } },
    });
  });
  const h1 = u.getByTestId("hedef-halka-1");
  const h2 = u.getByTestId("hedef-halka-2");
  const yer = (el: { props: { style: unknown } }) => {
    const st = el.props.style;
    const d = Array.isArray(st) ? Object.assign({}, ...st.filter(Boolean)) : (st as Record<string, number>);
    return { left: d.left as number, top: d.top as number };
  };
  // ⚠️ KONUM `pxn` (kare oranı) ile hesaplanmalı: ham `px` kullanılsaydı bu değerler NaN olurdu
  // (alan yok) ya da kutu dışına düşerdi — halkalar hedeften kayardı.
  expect(Number.isFinite(yer(h1).left)).toBe(true);
  expect(Number.isFinite(yer(h2).left)).toBe(true);
  expect(yer(h2).left).toBeGreaterThan(yer(h1).left);
  expect(yer(h2).top).toBeGreaterThan(yer(h1).top);
  // Kare ÜSTÜNDEN seçim de listeyle AYNI ucu çağırır (iki yol ayrışamaz).
  await act(async () => { fireEvent.press(h2); });
  expect(govde("/ai/pro/organ")).toMatchObject({ organ_id: 2, model: "fantom" });
  (apiPost as jest.Mock).mockClear();
  await act(async () => { fireEvent.press(u.getByTestId("hedef-satir-1")); });
  expect(govde("/ai/pro/organ")).toMatchObject({ organ_id: 1, model: "fantom" });
});

it("KRİTİK: kabin işareti yoksa (method pixel) SEBEP peşinen yazılır", async () => {
  const u = ciz();
  await act(async () => {});
  await act(async () => { fireEvent.press(u.getByLabelText(/Fantom Tümör/)); });
  await act(async () => { fireEvent.press(u.getByLabelText("AI Pro otonom seansı başlat")); });
  mockDurum = { active: false, localized: false, method: "pixel", subjectDetected: true, targets: [{ id: 1, label: "Tümör 1", pxn: [0.5, 0.5], reliability: 0.2 }] };
  await bekle(u, 2);
  expect(u.getAllByText(/kabin işareti/).length).toBeGreaterThanOrEqual(1);
  expect(u.queryByText(/kabin işaretiyle doğrulandı/)).toBeNull();
});

it("KRİTİK: bayrak KAPALI → 'Deneysel' rozeti + önizleme yolu KAPANMAZ (tezgâh ölçümü)", async () => {
  mockDurum = { active: false, localized: false, arastirmaAiProAcik: false };
  const u = ciz();
  await act(async () => {});
  await bekle(u);
  expect(u.getAllByText(/Deneysel/).length).toBeGreaterThanOrEqual(1);
  await act(async () => { fireEvent.press(u.getByLabelText(/Fantom Tümör/)); });
  await act(async () => { fireEvent.press(u.getByLabelText("AI Pro otonom seansı başlat")); });
  expect(govde("/ai/pro/hazirlik/baslat")).toMatchObject({ model: "fantom" });
});

it("KRİTİK: model paketi eksikse kart PASİF ve sebebi yazılı", async () => {
  mockEnvanter = { moduller: [{ modul: "em_fantom", hazir: true }, { modul: "em_petri", hazir: true }, { modul: "petri_yolo", hazir: false }] };
  const u = ciz();
  await act(async () => {});
  await bekle(u);
  expect(u.getByText(/Araştırma model paketi bu cihazda kurulu değil/)).toBeTruthy();
  const petri = u.getByLabelText(/Petri Kuyu/);
  expect(petri.props.accessibilityState?.disabled).toBe(true);
  await act(async () => { fireEvent.press(petri); });
  await act(async () => { fireEvent.press(u.getByLabelText("AI Pro otonom seansı başlat")); });
  expect(govde("/ai/pro/hazirlik/baslat")).toBeUndefined();   // seçilemedi → başlatılamaz
});

it("KRİTİK: seans sürerken model DEĞİŞTİRİLEMEZ (kart kilitli + sebep)", async () => {
  mockDurum = { active: true, localized: true, model: "fantom", method: "aruco_pnp" };
  const u = ciz();
  await act(async () => {});
  await bekle(u);
  expect(u.getByText(/Seans\/hazırlık sürerken model değiştirilemez/)).toBeTruthy();
  const kart = u.getByLabelText(/Petri Kuyu/);
  expect(kart.props.accessibilityState?.disabled).toBe(true);
});

it("KRİTİK: sihirbaz adımı ve Geri — Geri sunucu önizlemesini BIRAKIR", async () => {
  const u = ciz();
  await act(async () => {});
  expect(u.getByLabelText("Adım 1 / 5: Model")).toBeTruthy();
  await act(async () => { fireEvent.press(u.getByLabelText(/Fantom Tümör/)); });
  expect(u.getByLabelText("Adım 2 / 5: Kamera")).toBeTruthy();
  await act(async () => { fireEvent.press(u.getByLabelText("AI Pro otonom seansı başlat")); });
  await act(async () => { fireEvent.press(u.getByLabelText(/Geri: önceki adıma dön/)); });
  expect((apiPost as jest.Mock).mock.calls.some((k) => k[0] === "/ai/pro/hazirlik/durdur")).toBe(true);
});
