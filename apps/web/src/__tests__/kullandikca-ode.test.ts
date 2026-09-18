// Author: mertaygn, cglrgrkn
/**
 * KULLANDIKÇA ÖDE (PAYG) — 8. parti, sahip isteği 2026-08-20.
 *
 * Sahip: "hiç önden satın almadan kullandıkça öde gibi bir üyelik olmalı."
 * Sahip (aynı tur): "ücretsiz sistem şu an aktifte devam etmeli, henüz aktif etme —
 * jeton kalsın, altyapı hazır şekilde."
 *
 * Bu dosya iki şeyi kilitler:
 *
 *  A) YENİ PLANIN DÜRÜST GÖSTERİMİ. Kullandıkça-öde planının aylık ücreti YOKTUR. Fiyat
 *     yollarının hepsi `monthly ?? 0` yazıyordu → yeni plan "₺0/ay" ya da "test sonrası ₺0/ay"
 *     olarak görünüyordu; ikisi de YANLIŞ (ücret jeton başınadır, sıfır değildir).
 *
 *  B) 7. PARTİDE KALDIRILAN "KUYRUK / HIZ" VAADİNİN SAYFALARDAKİ KALINTILARI. Vaat
 *     `config.ts` içinden kaldırılmıştı; ama Pricing/Home/Ödeme sayfalarının KENDİ gömülü
 *     metinleri hayatta kaldı. Bu, deponun 1 numaralı hata deseninin aynısı: "aynı kural, iki
 *     yüzey — biri düzeltilmiş, öteki değil". Yapay zekâ analizleri KLİNİK BİLGİSAYARINDA
 *     koşar; "yoğun saatte beklersiniz / anında gelir" cümlesinin ölçülebilir karşılığı yoktur.
 *
 * Ayrıca ÇİFT KAYNAK kapatılır: karşılaştırma tablosunun sütun başlıkları `['Başlangıç','Pro',
 * 'Pro+']` diye KODA GÖMÜLÜYDÜ. PLANS'e plan eklemek tabloyu sessizce eksik bırakıyordu.
 */
import { describe, expect, it } from 'vitest'

import { kaynakSoy as soy } from './_soyucu'

import CONFIG_SRC from '../config.ts?raw'
import PRICING_SRC from '../pages/Pricing.tsx?raw'
import HOME_SRC from '../pages/Home.tsx?raw'
import ODEME_SRC from '../pages/Odeme.tsx?raw'
import { PLANS, COMPARE, FAQ, JETON, FREE_MODE } from '../config'
import { planFiyatGorunumu, planKisaFiyat } from '../lib/planFiyat'

const payg = () => PLANS.find((p) => p.tier === 'kullandikca')

describe('1) kullandıkça-öde planı vardır ve dürüst anlatılır', () => {
  it('KRİTİK: plan listede yer alır ve aylık ücreti YOKTUR', () => {
    const p = payg()
    expect(p, 'kullandıkça-öde planı PLANS içinde yok').toBeTruthy()
    expect(p!.monthly, 'kullandıkça-öde planına aylık ücret yazılmış').toBeNull()
    expect(p!.yearly, 'kullandıkça-öde planına yıllık ücret yazılmış').toBeNull()
  })

  it('KRİTİK: "önden ödeme yok" vaadi metinde AÇIKÇA geçer', () => {
    const p = payg()!
    const hepsi = [p.desc, p.period, p.jetonHakki, ...p.features].join(' ').toLowerCase()
    expect(hepsi, 'planın ayırt edici vaadi (aylık ücret/önden ödeme YOK) yazılmamış').toMatch(
      /(aylık ücret (ve önden jeton alımı )?yok|önden ödeme yok)/,
    )
  })

  it('KRİTİK: jeton birim fiyatı tek kaynaktan gelir ve plan etiketiyle uyuşur', () => {
    const p = payg()!
    // Etiketteki rakam JETON.kullandikcaOde.jetonFiyati ile aynı olmalı; ayrışırsa kullanıcı
    // fiyat sayfasında bir sayı, faturada başka bir sayı görür.
    const m = /₺\s*([\d.,]+)/.exec(p.priceLabel ?? '')
    expect(m, `fiyat etiketinde ₺ tutar yok: ${p.priceLabel}`).toBeTruthy()
    const etiket = Number(m![1].replace(/\./g, '').replace(',', '.'))
    expect(etiket, 'etiketteki birim fiyat JETON.kullandikcaOde.jetonFiyati ile ayrışmış').toBe(
      JETON.kullandikcaOde.jetonFiyati,
    )
  })
})

