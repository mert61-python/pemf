/**
 * KP-3 C · services/hesapGecisi + services/pairing kapsanmayan kolları — her test bir DAVRANIŞ iddiası:
 *  hesapGecisi (CH1 düzeneği):
 *   - Zaten etkin hesaba "geç" → oturum YENİDEN kurulmaz, kimlik başlıkları DÜŞMEZ, yinelenen park kaydı temizlenir.
 *   - Belirteç hatası sınıflandırması: ağ / zaman aşımı iletisi (ad ne olursa olsun) KALICI SAYILMAZ → hedef parkta kalır; hatasız
 *     reddedilen (istisna fırlatan) oturum kurulumu da geri kuruluma düşer.
 *   - Etkin oturum okunamazsa (getSession atar / belirteçsiz oturum) "etkin hesap yok" sayılır → önceki hesap park EDİLMEZ.
 *  pairing (pairing.test düzeneği):
 *   - Cihaz kaydı var ama adresi yoksa son görülme ZAMANI taşınır (yoksa yalnız durum).
 *   - Takas başarılı ama adres uygulanamazsa "geçersiz adres" ve kalıcı yazım YOK; çözümleyici atarsa "hata"; adres diske
 *     yazılamasa da oturum içi bağlantı "ok" döner.
 * SAHTE: Supabase oturum deposu + auth istemcisi, apiClient başlıkları; cihaz kaydı / keşif / config sınırları (pairing).
 */
