// Author: mertaygn, cglrgrkn
/**
 * "BUGÜN TAHSİL EDİLECEK" TUTARI, PLANIN GERÇEK DÖNEM BEDELİ OLMALI (denetim 2026-08-18).
 *
 * `Odeme.tsx` yıllık+Araştırma seçiminde `RESEARCH_ADDON.monthly` değerini 12 ile çarpıyordu →
 * ekranda ₺14.580 yazarken `IYZICO_SETUP.md` plan tablosuna göre iyzico ₺13.800 tahsil edecekti
 * (₺780 fark). Sayı artık `RESEARCH_ADDON.yearly` tek kaynağından geliyor; tutarların KENDİSİ
 * `src/lib/__tests__/download.test.ts` içinde kilitli. Bu dosya SAYFANIN o kaynağı gerçekten
 * kullandığını kilitler — aksi halde config doğru, ekran yanlış kalırdı.
 *
 * ⚠️ TEST BİÇİMİ: bu depoda DOM/jsdom ortamı YOK (bkz. auth-modal-focus.test.ts gerekçesi) →
 * bileşeni render edip ekrandaki tutarı okuyamayız. Ölçülen şey `chargeNow` İFADESİDİR.
 * ⚠️ YORUMLAR SOYULUR: düzeltmenin kendi gerekçesi eski çarpımı aynen anlatıyor; soyulmazsa
 * kapı kendi açıklamasını görüp yanlış-KIRMIZI verir (bu depo aynı tuzağa dört kez düştü).
 */
import { describe, expect, it } from 'vitest'
import SRC from '../Odeme.tsx?raw'

/** `chargeNow` atamasının ifadesi, blok ve satır yorumları SOYULMUŞ. */
function chargeNowIfadesi(): string {
  const yorumsuz = SRC.replace(/\/\*[\s\S]*?\*\//g, ' ')
    .split('\n')
    .filter((l) => !l.trim().startsWith('//'))
    .join('\n')
  const bas = yorumsuz.indexOf('const chargeNow')
  expect(bas, 'chargeNow ataması bulunamadı — test güncellenmeli').toBeGreaterThan(-1)
  return yorumsuz.slice(bas, yorumsuz.indexOf('\n  const periodLabel', bas))
}

describe('Odeme sayfası dönem bedeli', () => {
  it('KRİTİK: yıllık Araştırma bedeli TEK KAYNAKTAN (RESEARCH_ADDON.yearly) gelir', () => {
    expect(chargeNowIfadesi()).toContain('RESEARCH_ADDON.yearly')
  })

  it('KRİTİK: eklenti 12 ayla çarpılmaz ("2 ay bedava" atlanmasın)', () => {
    expect(chargeNowIfadesi()).not.toMatch(/RESEARCH_ADDON\.monthly\s*\*\s*12/)
  })

  it('KARŞIT-KANIT: planın kendi yıllık bedeli hâlâ toplanıyor (eklenti tek başına kalmasın)', () => {
    expect(chargeNowIfadesi()).toContain('plan?.yearly')
  })

  it('KARŞIT-KANIT: AYLIK yolda hâlâ aylık eklenti kullanılıyor', () => {
    expect(chargeNowIfadesi()).toContain('total')
    expect(SRC).toContain('RESEARCH_ADDON.monthly')
  })
})
