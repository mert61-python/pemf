/**
 * YH B3 (S-YH) — paylaşılabilir dil bağlantısı `?lang=tr|en`: adresteki dil kayıtlı seçimden ÖNCE gelir ve seçim olarak HATIRLANIR (site
 * içi bağlantılar parametre taşımaz); geçersiz değer yok sayılır (Y161: kayıtlı seçim > tarayıcı dili); dil düğmesi adreste `lang` varsa onu
 * yeni dile eşitler, yoksa adrese dokunmaz; bayrak KAPALIYKEN adres de Türkçeyi değiştiremez. Depolama erişilemezse çökmez.
 * Modül düzeyi başlatma ölçüldüğü için her senaryo `vi.resetModules()` + yeni içe aktarma ile koşar.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

type Ortam = { arama: string; kayitli?: string | null; tarayici?: string; depoAtar?: boolean; bayrak?: boolean }

async function yukle(o: Ortam) {
  vi.resetModules()
  const depo = new Map<string, string>()
  if (o.kayitli) depo.set('pemf.dil', o.kayitli)
  const atar = () => {
    throw new Error('depo kapalı')
  }
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => (o.depoAtar ? atar() : (depo.get(k) ?? null)),
    setItem: (k: string, v: string) => (o.depoAtar ? atar() : void depo.set(k, String(v))),
    removeItem: (k: string) => void depo.delete(k),
  })
  vi.stubGlobal('document', { documentElement: { lang: '' }, title: '', querySelector: () => null })
  vi.stubGlobal('navigator', { language: o.tarayici ?? 'tr-TR' })
  const yazilan: string[] = []
  vi.stubGlobal('location', { search: o.arama, href: `https://pemf-vet-web.vercel.app/pricing${o.arama}`, pathname: '/pricing' })
  vi.stubGlobal('history', { state: { r: 1 }, replaceState: (_s: unknown, _t: string, u: string) => void yazilan.push(u) })
  if (o.bayrak !== undefined) {
    vi.doMock('../bayrak', () => ({ I18N_EN_ACIK: o.bayrak }))
  } else {
    vi.doUnmock('../bayrak')
  }
  const m = await import('../index')
  return { m, i18n: m.default, depo, yazilan }
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.doUnmock('../bayrak')
})

describe('?lang= ilk yükleme', () => {
  it('?lang=en: Türkçe tarayıcı + kayıtlı tr olsa bile İngilizce açılır ve en kaydedilir', async () => {
    const { i18n, depo } = await yukle({ arama: '?lang=en', kayitli: 'tr', tarayici: 'tr-TR' })
    expect(i18n.language).toBe('en')
    expect(depo.get('pemf.dil')).toBe('en')
  })

  it('?lang=tr: İngilizce tarayıcıda Türkçe', async () => {
    const { i18n, depo } = await yukle({ arama: '?lang=tr', tarayici: 'en-US' })
    expect(i18n.language).toBe('tr')
    expect(depo.get('pemf.dil')).toBe('tr')
  })

  it('geçersiz ?lang=de yok sayılır: kayıtlı seçim > tarayıcı dili (Y161), kayıt DEĞİŞMEZ', async () => {
    const a = await yukle({ arama: '?lang=de', kayitli: 'en', tarayici: 'tr-TR' })
    expect(a.i18n.language).toBe('en')
    const b = await yukle({ arama: '?lang=de', tarayici: 'en-GB' })
    expect(b.i18n.language).toBe('en')
    expect(b.depo.has('pemf.dil')).toBe(false)
  })

  it('parametre yok: kayıtlı seçim yoksa tarayıcı dili; hiçbir şey kaydedilmez', async () => {
    const { i18n, depo } = await yukle({ arama: '', tarayici: 'de-DE' })
    expect(i18n.language).toBe('en')
    expect(depo.size).toBe(0)
  })

  it('bayrak KAPALI: ?lang=en Türkçeyi DEĞİŞTİREMEZ ve kaydedilmez', async () => {
    const { i18n, depo } = await yukle({ arama: '?lang=en', tarayici: 'en-US', bayrak: false })
    expect(i18n.language).toBe('tr')
    expect(depo.size).toBe(0)
  })

  it('depolama erişilemezse çökmez; adres dili yine uygulanır', async () => {
    const { i18n } = await yukle({ arama: '?lang=en', depoAtar: true })
    expect(i18n.language).toBe('en')
  })
})

describe('dil düğmesi ↔ adres', () => {
  it('adreste lang VARSA yeni dile eşitlenir (yeniden yüklemede eski dile dönmez); yol + diğer parametreler korunur', async () => {
    const { m, yazilan } = await yukle({ arama: '?lang=en&tier=pro', tarayici: 'en-US' })
    await m.dilSec('tr')
    expect(yazilan).toEqual(['/pricing?lang=tr&tier=pro'])
  })

  it('adreste lang YOKSA adrese dokunulmaz', async () => {
    const { m, yazilan } = await yukle({ arama: '?tier=pro', tarayici: 'en-US' })
    await m.dilSec('tr')
    expect(yazilan).toEqual([])
  })
})
