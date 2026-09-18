// Author: mertaygn, cglrgrkn
/**
 * CİHAZ EŞLEŞTİRME — kod/kimlik ile uzak cihaza bağlanmanın TEK YOLU.
 *
 * NEDEN AYRI SERVİS (2026-08-13): bu akış Ayarlar ekranının içinde gömülüydü. Farklı ağdaki
 * ilk açılışta kullanıcıyı yönlendiren yeni bir karşılama akışı da aynı işi yapacaktı; aynı
 * mantığı ikinci kez yazmak, güvenlik değişmezlerinin iki kopyadan birinde eskimesi demekti.
 * Bu oturumda tam olarak o hatanın (paralel çözümleme yolları) bedeli ödendi.
 *
 * KORUNAN GÜVENLİK DEĞİŞMEZLERİ — sıralama dahil DEĞİŞTİRMEYİN:
 *   1. Çözümleme SEBEBİYLE döner (bkz. deviceRegistry): "kod yanlış" ile "cihazda uzaktan
 *      erişim kapalı" AYRI şeylerdir; ikisini `null`a indirmek kullanıcıyı yanlış yere bakmaya
 *      yönlendirir (2026-08-12 saha bildirimi).
 *   2. KAYDETMEDEN ÖNCE `/api/health` doğrulanır ve `device_id` KARŞILAŞTIRILIR. Cloudflare
 *      tünel URL'i başka bir kliniğe yeniden atanmış ya da Supabase satırı zehirlenmişse,
 *      kimlik uyuşmazlığında BAĞLANILMAZ — yanlış hastaya komut gönderme riski.
 *   3. Kod yolunda token TAKASI yapılır ve SONUCU denetlenir. Eskiden sonuç yok sayılıyordu →
 *      "bağlandı ✓" deniyor ama sonraki her istek 401 alıyordu (audit P0/#25).
 */
import AsyncStorage from "@react-native-async-storage/async-storage";

import { setStoredDeviceId, updateServiceConfig } from "@/services/config";
import { uzakCihaziKimlikleCoz, uzakCihaziKodlaCoz } from "@/services/deviceRegistry";
import { checkHealth, exchangeCodeForToken } from "@/services/discovery";

/** Girdi 8 karakteri aşmıyorsa EŞLEŞTİRME KODU, aşıyorsa CİHAZ KİMLİĞİ kabul edilir. */
export const KOD_MAX_UZUNLUK = 8;

export type EslesmeSonuc =
  | { durum: "ok"; url: string; deviceId: string }
  /** Çözümleme sebepleri (deviceRegistry ile birebir). */
  | { durum: "yok" }
  /** Cihaz kayıtlı ama uzak adresi yok. `sonGorulme`: bulut kaydının son güncellenme anı
   *  (ISO). Kayıt eskiyse sorun "uzaktan erişim kapalı" DEĞİL, cihazın buluta hiç
   *  yazamamasıdır (denetim 2026-08-28 #02). */
  | { durum: "adres_yok"; sonGorulme?: string }
  | { durum: "bayat" }
  | { durum: "hata" }
  /** Kayıt bulundu ama cihaz şu an yanıt vermiyor / kimlik doğrulanamadı. */
  | { durum: "ulasilamiyor" }
  /** Dönen adres biçimsel olarak geçersiz — mevcut ayarı BOZMA. */
  | { durum: "gecersiz_adres" }
  /** Bağlandı ama kod token'a çevrilemedi → istekler 401 olurdu; dürüstçe bildir. */
  | { durum: "kod_reddedildi" };

/** Kullanıcıya gösterilecek metin — TEK KAYNAK (iki ekran da aynısını söylesin). */
export function eslesmeMesaji(s: EslesmeSonuc): string {
  switch (s.durum) {
    case "ok":
      return "Cihaz eşleştirildi ve bağlanıldı ✓";
    case "adres_yok": {
      // ⚠️ DENETİM 2026-08-28 #02 — ESKİ CÜMLE İKİ KEZ YANLIŞ YÖNE KİLİTLİYORDU:
      // "Cihazın kendi ekranından uzaktan erişimi açın; kod doğru."
      // Ölçülen saha durumunda uzaktan erişim ZATEN AÇIK ve kodun doğru olduğu da bilinmiyor —
      // cihaz bulut kaydına 13 gündür yazamıyordu (sır uyuşmazlığı), yani buluttaki kod
      // ekrandakinden farklı olabilir. Kayıt bayatsa bunu SÖYLE; "kod doğru" iddiasını kaldır.
      const gun = s.sonGorulme ? Math.floor((Date.now() - new Date(s.sonGorulme).getTime()) / 86400000) : null;
      if (gun !== null && gun >= 1) {
        return (
          `Cihaz kayıtlı ama uzaktan erişim adresi yok ve bulut kaydı ${gun} gündür güncellenmemiş. `
          + "Bu genellikle cihazın buluta yazamadığı anlamına gelir (cihaz açık olsa bile). "
          + "Cihazın Ayarlar ekranındaki uyarıyı kontrol edin; sorun sürerse destek ekibine bildirin."
        );
      }
      return (
        "Cihaz bulundu ama uzaktan erişim adresi yok. Cihaz açıksa ve uzaktan erişim etkinse, "
        + "cihazın Ayarlar ekranındaki bulut kaydı uyarısını kontrol edin."
      );
    }
    case "bayat":
      return "Cihaz kayıtlı ama şu an çevrimdışı görünüyor. Cihazın açık ve internete bağlı olduğundan emin olun.";
    case "hata":
      return "Buluta ulaşılamadı (bağlantı/zaman aşımı). İnternetinizi kontrol edip tekrar deneyin.";
    case "ulasilamiyor":
      return "Cihaz bulundu ama şu an çevrimdışı ya da kimlik doğrulanamadı.";
    case "gecersiz_adres":
      return "Geçersiz cihaz adresi biçimi.";
    case "kod_reddedildi":
      return "Cihaz bulundu ama eşleştirme kodu kabul edilmedi — kodu kontrol edip tekrar deneyin.";
    default:
      // ⚠️ DÜRÜST MESAJ (denetim 2026-08-17): bu dal YALNIZ "kod yanlış" demek DEĞİL. Sunucudaki
      // `resolve_device` tazelik penceresi dışında kalan (uzun süredir kapalı) cihaz da buraya
      // düşer. Eskiden yalnız "Kodu kontrol edin" deniyordu ve kullanıcı yanlış yöne bakıp kodu
      // defalarca kontrol ediyordu — 2026-08-12 saha bildiriminin aynısı. Cümle pencere
      // genişletilmeden ÖNCE de SONRA da doğru: 30 günden eski cihaz hâlâ buraya düşer.
      return (
        "Bu kod/kimlikle eşleşen çevrimiçi cihaz bulunamadı. Cihaz uzun süredir kapalı/çevrimdışıysa "
        + "da bu mesajı alırsınız: önce cihazın açık ve internete bağlı olduğundan emin olun, sonra "
        + "kodu kontrol edin."
      );
  }
}

