// Author: mertaygn, cglrgrkn
/**
 * CİHAZ EŞLEŞTİRME SERVİSİ — Ayarlar ekranı ve karşılama rehberinin ORTAK yolu.
 *
 * NEDEN TEK SERVİS: bu akış Ayarlar'ın içinde gömülüydü. Farklı ağdaki ilk açılışta kullanıcıyı
 * yönlendiren rehber de aynı işi yapacaktı; ikinci kopya, güvenlik değişmezlerinin birinde
 * sessizce eskimesi demekti (bu oturumda `getDeviceByPairingCode`/`getRemoteUrlForDevice`
 * ayrışmasının bedeli ödendi).
 *
 * KİLİTLENEN DEĞİŞMEZLER (sıra dahil):
 *   1. Çözümleme SEBEBİ korunur — "kod yanlış" ile "cihazda uzaktan erişim kapalı" ayrı.
 *   2. KAYDETMEDEN ÖNCE health + device_id doğrulaması. Bayat/zehirlenmiş tünel URL'i başka
 *      kliniğin cihazına düşebilir → yanlış hastaya komut riski.
 *   3. Kod yolunda token takası ve SONUCUNUN denetimi. Aksi hâlde "bağlandı ✓" denip sonraki
 *      her istek 401 alır (audit P0/#25).
 */
const mockCozKod = jest.fn();
const mockCozKimlik = jest.fn();
const mockHealth = jest.fn();
const mockExchange = jest.fn();
const mockUpdateCfg = jest.fn();
const mockSetDeviceId = jest.fn();

jest.mock("@/services/deviceRegistry", () => ({
  uzakCihaziKodlaCoz: (...a: unknown[]) => mockCozKod(...a),
  uzakCihaziKimlikleCoz: (...a: unknown[]) => mockCozKimlik(...a),
}));
jest.mock("@/services/discovery", () => ({
  checkHealth: (...a: unknown[]) => mockHealth(...a),
  exchangeCodeForToken: (...a: unknown[]) => mockExchange(...a),
}));
jest.mock("@/services/config", () => ({
  updateServiceConfig: (...a: unknown[]) => mockUpdateCfg(...a),
  setStoredDeviceId: (...a: unknown[]) => mockSetDeviceId(...a),
}));

import { cihazaBaglan, eslesmeMesaji } from "@/services/pairing";

const URL_ = "https://ornek.trycloudflare.com";
const ID_ = "140936350360443";
const bulundu = { durum: "bulundu", url: URL_, device: { device_id: ID_ } };

beforeEach(() => {
  for (const m of [mockCozKod, mockCozKimlik, mockHealth, mockExchange, mockUpdateCfg, mockSetDeviceId]) {
    m.mockReset();
  }
  mockHealth.mockResolvedValue(true);
  mockExchange.mockResolvedValue(true);
  mockUpdateCfg.mockReturnValue(true);
  mockSetDeviceId.mockResolvedValue(undefined);
});

describe("cihazaBaglan", () => {
  it("kod ile bağlanır ve kimliği KALICI yazar", async () => {
    mockCozKod.mockResolvedValue(bulundu);
    const s = await cihazaBaglan("MVPDDN");
    expect(s).toMatchObject({ durum: "ok", url: URL_, deviceId: ID_ });
    expect(mockSetDeviceId).toHaveBeenCalledWith(ID_);
  });

  it("KRITIK: health düşerse KAYDETMEZ (bayat/zehirli tünel koruması)", async () => {
    mockCozKod.mockResolvedValue(bulundu);
    mockHealth.mockResolvedValue(false);
    expect((await cihazaBaglan("MVPDDN")).durum).toBe("ulasilamiyor");
    expect(mockUpdateCfg).not.toHaveBeenCalled();
    expect(mockSetDeviceId).not.toHaveBeenCalled();
  });

  it("KRITIK: health çağrısına device_id GEÇİLİR (yanlış cihaza bağlanma)", async () => {
    mockCozKod.mockResolvedValue(bulundu);
    await cihazaBaglan("MVPDDN");
    expect(mockHealth).toHaveBeenCalledWith(URL_, ID_);
  });

  it("KRITIK: token takası başarısızsa 'bağlandı' DEMEZ", async () => {
    mockCozKod.mockResolvedValue(bulundu);
    mockExchange.mockResolvedValue(false);
    expect((await cihazaBaglan("MVPDDN")).durum).toBe("kod_reddedildi");
  });

  it("geçersiz adres mevcut ayarı BOZMAZ", async () => {
    mockCozKod.mockResolvedValue(bulundu);
    mockUpdateCfg.mockReturnValue(false);
    expect((await cihazaBaglan("MVPDDN")).durum).toBe("gecersiz_adres");
    expect(mockSetDeviceId).not.toHaveBeenCalled();
  });

  it("çözümleme sebebi KORUNUR (kod yanlış ≠ adres yok)", async () => {
    for (const d of ["yok", "adres_yok", "bayat", "hata"]) {
      mockCozKod.mockResolvedValue({ durum: d });
      expect((await cihazaBaglan("MVPDDN")).durum).toBe(d);
    }
  })

  it("uzun girdi CİHAZ KİMLİĞİ sayılır ve token takası YAPILMAZ", async () => {
    mockCozKimlik.mockResolvedValue(bulundu);
    const s = await cihazaBaglan(ID_);
    expect(s.durum).toBe("ok");
    expect(mockCozKimlik).toHaveBeenCalledWith(ID_);
    expect(mockCozKod).not.toHaveBeenCalled();
    expect(mockExchange).not.toHaveBeenCalled(); // kod yok → takas yok
  });

  it("boş girdide ağa hiç çıkmaz", async () => {
    expect((await cihazaBaglan("   ")).durum).toBe("yok");
    expect(mockCozKod).not.toHaveBeenCalled();
  });

  it("her sebebin kullanıcıya dönük bir mesajı vardır", () => {
    for (const d of ["ok", "yok", "adres_yok", "bayat", "hata", "ulasilamiyor", "gecersiz_adres", "kod_reddedildi"]) {
      const m = eslesmeMesaji({ durum: d, url: URL_, deviceId: ID_ } as never)
      expect(typeof m).toBe("string")
      expect(m.length).toBeGreaterThan(10)
    }
  })
});
