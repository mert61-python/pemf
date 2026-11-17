/**
 * @jest-environment jsdom
 */
/**
 * KP-2 · src/screens/SettingsScreen.tsx (WEB / masaüstü yolu) · sözleşmeler:
 *  - yedek alma (LAN yolu): içerik dönmezse "yedek alınamadı" hatası; bozuk base64 → "kaydedilemedi", indirme KURULMAZ;
 *  - parola penceresinde "Vazgeç" → /data/export GÖNDERİLMEZ, düğmeler serbest kalır;
 *  - geri yükleme onayı reddedilirse /data/import GÖNDERİLMEZ;
 *  - web bağlantı testi / yeniden tarama: KENDİ kökenini (/api/health) sınar; başarı / HTTP hatası / ağ hatası ayrı metin;
 *  - eşleştirme kodunu kopyalama: pano varsa yazar + "kopyalandı", pano reddederse değeri pencerede gösterir;
 *  - donanım self-test ve PWM sıfırlama: söküm kapısı + onay; onaysız istek GİTMEZ; sonuç metni sunucu durumuna göre;
 *  - saklama süresi seçeneği → POST /settings/retention {days};
 *  - /settings/ kaydı sunucu reddederse "Kaydetme hatası".
 * (Profil düzenleme yerel dosyada: KP2_SettingsScreen_native.test.tsx — gerçek supabaseAuth jsdom'da yüklenemez: modül düzeyindeki
 *  `new URL(...)` bu ortamda tanımsız; ölçüldü "ReferenceError: URL is not defined". Burada supabaseAuth ekran dışı sahte.)
 * GERÇEK: SettingsScreen, apiClient, config, BackupPassphraseDialog, toastBridge.
 * SAHTE (en alt kat / ekran dışı): fetch, window.confirm / alert, pano, ekranın bağlamları, supabaseAuth (bu dosyada kullanılmaz).
 */
jest.mock("react-native", () => jest.requireActual("react-native-web"));
const mockToast = jest.fn();
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: mockToast }) }));
const mockKip = { isExpert: true, isResearcher: false };
const mockSetUserMode = jest.fn();
jest.mock("@/context/UserModeContext", () => ({
  useUserMode: () => ({ setUserMode: mockSetUserMode, ...mockKip }),
}));
const mockOturum: { session: unknown } = { session: null };
jest.mock("@/context/AuthContext", () => ({ useAuth: () => mockOturum }));
const mockReconnect = jest.fn();
jest.mock("@/context/LiveDataContext", () => ({ useLiveData: () => ({ reconnect: mockReconnect, wsConnected: true }) }));
const mockGuard = jest.fn(async (_e: string) => true);
jest.mock("@/hooks/useTeardownGuard", () => ({ useTeardownGuard: () => (e: string) => mockGuard(e) }));
jest.mock("@/services/supabaseAuth", () => ({ updateProfile: jest.fn() }));
jest.mock("expo-linear-gradient", () => {
  const R = require("react");
  const { View } = require("react-native-web");
  return { LinearGradient: ({ children, style }: { children?: unknown; style?: unknown }) => R.createElement(View, { style }, children) };
});

import React, { act } from "react";
import i18n from "i18next";
import { SettingsScreen } from "@/screens/SettingsScreen";
import { serviceConfig } from "@/services/config";
import { setToastHandler } from "@/services/toastBridge";
import { Sahne } from "../../context/__tests__/operatorAparati";

const t = (k: string, o?: Record<string, unknown>) => i18n.t(k, o as never) as unknown as string;
const PAROLA = "klinik-yedek-2026-kp2";
const NodeURL = require("url").URL;

type Cagri = { url: string; yol: string; yontem: string; govde: Record<string, unknown> | null };
let cagrilar: Cagri[];
let ozel: (yol: string, yontem: string, url: string, init?: RequestInit) => unknown | undefined;
let s: Sahne;
let eskiURL: unknown;
let eskiTaban: string;
const mockApiHata = jest.fn();

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

