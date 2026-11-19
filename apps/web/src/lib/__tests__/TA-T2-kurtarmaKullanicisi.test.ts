// Author: mertaygn, cglrgrkn
/**
 * TA T2 (Y292-3) · lib/supabase.ts `kurtarmaKullanicisi`: kurtarma kanıtı YALNIZ `PASSWORD_RECOVERY` olayı; dinleyici istemciyle
 * AYNI anda (modül düzeyinde) kurulur ki olay sayfa bileşeni yüklenmeden yayılsa da kaçmasın. Düz SIGNED_IN / TOKEN_REFRESHED
 * kurtarma SAYILMAZ; SIGNED_OUT unutturur. Sahte EN ALT katta: `@supabase/supabase-js` createClient.
 */
import { expect, it, vi } from 'vitest'

const s = vi.hoisted(() => ({ dinleyiciler: [] as ((olay: string, oturum: unknown) => void)[] }))
vi.mock('@supabase/supabase-js', () => ({
  createClient: () => ({
    auth: {
      onAuthStateChange: (f: (olay: string, oturum: unknown) => void) => {
        s.dinleyiciler.push(f)
        return { data: { subscription: { unsubscribe() {} } } }
      },
    },
  }),
}))

import { kurtarmaKullanicisi } from '../supabase'

it('modül yüklenince dinleyici HEMEN kurulur (bileşen beklenmez); yalnız PASSWORD_RECOVERY kimlik kaydeder, SIGNED_OUT unutturur', () => {
  expect(s.dinleyiciler).toHaveLength(1)
  const yay = (olay: string, oturum: unknown) => s.dinleyiciler[0](olay, oturum)
  expect(kurtarmaKullanicisi()).toBeNull()
  yay('INITIAL_SESSION', { user: { id: 'u-girisli' } })
  yay('SIGNED_IN', { user: { id: 'u-girisli' } })
  expect(kurtarmaKullanicisi()).toBeNull()
  yay('PASSWORD_RECOVERY', { user: { id: 'u-kurtarma' } })
  expect(kurtarmaKullanicisi()).toBe('u-kurtarma')
  yay('TOKEN_REFRESHED', { user: { id: 'u-kurtarma' } })
  yay('SIGNED_IN', { user: { id: 'u-baska' } }) // başka sekmede giriş: kimlik DEĞİŞMEZ (sayfa gönderimde oturumu karşılaştırır)
  expect(kurtarmaKullanicisi()).toBe('u-kurtarma')
  yay('SIGNED_OUT', null)
  expect(kurtarmaKullanicisi()).toBeNull()
  yay('PASSWORD_RECOVERY', null) // oturumsuz olay kimlik UYDURMAZ
  expect(kurtarmaKullanicisi()).toBeNull()
  yay('PASSWORD_RECOVERY', { user: {} })
  expect(kurtarmaKullanicisi()).toBeNull()
})
