// Author: mertaygn, cglrgrkn
/**
 * XAI §KALAN A-GRUBU — davranış kilitleri (xai-entegrasyon-plani.md §KALAN-2026-08-26).
 *
 * Kilitlenen davranışlar:
 *  A1) Böbrek CT: "Isı haritası üret" anahtarı isteğe `explain=true` ekler; yanıttaki
 *      xai_image_base64 EigenCAM bölümü olarak görünür (anahtar kapalıyken explain GİTMEZ).
 *  A2) Kedi Organ: mirror_warning + anatomic_consistency.passed===false rozetleri
 *      (⚠️ backend anahtarı "ok" değil "passed" — ölçüldü, validation.py dönüşü).
 *  A3) Petri: kanser kuyusunda "gerekçe: N mavi piksel (eşik ≥30)" satırı; sağlıklıda YOK.
 *  A4) FGS: ölçüm-vs-popülasyon-bandı paneli (fgs_bantlari p5–p95) + bant-dışı işareti;
 *      bantlar yanıtta yoksa panel HİÇ yok (eski backend'e zarif düşüş).
 */
let mockMode = "veterinarian";
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async () => null),
  apiPost: jest.fn(async () => null),
  authHeaders: jest.fn(() => ({})),
  platformAlert: jest.fn(),
  platformConfirm: jest.fn(async () => true),
  AI_TIMEOUT_MS: 120000,
  aiHataMesaji: jest.fn(() => "hata"),
}));
jest.mock("@/services/config", () => ({
  serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api" },
}));
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: jest.fn() }) }));
jest.mock("@/context/UserModeContext", () => ({
  useUserMode: () => ({ userMode: mockMode, hasAiHub: true }),
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "v@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({ useOperator: () => ({ operatorEmail: "v@x.com" }) }));
jest.mock("@/context/EntitlementContext", () => ({ useEntitlement: () => ({ research: true }) }));
// Her test FARKLI hasta id'si → ekranın resetAiCachesForOwner mekanizması modül cache'lerini
// temizler (moduleCache sızıntısı ölçüldü; resetModules React'i kırıyor — KULLANMA).
let mockHastaId = 100;
jest.mock("@/context/AppNavContext", () => ({
  useAppNav: () => ({ navigate: jest.fn(), selectedPatient: { id: mockHastaId, name: `Deney-${mockHastaId}` } }),
}));
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: null, wsConnected: true, aiVisionFresh: false }),
}));
jest.mock("@/components/domain/PatientGate", () => {
  const React = require("react");
  return { PatientGate: ({ children }: any) => React.createElement(React.Fragment, null, children) };
});
jest.mock("expo-camera", () => ({ CameraView: () => null, useCameraPermissions: () => [{ granted: true }, jest.fn()] }));
jest.mock("expo-audio", () => ({
  useAudioRecorder: () => ({ record: jest.fn(), stop: jest.fn(), uri: null }),
  RecordingPresets: { HIGH_QUALITY: {} },
  setAudioModeAsync: jest.fn(),
  requestRecordingPermissionsAsync: jest.fn(async () => ({ granted: true })),
}));
// Foto seçici + küçültücü: native yol image_base64 gönderir (RN fetch file:// okuyamıyor — ölçüldü).
jest.mock("expo-image-picker", () => ({
  launchImageLibraryAsync: jest.fn(async () => ({ canceled: false, assets: [{ uri: "file:///foto.jpg" }] })),
  launchCameraAsync: jest.fn(async () => ({ canceled: false, assets: [{ uri: "file:///foto.jpg" }] })),
  MediaTypeOptions: { Images: "Images" },
}));
jest.mock("expo-image-manipulator", () => ({
  manipulateAsync: jest.fn(async () => ({ uri: "file:///kucuk.jpg", base64: "KUCUK64" })),
  SaveFormat: { JPEG: "jpeg" },
}));

import React from "react";
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";

import { AiHubScreen as Ekran } from "@/screens/AiHubScreen";

function fetchYaniti(govde: any) {
  (global.fetch as jest.Mock).mockResolvedValueOnce({ ok: true, json: async () => govde });
}