const RETENTION = { days: 365, configured: true, acknowledged: true, pending: 0, default: 365 };

beforeEach(() => {
  jest.useFakeTimers();
  mockToast.mockReset();
  mockApiHata.mockReset();
  mockGuard.mockReset();
  mockGuard.mockResolvedValue(true);
  mockReconnect.mockReset();
  mockKip.isExpert = true;
  mockKip.isResearcher = false;
  mockOturum.session = null;
  setToastHandler((m: string, tur?: string) => mockApiHata(m, tur));
  eskiURL = (global as unknown as { URL: unknown }).URL;
  const U = class extends NodeURL {} as unknown as { createObjectURL: unknown; revokeObjectURL: unknown };
  U.createObjectURL = jest.fn(() => "blob:yedek");
  U.revokeObjectURL = jest.fn();
  (global as unknown as { URL: unknown }).URL = U;
  eskiTaban = serviceConfig.apiBaseUrl;
  cagrilar = [];
  ozel = () => undefined;
  (global as unknown as { fetch: unknown }).fetch = jest.fn((url: string, init?: RequestInit) => {
    const yol = String(url).replace(/^[a-z]+:\/\/[^/]+/i, "").replace(/^\/api/, "").split("?")[0];
    const yontem = (init?.method || "GET").toUpperCase();
    cagrilar.push({ url: String(url), yol, yontem, govde: init?.body ? JSON.parse(String(init.body)) : null });
    const o = ozel(yol, yontem, String(url), init);
    if (o instanceof Error) return Promise.reject(o);
    if (o !== undefined) return Promise.resolve(o);
    if (yol === "/settings/retention" && yontem === "GET") return Promise.resolve(sahteYanit(RETENTION));
    if (yol === "/health") return Promise.resolve(sahteYanit({ pairingCode: "KP2KOD", deviceId: "cihaz-kp2-0001", cloudRegistry: "ok" }));
    return Promise.resolve(sahteYanit({}));
  });
  s = new Sahne();
});

afterEach(async () => {
  await s.sok();
  setToastHandler(null);
  (global as unknown as { URL: unknown }).URL = eskiURL;
  serviceConfig.apiBaseUrl = eskiTaban;
  jest.clearAllTimers();
  jest.useRealTimers();
  delete (navigator as unknown as { clipboard?: unknown }).clipboard;
});

async function ekran(taban = "http://127.0.0.1:8000/api") {
  serviceConfig.apiBaseUrl = taban;
  await s.ciz(<SettingsScreen />);
  await s.bosalt(10);
}

const toastlar = () => mockToast.mock.calls.map((c) => [String(c[0]), c[1]] as [string, unknown]);
const istek = (yol: string, yontem = "POST") => cagrilar.filter((c) => c.yol === yol && c.yontem === yontem);

// ── Veri taşıma (yedek) ─────────────────────────────────────────────────────────────────────────────────────────────────────
async function disaAktarBaslat() {
  await s.tikla(t("ayarlar.veriTasima.disaAktarEtiketi"));
  await s.yaz(t("ayarlar.yedekParola.parolaEtiketi"), PAROLA);
  await s.yaz(t("ayarlar.yedekParola.tekrarEtiketi"), PAROLA);
  await s.tikla(t("ayarlar.yedekParola.olusturEtiketi"));
  await s.bosalt(10);
}

