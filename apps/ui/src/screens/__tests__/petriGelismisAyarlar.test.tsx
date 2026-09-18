// Author: mertaygn
/**
 * PETRİ GELİŞMİŞ (ARAŞTIRMA) AYARLARI — arayüzden ayarlanabilir 6 parametre + denetim anahtarı.
 *
 * SAHİP TALEBİ (2026-09-09): "3 parametre arayüzden ayarlanabilir olsun. Görüntünün çözünürlüğü
 * fazla, yoloya göre resize ekle." → netleştirme: "Altısı da ayarlanabilir olsun."
 *
 * NE ÖLÇÜLÜYOR (varlık değil UYGULAMA): "panel açılıyor mu" değil, GERÇEKTEN GÖNDERİLEN
 * `FormData` ölçülür. Bu ayrımın bedeli bugün iki kez ödendi:
 *   · scratch modülünde yön arayüzde seçiliyor ama zincirin son halkasına geçmiyordu (çizgiler
 *     yatay çiziliyordu) — "seçici var" testi bunu YAKALAMAZDI.
 *   · Aynı sınıf: alan `formData`ya eklenmezse panel çalışıyor GİBİ görünür, sonuç değişmez.
 *
 * KİLİTLENEN DAVRANIŞLAR
 *  1) Dokunulmamış panel HİÇBİR ayar göndermez → eski davranış bit-bit korunur.
 *  2) Girilen değerler doğru alan adlarıyla gider (backend Form adlarıyla aynı).
 *  3) Türkçe ondalık ("0,05") NOKTAYA çevrilir — çevrilmezse `parseFloat` 0 döner ve SESSİZ
 *     yanlış eşikle analiz koşar (`sayiya_cevir` dersi).
 *  4) Aralık dışı değer İSTEK ATILMADAN reddedilir (kullanıcı sunucu turu beklemez).
 *  5) Denetim anahtarı: AÇIKken hiçbir şey gönderilmez (sunucudaki
 *     PEMF_AI_PLAUSIBILITY_GUARD kaçış kapağı EZİLMEZ), KAPATILINCA `plaus_guard=false` gider.
 *  6) "Varsayılanlara dön" alanları gerçekten boşaltır.
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
jest.mock("@/services/config", () => ({
  serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api" },
}));
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: mockToast }) }));
jest.mock("@/context/UserModeContext", () => ({
  useUserMode: () => ({ userMode: mockMode, hasAiHub: true }),
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "r@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({ useOperator: () => ({ operatorEmail: "r@x.com" }) }));
jest.mock("@/context/EntitlementContext", () => ({ useEntitlement: () => ({ research: true }) }));
let mockHastaId = 500;
jest.mock("@/context/AppNavContext", () => ({
  useAppNav: () => ({ navigate: jest.fn(), selectedPatient: { id: mockHastaId, name: `Petri-${mockHastaId}` } }),
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
jest.mock("expo-document-picker", () => ({ getDocumentAsync: jest.fn(async () => ({ canceled: true })) }));
jest.mock("expo-image-picker", () => ({
  MediaTypeOptions: { Images: "Images" },
  launchImageLibraryAsync: jest.fn(async () => ({
    canceled: false,
    assets: [{ uri: "file:///petri.jpg", base64: "PETRI64", file: null }],
  })),
  launchCameraAsync: jest.fn(async () => ({ canceled: true })),
}));
jest.mock("expo-image-manipulator", () => ({
  SaveFormat: { JPEG: "jpeg" },
  manipulateAsync: jest.fn(async () => ({ uri: "file:///petri-kucuk.jpg", base64: "PETRI64" })),
}));

import React from "react";
import { fireEvent, render, waitFor } from "@testing-library/react-native";

import { AiHubScreen as Ekran } from "@/screens/AiHubScreen";

/** `FormData`nın gerçekten taşıdığı alanlar (RN polyfill `_parts`, jsdom `forEach`). */
function formAlanlari(body: any): Record<string, string> {
  const cikti: Record<string, string> = {};
  const parts = body?._parts;
  if (Array.isArray(parts)) {
    for (const [k, v] of parts) cikti[String(k)] = typeof v === "object" ? "[blob]" : String(v);
    return cikti;
  }
  if (typeof body?.forEach === "function") {
    body.forEach((v: any, k: string) => {
      cikti[k] = typeof v === "object" ? "[blob]" : String(v);
    });
  }
  return cikti;
}

const YANIT = {
  status: "no_detection",
  success: false,
  n_wells: 0,
  n_cancer: 0,
  n_healthy: 0,
  wells: [],
  image_base64: "OUT64",
  yolo_ayar: { conf: 0.05, iou: 0.7, imgsz: 640 },
  resize: {},
  plausibility: {},
};

beforeEach(() => {
  mockHastaId += 1;
  mockMode = "researcher";
  mockToast.mockClear();
  global.fetch = jest.fn(async () => ({ ok: true, json: async () => YANIT })) as any;
});

/** Petri modülünü aç, görüntü seç (analiz düğmesi görüntü olmadan çalışmaz). */
async function petriAc() {
  const u = render(<Ekran />);
  fireEvent.press(u.getAllByLabelText("Petri Kuyu")[0]);
  await waitFor(() => u.getByText("Petri Kuyu Analizi"));
  fireEvent.press(u.getByText("Galeriden Seç"));
  await waitFor(() => expect(u.getByText("Petri Analizini Başlat")).toBeTruthy());
  return u;
}

