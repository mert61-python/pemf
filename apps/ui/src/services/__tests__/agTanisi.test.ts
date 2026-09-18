// Author: mertaygn, cglrgrkn
/**
 * AĞ TANISI — "cihaz bulunamadı"nın SEBEBİNİ söyler.
 *
 * SAHA BİLDİRİMİ (2026-08-14): telefon ve cihaz aynı Wi-Fi'deydi, cihaz çalışıyordu, mDNS doğru
 * arayüzde yayındaydı, güvenlik duvarı açıktı — ama bağlanmıyordu. Sebep modemde açılmış
 * **istemci izolasyonu**ydu. Bunu bulmak ürünü yazan kişinin bir saatini aldı.
 *
 * Kilitlenen davranışlar:
 *   • Üç kanıt birden varsa (internetten erişilir + AYNI alt ağ + yerelden erişilmez) → izolasyon.
 *   • Kanıtlardan BİRİ eksikse → `bilinmiyor`. ⚠️ Yanlış teşhis, teşhissizlikten KÖTÜDÜR:
 *     kullanıcıyı modem ayarlarında boşuna gezdirir.
 *   • Tanı YAN ETKİSİZ olmalı (kimlik/token yazmamalı) — `checkHealth` bilerek kullanılmıyor.
 */
import { agTanisiYap, altAg, taniMesaji, type TaniBagimliliklari } from "../agTanisi";

const CIHAZ_IP = "192.168.1.44";
const TUNEL = "https://x.trycloudflare.com";

/** Varsayılan: izolasyon senaryosu (aynı alt ağ, tünel çalışır, yerel çalışmaz). */
const kur = (over: TaniBagimliliklari = {}): TaniBagimliliklari => ({
  kimlikOku: jest.fn().mockResolvedValue("140936350360443"),
  uzakCoz: jest.fn().mockResolvedValue({ durum: "bulundu", device: { device_id: "1" }, url: TUNEL }),
  saglikSor: jest.fn(async (adres: string) =>
    adres === TUNEL ? { localIp: CIHAZ_IP } : null
  ),
  telefonIp: jest.fn().mockResolvedValue("192.168.1.87"),
  ...over,
});

describe("altAg", () => {
  it("/24 alt ağı çıkarır", () => {
    expect(altAg("192.168.1.44")).toBe("192.168.1");
  });

  it("bozuk biçimde null döner (yanlış karşılaştırma yapılmasın)", () => {
    for (const bozuk of ["", "192.168.1", "a.b.c.d", "192.168.1.999", "1.2.3.4.5"]) {
      expect(altAg(bozuk)).toBeNull();
    }
  });
});

