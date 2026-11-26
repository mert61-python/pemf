/**
 * YS1c · Y320 (3) — SİTE TESTLERİNİN DİLİ TR'YE SABİT (vitest `setupFiles`; her test dosyasından ÖNCE yüklenir).
 *
 * NEDEN: bayrak açıkken site dili `?lang=` > kayıtlı seçim > TARAYICI YERELİ (`navigator.language`, src/i18n/dil.ts). Node ≥ 21'de
 * `globalThis.navigator` makinenin ICU yerelini taşır: bu makinede tr-TR, GitHub ubuntu koşucusunda (LANG=C.UTF-8) en-US → site-ci
 * 25-11'de 12 dosya / 37 test kırmızı (testler sitenin İngilizce hâlini gördü). Ürün davranışı DEĞİŞMEZ (Türkçe tarayıcı Türkçe görür).
 * Yalnız `language` TR'ye sabitlenir; EN testleri dili kendileri kurar (`__bayrakTestiAyarla`, `dilSec('en')`, `vi.stubGlobal`).
 * Diğer navigator özellikleri GERÇEK nesneden okunur (`Reflect.get` alıcısı gerçek nesne → Node'un özel alanlı alıcıları bozulmaz).
 * Kapı: src/__tests__/dilSabit.YS1.test.ts.
 */
export function dilTrSabitle(kok: { navigator?: Navigator } = globalThis): void {
  const asil = kok.navigator as Navigator
  Object.defineProperty(kok, 'navigator', {
    configurable: true,
    writable: true,
    value: new Proxy(asil, { get: (hedef, ad) => (ad === 'language' ? 'tr-TR' : Reflect.get(hedef, ad)) }),
  })
}

dilTrSabitle()
