// Author: mertaygn, cglrgrkn
/**
 * AII-3.10 (AI incelemesi A3, 2026-10-12) — petri formunun gizli alan / "Varsayılanlara dön" yolları (AI-2 C5 kapısı bu yolları ölçmüyordu).
 *
 * Ölçülen (bca9e544): `PemfKapisiKutusu` başlığı yalnız `pemf_gecerli`ye bakıyor. Kabin çerçevesi geçerli AMA engelleyici uyarı
 * (fantom `layout_mismatch`, petri `control_cancer_missed`) varken kutu kırmızı çerçeveli ve "D / P / E değerleri bobin sürüşüne
 * ESAS ALINMAZ" + "sonuç kullanılamaz" diyor; başlık ise YEŞİL "✔ PEMF girdisi geçerli" (fantomda ayrıca "✔ tespit güvenilir").
 * Göz ilk satırı okur → çelişkili hüküm. Kapı: sürülemez sonuçta başlık "✔ … geçerli" demez ve hükmü söyler.
 * K4 sondaları (uçta YEŞİL beklenir): kısmi alanlı (eski GPU imajı) yanıtta "geçerli" uydurulmaz; plaka kipinde 422 yönlendirmesi
 * görünür ve kip değişince `plate_type=0` gider; gizli alanın eski değeri kip değişimi / "Varsayılanlara dön" / yeniden açılışta SIZMAZ.
 */
let mockMode = "researcher";
const mockToast = jest.fn();
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async () => null),
  apiPost: jest.fn(async () => null),
  authHeaders: jest.fn(() => ({})),
  platformAlert: jest.fn(),
  platformConfirm: jest.fn(async () => true),
  AI_TIMEOUT_MS: 120000,
  aiHataMesaji: jest.fn(() => "hata"),
}));
jest.mock("@/services/config", () => ({ serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api" } }));
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: mockToast }) }));
jest.mock("@/context/UserModeContext", () => ({ useUserMode: () => ({ userMode: mockMode, hasAiHub: true }) }));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "r@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({ useOperator: () => ({ operatorEmail: "r@x.com" }) }));
jest.mock("@/context/EntitlementContext", () => ({ useEntitlement: () => ({ research: true }) }));
let mockHastaId = 3900;
jest.mock("@/context/AppNavContext", () => ({
  useAppNav: () => ({ navigate: jest.fn(), selectedPatient: { id: mockHastaId, name: `AII39-${mockHastaId}` } }),
}));
jest.mock("@/context/LiveDataContext", () => ({ useLiveData: () => ({ snapshot: null, wsConnected: true, aiVisionFresh: false }) }));
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
jest.mock("expo-document-picker", () => ({ getDocumentAsync: jest.fn(async () => ({ canceled: true })) }));
jest.mock("expo-image-picker", () => ({
  MediaTypeOptions: { Images: "Images" },
  launchImageLibraryAsync: jest.fn(async () => ({ canceled: false, assets: [{ uri: "file:///g.jpg", base64: "G64", file: null }] })),
  launchCameraAsync: jest.fn(async () => ({ canceled: true })),
}));
jest.mock("expo-image-manipulator", () => ({
  SaveFormat: { JPEG: "jpeg" },
  manipulateAsync: jest.fn(async () => ({ uri: "file:///g-kucuk.jpg", base64: "G64" })),
}));

import React from "react";
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";

import { AiHubScreen as Ekran } from "@/screens/AiHubScreen";

function formAlanlari(body: any): Record<string, string> {
  const cikti: Record<string, string> = {};
  const parts = body?._parts;
  if (Array.isArray(parts)) {
    for (const [k, v] of parts) cikti[String(k)] = typeof v === "object" ? "[blob]" : String(v);
    return cikti;
  }
  if (typeof body?.forEach === "function") body.forEach((v: any, k: string) => { cikti[k] = typeof v === "object" ? "[blob]" : String(v); });
  return cikti;
}
function sonForm(): Record<string, string> {
  const c = (global.fetch as jest.Mock).mock.calls;
  return formAlanlari(c[c.length - 1][1].body);
}

