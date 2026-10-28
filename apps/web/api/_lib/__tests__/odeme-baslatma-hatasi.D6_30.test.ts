// Author: mertaygn, cglrgrkn
/**
 * D6.30 (B-7.5) — ödeme sayfası sunucunun 409 ve ALAN-ÖZEL iletilerini genel "tekrar deneyin"e ÇEVİRMEZ.
 *
 * 🔴 ÖLÇÜLEN (HEAD ebf1c3fe): `src/pages/Odeme.tsx:81` her hatayı `odemeHatasiTurkce(error)`a sokuyordu; o sınıflandırıcı yalnız
 * yetersiz bakiye / 3D / abonelik-yok desenlerini tanır, gerisi `hesap.hata.islemTamamlanamadi` ("İşlem tamamlanamadı. Lütfen tekrar
 * deneyin …"). Sonuç: `api/checkout.ts` 409 "Hesabınızda zaten aktif bir abonelik var … önce mevcut aboneliğinizi iptal edin" ve 400
 * "Lütfen \"TC Kimlik No\" alanını doldurun" / "TC Kimlik No 11 haneli olmalıdır" iletileri ekranda "tekrar deneyin" oluyordu —
 * kullanıcı önce iptal etmesi gerektiğini ya da HANGİ kutuyu düzelteceğini bilemiyordu (07 §B-7.5).
 *
 * ÖLÇÜT (sahte YALNIZ ağ kenarında): Supabase uçları (`auth/v1/user`, `rest/v1/subscriptions`) ve iyzico modülü sahte; `/api/checkout`
 * isteği GERÇEK `api/checkout.ts` handler'ına yönlenir; GERÇEK `initCheckout()` + GERÇEK `odemeBaslatmaHatasi()` (ekranın çağırdığı) +
 * GERÇEK i18n (TR ve bayrak açık EN). Ham sunucu metni İngilizce ekrana SIZMAZ.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const depo = new Map<string, string>()
vi.stubGlobal('localStorage', {
  getItem: (k: string) => (depo.has(k) ? depo.get(k)! : null),
  setItem: (k: string, v: string) => void depo.set(k, String(v)),
  removeItem: (k: string) => void depo.delete(k),
})
vi.stubGlobal('document', { documentElement: { lang: '' }, title: '', querySelector: () => null })
vi.stubGlobal('window', { location: { origin: 'https://pemf-vet-web.vercel.app' } })

vi.mock('../../../src/lib/supabase', () => ({
  supabase: { auth: { getSession: async () => ({ data: { session: { access_token: 'jwt-kullanici' } } }) } },
}))
vi.mock('../iyzico.js', () => ({
  planRef: vi.fn().mockReturnValue('plan-ref'),
  subInitialize: vi.fn().mockResolvedValue({ status: 'failure', errorCode: '10051', errorMessage: 'Kart limiti yetersiz' }),
}))

const i18nMod = await import('../../../src/i18n')
const dilMod = await import('../../../src/i18n/dil')
const { default: handler } = await import('../../checkout.js')
const { initCheckout } = await import('../../../src/lib/checkout')
const { odemeBaslatmaHatasi } = await import('../../../src/lib/authHatalari')
const { COMPANY } = await import('../../../src/config')
const trHesap = (await import('../../../src/i18n/tr/hesap.json')).default
const enHesap = (await import('../../../src/i18n/en/hesap.json')).default
const trOdeme = (await import('../../../src/i18n/tr/odeme.json')).default
const enOdeme = (await import('../../../src/i18n/en/odeme.json')).default

const TR_HARF = /[çğıöşüÇĞİÖŞÜ]/
const OLD = { ...process.env }
const durum: { abonelikRef: string | null; sonApi: { kod: number; govde: Record<string, unknown> } | null } = { abonelikRef: null, sonApi: null }

async function gercekHandlerdan(govde: string): Promise<Response> {
  let kod = 0
  let cikti: Record<string, unknown> = {}
  const res = {
    status(k: number) { kod = k; return res },
    json(g: Record<string, unknown>) { cikti = g; return res },
  }
  await handler({ method: 'POST', headers: {}, body: JSON.parse(govde) } as never, res as never)
  durum.sonApi = { kod, govde: cikti }
  return new Response(JSON.stringify(cikti), { status: kod, headers: { 'Content-Type': 'application/json' } })
}

const TAM = { name: 'Ayşe', surname: 'Kaya', identityNumber: '12345678901', gsmNumber: '+905551112233', city: 'Ankara', address: 'Çankaya', zipCode: '' }

/** Ekranın yaptığının AYNISI: initCheckout → hata varsa odemeBaslatmaHatasi. */
async function ekranMetni(musteri: Record<string, string>): Promise<string> {
  const { content, error, kod, alan, sebep } = await initCheckout({ tier: 'pro', yearly: false, research: false, customer: musteri as never })
  expect(content, 'ödeme beklenmedik biçimde başladı').toBeUndefined()
  expect(error, 'hata dönmedi').toBeTruthy()
  return odemeBaslatmaHatasi({ error, kod, alan, sebep })
}

