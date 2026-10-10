/**
 * @jest-environment jsdom
 */
/**
 * F2-1.2 (2-F incelemesi) · A-73 — Ayarlar → Veri Saklama Süresi: cihaz saati ileri sıçradıysa ya da geride kaldıysa geri dönüşsüz
 * saklama adımları (maskeleme, anonimleştirme, süresi dolan kayıtların silinmesi) operatör saati onaylayana dek BEKLER.
 * ===========================================================================================================================
 * ÖLÇÜLEN KUSUR: saat +10 yıl sıçrayınca tek tur tüm hastaları anonimleştirip tüm doz kaydını siliyordu. Backend artık şüpheyi kalıcı
 * işaretliyor ve `/api/settings/retention` `clockSuspect` (neden metni ya da null) döndürüyor; ekran şüpheyi ve sonucunu SÖYLEMELİ,
 * onay düğmesi `clock_confirm: true` göndermeli. Düğme olmadan sahada saklama SÜRESİZ dururdu (yalnız teknik destek açabilirdi).
 * GERÇEK: SettingsScreen, apiClient, config. GET yanıtı GERÇEK backend fikstürü (`__fixtures__/retentionAnonim.D254.json` —
 * `clockSuspect: null` alanı dahil; tests/test_kvkk_anonimlestirme_ONAYLI_ve_EKSIKSIZ_D254.py tazeliğini denetler); şüpheli durumun
 * metni ve onayın uca etkisi tests/test_saat_SICRAMASI_geri_donussuz_islem_yapmaz_A73_F2_1_2.py'de GERÇEK uçla ölçülür.
 * Sahte (ekran dışı): fetch, bağlamlar.
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

const ONAY_ETIKETI = "Cihaz saatinin doğru olduğunu onayla";
const NEDEN = "ileri: cihaz saati 2036-10-07 13:36, son gorulen 2026-10-10 13:36";
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

test("KRİTİK: saat şüphesi varsa nedeni ve sonucu SÖYLENİR, onay düğmesi clock_confirm gönderir", async () => {
  expect(FIKSTUR.durum).toBe(200);
  expect("clockSuspect" in FIKSTUR.govde).toBe(true); // GERÇEK yanıt alanı taşıyor (sözleşme)
  retentionGovde.clockSuspect = NEDEN;
  await ekran();
  const metin = s.metin();
  expect(metin).toMatch(/Cihaz saati şüpheli/);
  expect(metin).toContain(NEDEN);
  expect(metin).toMatch(/maskeleme, anonimleştirme ve süresi dolan\s+kayıtların silinmesi YAPILMAZ/);
  expect(metin).toMatch(/eski tarihli görünür/);
  await s.tikla(ONAY_ETIKETI);
  const post = cagrilar.filter((c) => c.yontem === "POST" && c.yol === "/settings/retention");
  expect(post.map((c) => c.govde)).toEqual([{ clock_confirm: true }]);
});

test("KARŞIT: GERÇEK yanıtta şüphe yok (null) — uyarı ve düğme YOK", async () => {
  expect(FIKSTUR.govde.clockSuspect).toBeNull();
  await ekran();
  expect(s.varMi(ONAY_ETIKETI)).toBe(false);
  expect(s.metin()).not.toMatch(/Cihaz saati şüpheli/);
});
