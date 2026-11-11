/**
 * KP-4 B1 · src/components/domain/AiProPanel.tsx (yerel / telefon) — OTONOM HAZIRLIK akışının kalan kolları.
 *  1) Kamera izni REDDEDİLİRSE hazırlık başlamaz: `/ai/pro/calibrate` GİTMEZ, kare akmaz, düğme yeniden basılabilir kalır.
 *  2) Öneri ALINAMAZSA hazırlıkta KALINIR, şerit "yeniden denenecek" der; 5 sn dolmadan yeni kareler öneriyi yeniden İSTEMEZ (fırtına
 *     yok), süre dolunca sonraki doğrulanmış karede yeniden istenir ve gelince onay penceresi açılır.
 *  3) HAZIRLIK TAVANI (120 sn): hayvan hiç bulunamazsa hazırlık kendiliğinden biter, operatör uyarılır, kare akışı durur (telefonda
 *     sunucu önizlemesi yok → `/hazirlik/durdur` gönderilmez).
 *  4) Onay penceresini KAPATMAK reddetmek DEĞİLDİR: pencere kapanır, `/approve` · `/reject` · `/start` gönderilmez.
 *  5) Hazırlıkta telefon kamerası ön ↔ arka çevrilebilir.
 *  6) Kare isteği ASILI kalırsa 15 sn sonra İPTAL edilir; o sürede yeni kare çekilmez (üst üste istek yok), iptalden sonra akış sürer.
 *  7) Cihaz API anahtarı tanımlıysa kare isteği onu `X-API-Key` başlığıyla taşır.
 * GERÇEK: AiProPanel, AiSpecApprovalModal, apiClient (platformAlert → RN Alert), korunanFetch, config (istemci kimliği).
 * SAHTE (en alt kat): fetch, kamera (kare yakalama + izin), RN `Alert.alert` (gözlemci), sahte saat; bağlamlar sabit girdi.
 */
let mockIzin: { granted: boolean } = { granted: true };
const mockIzinIste = jest.fn();
const mockFoto = jest.fn();
let mockFacing: string | undefined;
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: null, wsConnected: true, aiVisionData: null, aiVisionFresh: false }),
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "v@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({ useOperator: () => ({ operatorEmail: "v@x.com" }) }));
jest.mock("expo-camera", () => {
  const R = require("react");
  return {
    CameraView: R.forwardRef((p: { facing?: string }, ref: unknown) => {
      mockFacing = p.facing;
      R.useImperativeHandle(ref, () => ({ takePictureAsync: mockFoto }));
      return null;
    }),
    useCameraPermissions: () => [mockIzin, mockIzinIste],
  };
});

import React from "react";
import { Alert } from "react-native";
import { act, fireEvent, render, type RenderResult } from "@testing-library/react-native";
import i18n from "i18next";

import { serviceConfig } from "@/services/config";
import { AiProPanel } from "../AiProPanel";

const T = (k: string, o?: object): string => (i18n.t as unknown as (k: string, o?: object) => string)(k, o);

type Yanit = [number, unknown];
let oneriYanitlari: Yanit[];
let kare: Record<string, unknown>;
let fetchSahte: jest.Mock;
let uyari: jest.SpyInstance;
let kareAsili = false;

const ONERI = {
  proposalId: "p-kp4", expiresAt: 0, meta: {},
  specs: { organ_id: 0, duration_minutes: 20, coil_ids: [1, 2, 3, 4, 5, 6, 7], D: [1, 1, 1, 1, 1, 1, 1], P: [0, 0, 0, 0, 0, 0, 0], e_field: 0.07 },
};

function yolu(url: unknown): string {
  return String(url).replace(/^[a-z]+:\/\/[^/]+/i, "").replace(/^\/api/, "");
}
const postlar = (yol: string) =>
  fetchSahte.mock.calls.filter((c) => yolu(c[0]) === yol && (c[1] as { method?: string } | undefined)?.method === "POST");

