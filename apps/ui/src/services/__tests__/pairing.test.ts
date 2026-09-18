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

import AsyncStorage from "@react-native-async-storage/async-storage";

import { cihazaBaglan, eslesmeMesaji } from "@/services/pairing";

const URL_ = "https://ornek.trycloudflare.com";
const ID_ = "140936350360443";
const bulundu = { durum: "bulundu", url: URL_, device: { device_id: ID_ } };

beforeEach(() => {
  for (const m of [mockCozKod, mockCozKimlik, mockHealth, mockExchange, mockUpdateCfg, mockSetDeviceId]) {
    m.mockReset();
  }
  // ⚠️ ZORUNLU: `AsyncStorage.setItem` çağrıları dosya boyunca BİRİKİYOR. Sıfırlanmazsa aşağıdaki
  // "adres yazılmadı" iddiası bayat bir satırı görüp yanlış-kırmızı verir.
  (AsyncStorage.setItem as jest.Mock).mockClear();
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
    expect(mockHealth).toHaveBeenCalledWith(URL_, ID_, expect.anything());
  });

  it("KRİTİK [5.9]: ön-prob checkHealth'e kimligiKaydet:false GEÇİLİR — takas düşerse kimlik B'ye dönemez", async () => {
    // checkHealth başarılı her yanıtta deviceId'yi diske yazar; takas ÖNCESİ prob bu yan
    // etkiyle F3 değişmezini ("token yoksa kalıcı yazım yok") device_id için deliyordu.
    // Kalıcı yazım, takas başarılıysa aşağıdaki setStoredDeviceId'de zaten yapılır.
    mockCozKod.mockResolvedValue(bulundu);
    await cihazaBaglan("MVPDDN");
    expect(mockHealth).toHaveBeenCalledWith(URL_, ID_, { kimligiKaydet: false });
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


// ── token takası düşerse KALICI YAZIM olmamalı (denetim 2026-08-17) ───────────

const adresYazildiMi = () =>
  (AsyncStorage.setItem as jest.Mock).mock.calls.map((c) => c[0]).includes("@pemf_server_address");

it("KRİTİK: token takası DÜŞERSE adres/device_id diske YAZILMAZ", async () => {
  // İKİ CİHAZLI klinikte gerçek zarar: telefon A cihazıyla LAN'da çalışırken B'nin kodu girilir,
  // health + device_id geçer ama takas 429/404 ile düşer. Eskiden adres B-TÜNELİNE yazılıyor ve
  // A'nın LAN adresi diskten SİLİNMİŞ oluyordu → token yok → REST 401 / WS 1008; kullanıcı
  // Ayarlar'dan kodu tekrar girmeden düzelmiyordu.
  mockCozKod.mockResolvedValue(bulundu);
  mockExchange.mockResolvedValue(false);

  const s = await cihazaBaglan("MVPDDN");

  expect(s.durum).toBe("kod_reddedildi");
  expect(mockExchange).toHaveBeenCalledTimes(1);
  expect(mockSetDeviceId).not.toHaveBeenCalled();
  expect(adresYazildiMi()).toBe(false);
});

it("POZİTİF KAPI: takas BAŞARILIYSA adres kalıcı yazılmaya devam eder", async () => {
  // "Hiç yazma" biçiminde bir mutasyonun bu düzeltme sanılmasını engeller.
  mockCozKod.mockResolvedValue(bulundu);
  mockExchange.mockResolvedValue(true);

  const s = await cihazaBaglan("MVPDDN");

  expect(s).toMatchObject({ durum: "ok", url: URL_, deviceId: ID_ });
  expect(mockSetDeviceId).toHaveBeenCalledWith(ID_);
  expect(adresYazildiMi()).toBe(true);
});

it("takas düşse de OTURUM İÇİ config güncellenmiş kalır (kullanıcı hemen tekrar deneyebilir)", async () => {
  // ⚠️ Erken dönüş `updateServiceConfig`ten SONRA olmalı: oturum içi bağlantı korunur, yalnız
  // KALICI yazım atlanır. Erken dönüşü yukarı taşıyan bir yama bu testi kırar.
  mockCozKod.mockResolvedValue(bulundu);
  mockExchange.mockResolvedValue(false);

  await cihazaBaglan("MVPDDN");

  expect(mockUpdateCfg).toHaveBeenCalledWith(URL_);
});

// ── "yok" mesajı DÜRÜST olmalı (denetim 2026-08-17) ──────────────────────────
// Sunucudaki `resolve_device` tazelik penceresi istemcinin `STALE_MS`i ile EŞİTTİ (ikisi de 5 dk),
// yani uzun süredir kapalı bir cihaz `bayat` DEĞİL `yok` olarak dönüyordu. Ekranda "Kodu kontrol
// edin" yazıyordu ve kullanıcı — kod doğru olduğu hâlde — kodu defalarca kontrol ediyordu
// (2026-08-12 saha bildiriminin aynısı). Pencere genişletildi; bu dal artık YALNIZ "kod yanlış"
// demediği için mesaj da iki sebebi birlikte söylemeli.

describe("eşleşme mesajı dürüstlüğü", () => {
  it("KRİTİK: 'yok' mesajı cihazın KAPALI/ÇEVRİMDIŞI olabileceğini de söyler", () => {
    const m = eslesmeMesaji({ durum: "yok" });
    expect(m).toMatch(/çevrimdışı|kapalı/i);
  });

  it("KRİTİK: 'yok' mesajı kod ihtimalini de söylemeye DEVAM eder", () => {
    // Karşı yöne savrulma koruması: yalnız "cihaz kapalı" demek, gerçekten yanlış kod giren
    // kullanıcıyı bu kez öbür yanlış yöne bakmaya iter.
    expect(eslesmeMesaji({ durum: "yok" })).toMatch(/kod/i);
  });

  it("KARŞIT-KANIT: 'bayat' AYRI ve DAHA KESİN mesajını korur", () => {
    // Mesajları birleştirmek bir düzeltme değil, bilgi KAYBI olur: `bayat` demek "kayıt bulundu,
    // kod DOĞRU" demektir — orada kod ihtimalinden hiç söz edilmemeli.
    const bayat = eslesmeMesaji({ durum: "bayat" });
    expect(bayat).not.toBe(eslesmeMesaji({ durum: "yok" }));
    expect(bayat).toMatch(/kayıtlı/i);
    expect(bayat).not.toMatch(/kodu kontrol/i);
  });
});
