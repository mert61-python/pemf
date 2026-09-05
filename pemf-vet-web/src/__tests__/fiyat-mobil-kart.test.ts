// Author: mertaygn, cglrgrkn
/**
 * FİYAT KARŞILAŞTIRMASI — MOBİL SATIR KARTI  [2026-09-05, responsive denetimi kalanı]
 * ==================================================================================
 * ÖLÇÜLEN DURUM (headless Edge + CDP, `scripts/responsive_kapisi.py` altyapısı):
 *
 *   görünüm    kap(px)  gizli(px)  kaydırmasız görünen sütun
 *   320×568      280       280       2 / 5
 *   390×844      350       210       3 / 5
 *   768×1024     720         0       5 / 5
 *
 * Yani 320 px telefonda tablonun YARISI gizliydi ve satır etiketi YAPIŞKAN OLMADIĞI için
 * kullanıcı sağa kaydırdığında hangi satıra baktığını da kaybediyordu. Sayfanın kendisi yatay
 * kaymadığı (`overflow-x-auto` kabı) için responsive kapısı bunu bulgu OLARAK GÖREMİYORDU —
 * bu bir kapı bulgusu değil, sahip kararıyla kapatılan bir kullanılabilirlik borcuydu.
 *
 * SEÇİLEN TASARIM — SATIR kartı (plan kartı DEĞİL):
 * Plan başına kartta karşılaştırma ekseni TAMAMEN kaybolur; kullanıcı iki planın aynı satırını
 * yan yana tutamaz, oysa bu sayfaya geliş sebebi tam olarak budur. Satır kartında eksen kartın
 * İÇİNDE kalır ve aynı değeri veren planlar tek satırda birleşir (fark katlaması).
 *
 * ⚠️ DOM YOK: bu depoda jsdom yok → ölçülen şey KAYNAKTIR. Görsel/piksel doğrulama
 * `scripts/responsive_kapisi.py --hedef site --durum pricing` ile yapıldı (8 ölçüm, 0 bulgu;
 * kart bloğunu hedefleyen CSS mutasyonu kapıyı KIRMIZI yaptı → kapı bu bloğu gerçekten ölçüyor).
 * ⚠️ Yorumlar SOYULUR: bu dosyanın kendi açıklaması eski hatalı yapıyı anlatıyor.
 */
import { describe, expect, it } from 'vitest'

import { kaynakSoy } from './_soyucu'

import { COMPARE, PLANS } from '../config'
import PRICING_SRC from '../pages/Pricing.tsx?raw'

const src = kaynakSoy(PRICING_SRC)

/** Kart bloğu ile tablo bloğunu ayır (ikisi de aynı bölümde). */
function kartBlogu(): string {
  const i = src.indexOf('lg:hidden')
  const j = src.indexOf('hidden overflow-x-auto lg:block')
  expect(i, 'kart bloğu (lg:hidden) bulunamadı').toBeGreaterThan(-1)
  expect(j, 'tablo sarmalayıcısı (hidden … lg:block) bulunamadı').toBeGreaterThan(i)
  return src.slice(i, j)
}

describe('görünüm anahtarı', () => {
  it('KRİTİK: 1024 altında kart, üstünde tablo — ikisi aynı anda çizilmez', () => {
    expect(src).toContain('lg:hidden')
    expect(src).toContain('hidden overflow-x-auto lg:block')
  })

  it('KRİTİK: gizleme display:none ile — sr-only/opacity-0 gizli varyantı a11y ağacında bırakır', () => {
    const blok = kartBlogu()
    expect(blok).not.toContain('sr-only')
    expect(blok).not.toContain('opacity-0')
    expect(blok).not.toMatch(/-left-\[\d+px\]/)
  })

  it('tablo yatay kaydırma kabını KORUR (sayfa gövdesi yatay kaymasın)', () => {
    // `overflow-x-auto` + `min-w-[560px]` birlikte kalmalı: kap silinirse 1024-1100 px arası
    // dar masaüstü pencerede sayfanın KENDİSİ yatay kayar.
    expect(src).toContain('overflow-x-auto')
    expect(src).toContain('min-w-[560px]')
  })
})

