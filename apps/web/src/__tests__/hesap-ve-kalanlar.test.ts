// Author: mertaygn, cglrgrkn
/**
 * HESAP GÖRÜNÜRLÜĞÜ + KALAN KALEMLER — kullanıcı-dostuluk denetimi 4. parti (2026-08-20).
 *
 * Bu partide kapatılanlar:
 *   · Abonelik iptali TARAYICI `confirm`/`alert` kutularıyla yürütülüyordu — para/abonelik gibi
 *     kritik bir eylemde sitenin tonu ve görsel dili tamamen kayboluyordu.
 *   · Giriş yapan kullanıcı hesabıyla ilgili HİÇBİR ŞEY göremiyordu (yalnız iptal + çıkış).
 *   · "Yakında" olan platform kartları çıkışsızdı (haber verme yolu yoktu).
 *   · Ekran görüntüsü bölümü "mobil ve masaüstünde aynı arayüz" diyordu ama görsellerin tamamı
 *     telefon çerçevesindeydi.
 *   · İndirme sayacı iç ölçüm diliyle ("Benzersiz kullanıcı" + metodoloji dipnotu) yazılmıştı.
 *   · Ödeme formunda TC Kimlik No'nun NEDEN istendiği geçiştiriliyordu.
 *
 * ⚠️ BİLEREK YAPILMAYAN: plan/yenileme tarihi gösteren tam bir "Hesabım" sayfası. `subscriptions`
 * tablosunda `current_period_end` alanına BU DEPODA HİÇBİR YOL değer YAZMIYOR (api/cancel.ts
 * yorumunda ölçülmüş) → tarih göstermek UYDURMA veri olurdu. Sahip kararı olarak kayıtlı.
 */
import { describe, expect, it } from 'vitest'

import { kaynakSoy as soy } from './_soyucu'

import ACCOUNT_SRC from '../components/AccountButton.tsx?raw'
import NOTFOUND_SRC from '../pages/NotFound.tsx?raw'
import ODEME_SRC from '../pages/Odeme.tsx?raw'
import DOWNLOAD_SRC from '../pages/Download.tsx?raw'
import SHOTS_SRC from '../components/AppScreenshots.tsx?raw'
import STATS_SRC from '../components/DownloadStats.tsx?raw'
import LEGAL_SRC from '../pages/Legal.tsx?raw'

describe('1) hesap alanı', () => {
  it('KRİTİK: abonelik iptali TARAYICI confirm/alert ile yapılmaz', () => {
    const s = soy(ACCOUNT_SRC)
    expect(s).not.toMatch(/window\.confirm/)
    expect(s).not.toMatch(/window\.alert/)
  })

  it('KRİTİK: giriş yapan kullanıcı HESABINI görür (e-posta + durum)', () => {
    // Header'da yalnız "Aboneliği iptal et" + "Çıkış" vardı; kullanıcı hangi hesapla girdiğini
    // bile göremiyordu (yalnız `title` ipucunda vardı — dokunmatikte görünmez).
    const s = soy(ACCOUNT_SRC)
    expect(s).toMatch(/\{email\}/)
    expect(s).toMatch(/Hesabım|Hesap/)
  })

  it('KRİTİK: iptal onayı SONUCU açıkça söyler (yenileme durur, bir daha ücret alınmaz)', () => {
    // ⚠️ İDDİA DEĞİŞTİ (6. parti, adversaryal inceleme): bu kapı önce "ödediğiniz dönemin
    // sonuna kadar erişiminiz sürer" ifadesini ZORUNLU tutuyordu. `api/cancel.ts` içindeki
    // ölçüm bunun TUTMADIĞINI gösteriyor (`current_period_end` hiçbir yol tarafından
    // yazılmıyor; hak katmanları yalnız `status`e bakıp `canceled`ı pasif sayıyor). Yani eski
    // kapı, tutulamayacak bir vaadi KİLİTLİYORDU. Ölçülen gerçeğe göre daraltıldı; vaadin
    // yokluğu ayrıca `dogruluk.test.ts` içinde kilitli.
    const s = soy(ACCOUNT_SRC)
    expect(s).toMatch(/yenileme/i)
    expect(s).toMatch(/bir daha ücret alınmaz/i)
  })

  it('KARŞIT-KANIT: UYDURMA abonelik verisi gösterilmez (yenileme tarihi/fatura)', () => {
    // `current_period_end` hiçbir yol tarafından yazılmıyor → tarih göstermek yanlış bilgi olurdu.
    const s = soy(ACCOUNT_SRC)
    expect(s).not.toMatch(/current_period_end|yenileme tarihi|fatura no/i)
  })
})

describe('2) kalan kalemler', () => {
  it('KRİTİK: 404 sayfası HTTP durum kodunu başlık gibi göstermez', () => {
    const s = soy(NOTFOUND_SRC)
    expect(s).not.toMatch(/>\s*404\s*</)
  })

  it('KRİTİK: TC Kimlik No’nun NEDEN istendiği yazılıdır', () => {
    // "iyzico güvenli ödeme için gereklidir" geçiştirmesi kullanıcıyı ikna etmiyordu.
    const s = soy(ODEME_SRC)
    const i = s.indexOf('TC Kimlik No')
    expect(i).toBeGreaterThan(-1)
    expect(s).toMatch(/yasal (zorunluluk|gereklilik)|fatura(landırma)? için|vergi mevzuatı/i)
  })

  it('KRİTİK: "Yakında" olan platformda haber-verme yolu var', () => {
    // Devre dışı buton hiçbir çıkış sunmuyordu; ana sayfadaki aynı durum e-posta bağlantısı veriyor.
    const s = soy(DOWNLOAD_SRC)
    const i = s.indexOf('Yakında')
    expect(i).toBeGreaterThan(-1)
    expect(s.slice(i - 300, i + 600)).toMatch(/mailto:/)
  })

  it('KRİTİK: ekran görüntüsü bölümü GÖSTERİLMEYEN bir şeyi vaat etmez', () => {
    // "mobil ve masaüstünde aynı arayüz" deniyordu; görsellerin tamamı telefon çerçevesinde.
    expect(soy(SHOTS_SRC)).not.toMatch(/mobil ve masaüstünde aynı arayüz/)
  })

  it('KRİTİK: indirme sayacı İÇ ÖLÇÜM diliyle konuşmaz', () => {
    const s = soy(STATS_SRC)
    expect(s).not.toMatch(/Benzersiz kullanıcı/)
    expect(s).not.toMatch(/bu yüzden toplanmazlar/)
  })

  it('KARŞIT-KANIT: KVKK’daki [REDACTED] ibaresi KALIR (sistem gerçekten böyle yazıyor)', () => {
    // Yazılım kayda birebir `[REDACTED]` yazıyor (servers/api_server.py, database/patient_database.py).
    // Metinden silmek belgeyi YANLIŞ yapardı; yapılması gereken tek şey ne olduğunu açıklamaktı.
    const s = soy(LEGAL_SRC)
    expect(s).toMatch(/REDACTED/)
    expect(s).toMatch(/REDACTED[\s\S]{0,240}(ibare|görün|yaz)/i)
  })
})