/** Modülü aç + galeriden görüntü seç (mock picker) — analiz butonu etkinleşir.
 * ⚠️ SON eşleşme basılır: Kedi Organ foto-rehberi "Galeriden Seç"i KALIN METİN olarak da
 * içeriyor; [0] o metne denk gelip hiçbir şey yapmıyordu (ölçüldü — buton ağaçta sonra). */
async function acVeSec(u: ReturnType<typeof render>, modulEtiketi: string) {
  fireEvent.press(u.getAllByLabelText(modulEtiketi)[0]);
  const adaylar = u.getAllByText("Galeriden Seç");
  await act(async () => { fireEvent.press(adaylar[adaylar.length - 1]); });
}

/** fetch mock'unun SON çağrısındaki FormData parçalarını {ad: değer} olarak döndürür. */
function sonIstekParcalari(): Record<string, string> {
  const calls = (global.fetch as jest.Mock).mock.calls;
  const body = calls[calls.length - 1][1].body;
  const out: Record<string, string> = {};
  // RN FormData getParts(); web polyfill'de entries() — ikisini de destekle.
  const parts = typeof body.getParts === "function" ? body.getParts() : [...body.entries()].map(([k, v]: any) => ({ fieldName: k, string: v }));
  for (const p of parts) out[p.fieldName] = p.string ?? "(dosya)";
  return out;
}

beforeEach(() => {
  mockHastaId += 1; // sahip değişimi → modül cache'leri ekran tarafından temizlenir
  mockMode = "veterinarian";
  global.fetch = jest.fn();
});

const FGS_TAM = {
  status: "success", detected: true, fgs_total: 3, pain_level: "mild", image_base64: "IMG64",
  raw_fgs: {
    action_units: { AU1_Ear_Position: { score: 1 }, AU2_Orbital_Tightening: { score: 0 } },
    // ear_angle bandın ÜSTÜNDE (0.9 > p95=0.8) → "bant dışı"; eye_ratio_avg bant İÇİNDE.
    measurements: { ear_angle: 0.9, eye_ratio_avg: 0.3 },
  },
  fgs_bantlari: { ear_angle: { p5: 0.2, p95: 0.8 }, eye_ratio_avg: { p5: 0.1, p95: 0.5 } },
};