const LAYOUT = "Tümör yerleşimi referansla uyuşmuyor (yanlış tespit ya da farklı fantom) — sonuç kullanılamaz; doğru fantomu kadraja alın.";
const KONTROL = "Boyalı (kanser) kontrol kuyucuğu kanser sınıflanmadı — bu plakada eşikler güvenilmez, sonuç kullanılamaz.";
const kuyu = (id: string, label = "healthy") => ({
  well_id: id, label, organ_id: label === "cancer" ? 1 : 0, centroid_cabin_mm: [19.3, 0, 0], D: [0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3],
  E_cancer: 0.1, E_healthy: 0.1, area_mm2: 150, cancer_reasons: [],
});
const FANTOM_ENGELLI = {
  status: "success", success: true, method: "coil_ring", mm_per_px: 0.31, n_tumor: 1, n_healthy: 0, healthy_regions: [],
  tumor_regions: [{ tumor_id: "T1", centroid_cabin_mm: [-43.6, -15, -9.2], D: [0.4, 0.4, 0.4, 0.4, 0.4, 0.4, 0.4], E_cancer: 0.005, E_healthy: 0.004, area_mm2: 316 }],
  image_base64: "OUT64", pemf_valid: true, reliable: true, warnings: ["layout_mismatch: x"],
  pemf_kapisi: { surulebilir: false, pemf_gecerli: true, nedenler: ["layout_mismatch"], eylem: LAYOUT,
    mesajlar: [{ kod: "layout_mismatch", metin: LAYOUT }], varsayimlar: [] },
};
const PETRI_ENGELLI = {
  status: "success", success: true, method: "plate_grid", mm_per_px: 0.118, n_wells: 2, n_cancer: 0, n_healthy: 2,
  wells: [kuyu("A1"), kuyu("B2")], image_base64: "OUT64", yolo_ayar: { conf: 0.6, iou: 0.7 }, resize: {}, plausibility: { kip: "plaka" },
  pemf_valid: true, warnings: ["control_cancer_missed: B2"],
  pemf_kapisi: { surulebilir: false, pemf_gecerli: true, nedenler: ["control_cancer_missed"], eylem: KONTROL,
    mesajlar: [{ kod: "control_cancer_missed", metin: KONTROL }], varsayimlar: [] },
};
const PETRI_SURULEBILIR = { ...PETRI_ENGELLI, warnings: [], pemf_kapisi: { surulebilir: true, pemf_gecerli: true, nedenler: [], eylem: "", mesajlar: [], varsayimlar: [] } };
const PETRI_KISMI_ESKI_GPU = { ...PETRI_ENGELLI, pemf_valid: false, warnings: [], pemf_kapisi: undefined };

let mockYanit: any = PETRI_ENGELLI;
beforeEach(() => {
  mockHastaId += 1;
  mockMode = "researcher";
  mockToast.mockClear();
  global.fetch = jest.fn(async () => ({ ok: true, json: async () => mockYanit })) as any;
});

async function modulAc(etiket: string, baslik: string, dugme: string) {
  const u = render(<Ekran />);
  fireEvent.press(u.getAllByLabelText(etiket)[0]);
  await waitFor(() => u.getByText(baslik));
  await act(async () => { fireEvent.press(u.getByText("Galeriden Seç")); });
  await waitFor(() => expect(u.getByText(dugme)).toBeTruthy());
  return u;
}
async function analizEt(u: ReturnType<typeof render>, dugme: string) {
  // düğme etiketi yalnız yükleme BİTTİĞİNDE görünür ("Analiz Ediliyor..." değil) — art arda analizde aparat yarışını önler
  await waitFor(() => u.getByText(dugme));
  const once = (global.fetch as jest.Mock).mock.calls.length;
  await act(async () => { fireEvent.press(u.getByText(dugme)); });
  await waitFor(() => expect((global.fetch as jest.Mock).mock.calls.length).toBeGreaterThan(once));
  const form = sonForm();
  await waitFor(() => u.getByText(dugme));
  return form;
}

