/**
 * @jest-environment jsdom
 */
/**
 * KP-8 · src/screens/AiHubScreen.tsx · WEB — Böbrek Hastalığı (CKD) + Yara Kapanma (scratch) kalan dallar (düzenek
 * KP3-AiHub-formVeDosyaModulleriWeb ile AYNI — sahte en alt katta):
 *  - CKD: sonuç "ckd" DEĞİLSE olumlu ("sağlıklı") yorum + düşük olasılık metni; olasılık / XAI gelmezse çökmez, XAI satırı yok.
 *  - Scratch: adı olmayan belge "goruntu" adıyla gider; kapanma ölçüsü gelmezse kayıt "%?" ve ekran boş yüzde; sunucu kapanma uyarısı
 *    "⚠" satırıyla görünür; iki ölçümde kapanma GERİLERSE fark işaretsiz (eksi) yazılır.
 */
jest.mock("react-native", () => jest.requireActual("react-native-web"));
jest.mock("react-native-safe-area-context", () => {
  const R = require("react");
  const { View } = require("react-native-web");
  return {
    useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
    SafeAreaProvider: ({ children }: { children?: unknown }) => children,
    SafeAreaView: ({ children, style }: { children?: unknown; style?: unknown }) => R.createElement(View, { style }, children),
  };
});
let mockKip: "veterinarian" | "researcher" = "researcher";
let mockHastaNo = 93000;
jest.mock("@/context/UserModeContext", () => ({ useUserMode: () => ({ userMode: mockKip, hasAiHub: true }) }));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "dr@klinik.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({
  useOperator: () => ({ operatorEmail: "dr@klinik.com" }),
  useOperatorOptional: () => ({ operatorEmail: "dr@klinik.com", operators: [] }),
}));
jest.mock("@/context/EntitlementContext", () => ({ useEntitlement: () => ({ research: true, realtime: false }) }));
jest.mock("@/context/AppNavContext", () => ({
  useAppNav: () => ({ navigate: jest.fn(), selectedPatient: { id: `kp3f-${mockHastaNo}`, name: `Pamuk-${mockHastaNo}` } }),
}));
jest.mock("@/context/LiveDataContext", () => ({ useLiveData: () => ({ snapshot: null, wsConnected: true, aiVisionFresh: false }) }));
jest.mock("@/components/domain/PatientGate", () => {
  const React = require("react");
  return { PatientGate: ({ children }: any) => React.createElement(React.Fragment, null, children) };
});
jest.mock("@/components/UpgradeModal", () => ({ UpgradeModal: () => null }));
jest.mock("expo-camera", () => ({ CameraView: () => null, useCameraPermissions: () => [{ granted: true }, jest.fn()] }));
jest.mock("expo-audio", () => ({
  useAudioRecorder: () => ({ record: jest.fn(), stop: jest.fn(), prepareToRecordAsync: jest.fn(), uri: null }),
  RecordingPresets: { HIGH_QUALITY: {} },
  setAudioModeAsync: jest.fn(),
  requestRecordingPermissionsAsync: jest.fn(async () => ({ granted: true })),
}));
jest.mock("expo-image-picker", () => ({ MediaTypeOptions: { Images: "Images" }, launchImageLibraryAsync: jest.fn(), launchCameraAsync: jest.fn() }));
jest.mock("expo-image-manipulator", () => ({ SaveFormat: { JPEG: "jpeg" }, manipulateAsync: jest.fn() }));
jest.mock("expo-document-picker", () => ({ getDocumentAsync: jest.fn() }));
jest.mock("expo-file-system/legacy", () => ({ readAsStringAsync: jest.fn(), documentDirectory: "file:///" }));
jest.mock("expo-haptics", () => ({ impactAsync: jest.fn(async () => undefined), notificationAsync: jest.fn(), selectionAsync: jest.fn(),
  ImpactFeedbackStyle: {}, NotificationFeedbackType: {} }));
jest.mock("expo-linear-gradient", () => {
  const R = require("react");
  const { View } = require("react-native-web");
  return { LinearGradient: ({ children, style }: { children?: unknown; style?: unknown }) => R.createElement(View, { style }, children) };
});

import i18n from "i18next";
import { act } from "react";
import * as DocumentPicker from "expo-document-picker";
import { AI_TIMEOUT_MS } from "@/services/apiClient";
import { aiDetayCumlesi } from "@/utils/aiHataDetayi";
import {
  alanlar, blobMetni, ekraniCiz, etiketeBas, ileti, metneBas, postlar, Sahne, saatiIlerlet, web, webKur, webSok,
} from "./KP3_aiHubWebAparati";

const T = (k: string, o?: object): string => (i18n.t as unknown as (k: string, o?: object) => string)(k, o);
const belgeSec = DocumentPicker.getDocumentAsync as jest.Mock;

let ozel: (yol: string, govde: unknown, yontem: string) => any = () => undefined;
let s: Sahne;

beforeEach(() => {
  mockHastaNo += 1;
  ozel = () => undefined;
  webKur((y, g, m) => ozel(y, g, m));
  belgeSec.mockReset();
  s = new Sahne();
});
afterEach(async () => {
  await s.sok();
  jest.useRealTimers();
  jest.restoreAllMocks();
  webSok();
});

async function moduluAc(kip: "veterinarian" | "researcher", ad: string) {
  mockKip = kip;
  await ekraniCiz(s);
  await etiketeBas(s, T(ad));
}

