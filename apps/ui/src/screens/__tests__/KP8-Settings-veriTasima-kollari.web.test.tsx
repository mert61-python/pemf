/**
 * @jest-environment jsdom
 */
/**
 * KP-8 · src/screens/SettingsScreen.tsx · Veri Taşıma kalan dallar (düzenek SettingsVeriTasima.D2E01_E03 ile AYNI — gerçek ekran +
 * apiClient + toastBridge; sahte fetch / dosya seçici / Blob URL). Sunucu yanıtı alan EKSİK gelse de ekran ÇÖKMEZ ve doğruyu söyler:
 *  - LAN yolunda sayım ve dosya adı gelmezse indirme VARSAYILAN adla başlar, sayım 0'larla söylenir.
 *  - Backend bu makinedeyken yol gelir ama BOYUT gelmezse "oluşturuldu" DENMEZ (yol yok hatası).
 *  - Geri yüklemede "zaten vardı" + "aktarılamadı" sayıları parantez içinde söylenir, başarısız varsa ileti HATA tonunda; sayım alanları
 *    eksikse 0; sunucu uyarısı yoksa ek metin yok.
 */
jest.mock("react-native", () => jest.requireActual("react-native-web"));
const mockToast = jest.fn();
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: mockToast }) }));
jest.mock("@/context/UserModeContext", () => ({
  useUserMode: () => ({ setUserMode: jest.fn(), isExpert: true, isResearcher: false }),
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: null }) }));
jest.mock("@/context/LiveDataContext", () => ({ useLiveData: () => ({ reconnect: jest.fn(), wsConnected: true }) }));
jest.mock("@/hooks/useTeardownGuard", () => ({ useTeardownGuard: () => (f: unknown) => f }));
jest.mock("@/services/discovery", () => ({ checkHealth: jest.fn(), discoverBackend: jest.fn() }));
jest.mock("@/services/supabaseAuth", () => ({ updateProfile: jest.fn() }));
jest.mock("@/services/pairing", () => ({ cihazaBaglan: jest.fn(), eslesmeMesaji: jest.fn() }));
jest.mock("expo-linear-gradient", () => {
  const R = require("react");
  const { View } = require("react-native-web");
  return { LinearGradient: ({ children, style }: { children?: unknown; style?: unknown }) => R.createElement(View, { style }, children) };
});

import React from "react";
import { SettingsScreen } from "@/screens/SettingsScreen";
import { serviceConfig } from "@/services/config";
import { setToastHandler } from "@/services/toastBridge";
import { Sahne } from "../../context/__tests__/operatorAparati";

const PAROLA = "klinik-yedek-2026-ekran";
const mockHata = jest.fn();
const NodeURL = require("url").URL;

type Cagri = { yol: string; yontem: string; govde: Record<string, unknown> | null; sinyal: AbortSignal | null | undefined };
let cagrilar: Cagri[];
let yanit: (yol: string) => unknown | null;
let s: Sahne;
let eskiURL: unknown;

function sahteYanit(veri: unknown, durum = 200) {
  const govde = JSON.stringify(veri);
  return {
    ok: durum >= 200 && durum < 300,
    status: durum,
    headers: { get: () => "application/json" },
    text: async () => govde,
    json: async () => JSON.parse(govde),
  };
}

beforeEach(() => {
  jest.useFakeTimers();
  mockToast.mockReset();
  mockHata.mockReset();
  setToastHandler((m: string, t?: string) => mockHata(m, t));
  eskiURL = (global as unknown as { URL: unknown }).URL;
  const U = class extends NodeURL {} as unknown as { createObjectURL: unknown; revokeObjectURL: unknown };
  U.createObjectURL = jest.fn(() => "blob:yedek");
  U.revokeObjectURL = jest.fn();
  (global as unknown as { URL: unknown }).URL = U;
  cagrilar = [];
  yanit = () => null;
  (global as unknown as { fetch: unknown }).fetch = jest.fn((url: string, init?: RequestInit) => {
    const yol = String(url).replace(/^[a-z]+:\/\/[^/]+/i, "").replace(/^\/api/, "");
    const yontem = (init?.method || "GET").toUpperCase();
    cagrilar.push({ yol, yontem, govde: init?.body ? JSON.parse(String(init.body)) : null, sinyal: init?.signal });
    const r = yontem === "POST" ? yanit(yol) : null;
    if (r) return Promise.resolve(r);
    if (yontem === "GET") return Promise.resolve(sahteYanit({}));
    return new Promise((_coz, reddet) => {
      // asılı istek: yalnız iptal (AbortController) sonlandırır — gerçek fetch gibi
      init?.signal?.addEventListener("abort", () => reddet(Object.assign(new Error("aborted"), { name: "AbortError" })));
    });
  });
  s = new Sahne();
});
afterEach(async () => {
  await s.sok();
  setToastHandler(null);
  (global as unknown as { URL: unknown }).URL = eskiURL;
  jest.useRealTimers();
});