describe("K4 sondaları (uçta yeşil beklenir)", () => {
  it("SONDA eski GPU imajı (pemf_valid=false, pemf_kapisi YOK) → kutu yok, 'geçerli' uydurulmaz, kart çökmez", async () => {
    mockYanit = PETRI_KISMI_ESKI_GPU;
    const u = await modulAc("Petri Kuyu", "Petri Kuyu Analizi", "Petri Analizini Başlat");
    await analizEt(u, "Petri Analizini Başlat");
    await waitFor(() => u.getByText(/Kuyu:/));
    expect(u.queryByTestId("pemf-kapisi")).toBeNull();
    expect(u.queryByText(/girdisi geçerli/)).toBeNull();
  });

  it("SONDA plaka kipinde 422 'Tekil petri kapları' yönlendirmesi görünür; kip değişince plate_type=0 gider", async () => {
    const u = await modulAc("Petri Kuyu", "Petri Kuyu Analizi", "Petri Analizini Başlat");
    const RED = "Bu modül 24 kuyucuklu petri plakası fotoğrafı bekliyor; yüklenen görüntüde plaka ızgarası doğrulanamadı (ölçülen: ızgarayı doğrulayan kuyucuk adayı 0 — beklenen ≥2; ince hizalama başarısız). … tekil petri kapları için 'Tekil petri kapları' kipini seçin.";
    (global.fetch as jest.Mock).mockImplementationOnce(async () => ({ ok: false, json: async () => ({ detail: RED }) }));
    const f1 = await analizEt(u, "Petri Analizini Başlat");
    expect(f1.plate_type).toBeUndefined();
    await waitFor(() => expect(mockToast).toHaveBeenCalled());
    expect(String(mockToast.mock.calls[mockToast.mock.calls.length - 1][0])).toContain("'Tekil petri kapları' kipini seçin");
    // yönlendirmenin söylediği seçici AYNI ekranda erişilebilir ve seçilebilir (tekil kipte plate_type=0 gittiği SONDA (b)'de ölçülür)
    const radyo = u.getByLabelText("Tekil petri kapları");
    expect(radyo.props.accessibilityRole).toBe("radio");
    expect(radyo.props.accessibilityState?.selected).toBe(false);
    fireEvent.press(radyo);
    await waitFor(() => expect(u.getByLabelText("Tekil petri kapları").props.accessibilityState?.selected).toBe(true));
    expect(u.getByLabelText("Petri çapı (cm)")).toBeTruthy();
  });

  it("SONDA gizli alan SIZMAZ (a): tekil kipte conf + çap girilip plakaya dönülünce GİTMEZ", async () => {
    mockYanit = PETRI_SURULEBILIR;
    const u = await modulAc("Petri Kuyu", "Petri Kuyu Analizi", "Petri Analizini Başlat");
    fireEvent.press(u.getByLabelText("Tekil petri kapları"));
    fireEvent.press(u.getByLabelText("Gelişmiş araştırma ayarları"));
    fireEvent.changeText(u.getByLabelText("Tespit güveni (conf)"), "0,05");
    fireEvent.changeText(u.getByLabelText("Petri çapı (cm)"), "8");
    fireEvent.press(u.getByLabelText("24 kuyucuklu plaka"));
    const f1 = await analizEt(u, "Petri Analizini Başlat");
    expect(f1.yolo_conf).toBeUndefined();
    expect(f1.petri_diameter_cm).toBeUndefined();
    expect(f1.plate_type).toBeUndefined();
  });

  it("SONDA gizli alan SIZMAZ (b): plaka kipinde kontroller + A1 köşesi 'Varsayılanlara dön' sonrası (AYNI kipte) GİTMEZ", async () => {
    mockYanit = PETRI_SURULEBILIR;
    const u = await modulAc("Petri Kuyu", "Petri Kuyu Analizi", "Petri Analizini Başlat");
    fireEvent.press(u.getByLabelText("Gelişmiş araştırma ayarları"));
    fireEvent.changeText(u.getByLabelText("Sağlıklı kontrol kuyucukları"), "A1");
    fireEvent.changeText(u.getByLabelText("Boyalı kontrol kuyucukları"), "B2");
    fireEvent.press(u.getByLabelText("A1 köşesi sağ-alt"));
    fireEvent.press(u.getByLabelText("Ayarları varsayılana döndür"));
    const f = await analizEt(u, "Petri Analizini Başlat");
    expect(f.control_healthy).toBeUndefined();
    expect(f.control_cancer).toBeUndefined();
    expect(f.a1_corner).toBeUndefined();
  });

  it("SONDA gizli alan SIZMAZ (b2): tekil kipe geçince plaka kontrolleri GİTMEZ, plate_type=0 gider", async () => {
    mockYanit = PETRI_SURULEBILIR;
    const u = await modulAc("Petri Kuyu", "Petri Kuyu Analizi", "Petri Analizini Başlat");
    fireEvent.press(u.getByLabelText("Gelişmiş araştırma ayarları"));
    fireEvent.changeText(u.getByLabelText("Boyalı kontrol kuyucukları"), "B2");
    fireEvent.press(u.getByLabelText("Tekil petri kapları"));
    const f = await analizEt(u, "Petri Analizini Başlat");
    expect(f.control_cancer).toBeUndefined();
    expect(f.plate_type).toBe("0");
  });

  it("SONDA gizli alan SIZMAZ (c): ekran kapatılıp açılınca eski kontrol / eşik GİTMEZ, kip varsayılana döner", async () => {
    mockYanit = PETRI_SURULEBILIR;
    const u = await modulAc("Petri Kuyu", "Petri Kuyu Analizi", "Petri Analizini Başlat");
    fireEvent.press(u.getByLabelText("Gelişmiş araştırma ayarları"));
    fireEvent.changeText(u.getByLabelText("Boyalı kontrol kuyucukları"), "B2");
    fireEvent.press(u.getByLabelText("Tekil petri kapları"));
    fireEvent.changeText(u.getByLabelText("Tespit güveni (conf)"), "0,05");
    u.unmount();
    const u2 = await modulAc("Petri Kuyu", "Petri Kuyu Analizi", "Petri Analizini Başlat");
    const f = await analizEt(u2, "Petri Analizini Başlat");
    expect(f.control_cancer).toBeUndefined();
    expect(f.yolo_conf).toBeUndefined();
    expect(f.plate_type).toBeUndefined();
  });
});