/** Görünen metni tam `metin` olan (en derin) elemanların `sira`ncısına bas — aynı seçenek adı birden çok satırda geçer. */
async function siradakineBas(metin: string, sira: number) {
  saatiIlerlet();
  const adaylar = Array.from(document.querySelectorAll("*")).filter(
    (e) => (e.textContent || "").trim() === metin && !Array.from(e.children).some((c) => (c.textContent || "").trim() === metin),
  ) as HTMLElement[];
  if (adaylar.length <= sira) throw new Error(`"${metin}" ${sira}. aday yok (${adaylar.length})`);
  await act(async () => { adaylar[sira].click(); });
  await s.bosalt(6);
}

/** Denetimli <input>'a gerçek `input` olayıyla yaz (Sahne.yaz'ın etiketsiz alan eşi). */
async function alanaYaz(el: HTMLInputElement, metin: string) {
  const ayarla = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
  await act(async () => {
    ayarla.call(el, metin);
    el.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await s.bosalt(2);
}

/** Yanıtı bekletilen fetch: `uc`a giden istek `serbest(yanit)` çağrılana (ya da iptal edilene) dek askıda kalır. */
function askidaUc(uc: string) {
  const d: { serbest: (durum: number, veri: unknown) => void; iptal: boolean } = { serbest: () => undefined, iptal: false };
  const kayitli = global.fetch;
  global.fetch = jest.fn((u: unknown, init: any = {}) => {
    if (!String(u).includes(uc)) return (kayitli as any)(u, init);
    web.istekler.push({ yontem: init.method || "GET", yol: uc, govde: init.body, basliklar: init.headers || {} });
    return new Promise((coz, reddet) => {
      d.serbest = (durum, veri) => coz({ ok: durum < 400, status: durum, json: async () => veri, headers: { get: () => null } });
      init.signal?.addEventListener("abort", () => {
        d.iptal = true;
        reddet(Object.assign(new Error("The operation was aborted."), { name: "AbortError" }));
      });
    });
  }) as any;
  return d;
}


describe("Böbrek Hastalığı · sağlıklı sonuç", () => {
  const SAYI_SIRA = ["age", "bp", "sg", "al", "su", "bgr", "bu", "sc", "sod", "pot", "hemo", "pcv", "wc", "rc"];
  const sayiAlani = (k: string) => Array.from(document.querySelectorAll('input[placeholder="—"]'))[SAYI_SIRA.indexOf(k)] as HTMLInputElement;

  it("ckd DEĞİL → olumlu yorum + düşük olasılık metni; olasılık / XAI yoksa çökmez", async () => {
    ozel = (y, _g, m) => (m === "POST" && y === "/ai/disease/kidney" ? [200, { status: "success", label: "notckd", model: "ExtraTrees" }] : undefined);
    await moduluAc("researcher", "ai.modul.bobrekHastaligi.ad");
    for (const [k, v] of [["age", "7"], ["sg", "1,02"], ["al", "1"], ["bu", "40"], ["sc", "1,2"], ["hemo", "13"]] as const) {
      await alanaYaz(sayiAlani(k), v);
    }
    await metneBas(s, T("ai.ckd.analiziBaslat"));
    const m = s.metin();
    expect(m).toContain(T("ai.ckd.sonuc.saglikli", { pct: undefined }));
    expect(m).toContain(T("ai.ckd.sonuc.dusukMetin", { pct: undefined }));
    expect(m).not.toContain(T("ai.ckd.sonuc.ckdOlasi", { pct: undefined }));
  });
});

describe("Yara Kapanma · sonuç varyantları", () => {
  const blobUrl = (icerik: string) => URL.createObjectURL(new Blob([icerik], { type: "image/png" }));

  it("adsız belge 'goruntu' adıyla; kapanma yoksa kayıt '%?'; kapanma uyarısı görünür; gerileyen karşılaştırma işaretsiz", async () => {
    let n = 0;
    const YANITLAR = [
      { status: "success", n_cells: 10, closure_uyari: "KP8 kenar bulanık" },
      { status: "success", n_cells: 12, closure: { closure_pct: 60, mean_gap_um: 100, max_gap_um: 200 } },
      { status: "success", n_cells: 12, closure: { closure_pct: 40, mean_gap_um: 150, max_gap_um: 250 } },
    ];
    ozel = (y, _g, m) => (m === "POST" && y === "/ai/vision/scratch" ? [200, YANITLAR[Math.min(n++, 2)]] : undefined);
    await moduluAc("researcher", "ai.modul.yaraKapanma.ad");
    belgeSec.mockResolvedValueOnce({ canceled: false, assets: [{ uri: blobUrl("YARA-X") }] });
    await metneBas(s, T("ai.scratch.dosyaSec"));
    await metneBas(s, T("ai.scratch.analizEt"));
    expect((alanlar(postlar("/ai/vision/scratch")[0].govde).file as File).name).toBe("goruntu");
    expect(JSON.stringify(postlar("/ai/log").map((p) => p.govde))).toContain("Kapanma %?");
    expect(s.metin()).toContain("⚠ KP8 kenar bulanık");
    // karşılaştırma iki FARKLI görüntü (etiket = dosya adı) ister: 0 sa → %60, 24 sa → %40 (kapanma GERİLEDİ)
    belgeSec.mockResolvedValueOnce({ canceled: false, assets: [{ uri: blobUrl("YARA-0"), name: "yara_0s.png" }] });
    await metneBas(s, "goruntu");
    await metneBas(s, T("ai.scratch.analizEt"));
    belgeSec.mockResolvedValueOnce({ canceled: false, assets: [{ uri: blobUrl("YARA-24"), name: "yara_24s.png" }] });
    await metneBas(s, "yara_0s.png");
    await metneBas(s, T("ai.scratch.analizEt"));
    await metneBas(s, T("ai.scratch.karsilastir"));
    expect(s.metin()).toContain(T("ai.scratch.delta", { isaret: "", fark: "-20.0" }));
  });
});
