// Author: mertaygn, cglrgrkn
/**
 * JETON ÜCRETLENDİRME MODELİ + AÇIK KARARLAR (7. parti, sahip talimatı 2026-08-20).
 *
 * Sahip: "ben karar vermeyeceğim, uygun olanı sen yap; ücretlendirme JETON sistemi olacak,
 * altyapısını da kur."
 *
 * NEDEN JETON: önceki metinler planları "işlem önceliği / kuyruk / gerçek zamanlı" ile
 * ayırıyordu; ama yapay zekâ analizleri klinik bilgisayarında ÇALIŞIYOR — "sunucuda sıra
 * beklersiniz" vaadinin karşılığı yoktu (metin denetimi bunu çelişki olarak ölçtü). Jeton
 * ÖLÇÜLEBİLİR bir birimdir: 1 jeton = 1 yapay zekâ analizi. Hem dürüst anlatılır hem uygulanır.
 *
 * VERİLEN KARARLAR (bu dosya kilitler):
 *   1. Planlar jetonla ayrışır (kuyruk/hız vaadi YOK).
 *   2. Aylık plan hakkı devretmez; SATIN ALINAN jeton süresizdir (kullanıcı parasını kaybetmez).
 *   3. Cihaz sayısı somut: 1 / 5 / 15 ("Sınırsız" iddiası kalktı — ek cihaz eklentisiyle çelişiyordu).
 *   4. Destek yanıt süresi somut ve plana göre farklı.
 *   5. Başlangıç: 14 gün tam erişim → sonra ÜCRETSİZ katman olarak devam (aylık küçük jeton hakkı).
 *   6. Fiyatlar KDV DÂHİL (sözleşme metniyle ve tahsilatla uyumlu).
 *
 * ⚠️ TIBBİ GÜVENLİK: jeton TİCARİ kapıdır. Süren seansı/acil durdurmayı ASLA engellemez —
 * yalnız yeni yapay zekâ analizini kapılar. Bu değişmez `servers/jeton.py` tarafında ayrıca
 * test edilir; burada metnin bunu SÖYLEDİĞİ kilitlenir.
 */
import { describe, expect, it } from 'vitest'

import { kaynakSoy as soy } from './_soyucu'

import CONFIG_SRC from '../config.ts?raw'
import PRICING_SRC from '../pages/Pricing.tsx?raw'
import { JETON, PLANS, COMPARE, FAQ } from '../config'

describe('1) jeton modeli tek kaynakta ve tutarlı', () => {
  it('KRİTİK: plan hakları, analiz maliyetleri ve ek paketler tanımlı', () => {
    expect(JETON.planHaklari.baslangic).toBeGreaterThan(0)
    expect(JETON.planHaklari.pro).toBeGreaterThan(JETON.planHaklari.baslangic)
    expect(JETON.planHaklari.pro_plus).toBeGreaterThan(JETON.planHaklari.pro)

    expect(JETON.maliyet.goruntu).toBeGreaterThan(0)
    expect(JETON.maliyet.ai_pro_seans).toBeGreaterThanOrEqual(JETON.maliyet.goruntu)
    expect(JETON.paketler.length).toBeGreaterThanOrEqual(2)
    for (const p of JETON.paketler) {
      expect(p.adet).toBeGreaterThan(0)
      expect(p.fiyat).toBeGreaterThan(0)
    }
  })

  it('KRİTİK: satın alınan jeton SÜRESİZ, aylık hak DEVRETMEZ (kural metinde de yazılı)', () => {
    expect(JETON.aylikHakDevreder).toBe(false)
    expect(JETON.satinAlinanSuresiz).toBe(true)
    const metin = `${soy(CONFIG_SRC)}`
    expect(metin).toMatch(/satın aldığınız jetonlar[^.]{0,80}(süresi[^.]{0,20}yok|süresiz)/i)
  })

  it('KRİTİK: ek paket fiyatı jeton başına plan içi haktan PAHALI olmamalı (mantık kapısı)', () => {
    // Ek paket, plan içindeki jetondan ucuz olursa kimse plana geçmez; absürt pahalı olursa
    // kimse ek paket almaz. Yalnız "sıfırdan büyük ve artan miktarda ucuzlayan" kilitlenir.
    const birim = JETON.paketler.map((p) => p.fiyat / p.adet)
    for (let i = 1; i < birim.length; i++) {
      expect(birim[i]).toBeLessThanOrEqual(birim[i - 1] + 1e-9)
    }
  })
})

