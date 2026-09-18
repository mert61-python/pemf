// Author: mertaygn
/**
 * HASTA BAŞINA SON ANALİZ — ev sahibi profili için (sahip isteği 2026-09-12).
 * ==========================================================================
 * "evcil hayvan modunda ana ekran tabına gerek yok. onu kaldır ve neler ekleyebileceğimizi
 *  düşün." → önerilerden ikisi burada:
 *   · Hastalar ekranında her hayvanın SON ANALİZİ ("Mia'ya en son ne zaman baktırdım?")
 *   · Akıllı Teşhis'te "kaldığın yerden" — son analiz edilen hayvan
 *
 * ⚠️ YENİ BACKEND YOK: `/api/ai/log` zaten hasta adı + tarih + özet döndürüyor. Ev sahibine
 * yeni bir uç açmak, olmayan bir veri modeli icat etmek olurdu.
 *
 * ⚠️ EŞLEME HASTA ADIYLA: `ai_analyses` tablosunda hasta KİMLİĞİ yok, ADI var. Bu bir
 * sınırlamadır ve burada AÇIKÇA söylenir: aynı adlı iki hayvan varsa analizler karışır.
 * Kimliğe geçmek backend + migrasyon işidir; o yapılana kadar ad bazlı eşleme, hiç
 * göstermemekten iyidir (ev sahibi profilinde zaten birkaç hayvan olur).
 */

import { aramaNormalize } from "@/utils/aramaNormalize";
import { inScope, type PatientScope } from "@/utils/patientScope";

/** `/api/ai/log` kaydının bu modülün ihtiyaç duyduğu asgari şekli. */
export interface AnalizKaydi {
  id?: number;
  patient_name?: string | null;
  /**
   * Hastanın OPAK KİMLİĞİ (2026-09-12 taşıması). Eşlemede ADIN ÖNÜNE geçer.
   *
   * ⚠️ Eski kayıtlarda BOŞTUR (taşıma yalnız adı TEK bir hastaya çözülenleri doldurur —
   * aynı adlı iki hayvan varsa tahmin EDİLMEZ). Bu yüzden eşleme kimlik→ad sırasıyla
   * çalışır; ad yedeği kaldırılırsa eski kayıtlar EKRANDAN KAYBOLUR.
   */
  patient_uuid?: string | null;
  /**
   * Analizi yapan hekim — KAPSAM SÜZGECİ İÇİN ZORUNLU alan.
   *
   * ⚠️ İlk sürümde YOKTU ve bu, denetimde bulunan bir sızıntıya yol açtı: `/api/ai/log`
   * operatör süzgeci DESTEKLEMEZ (tüm kliniği döndürür), dolayısıyla çağıran taraf
   * `patientScope.inScope` ile süzmek ZORUNDADIR. Alan tipte olmayınca o süzme yazılamıyor,
   * yazılmayınca da "Benim Hastalarım" kartının altında BAŞKA bir hekimin analizi görünüyordu.
   */
  operator_email?: string | null;
  created_at?: string | null;
  result_summary?: string | null;
  module_label?: string | null;
  module_id?: string | null;
  confidence?: number | null;
}

/**
 * Hasta adı (normalize) → o hastanın EN YENİ analizi.
 *
 * ⚠️ "EN YENİ" SIRAYA GÜVENMEZ: `/api/ai/log` id DESC döner ama bir gün sıralama değişirse
 * kart sessizce ESKİ analizi gösterirdi. Karşılaştırma `created_at`/`id` ile AÇIK yapılır.
 */
export function hastayaGoreSonAnaliz(kayitlar: readonly AnalizKaydi[] | null | undefined): Map<string, AnalizKaydi> {
  const harita = new Map<string, AnalizKaydi>();
  const koy = (anahtar: string, k: AnalizKaydi) => {
    if (!anahtar) return;
    const mevcut = harita.get(anahtar);
    if (!mevcut || dahaYeni(k, mevcut)) harita.set(anahtar, k);
  };
  for (const k of kayitlar ?? []) {
    // ⚠️ HER İKİ ANAHTAR DA YAZILIR (kimlik VE ad):
    //  · Kimlik → 2026-09-12 taşımasından sonraki kayıtlar; aynı adlı iki hayvanı AYIRIR.
    //  · Ad     → kimliği olmayan ESKİ kayıtlar; taşıma belirsiz adları BİLEREK doldurmadı.
    // İkisini birden yazmak, `hastaAnahtarlari` ile arayan tarafın önce kimliği deneyip
    // bulamazsa ada düşmesini sağlar — geçmiş taşıma günü ikiye bölünmüş görünmez.
    koy(kimlikAnahtari(k?.patient_uuid), k);
    koy(adAnahtari(k?.patient_name), k);
  }
  return harita;
}

/** Kimlik anahtarı — ada çarpışmasın diye ön ekli (boş kimlik anahtar ÜRETMEZ). */
export function kimlikAnahtari(kimlik: string | null | undefined): string {
  const k = String(kimlik ?? "").trim();
  return k ? `#${k}` : "";
}

