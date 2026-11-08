/**
 * @jest-environment jsdom
 */
/**
 * KP-3 C · Ayarlar → Veri Saklama: anonimleştirme son turunun ZAMANI bilinmiyorsa (denetim satırında `ts_utc` yok) metin SEÇİLİ DİLDE
 * söylenir — İngilizce arayüzde "Last run: Unknown", Türkçede "Son tur: Bilinmiyor".
 * ÖLÇÜLEN KUSUR (KP-3, 11-08): `sonTurZamani` zaman yoksa SABİT Türkçe "bilinmiyor" döndürüyordu → İngilizce arayüzde
 * "Last run: bilinmiyor — patients: 2." (her yeni metin iki dilde kuralı).
 * GERÇEK: SettingsScreen, apiClient, config, i18n. GET yanıtı GERÇEK backend fikstürü (D254) + `lastRun` zamansız. Sahte: fetch, bağlamlar.
 */
jest.mock("react-native", () => jest.requireActual("react-native-web"));
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: jest.fn() }) }));
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
import i18n from "i18next";
import { SettingsScreen } from "@/screens/SettingsScreen";
import { serviceConfig } from "@/services/config";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { Sahne } from "../../context/__tests__/operatorAparati";
import FIKSTUR from "./__fixtures__/retentionAnonim.D254.json";

let s: Sahne;
beforeEach(() => {
  const govde = JSON.parse(JSON.stringify(FIKSTUR.govde));
  govde.anonymization.acknowledged = true;
  govde.anonymization.lastRun = { at: null, count: 2 };
  (global as unknown as { fetch: unknown }).fetch = jest.fn((url: string, init?: RequestInit) => {
    const yol = String(url).replace(/^[a-z]+:\/\/[^/]+/i, "").replace(/^\/api/, "").split("?")[0];
    const veri = yol === "/settings/retention" && (init?.method || "GET").toUpperCase() === "GET" ? govde : {};
    const metin = JSON.stringify(veri);
    return Promise.resolve({ ok: true, status: 200, headers: { get: () => "application/json" }, text: async () => metin, json: async () => JSON.parse(metin) });
  });
  s = new Sahne();
});
afterEach(async () => {
  await s.sok();
  __bayrakTestiAyarla(null);
  await i18n.changeLanguage("tr");
});

async function ekran() {
  serviceConfig.apiBaseUrl = "http://127.0.0.1:18080";
  await s.ciz(<SettingsScreen />);
  await s.bosalt(10);
}

it("İngilizce arayüzde zamanı bilinmeyen son tur 'Last run: Unknown' der (Türkçe sızmaz)", async () => {
  __bayrakTestiAyarla(true); // jest.setup kuralı: İngilizceyi deneyen test bayrağı açıkça açar, sonunda geri alır
  await i18n.changeLanguage("en");
  await ekran();
  expect(s.metin()).toMatch(/Last run: Unknown — patients: 2\./);
  expect(s.metin()).not.toMatch(/bilinmiyor/i);
});

it("Türkçe arayüzde 'Son tur: Bilinmiyor'", async () => {
  await ekran();
  expect(s.metin()).toMatch(/Son tur: Bilinmiyor — 2 hasta\./);
});
