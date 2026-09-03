// Author: mertaygn, cglrgrkn
/**
 * ckdOnKontrol — CKD (kronik böbrek hastalığı) analizi için GÖNDERİM ÖNCESİ eyleme dönük ön-kontrol.
 * ============================================================================
 * B5 (denetim 2026-09-03): sunucunun asgari-girdi kapısı (utils/klinik_asgari.py: CKD_MIN_ALAN=6
 * dolu alan VE {sc,bu,sg,al,hemo} çekirdeğinden en az biri) yalnız "Bulgular" düğmeleriyle
 * (rbc/pc/pcc/ba/htn/dm/cad/appet/pe/ane) ASLA sağlanamaz → sayısal alan girilmeden "ne seçilirse
 * seçilsin" 422 dönüyor, UI bunu jenerik "Analiz sırasında hata oluştu."a çeviriyordu (gerekçe
 * kayboluyordu). Bu fonksiyon aynı kuralı istemcide uygular ve NE yapılacağını söyler.
 *
 * ⚠️ Sunucu 422 kapısı NİHAİDİR; bu yalnız kullanıcıya erken, anlaşılır geri bildirimdir.
 * Sabitler klinik_asgari.py ile ELLE eşlenir — orası değişirse burası da güncellenmeli.
 * Saf fonksiyon (AiHubScreen native modül yüklediği için ayrı dosyada; aiHataDetayi.ts deseni).
 */

/** klinik_asgari.py CKD_MIN_ALAN paritesi. */
export const CKD_MIN_ALAN = 6;
/** klinik_asgari.py CKD_CEKIRDEK paritesi — böbrek işlevine dair en az biri gerekli. */
export const CKD_CEKIRDEK = ["sc", "bu", "sg", "al", "hemo"] as const;

/**
 * Payload (yalnız DOLU alanlar, UCI CKD anahtarlarıyla) yeterli mi?
 * @returns null = gönderilebilir; string = kullanıcıya gösterilecek eyleme dönük mesaj.
 * `explain` bayrağı alan sayılmaz (payload'a eklenmiş olsa da).
 */
export function ckdOnKontrol(
  payload: Record<string, unknown>,
  etiket: (k: string) => string = (k) => k,
): string | null {
  const dolu = Object.keys(payload).filter((k) => k !== "explain").length;
  const cekirdekVar = CKD_CEKIRDEK.some((k) => k in payload);
  if (dolu >= CKD_MIN_ALAN && cekirdekVar) return null;
  const eksik = CKD_CEKIRDEK.filter((k) => !(k in payload)).map(etiket).join(", ");
  return (
    `Analiz için en az ${CKD_MIN_ALAN} alan doldurun (şu an ${dolu}) ve böbrek işlevine dair ` +
    `en az bir değer girin: ${eksik}. Bulgu düğmeleri tek başına yeterli değildir.`
  );
}