beforeEach(async () => {
  process.env.SUPABASE_URL = 'https://proje.supabase.co'
  process.env.SUPABASE_ANON_KEY = 'anon-anahtar-testte'
  process.env.SUPABASE_SERVICE_ROLE_KEY = 'servis-anahtari-testte'
  process.env.PUBLIC_SITE_URL = 'https://pemf-vet-web.vercel.app'
  durum.abonelikRef = null
  durum.sonApi = null
  vi.spyOn(console, 'error').mockImplementation(() => {})
  vi.stubGlobal('fetch', async (girdi: unknown, init?: { body?: string }) => {
    const url = String(girdi)
    if (url === 'https://proje.supabase.co/auth/v1/user') return new Response(JSON.stringify({ id: 'u-1', email: 'v@k.tr' }), { status: 200 })
    if (url.startsWith('https://proje.supabase.co/rest/v1/subscriptions?')) {
      return new Response(JSON.stringify(durum.abonelikRef ? [{ stripe_subscription_id: durum.abonelikRef }] : []), { status: 200 })
    }
    if (url === '/api/checkout') return gercekHandlerdan(init?.body ?? '{}')
    throw new Error(`beklenmeyen ağ isteği: ${url}`)
  })
})
afterEach(async () => {
  vi.restoreAllMocks()
  process.env = { ...OLD }
  dilMod.__bayrakTestiAyarla(null)
  await i18nMod.dilSec('tr')
})

async function dil(d: 'tr' | 'en') {
  dilMod.__bayrakTestiAyarla(d === 'en')
  await i18nMod.dilSec(d)
}

const GENEL_TR = trHesap.hata.islemTamamlanamadi.replace('{{email}}', COMPANY.email)

describe('D6.30 · 409 zaten abone → ekran İPTAL yolunu söyler (genel "tekrar deneyin" DEĞİL)', () => {
  it('KRİTİK (TR): 409 already_subscribed → "iptal" içeren katalog metni', async () => {
    await dil('tr')
    durum.abonelikRef = 'sub-eski'
    const m = await ekranMetni(TAM)
    expect(durum.sonApi?.kod).toBe(409)
    expect(m).not.toBe(GENEL_TR)
    expect(m).toMatch(/iptal/i)
    expect(m).toBe(trHesap.odeme.zatenAbone)
  })
  it('KRİTİK (EN): aynı durum İngilizce, Türkçe harf YOK, "cancel" geçer', async () => {
    await dil('en')
    durum.abonelikRef = 'sub-eski'
    const m = await ekranMetni(TAM)
    expect(m).toBe(enHesap.odeme.zatenAbone)
    expect(m).toMatch(/cancel/i)
    expect(TR_HARF.test(m), m).toBe(false)
  })
})

