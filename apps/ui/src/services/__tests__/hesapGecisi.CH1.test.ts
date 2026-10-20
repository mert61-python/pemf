// Author: mertaygn, cglrgrkn
/**
 * CH1 · Y151 — e-posta hesapları arasında geçiş (`services/hesapGecisi`).
 * ======================================================================
 * SÖZLEŞME: (1) geçişte etkin hesap park edilir, kimlik başlıkları (Bearer + abonelik) HEMEN düşer ve hesap kuşağı artar — hedef
 * oturum kurulmadan ÖNCE; (2) düşerse önceki hesap geri kurulur, hedef ağ hatasında parkta kalır, kalıcı geçersizse silinir ve
 * "yeniden giriş" denir; (3) seans sürerken / bobin çalışırken / donanım belirsizken geçiş KAPALI ve nedeni yazılı (teardown koruması
 * ile aynı koşullar); (4) park edilmiş hesaptan çıkış etkin hesabı DEĞİŞTİRMEZ, belirteci önce yerelden siler, sonra sunucuda iptal
 * eder (beklemeden); (5) belirteç değeri hata iletisinde yok.
 * ⚠️ MUTASYON: başlık düşürme setSession'dan SONRAYA alınırsa (1) KIRMIZI; geri kurulum silinirse (2) KIRMIZI; engel koşullarından
 * biri düşerse (3) KIRMIZI.
 */
const mockDepo = new Map<string, string>();
const mockSira: string[] = [];
const mockAuth = {
  getSession: jest.fn(),
  setSession: jest.fn(),
  admin: { signOut: jest.fn(async () => ({ data: null, error: null })) },
};
jest.mock("@/services/supabaseAuth", () => ({
  // ⚠️ getter: jest.mock fabrikası import'larla birlikte hoist edilir — `mockAuth` o anda henüz başlatılmamıştır.
  supabaseAuth: { get auth() { return mockAuth; } },
  oturumDeposu: {
    getItem: async (k: string) => (mockDepo.has(k) ? mockDepo.get(k)! : null),
    setItem: async (k: string, v: string) => { mockDepo.set(k, v); },
    removeItem: async (k: string) => { mockDepo.delete(k); },
  },
}));
jest.mock("@/services/apiClient", () => ({
  hesapKusagiArtir: jest.fn(() => { mockSira.push("kusak"); return 1; }),
  setAuthBearer: jest.fn((v: unknown) => { mockSira.push(`bearer:${v}`); }),
  setEntitlementHeaders: jest.fn((v: unknown) => { mockSira.push(`hak:${v}`); }),
}));

import { hesabaGec, hesapGecisiEngeli, parkHesabindanCik, tumParkHesaplardanCik, hesapGecisSeansEngeli, hesapGecisBelirsizEngeli } from "@/services/hesapGecisi";
import { parkEt, parkHesaplari } from "@/services/hesapDeposu";

const oturum = (email: string, rt: string) => ({
  data: { session: { access_token: `AT-${email}`, refresh_token: rt, expires_at: 9, user: { email } } },
});
const A = { email: "a@klinik.com", rt: "RT-A-GIZLI" };
const B = { email: "b@klinik.com", rt: "RT-B-GIZLI" };

beforeEach(async () => {
  mockDepo.clear();
  mockSira.length = 0;
  jest.clearAllMocks();
  mockAuth.getSession.mockResolvedValue(oturum(A.email, A.rt));
  await parkEt({ email: B.email, access_token: "AT-B", refresh_token: B.rt });
});

const parkta = async () => (await parkHesaplari()).map((h) => h.email);

it("KRİTİK: geçişte A park edilir; başlıklar düşer ve kuşak artar — hedef oturum kurulmadan ÖNCE", async () => {
  mockAuth.setSession.mockImplementation(async () => { mockSira.push("setSession"); return { data: {}, error: null }; });
  const r = await hesabaGec("B@klinik.com");
  expect(r).toEqual({ ok: true });
  expect(mockAuth.setSession).toHaveBeenCalledWith({ access_token: "AT-B", refresh_token: B.rt });
  const i = mockSira.indexOf("setSession");
  expect(mockSira.slice(0, i)).toEqual(expect.arrayContaining(["kusak", "bearer:null", "hak:null"]));
  expect(await parkta()).toEqual([A.email]); // A parkta (belirteciyle), B etkin → parktan çıktı
  expect((await parkHesaplari())[0].refresh_token).toBe(A.rt);
});

