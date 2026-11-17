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
 * ⚠️ EŞLEME (D2.E11 · SAHİP KARARI A-62, 2-C): kayıt TEK anahtara yazılır — kimlikliyse KİMLİĞE, kimliksizse ADA; kimliği olan
 * hasta YALNIZ kimliğiyle aranır (AD YEDEĞİ YOK). Eskiden kimlikli kayıt ad anahtarına da yazılıyor ve kimlik bulunamayınca
 * ada düşülüyordu → aynı adlı ikinci hayvan (Mia/Köpek) birincinin (Mia/Kedi) analizini Hastalar kartında ve "kaldığın
 * yerden" şeridinde görüyordu (ölçüldü, İG-6.59). Bilinen bedel (A-62): kimliksiz ESKİ kayıtlar kimlikli hastanın kartında
 * ve şeridinde görünmez — AI Geçmişi'nde kalır. Kimliği olmayan hasta (eski istemci) adla eşlenmeye devam eder.
 * Kapı: screens/__tests__/sonAnalizAdYedegi.E11.A62.web.test.tsx.
 */

import { aramaNormalize } from "@/utils/aramaNormalize";
import { inScope, type PatientScope } from "@/utils/patientScope";
import { etkinBicimYereli } from "@/i18n/dil";

/** `/api/ai/log` kaydının bu modülün ihtiyaç duyduğu asgari şekli. */
export interface AnalizKaydi {
  id?: number;
  patient_name?: string | null;
  /**
   * Hastanın OPAK KİMLİĞİ (2026-09-12 taşıması). Eşlemede ADIN ÖNÜNE geçer.
   *
   * ⚠️ Eski kayıtlarda BOŞTUR (taşıma yalnız adı TEK bir hastaya çözülenleri doldurur —
   * aynı adlı iki hayvan varsa tahmin EDİLMEZ). A-62: böyle bir kayıt yalnız AD anahtarına yazılır; kimlikli hasta onu
   * görmez (bilinen bedel — AI Geçmişi'nde kalır).
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
    // ⚠️ A-62: TEK anahtar — kimlikli kayıt yalnız KİMLİĞE (aynı adlı başka hayvanın ad aramasına SIZMAZ), kimliksiz eski
    // kayıt yalnız ADA. Eskiden ikisine birden yazılıyordu (bkz. dosya başı).
    koy(kayitHastaAnahtari(k), k);
  }
  return harita;
}

/**
 * D2.71 (B-6.20): bir AI KAYDININ hasta anahtarı — TEK anahtar: kimliği varsa KİMLİK (`#…`), yoksa ad. Aynı adlı iki hayvanın
 * kimlikli kayıtları AYRI anahtar alır; kimliksiz ESKİ kayıtlar ada göre birlikte kalır (ayrılamaz — yalnız gösterim).
 * AI Geçmişi'nin hasta çipleri ve süzmesi bunu kullanır.
 */
export function kayitHastaAnahtari(k: { patient_uuid?: string | null; patient_name?: string | null }): string {
  return kimlikAnahtari(k?.patient_uuid) || adAnahtari(k?.patient_name);
}

/** Kimlik anahtarı — ada çarpışmasın diye ön ekli (boş kimlik anahtar ÜRETMEZ). */
export function kimlikAnahtari(kimlik: string | null | undefined): string {
  const k = String(kimlik ?? "").trim();
  return k ? `#${k}` : "";
}

/**
 * Bir hasta için DENENECEK anahtarlar.
 *
 * ⚠️ A-62 (sahip kararı, 2-C): kimliği olan hasta YALNIZ kimliğiyle aranır — AD YEDEĞİ YOK. Eskiden kimlik bulunamayınca ada
 * düşülüyordu ("ad yedeği kaldırılamaz" gerekçesi: taşımanın bilerek kimliksiz bıraktığı eski kayıtlar ekrandan kaybolmasın);
 * bu, aynı adlı ikinci hayvana birincinin analizini gösteriyordu. Sahip, eski kayıtların kart/şeritte görünmemesini (AI
 * Geçmişi'nde kalırlar) yanlış hastaya atfa tercih etti. Kimliği olmayan hasta adla aranır.
 */
export function hastaAnahtarlari(hasta: { id?: string | null; name?: string | null }): string[] {
  const kimlik = kimlikAnahtari(hasta?.id);
  return kimlik ? [kimlik] : [adAnahtari(hasta?.name)].filter(Boolean);
}

/** Haritadan bir hastanın son analizi — kimliği varsa YALNIZ kimlikle (A-62), yoksa adla. */
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

/** Kart altına yazılacak kısa özet (TR "12.09.2026 · Kapanma %42" · EN "12/09/2026 · …" — Y295) — yoksa null. */
export function sonAnalizOzeti(k: AnalizKaydi | undefined | null): string | null {
  if (!k) return null;
  const parcalar: string[] = [];
  const t = Date.parse(k.created_at ?? "");
  if (Number.isFinite(t)) parcalar.push(new Date(t).toLocaleDateString(etkinBicimYereli()));
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