describe("yedek alma (tarayıcı / LAN yolu) — dosya içeriği doğrulanmadan 'indirme başladı' DENMEZ", () => {
  test("LAN yolunda yanıt data_b64 taşımıyor → 'yedek alınamadı' hatası, indirme kurulmaz", async () => {
    const indir = jest.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    ozel = (yol, yontem) => (yol === "/data/export" && yontem === "POST" ? sahteYanit({ status: "success", counts: { patients: 2 } }) : undefined);
    try {
      await ekran("http://192.168.1.50:8000/api");
      await disaAktarBaslat();
      expect(istek("/data/export")).toHaveLength(1);
      expect(istek("/data/export")[0].govde).toEqual({ passphrase: PAROLA });
      expect(toastlar()).toEqual([[t("ayarlar.yedek.icerikYok"), "error"]]);
      expect(indir).not.toHaveBeenCalled();
    } finally {
      indir.mockRestore();
    }
  });

  test("LAN yolunda data_b64 bozuk (çözülemez base64) → 'yedek dosyası kaydedilemedi', indirme/başarı metni YOK", async () => {
    const indir = jest.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    ozel = (yol, yontem) =>
      yol === "/data/export" && yontem === "POST"
        ? sahteYanit({ status: "success", filename: "x.pemfbak", data_b64: "@@bozuk base64@@", counts: { patients: 1 } })
        : undefined;
    try {
      await ekran("http://192.168.1.50:8000/api");
      await disaAktarBaslat();
      expect(toastlar()).toEqual([[t("ayarlar.yedek.kaydedilemedi"), "error"]]);
      expect(indir).not.toHaveBeenCalled();
    } finally {
      indir.mockRestore();
    }
  });

  test("parola penceresinde 'Vazgeç' → /data/export GÖNDERİLMEZ, düğme serbest; sonraki gerçek yedek TEK istek gönderir", async () => {
    ozel = (yol, yontem) => (yol === "/data/export" && yontem === "POST" ? sahteYanit({ status: "success", counts: {} }) : undefined);
    await ekran("http://192.168.1.50:8000/api");
    await s.tikla(t("ayarlar.veriTasima.disaAktarEtiketi"));
    expect(s.varMi(t("ayarlar.yedekParola.parolaEtiketi"))).toBe(true);
    await s.tikla(t("ortak.vazgec"));
    await s.bosalt(5);
    expect(istek("/data/export")).toHaveLength(0);
    expect(s.etiket(t("ayarlar.veriTasima.disaAktarEtiketi")).getAttribute("aria-disabled")).not.toBe("true");
    expect(s.metin()).not.toContain(t("ayarlar.veriTasima.hazirlaniyor"));
    expect(mockToast).not.toHaveBeenCalled();
    // vazgeçilen söz null ile çözüldü: yeni deneme yalnız KENDİ isteğini gönderir (eski bekleyen akış canlanmaz)
    await disaAktarBaslat();
    expect(istek("/data/export")).toHaveLength(1);
  });

  test("geri yükleme: 'geri yükle' onayı REDDEDİLİRSE /data/import gönderilmez, düğmeler kilitlenmez", async () => {
    await ekran("http://127.0.0.1:8000/api");
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
    let onayMetni = "";
    const onay = jest.spyOn(window, "confirm").mockImplementation((m?: string) => {
      onayMetni = String(m ?? "");
      return false;
    });
    try {
      await s.tikla(t("ayarlar.veriTasima.geriYukleEtiketi"));
      const dosya = { name: "yedek.pemfbak", arrayBuffer: async () => new Uint8Array([80, 69, 77, 70]).buffer };
      Object.defineProperty(girdi!, "files", { value: [dosya] });
      await act(async () => { void (girdi as unknown as { onchange: () => Promise<void> }).onchange(); });
      await s.bosalt();
      await s.yaz(t("ayarlar.yedekParola.parolaEtiketi"), PAROLA);
      await s.tikla(t("ayarlar.yedekParola.devamEtiketi"));
      await s.bosalt(10);
    } finally {
      casus.mockRestore();
      onay.mockRestore();
    }
    expect(onayMetni).toContain(t("ayarlar.yedek.geriYukleBaslik"));
    expect(istek("/data/import")).toHaveLength(0);
    expect(s.metin()).not.toContain(t("ayarlar.veriTasima.yukleniyor"));
    expect(s.etiket(t("ayarlar.veriTasima.geriYukleEtiketi")).getAttribute("aria-disabled")).not.toBe("true");
  });
});