async function analizEt(u: ReturnType<typeof render>) {
  fireEvent.press(u.getByText("Petri Analizini Başlat"));
  await waitFor(() => expect(global.fetch as jest.Mock).toHaveBeenCalled());
  return formAlanlari((global.fetch as jest.Mock).mock.calls[0][1].body);
}

function paneliAc(u: ReturnType<typeof render>) {
  fireEvent.press(u.getByLabelText("Gelişmiş araştırma ayarları"));
}

describe("Petri gelişmiş (araştırma) ayarları", () => {
  it("KRİTİK: dokunulmamış panel HİÇBİR ayar göndermez (eski davranış korunur)", async () => {
    const u = await petriAc();
    paneliAc(u); // panel açıldı ama hiçbir alana dokunulmadı
    const alanlar = await analizEt(u);
    for (const ad of [
      "yolo_conf", "yolo_iou", "resize_max",
      "plaus_circularity", "plaus_conf", "plaus_area_frac", "plaus_guard",
    ]) {
      expect(alanlar[ad]).toBeUndefined();
    }
  });

  it("KRİTİK: girilen altı değer DOĞRU alan adlarıyla gönderilir", async () => {
    const u = await petriAc();
    paneliAc(u);
    fireEvent.changeText(u.getByLabelText("Tespit güveni (conf)"), "0.05");
    fireEvent.changeText(u.getByLabelText("Örtüşme eşiği (IoU)"), "0.5");
    fireEvent.changeText(u.getByLabelText("Küçültme (uzun kenar, px)"), "960");
    fireEvent.changeText(u.getByLabelText("Denetim: dairesellik ≥"), "0.3");
    fireEvent.changeText(u.getByLabelText("Denetim: güven ≥"), "0.4");
    fireEvent.changeText(u.getByLabelText("Denetim: en büyük tespit ≤"), "0.9");

    const alanlar = await analizEt(u);
    expect(alanlar.yolo_conf).toBe("0.05");
    expect(alanlar.yolo_iou).toBe("0.5");
    expect(alanlar.resize_max).toBe("960");
    expect(alanlar.plaus_circularity).toBe("0.3");
    expect(alanlar.plaus_conf).toBe("0.4");
    expect(alanlar.plaus_area_frac).toBe("0.9");
  });

  it("KRİTİK: Türkçe ondalık '0,05' NOKTAYA çevrilir (yoksa sessizce 0 giderdi)", async () => {
    const u = await petriAc();
    paneliAc(u);
    fireEvent.changeText(u.getByLabelText("Tespit güveni (conf)"), "0,05");
    const alanlar = await analizEt(u);
    expect(alanlar.yolo_conf).toBe("0.05");
  });

  it("KRİTİK: aralık dışı değer İSTEK ATILMADAN reddedilir", async () => {
    const u = await petriAc();
    paneliAc(u);
    fireEvent.changeText(u.getByLabelText("Küçültme (uzun kenar, px)"), "1");
    fireEvent.press(u.getByText("Petri Analizini Başlat"));
    await waitFor(() => expect(mockToast).toHaveBeenCalled());
    expect(global.fetch as jest.Mock).not.toHaveBeenCalled();
    expect(String(mockToast.mock.calls[0][0])).toMatch(/320/);
  });

  it("küçültme 0 = KAPALI, sınır ihlali değil (istek atılır)", async () => {
    const u = await petriAc();
    paneliAc(u);
    fireEvent.changeText(u.getByLabelText("Küçültme (uzun kenar, px)"), "0");
    const alanlar = await analizEt(u);
    expect(alanlar.resize_max).toBe("0");
  });

  it("KRİTİK: denetim AÇIKken plaus_guard GÖNDERİLMEZ (sunucu kaçış kapağı ezilmez)", async () => {
    const u = await petriAc();
    paneliAc(u);
    const alanlar = await analizEt(u);
    expect(alanlar.plaus_guard).toBeUndefined();
  });

  it("KRİTİK: denetim KAPATILINCA plaus_guard=false gönderilir", async () => {
    const u = await petriAc();
    paneliAc(u);
    fireEvent.press(u.getByLabelText("Petri değil denetimi"));
    const alanlar = await analizEt(u);
    expect(alanlar.plaus_guard).toBe("false");
  });

  it("denetim kapatılınca YANILTICI SONUÇ uyarısı görünür", async () => {
    const u = await petriAc();
    paneliAc(u);
    expect(u.queryByText(/Denetim kapalı/)).toBeNull();
    fireEvent.press(u.getByLabelText("Petri değil denetimi"));
    expect(u.getByText(/Denetim kapalı/)).toBeTruthy();
  });

  it("'Varsayılanlara dön' alanları boşaltır ve denetimi geri açar", async () => {
    const u = await petriAc();
    paneliAc(u);
    fireEvent.changeText(u.getByLabelText("Tespit güveni (conf)"), "0.05");
    fireEvent.press(u.getByLabelText("Petri değil denetimi"));
    fireEvent.press(u.getByLabelText("Ayarları varsayılana döndür"));

    const alanlar = await analizEt(u);
    expect(alanlar.yolo_conf).toBeUndefined();
    expect(alanlar.plaus_guard).toBeUndefined();
  });
});
