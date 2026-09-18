// Author: mertaygn, cglrgrkn
/**
 * KULLANICI YOLCULUĞU — kullanıcı-dostuluk denetimi 3. parti (2026-08-20).
 *
 * Derin tarama, metin kalitesinden ayrı olarak AKIŞ kopuklukları ölçtü: kullanıcı bir soruyu
 * soruyor ama cevap sitede hiç yok, ya da bir düğmeye basıyor ve beklediği yere gitmiyor.
 * Bu dosya o kopuklukları kilitler.
 *
 * ⚠️ DOM YOK / YORUMLAR SOYULUR — gerekçeler `metin-guveni.test.ts` başlığında.
 */
import { describe, expect, it } from 'vitest'

import { kaynakSoy as soy } from './_soyucu'

import DOWNLOAD_SRC from '../pages/Download.tsx?raw'
import PRICING_SRC from '../pages/Pricing.tsx?raw'
import SUPPORT_SRC from '../pages/Support.tsx?raw'
import RESET_SRC from '../pages/ResetPassword.tsx?raw'
import ERRBOUND_SRC from '../components/ErrorBoundary.tsx?raw'
import CONFIG_SRC from '../config.ts?raw'

import { FAQ, CLIENT } from '../config'

// ─────────────────────────── 1) SSS: satın alma sorularının cevabı ───────────────────────────

describe('1) SSS kapsamı', () => {
  it('KRİTİK: satın alma kararını belirleyen sorular SSS’te CEVAPLANIR', () => {
    // Beş soruluk SSS yalnız kurulumu anlatıyordu; plan farkı, AI Pro'nun ne yaptığı, deneme
    // sonu, iptal/iade gibi karar sorularının cevabı sitenin HİÇBİR yerinde yoktu.
    // ⚠️ TÜRKÇE KÜÇÜK-HARF TUZAĞI: `toLocaleLowerCase('tr')` "AI Pro"yu "aı pro" yapar (I→ı) ve
    // desen tutmaz — ilk koşuda ölçüldü. Metni OLDUĞU GİBİ bırakıp desenleri `i` bayrağıyla ara.
    const hepsi = FAQ.map((f) => `${f.q} ${f.a}`).join('\n')
    const beklenen: ReadonlyArray<readonly [string, RegExp]> = [
      ['plan farkı', /pro ile pro\+|plan(lar)? arasındaki fark/i],
      ['AI Pro nedir', /AI Pro nedir/i],
      ['deneme sonu', /deneme süresi|14 gün.{0,20}sonunda|deneme biterse/i],
      ['iptal / iade', /iptal/i],
      ['Araştırma profili kime', /araştırma profili/i],
      ['mobil uygulama ne işe yarar', /telefon uygulaması|mobil uygulama/i],
    ]
    const eksik = beklenen.filter(([, d]) => !d.test(hepsi)).map(([ad]) => ad)
    expect(eksik).toEqual([])
  })

  it('KRİTİK: "her şey çevrimdışı çalışır" derken planın NEYİ belirlediği yazılır', () => {
    // SSS "tüm modeller cihazda, çevrimdışı çalışır" derken planlar "analiz sırada bekler"
    // diyordu; her şey cihazda koşuyorsa neden ödemeye bağlı bir sıra olduğu belirsizdi.
    // ⚠️ İkinci Türkçe tuzağı: JS'in `i` bayrağı "İ" (U+0130) ile "i"yi EŞLEŞTİRMEZ —
    // 'İnternet olmadan çalışır mı?' sorusu /internet/i ile bulunamıyordu (ölçüldü).
    const cevrimdisi = FAQ.find((f) => /çevrimdışı|[İi]nternet olmadan/.test(f.q))
    expect(cevrimdisi, 'çevrimdışı sorusu kayboldu').toBeTruthy()
    // ⚠️ BEKLENTİ GÜNCELLENDİ (8. parti) — GEVŞETME DEĞİL, KAYNAK DEĞİŞİMİ:
    // 6. partide bu satır /öncelik|sınır/ arıyordu, çünkü cevap "yoğun anlardaki İŞLEM
    // ÖNCELİĞİNİZİ belirler" diyordu. 8. partide o vaat bütün yüzeylerden KALDIRILDI (ölçülebilir
    // karşılığı yoktu: analizler klinik bilgisayarında koşuyor). Artık aranan şey, çelişkinin
    // yerine geçen DOĞRU cümledir: planın belirlediği şey AYLIK ANALİZ SAYISIDIR (jeton).
    // Eski kalıp geri gelirse 3. maddedeki kalıntı testleri kırmızıya döner — kapı açık kalmıyor.
    expect(`${cevrimdisi!.a}`, 'planın neyi belirlediği yazılmamış').toMatch(/analiz|jeton/i)
    expect(`${cevrimdisi!.a}`, 'kaldırılan hız/öncelik vaadi geri gelmiş').not.toMatch(
      /işlem önceliğ|yoğun anlarda|sırada bekle/i,
    )
    expect(`${cevrimdisi!.a}`).toMatch(/fark/i) // ilgili maddeye yönlendirme duruyor
  })
})

