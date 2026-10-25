// Author: mertaygn, cglrgrkn
/**
 * D3.21 (B-7.7) + D3.22 (B-7.8 · A-20) — ödeme dönüşü (FREE_MODE'da UYKUDA; Vercel'e istek YOK, iyzico sahte):
 *  - callback: iyzico yanıtında `conversationId` YOKSA `?uid` tek başına KABUL EDİLMEZ (fail-closed) — eskiden
 *    `conversationId || uidQuery` yedeği aboneliği kurbanın satırına yazdırıyordu.
 *  - dönüş adresi izin listesi: YALNIZ üretim alanı (A-20); başkasının `*.vercel.app` projesi reddedilir; önizleme yalnız
 *    EXTRA_ALLOWED_ORIGINS'e açıkça yazılırsa.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'

const OLD = { ...process.env }

vi.mock('../iyzico.js', () => ({
  subRetrieveByToken: vi.fn(),
  subRetrieveByRef: vi.fn(),
  planMeta: vi.fn(),
  verifyWebhookSignature: vi.fn().mockReturnValue(true),
}))

import * as iyzico from '../iyzico.js'
import * as util from '../util.js'

function sahteRes() {
  const res: Record<string, unknown> = {}
  res.statusCode = 0
  res.gidilen = ''
  res.status = vi.fn().mockImplementation((k: number) => ((res.statusCode = k), res))
  res.json = vi.fn().mockReturnValue(res)
  res.redirect = vi.fn().mockImplementation((k: number, u: string) => ((res.statusCode = k), (res.gidilen = u), res))
  return res as unknown as { statusCode: number; gidilen: string } & Record<string, ReturnType<typeof vi.fn>>
}

beforeEach(() => {
  process.env.SUPABASE_URL = 'https://proje.supabase.co'
  process.env.SUPABASE_SERVICE_ROLE_KEY = 'servis-anahtari-testte'
  process.env.PUBLIC_SITE_URL = 'https://pemf-vet-web.vercel.app'
  process.env.EXTRA_ALLOWED_ORIGINS = ''
  vi.restoreAllMocks()
})
afterEach(() => {
  vi.unstubAllGlobals()
  process.env = { ...OLD }
})

describe('D3.21 callback IDOR fail-closed', () => {
  it('KRİTİK: conversationId YOKKEN ?uid=kurban ile abonelik YAZILMAZ, hata sayfasına gider', async () => {
    vi.mocked(iyzico.subRetrieveByToken).mockResolvedValue({
      pricingPlanReferenceCode: 'plan-pro',
      referenceCode: 'sub-1',
      customerReferenceCode: 'cust-1',
      subscriptionStatus: 'ACTIVE',
    } as never)
    vi.mocked(iyzico.planMeta).mockReturnValue({ tier: 'pro', research: false, yearly: false } as never)
    const upsert = vi.spyOn(util, 'upsertSubscription').mockResolvedValue()
    const yenile = vi.spyOn(util, 'jetonDonemYenile').mockResolvedValue()
    const { default: handler } = await import('../../callback.js')
    const res = sahteRes()
    await handler({ body: { token: 't-1' }, query: { uid: 'kurban' } } as never, res as never)
    expect(upsert).not.toHaveBeenCalled()
    expect(yenile).not.toHaveBeenCalled()
    expect(res.gidilen).toContain('/pricing?checkout=error')
  })

  it('KARŞIT: conversationId varsa (uid eşleşse de eşleşmese de yok sayılır) o kullanıcıya yazılır', async () => {
    vi.mocked(iyzico.subRetrieveByToken).mockResolvedValue({
      conversationId: 'uid-7',
      pricingPlanReferenceCode: 'plan-pro',
      referenceCode: 'sub-1',
      customerReferenceCode: 'cust-1',
      subscriptionStatus: 'ACTIVE',
    } as never)
    vi.mocked(iyzico.planMeta).mockReturnValue({ tier: 'pro', research: false, yearly: false } as never)
    const upsert = vi.spyOn(util, 'upsertSubscription').mockResolvedValue()
    vi.spyOn(util, 'jetonDonemYenile').mockResolvedValue()
    const { default: handler } = await import('../../callback.js')
    const res = sahteRes()
    await handler({ body: { token: 't-1' }, query: {} } as never, res as never)
    expect(upsert).toHaveBeenCalledWith(expect.objectContaining({ user_id: 'uid-7' }))
    expect(res.gidilen).toContain('checkout=success')
  })
})

describe('D3.22 dönüş adresi yalnız üretim alanı (A-20)', () => {
  it('KRİTİK: başkasının *.vercel.app projesi ve kendi önizleme alanı (açıkça eklenmeden) REDDEDİLİR', () => {
    expect(util.isAllowedOrigin('https://baska-birinin-projesi.vercel.app')).toBe(false)
    expect(util.isAllowedOrigin('https://pemf-vet-web-git-abc.vercel.app')).toBe(false)
  })

  it('KARŞIT: üretim alanı ve EXTRA_ALLOWED_ORIGINS ile açıkça eklenen alan kabul', () => {
    expect(util.isAllowedOrigin('https://pemf-vet-web.vercel.app')).toBe(true)
    process.env.EXTRA_ALLOWED_ORIGINS = 'https://pemf-vet-web-git-abc.vercel.app'
    expect(util.isAllowedOrigin('https://pemf-vet-web-git-abc.vercel.app')).toBe(true)
  })
})