describe("agTanisiYap", () => {
  it("KRITIK: üç kanıt da varsa İZOLASYON teşhisi koyar", async () => {
    const t = await agTanisiYap(kur());
    expect(t).toEqual({ durum: "izolasyon", cihazIp: CIHAZ_IP });
  });

  it("KRITIK: yerel adrese ULAŞILIYORSA izolasyon DEMEZ", async () => {
    // Ulaşılıyorsa keşif zaten çalışırdı → arıza başka yerde; suçu modeme atma.
    const t = await agTanisiYap(kur({ saglikSor: jest.fn().mockResolvedValue({ localIp: CIHAZ_IP }) }));
    expect(t).toEqual({ durum: "bilinmiyor" });
  });

  it("KRITIK: telefonun adresi okunamıyorsa TAHMİN ETMEZ", async () => {
    // Alt ağ karşılaştırması yapılamıyorsa izolasyon iddiası kanıtsızdır.
    const t = await agTanisiYap(kur({ telefonIp: jest.fn().mockResolvedValue(null) }));
    expect(t).toEqual({ durum: "bilinmiyor" });
  });

  it("FARKLI alt ağda 'farkli_ag' der (kod yolu zaten doğru cevap)", async () => {
    const t = await agTanisiYap(kur({ telefonIp: jest.fn().mockResolvedValue("10.0.0.5") }));
    expect(t).toEqual({ durum: "farkli_ag", cihazIp: CIHAZ_IP });
  });

  it("cihaz internetten de yanıt vermiyorsa 'cihaz_kapali'", async () => {
    // ⚠️ Cihaz kapalıyken yerel erişimsizlik izolasyon KANITI değildir.
    const t = await agTanisiYap(kur({ saglikSor: jest.fn().mockResolvedValue(null) }));
    expect(t).toEqual({ durum: "cihaz_kapali" });
  });

  it("kayıt bayat / uzak adres yoksa 'cihaz_kapali'", async () => {
    for (const durum of ["bayat", "adres_yok"]) {
      const t = await agTanisiYap(kur({ uzakCoz: jest.fn().mockResolvedValue({ durum, device: {} }) }));
      expect(t).toEqual({ durum: "cihaz_kapali" });
    }
  });

  it("buluta ulaşılamıyorsa (hata/yok) 'bilinmiyor'", async () => {
    for (const durum of ["hata", "yok"]) {
      const t = await agTanisiYap(kur({ uzakCoz: jest.fn().mockResolvedValue({ durum }) }));
      expect(t).toEqual({ durum: "bilinmiyor" });
    }
  });

  it("hiç eşleşilmemişse (kimlik yok) 'bilinmiyor' — bulut hiç sorgulanmaz", async () => {
    const uzakCoz = jest.fn();
    const t = await agTanisiYap(kur({ kimlikOku: jest.fn().mockResolvedValue(null), uzakCoz }));
    expect(t).toEqual({ durum: "bilinmiyor" });
    expect(uzakCoz).not.toHaveBeenCalled();
  });

  it("cihaz yerel adresini bildirmiyorsa 'bilinmiyor'", async () => {
    const t = await agTanisiYap(kur({ saglikSor: jest.fn().mockResolvedValue({}) }));
    expect(t).toEqual({ durum: "bilinmiyor" });
  });

  it("cihazın bildirdiği yerel adres BOZUKSA 'bilinmiyor'", async () => {
    const t = await agTanisiYap(kur({ saglikSor: jest.fn().mockResolvedValue({ localIp: "yok" }) }));
    expect(t).toEqual({ durum: "bilinmiyor" });
  });

  it("ÖNCE tünel, SONRA yerel yoklanır (sıra kanıtın mantığı)", async () => {
    const sira: string[] = [];
    const saglikSor = jest.fn(async (adres: string) => {
      sira.push(adres);
      return adres === TUNEL ? { localIp: CIHAZ_IP } : null;
    });
    await agTanisiYap(kur({ saglikSor }));
    expect(sira).toEqual([TUNEL, `http://${CIHAZ_IP}:8000`]);
  });
});

describe("taniMesaji", () => {
  it("izolasyon mesajı NE YAPILACAĞINI söyler ve cihaz adresini içerir", () => {
    const m = taniMesaji({ durum: "izolasyon", cihazIp: CIHAZ_IP });
    expect(m?.metin).toContain(CIHAZ_IP);
    expect(m?.metin).toMatch(/izolasyon/i);
  });

  it("KRITIK: 'bilinmiyor' için HİÇBİR ŞEY söylemez", () => {
    expect(taniMesaji({ durum: "bilinmiyor" })).toBeNull();
  });

  it("her teşhis edilebilir durumun bir metni vardır", () => {
    for (const t of [
      { durum: "izolasyon" as const, cihazIp: CIHAZ_IP },
      { durum: "farkli_ag" as const, cihazIp: CIHAZ_IP },
      { durum: "cihaz_kapali" as const },
    ]) {
      const m = taniMesaji(t);
      expect(m?.baslik?.length).toBeGreaterThan(0);
      expect(m?.metin?.length).toBeGreaterThan(0);
    }
  });
});