// ── Bağlantı (web: kendi kökeni) ───────────────────────────────────────────────────────────────────────────────────────────────
describe("web bağlantı testi / yeniden tarama — taban DEĞİŞMEZ, kendi kökeni sınanır", () => {
  const kokenSaglik = (c: Cagri) => c.url === `${window.location.origin}/api/health`;

  test("Test Et: köken /api/health 200 → 'Bağlı' rozeti + 'sunucuya bağlısınız'; taban yeniden yönlendirilmez", async () => {
    await ekran("http://127.0.0.1:8000/api");
    await s.metneTikla(t("ayarlar.baglanti.testEt"));
    await s.bosalt(5);
    expect(cagrilar.filter(kokenSaglik)).toHaveLength(1);
    expect(toastlar()).toEqual([[t("ayarlar.baglanti.bagli"), "success"]]);
    expect(s.metin()).toContain(t("ayarlar.baglanti.durumBagli"));
    expect(serviceConfig.apiBaseUrl).toBe("http://127.0.0.1:8000/api");
    expect(mockReconnect).not.toHaveBeenCalled();
  });

  test("Test Et: köken 503 → 'Bağlanamadı' + 'sunucuya ulaşılamadı' (error)", async () => {
    ozel = (_y, _m, url) => (url === `${window.location.origin}/api/health` ? sahteYanit({}, 503) : undefined);
    await ekran();
    await s.metneTikla(t("ayarlar.baglanti.testEt"));
    await s.bosalt(5);
    expect(toastlar()).toEqual([[t("ayarlar.baglanti.ulasilamadi"), "error"]]);
    expect(s.metin()).toContain(t("ayarlar.baglanti.durumBaglanamadi"));
  });

  test("Test Et: ağ hatası (fetch reddi) → 'zaman aşımı' metni, arama kilidi kalkar", async () => {
    ozel = (_y, _m, url) => (url === `${window.location.origin}/api/health` ? new TypeError("Failed to fetch") : undefined);
    await ekran();
    await s.metneTikla(t("ayarlar.baglanti.testEt"));
    await s.bosalt(5);
    expect(toastlar()).toEqual([[t("ayarlar.baglanti.zamanAsimi"), "error"]]);
    expect(s.metin()).toContain(t("ayarlar.baglanti.durumBaglanamadi"));
    expect(s.metin()).toContain(t("ayarlar.baglanti.yenidenTara"));
    expect(s.metin()).not.toContain(t("ayarlar.baglanti.araniyor"));
  });

  test("Yeniden Tara (web): köken 200 → 'bu sayfanın sunucusu' metni; keşif taraması YAPILMAZ (tek istek)", async () => {
    await ekran();
    const once = cagrilar.length;
    await s.metneTikla(t("ayarlar.baglanti.yenidenTara"));
    await s.bosalt(5);
    expect(cagrilar.slice(once).map((c) => c.url)).toEqual([`${window.location.origin}/api/health`]);
    expect(toastlar()).toEqual([[t("ayarlar.baglanti.bagliBuSayfa"), "success"]]);
    expect(s.metin()).toContain(t("ayarlar.baglanti.durumBagli"));
  });

  test("Yeniden Tara (web): köken 500 → 'ulaşılamadı' (error); fetch reddi → aynı metin, 'Bağlanamadı' rozeti", async () => {
    ozel = (_y, _m, url) => (url === `${window.location.origin}/api/health` ? sahteYanit({}, 500) : undefined);
    await ekran();
    await s.metneTikla(t("ayarlar.baglanti.yenidenTara"));
    await s.bosalt(5);
    expect(toastlar()).toEqual([[t("ayarlar.baglanti.ulasilamadi"), "error"]]);
    mockToast.mockReset();
    ozel = (_y, _m, url) => (url === `${window.location.origin}/api/health` ? new TypeError("Failed to fetch") : undefined);
    await s.metneTikla(t("ayarlar.baglanti.yenidenTara"));
    await s.bosalt(5);
    expect(toastlar()).toEqual([[t("ayarlar.baglanti.ulasilamadi"), "error"]]);
    expect(s.metin()).toContain(t("ayarlar.baglanti.durumBaglanamadi"));
  });
});

