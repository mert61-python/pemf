// Author: mertaygn, cglrgrkn
/**
 * SİTEDEKİ "ÇIKIŞ" TÜM CİHAZLARI DÜŞÜRÜYORDU (denetim 2026-08-18).
 *
 * `supabase.auth.signOut()` supabase-js v2'de VARSAYILAN olarak `scope: 'global'` çalışır ve
 * kullanıcının TÜM yenileme jetonlarını sunucuda iptal eder. Yani pazarlama sitesindeki tek
 * "Çıkış" düğmesi (Header → AccountButton), aynı hesapla açık olan:
 *   · mobil uygulamanın oturumunu (pf — Supabase auth),
 *   · klinikteki masaüstü launcher'ın oturumunu (1.9.9'dan beri Supabase girişi + "Beni hatırla")
 * da düşürüyordu. Kullanıcı bunu istemiyor, sebebini de göremiyor: klinikteki cihaz kendiliğinden
 * "giriş yapın" ekranına düşüyor.
 *
 * ⚠️ TEST BİÇİMİ: bu depoda jsdom/DOM ortamı YOK (bkz. auth-modal-focus.test.ts'teki aynı
 * gerekçe) → React context'i render edip `signOut`u çağıramayız. Ölçülen şey ÇAĞRI ARGÜMANIDIR
 * ve o argüman kaynakta tek bir yerde geçiyor; `?raw` ile okunur.
 */
import { describe, expect, it } from 'vitest'
import SRC from '../AuthContext.tsx?raw'

/** `signOut:` alanının gövdesi (kapanış `},`a kadar), YORUMLAR SOYULMUŞ.
 *
 *  ⚠️ Soyma ZORUNLU: bu düzeltmenin KENDİ gerekçe yorumu `signOut()` dizesini aynen içeriyor
 *  (v2 varsayılanını anlatıyor). Soyulmazsa "argümansız çağrı yok" iddiası kendi açıklamasını
 *  görüp yanlış-KIRMIZI verir — ve ters yönde de kandırılabilirdi. Bu depo aynı tuzağa daha
 *  önce dört kez düştü; kapı yazarken yorum soymak artık kural. */
function signOutGovdesi(): string {
  const bas = SRC.indexOf('signOut: async () =>')
  expect(bas, 'signOut alanı bulunamadı — test güncellenmeli').toBeGreaterThan(-1)
  return SRC.slice(bas, SRC.indexOf('\n    },', bas))
    .split('\n')
    .filter((l) => !l.trim().startsWith('//'))
    .join('\n')
}

describe('site çıkışı yalnız BU tarayıcıyı kapatır', () => {
  it("KRİTİK: signOut 'local' kapsamıyla çağrılır (mobil/launcher oturumu düşmesin)", () => {
    expect(signOutGovdesi()).toMatch(/signOut\(\s*\{[^}]*scope:\s*'local'/)
  })

  it('KARŞIT-KANIT: çağrı hâlâ YAPILIYOR (kapsamı daraltmak, çıkışı kaldırmak değildir)', () => {
    expect(signOutGovdesi()).toContain('supabase.auth.signOut(')
    expect(signOutGovdesi()).toContain('await')
  })

  it("argümansız `signOut()` (v2 varsayılanı = 'global') KULLANILMAZ", () => {
    expect(signOutGovdesi()).not.toMatch(/signOut\(\s*\)/)
  })
})
