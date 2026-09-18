// Author: mertaygn, cglrgrkn
/**
 * UZAK OPERATÖRE DÜRÜST MESAJ — denetim 2026-08-28 #02.
 *
 * Arızayı yaşayan kişi CİHAZIN BAŞINDAKİ değil, uzaktan bağlanmaya çalışan operatördür.
 * Ona gösterilen eski cümle iki kez yanlış yöne kilitliyordu:
 *
 *     "Cihaz bulundu ama uzaktan erişim adresi yok.
 *      Cihazın kendi ekranından uzaktan erişimi açın; kod doğru."
 *
 * Ölçülen saha durumunda (a) uzaktan erişim ZATEN açıktı, (b) kodun doğru olduğu da
 * bilinmiyordu — cihaz bulut kaydına 13 gündür yazamadığı için buluttaki kod ekrandakinden
 * farklı olabilir. Kullanıcı "uzaktan erişimi aç" diye kapalı olmayan bir şeyi açmaya ve
 * "kod doğru" denildiği için kodu sorgulamamaya yönlendiriliyordu.
 *
 * `deviceRegistry._cozumle` bu dalda `device`i (dolayısıyla `last_seen`i) zaten döndürüyordu;
 * bilgi `pairing.cihazaBaglan` içinde atılıyordu. Artık taşınıyor ve mesaj gerçeği söylüyor.
 */
import { eslesmeMesaji } from "@/services/pairing";

const gunOnce = (n: number) => new Date(Date.now() - n * 86400000).toISOString();

describe("eslesmeMesaji — adres_yok", () => {
  it("KRİTİK: yanıltıcı 'kod doğru' iddiası KALDIRILDI", () => {
    for (const s of [
      { durum: "adres_yok" } as const,
      { durum: "adres_yok", sonGorulme: gunOnce(13) } as const,
    ]) {
      expect(eslesmeMesaji(s)).not.toMatch(/kod doğru/i);
    }
  });

  it("KRİTİK: bayat kayıtta GÜN SAYISI söylenir ve doğru yöne bakılır", () => {
    const m = eslesmeMesaji({ durum: "adres_yok", sonGorulme: gunOnce(13) });
    expect(m).toMatch(/13 gün/);
    // Asıl sebep: cihaz buluta YAZAMIYOR — "cihaz kapalı" değil.
    expect(m).toMatch(/buluta yazamadığı/i);
    // Operatörü, rozetin göründüğü yere yönlendir.
    expect(m).toMatch(/Ayarlar/);
  });

  it("gün bilgisi yoksa da 'uzaktan erişimi açın' emri verilmez (zaten açık olabilir)", () => {
    const m = eslesmeMesaji({ durum: "adres_yok" });
    expect(m).toMatch(/Ayarlar/);
    expect(m).not.toMatch(/kendi ekranından uzaktan erişimi açın/i);
  });

  it("bugün güncellenmiş kayıtta gün sayısı UYDURULMAZ", () => {
    const m = eslesmeMesaji({ durum: "adres_yok", sonGorulme: new Date().toISOString() });
    expect(m).not.toMatch(/\d+ gündür/);
  });

  it("karşıt-kanıt: diğer durumların mesajları DEĞİŞMEDİ", () => {
    expect(eslesmeMesaji({ durum: "ok", url: "https://x", deviceId: "1" })).toMatch(/eşleştirildi/i);
    expect(eslesmeMesaji({ durum: "bayat" })).toMatch(/çevrimdışı/i);
    expect(eslesmeMesaji({ durum: "kod_reddedildi" })).toMatch(/kabul edilmedi/i);
    expect(eslesmeMesaji({ durum: "yok" })).toMatch(/bulunamadı/i);
  });
});
