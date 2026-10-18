/**
 * SG.G4-2 / G4-3 / G5 / G6 (sahip gözlemleri 2026-10-13) — AI Hub CANLI KAMERA kipi.
 *
 * G5 "segmentasyonda canlıya geçince saniyede 1 analiz yapmıyor fgs gibi olmuyor": canlı döngü `setInterval(capture, 2500)` ve
 *    HER hatayı sessiz yutuyordu; kurulu üründe segmentasyon kareleri modalite kapısından 422 aldı → ekranda HİÇBİR şey yoktu.
 * G4-2 termal canlıda normal kamera: kapı 422 verince ESKİ teşhis ekranda kalıyordu; "termal kamerayı seçin" denmiyordu.
 * G4-3 "(Doğruluk: %95.3)" — model güveni doğruluk değildir.
 * G6 "fgs de canlı kamera açınca görüntü soluk görünüyor": analiz karesi canlı önizlemenin üstüne `opacity: 0.8` ile biniyordu.
 * GERÇEK: AiHubScreen, VisionModule, CatOrganModule, `utils/canliKare`. Sahte (ekran dışı): fetch, kamera (kare yakalama), bağlamlar.
 */
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async () => null),
  apiPost: jest.fn(async () => null),
  authHeaders: jest.fn(() => ({})),
  platformAlert: jest.fn(),
  platformConfirm: jest.fn(async () => true),
  AI_TIMEOUT_MS: 120000,
  aiHataMesaji: () => "Ağ veya sunucu hatası.",
}));
jest.mock("@/services/config", () => ({ serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api" } }));
jest.mock("@/components/ui/ToastProvider", () => {
  const fn = jest.fn();
  return { useToast: () => ({ showToast: fn }), __toast: fn };
});
jest.mock("@/context/UserModeContext", () => ({
  useUserMode: () => ({ userMode: "veterinarian", hasAiHub: true }),
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "v@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({ useOperator: () => ({ operatorEmail: "v@x.com" }), useOperatorOptional: () => null }));
jest.mock("@/context/EntitlementContext", () => ({ useEntitlement: () => ({ research: true, realtime: true }) }));
jest.mock("@/context/AppNavContext", () => ({
  useAppNav: () => ({ navigate: jest.fn(), selectedPatient: { id: 1, name: "Test Hasta" } }),
}));
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: null, wsConnected: true, aiVisionFresh: false, aiVisionData: null }),
}));
jest.mock("@/components/domain/PatientGate", () => {
  const React = require("react");
  return { PatientGate: ({ children }: any) => React.createElement(React.Fragment, null, children) };
});
// Kamera: kare yakalama yüzeyi (ref) — gerçek cihaz yok.
jest.mock("expo-camera", () => {
  const R = require("react");
  const CameraView = R.forwardRef((_p: unknown, ref: unknown) => {
    R.useImperativeHandle(ref, () => ({ takePictureAsync: async () => ({ uri: "file:///kare.jpg" }) }));
    return null;
  });
  return { CameraView, useCameraPermissions: () => [{ granted: true }, jest.fn()] };
});
jest.mock("expo-audio", () => ({
  useAudioRecorder: () => ({ record: jest.fn(), stop: jest.fn(), uri: null }),
  RecordingPresets: { HIGH_QUALITY: {} },
  setAudioModeAsync: jest.fn(),
  requestRecordingPermissionsAsync: jest.fn(async () => ({ granted: true })),
}));
jest.mock("expo-image-picker", () => ({
  MediaTypeOptions: { Images: "Images" },
  launchImageLibraryAsync: jest.fn(async () => ({ canceled: false, assets: [{ uri: "file:///kedi.jpg" }] })),
  launchCameraAsync: jest.fn(async () => ({ canceled: true })),
}));
jest.mock("expo-image-manipulator", () => ({
  SaveFormat: { JPEG: "jpeg" },
  manipulateAsync: jest.fn(async (uri: string) => ({ uri, base64: "QUJD" })),
}));

import React from "react";
import { StyleSheet } from "react-native";
import { act, fireEvent, render } from "@testing-library/react-native";

import { AiHubScreen } from "@/screens/AiHubScreen";

type Yanit = { ok: boolean; status: number; body: unknown };
let kuyruk: Yanit[];
let fetchMock: jest.Mock;

function yanit(body: unknown, status = 200): Yanit {
  return { ok: status >= 200 && status < 300, status, body };
}

beforeEach(() => {
  jest.useFakeTimers();
  kuyruk = [];
  fetchMock = jest.fn(async () => {
    const y = kuyruk.length > 1 ? kuyruk.shift()! : kuyruk[0];
    return { ok: y.ok, status: y.status, json: async () => y.body };
  });
  (global as any).fetch = fetchMock;
});
afterEach(() => {
  jest.useRealTimers();
});

async function ilerle(ms: number) {
  await act(async () => { jest.advanceTimersByTime(ms); });
  for (let i = 0; i < 12; i++) await act(async () => { await Promise.resolve(); });
}

async function canliAc(modul: RegExp) {
  const u = render(<AiHubScreen />);
  fireEvent.press(u.getAllByLabelText(modul)[0]);
  await act(async () => { fireEvent.press(u.getByRole("button", { name: "Canlı Kamera" })); });
  return u;
}

const SEG_RED = yanit({ detail: "Bu modül renkli fotoğraf bekliyor; yüklenen görüntü boyalı patoloji preparatı (H&E) gibi görünüyor. Yanlış görüntüyle üretilen sonuç yanıltıcı olur — lütfen doğru türde bir görüntü yükleyin." }, 422);
const TERMAL_RED = yanit({ detail: "Bu görüntü termal kamera görüntüsüne benzemiyor (renk paleti / sıcaklık eşlemesi yok). Termal kameradan çekin ya da termal görüntü yükleyin." }, 422);
const TERMAL_HASTA = yanit({
  status: "success", image_base64: "SONKARE_TERMAL", prediction: { label: "Sick", confidence: 0.953 },
  girdi_dogrulama: { durum: "termal_paleti", dogrulandi: true, uyari: null },
});

it("KRİTİK G5: segmentasyon canlıda 422 sessiz YUTULMAZ — son kare durumu nedeniyle görünür", async () => {
  kuyruk = [SEG_RED];
  const u = await canliAc(/^Segmentasyon/);
  await ilerle(1100);
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(String(fetchMock.mock.calls[0][0])).toContain("/ai/vision/segmentation");
  expect(u.getByTestId("canli-durum").props.children).toMatch(/^Son kare analiz edilemedi: Bu modül renkli fotoğraf bekliyor/);
});

it("KRİTİK G5: segmentasyon canlıda kedi yoksa 'bulunamadı' BİLGİ olarak görünür", async () => {
  kuyruk = [yanit({ status: "success", cat_count: 0, image_base64: "SEG" })];
  const u = await canliAc(/^Segmentasyon/);
  await ilerle(1100);
  expect(u.getByTestId("canli-durum").props.children).toBe("Son kare: kedi bulunamadı — kedinin tümü kadraja girsin.");
});

it("KRİTİK G5-3: uyarlamalı döngü — 3,2 sn'de 3 kare (eski sabit 2,5 sn aralıkta 1)", async () => {
  kuyruk = [yanit({ status: "success", cat_count: 1, image_base64: "SEG" })];
  await canliAc(/^Segmentasyon/);
  await ilerle(1100);
  await ilerle(1000);
  await ilerle(1100);
  expect(fetchMock.mock.calls.length).toBeGreaterThanOrEqual(3);
});

it("KRİTİK G4-2: termal canlıda kapı 422 → ESKİ teşhis ekrandan KALKAR, 'termal kamerayı seçin' der", async () => {
  kuyruk = [TERMAL_HASTA, TERMAL_RED];
  const u = await canliAc(/^Termal/);
  await ilerle(1100);
  expect(u.queryByText(/Termal anormallik ·/)).toBeTruthy();
  await ilerle(1100);
  expect(fetchMock).toHaveBeenCalledTimes(2);
  expect(u.queryByText(/Termal anormallik ·/)).toBeNull();
  expect(u.getByTestId("canli-durum").props.children).toMatch(/^Seçili kamera termal görüntü vermiyor — termal kamerayı seçin\./);
});

it("KRİTİK G6: canlı kipte son analiz karesi OPAK, canlı önizleme köşede — yarı saydam bindirme YOK", async () => {
  kuyruk = [TERMAL_HASTA];
  const u = await canliAc(/^Termal/);
  expect(u.getByTestId("canli-onizleme-tam")).toBeTruthy(); // ilk sonuç gelene dek canlı önizleme tam kutu
  await ilerle(1100);
  const kareler = u.UNSAFE_queryAllByType(require("react-native").Image)
    .filter((n: any) => String(n.props?.source?.uri || "").includes("SONKARE_TERMAL"));
  expect(kareler.length).toBeGreaterThan(0);
  for (const k of kareler) {
    const st = StyleSheet.flatten(k.props.style) || {};
    expect(st.opacity === undefined || st.opacity === 1).toBe(true);
  }
  expect(u.getByTestId("canli-onizleme-kose")).toBeTruthy();
  expect(u.getByTestId("canli-son-kare-yasi").props.children.join("")).toMatch(/^Son analiz \d+,\d sn önce$/);
});

it("KRİTİK G4-3: termal sonuç 'Doğruluk' DEMEZ, 'Model güveni' der; girdi doğrulanamadıysa uyarı görünür", async () => {
  kuyruk = [yanit({
    status: "success", image_base64: "X", prediction: { label: "Sick", confidence: 0.953 },
    girdi_dogrulama: { durum: "akromatik", dogrulandi: false, uyari: "Girdi termal olarak doğrulanamadı: görüntü renksiz (gri tonlamalı)." },
  })];
  const u = render(<AiHubScreen />);
  fireEvent.press(u.getAllByLabelText(/^Termal/)[0]);
  await act(async () => { fireEvent.press(u.getByRole("button", { name: "Galeriden Seç" })); });
  await act(async () => { fireEvent.press(u.getByRole("button", { name: "AI Analizini Başlat" })); });
  for (let i = 0; i < 12; i++) await act(async () => { await Promise.resolve(); });
  expect(u.queryByText(/Doğruluk/)).toBeNull();
  expect(u.getByText(/Model güveni: %95\.3 — modelin kendi tahminine güveni; doğruluk değildir/)).toBeTruthy();
  expect(u.getByTestId("termal-girdi-uyarisi")).toBeTruthy();
});

it("KRİTİK G5: kedi organ canlıda 'bulunamadı' BİLGİSİ görünür (eskiden 500 → sessiz)", async () => {
  kuyruk = [yanit({
    status: "success", image_base64: "ORG", n_organs: 0, organs: [], detected: false, bulunamadi: "kedi_bulunamadi",
    bulunamadi_mesaji: "Görüntüde kedi bulunamadı. Kedinin tümü kadraja girsin; ışık iyi ve görüntü net olsun.",
  })];
  const u = await canliAc(/^Kedi Organ/);
  await ilerle(1100);
  expect(u.getByTestId("canli-durum").props.children).toBe("Son kare: Görüntüde kedi bulunamadı. Kedinin tümü kadraja girsin; ışık iyi ve görüntü net olsun.");
  expect(u.getByText(/Kedi bulunamadı/)).toBeTruthy();
});

const YON_NOTU = "Paletin kamera yönünde olduğundan emin olun (soğuk = siyah / mor, sıcak = sarı) — ters palette sonuç tersine dönebilir.";

it("KRİTİK S-SGI.4: 'doğrulandı' termal sonuçta da palet YÖNÜ notu görünür (canlı kipte de); 'doğrulanamadı' uyarısı ÇIKMAZ", async () => {
  kuyruk = [yanit({
    status: "success", image_base64: "SONKARE_TERMAL", prediction: { label: "Sick", confidence: 0.953 },
    girdi_dogrulama: { durum: "termal_paleti", dogrulandi: true, uyari: null, yon_notu: YON_NOTU },
  })];
  const u = await canliAc(/^Termal/);
  await ilerle(1100);
  expect(u.queryByText(/Termal anormallik ·/)).toBeTruthy();
  expect(u.getByTestId("termal-yon-notu").props.children.join("")).toBe(`ⓘ ${YON_NOTU}`);
  expect(u.queryByTestId("termal-girdi-uyarisi")).toBeNull();
});

it("KARŞIT S-SGI.4: notu taşımayan (eski) yanıtta yön notu satırı ÇİZİLMEZ", async () => {
  kuyruk = [TERMAL_HASTA];
  const u = await canliAc(/^Termal/);
  await ilerle(1100);
  expect(u.queryByText(/Termal anormallik ·/)).toBeTruthy();
  expect(u.queryByTestId("termal-yon-notu")).toBeNull();
});