beforeEach(() => {
  jest.useFakeTimers();
  mockIzin = { granted: true };
  mockIzinIste.mockReset().mockResolvedValue({ granted: true });
  mockFoto.mockReset().mockResolvedValue({ base64: "QUFBQQ==" });
  mockFacing = undefined;
  oneriYanitlari = [[200, ONERI]];
  kare = { status: "success", detected: true, catDetected: true, reliability: 0.9 };
  uyari = jest.spyOn(Alert, "alert").mockImplementation(() => undefined);
  uyari.mockClear();
  kareAsili = false;
  fetchSahte = jest.fn(async (url: unknown, init: { signal?: AbortSignal } = {}) => {
    const yol = yolu(url);
    if (kareAsili && yol === "/ai/ai_pro/frame") {
      // Asılı istek: yalnız istemcinin İPTALİ (AbortController) bitirir — gerçek fetch gibi AbortError ile düşer.
      return new Promise((_coz, reddet) => {
        init.signal?.addEventListener("abort", () => reddet(Object.assign(new Error("aborted"), { name: "AbortError" })));
      });
    }
    let y: Yanit = [200, { status: "success" }];
    if (yol === "/ai/pro/status") y = [200, { active: false }];
    else if (yol === "/ai/ai_pro/frame") y = [200, kare];
    else if (yol === "/ai/pro/propose") y = oneriYanitlari.length > 1 ? oneriYanitlari.shift()! : oneriYanitlari[0];
    // Gerçek ağ gibi her yanıt YENİ nesne (aynı başvuru React durumunu değiştirmez — ürün kare kimliğine dayanır).
    return { ok: y[0] < 400, status: y[0], json: async () => JSON.parse(JSON.stringify(y[1])), text: async () => JSON.stringify(y[1]),
      headers: { get: () => "application/json" } };
  });
  (global as unknown as { fetch: unknown }).fetch = fetchSahte;
});
afterEach(() => {
  uyari.mockRestore();
  jest.useRealTimers();
});

async function bosalt(n = 40) {
  for (let i = 0; i < n; i++) await act(async () => { await Promise.resolve(); });
}
async function ilerle(ms: number) {
  await act(async () => { jest.advanceTimersByTime(ms); });
  await bosalt();
}
async function panel(): Promise<RenderResult> {
  const u = render(<AiProPanel patientName="Tekir" />);
  await bosalt();
  return u;
}
async function baslat(u: RenderResult) {
  await act(async () => { fireEvent.press(u.getByLabelText(T("ai.pro.dugme.baslatEtiket"))); });
  await bosalt();
}
const hazirlikMetni = (u: RenderResult) => String(u.getByTestId("aipro-hazirlik-metni-metin").props.children);

it("KRİTİK: kamera izni reddedilirse hazırlık BAŞLAMAZ — /calibrate gitmez, kare akmaz, düğme yeniden basılabilir", async () => {
  mockIzin = { granted: false };
  mockIzinIste.mockResolvedValue({ granted: false });
  const u = await panel();
  await baslat(u);
  expect(mockIzinIste).toHaveBeenCalledTimes(1);
  expect(postlar("/ai/pro/calibrate")).toHaveLength(0);
  expect(u.queryByTestId("aipro-hazirlik-metni")).toBeNull();
  const dugme = u.getByLabelText(T("ai.pro.dugme.baslatEtiket"));
  expect(dugme.props.accessibilityState).toEqual(expect.objectContaining({ busy: false, disabled: false }));
  await ilerle(5000);
  expect(mockFoto).not.toHaveBeenCalled();
});

it("KARŞIT: izin VERİLİRSE hazırlık başlar (/calibrate + kare akışı)", async () => {
  mockIzin = { granted: false };
  mockIzinIste.mockResolvedValue({ granted: true });
  const u = await panel();
  await baslat(u);
  expect(postlar("/ai/pro/calibrate")).toHaveLength(1);
  expect(u.getByTestId("aipro-hazirlik-metni")).toBeTruthy();
});

it("KRİTİK: öneri alınamazsa hazırlıkta kalınır ('yeniden denenecek'); 5 sn dolmadan yeniden İSTENMEZ, sonra istenir ve pencere açılır", async () => {
  oneriYanitlari = [[422, { detail: "Bu konum için sürülebilir parametre yok." }], [200, ONERI]];
  const u = await panel();
  await baslat(u);
  await ilerle(1500); // kare 1 (doğrulanıyor 1/2)
  await ilerle(1500); // kare 2 → öneri isteği (başarısız)
  expect(postlar("/ai/pro/propose")).toHaveLength(1);
  expect(hazirlikMetni(u)).toBe(T("ai.pro.hata.oneriDenenecek"));
  await ilerle(1500);
  await ilerle(1500);
  await ilerle(1500); // +4,5 sn: yeni doğrulanmış kareler geldi ama bekleme sürüyor
  expect(postlar("/ai/pro/propose")).toHaveLength(1);
  expect(u.queryByLabelText(T("ai.pro.onay.onaylaEtiket"))).toBeNull();
  await ilerle(1500); // +6 sn: bekleme bitti → sonraki karede yeniden istenir
  expect(postlar("/ai/pro/propose")).toHaveLength(2);
  expect(u.queryByTestId("aipro-hazirlik-metni")).toBeNull(); // öneri geldi → hazırlık bitti
});

