/**
 * I18NI-A2.10 KALICI KAPI (14-I18N-INCELEME): sitenin YOKLUK kapıları (kullandikca-ode / metin-guveni / dogruluk / sade-dil) sayfa kaynağını
 * `gorunenMetinler(src)` ile tarar = kaynak + O DOSYANIN değişmez `t('…')` anahtarları. Sayfada config getter'ından (`PLANS[i].desc` →
 * `i18n.t('icerik.plan.*')`) ya da dinamik anahtarla (`t(n.anahtar)`, `t(s.baslik)`) çizilen metin taranmaz. Ölçüldü: "yoğun saatlerde
 * sırada bekleme" iddiası `icerik.plan.baslangic.aciklama`ya (fiyat sayfası plan kartında görünür) eklenince `kullandikca-ode.test.ts`
 * 19/19 YEŞİL. Yasaklı iddia için güvenli üst küme: BÜTÜN TR (ve EN) kataloğu.
 * D6.31 (B-7.1): "Anında analiz" artık listede — Pro+ plan rozeti kaldırıldı (12c [İNCELE] kapandı); fiyat kartında çizim kapısı
 * `fiyat-destek-vaadi.D6_31.test.ts`.
 * Koşum: vitest run src/__tests__/yokluk-katalog.I18NI.test.ts
 */
import { describe, expect, it } from 'vitest'
import { EN, TR } from './_kaynakMetni'

const TUM_TR = Object.values(TR).join('\n')
const TUM_EN = Object.values(EN).join('\n')

describe('yasaklı iddialar KATALOĞUN HİÇBİR değerinde yok (sayfaya hangi yoldan gelirse gelsin)', () => {
  it.each([
    ['yoğun saatte bekleme (kaldırılan kuyruk vaadi)', /yoğun saatlerde.{0,30}bekleme/i, /peak hours?.{0,30}wait/i],
    ['gerçek-zamanlı öncelik satışı', /gerçek[- ]zamanlı öncelik/i, /real[- ]time priority/i],
    ['taslak / şablon iç notu', /şablondur/i, /this text is a template/i],
    ['telefon tek başına terapi uygulamaz (yanlış sınır)', /telefon tek başına terapi uygulamaz/i, /phone alone does not (apply|deliver) therapy/i],
    ['anında analiz (kaldırılan hız vaadi — eski Pro+ rozeti)', /anında analiz/i, /instant analys[ie]s/i],
  ])('%s', (_ad, tr, en) => {
    expect(TUM_TR).not.toMatch(tr)
    expect(TUM_EN).not.toMatch(en)
  })
})
