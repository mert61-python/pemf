/**
 * @jest-environment jsdom
 */
/**
 * SG.G3 (sahip gözlemi 2026-10-13) — Araştırma profilinin Ayarlar ekranında "Donanım Bakım ve Servis", "Veri Taşıma (Cihaz
 * Değişimi)" ve "Veri Saklama Süresi" kartları YOKTU (üçü de `isExpert` = yalnız veteriner koşullu). Sahip: "araştırma profilinin
 * ayarlar kısmında bunlar da olmalı veterinerde var araştırmada yok."
 * Ek (görselde ölçüldü): saklama süresi düğmeleri `flex: 0` ile web'de esas genişliği %0 alıyor ("Kapalı" taşıyor, "1 yıl" kırılıyor)
 * ve seçili süre ayırt edilmiyordu (seçili ile seçilmeyenin kenar / yazı rengi AYNI).
 * GERÇEK: SettingsScreen, apiClient, config; retention GET yanıtı GERÇEK backend fikstürü. Sahte (ekran dışı): fetch, bağlamlar.
 */
jest.mock("react-native", () => jest.requireActual("react-native-web"));
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: jest.fn() }) }));
const mockKip = { isExpert: false, isResearcher: true };
jest.mock("@/context/UserModeContext", () => ({
  useUserMode: () => ({ setUserMode: jest.fn(), ...mockKip }),
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
import { Sahne } from "../../context/__tests__/operatorAparati";
import YENI from "./__fixtures__/retentionYeniKlinik.F235.json";

let s: Sahne;

function sahteYanit(veri: unknown, durum = 200) {
  const metin = JSON.stringify(veri);
  return {
    ok: durum >= 200 && durum < 300,
    status: durum,
    headers: { get: () => "application/json" },
    text: async () => metin,
    json: async () => JSON.parse(metin),
  };
}

beforeEach(() => {
  (global as unknown as { fetch: unknown }).fetch = jest.fn((url: string, init?: RequestInit) => {
    const yol = String(url).replace(/^[a-z]+:\/\/[^/]+/i, "").replace(/^\/api/, "").split("?")[0];
    const yontem = (init?.method || "GET").toUpperCase();
    if (yol === "/settings/retention" && yontem === "GET") return Promise.resolve(sahteYanit(YENI.govde));
    return Promise.resolve(sahteYanit({}));
  });
  s = new Sahne();
});
afterEach(async () => {
  await s.sok();
});

async function ciz(isExpert: boolean, isResearcher: boolean): Promise<string> {
  mockKip.isExpert = isExpert;
  mockKip.isResearcher = isResearcher;
  serviceConfig.apiBaseUrl = "http://127.0.0.1:8000";
  await s.ciz(<SettingsScreen />);
  await s.bosalt(10);
  return s.metin();
}

const KARTLAR = ["Donanım Bakım ve Servis", "Veri Taşıma (Cihaz Değişimi)", "Veri Saklama Süresi"];

test("KRİTİK: ARAŞTIRMA profilinde bakım, taşıma ve saklama kartları VAR ve kapsamın cihaz geneli olduğunu söyler", async () => {
  const m = await ciz(false, true);
  for (const k of KARTLAR) expect(m).toContain(k);
  expect(m).toContain("Bu cihazdaki TÜM kayıtlar — klinik ve araştırma");
  expect(m).toContain("Saklama süresi bu cihazdaki TÜM seans kayıtlarına uygulanır (klinik ve araştırma).");
  expect(s.varMi("Bu cihazdaki tüm kayıtları şifreli dosyaya aktar")).toBe(true);
});

test("KARŞIT: VETERİNER profilinde üç kart AYNEN (araştırma metni yok)", async () => {
  const m = await ciz(true, false);
  for (const k of KARTLAR) expect(m).toContain(k);
  expect(m).not.toContain("klinik ve araştırma");
  expect(s.varMi("Klinik verilerini şifreli dosyaya aktar")).toBe(true);
});

test("KRİTİK: EV SAHİBİ profilinde üç kart GİZLİ kalır (KVKK)", async () => {
  const m = await ciz(false, false);
  for (const k of KARTLAR) expect(m).not.toContain(k);
});

test("KRİTİK: saklama süresi seçeneklerinde SEÇİLİ olan erişilebilir durumla ve görsel olarak ayırt edilir", async () => {
  await ciz(true, false);
  const secili = s.etiket("Saklama süresi 365 gün");
  const digerleri = ["Maskelemeyi kapat", "Saklama süresi 730 gün", "Saklama süresi 1825 gün"].map((a) => s.etiket(a));
  expect(secili.getAttribute("aria-selected")).toBe("true");
  for (const d of digerleri) expect(d.getAttribute("aria-selected")).toBe("false");
  const arka = (e: HTMLElement) => window.getComputedStyle(e).backgroundColor;
  expect(arka(secili)).not.toBe(arka(digerleri[0]));
});