it("KRİTİK: hazırlık TAVANI (120 sn) — hayvan bulunamazsa hazırlık biter, operatör uyarılır, kare akışı durur, sunucuya durdur gitmez", async () => {
  kare = { status: "success", detected: false, catDetected: false };
  const u = await panel();
  await baslat(u);
  for (let i = 0; i < 119; i++) await ilerle(1000);
  expect(u.getByTestId("aipro-hazirlik-metni")).toBeTruthy();
  expect(uyari).not.toHaveBeenCalled();
  await ilerle(1000);
  expect(uyari).toHaveBeenCalledWith(T("ai.pro.uyari.konumlandirmaTamamlanamadi"), T("ai.pro.uyari.konumlandirmaTamamlanamadiGovde"));
  expect(u.queryByTestId("aipro-hazirlik-metni")).toBeNull();
  expect(postlar("/ai/pro/hazirlik/durdur")).toHaveLength(0);
  expect(postlar("/ai/pro/propose")).toHaveLength(0);
  const kareSayisi = mockFoto.mock.calls.length;
  await ilerle(6000);
  expect(mockFoto.mock.calls.length).toBe(kareSayisi);
});

it("KRİTİK: onay penceresini KAPATMAK reddetmek değildir — pencere kapanır, /approve /reject /start GİTMEZ", async () => {
  const u = await panel();
  await baslat(u);
  await ilerle(1500);
  await ilerle(1500);
  expect(postlar("/ai/pro/propose")).toHaveLength(1);
  expect(u.getByLabelText(T("ai.pro.onay.onaylaEtiket"))).toBeTruthy();
  await act(async () => { fireEvent.press(u.getByLabelText(T("ortak.kapat"))); });
  await bosalt();
  expect(u.queryByLabelText(T("ai.pro.onay.onaylaEtiket"))).toBeNull();
  for (const yol of ["/ai/pro/approve", "/ai/pro/reject", "/ai/pro/start"]) expect(postlar(yol)).toHaveLength(0);
});

it("hazırlıkta telefon kamerası ön ↔ arka çevrilir", async () => {
  kare = { status: "success", detected: false, catDetected: true };
  const u = await panel();
  await baslat(u);
  expect(mockFacing).toBe("back");
  await act(async () => { fireEvent.press(u.getByLabelText(T("ai.pro.kamera.cevirEtiketi"))); });
  expect(mockFacing).toBe("front");
  await act(async () => { fireEvent.press(u.getByLabelText(T("ai.pro.kamera.cevirEtiketi"))); });
  expect(mockFacing).toBe("back");
});

it("KRİTİK: asılı kare isteği 15 sn sonra İPTAL edilir; o sürede üst üste kare çekilmez, iptalden sonra akış sürer", async () => {
  kareAsili = true;
  kare = { status: "success", detected: false, catDetected: true };
  const u = await panel();
  await baslat(u);
  await ilerle(1500); // kare 1 → istek asılı
  const kareIstekleri = () => fetchSahte.mock.calls.filter((c) => yolu(c[0]) === "/ai/ai_pro/frame");
  expect(kareIstekleri()).toHaveLength(1);
  const sinyal = (kareIstekleri()[0][1] as { signal: AbortSignal }).signal;
  for (let i = 0; i < 9; i++) await ilerle(1500); // +13,5 sn (toplam 15 sn): istek uçuşta → yeni kare YOK
  expect(sinyal.aborted).toBe(false);
  expect(mockFoto).toHaveBeenCalledTimes(1);
  kareAsili = false;
  await ilerle(1500); // 15 sn doldu → iptal; sonraki tur yeni kare çeker
  expect(sinyal.aborted).toBe(true);
  await ilerle(1500);
  expect(mockFoto.mock.calls.length).toBeGreaterThanOrEqual(2);
  expect(kareIstekleri().length).toBeGreaterThanOrEqual(2);
  expect(u.getByTestId("aipro-hazirlik-metni")).toBeTruthy(); // hazırlık sürüyor
});

it("cihaz API anahtarı tanımlıysa kare isteği X-API-Key taşır; anahtar yokken başlık yok", async () => {
  const eski = serviceConfig.apiToken;
  try {
    (serviceConfig as { apiToken?: string | null }).apiToken = "";
    const u0 = await panel();
    await baslat(u0);
    await ilerle(1500);
    const anahtarsiz = fetchSahte.mock.calls.find((c) => yolu(c[0]) === "/ai/ai_pro/frame")!;
    expect((anahtarsiz[1] as { headers: Record<string, string> }).headers["X-API-Key"]).toBeUndefined();
    u0.unmount();
    fetchSahte.mockClear();
    (serviceConfig as { apiToken?: string | null }).apiToken = "cihaz-anahtari";
    const u = await panel();
    await baslat(u);
    await ilerle(1500);
    const ilk = fetchSahte.mock.calls.find((c) => yolu(c[0]) === "/ai/ai_pro/frame")!;
    expect((ilk[1] as { headers: Record<string, string> }).headers["X-API-Key"]).toBe("cihaz-anahtari");
  } finally {
    (serviceConfig as { apiToken?: string | null }).apiToken = eski;
  }
});