it("KRİTİK: ağ hatasında önceki hesap GERİ KURULUR, B parkta kalır, ileti belirteç içermez", async () => {
  mockAuth.setSession
    .mockResolvedValueOnce({ data: {}, error: { name: "AuthRetryableFetchError", status: 0, message: "Failed to fetch" } })
    .mockResolvedValueOnce({ data: {}, error: null });
  const r = await hesabaGec(B.email);
  expect(r.ok).toBe(false);
  expect(r.hata).toMatch(/sunucuya ulaşılamadı.*Önceki hesapta kalındı/);
  expect(mockAuth.setSession).toHaveBeenNthCalledWith(2, { access_token: `AT-${A.email}`, refresh_token: A.rt });
  expect(await parkta()).toEqual([B.email]); // A yeniden etkin (parktan çıktı), B hâlâ açık
  expect(JSON.stringify(r)).not.toMatch(/RT-|AT-/);
});

it("KRİTİK: B'nin oturumu kalıcı geçersizse B parktan silinir, 'yeniden giriş' denir, A geri kurulur", async () => {
  mockAuth.setSession
    .mockResolvedValueOnce({ data: {}, error: { name: "AuthApiError", status: 400, message: "Invalid Refresh Token: Refresh Token Not Found" } })
    .mockResolvedValueOnce({ data: {}, error: null });
  const r = await hesabaGec(B.email);
  expect(r.ok).toBe(false);
  expect(r.hata).toMatch(/oturumu sona ermiş.*Hesap ekle/);
  expect(await parkta()).toEqual([]);
  expect(mockAuth.setSession).toHaveBeenCalledTimes(2);
});

it("parkta olmayan hesaba geçilmez (setSession çağrılmaz)", async () => {
  const r = await hesabaGec("yok@klinik.com");
  expect(r.ok).toBe(false);
  expect(mockAuth.setSession).not.toHaveBeenCalled();
});

describe("KRİTİK seans koruması (teardown koruması ile AYNI koşullar)", () => {
  const bos = { coils: [{ id: 1, running: false }], activeTreatment: { isActive: false } } as never;
  it.each([
    ["bobin çalışıyor", { coils: [{ id: 2, running: true }], activeTreatment: { isActive: false } }, false, hesapGecisSeansEngeli()],
    ["aktif seans", { coils: [], activeTreatment: { isActive: true } }, false, hesapGecisSeansEngeli()],
    ["donanım belirsiz", { coils: [], activeTreatment: { isActive: false } }, true, hesapGecisBelirsizEngeli()],
  ])("%s → geçiş KAPALI + neden", (_ad, snap, belirsiz, metin) => {
    expect(hesapGecisiEngeli(snap as never, belirsiz as boolean)).toBe(metin);
  });
  it("KARŞIT boşta → açık", () => {
    expect(hesapGecisiEngeli(bos, false)).toBeNull();
  });
});

it("KRİTİK park edilmiş hesaptan çıkış: yalnız o hesap; etkin oturuma DOKUNULMAZ; önce yerel silme, sonra sunucuda iptal", async () => {
  await parkHesabindanCik("B@KLINIK.com");
  expect(await parkta()).toEqual([]);
  expect(mockAuth.setSession).not.toHaveBeenCalled();
  expect(mockAuth.admin.signOut).toHaveBeenCalledWith("AT-B", "local");
});

it("tüm park edilmiş hesaplardan çıkış: depo boşalır; sunucu iptali beklenmez (asılı ağ çıkışı durdurmaz)", async () => {
  mockAuth.admin.signOut.mockImplementation(() => new Promise(() => {})); // hiç dönmeyen ağ
  await tumParkHesaplardanCik();
  expect(await parkta()).toEqual([]);
});
