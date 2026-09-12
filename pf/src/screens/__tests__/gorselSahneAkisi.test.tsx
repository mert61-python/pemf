// Author: mertaygn
/**
 * GÖRSEL SAHNE — GERÇEK EKRAN AKIŞI.  [AI Hub planı, ADIM 4 / G1, G3, G5, G7]
 * ==========================================================================
 * SAHİBİN 2026-09-09 BİLDİRİMİ, iki madde:
 *  1. "girdi kayboluyor" — sonuç gelince kullanıcının fotoğrafı ekrandan siliniyordu.
 *  2. "sonuç küçük ve yazıları okunmaz geliyor" — gösterilen tek şey 2×3 mozaikti.
 *
 * ⚠️ BU DOSYA BİRİM DEĞİL AKIŞ ÖLÇER: `sahneSayfalari()` kusursuz çalışırken ekranın onu
 * ÇAĞIRMAMASI mümkündür ve birim testleri YEŞİL kalırdı. Burada gerçek modül açılır, görüntü
 * seçilir, analiz koşturulur ve EKRANDAKİ düğümler okunur.
 *
 * ⚠️ Harness `petriGelismisAyarlar.test.tsx` ile AYNI (mock listesi birebir). İlk yazımda
 * mock'lar elle kopyalanmıştı ve analiz düğmesi sessizce çalışmıyordu — çalışan harness'tan
 * türetmek, "testin kendi kurulumunu ölçmesi" turunu bitirdi.
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

const P = (k: string, ad: string, w: number, h: number) => ({ k, ad, image_base64: 'B64_' + k, image_w: w, image_h: h });

/** ADIM 3 sozlesmesine uygun 7 panelli petri yaniti. */
const YANIT = {
  status: 'success', success: true, n_wells: 2, n_cancer: 1, n_healthy: 1, wells: [],
  image_base64: 'B64_07_combined', image_w: 1600, image_h: 1067,
  paneller: [
    P('01_input', 'Girdi', 640, 480),
    P('02_yolo_dets', 'Tespit', 800, 600),
    P('03_yolo_masks', 'Maske', 320, 240),
    P('04_classify', 'Siniflama', 400, 400),
    P('05_local_coords', 'Koordinat', 500, 500),
    P('06_predictions', 'Tahmin', 1200, 400),
    P('07_combined', 'Birlesik', 1600, 1067),
  ],
  yolo_ayar: {}, resize: {}, plausibility: {},
};

/** Eski backend / panelsiz modul yaniti (G5). */
const PANELSIZ: any = { ...YANIT, paneller: undefined };
let aktifYanit: any = YANIT;

