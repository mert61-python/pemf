// Author: mertaygn, cglrgrkn
/**
 * SİTE RESPONSIVE SÖZLEŞMESİ  [W, 2026-09-04 responsive denetimi]
 * ===============================================================
 * ÖLÇÜLEN DURUM (headless Edge + CDP, `scripts/responsive_kapisi.py`):
 *  · 320 px telefonda `document.scrollWidth` 391 > 320 — SAYFA YATAY KAYIYORDU. Kök neden:
 *    ızgara öğesinin otomatik minimum genişliği (min-content) parçayı şişiriyordu (`ampirik-1`).
 *  · 768-1023 px tablette üst şeritteki bağlantılar + "PEMF Vet'i İndir" aynı satıra sığmıyor,
 *    CTA iki satıra kırılıyordu (`site-1`).
 *  · Altbilgi ve destek sayfasındaki yasal bağlantıların dokunma alanı 120-276 × 20 px'ti;
 *    erişilebilirlik tabanı 44 px (`site-16`, 100 ölçüm bulgusu).
 *  · `dark:` varyantı bu projede HİÇ TANIMLI DEĞİL (tek koyu tema) → o sınıflar ÖLÜYDÜ ve
 *    açık-tema rengi (`text-red-600`) koyu zeminde okunmuyordu (`site-6`).
 *  · iOS Safari 16 px'in altındaki input'a odaklanınca sayfayı yakınlaştırıp geri çıkmıyordu
 *    (`site-3`).
 *
 * ⚠️ DOM YOK: bu depoda jsdom ortamı yok → ölçülen şey KAYNAĞIN kendisidir. Görsel doğrulama
 * `scripts/responsive_kapisi.py --hedef site` ile yapılır (40 ölçüm, 0 bulgu).
 * ⚠️ Yorumlar SOYULUR: bu dosyanın kendi açıklaması eski hatalı sınıfları anlatıyor.
 * ⚠️ CSS İDDİALARI BURADA DEĞİL: `index.css` bu vitest kurulumunda hiçbir sorgu ekiyle
 *    (?raw / ?inline / import.meta.glob) okunamıyor — Vite CSS eklentisi araya giriyor ve
 *    içerik BOŞ geliyor (ölçüldü). node:fs de kullanılamaz: tsconfig.app.json testleri de
 *    tip denetiminden geçiriyor ve node tipleri yok (`npx tsc -b` kırmızı olurdu, ölçüldü).
 *    CSS sözleşmesi: guii/tests/test_site_responsive_css.py
 */
import { describe, expect, it } from 'vitest'

import { kaynakSoy } from './_soyucu'

import ACCOUNT_SRC from '../components/AccountButton.tsx?raw'
import AUTHMODAL_SRC from '../context/AuthModal.tsx?raw'
import DOWNLOAD_SRC from '../pages/Download.tsx?raw'
import FEATURES_SRC from '../pages/Features.tsx?raw'
import FOOTER_SRC from '../components/Footer.tsx?raw'
import HEADER_SRC from '../components/Header.tsx?raw'
import HOME_SRC from '../pages/Home.tsx?raw'
import PACKAGE_SRC from '../components/PackageBuilder.tsx?raw'
import ODEME_SRC from '../pages/Odeme.tsx?raw'
import PRICING_SRC from '../pages/Pricing.tsx?raw'
import RESET_SRC from '../pages/ResetPassword.tsx?raw'

const TSX = {
  AccountButton: ACCOUNT_SRC,
  AuthModal: AUTHMODAL_SRC,
  Download: DOWNLOAD_SRC,
  Features: FEATURES_SRC,
  Footer: FOOTER_SRC,
  Header: HEADER_SRC,
  Home: HOME_SRC,
  Odeme: ODEME_SRC,
  PackageBuilder: PACKAGE_SRC,
  Pricing: PRICING_SRC,
  ResetPassword: RESET_SRC,
}

describe('yatay taşma', () => {
  it('KRİTİK: hero ızgara öğesi min-w-0 taşır (320 px sayfa yatay kaymaz)', () => {
    for (const [ad, src] of [
      ['Home', HOME_SRC],
      ['Features', FEATURES_SRC],
    ] as const) {
      expect(kaynakSoy(src), `${ad}: ızgara öğesi min-w-0 taşımıyor`).toContain('min-w-0 lg:pl-6')
    }
  })
})

describe('üst şerit kırılımı', () => {
  const header = kaynakSoy(HEADER_SRC)

  it('KRİTİK: masaüstü navigasyonu lg kırılımında (768-1023 tablette hamburger)', () => {
    expect(header).toContain('lg:flex')
    expect(header).not.toContain('md:flex')
    expect(header).toContain('lg:hidden')
  })

  it('indirme düğmesi satıra kırılmaz', () => {
    expect(header).toContain('whitespace-nowrap')
  })

  it('mobil çekmece kısa ekranda kaydırılabilir', () => {
    expect(header).toContain('overflow-y-auto')
  })
})

describe('dokunma hedefleri', () => {
  it('KRİTİK: altbilgi bağlantıları 44 px tabanını .tap ile alır', () => {
    const footer = kaynakSoy(FOOTER_SRC)
    const baglantilar = footer.match(/<Link[^>]*className="[^"]*"/g) ?? []
    expect(baglantilar.length).toBeGreaterThan(0)
    for (const b of baglantilar) {
      expect(b, `altbilgi bağlantısı .tap taşımıyor: ${b}`).toContain('tap')
    }
  })

})

