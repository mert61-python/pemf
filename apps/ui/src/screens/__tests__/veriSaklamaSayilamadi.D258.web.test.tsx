/**
 * @jest-environment jsdom
 */
/**
 * D2.58 · B-3.90 — Ayarlar → Veri Saklama Süresi: maskelenmeyi bekleyen kayıt sayısı OKUNAMAZSA ekran "0 bekleyen" demez.
 * ===========================================================================================================================
 * ÖLÇÜLEN KUSUR: `redaksiyon_bekleyen_sayisi` DB hatasında 0 dönüyordu → ekran geri dönüşsüz maskeleme sorusunu SORMUYORDU. Backend
 * artık `pending: null` (sayılamadı) döndürüyor; ekran bunu SÖYLEMELİ ve onay düğmesi ÇIKMAMALI (sayı görülmeden onay yok, A-09).
 * GERÇEK: SettingsScreen, apiClient, config. GET yanıtı GERÇEK backend fikstürü (`__fixtures__/retentionSayilamadi.D258.json` —
 * tests/test_pii_redaksiyon_SAYIMLARI_durust_D258.py üretir ve tazeliğini denetler). Sahte (ekran dışı): fetch, bağlamlar.
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
import { Sahne } from "../../context/__tests__/operatorAparati";
import FIKSTUR from "./__fixtures__/retentionSayilamadi.D258.json";

const ONAY_ETIKETI = "Geri dönüşsüz maskelemeyi onayla ve başlat";
let retentionGovde: Record<string, unknown>;
let s: Sahne;

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
  retentionGovde = JSON.parse(JSON.stringify(FIKSTUR.govde));
  (global as unknown as { fetch: unknown }).fetch = jest.fn((url: string, init?: RequestInit) => {
    const yol = String(url).replace(/^[a-z]+:\/\/[^/]+/i, "").replace(/^\/api/, "").split("?")[0];
    const yontem = (init?.method || "GET").toUpperCase();
    if (yol === "/settings/retention" && yontem === "GET") return Promise.resolve(sahteYanit(retentionGovde));
    return Promise.resolve(sahteYanit({}));
  });
  s = new Sahne();
});
afterEach(async () => {
  await s.sok();
});

async function ekran() {
  serviceConfig.apiBaseUrl = "http://127.0.0.1:8000";
  await s.ciz(<SettingsScreen />);
  await s.bosalt(10);
}

test("KRİTİK: bekleyen sayılamadı (null) — '0 bekleyen' yalanı yok, okunamadı denir, onay düğmesi YOK", async () => {
  expect(FIKSTUR.durum).toBe(200);
  expect(FIKSTUR.govde).toMatchObject({ pending: null, acknowledged: false });
  await ekran();
  expect(s.metin()).toMatch(/Maskelenmeyi bekleyen seans kaydı sayısı okunamadı/);
  expect(s.varMi(ONAY_ETIKETI)).toBe(false);
});

test("KARŞIT: sayı okunabiliyorsa (1) uyarı yok, onay düğmesi VAR", async () => {
  retentionGovde.pending = 1;
  await ekran();
  expect(s.metin()).not.toMatch(/okunamadı — tedavi veritabanını/);
  expect(s.varMi(ONAY_ETIKETI)).toBe(true);
});
