/**
 * @jest-environment jsdom
 */
/**
 * KP-3 C · src/screens/AiHubScreen.tsx · RNA (CSV) · Böbrek Hastalığı (form) · hekim Kedi Sesi · Yara Kapanma (scratch) — WEB sözleşmeleri.
 *  RNA: "CSV Seç" yalnız `.csv` seçicisi açar; dosya adı görünür ve düğme "Başka CSV" olur; "genleri göster" açıkken `explain=true` gider;
 *       istisna → sade ileti (ham hata / DOSYA YOLU gösterilmez — hasta adı taşıyabilir), ayrıntı yalnız konsola.
 *  Böbrek: seçilen bulgu ikinci basışta KALDIRILIR; asgari alan / çekirdek değer yoksa ön-kontrol uyarısı (eksik çekirdek alanların
 *       adlarıyla) ve istek GİTMEZ; virgüllü ondalık sayıya çevrilir; sunucunun gerekçesi apiClient iletisiyle KALIR (modül ezmez);
 *       gerekçesiz HTTP hatası ve ağ hatası → "analiz tamamlanamadı".
 *  Kedi Sesi (hekim): "Ses Yükle" `audio/*` seçicisi; 500 → "Analiz sırasında hata oluştu."; Error OLMAYAN ret → "Hata: <ileti>".
 *  Yara Kapanma: seçim iptali hiçbir şeyi değiştirmez; `blob:` URI'li seçim analizde blob'dan okunup ÖZGÜN adıyla gider, yeni seçim
 *       eskisinin nesne URL'sini bırakır; yön / objektif / ısı haritası alanları gider; sunucu `error` metni gösterilir; sonuçtan sonra
 *       parametre değişirse "yeniden analiz" notu; uçuştaki analizde parametre değişirse GEÇ YANIT YOK SAYILIR (kayıt da yazılmaz) ve
 *       analiz sürerken dosya seçici açılmaz.
 *  Ortak: analiz 8 sn'yi aşarsa modülün "model hazırlanıyor" ipucu; zaman sınırı dolunca istek İPTAL → zaman aşımı iletisi.
 * GERÇEK: AiHubScreen, ToastProvider, apiClient (apiPost), korunanFetch, sesYukleme, ckdOnKontrol. SAHTE (en alt kat): fetch, dosya
 * seçici (web `<input type=file>` / expo-document-picker), URL nesne-URL'leri, güvenli alan, expo modülleri; bağlamlar sabit girdi.
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

// ─────────────────────────────── RNA ───────────────────────────────
describe("Böbrek RNA (CSV)", () => {
  const CSV = () => new File(["gen,ifade\nVHL,2.1\n"], "kirc_genler.csv", { type: "text/csv" });

  it("yalnız .csv seçicisi; ad görünür, düğme 'Başka CSV'; 'genleri göster' açıkken explain=true; `file` özgün adıyla gider", async () => {
    await moduluAc("researcher", "ai.modul.bobrekRna.ad");
    web.dosyaSiradaki = CSV();
    await metneBas(s, T("ai.rna.csvSec"));
    expect(web.acilanSeciciler).toEqual([{ accept: ".csv,text/csv", capture: null }]);
    expect(s.metin()).toContain("📄 kirc_genler.csv");
    expect(s.metin()).toContain(T("ai.rna.baskaCsv"));
    await metneBas(s, `☐${T("ai.rna.genleriGoster")}`);
    await metneBas(s, T("ai.rna.analiziBaslat"));
    const a = alanlar(postlar("/ai/rna/kidney")[0].govde);
    expect((a.file as File).name).toBe("kirc_genler.csv");
    expect(await blobMetni(a.file)).toContain("VHL,2.1");
    expect(a.explain).toBe("true");
    expect(ileti()).toBe(T("ai.hata.analizSirasinda")); // gövdesiz yanıt → başarısız sayılır
  });

  it("istisna → sade 'RNA analizi başarısız' iletisi (dosya yolu ekranda YOK); ayrıntı konsola", async () => {
    const konsol = jest.spyOn(console, "error").mockImplementation(() => undefined);
    const hata = new Error("C:\\Hastalar\\Mia\\kirc_genler.csv okunamadı");
    ozel = (y, _g, m) => (m === "POST" && y === "/ai/rna/kidney" ? { hata } : undefined);
    await moduluAc("researcher", "ai.modul.bobrekRna.ad");
    web.dosyaSiradaki = CSV();
    await metneBas(s, T("ai.rna.csvSec"));
    await metneBas(s, T("ai.rna.analiziBaslat"));
    expect(ileti()).toBe(T("ai.rna.basarisiz"));
    expect(s.metin()).not.toContain("Hastalar");
    expect(konsol).toHaveBeenCalledWith("RNA analizi hatası:", hata);
  });
});

// ─────────────────────────── Böbrek Hastalığı ───────────────────────────
describe("Böbrek Hastalığı (form)", () => {
  /** CKD_NUMERIC sırası: age bp sg al su bgr bu sc sod pot hemo pcv wc rc. */
  const SAYI_SIRA = ["age", "bp", "sg", "al", "su", "bgr", "bu", "sc", "sod", "pot", "hemo", "pcv", "wc", "rc"];
  const sayiAlani = (k: string) => Array.from(document.querySelectorAll('input[placeholder="—"]'))[SAYI_SIRA.indexOf(k)] as HTMLInputElement;
  async function cekirdekDoldur() {
    for (const [k, v] of [["age", "7"], ["sg", "1,02"], ["al", "1"], ["bu", "40"], ["sc", "1,2"], ["hemo", "13"]] as const) {
      await alanaYaz(sayiAlani(k), v);
    }
  }

  it("bulgu ikinci basışta kalkar; asgari alan yoksa ön-kontrol (eksik çekirdek alan adlarıyla), istek GİTMEZ", async () => {
    await moduluAc("researcher", "ai.modul.bobrekHastaligi.ad");
    await siradakineBas(T("ai.ckd.secenek.anormal"), 0); // rbc
    await siradakineBas(T("ai.ckd.secenek.var"), 0); // pcc
    await siradakineBas(T("ai.ckd.secenek.kotu"), 0); // appet …
    await siradakineBas(T("ai.ckd.secenek.kotu"), 0); // … ikinci basış: kaldırıldı
    await metneBas(s, T("ai.ckd.analiziBaslat"));
    const eksik = ["ai.ckd.alan.sc", "ai.ckd.alan.bu", "ai.ckd.alan.sg", "ai.ckd.alan.al", "ai.ckd.alan.hemo"].map((k) => T(k)).join(", ");
    expect(ileti()).toBe(T("ai.ckd.onKontrol", { minAlan: 6, dolu: 2, eksik }));
    expect(postlar("/ai/disease/kidney")).toHaveLength(0);
  });

  it("virgüllü ondalık sayıya çevrilir + bulgu gider; sunucu gerekçesi apiClient iletisinde KALIR (modül ezmez)", async () => {
    ozel = (y, _g, m) => (m === "POST" && y === "/ai/disease/kidney" ? [422, { detail: "Kreatinin aralık dışı." }] : undefined);
    await moduluAc("researcher", "ai.modul.bobrekHastaligi.ad");
    await cekirdekDoldur();
    await siradakineBas(T("ai.ckd.secenek.evet"), 0); // htn
    await metneBas(s, T("ai.ckd.analiziBaslat"));
    expect(postlar("/ai/disease/kidney")[0].govde).toEqual({ age: 7, sg: 1.02, al: 1, bu: 40, sc: 1.2, hemo: 13, htn: "yes", explain: true });
    expect(ileti()).toBe(`${T("ortak.hata.sunucuHatasi")}: Kreatinin aralık dışı.`);
  });

  it("gerekçesiz HTTP hatası ve ağ hatası → 'analiz tamamlanamadı'", async () => {
    ozel = (y, _g, m) => (m === "POST" && y === "/ai/disease/kidney" ? [500, {}] : undefined);
    await moduluAc("researcher", "ai.modul.bobrekHastaligi.ad");
    await cekirdekDoldur();
    await metneBas(s, T("ai.ckd.analiziBaslat"));
    expect(ileti()).toBe(aiDetayCumlesi(undefined, T("ai.ckd.tamamlanamadi")));
    jest.spyOn(console, "error").mockImplementation(() => undefined);
    ozel = (y, _g, m) => (m === "POST" && y === "/ai/disease/kidney" ? { hata: new TypeError("Failed to fetch") } : undefined);
    await metneBas(s, T("ai.ckd.analiziBaslat"));
    expect(postlar("/ai/disease/kidney")).toHaveLength(2);
    expect(ileti()).toBe(T("ai.ckd.tamamlanamadi"));
  });
});