async function ekran(taban: string) {
  serviceConfig.apiBaseUrl = taban;
  await s.ciz(<SettingsScreen />);
}

async function disaAktarBaslat() {
  await s.tikla("Klinik verilerini şifreli dosyaya aktar");
  await s.yaz("Yedek parolası", PAROLA);
  await s.yaz("Yedek parolası tekrar", PAROLA);
  await s.tikla("Yedeği oluştur");
}

async function iceAktarBaslat() {
  const gercekOlustur = document.createElement.bind(document);
  let girdi: HTMLInputElement | null = null;
  const casus = jest.spyOn(document, "createElement").mockImplementation(((ad: string, sec?: ElementCreationOptions) => {
    const el = gercekOlustur(ad, sec);
    if (ad === "input") {
      girdi = el as HTMLInputElement;
      jest.spyOn(girdi, "click").mockImplementation(() => {});
    }
    return el;
  }) as typeof document.createElement);
  const onay = jest.spyOn(window, "confirm").mockImplementation((m?: string) => {
    sonOnayMetni = String(m ?? "");
    return true;
  });
  try {
    await s.tikla("Şifreli yedekten geri yükle");
    expect(girdi).not.toBeNull();
    const dosya = { name: "yedek.pemfbak", arrayBuffer: async () => new Uint8Array([80, 69, 77, 70]).buffer };
    Object.defineProperty(girdi!, "files", { value: [dosya] });
    await s.bosalt();
    void (girdi as unknown as { onchange: () => Promise<void> }).onchange();
    await s.bosalt();
    await s.yaz("Yedek parolası", PAROLA);
    await s.tikla("Devam et");
    await s.bosalt(10);
  } finally {
    casus.mockRestore();
    onay.mockRestore();
  }
}

const metinler = () => [...mockHata.mock.calls, ...mockToast.mock.calls].map((c) => String(c[0]));
let sonOnayMetni = "";


it("LAN: sayım ve dosya adı gelmezse indirme varsayılan adla başlar, sayım 0'larla söylenir", async () => {
  const indir = jest.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  yanit = (yol) => (yol === "/data/export" ? sahteYanit({ status: "success", data_b64: "UEVNRg==" }) : null);
  try {
    await ekran("http://192.168.1.50:8000/api");
    await disaAktarBaslat();
    expect(indir).toHaveBeenCalledTimes(1);
    const m = mockToast.mock.calls.map((x) => String(x[0]));
    expect(m.some((x) => x.includes("pemf-vet-yedek.pemfbak") && /İndirme başlatıldı/.test(x))).toBe(true);
    expect(m.some((x) => /0 hasta/.test(x))).toBe(true);
  } finally {
    indir.mockRestore();
  }
});

it("yerel: yol gelir ama boyut gelmezse 'oluşturuldu' DENMEZ, hata söylenir", async () => {
  yanit = (yol) => (yol === "/data/export" ? sahteYanit({ status: "success", yol: "C:\\Yedek\\x.pemfbak", counts: {} }) : null);
  await ekran("http://127.0.0.1:8000/api");
  await disaAktarBaslat();
  const m = mockToast.mock.calls;
  expect(m.some((x) => /oluşturuldu/.test(String(x[0])))).toBe(false);
  expect(m.some((x) => x[1] === "error")).toBe(true);
});

it("geri yükleme: 'zaten vardı' + 'aktarılamadı' parantez içinde, başarısız varsa HATA tonu; eksik sayımlar 0; uyarı yoksa ek yok", async () => {
  yanit = (yol) =>
    yol === "/data/import" ? sahteYanit({ status: "success", counts: { patient_db_zaten_vardi: 2, patient_db_basarisiz: 1 } }) : null;
  await ekran("http://192.168.1.50:8000/api");
  await iceAktarBaslat();
  const son = mockToast.mock.calls[mockToast.mock.calls.length - 1];
  expect(son[1]).toBe("error");
  const metin = String(son[0]);
  expect(metin).toMatch(/\(.*2.*,.*1.*\)$/);
  expect(metin).toMatch(/0 hasta/);
  yanit = (yol) =>
    yol === "/data/import" ? sahteYanit({ status: "success", counts: { patients: 1, treatment_sessions: 0, ai_analyses: 0 } }) : null;
  mockToast.mockReset();
  await iceAktarBaslat();
  const iki = mockToast.mock.calls[mockToast.mock.calls.length - 1];
  expect(iki[1]).toBe("success");
  expect(String(iki[0])).not.toMatch(/\(/);
});
