/**
 * @jest-environment jsdom
 */
/**
 * F2-3.5 (2-F incelemesi A3, K2 · A-06 / A-38) — Ayarlar → Veri Saklama Süresi kartı maskelemenin ONAYSIZ başlamadığını söyler.
 * ===========================================================================================================================
 * Davranış (ölçüldü, tests/test_veri_saklama_karti_ONAYSIZ_maskeleme_BASLAMAZ_F235.py — fikstürleri de o üretir ve tazeliğini
 * denetler): yeni klinikte `/api/settings/retention` = {days: 365,
 * acknowledged: false, pending: 0}; GERÇEK bakım turu onaysız HİÇBİR adı maskelemez. Legal §6: "maskelenmesi varsayılan olarak
 * KAPALIdır ve klinik açıkça onaylamadan başlamaz". Kart ise onaysız durumda "adlar 365 gün sonra kalıcı olarak maskelenir" diyordu.
 * GERÇEK: SettingsScreen, apiClient, config; GET yanıtları GERÇEK backend yanıtı (fikstür). Sahte (ekran dışı): fetch, bağlamlar.
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
import YENI from "./__fixtures__/retentionYeniKlinik.F235.json";
import BEKLEYEN from "./__fixtures__/retentionOnaysizBekleyen.F235.json";

let govde: Record<string, unknown>;
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
    if (yol === "/settings/retention" && yontem === "GET") return Promise.resolve(sahteYanit(govde));
    return Promise.resolve(sahteYanit({}));
  });
  s = new Sahne();
});
afterEach(async () => {
  await s.sok();
});

async function kart(): Promise<string> {
  serviceConfig.apiBaseUrl = "http://127.0.0.1:8000";
  await s.ciz(<SettingsScreen />);
  await s.bosalt(10);
  const metin = s.metin();
  const i = metin.indexOf("Veri Saklama Süresi");
  expect(i).toBeGreaterThanOrEqual(0); // aparat: kart çizildi
  const j = metin.indexOf("Hakkında", i);
  return metin.slice(i, j > i ? j : undefined);
}

test("KRİTİK: yeni klinik (onay YOK, bekleyen 0) — kart maskelemeyi 'kalıcı olarak maskelenir' diye OLMUŞ gibi anlatmaz; onaysız başlamadığını söyler", async () => {
  expect(YENI.govde).toMatchObject({ days: 365, acknowledged: false, pending: 0 });
  govde = JSON.parse(JSON.stringify(YENI.govde));
  const k = await kart();
  expect(k).toMatch(/onay/i);
  expect(k).not.toMatch(/adları 365 gün sonra kalıcı olarak maskelenir/);
});

test("KRİTİK: onaysız + 1 bekleyen — kart yine 'maskelenir' diye kesin konuşmaz (bekleyen uyarısı ve onay düğmesi durur)", async () => {
  expect(BEKLEYEN.govde).toMatchObject({ days: 365, acknowledged: false, pending: 1 });
  govde = JSON.parse(JSON.stringify(BEKLEYEN.govde));
  const k = await kart();
  expect(k).toMatch(/1 seans kaydı 365 günlük süreyle maskelenmeyi bekliyor/);
  expect(k).not.toMatch(/adları 365 gün sonra kalıcı olarak maskelenir/);
});

test("KARŞIT: onaylı (acknowledged) — kart maskelemenin UYGULANDIĞINI söyler", async () => {
  govde = { ...JSON.parse(JSON.stringify(YENI.govde)), acknowledged: true, approvedDays: 365, approvedCount: 0 };
  const k = await kart();
  expect(k).toMatch(/365 gün sonra kalıcı olarak maskelenir/);
});