/**
 * Kod ya da cihaz kimliğiyle uzak cihaza bağlan; başarılıysa adresi ve kimliği KALICI yaz.
 *
 * Çağıran yalnız arayüz işini yapar (toast, durum rozeti, WS yeniden bağlama) — bağlantı
 * kararının kendisi burada, tek yerde verilir.
 */
export async function cihazaBaglan(girdi: string): Promise<EslesmeSonuc> {
  const input = girdi.trim();
  if (!input) return { durum: "yok" };

  try {
    const kodMu = input.length <= KOD_MAX_UZUNLUK;
    const c = kodMu ? await uzakCihaziKodlaCoz(input) : await uzakCihaziKimlikleCoz(input);
    if (c.durum !== "bulundu") {
      // ⚠️ DENETİM 2026-08-28 #02: `adres_yok` dalında `deviceRegistry` `device`i (dolayısıyla
      // `last_seen`i) DÖNDÜRÜYOR ama burada atılıyordu. Oysa arızayı yaşayan kişi tam da bu
      // uzak operatördür: cihazın bulut kaydı 13 gündür güncellenmediği hâlde kendisine
      // "uzaktan erişimi açın; kod doğru" deniyor — ikisi de yanlış yöne kilitliyor.
      // Kaydın ne kadar bayat olduğunu taşırsak mesaj gerçeği söyleyebilir.
      if (c.durum === "adres_yok" && c.device?.last_seen) {
        return { durum: "adres_yok", sonGorulme: c.device.last_seen };
      }
      return { durum: c.durum };
    }

    const url = c.url;
    const deviceId = c.device.device_id;

    // (2) Kaydetmeden ÖNCE canlılık + KİMLİK doğrulaması. [5.9]: kimligiKaydet:false —
    // checkHealth'in "başarılı yanıtta deviceId'yi sakla" yan etkisi token takasından ÖNCE
    // koştuğu için, takas düşse de kayıtlı kimlik B cihazına dönüyordu (F3 delinmesi).
    // Kalıcı kimlik yazımı yalnız takas başarılıysa aşağıdaki setStoredDeviceId'de.
    if (!(await checkHealth(url, deviceId, { kimligiKaydet: false }))) return { durum: "ulasilamiyor" };

    // Geçersiz adres mevcut ayarı BOZMASIN.
    if (!updateServiceConfig(url)) return { durum: "gecersiz_adres" };

    // (3) Kod yolunda token takası — sonucu DENETLE.
    const tokenOk = kodMu ? await exchangeCodeForToken(url, input) : true;

    // ⚠️ TOKEN YOKSA KALICI YAZIM YOK (denetim 2026-08-17). Eskiden takas düşse de adres+device_id
    // diske yazılıyor, fonksiyon yalnızca `kod_reddedildi` dönüyordu. İKİ CİHAZLI klinikte sonuç:
    // telefon A cihazıyla LAN'da çalışırken B'nin kodu girilir, health+device_id geçer ama takas
    // 429/404 ile düşer → adres B-TÜNELİNE yazılır, A'nın LAN adresi diskten SİLİNMİŞ olur,
    // token yoktur → REST 401 / WS 1008. Kullanıcı Ayarlar'dan kodu tekrar girmeden düzelmez.
    // Oturum içi config (`updateServiceConfig`, yukarıda) DEĞİŞMEZ → kullanıcı hemen tekrar
    // deneyebilir; tek cihazlı klinikte keşif merdiveni bir sonraki turda kendini onarır.
    if (!tokenOk) return { durum: "kod_reddedildi" };

    await setStoredDeviceId(deviceId);
    try {
      await AsyncStorage.setItem("@pemf_server_address", url);
    } catch {
      // Adres kalıcı yazılamadıysa oturum içi bağlantı yine çalışır; sonraki açılışta keşif devreye girer.
    }

    return { durum: "ok", url, deviceId };
  } catch {
    return { durum: "hata" };
  }
}
