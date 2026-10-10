/**
 * @jest-environment jsdom
 */
/**
 * D2.55 · A-09 — Ayarlar → Veri Saklama Süresi: PII maskeleme onayı ONAYLANAN SÜREYE bağlıdır.
 * ===========================================================================================================================
 * ÖLÇÜLEN KUSUR: onay süreden bağımsız bir boolean'dı; 1825 gün onaylandıktan sonra süre 365'e düşünce genişleyen kapsam ne ekranda
 * gösteriliyor ne yeniden soruluyordu. Backend artık onayı süreye + kapsama bağlıyor ve `approvalStale / approvedDays` döndürüyor;
 * ekran önceki onayın NEDEN geçmediğini ve etkilenecek kayıt sayısını SÖYLEMELİ, onay düğmesi GÖSTERDİĞİ süreyi
 * (`acknowledge_days`) göndermeli (süre arada değiştiyse backend 409 verir — onay kaydedilmez) ve hata sonrası ekran yenilenmeli.
 * GERÇEK: SettingsScreen, apiClient, config. GET yanıtı GERÇEK backend fikstürü (`__fixtures__/retentionPiiOnay.D255.json` —
 * tests/test_pii_onayi_SUREYE_ve_KAPSAMA_bagli_A09_D255.py üretir ve tazeliğini denetler). Sahte (ekran dışı): fetch, bağlamlar.
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
import FIKSTUR from "./__fixtures__/retentionPiiOnay.D255.json";

const ONAY_ETIKETI = "Geri dönüşsüz maskelemeyi onayla ve başlat";
type Cagri = { yol: string; yontem: string; govde: Record<string, unknown> | null };
let cagrilar: Cagri[];
let retentionGovde: Record<string, unknown>;
let postDurum: number;
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
  postDurum = 200;
  retentionGovde = JSON.parse(JSON.stringify(FIKSTUR.govde));
  (global as unknown as { fetch: unknown }).fetch = jest.fn((url: string, init?: RequestInit) => {
    const yol = String(url).replace(/^[a-z]+:\/\/[^/]+/i, "").replace(/^\/api/, "").split("?")[0];
    const yontem = (init?.method || "GET").toUpperCase();
    cagrilar.push({ yol, yontem, govde: init?.body ? JSON.parse(String(init.body)) : null });
    if (yol === "/settings/retention" && yontem === "GET") return Promise.resolve(sahteYanit(retentionGovde));
    if (yol === "/settings/retention" && yontem === "POST") {
      return Promise.resolve(
        postDurum === 200 ? sahteYanit({ status: "success" }) : sahteYanit({ detail: "Saklama süresi değişti" }, postDurum),
      );
    }
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

const retentionGetSayisi = () => cagrilar.filter((c) => c.yontem === "GET" && c.yol === "/settings/retention").length;

test("KRİTİK: süre 1825 → 365 düştü — önceki onayın neden geçmediği ve etkilenecek kayıt sayısı SÖYLENİR, onay GÖSTERİLEN süreyi gönderir", async () => {
  expect(FIKSTUR.durum).toBe(200);
  expect(FIKSTUR.govde).toMatchObject({ days: 365, acknowledged: false, pending: 1, approvedDays: 1825, approvalStale: true });
  await ekran();
  const metin = s.metin();
  expect(metin).toMatch(/Önceki onay 1825 günlük süre içindi/);
  expect(metin).toMatch(/yeni onay gerekiyor/);
  expect(metin).toMatch(/1 seans kaydı 365 günlük süreyle maskelenmeyi bekliyor/);
  await s.tikla(ONAY_ETIKETI);
  const post = cagrilar.filter((c) => c.yontem === "POST" && c.yol === "/settings/retention");
  expect(post.map((c) => c.govde)).toEqual([{ acknowledge: true, acknowledge_days: 365 }]);
});

test("KRİTİK: onay 409 ile reddedilirse (süre arada değişti) ekran YENİLENİR — operatör güncel süreyi görür", async () => {
  postDurum = 409;
  await ekran();
  const once = retentionGetSayisi();
  await s.tikla(ONAY_ETIKETI);
  await s.bosalt(10);
  expect(retentionGetSayisi()).toBeGreaterThan(once);
});

test("KARŞIT: eski biçim onay (süresi bilinmiyor) — 'eski sürüm' denir; geçerli onayda uyarı ve düğme YOK", async () => {
  retentionGovde.approvedDays = null;
  await ekran();
  expect(s.metin()).toMatch(/hangi süreye verildiğini taşımıyor/);
  await s.sok();
  s = new Sahne();
  Object.assign(retentionGovde, { acknowledged: true, pending: 0, approvalStale: false, approvedDays: 365, approvedCount: 1 });
  await ekran();
  expect(s.varMi(ONAY_ETIKETI)).toBe(false);
  expect(s.metin()).not.toMatch(/yeni onay gerekiyor/);
});
