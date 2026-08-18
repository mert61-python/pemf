// Author: mertaygn, cglrgrkn
/**
 * Ödeme katmanı — bu denetimde düzeltilen davranışlar (gerçek para).
 *
 *   #31/#37 `origin` İSTEMCİDEN geliyordu ve doğrulanmadan iyzico callbackUrl'ine yazılıyordu
 *           (açık yönlendirme / ödeme geri-dönüş kaçırma). Artık izin listesi.
 *   #107    Bilinmeyen iyzico durumu KOŞULSUZ 'canceled'a düşüyordu → beklenmedik/geçici bir
 *           statüde abonelik sessizce "iptal edilmiş" kaydediliyordu.
 *           ⚠️ 2026-08-18: bu maddenin eski metni "hakkı sessizce iptal ediliyordu" diyordu;
 *           ölçüldü, hak açısından FARK YOK — hakkı okuyan iki katman da `past_due`yu `canceled`
 *           gibi PASİF sayıyor (bkz. util.ts'teki gerekçe). Kazanç: `past_due` satırı CANLI
 *           sayıldığı için abonelik iptal edilebilir kalır ve ikinci abonelik açılmaz.
 *   #104    IYZICO_URI yoksa sessizce SANDBOX'a düşülüyordu → üretimde tahsilat YAPILMADAN
 *           abonelik aktifleşir. Artık fail-closed.
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { isAllowedOrigin, mapIyzicoStatus } from '../util.js'

const OLD = { ...process.env }
beforeEach(() => {
  process.env.PUBLIC_SITE_URL = 'https://pemf-vet-web.vercel.app'
  delete process.env.EXTRA_ALLOWED_ORIGINS
})
afterEach(() => { process.env = { ...OLD } })

describe('isAllowedOrigin — ödeme geri-dönüş adresi istemciye bırakılamaz', () => {
  it('yapılandırılmış site adresini kabul eder', () => {
    expect(isAllowedOrigin('https://pemf-vet-web.vercel.app')).toBe(true)
  })

  it('KRİTİK: rastgele bir host REDDEDİLİR (açık yönlendirme)', () => {
    expect(isAllowedOrigin('https://evil.example.com')).toBe(false)
    expect(isAllowedOrigin('https://pemf-vet-web.vercel.app.evil.com')).toBe(false)
  })

  it('http (TLS yok) REDDEDİLİR — ödeme dönüşü şifresiz taşınmaz', () => {
    expect(isAllowedOrigin('http://pemf-vet-web.vercel.app')).toBe(false)
  })

  it('Vercel önizleme dağıtımlarına izin verir (PR deploy akışı kırılmasın)', () => {
    expect(isAllowedOrigin('https://pemf-vet-web-git-abc.vercel.app')).toBe(true)
  })

  it('EXTRA_ALLOWED_ORIGINS ile özel alan adı eklenebilir', () => {
    process.env.EXTRA_ALLOWED_ORIGINS = 'https://v-pemf.com, https://www.v-pemf.com'
    expect(isAllowedOrigin('https://v-pemf.com')).toBe(true)
    expect(isAllowedOrigin('https://baska.com')).toBe(false)
  })

  it('bozuk/boş girdi çökmeden reddedilir', () => {
    for (const bad of ['', 'javascript:alert(1)', 'değil-url', null, undefined, 42, {}]) {
      expect(isAllowedOrigin(bad as unknown)).toBe(false)
    }
  })
})

describe('mapIyzicoStatus — bilinmeyen durum hakkı SESSİZCE iptal etmez', () => {
  it('bilinen durumlar doğru eşlenir', () => {
    expect(mapIyzicoStatus('ACTIVE')).toBe('active')
    expect(mapIyzicoStatus('PENDING')).toBe('trialing')
    expect(mapIyzicoStatus('UNPAID')).toBe('past_due')
    expect(mapIyzicoStatus('CANCELED')).toBe('canceled')
    expect(mapIyzicoStatus('EXPIRED')).toBe('canceled')
    expect(mapIyzicoStatus('UPGRADED')).toBe('canceled')
  })

  it('KRİTİK: BİLİNMEYEN durum "canceled" DEĞİL "past_due" (ödeyen kullanıcı erişimini kaybetmesin)', () => {
    expect(mapIyzicoStatus('RETRY')).toBe('past_due')
    expect(mapIyzicoStatus('')).toBe('past_due')
    expect(mapIyzicoStatus('bilinmeyen-yeni-statu')).toBe('past_due')
  })

  it('büyük/küçük harf duyarsız', () => {
    expect(mapIyzicoStatus('active')).toBe('active')
  })
})

describe('iyzico endpoint — fail-closed (sessizce sandbox YOK)', () => {
  it('KRİTİK: IYZICO_URI yoksa istemci kurulmaz (tahsilatsız abonelik riski)', async () => {
    delete process.env.IYZICO_URI
    delete process.env.IYZICO_ALLOW_SANDBOX
    process.env.IYZICO_API_KEY = 'k'
    process.env.IYZICO_SECRET_KEY = 's'
    const { iyzico } = await import('../iyzico.js')
    expect(() => iyzico()).toThrow(/IYZICO_URI/)
  })
})
