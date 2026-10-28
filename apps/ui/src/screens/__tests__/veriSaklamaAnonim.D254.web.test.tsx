/**
 * @jest-environment jsdom
 */
/**
 * D2.54 · A-06 — Ayarlar → Veri Saklama Süresi: 5 yıl inaktif hasta anonimleştirmesi OPERATÖR ONAYINA bağlıdır.
 * ===========================================================================================================================
 * ÖLÇÜLEN KUSUR: günlük bakım 1825 gün inaktif hastaları ONAYSIZ ve SESSİZ anonimleştiriyordu; ekranda ne bekleyen sayı ne onay vardı.
 * Backend artık onay olmadan hiçbir hastaya dokunmuyor ve `/api/settings/retention` `anonymization {days, acknowledged, pending}`
 * döndürüyor; ekran bekleyen sayıyı ve geri dönüşsüzlüğü SÖYLEMELİ, onay düğmesi `anonymize_acknowledge: true` göndermeli.
 * GERÇEK: SettingsScreen, apiClient, config. GET yanıtı GERÇEK backend fikstürü (`__fixtures__/retentionAnonim.D254.json` —
 * tests/test_kvkk_anonimlestirme_ONAYLI_ve_EKSIKSIZ_D254.py üretir ve tazeliğini denetler). Sahte (ekran dışı): fetch, bağlamlar.
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
import FIKSTUR from "./__fixtures__/retentionAnonim.D254.json";

const ONAY_ETIKETI = "Geri dönüşsüz anonimleştirmeyi onayla ve başlat";
type Cagri = { yol: string; yontem: string; govde: Record<string, unknown> | null };
let cagrilar: Cagri[];
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
  cagrilar = [];
  retentionGovde = JSON.parse(JSON.stringify(FIKSTUR.govde));
  (global as unknown as { fetch: unknown }).fetch = jest.fn((url: string, init?: RequestInit) => {
    const yol = String(url).replace(/^[a-z]+:\/\/[^/]+/i, "").replace(/^\/api/, "").split("?")[0];
    const yontem = (init?.method || "GET").toUpperCase();
    cagrilar.push({ yol, yontem, govde: init?.body ? JSON.parse(String(init.body)) : null });
    if (yol === "/settings/retention" && yontem === "GET") return Promise.resolve(sahteYanit(retentionGovde));
    if (yol === "/settings/retention" && yontem === "POST") return Promise.resolve(sahteYanit({ status: "success" }));
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

test("KRİTİK: onaysız — bekleyen hasta sayısı ve geri dönüşsüzlük SÖYLENİR, onay düğmesi anonymize_acknowledge gönderir", async () => {
  expect(FIKSTUR.durum).toBe(200);
  await ekran();
  const metin = s.metin();
  expect(metin).toMatch(/1 hasta 1825 gündür \(5 yıl\) seans yapılmadığı için/);
  expect(metin).toMatch(/GERİ ALINAMAZ/);
  // F2-3.3 (2-F incelemesi · A-38): Legal §6 "adı, sahibinin adı, iletişim bilgileri, yaşı ve kilosu ... anonimleştirilir".
  expect(metin).toMatch(/iletişim bilgileri, yaşı ve kilosu/);
  expect(metin).toMatch(/Onaylayana kadar hiçbir kayda dokunulmaz/);
  await s.tikla(ONAY_ETIKETI);
  const post = cagrilar.filter((c) => c.yontem === "POST" && c.yol === "/settings/retention");
  expect(post.map((c) => c.govde)).toEqual([{ anonymize_acknowledge: true }]);
});

test("KARŞIT: onaylıysa düğme YOK, onaylı durum söylenir", async () => {
  (retentionGovde.anonymization as Record<string, unknown>).acknowledged = true;
  await ekran();
  expect(s.varMi(ONAY_ETIKETI)).toBe(false);
  expect(s.metin()).toMatch(/Anonimleştirme onaylı/);
});

test("KARŞIT: bekleyen sayılamadıysa (null) '0 bekleyen' yalanı yok — okunamadı denir, düğme YOK", async () => {
  (retentionGovde.anonymization as Record<string, unknown>).pending = null;
  await ekran();
  expect(s.varMi(ONAY_ETIKETI)).toBe(false);
  expect(s.metin()).toMatch(/bekleyen hasta sayısı okunamadı/);
});

const GERI_AL_ETIKETI = "Anonimleştirme onayını geri al";

test("KRİTİK (S-F2-1.1): onaylıyken son tur SÖYLENİR ve GERİ ALMA düğmesi anonymize_revoke gönderir", async () => {
  expect("lastRun" in (FIKSTUR.govde.anonymization as Record<string, unknown>)).toBe(true); // GERÇEK yanıt alanı taşıyor
  const a = retentionGovde.anonymization as Record<string, unknown>;
  a.acknowledged = true;
  a.lastRun = { at: "2026-10-10T13:40:42+00:00", count: 2 };
  await ekran();
  expect(s.metin()).toMatch(/Son tur: .+ — 2 hasta\./);
  await s.tikla(GERI_AL_ETIKETI);
  const post = cagrilar.filter((c) => c.yontem === "POST" && c.yol === "/settings/retention");
  expect(post.map((c) => c.govde)).toEqual([{ anonymize_revoke: true }]);
});

test("KARŞIT (S-F2-1.1): GERÇEK yanıtta tur yok (lastRun null) — 'henüz tur yapılmadı'; onaysızken geri alma düğmesi YOK", async () => {
  expect((FIKSTUR.govde.anonymization as Record<string, unknown>).lastRun).toBeNull();
  (retentionGovde.anonymization as Record<string, unknown>).acknowledged = true;
  await ekran();
  expect(s.metin()).toMatch(/Henüz anonimleştirme turu yapılmadı/);
  await s.sok();
  s = new Sahne();
  (retentionGovde.anonymization as Record<string, unknown>).acknowledged = false;
  await ekran();
  expect(s.varMi(GERI_AL_ETIKETI)).toBe(false);
});
