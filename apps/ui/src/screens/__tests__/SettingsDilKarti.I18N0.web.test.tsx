/**
 * @jest-environment jsdom
 */
/**
 * I18N-0 · Ayarlar'daki "Dil / Language" kartı İngilizce BAYRAĞINA bağlı (Y158): kapalıyken HİÇ çizilmez (Türkçe görünüm aynen),
 * açıkken görünür. Koşum takımı `SettingsUzmanKartlari.SG_G3.web.test.tsx` ile aynı.
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
import { SettingsScreen } from "@/screens/SettingsScreen";
import { serviceConfig } from "@/services/config";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { Sahne } from "../../context/__tests__/operatorAparati";

let s: Sahne;

beforeEach(() => {
  (global as unknown as { fetch: unknown }).fetch = jest.fn(() =>
    Promise.resolve({ ok: true, status: 200, headers: { get: () => "application/json" }, text: async () => "{}", json: async () => ({}) }),
  );
  s = new Sahne();
});
afterEach(async () => {
  __bayrakTestiAyarla(null);
  await s.sok();
});

async function ciz(): Promise<string> {
  serviceConfig.apiBaseUrl = "http://127.0.0.1:8000";
  await s.ciz(<SettingsScreen />);
  await s.bosalt(10);
  return s.metin();
}

it("bayrak KAPALI (bugün): dil kartı YOK — Türkçe Ayarlar ekranı göçten önceki gibi", async () => {
  const metin = await ciz();
  expect(metin).toContain("Sistem Ayarları");
  expect(metin).not.toContain("Dil / Language");
  expect(metin).not.toContain("English");
});

it("bayrak AÇIK (inceleme sonrası): dil kartı görünür, iki seçenek kendi dilinde yazılı", async () => {
  __bayrakTestiAyarla(true);
  const metin = await ciz();
  expect(metin).toContain("Dil / Language");
  expect(metin).toContain("Türkçe");
  expect(metin).toContain("English");
});