// ── KP-7 B (işlev ölçüsü): zamanlı kollar ────────────────────────────────────────────────────────────────────────────────────
describe("KP-7 B · zamanlı kollar — askıdaki köken yoklaması kesilir, indirme adresi ve kayıt satırı gecikmeyle temizlenir", () => {
  const KOKEN = () => `${window.location.origin}/api/health`;
  /** İstek ASKIDA kalır; yalnız iptal sinyaliyle reddedilir (yanıt vermeyen sunucu). */
  const askida = (init?: RequestInit) =>
    new Promise((_coz, reddet) => {
      (init?.signal as AbortSignal | undefined)?.addEventListener("abort", () => reddet(new Error("AbortError")));
    });

  test("Test Et: köken yanıt vermezse 5 sn sonra kesilir → 'zaman aşımı', arama kilidi kalkar", async () => {
    ozel = (_y, _m, url, init) => (url === KOKEN() ? askida(init) : undefined);
    await ekran();
    await s.metneTikla(t("ayarlar.baglanti.testEt"));
    await act(async () => { jest.advanceTimersByTime(4999); });
    await s.bosalt(5);
    expect(toastlar()).toEqual([]);
    await act(async () => { jest.advanceTimersByTime(1); });
    await s.bosalt(5);
    expect(toastlar()).toEqual([[t("ayarlar.baglanti.zamanAsimi"), "error"]]);
    expect(s.metin()).not.toContain(t("ayarlar.baglanti.araniyor"));
  });

  test("Yeniden Tara (web): köken yanıt vermezse 5 sn sonra kesilir → 'ulaşılamadı', 'Bağlanamadı' rozeti", async () => {
    ozel = (_y, _m, url, init) => (url === KOKEN() ? askida(init) : undefined);
    await ekran();
    await s.metneTikla(t("ayarlar.baglanti.yenidenTara"));
    await act(async () => { jest.advanceTimersByTime(4999); });
    await s.bosalt(5);
    expect(toastlar()).toEqual([]);
    await act(async () => { jest.advanceTimersByTime(1); });
    await s.bosalt(5);
    expect(toastlar()).toEqual([[t("ayarlar.baglanti.ulasilamadi"), "error"]]);
    expect(s.metin()).toContain(t("ayarlar.baglanti.durumBaglanamadi"));
  });

  test("LAN yedeği indirilince nesne adresi 10 sn SONRA bırakılır (hemen değil — indirme kesilmesin)", async () => {
    const indir = jest.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    ozel = (yol, yontem) =>
      yol === "/data/export" && yontem === "POST"
        ? sahteYanit({ status: "success", filename: "y.pemfbak", data_b64: "UEVNRg==", counts: { patients: 1 } })
        : undefined;
    const birak = (global as unknown as { URL: { revokeObjectURL: jest.Mock } }).URL.revokeObjectURL;
    try {
      await ekran("http://192.168.1.50:8000/api");
      await disaAktarBaslat();
      expect(indir).toHaveBeenCalledTimes(1);
      await act(async () => { jest.advanceTimersByTime(9999); });
      expect(birak).not.toHaveBeenCalled();
      await act(async () => { jest.advanceTimersByTime(1); });
      expect(birak).toHaveBeenCalledWith("blob:yedek");
    } finally {
      indir.mockRestore();
    }
  });

  test("ayar kaydı başarılıysa 'Kaydedildi' satırı 3 sn sonra kendiliğinden silinir", async () => {
    ozel = (yol, yontem) => (yol === "/settings/" && yontem === "POST" ? sahteYanit({ status: "success" }) : undefined);
    await ekran();
    await s.metneTikla(t("ayarlar.kaydetDugme"));
    await s.bosalt(5);
    expect(s.metin()).toContain(t("ayarlar.kaydedildi"));
    await act(async () => { jest.advanceTimersByTime(2999); });
    expect(s.metin()).toContain(t("ayarlar.kaydedildi"));
    await act(async () => { jest.advanceTimersByTime(1); });
    expect(s.metin()).not.toContain(t("ayarlar.kaydedildi"));
  });
});