describe('D6.30 · alan-özel 400 → ekran HANGİ kutunun eksik / hatalı olduğunu söyler', () => {
  const ETIKET: [alan: keyof typeof TAM, tr: string, en: string][] = [
    ['name', trOdeme.ad, enOdeme.ad],
    ['surname', trOdeme.soyad, enOdeme.soyad],
    ['identityNumber', trOdeme.tc, enOdeme.tc],
    ['gsmNumber', trOdeme.telefon, enOdeme.telefon],
    ['city', trHesap.alan.sehir, enHesap.alan.sehir],
    ['address', trOdeme.adres, enOdeme.adres],
  ]
  for (const [alan, trEtiket, enEtiket] of ETIKET) {
    it(`KRİTİK: "${alan}" boş → metin kutunun EKRAN etiketini anar (TR "${trEtiket}" / EN "${enEtiket}")`, async () => {
      await dil('tr')
      const tr = await ekranMetni({ ...TAM, [alan]: '' })
      expect(durum.sonApi?.kod).toBe(400)
      expect(tr).toContain(`"${trEtiket}"`)
      expect(tr).not.toBe(GENEL_TR)
      await dil('en')
      const en = await ekranMetni({ ...TAM, [alan]: '   ' })
      expect(en).toContain(`"${enEtiket}"`)
      expect(TR_HARF.test(en.replace(enEtiket, '')), en).toBe(false)
    })
  }
  it('KRİTİK: biçim / uzunluk hataları kendi metnine gider (TC 11 hane · telefon · adres uzun)', async () => {
    await dil('tr')
    expect(await ekranMetni({ ...TAM, identityNumber: '123' })).toBe(trHesap.odeme.tcBicim)
    expect(await ekranMetni({ ...TAM, gsmNumber: 'abc' })).toBe(trHesap.odeme.telefonBicim)
    expect(await ekranMetni({ ...TAM, address: 'x'.repeat(401) })).toBe(trHesap.odeme.adresUzun)
    expect(await ekranMetni({ ...TAM, city: 'y'.repeat(61) })).toBe(trHesap.odeme.adresUzun)
    await dil('en')
    for (const m of [
      await ekranMetni({ ...TAM, identityNumber: '123' }),
      await ekranMetni({ ...TAM, gsmNumber: 'abc' }),
      await ekranMetni({ ...TAM, address: 'x'.repeat(401) }),
    ]) expect(TR_HARF.test(m), m).toBe(false)
  })
})

describe('D6.30 · KARŞIT: tanınmayan sağlayıcı hatası eskisi gibi sınıflandırıcıya düşer; ham metin sızmaz', () => {
  it('iyzico başlatma hatası (502) → odemeHatasiTurkce sınıfı (yetersiz → tahsil edilemedi); EN Türkçe harfsiz', async () => {
    await dil('tr')
    expect(await ekranMetni(TAM)).toBe(trHesap.odeme.tahsilEdilemedi)
    expect(durum.sonApi?.kod).toBe(502)
    await dil('en')
    const en = await ekranMetni(TAM)
    expect(en).toBe(enHesap.odeme.tahsilEdilemedi)
    expect(TR_HARF.test(en)).toBe(false)
  })
  it('kodsuz / alansız yanıt (eski sunucu) genel metne düşer — uydurma alan adı YOK', async () => {
    await dil('tr')
    expect(odemeBaslatmaHatasi({ error: 'Lütfen "X" alanını doldurun.', kod: 'customer' })).toBe(GENEL_TR)
    expect(odemeBaslatmaHatasi({ error: 'bilinmeyen', kod: 'customer', alan: 'olmayanAlan', sebep: 'eksik' })).toBe(GENEL_TR)
    // nesne ön-ek adları (prototip) alan etiketi SAYILMAZ
    expect(odemeBaslatmaHatasi({ error: 'bilinmeyen', kod: 'customer', alan: 'constructor', sebep: 'eksik' })).toBe(GENEL_TR)
  })
})