// ─────────────────────────── Kedi Sesi (hekim) ───────────────────────────
describe("Kedi Sesi (hekim)", () => {
  it("'Ses Yükle' audio/* seçicisi; 500 → 'Analiz sırasında hata oluştu.'; Error OLMAYAN ret → 'Hata: <ileti>'", async () => {
    ozel = (y, _g, m) => (m === "POST" && y === "/ai/sound/cat" ? [500, { status: "error" }] : undefined);
    await moduluAc("veterinarian", "ai.modul.kediSesi.ad");
    web.dosyaSiradaki = new File([new Uint8Array([1, 2, 3])], "miyav.wav", { type: "audio/wav" });
    await metneBas(s, T("ai.ses.sesYukle"));
    expect(web.acilanSeciciler).toEqual([{ accept: "audio/*", capture: null }]);
    await metneBas(s, T("ai.ses.analiziBaslat"));
    expect((alanlar(postlar("/ai/sound/cat")[0].govde).file as File).name).toBe("miyav.wav");
    expect(ileti()).toBe(T("ai.hata.analizSirasinda"));
    ozel = (y, _g, m) => (m === "POST" && y === "/ai/sound/cat" ? { hata: "tünel kapandı" } : undefined);
    await metneBas(s, T("ai.ses.analiziBaslat"));
    expect(ileti()).toBe(T("ai.hata.hataIleti", { ileti: "tünel kapandı" }));
  });
});

