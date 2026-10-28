/**
 * @jest-environment jsdom
 */
/**
 * D6.08 (B-3.2 · A-06) — Ayarlar → Veri Saklama Süresi: "Maskeleme KAPALI" metni 5 yıl (1825 gün) hasta anonimleştirmesiyle ÇELİŞMEZ.
 * ===========================================================================================================================
 * ÖLÇÜLEN KUSUR: maskeleme kapalıyken (`days: 0`) kart "hasta ve operatör adları süresiz saklanır" diyordu. Gerçek: günlük bakım
 * (`servers/api_server.py` → `services/kvkk_anonimlestirme.tur`, `ESIK_GUN = 1825`) 1825 gün tedavi görmeyen hastaların adını ve
 * iletişim bilgilerini — seans ve AI kayıtlarındakiler dahil — operatör ONAYIYLA anonimleştirir; hekim adı kalır (A-27). Maskeleme
 * kapalıyken süresi dolan seans kaydı maskelenmez (`thdb_bakim.apply_data_retention_policy`, süre 0 = adım kapalı); "süresiz" değildir.
 * GERÇEK: SettingsScreen, apiClient, config, katalog. GET yanıtı GERÇEK backend fikstürü (`retentionYeniKlinik.F235.json`, tazeliği
 * tests/test_veri_saklama_karti_ONAYSIZ_maskeleme_BASLAMAZ_F235.py denetler); operatörün "Kapalı" seçimi (`days: 0`) fikstür üstünde.
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
import { EN, TR } from "@/i18n/__tests__/kaynakMetni";
import { Sahne } from "../../context/__tests__/operatorAparati";
import YENI from "./__fixtures__/retentionYeniKlinik.F235.json";

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

/** Operatör "Kapalı"yı seçmiş klinik: GERÇEK yanıtın `days: 0` hâli (bekleyen 0 — süre 0'da sayılmaz, `system_router.retention_durumu`). */
function maskeKapali(): Record<string, unknown> {
  const g = JSON.parse(JSON.stringify(YENI.govde)) as Record<string, unknown>;
  return { ...g, days: 0, configured: true, pending: 0 };
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

test("KRİTİK: maskeleme KAPALI + anonimleştirme onaysız — kart 'süresiz saklanır' DEMEZ; 1825 günlük anonimleştirmeyi ve onayı SÖYLER", async () => {
  expect((YENI.govde.anonymization as Record<string, unknown>).days).toBe(1825); // GERÇEK yanıt: eşik `kvkk_anonimlestirme.ESIK_GUN`
  govde = maskeKapali();
  const k = await kart();
  expect(k).toMatch(/Maskeleme KAPALI/);
  expect(k).not.toMatch(/süresiz/);
  expect(k).toMatch(/1825 gün \(5 yıl\) tedavi görmeyen hastaların/);
  expect(k).toMatch(/yalnız onayınızla anonimleştirilir/);
  expect(k).toMatch(/hekim adı kalır/);
});

test("KRİTİK: maskeleme KAPALI + anonimleştirme ONAYLI — 'süresiz' yalanı yok; onaylı durum da söylenir", async () => {
  govde = maskeKapali();
  (govde.anonymization as Record<string, unknown>).acknowledged = true;
  const k = await kart();
  expect(k).not.toMatch(/süresiz/);
  expect(k).toMatch(/1825 gün \(5 yıl\) tedavi görmeyen hastaların/);
  expect(k).toMatch(/Anonimleştirme onaylı — 1825 gün/);
});

test("KRİTİK (D67 orkestratör mutantı: eşik sabit 1825 YAŞADI): eşik YANITTAN — yanıt başka eşik taşırsa kart o eşiği söyler", async () => {
  govde = maskeKapali();
  (govde.anonymization as Record<string, unknown>).days = 2190;
  const k = await kart();
  expect(k).toMatch(/2190 gün \(5 yıl\) tedavi görmeyen hastaların/);
  expect(k).not.toMatch(/1825 gün \(5 yıl\) tedavi görmeyen/);
});

test("KARŞIT: anonimleştirme alanı olmayan (eski) yanıt — kart çizilir, yer tutucu ham kalmaz, 'süresiz' yine YOK", async () => {
  govde = maskeKapali();
  delete govde.anonymization;
  const k = await kart();
  expect(k).toMatch(/Maskeleme KAPALI — seans kayıtlarındaki hasta ve operatör adları süre dolunca maskelenmez\./);
  expect(k).not.toMatch(/\{\{gun\}\}|undefined/);
  expect(k).not.toMatch(/süresiz/);
});

test("KARŞIT: maskeleme AÇIK (onaylı) — 'Maskeleme KAPALI' cümlesi çizilmez", async () => {
  govde = { ...maskeKapali(), days: 365, acknowledged: true };
  const k = await kart();
  expect(k).not.toMatch(/Maskeleme KAPALI/);
  expect(k).not.toMatch(/kimlik bilgileri ise/); // "KAPALI" cümlesinin devamı tek başına çizilmez
  expect(k).toMatch(/365 gün sonra kalıcı olarak maskelenir/);
});

test("KATALOG: TR birebir, EN dolu ve 'indefinitely' iddiası yok", () => {
  expect(TR["ayarlar.saklama.kapali"]).toBe("Maskeleme KAPALI — seans kayıtlarındaki hasta ve operatör adları süre dolunca maskelenmez.");
  expect(TR["ayarlar.saklama.kapaliAnonim"]).toBe(
    " {{gun}} gün (5 yıl) tedavi görmeyen hastaların kimlik bilgileri ise yalnız onayınızla anonimleştirilir; hekim adı kalır.",
  );
  expect(EN["ayarlar.saklama.kapali"]).toBe("Masking OFF — patient and operator names in session records are not masked when a period ends.");
  expect(EN["ayarlar.saklama.kapaliAnonim"]).toBe(
    " Patients not treated for {{gun}} days (5 years) have their identity details anonymized only with your approval; the veterinarian's name remains.",
  );
  expect(`${EN["ayarlar.saklama.kapali"]}${EN["ayarlar.saklama.kapaliAnonim"]}`).not.toMatch(/indefinitely/i);
});

// TUR 2 (çürütücü kolu): eşik gün sayısı TEK KAYNAKTAN (yanıtın `anonymization.days` = backend `kvkk_anonimlestirme.ESIK_GUN`) gelir.
// Sabit 1825 yazan mutant (`cur608_n1`) yukarıdaki testlerde YAŞIYORDU — gerçek fikstür de 1825 taşıdığından ayırt edilemiyordu.
test("TEK KAYNAK (tur 2): eşik gün sayısı YANITTAN gelir — ekranda sabit 1825 yazılmaz", async () => {
  govde = maskeKapali();
  (govde.anonymization as Record<string, unknown>).days = 1826;
  const k = await kart();
  expect(k).toMatch(/1826 gün/);
  expect(k).not.toMatch(/1825 gün/);
});
