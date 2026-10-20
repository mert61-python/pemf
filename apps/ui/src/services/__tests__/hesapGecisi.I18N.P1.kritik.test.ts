// Author: mertaygn, cglrgrkn
/**
 * I18N-P1 · KRİTİK — hesap geçişi engel iletileri (seans / bobin güvenliği): TR göç öncesiyle BAYT BAYT aynı, EN doğru ve eylem AYNI
 * (engel koşulları dilden bağımsız: çalışan bobin / aktif seans / belirsiz donanım → kapalı; boşta → açık). ACİL DURDUR ekranda kalır
 * cümlesi iki dilde de bulunur. Eylem (kapı) mantığı `hesapGecisi.CH1.test.ts`'te; burada metin + dil değişimi.
 */
jest.mock("@/services/supabaseAuth", () => ({ supabaseAuth: { auth: {} }, oturumDeposu: {} }));
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(),
  hesapKusagiArtir: jest.fn(),
  setAuthBearer: jest.fn(),
  setEntitlementHeaders: jest.fn(),
}));

import { act } from "@testing-library/react-native";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";
import { hesapGecisBelirsizEngeli, hesapGecisSeansEngeli, hesapGecisiEngeli, onaySirasindaSeansBasladi } from "@/services/hesapGecisi";

const depo = { setItem: async () => undefined };
const calisan = { coils: [{ id: 1, running: true }], activeTreatment: { isActive: false } } as never;
const aktif = { coils: [], activeTreatment: { isActive: true } } as never;
const bos = { coils: [{ id: 1, running: false }], activeTreatment: { isActive: false } } as never;

const TR_SEANS = "Seans sürerken (bobinler çalışırken) e-posta hesabı değiştirilemez — önce seansı bitirin. ACİL DURDUR ekranda kalır.";
const TR_BELIRSIZ = "Bobinlerin durumu bilinmiyor (cihaz bağlantısı yok) — e-posta hesabı değiştirilemez. Önce bağlantıyı ve bobinleri kontrol edin.";
const TR_ONAY = "Onay penceresi açıkken bobinler çalışmaya / seans başladı — işlem iptal edildi. ACİL DURDUR ekranda kalır; seansı bitirip tekrar deneyin.";
const EN_SEANS = "The email account cannot be switched while a session is running (coils are active) — finish the session first. EMERGENCY STOP stays on screen.";
const EN_BELIRSIZ = "The coil status is unknown (no device connection) — the email account cannot be switched. Check the connection and the coils first.";
const EN_ONAY =
  "The coils started running / a session started while the confirmation window was open — the action was canceled. EMERGENCY STOP stays on screen; finish the session and try again.";

afterEach(async () => {
  __bayrakTestiAyarla(null);
  await act(async () => {
    await dilSec("tr", depo);
  });
});

it("Türkçe: engel metinleri göç öncesiyle aynı; koşullar aynı", () => {
  expect(hesapGecisiEngeli(calisan, false)).toBe(TR_SEANS);
  expect(hesapGecisiEngeli(aktif, false)).toBe(TR_SEANS);
  expect(hesapGecisiEngeli(bos, true)).toBe(TR_BELIRSIZ);
  expect(hesapGecisiEngeli(bos, false)).toBeNull();
  expect(onaySirasindaSeansBasladi()).toBe(TR_ONAY);
});

it("İngilizce (bayrak açık): metinler İngilizce, 'EMERGENCY STOP ekranda kalır' var; ENGEL KOŞULLARI AYNI", async () => {
  __bayrakTestiAyarla(true);
  await act(async () => {
    await dilSec("en", depo);
  });
  expect(hesapGecisiEngeli(calisan, false)).toBe(EN_SEANS);
  expect(hesapGecisiEngeli(aktif, false)).toBe(EN_SEANS);
  expect(hesapGecisiEngeli(bos, true)).toBe(EN_BELIRSIZ);
  expect(hesapGecisiEngeli(bos, false)).toBeNull();
  expect(hesapGecisSeansEngeli()).toContain("EMERGENCY STOP");
  expect(hesapGecisBelirsizEngeli()).toBe(EN_BELIRSIZ);
  expect(onaySirasindaSeansBasladi()).toBe(EN_ONAY);
});
