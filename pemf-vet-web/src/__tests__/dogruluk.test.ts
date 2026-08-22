// Author: mertaygn, cglrgrkn
/**
 * METİN DOĞRULUĞU — adversaryal inceleme düzeltmeleri (6. parti, 2026-08-20).
 *
 * Dört partilik metin turundan sonra bağımsız bir inceleme, YENİ metinlerde de kusur buldu.
 * Bu dosya, ölçülebilir OLGU iddialarını kilitler — "güzel cümle" değil, DOĞRU cümle.
 *
 * Kilitlenen olgular:
 *  1. Telefon uygulamasının rolü: uygulama bobin sürebiliyor (pf/src/screens/ControlScreen.tsx,
 *     components/domain/CoilParameterPanel.tsx, hooks/useSessionControl.ts) → 5. partide yazdığım
 *     "telefon tek başına terapi uygulamaz / cihazı sürmek için masaüstü gerekir" ifadesi YANLIŞTI.
 *  2. Abonelik iptalinde "ödediğiniz dönemin sonuna kadar erişim" vaadi: `api/cancel.ts` bunu
 *     ÖLÇÜP ÇÜRÜTÜYOR (`current_period_end` hiçbir yol tarafından yazılmıyor; hak katmanları
 *     yalnız `status`e bakıyor). Tutulamayacak vaat metinden çıkar.
 *  3. Desteklenen platform listesi: `macosReady/linuxReady = false` → indirilemeyen platform
 *     "destekleniyor" gibi sunulamaz; indirilebilen Android ise listeden düşmez.
 *  4. Ücretsiz dönemde fiyat gösterilmez (kural ana sayfada uygulanmıştı, fiyat sayfasında değil).
 *  5. Ham sağlayıcı (iyzico) hata metni ekrana basılmaz — auth tarafındaki kuralın aynısı.
 *  6. Metinden çıkarılan bir iddia SİMGE olarak da durmamalı (Bluetooth logosu).
 */
import { describe, expect, it } from 'vitest'

import { kaynakSoy as soy } from './_soyucu'

import CONFIG_SRC from '../config.ts?raw'
import PRICING_SRC from '../pages/Pricing.tsx?raw'
import ODEME_SRC from '../pages/Odeme.tsx?raw'
import ACCOUNT_SRC from '../components/AccountButton.tsx?raw'
import HOME_SRC from '../pages/Home.tsx?raw'
import { FAQ, CLIENT, FEATURES, PLANS } from '../config'
import { planFiyatGorunumu, planKisaFiyat } from '../lib/planFiyat'

describe('1) telefon uygulamasının rolü DOĞRU anlatılır', () => {
  it('KRİTİK: "telefon cihazı süremez" gibi YANLIŞ bir sınır iddia edilmez', () => {
    const s = soy(CONFIG_SRC)
    expect(s).not.toMatch(/telefon tek başına terapi uygulamaz/i)
    expect(s).not.toMatch(/Cihazı sürmek için masaüstü uygulaması gerekir/i)
  })

  it('KRİTİK: telefonun GERÇEK yeteneği yazılır (seans + bobin ayarı + izleme)', () => {
    const cevap = FAQ.find((f) => /telefon uygulaması/i.test(f.q))?.a ?? ''
    expect(cevap).toMatch(/seans/i)
    expect(cevap).toMatch(/bobin|ayar/i)
    // Doğru olan sınır: cihaz klinikteki bilgisayara bağlıdır, telefon ona UZAKTAN bağlanır.
    expect(cevap).toMatch(/klinikteki bilgisayar|aynı ağ|uzaktan/i)
  })
})

describe('2) tutulamayacak vaat yok', () => {
  it('KRİTİK: iptal sonrası "dönem sonuna kadar erişim" vaadi verilmez (ölçülmüş: tutmuyor)', () => {
    const hepsi = `${FAQ.map((f) => f.a).join(' ')} ${soy(ACCOUNT_SRC)}`
    expect(hepsi).not.toMatch(/dönem(in)? sonuna kadar erişim/i)
  })

  it('KARŞIT-KANIT: iptalin GERÇEK etkisi (yenilemenin durması) söylenmeye devam eder', () => {
    const hepsi = `${FAQ.map((f) => f.a).join(' ')} ${soy(ACCOUNT_SRC)}`
    expect(hepsi).toMatch(/yenileme/i)
  })
})