beforeEach(() => {
  mockHastaId += 1;
  mockMode = "researcher";
  mockToast.mockClear();
  aktifYanit = YANIT;
  global.fetch = jest.fn(async () => ({ ok: true, json: async () => aktifYanit })) as any;
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


/** Petri modülünü aç, görüntü seç, analiz et, sahneyi ölç. */
async function akis() {
  const u = render(<Ekran />);
  fireEvent.press(u.getAllByLabelText("Petri Kuyu")[0]);
  await waitFor(() => u.getByText("Petri Kuyu Analizi"));
  fireEvent.press(u.getByText("Galeriden Seç"));
  // ⚠️ "Başlat" düğmesini beklemek GERÇEK BİR BEKLEME DEĞİL: düğme görüntü seçilmeden de
  // render ediliyor (yalnız `disabled`). Foto seçimi async (`shrinkForUpload`) olduğu için
  // düğmeye imageUri set olmadan basılıyor ve analiz SESSİZCE hiç başlamıyordu. Sahnenin
  // kendisi yalnız imageUri varken çizilir → doğru bekleme çıpası odur.
  await waitFor(() => expect(u.queryByTestId("petri-sahne")).toBeTruthy());
  fireEvent.press(u.getByText("Petri Analizini Başlat"));
  await waitFor(() => expect(global.fetch as jest.Mock).toHaveBeenCalled());
  await waitFor(() => expect(u.queryByTestId("petri-sahne-sayac")).toBeTruthy());
  // ⚠️ Oran kilidi dalı `onLayout` olmadan HİÇ koşmaz (sahte-yeşil kaynağı) — genişliği
  // testin KENDİSİ verir. Plan turunda ölçüldü: bugüne dek hiçbir test onLayout ateşlemiyordu.
  fireEvent(u.getByTestId("petri-sahne").children[0] as never, "layout", {
    nativeEvent: { layout: { width: 900, height: 400 } },
  });
  return u;
}

const sayacMetni = (u: ReturnType<typeof render>) =>
  ([] as any[]).concat(u.getByTestId("petri-sahne-sayac").props.children).join("");

describe("Görsel sahne — ekran akışı", () => {
  it("KRİTİK: sonuç gelince GİRDİ çipi durur ve YEREL dosyayı gösterir", async () => {
    // ⚠️ Sahibin 1. şikâyeti. Eski kod sonucu görünce girdiyi siliyordu; fantom/petri'de
    // `image_base64` `no_detection` yolunda da geldiği için girdi dalı ASLA çalışmıyordu.
    //
    // MUTASYON: `sahneSayfalari(result, imageUri)` → `sahneSayfalari(result, null)` → KIRMIZI.
    const u = await akis();
    fireEvent.press(u.getByTestId("petri-sahne-cip-01_input"));
    expect(u.getByTestId("petri-sahne-gorsel-sahne").props.source.uri).toBe("file:///petri-kucuk.jpg");
  });

  it("KRİTİK: YEDİ panelin hepsi çip olarak yayında", async () => {
    // ⚠️ Sahibin 2. şikâyeti: 6 panel üretilip aynı satırda çöpe atılıyordu.
    const u = await akis();
    for (const k of ["01_input", "02_yolo_dets", "03_yolo_masks", "04_classify", "05_local_coords", "06_predictions", "07_combined"]) {
      expect(u.getByTestId(`petri-sahne-cip-${k}`)).toBeTruthy();
    }
    expect(sayacMetni(u)).toContain("/7");
  });

  it("KRİTİK: varsayılan sayfa OKUNMAZ MOZAİK değil", async () => {
    // ⚠️ BİLİNÇLİ KARAR (plan §8): mozaiği varsayılan yapmak, düzeltilmeye çalışılan şikâyetin
    // ilk bakışta AYNEN sürmesi demekti.
    const u = await akis();
    expect(sayacMetni(u)).toContain("Tahmin");
    expect(sayacMetni(u)).toContain("6/7");
  });

  it("KRİTİK: çip/ok gezinmesi EK AĞ ÇAĞRISI üretmez", async () => {
    // ⚠️ Paneller TEK yanıtta geliyor. Tembel bir panel ucu hem auth-muaf bir yüzey ekler
    // hem de her çip basışında istek atardı (plan bunu bilerek reddetti).
    const u = await akis();
    const oncesi = (global.fetch as jest.Mock).mock.calls.length;
    fireEvent.press(u.getByTestId("petri-sahne-cip-01_input"));
    fireEvent.press(u.getByTestId("petri-sahne-cip-07_combined"));
    fireEvent.press(u.getByTestId("petri-sahne-onceki"));
    expect((global.fetch as jest.Mock).mock.calls.length).toBe(oncesi);
  });

  it("KRİTİK: backend panel göndermezse İKİ sayfa — çökme ve yanıltıcı uyarı YOK", async () => {
    // ⚠️ YENİ İSTEMCİ + ESKİ BACKEND: normalizasyon olmasaydı galeri BOŞ kalırdı.
    aktifYanit = PANELSIZ;
    const u = await akis();
    expect(sayacMetni(u)).toContain("/2");
    expect(u.getByTestId("petri-sahne-cip-01_input")).toBeTruthy();
    expect(u.getByTestId("petri-sahne-gorsel-sahne").props.source.uri).not.toContain("undefined");
    expect(mockToast).not.toHaveBeenCalled();
  });

  it("KRİTİK: görüntü seçilmeden sahne çizilmez, yer tutucu gösterilir", async () => {
    const u = render(<Ekran />);
    fireEvent.press(u.getAllByLabelText("Petri Kuyu")[0]);
    await waitFor(() => u.getByText("Petri Kuyu Analizi"));
    expect(u.queryByTestId("petri-sahne-kutu")).toBeNull();
    expect(u.getByText("Görüntü seçilmedi")).toBeTruthy();
  });

  it("KRİTİK: galeri YALNIZ analiz panellerini taşır, XAI ısı haritasını DEĞİL", async () => {
    // ⚠️ Isı haritası KENDİ bloğunda kalır: galeri sayfasına taşınsaydı hem `xaiKalanA` (A1)
    // hem `xaiIsiHaritasiBoyut` (XAI64'lü <Image> == 1) kapıları kırılırdı.
    const u = await akis();
    expect(u.getAllByTestId(/^petri-sahne-cip-/)).toHaveLength(7);
  });
});
