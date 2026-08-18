// Author: mertaygn, cglrgrkn
/**
 * ŞİRKET KÜNYESİ — TEK KAYNAK (2026-08-07)
 *
 * Tıbbi cihaz yazılımında kullanıcı, hangi tüzel kişiye ulaşacağını uygulama içinden
 * görebilmelidir. Bu sabitler `pemf-vet-web/src/config.ts` içindeki `COMPANY` bloğuyla
 * AYNI bilgileri taşır — biri değişirse diğeri de güncellenmelidir.
 *
 * ⚠️ Buraya yer tutucu (`[TİCARİ ÜNVAN]` gibi) YAZMAYIN: künye kullanıcıya gösterilir,
 * eksik bilgi göstermektense alanı hiç göstermemek doğrudur.
 */
export const FIRMA = {
  urun: "PEMF Vet",
  unvan: "İBİA Teknoloji Makina Arge Danışmanlık Sanayi ve Ticaret Limited Şirketi",
  kisaUnvan: "İBİA Teknoloji Ltd. Şti.",
  adres: "Yeşiltepe Mah. İsmet İnönü 2 Cad. No: 2-57, Tepebaşı / Eskişehir",
  tel: "+90 531 388 04 13",
  eposta: "destek@v-pemf.com",
  mersis: "0469084142300001",
  vkn: "4690841423",
  ticaretSicil: "45277",
  vergiDairesi: "Eskişehir Vergi Dairesi Başkanlığı",
  yil: 2026,
} as const;