// ─────────────────────────── Yara Kapanma ───────────────────────────
describe("Yara Kapanma (scratch)", () => {
  const blobUrl = (icerik: string) => URL.createObjectURL(new Blob([icerik], { type: "image/png" }));
  async function dosyaSecildi(uri: string, name: string) {
    belgeSec.mockResolvedValueOnce({ canceled: false, assets: [{ uri, name }] });
    await metneBas(s, dugmeMetni());
  }
  /** Dosya düğmesinin o anki metni (seçim yokken "Dosya seç", sonra dosya adı). */
  let dugmeMetni = () => T("ai.scratch.dosyaSec");

  it("iptal → değişmez; blob: seçim analizde blob'dan ÖZGÜN adıyla gider; yeni seçim eskisini bırakır; yön/objektif/ısı haritası gider", async () => {
    ozel = (y, _g, m) =>
      m === "POST" && y === "/ai/vision/scratch" ? [500, { error: "TIFF sıkıştırması desteklenmiyor; PNG olarak dışa aktarın." }] : undefined;
    await moduluAc("researcher", "ai.modul.yaraKapanma.ad");
    belgeSec.mockResolvedValueOnce({ canceled: true });
    await metneBas(s, T("ai.scratch.dosyaSec"));
    expect(belgeSec).toHaveBeenCalledTimes(1);
    expect(s.metin()).toContain(T("ai.scratch.dosyaSec"));
    const u1 = blobUrl("YARA-0");
    dugmeMetni = () => T("ai.scratch.dosyaSec");
    await dosyaSecildi(u1, "yara_0s.png");
    const u2 = blobUrl("YARA-24");
    dugmeMetni = () => "yara_0s.png";
    await dosyaSecildi(u2, "yara_24s.tif");
    expect(web.serbestBirakilan).toContain(u1);
    await metneBas(s, T("ai.scratch.yatay"));
    await metneBas(s, "20×");
    await metneBas(s, `☐${T("ai.scratch.isiHaritasiUret")}`);
    await metneBas(s, T("ai.scratch.analizEt"));
    const a = alanlar(postlar("/ai/vision/scratch")[0].govde);
    expect((a.file as File).name).toBe("yara_24s.tif");
    expect(await blobMetni(a.file)).toBe("YARA-24");
    expect([a.scratch_yonu, a.pixel_mm, a.explain]).toEqual(["yatay", "0.00033", "true"]);
    expect(ileti()).toBe("TIFF sıkıştırması desteklenmiyor; PNG olarak dışa aktarın.");
  });

  it("sonuçtan sonra parametre değişirse 'yeniden analiz' notu; uçuşta parametre değişirse geç yanıt YOK SAYILIR, seçici açılmaz", async () => {
    const BASARI = { status: "success", n_cells: 120, closure: { closure_pct: 42, mean_gap_um: 300, max_gap_um: 500 }, closure_image_base64: "Q0w=" };
    ozel = (y, _g, m) => (m === "POST" && y === "/ai/vision/scratch" ? [200, BASARI] : undefined);
    await moduluAc("researcher", "ai.modul.yaraKapanma.ad");
    dugmeMetni = () => T("ai.scratch.dosyaSec");
    await dosyaSecildi(blobUrl("YARA-A"), "yara_a.png");
    await metneBas(s, T("ai.scratch.analizEt"));
    expect(s.metin()).toContain("300 µm");
    expect(s.metin()).not.toContain(T("ai.scratch.parametreDegisti"));
    await metneBas(s, T("ai.scratch.yatay"));
    expect(s.metin()).toContain(T("ai.scratch.parametreDegisti"));
    // uçuştaki analiz
    const d = askidaUc("/ai/vision/scratch");
    const logOnce = postlar("/ai/log").length;
    await metneBas(s, T("ai.scratch.analizEt"));
    const secimOnce = belgeSec.mock.calls.length;
    await metneBas(s, "yara_a.png"); // analiz sürerken dosya düğmesi
    expect(belgeSec.mock.calls.length).toBe(secimOnce);
    await metneBas(s, "40×");
    await act(async () => { d.serbest(200, { ...BASARI, closure: { closure_pct: 77, mean_gap_um: 111, max_gap_um: 222 } }); });
    await s.bosalt(8);
    expect(s.metin()).not.toContain("111 µm");
    expect(postlar("/ai/log").length).toBe(logOnce);
  });

  it("ağ hatası → 'istek gönderilemedi'", async () => {
    ozel = (y, _g, m) => (m === "POST" && y === "/ai/vision/scratch" ? { hata: new TypeError("Failed to fetch") } : undefined);
    await moduluAc("researcher", "ai.modul.yaraKapanma.ad");
    dugmeMetni = () => T("ai.scratch.dosyaSec");
    await dosyaSecildi(blobUrl("YARA-N"), "yara_n.png");
    await metneBas(s, T("ai.scratch.analizEt"));
    expect(ileti()).toBe(T("ortak.hata.aiGonderilemedi"));
  });
});