describe('2) aylık-ücret varsayan fiyat yolları yeni planı YANLIŞ göstermez', () => {
  // ⚠️ TEST TASARIMI DÜZELTİLDİ (aynı parti): ilk hâli kaynak metninde `monthly ?? 0` KALIBINI
  // arıyordu. Bu bir VEKİL ölçüydü ve yanlıştı — kalıp, aylık ücreti OLAN planlar için hâlâ
  // meşru şekilde duruyor; yanlış olan tek şey sıralamaydı. Vekil yerine ÜRETİLEN METİN sınanır.
  it('KRİTİK: hiçbir plan "₺0" fiyat göstermez (ne kartta ne ana sayfada)', () => {
    for (const p of PLANS) {
      for (const yillik of [false, true]) {
        const g = planFiyatGorunumu(p, yillik)
        const hepsi = `${g.buyuk} ${g.kucuk}`
        expect(hepsi, `${p.name} planı "₺0" gösteriyor: ${hepsi}`).not.toMatch(/₺0(?!\d)/)
      }
      expect(planKisaFiyat(p), `${p.name} ana sayfada "₺0" gösteriyor`).not.toMatch(/₺0(?!\d)/)
    }
  })

  it('KRİTİK: kullandıkça-öde planı JETON BAŞINA fiyatı gösterir, aylık tarife göstermez', () => {
    const p = payg()!
    const g = planFiyatGorunumu(p, true)
    expect(g.buyuk, 'büyük fiyat alanında jeton birim fiyatı yok').toMatch(/jeton/i)
    expect(
      `${g.buyuk} ${g.kucuk}`,
      'aylık ücreti olmayan plana "…/ay" tarifesi yazılmış',
    ).not.toMatch(/test sonrası/)
    expect(planKisaFiyat(p)).toBe(p.priceLabel)
  })

  it('KARŞIT-KANIT: aylık ücreti OLAN planlarda ücretsiz-dönem metni KORUNUR', () => {
    // Aşırı-genişleme koruması: kullandıkça-öde için açılan yol, Pro/Pro+’ın ücretsiz dönem
    // gösterimini bozmamalı (5. partide eklenen "rakam yerine durum" kuralı).
    const pro = PLANS.find((x) => x.tier === 'pro')!
    const g = planFiyatGorunumu(pro, true)
    expect(g.buyuk).toBe('Şu an ücretsiz')
    expect(g.kucuk, 'ücretsiz dönemde asıl tarife notu kayboldu').toMatch(/test sonrası ₺/)
  })
})

describe('3) 7. partide kaldırılan HIZ/KUYRUK vaadinin sayfa kalıntıları', () => {
  it('KRİTİK: fiyat sayfası "yoğun saatte bekleme / anında sonuç" iddiasında bulunmaz', () => {
    const s = soy(PRICING_SRC)
    expect(s).not.toMatch(/yoğun saatlerde.{0,30}bekleme/i)
    expect(s).not.toMatch(/sonuç anında gelir/i)
    expect(s).not.toMatch(/ne kadar hızlı sonuç vereceğini belirler/i)
  })

  it('KRİTİK: ana sayfa aynı hız vaadini tekrarlamaz', () => {
    expect(soy(HOME_SRC)).not.toMatch(/ne kadar hızlı sonuç vereceğini belirler/i)
  })

  it('KRİTİK: ödeme sayfası "Anında analiz" rozeti göstermez', () => {
    expect(soy(ODEME_SRC)).not.toMatch(/Anında analiz/i)
  })

  it('KRİTİK: plan açıklamaları "gerçek-zamanlı öncelik" satmaz', () => {
    const s = soy(CONFIG_SRC)
    // Yorumlar soyulduğu için bu yalnız GERÇEK metinleri (desc/features) tarar.
    expect(s).not.toMatch(/Gerçek-zamanlı öncelik/i)
  })
})

describe('4) karşılaştırma tablosu ÇİFT KAYNAK değildir', () => {
  it('KRİTİK: sütun başlıkları koda gömülmez, PLANS’ten türetilir', () => {
    const s = soy(PRICING_SRC)
    expect(
      /\[\s*'Başlangıç'\s*,\s*'Pro'\s*,\s*'Pro\+'\s*\]/.test(s),
      'tablo başlıkları hâlâ gömülü dizi → PLANS’e eklenen plan tabloda görünmez',
    ).toBe(false)
  })

  it('KRİTİK: her karşılaştırma satırı HER plan için değer verir', () => {
    const tierler = PLANS.map((p) => p.tier)
    for (const row of COMPARE) {
      for (const t of tierler) {
        expect(
          (row.values as Record<string, string>)[t],
          `"${row.label}" satırında ${t} planının değeri eksik`,
        ).toBeTruthy()
      }
    }
  })

  it('kart ızgarası plan sayısıyla uyumludur (4 plan 3 sütuna sıkışmaz)', () => {
    const s = soy(PRICING_SRC)
    const m = /lg:grid-cols-(\d)/.exec(s)
    expect(m, 'plan ızgarasında lg:grid-cols-N bulunamadı').toBeTruthy()
    expect(Number(m![1]), 'ızgara sütun sayısı plan sayısından az').toBeGreaterThanOrEqual(
      PLANS.length,
    )
  })
})

