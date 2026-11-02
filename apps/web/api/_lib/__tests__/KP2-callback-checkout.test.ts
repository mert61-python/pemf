// Author: mertaygn, cglrgrkn
/**
 * KP-2 · api/callback.ts + api/checkout.ts · sözleşmeler:
 *  callback — `?uid` iyzico'nun conversationId'siyle UYUŞMAZSA reddedilir (hata sayfası, yazım yok) · ödeme alınmış ama eşleme
 *  tutmamışsa (plan / durum) 'incomplete'e gider ve teşhis için YALNIZ eşleme alanları günlüğe yazılır · iyzico çağrısı patlarsa
 *  hata sayfasına gider · başarıda abonelik + plan jeton hakkı yazılır ve indirme sayfasına gider.
 *  checkout — tam başarı yolu: iyzico'ya giden istek (conversationId = doğrulanmış kullanıcı, plan referansı ortamdan, geri dönüş
 *  adresi SUNUCU yapılandırmasından, e-posta doğrulanmış hesaptan, posta kodu varsayılanı) ve 200 {content, token} · site adresi
 *  yapılandırılmamışsa 500 ve iyzico'ya GİDİLMEZ · beklenmeyen istisna → 500 genel mesaj (iç ayrıntı sızmaz).
 *
 * Sahte EN ALT katta: `iyzipay` SDK + `fetch` (Supabase REST). Her test modülleri TAZE yükler (iyzico istemcisi tekildir).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

type Gc = (err: unknown, sonuc?: unknown) => void
const sdk = vi.hoisted(() => {
  const durum = {
    formSonuc: {} as Record<string, unknown>,
    formHata: null as unknown,
    initialize: [] as Record<string, unknown>[],
    initSonuc: {} as Record<string, unknown>,
  }
  class SahteIyzipay {
    static LOCALE = { TR: 'tr', EN: 'en' }
    static SUBSCRIPTION_INITIAL_STATUS = { ACTIVE: 'ACTIVE', PENDING: 'PENDING' }
    subscription = {}
    subscriptionCheckoutForm = {
      retrieve: (_istek: unknown, cb: Gc) => cb(durum.formHata, durum.formSonuc),
      initialize: (istek: Record<string, unknown>, cb: Gc) => {
        durum.initialize.push(istek)
        cb(null, durum.initSonuc)
      },
    }
  }
  return { durum, SahteIyzipay }
})
vi.mock('iyzipay', () => ({ default: sdk.SahteIyzipay }))

type Kayit = { url: string; yontem: string; govde: unknown }
let kayit: Kayit[] = []
let mevcutAbonelik: unknown[] = []
const json = (v: unknown, status = 200) => new Response(JSON.stringify(v), { status, headers: { 'Content-Type': 'application/json' } })
function agKur() {
  kayit = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const u = String(url)
      kayit.push({ url: u, yontem: init.method ?? 'GET', govde: init.body ? JSON.parse(String(init.body)) : undefined })
      if (u.endsWith('/auth/v1/user')) return json({ id: 'u-7', email: 'klinik@ornek.test' })
      if (u.includes('/rest/v1/subscriptions?')) return json(mevcutAbonelik)
      if (u.endsWith('/rest/v1/subscriptions')) return new Response(null, { status: 201 })
      if (u.includes('/rpc/jeton_donem_yenile')) return new Response('', { status: 200 })
      throw new Error(`beklenmeyen ağ isteği: ${u}`)
    }),
  )
}

function sahteRes() {
  const res = { kod: 0, govde: undefined as unknown, gidilen: '' } as {
    kod: number
    govde: Record<string, unknown>
    gidilen: string
  } & Record<string, unknown>
  res.status = (k: number) => ((res.kod = k), res)
  res.json = (g: Record<string, unknown>) => ((res.govde = g), res)
  res.redirect = (k: number, u: string) => ((res.kod = k), (res.gidilen = u), res)
  return res
}

beforeEach(() => {
  vi.resetModules()
  vi.stubEnv('IYZICO_URI', 'https://api.ornek-odeme.test')
  vi.stubEnv('IYZICO_API_KEY', 'test-anahtar-1')
  vi.stubEnv('IYZICO_SECRET_KEY', 'test-gizli-1')
  vi.stubEnv('IYZICO_PLAN_PRO_MONTHLY', 'plan-pro-aylik')
  vi.stubEnv('IYZICO_PLAN_PROPLUS_RESEARCH_YEARLY', 'plan-proplus-arastirma-yillik')
  vi.stubEnv('SUPABASE_URL', 'https://proje-ornek.supabase.test')
  vi.stubEnv('SUPABASE_ANON_KEY', 'test-anon-anahtari')
  vi.stubEnv('SUPABASE_SERVICE_ROLE_KEY', 'test-servis-anahtari')
  vi.stubEnv('PUBLIC_SITE_URL', 'https://site-ornek.test')
  vi.stubEnv('EXTRA_ALLOWED_ORIGINS', '')
  sdk.durum.formHata = null
  sdk.durum.formSonuc = {}
  sdk.durum.initialize.length = 0
  sdk.durum.initSonuc = { status: 'success', checkoutFormContent: '<script>iyzi</script>', token: 'form-tk-1' }
  mevcutAbonelik = []
  agKur()
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
  vi.restoreAllMocks()
})

describe('callback', () => {
  async function callback(query: Record<string, string>, body: Record<string, string> = { token: 'form-tk-1' }) {
    const h = (await import('../../callback')).default
    const res = sahteRes()
    await h({ body, query } as never, res as never)
    return res
  }

  it('uid ≠ conversationId → hata sayfası, abonelik YAZILMAZ, ret günlüğe (uid değeri günlüğe yazılmaz)', async () => {
    const gunluk = vi.spyOn(console, 'error').mockImplementation(() => {})
    sdk.durum.formSonuc = { conversationId: 'u-7', pricingPlanReferenceCode: 'plan-pro-aylik', referenceCode: 'sub-1', subscriptionStatus: 'ACTIVE' }
    const res = await callback({ uid: 'kurban' })
    expect(res.kod).toBe(302)
    expect(res.gidilen).toBe('/pricing?checkout=error')
    expect(kayit).toHaveLength(0)
    expect(gunluk).toHaveBeenCalledWith('callback: uid/conversationId uyuşmuyor — istek reddedildi', { conversationId: 'u-7' })
  })

  it('uid = conversationId → kabul; abonelik + jeton hakkı yazılır, indirme sayfasına gider', async () => {
    sdk.durum.formSonuc = {
      conversationId: 'u-7',
      pricingPlanReferenceCode: 'plan-pro-aylik',
      referenceCode: 'sub-1',
      customerReferenceCode: 'cus-1',
      subscriptionStatus: 'ACTIVE',
    }
    const res = await callback({ uid: 'u-7' })
    expect(res.gidilen).toBe('/download?checkout=success')
    expect(kayit.find((k) => k.url.endsWith('/rest/v1/subscriptions'))?.govde).toMatchObject({
      user_id: 'u-7',
      tier: 'pro',
      status: 'active',
      addons: [],
      stripe_subscription_id: 'sub-1',
      stripe_customer_id: 'cus-1',
    })
    expect(kayit.find((k) => k.url.includes('/rpc/jeton_donem_yenile'))?.govde).toEqual({ p_user: 'u-7', p_aylik_hak: 500 })
  })

  it('ödeme durumu canlı değil (CANCELED) → "incomplete" ve teşhis günlüğü yalnız eşleme alanlarıyla; yazım YOK', async () => {
    const gunluk = vi.spyOn(console, 'error').mockImplementation(() => {})
    sdk.durum.formSonuc = { conversationId: 'u-7', pricingPlanReferenceCode: 'plan-pro-aylik', referenceCode: 'sub-1', subscriptionStatus: 'CANCELED' }
    const res = await callback({})
    expect(res.gidilen).toBe('/pricing?checkout=incomplete')
    expect(gunluk).toHaveBeenCalledWith('callback: abonelik yazılamadı', {
      hasUserId: true,
      planRef: 'plan-pro-aylik',
      planResolved: true,
      subRef: 'sub-1',
      status: 'canceled',
    })
    expect(kayit).toHaveLength(0)
  })

  it('plan referansı yapılandırmada yok → "incomplete", planResolved:false', async () => {
    const gunluk = vi.spyOn(console, 'error').mockImplementation(() => {})
    sdk.durum.formSonuc = { conversationId: 'u-7', pricingPlanReferenceCode: 'plan-eski', referenceCode: 'sub-1', subscriptionStatus: 'ACTIVE' }
    const res = await callback({})
    expect(res.gidilen).toBe('/pricing?checkout=incomplete')
    expect(gunluk).toHaveBeenCalledWith('callback: abonelik yazılamadı', expect.objectContaining({ planRef: 'plan-eski', planResolved: false }))
  })

  it('iyzico retrieve hata verirse → hata sayfası ve günlük; yazım YOK', async () => {
    const gunluk = vi.spyOn(console, 'error').mockImplementation(() => {})
    sdk.durum.formHata = new Error('iyzico 503')
    const res = await callback({}, { token: 'form-tk-1' })
    expect(res.gidilen).toBe('/pricing?checkout=error')
    expect(gunluk).toHaveBeenCalledWith('callback error', sdk.durum.formHata)
    expect(kayit).toHaveLength(0)
  })

  it('token sorgu parametresinden de okunur (gövde boş)', async () => {
    sdk.durum.formSonuc = { conversationId: 'u-7', pricingPlanReferenceCode: 'plan-pro-aylik', referenceCode: 'sub-1', subscriptionStatus: 'PENDING' }
    const res = await callback({ token: 'sorgu-tk' }, {})
    expect(res.gidilen).toBe('/download?checkout=success')
    expect(kayit.find((k) => k.url.endsWith('/rest/v1/subscriptions'))?.govde).toMatchObject({ status: 'trialing' })
  })

  it('KP-2 tur 2: token ne gövdede ne sorguda → hata sayfası (302 /pricing?checkout=error), ağa / yazıma GİDİLMEZ', async () => {
    const res = await callback({}, {})
    expect(res.kod).toBe(302)
    expect(res.gidilen).toBe('/pricing?checkout=error')
    expect(kayit).toHaveLength(0)
  })
})

describe('checkout', () => {
  const MUSTERI = {
    name: 'Ayşe',
    surname: 'Veteriner',
    identityNumber: '10000000146',
    gsmNumber: '+905551112233',
    city: 'İzmir',
    address: 'Örnek Mah. 1',
  }
  async function checkout(govde: Record<string, unknown>, headers: Record<string, string> = {}) {
    const h = (await import('../../checkout')).default
    const res = sahteRes()
    await h({ method: 'POST', headers, body: govde } as never, res as never)
    return res
  }

  it('KP-2 tur 2: POST dışı yöntem → 405 {error: "method"}; kimlik / iyzico çağrısı YOK', async () => {
    const h = (await import('../../checkout')).default
    const res = sahteRes()
    await h({ method: 'GET', headers: {}, body: {} } as never, res as never)
    expect(res.kod).toBe(405)
    expect(res.govde).toEqual({ error: 'method' })
    expect(kayit).toHaveLength(0)
    expect(sdk.durum.initialize).toHaveLength(0)
  })

  it('KP-2 tur 2: oturum jetonu boş → 401 {error: "auth"} + giriş iletisi; Supabase kimlik ucuna istek GİTMEZ, iyzico başlatılmaz', async () => {
    const res = await checkout({ tier: 'pro', yearly: false, research: false, token: '', customer: MUSTERI })
    expect(res.kod).toBe(401)
    expect(res.govde).toEqual({ error: 'auth', message: 'Önce giriş yapın.' })
    expect(kayit.filter((k) => k.url.endsWith('/auth/v1/user'))).toHaveLength(0)
    expect(sdk.durum.initialize).toHaveLength(0)
  })

  it('başarı → 200 {content, token}; iyzico isteği sunucu yapılandırmasıyla kurulur (istemci origin\'i izin dışı → yok sayılır)', async () => {
    const res = await checkout({ tier: 'pro_plus', yearly: true, research: true, token: 'jwt-1', origin: 'https://saldirgan.test', customer: MUSTERI })
    expect(res.kod).toBe(200)
    expect(res.govde).toEqual({ content: '<script>iyzi</script>', token: 'form-tk-1' })
    expect(sdk.durum.initialize).toHaveLength(1)
    const istek = sdk.durum.initialize[0]
    const adres = { contactName: 'Ayşe Veteriner', city: 'İzmir', country: 'Turkey', address: 'Örnek Mah. 1', zipCode: '00000' }
    expect(istek).toEqual({
      locale: 'tr',
      conversationId: 'u-7',
      pricingPlanReferenceCode: 'plan-proplus-arastirma-yillik',
      subscriptionInitialStatus: 'ACTIVE',
      callbackUrl: 'https://site-ornek.test/api/callback?uid=u-7',
      customer: {
        name: 'Ayşe',
        surname: 'Veteriner',
        email: 'klinik@ornek.test',
        identityNumber: '10000000146',
        gsmNumber: '+905551112233',
        billingAddress: adres,
        shippingAddress: adres,
      },
    })
  })

  it('izinli origin (sondaki / atılır) geri dönüş adresine yazılır; posta kodu verilmişse korunur', async () => {
    vi.stubEnv('EXTRA_ALLOWED_ORIGINS', 'https://onizleme-ornek.test')
    await checkout({ tier: 'pro', token: 'jwt-1', origin: 'https://onizleme-ornek.test/', customer: { ...MUSTERI, zipCode: '35000' } })
    const istek = sdk.durum.initialize[0] as { callbackUrl: string; pricingPlanReferenceCode: string; customer: { billingAddress: { zipCode: string } } }
    expect(istek.callbackUrl).toBe('https://onizleme-ornek.test/api/callback?uid=u-7')
    expect(istek.pricingPlanReferenceCode).toBe('plan-pro-aylik')
    expect(istek.customer.billingAddress.zipCode).toBe('35000')
  })

  it('PUBLIC_SITE_URL yok → Host başlığından https adresi kurulur', async () => {
    vi.stubEnv('PUBLIC_SITE_URL', '')
    await checkout({ tier: 'pro', token: 'jwt-1', customer: MUSTERI }, { host: 'host-ornek.test' })
    expect((sdk.durum.initialize[0] as { callbackUrl: string }).callbackUrl).toBe('https://host-ornek.test/api/callback?uid=u-7')
  })

  it('site adresi hiç yapılandırılmamış (PUBLIC_SITE_URL yok, Host yok, origin izinsiz) → 500 ve iyzico\'ya GİDİLMEZ', async () => {
    vi.stubEnv('PUBLIC_SITE_URL', '')
    const res = await checkout({ tier: 'pro', token: 'jwt-1', origin: 'https://saldirgan.test', customer: MUSTERI })
    expect(res.kod).toBe(500)
    expect(res.govde).toEqual({ error: 'server', message: 'Site adresi yapılandırılmamış.' })
    expect(sdk.durum.initialize).toHaveLength(0)
  })

  it('beklenmeyen istisna (plan ortam değişkeni eksik) → 500 genel mesaj; değişken ADI yanıta sızmaz, günlüğe gider', async () => {
    const gunluk = vi.spyOn(console, 'error').mockImplementation(() => {})
    const res = await checkout({ tier: 'pro', yearly: true, token: 'jwt-1', customer: MUSTERI })
    expect(res.kod).toBe(500)
    expect(res.govde).toEqual({ error: 'server', message: 'Ödeme başlatılamadı. Lütfen daha sonra tekrar deneyin.' })
    expect(JSON.stringify(res.govde)).not.toContain('IYZICO_PLAN_PRO_YEARLY')
    expect(gunluk).toHaveBeenCalledWith('checkout error', expect.objectContaining({ message: 'Eksik ortam değişkeni: IYZICO_PLAN_PRO_YEARLY' }))
    expect(sdk.durum.initialize).toHaveLength(0)
  })
})