// ─────────────────────────── Ortak: uzun analiz + zaman aşımı ───────────────────────────
describe.each([
  {
    ad: "ai.modul.bobrekRna.ad", kip: "researcher" as const, uc: "/ai/rna/kidney", sinir: AI_TIMEOUT_MS, ipucu: "ai.ortak.modelHazirlaniyor",
    hazirla: async () => { web.dosyaSiradaki = new File(["g\n"], "g.csv", { type: "text/csv" }); await metneBas(s, T("ai.rna.csvSec")); },
    baslat: "ai.rna.analiziBaslat",
  },
  {
    ad: "ai.modul.kediSesi.ad", kip: "veterinarian" as const, uc: "/ai/sound/cat", sinir: AI_TIMEOUT_MS, ipucu: "ai.ortak.modelHazirlaniyor",
    hazirla: async () => { web.dosyaSiradaki = new File([new Uint8Array([9])], "m.wav", { type: "audio/wav" }); await metneBas(s, T("ai.ses.sesYukle")); },
    baslat: "ai.ses.analiziBaslat",
  },
  {
    ad: "ai.modul.yaraKapanma.ad", kip: "researcher" as const, uc: "/ai/vision/scratch", sinir: 300_000, ipucu: "ai.scratch.modelHazirlaniyor",
    hazirla: async () => {
      belgeSec.mockResolvedValueOnce({ canceled: false, assets: [{ uri: URL.createObjectURL(new Blob(["Y"], { type: "image/png" })), name: "y.png" }] });
      await metneBas(s, T("ai.scratch.dosyaSec"));
    },
    baslat: "ai.scratch.analizEt",
  },
])("$uc · uzun analiz", (m) => {
  it("8 sn'yi aşınca 'model hazırlanıyor' ipucu; zaman sınırı dolunca istek iptal → zaman aşımı iletisi", async () => {
    jest.spyOn(console, "error").mockImplementation(() => undefined);
    await moduluAc(m.kip, m.ad);
    await m.hazirla();
    const d = askidaUc(m.uc);
    jest.useFakeTimers({ doNotFake: ["queueMicrotask", "nextTick", "Date"] });
    await metneBas(s, T(m.baslat));
    expect(s.metin()).not.toContain(T(m.ipucu));
    await s.ilerlet(8000);
    expect(s.metin()).toContain(T(m.ipucu));
    expect(d.iptal).toBe(false);
    await s.ilerlet(m.sinir);
    await s.bosalt(6);
    expect(d.iptal).toBe(true);
    expect(ileti()).toBe(T("ortak.hata.aiZamanAsimi"));
    expect(s.metin()).not.toContain(T(m.ipucu));
  });
});
