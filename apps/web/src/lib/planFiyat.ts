// Author: mertaygn, cglrgrkn
/**
 * PLAN FİYAT GÖSTERİMİ — TEK KAYNAK.
 *
 * NEDEN AYRI DOSYA (8. parti): aynı hesap İKİ sayfada ayrı ayrı yazılıydı — `Pricing.tsx`
 * (`priceView`) ve `Home.tsx` (satır içi JSX). İkisi de `p.monthly ?? 0` varsayıyordu; aylık
 * ücreti OLMAYAN "Kullandıkça Öde" planı eklenince biri "test sonrası ₺0/ay", öteki "₺0/ay"
 * yazdı. İkisi de yanlıştı: ücret sıfır değil, JETON BAŞINA.
 *
 * Bu, deponun 1 numaralı hata deseninin fiyat yüzeyindeki hâli: "aynı kural, iki yer — biri
 * düzeltilir, öteki unutulur". Hesap buraya taşındı; iki sayfa da bunu çağırır ve
 * `kullandikca-ode.test.ts` DAVRANIŞI (üretilen metni) sınar, kaynak kodu değil.
 *
 * SIRA ÖNEMLİ:
 *   1. `priceLabel` varsa o kazanır — aylık ücret kavramı olmayan planlar (kullandıkça öde)
 *      kendi etiketini taşır. FREE_MODE dalından ÖNCE gelmeli.
 *   2. Ücretsiz dönemde (FREE_MODE) ücretli planlar rakam yerine durum yazar.
 *   3. Kalan durumda aylık/yıllık tarife.
 */
import { FREE_MODE, type Plan } from '../config'

export type FiyatGorunumu = {
  /** Büyük punto: ya tutar ya durum ("Şu an ücretsiz"). */
  buyuk: string
  /** Küçük açıklama satırı (dönem, yıllık toplam, test sonrası tarife…). */
  kucuk: string
}

const tl = (n: number) => `₺${n.toLocaleString('tr-TR')}`

export function planFiyatGorunumu(p: Plan, yillik: boolean): FiyatGorunumu {
  // (1) Kendi etiketi olan plan — aylık ücret varsayımı UYGULANMAZ.
  if (p.priceLabel) return { buyuk: p.priceLabel, kucuk: p.period }

  // (2) Ücretsiz dönem: rakam yerine durum; asıl tarife küçük not olarak kalır (şeffaflık).
  if (FREE_MODE && p.paid) {
    return { buyuk: 'Şu an ücretsiz', kucuk: `test sonrası ${tl(p.monthly ?? 0)}/ay` }
  }

  // (3) Normal tarife.
  const aylikTutar = yillik ? Math.round((p.yearly ?? 0) / 12) : p.monthly ?? 0
  return {
    buyuk: tl(aylikTutar),
    kucuk: yillik ? `${p.period} · yıllık ${tl(p.yearly ?? 0)}` : p.period,
  }
}

/**
 * Ana sayfadaki kompakt plan kutusunun sağ tarafı — tek satırlık özet.
 * Aynı sıra kuralı geçerlidir; `monthly ?? 0` yalnız EN SON dalda kullanılabilir.
 */
export function planKisaFiyat(p: Plan): string {
  if (p.priceLabel) return p.priceLabel
  if (FREE_MODE) return 'Şu an ücretsiz'
  return `${tl(p.monthly ?? 0)}/ay`
}
