// Author: mertaygn, cglrgrkn
/**
 * KP-8 · api/_lib/util.ts kalan dallar (sahte `fetch` — canlı Supabase YOK):
 *  - `isAllowedOrigin`: site adresi (PUBLIC_SITE_URL) tanımsız ve ek köken yokken HİÇBİR köken izinli değil.
 *  - `verifyUser`: kimlik ucu kimliksiz gövde dönerse `null` (oturum uydurulmaz).
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { isAllowedOrigin, verifyUser } from '../util'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})

describe('api/_lib/util', () => {
  it('site adresi tanımsız + ek köken yok → hiçbir köken izinli değil', () => {
    vi.stubEnv('EXTRA_ALLOWED_ORIGINS', '')
    vi.stubEnv('PUBLIC_SITE_URL', '')
    delete process.env.PUBLIC_SITE_URL
    expect(isAllowedOrigin('https://site-ornek.test')).toBe(false)
  })

  it('kimlik ucu kimliksiz gövde dönerse null', async () => {
    vi.stubEnv('SUPABASE_URL', 'https://proje-ornek.supabase.test')
    vi.stubEnv('SUPABASE_ANON_KEY', 'test-anon-anahtari')
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ email: 'x@y.test' }), { status: 200, headers: { 'Content-Type': 'application/json' } })))
    await expect(verifyUser('jwt')).resolves.toBeNull()
  })
})
