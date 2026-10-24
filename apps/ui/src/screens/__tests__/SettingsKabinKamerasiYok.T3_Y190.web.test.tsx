/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * T3 · Y190 (sahip 2026-10-24: "kamera seçimi de burada olmalı, ayarlar içinde değil") — Ayarlar ekranında "Kabin kamerası" kartı
 * YOK (backend bu makinedeyken de). Ölçülen (3a4c2f5b): kart yalnız Ayarlar'daydı (`backendBuMakinede()` ise); seçim artık petri /
 * fantom analiz panellerinde ve AI Pro panelinde. GERÇEK: SettingsScreen; sahte (ekran dışı): fetch, bağlamlar.
 */
jest.mock("react-native", () => jest.requireActual("react-native-web"));
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: jest.fn() }) }));
jest.mock("@/context/UserModeContext", () => ({
  useUserMode: () => ({ setUserMode: jest.fn(), isExpert: false, isResearcher: true }),
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: null }) }));
jest.mock("@/context/LiveDataContext", () => ({ useLiveData: () => ({ reconnect: jest.fn(), wsConnected: true }) }));
jest.mock("@/hooks/useTeardownGuard", () => ({ useTeardownGuard: () => (f: unknown) => f }));
jest.mock("@/services/discovery", () => ({ checkHealth: jest.fn(), discoverBackend: jest.fn() }));
jest.mock("@/services/supabaseAuth", () => ({ updateProfile: jest.fn() }));
jest.mock("@/services/pairing", () => ({ cihazaBaglan: jest.fn(), eslesmeMesaji: jest.fn() }));
// ⚠️ Bu ortamda (react-native-web + jsdom) `URL` RN çoklu-dolgusudur ve kurucu değildir → gerçek `backendBuMakinede()` HEP false
// döner (ölçüldü: "URL is not a constructor") ve kart zaten çizilmezdi — kapı KÖR kalırdı. Karar açıkça "bu makinede" sabitlenir.
jest.mock("@/services/backendKonumu", () => ({ backendBuMakinede: () => true }));
jest.mock("expo-linear-gradient", () => {
  const R = require("react");
  const { View } = require("react-native-web");
  return { LinearGradient: ({ children, style }: { children?: unknown; style?: unknown }) => R.createElement(View, { style }, children) };
});

import React from "react";
import { SettingsScreen } from "@/screens/SettingsScreen";
import { serviceConfig } from "@/services/config";
import { Sahne } from "../../context/__tests__/operatorAparati";

let s: Sahne;

beforeEach(() => {
  const yanit = (veri: unknown) => {
    const metin = JSON.stringify(veri);
    return { ok: true, status: 200, headers: { get: () => "application/json" }, text: async () => metin, json: async () => veri };
  };
  (global as unknown as { fetch: unknown }).fetch = jest.fn((url: string) =>
    Promise.resolve(yanit(String(url).includes("/settings/kabin-kamerasi") ? { secili: null } : {})),
  );
  s = new Sahne();
});
afterEach(async () => {
  await s.sok();
});

test("KRİTİK: backend bu makinedeyken de Ayarlar'da 'Kabin kamerası' kartı YOK (seçim analiz / AI Pro panelinde)", async () => {
  serviceConfig.apiBaseUrl = "http://127.0.0.1:8000";
  await s.ciz(<SettingsScreen />);
  await s.bosalt(10);
  const m = s.metin();
  expect(m).toContain("Veri Saklama Süresi"); // aparat: ekran gerçekten çizildi
  expect(m).not.toContain("Kabin kamerası");
  expect(m).not.toContain("Kameraları tara");
  expect(document.querySelector('[data-testid="kabin-kamerasi-tara"]')).toBeNull();
});
