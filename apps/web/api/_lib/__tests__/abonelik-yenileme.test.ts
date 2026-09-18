// Author: mertaygn, cglrgrkn
/**
 * İPTAL EDEN KULLANICI BİR DAHA ABONE OLAMIYORDU (denetim 2026-08-18).
 *
 * `api/cancel.ts` iptalde yalnız `status='canceled'` yazıyor; `stripe_subscription_id` satırda
 * KALIYOR (bilerek: `getUserBySubscriptionRef` webhook'ta o referansla kullanıcıyı buluyor).
 * Ama `getSubscriptionRefByUser` DURUM FİLTRESİZ sorguluyordu → iptal edilmiş satırın referansı
 * da dönüyordu ve `api/checkout.ts` "Hesabınızda zaten aktif bir abonelik var. Plan değiştirmek
 * için önce mevcut aboneliğinizi iptal edin." diyerek 409 basıyordu.
 *
 * Sonuç: kullanıcı iptal ettikten sonra BİR DAHA ABONE OLAMIYOR ve plan da DEĞİŞTİREMİYOR;
 * üstelik hata mesajı ona zaten yaptığı şeyi (iptal et) söylüyor. Tekrar "iptal et"e basarsa
 * iyzico zaten iptal edilmiş aboneliği reddediyor → 502 "İptal edilemedi". Çıkışsız döngü.
 *
 * DEĞİŞMEZ: `getSubscriptionRefByUser` yalnız CANLI aboneliği (active/trialing/past_due) döner.
 * `past_due` DE canlıdır — ödeme aksamış ama iyzico'da abonelik duruyor; onu ikizlemek
 * kullanıcıyı iki kez tahsilata açar (checkout.ts:23-27'deki yetim-kayıt gerekçesi).
 *
 * ⚠️ Sahte `fetch` PostgREST'i TAKLİT eder (URL'deki `status=in.(...)` filtresini GERÇEKTEN
 * uygular). Aksi halde test totolojik olurdu: filtreyi testin kendisi uydurmuş olurdu.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { getSubscriptionRefByUser } from '../util.js'

const OLD = { ...process.env }
type Satir = { user_id: string; status: string; stripe_subscription_id: string }

/** Tablodaki tek satır — testler bunu değiştirir. */
let TABLO: Satir[] = []
let SON_URL = ''

function sahtePostgrest(url: string): Satir[] {
  const u = new URL(url)
  let rows = TABLO
  const uid = u.searchParams.get('user_id') // "eq.<id>"
  if (uid?.startsWith('eq.')) rows = rows.filter((r) => r.user_id === uid.slice(3))
  const st = u.searchParams.get('status') // "in.(a,b,c)"
  if (st?.startsWith('in.(')) {
    const kabul = st.slice(4, -1).split(',').map((s) => s.trim())
    rows = rows.filter((r) => kabul.includes(r.status))
  }
  return rows
}

beforeEach(() => {
  process.env.SUPABASE_URL = 'https://proje.supabase.co'
  process.env.SUPABASE_SERVICE_ROLE_KEY = 'servis-anahtari-testte'
  SON_URL = ''
  vi.stubGlobal('fetch', async (url: string) => {
    SON_URL = url
    const rows = sahtePostgrest(url)
    return { ok: true, json: async () => rows } as unknown as Response
  })
})
afterEach(() => {
  vi.unstubAllGlobals()
  process.env = { ...OLD }
})