/**
 * Bir hasta için DENENECEK anahtarlar — SIRA ÖNEMLİ: önce kimlik, sonra ad.
 *
 * ⚠️ AD YEDEĞİ KALDIRILAMAZ: taşıma, adı birden çok hastaya çözülen kayıtları BİLEREK
 * kimliksiz bıraktı (yanlış kimlik yazmak geri alınamaz bir karışma olurdu). Yedek
 * kaldırılırsa o kayıtlar ekrandan sessizce kaybolur.
 */
export function hastaAnahtarlari(hasta: { id?: string | null; name?: string | null }): string[] {
  return [kimlikAnahtari(hasta?.id), adAnahtari(hasta?.name)].filter(Boolean);
}

/** Haritadan bir hastanın son analizi — önce kimlik, sonra ad. */
export function hastaninSonAnalizi(
  harita: Map<string, AnalizKaydi>,
  hasta: { id?: string | null; name?: string | null },
): AnalizKaydi | undefined {
  for (const anahtar of hastaAnahtarlari(hasta)) {
    const k = harita.get(anahtar);
    if (k) return k;
  }
  return undefined;
}

/** İki kayıttan `a` daha mı yeni? (önce tarih, eşitlik/eksiklikte id) */
function dahaYeni(a: AnalizKaydi, b: AnalizKaydi): boolean {
  const ta = Date.parse(a?.created_at ?? "");
  const tb = Date.parse(b?.created_at ?? "");
  if (Number.isFinite(ta) && Number.isFinite(tb) && ta !== tb) return ta > tb;
  return (a?.id ?? 0) > (b?.id ?? 0);
}

/**
 * Hasta adını eşleme anahtarına çevirir — TEK KAYNAK `aramaNormalize`.
 *
 * ⚠️ KENDİ NORMALİZASYONUNU YAZMA — ASIL KURAL BU. `aramaNormalize` Türkçe katlamayı
 * (İ→i, I→ı + NFC) zaten doğru uyguluyor ve bu deponun "aynı kural ÜÇ YERDE kopyalanmış"
 * bulgusunun çözümü olarak TEK KAYNAK ilan edilmiş. Dördüncü bir kopya, o bulgunun
 * tekrarı olurdu — kopya, kuralın bir yerde düzeltilip diğerinde kalması demektir.
 *
 * ⚠️ İLK SÜRÜM `toLocaleUpperCase("tr")` YAZIYORDU. Mutasyonla ölçüldü: büyük-harf katlama
 * da eşleştirme için ÇALIŞIYOR (iki taraf aynı yönde katlandığı sürece). Yani hata
 * "yanlış yön" değil, TEK KAYNAĞI ATLAMAKTI. Buradaki kapı da onu ölçer: `adAnahtari`
 * çıktısı `aramaNormalize` çıktısıyla AYNI olmalı.
 */
export function adAnahtari(ad: string | null | undefined): string {
  return aramaNormalize(String(ad ?? "").trim());
}

/** Kart altına yazılacak kısa özet ("12.09.2026 · Kapanma %42") — yoksa null. */
export function sonAnalizOzeti(k: AnalizKaydi | undefined | null): string | null {
  if (!k) return null;
  const parcalar: string[] = [];
  const t = Date.parse(k.created_at ?? "");
  if (Number.isFinite(t)) parcalar.push(new Date(t).toLocaleDateString("tr-TR"));
  const ozet = (k.result_summary || "").trim();
  if (ozet) parcalar.push(ozet);
  else {
    const modul = (k.module_label || k.module_id || "").trim();
    if (modul) parcalar.push(modul);
  }
  return parcalar.length ? parcalar.join(" · ") : null;
}

/**
 * Bir AI analiz kaydı bu kapsamda GÖRÜNMELİ mi?
 *
 * ═══════════════════════════════════════════════════════════════════════════════
 * ⚠️ NEDEN AYRI BİR AD — DENETİMDE ÖĞRENİLDİ (2026-09-12)
 * ═══════════════════════════════════════════════════════════════════════════════
 * `/api/ai/log` OPERATÖR SÜZGECİ DESTEKLEMEZ: her zaman TÜM kliniğin analizlerini döndürür.
 * Süzme sorumluluğu çağıranda olduğu için, süzmeyi UNUTAN her yeni çağrı sessiz bir kapsam
 * sızıntısıdır — nitekim ev sahibi eklentileri için eklenen iki yeni çağrı da unutmuştu ve
 * "Benim Hastalarım" kartının altında BAŞKA hekimin analizi görünüyordu.
 *
 * ⚠️ KAPI NEDEN `inScope(`E PİNLENEMEDİ: `PatientScreen` HASTA süzmesi için zaten `inScope`
 * kullanıyor; dosyada o ad geçtiği için analiz süzgeci silinse bile kapı YEŞİL kalıyordu
 * (mutasyonla ölçüldü). Bu yüzden analiz kayıtlarına ÖZGÜ, ayrı bir ad gerekiyor —
 * `tests/test_kapsam_sahipligi.py` `/ai/log` çağıran her ekranda `kapsamda(` arar.
 *
 * ⚠️ KURAL KOPYALANMAZ: karar yine `patientScope.inScope`tan gelir; bu yalnız ADLANDIRILMIŞ
 * bir geçittir ("sahipsiz = benim" kuralı tek yerde kalır).
 */
export function kapsamda(
  kayit: { operator_email?: string | null },
  scope: PatientScope,
  myEmail: string,
): boolean {
  return inScope(kayit, scope, myEmail);
}
