/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * D2.E03 (İG-6.21 · Y84) + D2.E01 (İG-6.20) — Ayarlar → Veri Taşıma: yedek alma / geri yükleme.
 * ===========================================================================================================================
 * D2.E03 ÖLÇÜLEN KUSUR: `/data/export` ve `/data/import` varsayılan 8 sn zaman aşımıyla çağrılıyordu; 2000 seanslık şifreli klinikte geri
 * yükleme ~3 dk sürüyor → istek 8,0 sn'de iptal, ekran "İşlem zaman aşımına uğradı … Tekrar deneyin — ilk analiz MODEL YÜKLEMESİ
 * nedeniyle …" diyordu; operatör tekrar denedi → kayıtlar İKİYE katlandı (sunucu yarısı D2.E02). Y84: ayrı UZUN zaman aşımı, düğme
 * kilitli + "Yükleniyor…", metin "Tekrar deneyin" DEMEZ.
 * D2.E01 ÖLÇÜLEN KUSUR: "Şifreli Yedek Oluştur" blob + `<a download>` ile indiriyor ve dosyanın oluşup oluşmadığını bilmeden
 * "Yedek oluşturuldu" diyordu; masaüstü WebView2'de `<a download>` sessizce ölebiliyor (09-11 saha arızası, `dosyaIndir.ts`). Şimdi:
 * backend bu makinedeyse dosyayı BACKEND yazar ve doğrular, "oluşturuldu" yalnız yol + boyutla döndüğünde; tarayıcı (LAN) yolunda metin
 * "İndirme başlatıldı — doğrulayın" der, "oluşturuldu" DEMEZ.
 * GERÇEK: SettingsScreen, BackupPassphraseDialog, apiClient (zaman aşımı + hata metni), toastBridge, config, dosyaIndir. Sahte (en alt
 * kat / ekran dışı): fetch, ekranın bağlamları (kullanıcı kipi, oturum, canlı veri, toast kancası), `window.confirm`, dosya seçici,
 * Blob URL. Ortam: jsdom + react-native-web + react-dom kökü (`operatorAparati.Sahne`); bu ortamda expo'nun `URL`u kurucu değil
 * (ölçüldü) → Node `URL` kurulur (ürün gerçek tarayıcıda / WebView2'de koşar).
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

describe("Y12 (D2.52) — geri yükleme metinleri gerçeği söyler: hasta kartları SİLİNMEZ, yedekte olmayanlar RAPORLANIR", () => {
  it("KRİTİK: onay metni hasta kartlarının silinmediğini söyler; başarı bildirimi sunucunun 'yedekte olmayan' uyarısını gösterir", async () => {
    sonOnayMetni = "";
    const uyari = "Yedekte olmayan 1 hastanın kartı korundu; bu hastaların bu cihazdaki seans ve analiz geçmişi geri yüklemeyle silindi (yedekte yoktu).";
    yanit = (yol) =>
      yol === "/data/import"
        ? sahteYanit({ status: "success", counts: { patients: 2, treatment_sessions: 4, ai_analyses: 2 }, yedekte_olmayan_hasta: 1, uyari })
        : null;
    await ekran("http://127.0.0.1:8000/api");
    await iceAktarBaslat();
    expect(sonOnayMetni).toMatch(/Hasta kartları silinmez/);
    expect(sonOnayMetni).not.toMatch(/SEANS ve AI ANALİZ geçmişi SİLİNİP/);
    const m = mockToast.mock.calls.map((x) => String(x[0]));
    expect(m.some((x) => x.includes(uyari))).toBe(true);
  });
});

describe("D2.E03 — yedek alma / geri yükleme UZUN zaman aşımıyla, 'Tekrar deneyin' YOK (Y84)", () => {
  it.each([
    ["dışa aktarma", "/data/export", disaAktarBaslat, "Hazırlanıyor…", "Klinik verilerini şifreli dosyaya aktar"],
    ["geri yükleme", "/data/import", iceAktarBaslat, "Yükleniyor…", "Şifreli yedekten geri yükle"],
  ])("KRİTİK: %s 8 sn'de İPTAL EDİLMEZ, 'model yüklemesi' / 'Tekrar deneyin' çıkmaz; düğme kilitli", async (_ad, yol, baslat, etiket, dugme) => {
    await ekran("http://192.168.1.50:8000/api");
    await baslat();
    const c = cagrilar.find((x) => x.yol === yol && x.yontem === "POST");
    expect(c).toBeDefined();
    await s.ilerlet(8000 + 2000);
    expect(c!.sinyal?.aborted).toBe(false);
    expect(metinler().filter((m) => /Tekrar deneyin|model yükleme/i.test(m))).toEqual([]);
    expect(s.metin()).toContain(etiket);
    expect(s.etiket(dugme).getAttribute("aria-disabled")).toBe("true");
  });

  it.each([
    ["dışa aktarma", "/data/export", disaAktarBaslat],
    ["geri yükleme", "/data/import", iceAktarBaslat],
  ])("KRİTİK: %s uzun zaman aşımı dolunca metin işlemin CİHAZDA SÜRÜYOR olabileceğini söyler, 'Tekrar deneyin' DEMEZ", async (_ad, yol, baslat) => {
    await ekran("http://192.168.1.50:8000/api");
    await baslat();
    const c = cagrilar.find((x) => x.yol === yol && x.yontem === "POST")!;
    await s.ilerlet(15 * 60 * 1000 - 1000);
    expect(c.sinyal?.aborted).toBe(false); // en az 15 dk (ADAY-DOGRULAMA önerisi)
    await s.ilerlet(60 * 60 * 1000);
    expect(c.sinyal?.aborted).toBe(true);
    const m = metinler();
    expect(m.some((x) => /sürüyor olabilir/.test(x))).toBe(true);
    expect(m.filter((x) => /Tekrar deneyin|model yükleme/i.test(x))).toEqual([]);
    expect(s.metin()).not.toContain("Yükleniyor…");
  });
});

describe("D2.E01 — 'Yedek oluşturuldu' yalnız dosya DOĞRULANINCA", () => {
  it("KRİTİK: backend BU MAKİNEDEYKEN dosyayı backend yazar (kaydet), <a download> kurulmaz, başarı yolu ve doğrulamayı söyler", async () => {
    const indir = jest.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    yanit = (yol) =>
      yol === "/data/export"
        ? sahteYanit({
            status: "success",
            yol: "C:\\Users\\klinik\\Desktop\\pemf-vet-yedek-20261009-0300.pemfbak",
            ad: "pemf-vet-yedek-20261009-0300.pemfbak",
            bayt: 4096,
            dogrulandi: true,
            counts: { patients: 3, treatment_sessions: 6, ai_analyses: 3 },
          })
        : null;
    try {
      await ekran("http://127.0.0.1:8000/api");
      await disaAktarBaslat();
      const c = cagrilar.find((x) => x.yol === "/data/export")!;
      expect(c.govde).toMatchObject({ passphrase: PAROLA, kaydet: true });
      expect(indir).not.toHaveBeenCalled();
      const basari = mockToast.mock.calls.filter((x) => x[1] === "success").map((x) => String(x[0]));
      expect(basari).toHaveLength(1);
      expect(basari[0]).toContain("pemf-vet-yedek-20261009-0300.pemfbak");
      expect(basari[0]).toMatch(/doğrulandı/);
    } finally {
      indir.mockRestore();
    }
  });

  it("KRİTİK: backend yerelken yanıt yol/boyut taşımıyorsa 'oluşturuldu' DENMEZ, hata söylenir", async () => {
    yanit = (yol) => (yol === "/data/export" ? sahteYanit({ status: "success", counts: { patients: 3 } }) : null);
    await ekran("http://127.0.0.1:8000/api");
    await disaAktarBaslat();
    expect(metinler().filter((m) => /oluşturuldu/.test(m))).toEqual([]);
    expect(mockToast.mock.calls.some((x) => x[1] === "error")).toBe(true);
  });

  it("KRİTİK: tarayıcı (LAN) yolunda indirme başlatılır ama metin 'oluşturuldu' DEMEZ, doğrulamayı ister", async () => {
    const indir = jest.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    yanit = (yol) =>
      yol === "/data/export"
        ? sahteYanit({ status: "success", filename: "pemf-vet-yedek.pemfbak", data_b64: "UEVNRg==", counts: { patients: 3, treatment_sessions: 6, ai_analyses: 3 } })
        : null;
    try {
      await ekran("http://192.168.1.50:8000/api");
      await disaAktarBaslat();
      const c = cagrilar.find((x) => x.yol === "/data/export")!;
      expect(c.govde?.kaydet).toBeUndefined();
      expect(indir).toHaveBeenCalledTimes(1);
      const m = mockToast.mock.calls.map((x) => String(x[0]));
      expect(m.filter((x) => /oluşturuldu/.test(x))).toEqual([]);
      expect(m.some((x) => /İndirme başlatıldı/.test(x) && /doğrulayın/.test(x))).toBe(true);
    } finally {
      indir.mockRestore();
    }
  });
});