describe('5) kullanıcı "ne zaman ne kadar öderim" sorusunun cevabını bulur', () => {
  it('KRİTİK: SSS kullandıkça-öde modelini açıklar', () => {
    const madde = FAQ.find((f) => /kullandıkça öde/i.test(f.q))
    expect(madde, 'SSS’de kullandıkça-öde maddesi yok').toBeTruthy()
    const a = madde!.a.toLowerCase()
    // 'yapmazsanız' de geçerli bir karşılık — ilk kalıp gereksiz dardı (kendi test hatam).
    expect(a, 'hiç kullanmayınca ne olacağı yazılmamış').toMatch(/kullanmazsanız|kullanmadığınız|yapmazsanız/)
    expect(a, 'faturalamanın ne zaman olduğu yazılmamış').toMatch(/ay sonu|dönem sonu|fatura/)
  })

  it('KRİTİK: birikmiş kullanım SINIRI kullanıcıya söylenir (sürpriz fatura olmaz)', () => {
    const madde = FAQ.find((f) => /kullandıkça öde/i.test(f.q))!
    expect(
      new RegExp(String(JETON.kullandikcaOde.borcTavani)).test(madde.a),
      'borç tavanı SSS’de geçmiyor — kullanıcı sınırı bilmeden kullanır',
    ).toBe(true)
  })

  it('KRİTİK: SSS’deki birim fiyat, plan kartındaki fiyatla AYNI', () => {
    // Aynı sayı iki yerde yazılıysa biri güncellenip öteki unutulur (deponun 1 numaralı deseni).
    const madde = FAQ.find((f) => /kullandıkça öde/i.test(f.q))!
    const beklenen = JETON.kullandikcaOde.jetonFiyati.toFixed(2).replace('.', ',')
    expect(
      madde.a.includes(`₺${beklenen}`),
      `SSS’de birim fiyat ₺${beklenen} geçmiyor — kart ile SSS ayrışmış`,
    ).toBe(true)
  })

  it('KRİTİK: "Pro daha ucuz" eşiği HESAPLANAN başabaş noktasıyla tutarlı', () => {
    // Metinde "ayda N analizden fazlaysa Pro ucuz" deniyor. N, Pro aylık ücreti ÷ jeton birim
    // fiyatıdır; iki sayıdan biri değişince metin sessizce YANLIŞ olur. Ölç, iddia etme.
    const madde = FAQ.find((f) => /kullandıkça öde/i.test(f.q))!
    const pro = PLANS.find((p) => p.tier === 'pro')!
    const basabas = (pro.monthly ?? 0) / JETON.kullandikcaOde.jetonFiyati
    const m = /ayda (?:yaklaşık )?([\d.]+)[’']?[a-zçğıöşü]* fazla/i.exec(madde.a)
    expect(m, 'SSS’de başabaş eşiği ("ayda N … fazla") cümlesi yok').toBeTruthy()
    const yazan = Number(m![1].replace(/\./g, ''))
    expect(
      Math.abs(yazan - basabas),
      `SSS "${yazan}" diyor ama başabaş ${basabas.toFixed(1)} analiz (₺${pro.monthly} ÷ ₺${JETON.kullandikcaOde.jetonFiyati})`,
    ).toBeLessThanOrEqual(10)
  })
})

describe('6) ⚠️ SATIŞ HÂLÂ KAPALI (sahip: "henüz aktif etme")', () => {
  it('KRİTİK: FREE_MODE açık — jeton altyapısı eklenmesi ücretsiz dönemi KAPATMADI', () => {
    expect(FREE_MODE, 'ücretsiz dönem kapanmış (sahip kararı: şu an aktif kalacak)').toBe(true)
  })

  it('KRİTİK: fiyat sayfası ücretsiz dönemde "ödeme alınmaz" der', () => {
    expect(soy(PRICING_SRC)).toMatch(/kart bilgisi istenmez, ödeme alınmaz/i)
  })
})