// ─────────────────────────── 2) İletişim yolu ───────────────────────────

describe('2) iletişim', () => {
  it('KRİTİK: kurumsal "İletişime Geçin" SSS sayfasına DEĞİL iletişime götürür', () => {
    // Kurumsal teklif bekleyen ziyaretçi "Sık sorulan sorular" başlığına düşüyordu.
    const s = soy(PRICING_SRC)
    const i = s.indexOf('İletişime Geçin')
    expect(i).toBeGreaterThan(-1)
    const cevre = s.slice(Math.max(0, i - 260), i)
    expect(cevre).toMatch(/mailto:/)
  })

  it('KRİTİK: destek sayfasında TELEFON ve yanıt süresi görünür', () => {
    // config'te telefon vardı, destek sayfasında yalnız e-posta duruyordu.
    const s = soy(SUPPORT_SRC)
    expect(s).toMatch(/COMPANY\.phone|tel:/)
    expect(s).toMatch(/iş günü|saat içinde/i)
  })
})

// ─────────────────────────── 3) Hata ekranlarından çıkış yolu ───────────────────────────

describe('3) hata ekranlarında ÇIKIŞ YOLU', () => {
  it('KRİTİK: ödeme hata bandında tıklanabilir destek/tekrar-dene bağlantısı var', () => {
    // "Tekrar deneyin veya destek ile iletişime geçin" diyordu ama hiçbiri tıklanabilir değildi.
    const s = soy(PRICING_SRC)
    const i = s.indexOf('Ödeme sırasında bir sorun')
    expect(i).toBeGreaterThan(-1)
    expect(s.slice(i - 400, i + 400)).toMatch(/mailto:|<a |Link to=/)
  })

  it('KRİTİK: genel hata ekranında "bize yazın" TIKLANABİLİR', () => {
    expect(soy(ERRBOUND_SRC)).toMatch(/mailto:/)
  })

  it('KRİTİK: şifre sıfırlama "yeniden başlatın" derken bir YOL gösterir', () => {
    // Sayfada hiçbir bağlantı/buton yoktu; kullanıcı akışı yeniden başlatamıyordu.
    const s = soy(RESET_SRC)
    const i = s.indexOf('süresi dolmuş')
    expect(i).toBeGreaterThan(-1)
    expect(s.slice(i, i + 700)).toMatch(/Link to=|href=/)
  })
})

// ─────────────────────────── 4) İndirme kararı ───────────────────────────

describe('4) indirme sayfası kararı', () => {
  it('KRİTİK: kartlar İNDİRİLECEK DOSYA BOYUTUNU gösterir', () => {
    // Dört kartın hiçbirinde boyut yoktu; kullanıcı ne indireceğini bilmiyordu.
    expect(soy(DOWNLOAD_SRC)).toMatch(/indirmeBoyutu|sizeMB|boyut/i)
  })

  it('KRİTİK: telefon uygulamasının NE İŞE YARADIĞI kartta yazar', () => {
    // Android kartı, masaüstünün yanında mı yoksa tek başına mı çalıştığını söylemiyordu.
    const not = soy(CONFIG_SRC).match(/androidRolNotu:\s*'([^']+)'/)?.[1] ?? ''
    expect(not.length).toBeGreaterThan(30)
    expect(soy(DOWNLOAD_SRC)).toMatch(/androidRolNotu/)
  })

  it('KRİTİK: disk gereksinimi ile paket hesaplayıcı ÇELİŞMEZ', () => {
    // Sistem gereksinimi "~5 GB", hesaplayıcı "≈1.8 GB" diyordu; ikisi de açıklamasızdı.
    const s = soy(DOWNLOAD_SRC)
    const i = s.search(/GB boş disk/)
    expect(i).toBeGreaterThan(-1)
    expect(s.slice(i - 200, i + 260)).toMatch(/seçtiğiniz profil|profil sayısına|değişir/i)
  })

  it('KARŞIT-KANIT: kurulum dosyası boyutu (küçük) ile toplam indirme AYRI AYRI anlatılır', () => {
    // Aşırı-düzeltme yönü: tek bir sayı yazmak ("5 GB indirilecek") kurulum dosyasının 3 MB
    // olduğu gerçeğini gizler ve kullanıcıyı gereksiz korkutur.
    expect(CLIENT.sizeMB).toBeLessThan(50)
    expect(soy(DOWNLOAD_SRC)).toMatch(/CLIENT\.sizeMB/)
  })
})

// ─────────────────────────── 5) Deneme süresi ───────────────────────────

describe('5) deneme süresi', () => {
  it('KRİTİK: "14 gün deneme" SONUNDA ne olacağı yazılıdır', () => {
    const hepsi = `${FAQ.map((f) => f.q + f.a).join(' ')} ${soy(CONFIG_SRC)}`
    expect(hepsi).toMatch(/deneme (süresi|sonunda|biterse)[^.]{0,140}(ücret|kart|devam|kapan|geç)/i)
  })
})