describe('3) platform listesi tutarlı', () => {
  it('KRİTİK: indirilemeyen platform "destekleniyor" diye sunulmaz', () => {
    // Ana sayfa rozetleri ve SSS, indirme kapısının gerçeğiyle uyumlu olmalı.
    expect(CLIENT.downloads.macos.ready).toBe(false)
    expect(CLIENT.downloads.linux.ready).toBe(false)
    const home = soy(HOME_SRC)
    expect(home).not.toMatch(/CLIENT\.downloads\.macos\.os/)
    const os = FAQ.find((f) => /işletim sistem/i.test(f.q))?.a ?? ''
    expect(os).toMatch(/hazırlan|yakında/i)
    expect(os).toMatch(/Android/i) // indirilebilen platform listeden düşmemeli
  })

  it('KRİTİK: özellik kartı Linux’u ÇALIŞIYOR gibi göstermez', () => {
    const platform = FEATURES.find((f) => /platform|güvenlik/i.test(f.title))?.desc ?? ''
    const hepsi = FEATURES.map((f) => f.desc).join(' ')
    expect(`${platform} ${hepsi}`).not.toMatch(/Windows ve Linux['’]ta tek uygulama/)
  })
})

describe('4) ücretsiz dönemde fiyat', () => {
  it('KRİTİK: fiyat sayfası da FREE_MODE kuralına uyar (ana sayfayla aynı)', () => {
    // ⚠️ ÖLÇÜ GÜÇLENDİRİLDİ (8. parti) — GEVŞETME DEĞİL: eskiden yalnız "Pricing.tsx içinde
    // `priceView` adlı bir şey var mı" diye bakıyordu. O fonksiyon src/lib/planFiyat.ts'e taşındı,
    // çünkü ana sayfa AYNI hesabı ikinci kez yazıyordu ve ikisi ayrışmıştı (kullandıkça-öde planı
    // birinde "test sonrası ₺0/ay", ötekinde "₺0/ay" görünüyordu). Test artık isim aramıyor;
    // (a) iki sayfanın da ORTAK kaynağı çağırdığını, (b) ücretsiz dönemde rakam yerine DURUM
    // yazıldığını davranış olarak ölçüyor.
    expect(soy(PRICING_SRC), 'fiyat sayfası ortak fiyat kaynağını çağırmıyor').toMatch(
      /planFiyatGorunumu/,
    )
    expect(soy(HOME_SRC), 'ana sayfa ortak fiyat kaynağını çağırmıyor').toMatch(/planKisaFiyat/)
    const pro = PLANS.find((p) => p.tier === 'pro')!
    expect(planFiyatGorunumu(pro, true).buyuk).toMatch(/ücretsiz/i)
    expect(planKisaFiyat(pro)).toMatch(/ücretsiz/i)
  })
})

describe('5) ham sağlayıcı hatası', () => {
  it('KRİTİK: iyzico’nun ham mesajı kullanıcıya basılmaz (auth kuralının aynısı)', () => {
    const s = soy(ODEME_SRC) + soy(ACCOUNT_SRC)
    expect(s).toMatch(/odemeHatasiTurkce/)
  })
})

describe('6) metinden çıkarılan iddia SİMGEDE de durmaz', () => {
  it('KRİTİK: "otomatik cihaz bağlantısı" kartı Bluetooth simgesi kullanmaz (üründe BLE yok)', () => {
    const kart = FEATURES.find((f) => /Cihaz Bağlantısı/i.test(f.title))
    expect(kart, 'bağlantı kartı bulunamadı').toBeTruthy()
    expect(kart!.icon).not.toBe('bluetooth')
  })
})
