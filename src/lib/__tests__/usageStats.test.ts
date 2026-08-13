// Author: mertaygn, cglrgrkn
/**
 * KULLANIM SAYACI — "indirme" değil BENZERSİZ KULLANIM (2026-08-13).
 *
 * Eski sayaç GitHub `download_count` gösteriyordu; o sayı "kaç kişi" DEĞİL "kaç indirme"dir
 * (client her sürümde kendini güncellerken kurulum dosyasını yeniden indirir + kendi
 * doğrulama indirmelerimiz). Yeni kaynak Supabase `usage_counts()` RPC'si.
 *
 * ⚠️ EN ÖNEMLİ DEĞİŞMEZ: veri YOKSA `null` dönülür ki bölüm HİÇ gösterilmesin. RPC henüz
 * deploy edilmemişken 0 ya da eski bir sayı göstermek, ziyaretçiye YANLIŞ bilgi vermektir.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const rpc = vi.fn()
vi.mock('../supabase', () => ({
  supabase: { rpc: (...a: unknown[]) => rpc(...a) },
  supabaseReady: true,
}))

const { fetchUsageStats } = await import('../usageStats')

beforeEach(() => rpc.mockReset())

describe('fetchUsageStats', () => {
  it('RPC satırını doğru eşler', async () => {
    rpc.mockResolvedValue({
      data: [{ accounts: 12, devices_total: 5, devices_active: 3 }],
      error: null,
    })
    const s = await fetchUsageStats()
    expect(s).toMatchObject({ accounts: 12, devicesTotal: 5, devicesActive: 3 })
    expect(rpc).toHaveBeenCalledWith('usage_counts')
  })

  it('KRITIK: RPC deploy edilmemişse null → bölüm gizlenir', async () => {
    // Supabase bilinmeyen fonksiyonda hata döner; 0 GÖSTERMEK yanlış bilgi olurdu.
    rpc.mockResolvedValue({ data: null, error: { message: 'function does not exist' } })
    expect(await fetchUsageStats()).toBeNull()
  })

  it('KRITIK: hata VARKEN veri de gelse KULLANILMAZ', async () => {
    // ⚠️ Bu test mutasyon turunda EKLENDİ: `error` kontrolünü silmek üstteki testi GEÇİYORDU,
    // çünkü orada `data` zaten boştu ve `!row` koruması sonucu kurtarıyordu. Yani `error`
    // kontrolü ÇİVİLENMEMİŞTİ. Supabase hata ile birlikte kısmi/bayat gövde döndürebilir;
    // o veriyi göstermek ziyaretçiye yanlış sayı vermek olur.
    rpc.mockResolvedValue({
      data: [{ accounts: 999, devices_total: 999, devices_active: 999 }],
      error: { message: 'permission denied' },
    })
    expect(await fetchUsageStats()).toBeNull()
  })

  it('boş sonuçta null döner', async () => {
    rpc.mockResolvedValue({ data: [], error: null })
    expect(await fetchUsageStats()).toBeNull()
  })

  it('istisnada null döner (ağ hatası sayfayı düşürmez)', async () => {
    // ⚠️ MOCK'UN İÇİNDE FIRLATMAYIN: vitest, mock içinde atılan hatayı — çağıran onu YAKALASA
    // BİLE — test hatası sayıyor (ayrı bir sonda ile doğrulandı: kod hatayı doğru yakalıyor,
    // testi düşüren vitest'in kaydı). Bunun yerine BOZUK YANIT verilir; hata `fetchUsageStats`
    // içinde (destructuring) oluşur → gerçek `catch` yolu aynen sınanır.
    rpc.mockReturnValue(undefined)
    expect(await fetchUsageStats()).toBeNull()
  })

  it('tek nesne (dizi değil) dönerse de eşler', async () => {
    rpc.mockResolvedValue({ data: { accounts: 7, devices_total: 2, devices_active: 2 }, error: null })
    expect((await fetchUsageStats())?.accounts).toBe(7)
  })

  it('iptal edilmiş istekte null döner', async () => {
    rpc.mockResolvedValue({ data: [{ accounts: 9, devices_total: 1, devices_active: 1 }], error: null })
    const ac = new AbortController()
    ac.abort()
    expect(await fetchUsageStats(ac.signal)).toBeNull()
  })
})