// ── Kopyalama ────────────────────────────────────────────────────────────────────────────────────────────────────────────────
describe("eşleştirme kimliğini kopyalama (web)", () => {
  test("pano varsa kod panoya yazılır ve '<etiket> panoya kopyalandı' (success)", async () => {
    const yaz = jest.fn(async (_v: string) => undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText: yaz }, configurable: true });
    await ekran();
    await s.metneTikla("KP2KOD");
    expect(yaz).toHaveBeenCalledWith("KP2KOD");
    expect(toastlar()).toEqual([[t("ayarlar.kopyala.kopyalandi", { etiket: t("ayarlar.eslestirme.kod") }), "success"]]);
  });

  test("pano yazımı reddedilirse değer pencerede (alert) gösterilir, 'kopyalandı' DENMEZ", async () => {
    Object.defineProperty(navigator, "clipboard", { value: { writeText: async () => { throw new Error("izin yok"); } }, configurable: true });
    const uyari = jest.spyOn(window, "alert").mockImplementation(() => {});
    try {
      await ekran();
      await s.metneTikla("KP2KOD");
      expect(uyari).toHaveBeenCalledWith(`${t("ayarlar.eslestirme.kod")}\nKP2KOD`);
      expect(mockToast).not.toHaveBeenCalled();
    } finally {
      uyari.mockRestore();
    }
  });

  test("pano API'si YOKSA cihaz kimliği 'elle kopyalayın' metniyle pencerede gösterilir", async () => {
    const uyari = jest.spyOn(window, "alert").mockImplementation(() => {});
    try {
      await ekran();
      await s.metneTikla("cihaz-kp2-0001");
      expect(uyari).toHaveBeenCalledWith(
        `${t("ayarlar.eslestirme.cihazKimligi")}\n${t("ayarlar.kopyala.elle", { deger: "cihaz-kp2-0001" })}`,
      );
    } finally {
      uyari.mockRestore();
    }
  });
});