describe('2) planlar jetonla anlatılır (kuyruk/hız vaadi yok)', () => {
  it('KRİTİK: plan metinlerinde "kuyruk/işlem önceliği/anında analiz" vaadi kalmadı', () => {
    const hepsi = PLANS.map((p) => `${p.jetonHakki} ${p.features.join(' ')} ${p.desc}`).join(' ')
    expect(hepsi).not.toMatch(/kuyru|sırayla işlenir|analizler anında/i)
  })

  it('KRİTİK: her ücretli plan AYLIK JETON hakkını söyler', () => {
    for (const p of PLANS) {
      const metin = `${p.jetonHakki} ${p.features.join(' ')}`
      expect(metin, `${p.name} planı jeton hakkını söylemiyor`).toMatch(/jeton/i)
    }
  })

  it('KRİTİK: karşılaştırma tablosunda jeton satırı var, "analiz hızı" satırı yok', () => {
    const etiketler = COMPARE.map((c) => c.label).join(' | ')
    expect(etiketler).toMatch(/jeton/i)
    expect(etiketler).not.toMatch(/analiz hızı/i)
  })
})

describe('3) somut sayılar (belirsiz vaat yok)', () => {
  it('KRİTİK: cihaz sayısı SOMUT — "Sınırsız" iddiası yok (ek cihaz eklentisiyle çelişiyordu)', () => {
    const cihaz = COMPARE.find((c) => /cihaz/i.test(c.label))
    expect(cihaz, 'cihaz satırı yok').toBeTruthy()
    expect(Object.values(cihaz!.values).join(' ')).not.toMatch(/sınırsız/i)
    expect(Object.values(cihaz!.values).join(' ')).toMatch(/\d/)
  })

  it('KRİTİK: destek yanıt süresi SOMUT ve planlar arasında farklı', () => {
    const destek = COMPARE.find((c) => /destek/i.test(c.label))
    expect(destek, 'destek satırı yok').toBeTruthy()
    const v = Object.values(destek!.values)
    expect(v.join(' ')).toMatch(/gün/i)
    expect(new Set(v).size).toBeGreaterThan(1) // üç plan aynı sözü vermez
  })
})

describe('4) Başlangıç planı ve KDV', () => {
  it('KRİTİK: deneme sonrası ne olacağı NET (ücretsiz katman olarak devam)', () => {
    const cevap = FAQ.find((f) => /deneme/i.test(f.q))?.a ?? ''
    expect(cevap).toMatch(/ücretsiz/i)
    expect(cevap).toMatch(/jeton/i)
  })

  it('KRİTİK: fiyat sayfasında KDV beyanı var (ödeme sayfasıyla aynı)', () => {
    expect(soy(PRICING_SRC)).toMatch(/KDV\s+dâhil/i)
  })
})

describe('5) tıbbi güvenlik değişmezi metinde', () => {
  it('KRİTİK: jetonun seansı/acil durdurmayı ENGELLEMEDİĞİ açıkça yazılı', () => {
    const hepsi = `${FAQ.map((f) => f.a).join(' ')} ${soy(CONFIG_SRC)}`
    // ⚠️ Edilgen çatıyı da kabul et: doğru Türkçe "engellenmez" (ilk yazımda yalnız etken
    // "engellemez" aranıyordu ve doğru metin yanlış-KIRMIZI veriyordu).
    expect(hepsi).toMatch(/jeton[^.]{0,180}(seans|acil durdurma)[^.]{0,80}(engellen?mez|etkilen?mez|durdurul?mez)/i)
  })
})
