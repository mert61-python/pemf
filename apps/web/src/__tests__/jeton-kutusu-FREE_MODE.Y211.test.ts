// Author: mertaygn, cglrgrkn
/**
 * Y211 · S-D67.4 (sahip, 2026-10-28) — ücretsiz dönemde (FREE_MODE) hesap menüsünde "Kalan jeton" kutusu GÖRÜNMEZ.
 *
 * ÖLÇÜLEN (D6.29, HEAD 8b002fc0): Y194 jetonu cihazda KOD düzeyinde kapattı; site hesap menüsü ise okunabilen bakiyeyi
 * "Kalan jeton N" diye göstermeye devam ediyordu (kullanıcı harcanmayan bir sayıyı "hak" sanır). Artık FREE_MODE'da bakiye
 * hiç OKUNMAZ (gereksiz istek yok) ve kutu çizilmez; ticari açılışta (FREE_MODE=false) ikisi de geri gelir.
 * ÖLÇÜT kaynak düzeyinde (sitenin vitest ortamında DOM / efekt çalıştırıcı yok — kutu menü açılıp asenkron okuma bitince çizilir;
 * `renderToString` efekt koşmaz). Yorumlar soyulur (string-bilinçli soyucu) — koşul yorumda kalırsa kapı KIRMIZI.
 */
import { describe, expect, it } from 'vitest'
import { kaynakSoy } from './_soyucu'
import ACCOUNT_SRC from '../components/AccountButton.tsx?raw'

const kod = kaynakSoy(ACCOUNT_SRC)

describe('Y211 · S-D67.4 — Kalan jeton kutusu FREE_MODE kapısında', () => {
  it('KRİTİK: bakiye okuması FREE_MODE iken HİÇ yapılmaz', () => {
    const efekt = kod.match(/useEffect\(\(\) => \{([^}]*?)void jetonBakiyesiniOku\(\)/)
    expect(efekt, 'aparat: jeton okuma efekti bulunamadı').not.toBeNull()
    expect(efekt![1]).toMatch(/if \(!acik \|\| FREE_MODE\) return/)
  })

  it('KRİTİK: "Kalan jeton" kutusu FREE_MODE iken çizilmez (koşul kutunun KENDİSİNDE)', () => {
    const i = kod.indexOf("t('hesap.kalanJeton')")
    expect(i, 'aparat: kalanJeton çizimi bulunamadı').toBeGreaterThan(0)
    const kosul = kod.lastIndexOf('{jeton', i)
    expect(kosul, 'aparat: kutunun koşulu bulunamadı').toBeGreaterThan(0)
    expect(kod.slice(kosul, kod.indexOf('(', kosul) + 1)).toBe('{jeton && !FREE_MODE && (')
  })

  it('KARŞIT: ücretsiz dönem notu (abonelik.testAsamasi) FREE_MODE dalında AYNEN', () => {
    expect(kod).toMatch(/\{FREE_MODE\s*\?\s*t\('hesap\.abonelik\.testAsamasi'\)/)
  })
})