// ── Bakım (self-test / PWM) ─────────────────────────────────────────────────────────────────────────────────────────────────
describe("donanım bakım — onaysız komut GİTMEZ, sonuç sunucu durumuna göre", () => {
  test("self-test: söküm kapısı + onay → POST /hardware/selftest; success → 'gönderildi'", async () => {
    ozel = (yol, yontem) => (yol === "/hardware/selftest" && yontem === "POST" ? sahteYanit({ status: "success" }) : undefined);
    const onay = jest.spyOn(window, "confirm").mockReturnValue(true);
    try {
      await ekran();
      await s.metneTikla(t("ayarlar.bakim.selfTestDugme"));
      await s.bosalt(5);
      expect(mockGuard).toHaveBeenCalledWith(t("ayarlar.bakim.selfTestEylem"));
      expect(onay.mock.calls[0][0]).toContain(t("ayarlar.bakim.selfTestBaslik"));
      expect(istek("/hardware/selftest")).toHaveLength(1);
      expect(toastlar()).toEqual([[t("ayarlar.bakim.selfTestGonderildi"), "success"]]);
    } finally {
      onay.mockRestore();
    }
  });

  test("self-test: sunucu success DÖNMEZSE 'gönderilemedi' (error)", async () => {
    ozel = (yol, yontem) => (yol === "/hardware/selftest" && yontem === "POST" ? sahteYanit({ status: "busy" }) : undefined);
    const onay = jest.spyOn(window, "confirm").mockReturnValue(true);
    try {
      await ekran();
      await s.metneTikla(t("ayarlar.bakim.selfTestDugme"));
      await s.bosalt(5);
      expect(toastlar()).toEqual([[t("ayarlar.bakim.selfTestGonderilemedi"), "error"]]);
    } finally {
      onay.mockRestore();
    }
  });

  test("self-test: seans sürüyor (söküm kapısı reddi) → onay bile sorulmaz, istek GİTMEZ; onay reddi → istek GİTMEZ", async () => {
    const onay = jest.spyOn(window, "confirm").mockReturnValue(false);
    try {
      mockGuard.mockResolvedValue(false);
      await ekran();
      await s.metneTikla(t("ayarlar.bakim.selfTestDugme"));
      await s.bosalt(5);
      expect(onay).not.toHaveBeenCalled();
      mockGuard.mockResolvedValue(true);
      await s.metneTikla(t("ayarlar.bakim.selfTestDugme"));
      await s.bosalt(5);
      expect(onay).toHaveBeenCalledTimes(1);
      expect(istek("/hardware/selftest")).toHaveLength(0);
      expect(mockToast).not.toHaveBeenCalled();
    } finally {
      onay.mockRestore();
    }
  });

  test("PWM sıfırlama: onay → POST /hardware/reset_pwm; success → 'sıfırlandı', hata → 'başarısız'; onay reddi → istek yok", async () => {
    let durum = "success";
    ozel = (yol, yontem) => (yol === "/hardware/reset_pwm" && yontem === "POST" ? sahteYanit({ status: durum }) : undefined);
    const onay = jest.spyOn(window, "confirm").mockReturnValue(false);
    try {
      await ekran();
      await s.metneTikla(t("ayarlar.bakim.pwmDugme"));
      await s.bosalt(5);
      expect(onay.mock.calls[0][0]).toContain(t("ayarlar.bakim.pwmBaslik"));
      expect(istek("/hardware/reset_pwm")).toHaveLength(0);
      expect(mockGuard).not.toHaveBeenCalled(); // bu eylemin kendisi durdurmadır — söküm kapısı sorulmaz
      onay.mockReturnValue(true);
      await s.metneTikla(t("ayarlar.bakim.pwmDugme"));
      await s.bosalt(5);
      expect(istek("/hardware/reset_pwm")).toHaveLength(1);
      expect(toastlar()).toEqual([[t("ayarlar.bakim.pwmSifirlandi"), "success"]]);
      durum = "error";
      mockToast.mockReset();
      await s.metneTikla(t("ayarlar.bakim.pwmDugme"));
      await s.bosalt(5);
      expect(toastlar()).toEqual([[t("ayarlar.bakim.pwmBasarisiz"), "error"]]);
    } finally {
      onay.mockRestore();
    }
  });
});

// ── Saklama süresi / Kaydet ──────────────────────────────────────────────────────────────────────────────────────────────────
describe("saklama süresi seçimi ve ayar kaydı", () => {
  test("'2 yıl' seçeneği → POST /settings/retention {days: 730}, ardından durum YENİDEN okunur", async () => {
    await ekran();
    const getOnce = istek("/settings/retention", "GET").length;
    await s.tikla(t("ayarlar.saklama.sureEtiketi", { gun: 730 }));
    await s.bosalt(5);
    expect(istek("/settings/retention").map((c) => c.govde)).toEqual([{ days: 730 }]);
    expect(istek("/settings/retention", "GET").length).toBe(getOnce + 1);
  });

  test("/settings/ kaydını sunucu reddederse (500) durum satırı 'Kaydetme hatası.' der", async () => {
    ozel = (yol, yontem) => (yol === "/settings/" && yontem === "POST" ? sahteYanit({ detail: "db kilitli" }, 500) : undefined);
    await ekran();
    await s.metneTikla(t("ayarlar.kaydetDugme"));
    await s.bosalt(5);
    expect(istek("/settings/")).toHaveLength(1);
    expect(s.metin()).toContain(t("ayarlar.kayitHatasi"));
    expect(s.metin()).not.toContain(t("ayarlar.kaydedildi"));
  });
});
