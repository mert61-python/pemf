/**
 * KP-4 B1 · src/components/domain/AiProPanel.tsx (WEB — sunucu kamerası) — hazırlık akışının kalan kolları.
 *  1) Öneri ALINAMAZSA şerit "yeniden deneniyor" der, `localized` sıfırlanır ("Yeniden Konumla" düğmesi "konumlandı" demez);
 *     5 sn dolmadan gelen durum yoklaması öneriyi yeniden İSTEMEZ (fırtına yok).
 *  2) HAZIRLIK TAVANI (120 sn): hazırlık biter, operatör uyarılır ve sunucu önizlemesi BIRAKILIR (`/ai/pro/hazirlik/durdur`).
 *  3) "Yeniden Konumla" (seans yokken) hazırlık komutu sunucuya ULAŞMAZSA hazırlığa GİRİLMEZ; kamera kutusu nedeni söyler (kör 120 sn
 *     "Hazırlanıyor…" yok). Ulaşırsa hazırlık başlar.
 * GERÇEK: AiProPanel, apiClient (platformAlert → window.alert), config (istemci kimliği).
 * SAHTE (en alt kat): fetch, `window.alert` (gözlemci), sahte saat; Platform.OS="web" (IS_WEB import anında → mock ÖNCE); bağlamlar
 * sabit girdi.
 */
jest.mock("react-native", () => {
  const RN = jest.requireActual("react-native");
  RN.Platform.OS = "web";
  return RN;
});
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: null, wsConnected: true, aiVisionData: null, aiVisionFresh: false }),
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "v@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({ useOperator: () => ({ operatorEmail: "v@x.com" }) }));
jest.mock("expo-camera", () => {
  const R = require("react");
  return { CameraView: R.forwardRef(() => null), useCameraPermissions: () => [{ granted: true }, jest.fn()] };
});

import React from "react";
import { act, fireEvent, render, type RenderResult } from "@testing-library/react-native";
import i18n from "i18next";

import { AiProPanel } from "../AiProPanel";

const T = (k: string, o?: object): string => (i18n.t as unknown as (k: string, o?: object) => string)(k, o);

type Yanit = [number, unknown];
let durum: Record<string, unknown>;
let hazirlikYaniti: Yanit;
let oneriYaniti: Yanit;
let fetchSahte: jest.Mock;
let uyari: jest.SpyInstance;

function yolu(url: unknown): string {
  return String(url).replace(/^[a-z]+:\/\/[^/]+/i, "").replace(/^\/api/, "");
}
const postlar = (yol: string) =>
  fetchSahte.mock.calls.filter((c) => yolu(c[0]) === yol && (c[1] as { method?: string } | undefined)?.method === "POST");