describe('tek kaynak', () => {
  it('KRİTİK: kart bloğu PLANS ve COMPARE üzerinden türer, dizi GÖMMEZ', () => {
    const blok = kartBlogu()
    expect(blok).toMatch(/COMPARE\.filter/)
    expect(blok).toMatch(/degerGruplari\(/)
    // Plan adları elle yazılmamalı.
    for (const p of PLANS) {
      expect(blok, `plan adı "${p.name}" karta GÖMÜLMÜŞ`).not.toContain(`'${p.name}'`)
    }
  })

  it('KRİTİK: kart bloğu `lg:grid-cols-*` KULLANMAZ', () => {
    // kullandikca-ode.test.ts dosyadaki İLK `lg:grid-cols-(\d)` eşleşmesini okur ve o çıpa
    // plan ızgarasına pinlidir; kart bloğuna küçük sayılı bir ızgara yazmak onu çalar.
    expect(kartBlogu()).not.toMatch(/lg:grid-cols-/)
  })

  it('gruplama tüm planları kapsar (hiçbir plan kartta düşmez)', () => {
    // degerGruplari PLANS üzerinde döner → grup sayıları toplamı daima plan sayısıdır.
    for (const row of COMPARE) {
      const gruplar = new Map<string, number>()
      for (const p of PLANS) {
        const v = row.values[p.tier]
        gruplar.set(v, (gruplar.get(v) ?? 0) + 1)
      }
      const toplam = [...gruplar.values()].reduce((a, b) => a + b, 0)
      expect(toplam, `"${row.label}" satırında plan kaybı`).toBe(PLANS.length)
    }
  })
})

describe('değer sözlüğü — bağlam kaybı', () => {
  it('KRİTİK: COMPARE hiçbir hücrede ÇIPLAK "—" kullanmaz', () => {
    // Tabloda sütun başlığı bağlam veriyordu ve aynı glif İKİ ZIT anlam taşıyordu:
    // "Jeton başına ücret: —" = ücret ALINMIYOR (avantaj) · "Araştırma profili: —" = YOK (eksiklik).
    // Kartta sütun yok → glif tek başına anlamsız.
    const ihlal: string[] = []
    for (const row of COMPARE) {
      for (const p of PLANS) {
        if (row.values[p.tier].trim() === '—') ihlal.push(`${row.label}/${p.tier}`)
      }
    }
    expect(ihlal, 'çıplak "—" bağlamsız okunduğunda anlamsız').toEqual([])
  })

  it('KRİTİK: sözlük iki sözcüklü — "Alınmıyor" (avantaj) ve "Yok" (eksiklik) ayrı', () => {
    const tum = COMPARE.flatMap((r) => PLANS.map((p) => r.values[p.tier]))
    expect(tum, 'ücret alınmadığını söyleyen değer yok').toContain('Alınmıyor')
    expect(tum.some((v) => v === 'Yok'), 'eksikliği söyleyen değer yok').toBe(true)
  })

  it('KRİTİK: valans ETİKETTEN TAHMİN EDİLMEZ (kod /ücret/i sezgiseli kullanmaz)', () => {
    // Sezgisel, config değiştiğinde sessizce yanlış renk üretir; anlam VERİDE olmalı.
    expect(src).not.toMatch(/\/ücret\/i/)
  })

  it('"✓ (…)" parantezli açıklaması kartta KORUNUR (5 jeton/seans bilgisi tek yerde)', () => {
    const aiPro = COMPARE.find((r) => /AI Pro/i.test(r.label))
    expect(aiPro).toBeTruthy()
    expect(Object.values(aiPro!.values).join(' ')).toMatch(/5 jeton/)
    // Deger bileşeni '✓' sonrasını olduğu gibi basar, boşsa 'Var' yazar.
    expect(src).toContain("v.slice(1).trim()")
    expect(src).toMatch(/ek \|\| 'Var'/)
  })
})

describe('erişilebilirlik', () => {
  it('KRİTİK: masaüstü tablosunda satır etiketi başlıktır (scope="row")', () => {
    // Yoksa ekran okuyucu "₺990"un hangi satıra ait olduğunu söyleyemez.
    expect(src).toContain('scope="row"')
    expect(src).toContain('scope="col"')
    expect(src).toContain('aria-labelledby="plan-karsilastirmasi"')
  })

  it('kart bloğunda etkileşimli öge YOK (44 px dokunma kapısında yeni hedef doğmaz)', () => {
    const blok = kartBlogu()
    expect(blok).not.toMatch(/<button/)
    expect(blok).not.toMatch(/<summary/)
    expect(blok).not.toMatch(/onClick=/)
    expect(blok).not.toMatch(/<Link\b/)
  })

  it('Pro+ vurgusu YALNIZ renkle taşınmaz — plan adı metinde yazılı', () => {
    const blok = kartBlogu()
    expect(blok).toMatch(/\{p\.name\}/)
  })
})

describe('sayı gömülmez', () => {
  it('KRİTİK: ortak satır kartı plan SAYISINI metne yazmaz ("dört planda da")', () => {
    // PLANS büyüyünce elle yazılmış sayı YALAN olurdu.
    expect(src).not.toMatch(/[Dd]ört planda/)
    expect(src).toContain('Tüm planlarda var')
  })
})
