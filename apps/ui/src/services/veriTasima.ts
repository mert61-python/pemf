// Author: mertaygn, cglrgrkn
/**
 * VERİ TAŞIMA (Ayarlar → şifreli yedek / geri yükleme) — zaman aşımı ve metinler TEK kaynakta (2-D).
 *
 * ⚠️ D2.E03 (İG-6.21 · Y84): bu iki çağrı varsayılan 8 sn zaman aşımıyla gidiyordu. 2000 seanslık şifreli klinikte geri yükleme ~3 dk
 * sürüyor (ölçüldü: 171 sn / 500 hasta + 2000 seans); istek 8,0 sn'de iptal ediliyor, ekran "Tekrar deneyin — ilk analiz MODEL YÜKLEMESİ
 * nedeniyle …" diyordu. Operatör tekrar deneyince ikinci istek ilk geri yükleme sürerken hedefi boş görüp kayıtları İKİYE katlıyordu
 * (sunucu yarısı D2.E02: ikinci istek artık 409). Sahip kararı Y84: ayrı UZUN zaman aşımı, işlem sürerken düğme kilitli ve
 * "Yükleniyor…", metin "Tekrar deneyin" DEMEZ.
 *
 * ⚠️ Bu sabitler `apiClient`e EKLENMEDİ: o modülü elle sahteleyen süitler yeni bir dışa aktarımı görmez (hafıza: apiClient elle sahte
 * fabrika). Kapı: src/screens/__tests__/SettingsVeriTasima.D2E01_E03.web.test.tsx
 */

/** Yedek alma ve geri yükleme isteklerinin zaman aşımı — 30 dk (aday doğrulamasının önerisi ≥ 15 dk; ölçülen en uzun ~5,5 dk). */
export const VERI_TASIMA_ZAMAN_ASIMI_MS = 30 * 60 * 1000;

/** Geri yükleme zaman aşımına uğrarsa: işlem cihazda SÜRÜYOR olabilir — tekrarlamak kayıtları çoğaltabilirdi. */
export const ICE_AKTARMA_ZAMAN_ASIMI_MESAJI =
  "Geri yükleme cihazda sürüyor olabilir — bitince kayıtlar görünür. İşlemi tekrarlamayın ve uygulamayı yeniden başlatmayın; " +
  "birkaç dakika sonra Seans Geçmişi'ni yenileyin.";

/** Yedek alma zaman aşımına uğrarsa: dosya cihazda hazırlanıyor olabilir. */
export const DISA_AKTARMA_ZAMAN_ASIMI_MESAJI =
  "Yedek alma cihazda sürüyor olabilir — cihaz zamanında yanıt vermedi (veri büyük olabilir). Bir süre bekleyip yedek dosyasının " +
  "oluşup oluşmadığını denetleyin.";