beforeEach(() => {
  jest.useFakeTimers();
  durum = { active: false, localized: false };
  hazirlikYaniti = [200, { status: "success" }];
  oneriYaniti = [422, { detail: "Bu konum için sürülebilir parametre yok." }];
  // RN test ortamında `window` küresel nesnedir; `alert` yoksa tanımlanır (platformAlert web kolu onu çağırır).
  if (typeof (window as { alert?: unknown }).alert !== "function") (window as { alert?: unknown }).alert = () => undefined;
  uyari = jest.spyOn(window, "alert").mockImplementation(() => undefined);
  uyari.mockClear();
  fetchSahte = jest.fn(async (url: unknown) => {
    const yol = yolu(url);
    let y: Yanit = [200, { status: "success" }];
    if (yol === "/ai/pro/status") y = [200, durum];
    else if (yol === "/ai/pro/hazirlik/baslat") y = hazirlikYaniti;
    else if (yol === "/ai/pro/propose") y = oneriYaniti;
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
const hazirlikMetni = (u: RenderResult) => String(u.getByTestId("aipro-hazirlik-metni-metin").props.children);

it("KRİTİK: web öneri alınamazsa şerit 'yeniden deneniyor', konum sıfırlanır; 5 sn dolmadan gelen yoklama yeniden İSTEMEZ", async () => {
  const u = await panel();
  await act(async () => { fireEvent.press(u.getByLabelText(T("ai.pro.dugme.baslatEtiket"))); });
  await bosalt();
  expect(postlar("/ai/pro/hazirlik/baslat")).toHaveLength(1);
  durum = { active: false, localized: true };
  await ilerle(3000); // yoklama: konumlandı → öneri (başarısız)
  expect(postlar("/ai/pro/propose")).toHaveLength(1);
  expect(hazirlikMetni(u)).toBe(T("ai.pro.hata.oneriDeneniyor"));
  expect(u.getByLabelText(T("ai.pro.yenidenKonumla.etiket"))).toBeTruthy(); // localized sıfırlandı
  expect(postlar("/ai/pro/hazirlik/durdur")).toHaveLength(0); // önizleme sürüyor
  await ilerle(3000); // +3 sn yoklama: yine konumlandı ama bekleme (5 sn) sürüyor
  expect(u.getByLabelText(T("ai.pro.yenidenKonumla.konumlandiEtiket"))).toBeTruthy();
  expect(postlar("/ai/pro/propose")).toHaveLength(1);
  expect(hazirlikMetni(u)).toBe(T("ai.pro.hata.oneriDeneniyor"));
});

it("KRİTİK (KP-5 · 5 ürün hatası): bekleme (5 sn) DOLUNCA öneri YENİDEN istenir — konum sabit kalsa da; fırtına yok", async () => {
  // Kök neden (KP-4 B1 ölçümü): başarısızlıktan sonra 3 sn'lik yoklama `localized`ı bekleme sürerken true yapıyordu; sonraki
  // yoklamalar değeri DEĞİŞTİRMEDİĞİ için efekt bir daha koşmuyor, şerit 120 sn tavanına kadar "yeniden deneniyor" diyordu.
  const u = await panel();
  await act(async () => { fireEvent.press(u.getByLabelText(T("ai.pro.dugme.baslatEtiket"))); });
  await bosalt();
  durum = { active: false, localized: true };
  await ilerle(3000); // t=3: öneri #1 (başarısız) → bekleme t=8'e dek
  expect(postlar("/ai/pro/propose")).toHaveLength(1);
  await ilerle(3000); // t=6: yoklama konumu yeniden true yapar, bekleme sürüyor → istek YOK
  expect(postlar("/ai/pro/propose")).toHaveLength(1);
  await ilerle(3000); // t=9: bekleme t=8'de doldu → öneri #2
  expect(postlar("/ai/pro/propose")).toHaveLength(2);
  oneriYaniti = [200, { proposalId: "p-3", specs: {}, meta: {} }];
  for (let i = 0; i < 3; i++) await ilerle(3000); // t=18: #2'nin (t=8) beklemesi t=13'te doldu → öneri #3 başarılı → önizleme bırakılır
  expect(postlar("/ai/pro/propose")).toHaveLength(3);
  expect(postlar("/ai/pro/hazirlik/durdur")).toHaveLength(1);
  expect(u.queryByTestId("aipro-hazirlik-metni")).toBeNull();
});

it("KARŞIT (KP-5 · 5): bekleme dolduğunda konum YOKSA (localized false) öneri İSTENMEZ", async () => {
  const u = await panel();
  await act(async () => { fireEvent.press(u.getByLabelText(T("ai.pro.dugme.baslatEtiket"))); });
  await bosalt();
  durum = { active: false, localized: true };
  await ilerle(3000);
  expect(postlar("/ai/pro/propose")).toHaveLength(1);
  durum = { active: false, localized: false };
  for (let i = 0; i < 4; i++) await ilerle(3000); // t=15: bekleme doldu ama konum kayıp
  expect(postlar("/ai/pro/propose")).toHaveLength(1);
  expect(hazirlikMetni(u)).toBe(T("ai.pro.hata.oneriDeneniyor"));
});

it("KRİTİK: web hazırlık TAVANI (120 sn) — hazırlık biter, operatör uyarılır, sunucu önizlemesi BIRAKILIR", async () => {
  const u = await panel();
  await act(async () => { fireEvent.press(u.getByLabelText(T("ai.pro.dugme.baslatEtiket"))); });
  await bosalt();
  for (let i = 0; i < 119; i++) await ilerle(1000);
  expect(u.getByTestId("aipro-hazirlik-metni")).toBeTruthy();
  expect(postlar("/ai/pro/hazirlik/durdur")).toHaveLength(0);
  await ilerle(1000);
  expect(postlar("/ai/pro/hazirlik/durdur")).toHaveLength(1);
  expect(uyari).toHaveBeenCalledWith(`${T("ai.pro.uyari.konumlandirmaTamamlanamadi")}\n${T("ai.pro.uyari.konumlandirmaTamamlanamadiGovdeKabin") /* AP-B6: web = kabin (sunucu) kamerası */}`);
  expect(u.queryByTestId("aipro-hazirlik-metni")).toBeNull();
  expect(u.getByText(T("ai.pro.kamera.durdu"))).toBeTruthy();
});

it("KRİTİK: 'Yeniden Konumla' hazırlık komutu sunucuya ulaşmazsa hazırlığa GİRİLMEZ, kamera kutusu nedeni söyler", async () => {
  hazirlikYaniti = [503, { detail: "Sunucu kamerası meşgul." }];
  const u = await panel();
  await act(async () => { fireEvent.press(u.getByLabelText(T("ai.pro.yenidenKonumla.etiket"))); });
  await bosalt();
  expect(postlar("/ai/pro/calibrate")).toHaveLength(1);
  expect(postlar("/ai/pro/hazirlik/baslat")).toHaveLength(1);
  expect(u.getByText(`⚠️ ${T("ai.pro.hata.hazirlikKomutu")}`)).toBeTruthy();
  expect(u.queryByTestId("aipro-hazirlik-metni")).toBeNull();
  expect(u.queryByText(T("ai.pro.dugme.hazirlaniyor"))).toBeNull();
});

it("KARŞIT: 'Yeniden Konumla' komutu ulaşırsa (seans yokken) hazırlık başlar", async () => {
  const u = await panel();
  await act(async () => { fireEvent.press(u.getByLabelText(T("ai.pro.yenidenKonumla.etiket"))); });
  await bosalt();
  expect(postlar("/ai/pro/hazirlik/baslat")).toHaveLength(1);
  expect(u.getByTestId("aipro-hazirlik-metni")).toBeTruthy();
  expect(u.getByText(T("ai.pro.dugme.hazirlaniyor"))).toBeTruthy();
});