describe("XAI §KALAN A-grubu davranış kilitleri", () => {
  it("A4 KRITIK: FGS ölçüm-band paneli — değer + [p5–p95] + bant-dışı işareti", async () => {
    const u = render(<Ekran />);
    await acVeSec(u, "Yüz Ağrısı (FGS)");
    fetchYaniti(FGS_TAM);
    await act(async () => { fireEvent.press(u.getByText("AI Analizini Başlat")); });

    await waitFor(() => u.getByText("Ölçümler · popülasyon bandı (p5–p95)"));
    // ear_angle: 0.9 > 0.8 → satırında bant-dışı işareti VAR; eye_ratio_avg içeride → YOK
    // (sayım yerine satır-birleşik regex: iç içe Text'ler aynı metni iki düğümde eşletiyor)
    expect(u.getByText(/Kulak açısı[\s\S]*bant dışı/)).toBeTruthy();
    expect(u.getByText(/\[0\.20 – 0\.80\]/)).toBeTruthy();
    expect(u.getByText(/Göz oranı/)).toBeTruthy();
    expect(u.queryByText(/Göz oranı[\s\S]*bant dışı/)).toBeNull();
  });

  it("A4 KARŞIT: eski backend (fgs_bantlari YOK) → panel hiç yok, skor yine görünür", async () => {
    const u = render(<Ekran />);
    await acVeSec(u, "Yüz Ağrısı (FGS)");
    const { fgs_bantlari: _at, ...eski } = FGS_TAM as any;
    fetchYaniti(eski);
    await act(async () => { fireEvent.press(u.getByText("AI Analizini Başlat")); });

    await waitFor(() => u.getByText(/FGS Skoru:/));
    expect(u.queryByText("Ölçümler · popülasyon bandı (p5–p95)")).toBeNull();
  });

  it("A2 KRITIK: Kedi Organ — ayna + anatomik-tutarlılık rozetleri ('passed' anahtarı)", async () => {
    const u = render(<Ekran />);
    await acVeSec(u, "Kedi Organ");
    fetchYaniti({
      status: "success", n_organs: 1, pose_type: "side", pnp_residual_px: 2.1, image_base64: "IMG64",
      organs: [{ name: "heart", coord_cabin_cm: [1, 2, 3], reliability: 0.8 }],
      mirror_warning: true, anatomic_consistency: { passed: false, violations: ["kalp-mide sırası"] },
    });
    await act(async () => { fireEvent.press(u.getByText("Organ Analizini Başlat")); });

    await waitFor(() => u.getByText(/Ayna belirsizliği/));
    expect(u.getByText(/Anatomik tutarlılık uyarısı/)).toBeTruthy();
  });

  it("A2 KARŞIT: uyarı alanları yok/pozitifken rozet YOK (passed:true rozet basmaz)", async () => {
    const u = render(<Ekran />);
    await acVeSec(u, "Kedi Organ");
    fetchYaniti({
      status: "success", n_organs: 1, pose_type: "side", pnp_residual_px: 2.1, image_base64: "IMG64",
      organs: [{ name: "heart", coord_cabin_cm: [1, 2, 3], reliability: 0.8 }],
      mirror_warning: false, anatomic_consistency: { passed: true, violations: [] },
    });
    await act(async () => { fireEvent.press(u.getByText("Organ Analizini Başlat")); });

    await waitFor(() => u.getByText(/organ bulundu/));
    expect(u.queryByText(/Ayna belirsizliği/)).toBeNull();
    expect(u.queryByText(/Anatomik tutarlılık uyarısı/)).toBeNull();
  });

  it("A3 KRITIK: Petri — kanser kuyusunda piksel-gerekçesi satırı; sağlıklıda YOK", async () => {
    mockMode = "researcher";
    const u = render(<Ekran />);
    await acVeSec(u, "Petri Kuyu");
    fetchYaniti({
      status: "success", success: true, n_wells: 2, n_cancer: 1, n_healthy: 1,
      method: "pixel", image_base64: "IMG64",
      wells: [
        { well_id: "W1", label: "cancer", organ_id: 1, centroid_cabin_mm: [1, 2, 3], E_cancer: 0.12, E_healthy: 0.05, area_mm2: 12.5, D: [], n_cancer_pixels: 42 },
        { well_id: "W2", label: "healthy", organ_id: 0, centroid_cabin_mm: [4, 5, 6], E_cancer: 0.02, E_healthy: 0.01, area_mm2: 11.0, D: [], n_cancer_pixels: 3 },
      ],
    });
    await act(async () => { fireEvent.press(u.getByText("Petri Analizini Başlat")); });

    await waitFor(() => u.getByText(/gerekçe: 42 mavi piksel \(eşik ≥30\)/));
    // sağlıklı kuyuda gerekçe satırı OLMAMALI (tek satır var: yalnız W1)
    expect(u.getAllByText(/gerekçe:/)).toHaveLength(1);
  });

  it("A1 KRITIK: Böbrek CT — anahtar açıkken explain=true GİDER, ısı haritası GÖRÜNÜR", async () => {
    mockMode = "researcher";
    const u = render(<Ekran />);
    await acVeSec(u, "Böbrek CT");
    fireEvent.press(u.getByText(/Isı haritası üret \(EigenCAM/));
    fetchYaniti({
      status: "success", n_detections: 1, image_base64: "IMG64", xai_image_base64: "XAI64",
      class_counts: { "Kidney Stone": 1 }, detections: [{ class_name: "Kidney Stone", conf: 0.9, bbox_xyxy: [0, 0, 10, 10] }],
    });
    await act(async () => { fireEvent.press(u.getByText("CT Analizini Başlat")); });

    await waitFor(() => u.getByText(/Isı haritası \(EigenCAM\)/));
    expect(sonIstekParcalari().explain).toBe("true");
  });

  it("A1 KARŞIT: anahtar kapalıyken explain HİÇ GİTMEZ (varsayılan ağır XAI yok)", async () => {
    mockMode = "researcher";
    const u = render(<Ekran />);
    await acVeSec(u, "Böbrek CT");
    fetchYaniti({ status: "success", n_detections: 0, image_base64: "IMG64", class_counts: {}, detections: [] });
    await act(async () => { fireEvent.press(u.getByText("CT Analizini Başlat")); });

    await waitFor(() => u.getByText(/böbrek yapısı tespit edilemedi/));
    expect("explain" in sonIstekParcalari()).toBe(false);
  });
});