describe('getSubscriptionRefByUser — iptal eden kullanıcı yeniden abone olabilmeli', () => {
  it('KRİTİK: İPTAL EDİLMİŞ abonelik yeni satın almayı ENGELLEMEZ', async () => {
    TABLO = [{ user_id: 'u1', status: 'canceled', stripe_subscription_id: 'ref-eski' }]
    expect(await getSubscriptionRefByUser('u1')).toBeNull()
  })

  it('KARŞIT-KANIT: AKTİF abonelik ikinci satın almayı ENGELLEMEYE devam eder', async () => {
    // "Her zaman null dön" biçimindeki bir yama düzeltme DEĞİL: çift abonelik yetim kayıt
    // bırakır (checkout.ts:23-27) → kullanıcı iki abonelikten de tahsil edilir.
    TABLO = [{ user_id: 'u1', status: 'active', stripe_subscription_id: 'ref-canli' }]
    expect(await getSubscriptionRefByUser('u1')).toBe('ref-canli')
  })

  it('KARŞIT-KANIT: `trialing` ve `past_due` DE canlıdır — engellemeye devam eder', async () => {
    for (const durum of ['trialing', 'past_due']) {
      TABLO = [{ user_id: 'u1', status: durum, stripe_subscription_id: `ref-${durum}` }]
      expect(await getSubscriptionRefByUser('u1')).toBe(`ref-${durum}`)
    }
  })

  it('filtre SUNUCUDA uygulanır (istemcide değil) — sorgu `status=in.(...)` taşır', async () => {
    // Satırı çekip JS'te elemek de çalışırdı ama iptal edilmiş satırın referansını ağa çıkarır;
    // asıl önemlisi: kapının nerede olduğu ölçülebilir kalsın.
    TABLO = []
    await getSubscriptionRefByUser('u1')
    expect(decodeURIComponent(SON_URL)).toContain('status=in.(')
    for (const canli of ['active', 'trialing', 'past_due']) {
      expect(decodeURIComponent(SON_URL)).toContain(canli)
    }
    expect(decodeURIComponent(SON_URL)).not.toContain('canceled')
  })

  it('satır hiç yoksa null (ilk kez abone olan kullanıcı)', async () => {
    TABLO = []
    expect(await getSubscriptionRefByUser('u1')).toBeNull()
  })
})

/**
 * ÇİFT-ABONELİK KAPISI FAIL-OPEN'DI (denetim 2026-08-18).
 *
 * `getSubscriptionRefByUser` Supabase yanıtı `ok` değilse (5xx, ağ hatası, RLS/anahtar sorunu)
 * `null` dönüyordu. İki çağıranın ihtiyacı ZITTIR:
 *
 *   · `api/checkout.ts` → `null` = "aboneliği yok" → yeni abonelik BAŞLATILIR. Yani altyapı
 *     hatası anında, zaten abonesi olan kullanıcıya İKİNCİ abonelik açılır: iki iyzico
 *     aboneliğinden de tahsilat yapılır ve `subscriptions.user_id` PRIMARY KEY olduğu için
 *     callback satırı EZER → eski referans kaybolur, `/api/cancel` onu ARTIK BULAMAZ.
 *     (checkout.ts:23-27 bu senaryoyu zaten "yetim kayıt" diye tarif ediyor — kapı tam da onu
 *     önlemek için var ama hata anında kendisi açılıyordu.)
 *   · `api/cancel.ts` → `null` = 404 "Aktif abonelik bulunamadı" (para hareketi yok, zararsız).
 *
 * Para hareketi olan yön FAIL-CLOSED olmalı. `throw` ikisini birden doğru yapar: iki uç da
 * hatayı zaten yakalıyor ve dürüst bir "sonra tekrar deneyin" mesajı dönüyor.
 */
describe('getSubscriptionRefByUser — altyapı hatası "aboneliği yok" DEMEK DEĞİLDİR', () => {
  it('KRİTİK: Supabase 5xx dönerse null DEĞİL HATA verir (çift abonelik açılmasın)', async () => {
    vi.stubGlobal('fetch', async () => ({ ok: false, status: 503, text: async () => 'upstream down' }) as unknown as Response)
    await expect(getSubscriptionRefByUser('u1')).rejects.toThrow()
  })

  it('KRİTİK: ağ hatası (fetch reddi) yutulmaz', async () => {
    vi.stubGlobal('fetch', async () => {
      throw new TypeError('network')
    })
    await expect(getSubscriptionRefByUser('u1')).rejects.toThrow()
  })

  it('KARŞIT-KANIT: BAŞARILI ve BOŞ yanıt hâlâ null (ilk kez abone olan engellenmesin)', async () => {
    // "Her durumda fırlat" biçimindeki bir yama düzeltme DEĞİL: hiç aboneliği olmayan kullanıcı
    // da satın alamaz hâle gelirdi.
    TABLO = []
    vi.stubGlobal('fetch', async (url: string) => {
      SON_URL = url
      return { ok: true, json: async () => sahtePostgrest(url) } as unknown as Response
    })
    expect(await getSubscriptionRefByUser('u1')).toBeNull()
  })
})