describe('tek koyu tema', () => {
  it('KRİTİK: `dark:` varyantı hiçbir kaynakta kullanılmaz (tanımlı değil → ölü sınıf)', () => {
    const ihlal: string[] = []
    for (const [ad, src] of Object.entries(TSX)) {
      if (/\bdark:/.test(kaynakSoy(src))) ihlal.push(ad)
    }
    expect(ihlal, `\`dark:\` varyantı tanımlı değil; token kullanın (text-warning/success/danger)`).toEqual([])
  })

})

describe('giriş/kayıt penceresi', () => {
  const modal = kaynakSoy(AUTHMODAL_SRC)

  it('KRİTİK: yükseklik svh ile sınırlı ve perde kaydırılabilir', () => {
    expect(modal).toContain('100svh')
    expect(modal).toContain('overflow-y-auto')
    // 90vh iOS'ta araç çubuğu yüzünden ekrandan taşıyordu.
    expect(modal).not.toContain('max-h-[90vh]')
  })
})

describe('geniş ekran ve akış', () => {
  it('KRİTİK: 1536 üstünde kapsayıcı genişler (2560 pikselde 704 px ölü kenar vardı)', () => {
    // ÖLÇÜLDÜ: max-w-6xl → 2560 px'te kap 1152 px, iki yanda 704 px boşluk.
    // 2xl:max-w-7xl ile kap 1280 px, boşluk 640 px.
    for (const [ad, src] of [
      ['Home', HOME_SRC],
      ['Features', FEATURES_SRC],
      ['Pricing', PRICING_SRC],
      ['Header', HEADER_SRC],
      ['Footer', FOOTER_SRC],
    ] as const) {
      const kaynak = kaynakSoy(src)
      const toplam = (kaynak.match(/max-w-6xl/g) ?? []).length
      const genis = (kaynak.match(/max-w-6xl 2xl:max-w-7xl/g) ?? []).length
      expect(genis, `${ad}: ${toplam - genis} kapsayıcı 2xl varyantı almamış`).toBe(toplam)
    }
  })

  it('KRİTİK: "Önerilen" rozeti AKIŞTA (mutlak konumda başlığın üstüne biniyordu)', () => {
    // ÖLÇÜLDÜ 320 px: rozet 224-283, başlık 81-244 → 20 px yatay çakışma.
    const paket = kaynakSoy(PACKAGE_SRC)
    expect(paket).not.toMatch(/absolute right-4 top-4/)
    expect(paket, 'başlık daralabilmeli, rozet daralmamalı').toMatch(/min-w-0 flex-1 text-lg font-bold/)
    expect(paket).toMatch(/shrink-0 rounded-full bg-primary\/15/)
  })

  it('hesap menüsü 320 px görünüm alanını AŞMAZ ve çekmecede akışa girer', () => {
    // ÖLÇÜLDÜ: sabit w-72 (288 px) + absolute right-0 → 320 px'te taşıyordu.
    const hesap = kaynakSoy(ACCOUNT_SRC)
    expect(hesap).toContain('max-w-[calc(100vw-2.5rem)]')
    expect(hesap).toMatch(/inline \? 'static w-full'/)
    expect(kaynakSoy(HEADER_SRC), 'çekmecedeki menü inline değil').toMatch(/AccountButton[\s\S]{0,80}?inline/)
  })
})

describe('dokunma hedefi kalanları', () => {
  it('KRİTİK: fiyat dönemi düğmeleri 44 px tabanını alır (32 px ölçülmüştü)', () => {
    const fiyat = kaynakSoy(PRICING_SRC)
    const pill = fiyat.match(/rounded-full px-4 font-medium transition-colors/g) ?? []
    expect(pill.length, 'Aylık/Yıllık düğmeleri bulunamadı').toBe(2)
    expect(fiyat).toMatch(/min-h-11 items-center justify-center rounded-full px-4/)
  })

  it('KRİTİK: "Çıkınca haber ver" 44 px tabanını alır (222×16 px ölçülmüştü)', () => {
    // ⚠️ Kapı bunu WCAG 2.5.8 ARALIK muafiyetiyle geçiriyor (komşu hedef yok) —
    // yani kapı yeşilken de bu hedef parmakla ıskalanıyordu. Kapı tabanı ≠ kullanılabilirlik.
    const indir = kaynakSoy(DOWNLOAD_SRC)
    const i = indir.indexOf('Çıkınca haber ver')
    expect(i).toBeGreaterThan(-1)
    expect(indir.slice(Math.max(0, i - 400), i)).toMatch(/className="tap /)
  })

  it('KRİTİK: altbilgi 400 px altında TEK sütuna iner', () => {
    // ÖLÇÜLDÜ 320 px: iki sütun × 120 px → "İptal, İade ve Cayma Hakkı" üç satıra sarıyordu.
    const alt = kaynakSoy(FOOTER_SRC)
    expect(alt).toMatch(/grid-cols-1/)
    expect(alt).toMatch(/min-\[400px\]:grid-cols-2/)
  })
})