const mockDepo = new Map<string, string>();
const mockSira: string[] = [];
const mockAuth = { getSession: jest.fn(), setSession: jest.fn(), admin: { signOut: jest.fn(async () => ({ data: null, error: null })) } };
jest.mock("@/services/supabaseAuth", () => ({
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
const mockCozKod = jest.fn();
const mockHealth = jest.fn();
const mockExchange = jest.fn();
const mockUpdateCfg = jest.fn();
const mockTabanCoz = jest.fn();
const mockSetDeviceId = jest.fn();
jest.mock("@/services/deviceRegistry", () => ({
  uzakCihaziKodlaCoz: (...a: unknown[]) => mockCozKod(...a),
  uzakCihaziKimlikleCoz: jest.fn(),
}));
jest.mock("@/services/discovery", () => ({
  checkHealth: (...a: unknown[]) => mockHealth(...a),
  exchangeCodeForToken: (...a: unknown[]) => mockExchange(...a),
  kimlikYoluErisimi: jest.fn(),
}));
jest.mock("@/services/config", () => ({
  updateServiceConfig: (...a: unknown[]) => mockUpdateCfg(...a),
  servisTabanlariniCoz: (...a: unknown[]) => mockTabanCoz(...a),
  setStoredDeviceId: (...a: unknown[]) => mockSetDeviceId(...a),
}));

import AsyncStorage from "@react-native-async-storage/async-storage";
import { hesabaGec } from "@/services/hesapGecisi";
import { parkEt, parkHesaplari } from "@/services/hesapDeposu";
import { cihazaBaglan } from "@/services/pairing";

const oturum = (email: string, rt: string) => ({
  data: { session: { access_token: `AT-${email}`, refresh_token: rt, expires_at: 9, user: { email } } },
});
const parkta = async () => (await parkHesaplari()).map((h) => h.email).sort();

beforeEach(async () => {
  mockDepo.clear();
  mockSira.length = 0;
  jest.clearAllMocks();
});

describe("hesapGecisi", () => {
  it("zaten etkin hesaba geçiş: oturum yeniden kurulmaz, başlıklar düşmez, yinelenen park kaydı temizlenir", async () => {
    mockAuth.getSession.mockResolvedValue(oturum("a@klinik.com", "RT-A"));
    await parkEt({ email: "a@klinik.com", access_token: "AT-A", refresh_token: "RT-A" });
    await expect(hesabaGec("A@klinik.com")).resolves.toEqual({ ok: true });
    expect(mockAuth.setSession).not.toHaveBeenCalled();
    expect(mockSira).toEqual([]);
    expect(await parkta()).toEqual([]);
  });

  it.each([
    ["ağ iletisi (adı genel Error)", { name: "Error", status: 400, message: "network request failed" }],
    ["zaman aşımı iletisi", { name: "AuthApiError", status: 401, message: "Request timeout" }],
  ])("%s KALICI sayılmaz → hedef parkta kalır, önceki hesap geri kurulur", async (_ad, hata) => {
    mockAuth.getSession.mockResolvedValue(oturum("a@klinik.com", "RT-A"));
    await parkEt({ email: "b@klinik.com", access_token: "AT-B", refresh_token: "RT-B" });
    mockAuth.setSession.mockResolvedValueOnce({ data: {}, error: hata }).mockResolvedValueOnce({ data: {}, error: null });
    const r = await hesabaGec("b@klinik.com");
    expect(r.ok).toBe(false);
    expect(await parkta()).toEqual(["b@klinik.com"]); // B parkta kaldı; A geri kuruldu → A parktan çıktı
    expect(mockAuth.setSession).toHaveBeenLastCalledWith({ access_token: "AT-a@klinik.com", refresh_token: "RT-A" });
  });

  it("oturum kurulumu istisna fırlatırsa geri kuruluma düşer; etkin oturum okunamazsa önceki hesap PARK EDİLMEZ", async () => {
    mockAuth.getSession.mockRejectedValueOnce(new Error("depo bozuk"));
    await parkEt({ email: "b@klinik.com", access_token: "AT-B", refresh_token: "RT-B" });
    mockAuth.setSession.mockRejectedValueOnce(undefined);
    const r = await hesabaGec("b@klinik.com");
    expect(r.ok).toBe(false);
    expect(await parkta()).toEqual(["b@klinik.com"]); // önceki hesap bilinmiyordu → park edilen yok
    mockAuth.getSession.mockResolvedValueOnce({ data: { session: { user: { email: "a@klinik.com" }, access_token: "x" } } }); // belirteçsiz
    mockAuth.setSession.mockResolvedValueOnce({ data: {}, error: null });
    await expect(hesabaGec("b@klinik.com")).resolves.toEqual({ ok: true });
    expect(await parkta()).toEqual([]); // belirteçsiz "etkin" oturum park EDİLMEDİ
    // hedef düşerse belirteçsiz "önceki" oturum GERİ KURULMAYA ÇALIŞILMAZ (refresh_token'sız setSession yok)
    await parkEt({ email: "b@klinik.com", access_token: "AT-B", refresh_token: "RT-B" });
    mockAuth.setSession.mockClear();
    mockAuth.getSession.mockResolvedValueOnce({ data: { session: { user: { email: "a@klinik.com" }, access_token: "x" } } });
    mockAuth.setSession.mockResolvedValueOnce({ data: {}, error: { name: "AuthRetryableFetchError", message: "Failed to fetch" } });
    await expect(hesabaGec("b@klinik.com")).resolves.toMatchObject({ ok: false });
    expect(mockAuth.setSession).toHaveBeenCalledTimes(1);
  });
});

describe("pairing", () => {
  const URL_ = "https://ornek.trycloudflare.com";
  const bulundu = { durum: "bulundu", url: URL_, device: { device_id: "D-1" } };
  beforeEach(() => {
    (AsyncStorage.setItem as jest.Mock).mockClear?.();
    mockHealth.mockResolvedValue(true);
    mockExchange.mockResolvedValue(true);
    mockUpdateCfg.mockReturnValue(true);
    mockTabanCoz.mockReturnValue({ apiBaseUrl: `${URL_}/api`, websocketUrl: "wss://x/ws", bridgeBaseUrl: `${URL_}/api` });
  });

  it("adresi olmayan kayıtta son görülme taşınır; yoksa yalnız durum", async () => {
    mockCozKod.mockResolvedValueOnce({ durum: "adres_yok", device: { device_id: "D-1", last_seen: "2026-10-25T08:00:00Z" } });
    await expect(cihazaBaglan("AB12CD")).resolves.toEqual({ durum: "adres_yok", sonGorulme: "2026-10-25T08:00:00Z" });
    mockCozKod.mockResolvedValueOnce({ durum: "adres_yok", device: { device_id: "D-1" } });
    await expect(cihazaBaglan("AB12CD")).resolves.toEqual({ durum: "adres_yok" });
  });

  it("takas sonrası adres uygulanamazsa 'geçersiz adres' ve kalıcı yazım YOK; çözümleyici atarsa 'hata'; disk yazımı düşse de 'ok'", async () => {
    mockCozKod.mockResolvedValueOnce(bulundu);
    mockUpdateCfg.mockReturnValueOnce(false);
    await expect(cihazaBaglan("AB12CD")).resolves.toEqual({ durum: "gecersiz_adres" });
    expect(mockSetDeviceId).not.toHaveBeenCalled();
    mockCozKod.mockRejectedValueOnce(new Error("Supabase 500"));
    await expect(cihazaBaglan("AB12CD")).resolves.toEqual({ durum: "hata" });
    mockCozKod.mockResolvedValueOnce(bulundu);
    jest.spyOn(AsyncStorage, "setItem").mockRejectedValueOnce(new Error("depo dolu"));
    await expect(cihazaBaglan("AB12CD")).resolves.toEqual({ durum: "ok", url: URL_, deviceId: "D-1" });
    expect(mockSetDeviceId).toHaveBeenCalledWith("D-1");
  });
});
