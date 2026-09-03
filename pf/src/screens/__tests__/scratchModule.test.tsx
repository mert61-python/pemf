// Author: mertaygn, cglrgrkn
/**
 * YARA KAPANMA (SCRATCH) MODÜLÜ — davranış kilitleri (plan: scratch-entegrasyon-plani.md v3 §5-6).
 *
 * Kilitlenen davranışlar:
 *  1) Profil: modül YALNIZ researcher'da görünür (karar 0.2 — fiili gizleme UI'da,
 *     backend kapısı uykuda olduğu için bu satır tek gerçek gizleme katmanıdır).
 *  2) Tek girdi → çoklu görsel: butonlu galeri; buton geçişi sahnedeki görseli değiştirir;
 *     [XAI]/[3'lü] butonları YALNIZ yanıtta alan varsa (zarif düşüş — eski backend'de buton yok).
 *  3) n_cells==0 uyarısı: dejenere sekmeler yok, uyarı metni + [Orijinal] var.
 *  4) Karşılaştır (karar 0.8): iki analizden Δ kapanma kartı.
 */
let mockMode = "researcher";
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async () => null),
  apiPost: jest.fn(async () => null),
  authHeaders: jest.fn(() => ({})),
  platformAlert: jest.fn(),
  platformConfirm: jest.fn(async () => true),
  AI_TIMEOUT_MS: 120000,
}));
jest.mock("@/services/config", () => ({
  serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api" },
}));
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: jest.fn() }) }));
jest.mock("@/context/UserModeContext", () => ({
  useUserMode: () => ({ userMode: mockMode, hasAiHub: true }),
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "r@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({ useOperator: () => ({ operatorEmail: "r@x.com" }) }));
jest.mock("@/context/EntitlementContext", () => ({ useEntitlement: () => ({ research: true }) }));
// Her test FARKLI hasta id'si alır → ekranın KENDİ resetAiCachesForOwner mekanizması
// modül-seviyesi cache'leri temizler (moduleCache testler arası sızıyordu — ölçüldü;
// resetModules çözümü React kopyasını da tazeleyip render'ı kırıyor, KULLANMA).
let mockHastaId = 1;
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
// Dosya seçici: TIF dosyası (native foto seçici TIFF listelemez → DocumentPicker deseni)
let mockDosyaAdi = "CONTROL-0H.tif";
jest.mock("expo-document-picker", () => ({
  getDocumentAsync: jest.fn(async () => ({
    canceled: false,
    assets: [{ uri: `file:///${mockDosyaAdi}`, name: mockDosyaAdi, file: null }],
  })),
}));

import React from "react";
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";

import { AiHubScreen as Ekran } from "@/screens/AiHubScreen";

const TAM_YANIT = {
  status: "success", n_cells: 2085, coverage_ratio: 0.47, score_mean: 0.61,
  scratch_yonu: "dikey", pixel_mm: 0.0016, device: "cuda:0",
  closure: { closure_pct: 29.3, mean_gap_um: 428, max_gap_um: 1278.4, gap_area_mm2: 1.0422 },
  input_image_base64: "GIRDI64", seg_image_base64: "SEG64",
  overlay_image_base64: "OV64", analysis_image_base64: "AN64", closure_image_base64: "CL64",
};

function fetchYaniti(govde: any) {
  (global.fetch as jest.Mock).mockResolvedValueOnce({ ok: true, json: async () => govde });
}

async function moduluAcVeSec(u: ReturnType<typeof render>) {
  fireEvent.press(u.getAllByLabelText("Yara Kapanma (Scratch)")[0]);
  fireEvent.press(u.getByText(/Görüntü seç/));
  await waitFor(() => u.getByText(mockDosyaAdi));
}

beforeEach(() => {
  mockDosyaAdi = "CONTROL-0H.tif";
  mockHastaId += 1;              // sahip değişimi → ekran cache'leri kendisi temizler
  mockMode = "researcher";
  global.fetch = jest.fn();
});

describe("Yara Kapanma (Scratch) modülü", () => {
  it("KRITIK: yalnız researcher profili görür (karar 0.2 — tek gizleme katmanı UI)", () => {
    const u = render(<Ekran />);
    expect(u.getAllByLabelText("Yara Kapanma (Scratch)").length).toBeGreaterThan(0);
    u.unmount();
    mockMode = "veterinarian";
    const v = render(<Ekran />);
    expect(v.queryAllByLabelText("Yara Kapanma (Scratch)")).toHaveLength(0);
  });

  it("KRITIK: tek girdi → metrikler + butonlu galeri; buton sahne görselini değiştirir; XAI butonu alan yokken GİZLİ", async () => {
    const u = render(<Ekran />);
    await moduluAcVeSec(u);
    fetchYaniti(TAM_YANIT);
    await act(async () => { fireEvent.press(u.getByText("Analiz Et")); });

    await waitFor(() => u.getByText("%29.3"));
    expect(u.getByText("2085")).toBeTruthy();               // hücre kartı
    expect(u.getByText(/428/)).toBeTruthy();                 // ort. gap
    // varsayılan sekme: Kapanma (primary endpoint)
    expect(u.getByTestId("sc-stage").props.source.uri).toContain("CL64");
    // butonla geçiş: Analiz → AN64, Orijinal → GIRDI64 (TIF'in tek gösterim yolu)
    fireEvent.press(u.getByText("Analiz"));
    expect(u.getByTestId("sc-stage").props.source.uri).toContain("AN64");
    fireEvent.press(u.getByText("Orijinal"));
    expect(u.getByTestId("sc-stage").props.source.uri).toContain("GIRDI64");
    // XAI alanları yanıtta YOK → butonları da YOK (zarif düşüş: boş sekme basılmaz)
    expect(u.queryByText("XAI")).toBeNull();
    expect(u.queryByText("3'lü panel")).toBeNull();
  });

  it("KRITIK: XAI'li yanıtta [XAI]/[3'lü] butonları belirir; xai_error'da yalnız satır", async () => {
    const u = render(<Ekran />);
    await moduluAcVeSec(u);
    fetchYaniti({ ...TAM_YANIT, xai_image_base64: "XAI64", xai_side_by_side_base64: "P364" });
    await act(async () => { fireEvent.press(u.getByText("Analiz Et")); });
    await waitFor(() => u.getByText("XAI"));
    fireEvent.press(u.getByText("3'lü panel"));
    expect(u.getByTestId("sc-stage").props.source.uri).toContain("P364");

    // xai_error: buton yok, satır var. ⚠️ Button 400ms çift-tık korumalı (ölçüldü:
    // peş peşe programatik basiş yutuluyordu) → ikinci basiştan önce bekle.
    await act(async () => { await new Promise((r) => setTimeout(r, 450)); });
    fetchYaniti({ ...TAM_YANIT, xai_error: "Açıklama üretilemedi" });
    await act(async () => { fireEvent.press(u.getByText("Analiz Et")); });
    await waitFor(() => u.getByText(/Açıklama üretilemedi/));
    expect(u.queryByText("3'lü panel")).toBeNull();
  });

  it("KRITIK (B4): anahtar AÇIK → sahne doğrudan [XAI] ile açılır; istenip gelmeyince uyarı; uyari yolunda uyarı YOK", async () => {
    // Bug: ısı haritası istenip üretilmişken sonuç hep "Kapanma"ya iniyor, [XAI] chip'i iki tık
    // arkada sessiz kalıyordu → operatör "ısı haritası gelmedi" sanıyordu. Ayrıca eski backend
    // (alan da xai_error da yok) tamamen sessizdi. `uyari` (hücre yok) yolunda XAI TASARIM GEREĞİ
    // üretilmez → orada uyarı YANLIŞ olur (doğrulayıcı mutasyonla kanıtladı: `!result.uyari` şart).
    const u = render(<Ekran />);
    await moduluAcVeSec(u);
    fireEvent.press(u.getByText(/Isı haritası üret/));
    fetchYaniti({ ...TAM_YANIT, xai_image_base64: "XAI64", xai_side_by_side_base64: "P364" });
    await act(async () => { fireEvent.press(u.getByText("Analiz Et")); });
    await waitFor(() => u.getByText("XAI"));
    expect(u.getByTestId("sc-stage").props.source.uri).toContain("XAI64"); // sahne XAI ile AÇILDI
    fireEvent.press(u.getAllByText("Kapanma")[1]); // [0]=metrik etiketi, [1]=sekme chip'i
    expect(u.getByTestId("sc-stage").props.source.uri).toContain("CL64");
    // Eski backend: XAI alanı da xai_error da yok → istenip gelmedi uyarısı
    await act(async () => { await new Promise((r) => setTimeout(r, 450)); });
    fetchYaniti({ ...TAM_YANIT });
    await act(async () => { fireEvent.press(u.getByText("Analiz Et")); });
    await waitFor(() => u.getByText(/bu yanıtta gelmedi/));
    // Hücre-yok `uyari` yolu: XAI üretilmez (tasarım) → "gelmedi" uyarısı OLMAMALI
    await act(async () => { await new Promise((r) => setTimeout(r, 450)); });
    fetchYaniti({ status: "success", n_cells: 0, closure: null, uyari: "Hucre tespit edilemedi",
      input_image_base64: "GIRDI64", scratch_yonu: "dikey", pixel_mm: 0.0016, device: "cpu" });
    await act(async () => { fireEvent.press(u.getByText("Analiz Et")); });
    await waitFor(() => u.getByText(/Hucre tespit edilemedi/));
    expect(u.queryByText(/bu yanıtta gelmedi/)).toBeNull();
  });

  it("KRITIK: hücre-yok uyarısı — dejenere sekme YOK, uyarı + Orijinal VAR", async () => {
    const u = render(<Ekran />);
    await moduluAcVeSec(u);
    fetchYaniti({ status: "success", n_cells: 0, closure: null,
      uyari: "Hucre tespit edilemedi — goruntuyu ve objektif secimini kontrol edin.",
      input_image_base64: "GIRDI64", scratch_yonu: "dikey", pixel_mm: 0.0016, device: "cpu" });
    await act(async () => { fireEvent.press(u.getByText("Analiz Et")); });
    await waitFor(() => u.getByText(/kontrol edin/));
    expect(u.queryByText("Kapanma")).toBeNull();
    expect(u.queryByText("Segmentasyon")).toBeNull();
    expect(u.getByText("Orijinal")).toBeTruthy();
    expect(u.getByTestId("sc-stage").props.source.uri).toContain("GIRDI64");
  });

  it("KRITIK: Karşılaştır — iki analizden Δ kapanma (karar 0.8, çalışmanın asıl sorusu)", async () => {
    const u = render(<Ekran />);
    await moduluAcVeSec(u);
    fetchYaniti({ ...TAM_YANIT, closure: { ...TAM_YANIT.closure, closure_pct: 4.3, mean_gap_um: 1053 } });
    await act(async () => { fireEvent.press(u.getByText("Analiz Et")); });
    await waitFor(() => u.getByText("%4.3"));
    // Aynı-etiket yeniden-analizi kaydı GÜNCELLER (ölçüldü: kendisiyle Δ sahtesi) →
    // karşılaştırma FARKLI dosyayla yapılır.
    mockDosyaAdi = "CONTROL-24H.tif";
    fireEvent.press(u.getByText("CONTROL-0H.tif"));
    await waitFor(() => u.getByText("CONTROL-24H.tif"));
    await act(async () => { await new Promise((r) => setTimeout(r, 450)); }); // 400ms çift-tık koruması
    fetchYaniti(TAM_YANIT);
    await act(async () => { fireEvent.press(u.getByText("Analiz Et")); });
    await waitFor(() => u.getByText("%29.3"));

    fireEvent.press(u.getByText(/Karşılaştır/));
    await waitFor(() => u.getByText(/Δ \+25\.0 puan/));
    expect(u.getByText(/1053→428 µm/)).toBeTruthy();
  });
});
