// Author: mertaygn, cglrgrkn
/**
 * SİTE METİN GÜVENİ — kullanıcı-dostuluk denetimi 1. parti (2026-08-20).
 *
 * Derin metin taraması (iki bağımsız mercek: jargon + anlaşılırlık) sitede YAYINDA olan yedi
 * "güven zedeleyen" kalem ölçtü. Bu dosya onların HER BİRİNİ kilitler — düzeltmeler metin
 * olduğu için tek koruma budur; biri geri gelirse burada kırmızı yanar.
 *
 * ⚠️ YORUMLAR SOYULUR: bu deponun dört kez düştüğü tuzak — düzeltmenin kendi gerekçesi eski
 * hatalı metni aynen anlatır; soyulmazsa kapı kendi açıklamasını görüp yanlış-KIRMIZI verir
 * (bkz. odeme-donem-bedeli.test.ts aynı not).
 * ⚠️ DOM YOK: bu depoda jsdom ortamı yok → bileşen render edilip ekran okunamaz; ölçülen şey
 * kaynak metnin KENDİSİDİR. Davranışsal olabilen tek parça (hata çevirisi) gerçekten koşturulur.
 */
import { describe, expect, it } from 'vitest'

import { kaynakSoy } from './_soyucu'

import LEGAL_SRC from '../pages/Legal.tsx?raw'
import ODEME_SRC from '../pages/Odeme.tsx?raw'
import HOME_SRC from '../pages/Home.tsx?raw'
import PRICING_SRC from '../pages/Pricing.tsx?raw'
import AUTHMODAL_SRC from '../context/AuthModal.tsx?raw'
import AUTHCTX_SRC from '../context/AuthContext.tsx?raw'
import RESET_SRC from '../pages/ResetPassword.tsx?raw'
import CONFIG_SRC from '../config.ts?raw'
import DOWNLOAD_SRC from '../pages/Download.tsx?raw'

import { authHatasiTurkce, SIFRE_KURALI, sifreGecerliMi } from '../lib/authHatalari'

/** Blok + satır yorumları soyulmuş kaynak (ortak, string-bilinçli soyucu — bkz. `_soyucu.ts`). */
const soy = kaynakSoy

// ─────────────────────────────── 1) Yasal şablon uyarısı ───────────────────────────────

describe('1) yasal belgelerdeki İÇ NOT', () => {
  it('KRİTİK: "şablondur / hukuk danışmanınca gözden geçirilmeli" uyarısı YAYINDA GÖRÜNMEZ', () => {
    // Yedi yasal belgenin (Mesafeli Satış, KVKK, Gizlilik…) EN ÜSTÜNDE müşteriye gösteriliyordu.
    // Satın alma öncesi sözleşme sayfasında "bu metin taslak" demek güveni doğrudan bitirir.
    const s = soy(LEGAL_SRC)
    expect(s).not.toMatch(/şablondur/i)
    expect(s).not.toMatch(/hukuk danışmanınca gözden geçirilmeli/i)
  })
})

// ─────────────────────────────── 2) KDV çelişkisi ───────────────────────────────

describe('2) KDV beyanı', () => {
  it('KRİTİK: ödeme sayfası "KDV dâhil DEĞİLDİR" demez (sözleşme + tahsilat davranışı bunun tersi)', () => {
    // Sözleşmeler (Mesafeli Satış md. 4 / Ön Bilgilendirme) "tüm vergiler (KDV) dâhil toplam
    // bedel sipariş özetinde gösterilen tutardır" diyor; api/checkout.ts ise listedeki tutarı
    // OLDUĞU GİBİ iyzico'ya geçiyor (hiçbir yerde vergi eklenmiyor) → "dâhil değildir" cümlesi
    // hem sözleşmeyle hem sistemin kendi davranışıyla çelişiyordu.
    expect(soy(ODEME_SRC)).not.toMatch(/KDV\s+dâhil\s+değildir/i)
  })

  it('KARŞIT-KANIT: sözleşmedeki "KDV dâhil toplam bedel" ifadesi DURUYOR (çapa)', () => {
    expect(soy(LEGAL_SRC)).toMatch(/vergiler\s*\(KDV\)\s*dâhil/i)
  })
})

// ─────────────────────────────── 3) Ücretsiz/ücretli çelişkisi ───────────────────────────────

describe('3) FREE_MODE tutarlılığı', () => {
  it('KRİTİK: ana sayfa fiyatları KODA GÖMMEZ — tek kaynak config (FREE_MODE ile çelişemesin)', () => {
    // Fiyat sayfası "tüm planlar şu an ücretsiz" derken ana sayfa ₺990 / ₺1.990 basıyordu:
    // iki sayfa birbirini yalanlıyordu. Fiyat artık config'ten gelir ve FREE_MODE'da gizlenir.
    const s = soy(HOME_SRC)
    expect(s).not.toMatch(/₺990/)
    expect(s).not.toMatch(/₺1\.990/)
    expect(s).toMatch(/FREE_MODE/)
  })

  it('KRİTİK: test-aşaması bandı VAR OLMAYAN buton adına atıf yapmaz', () => {
    // Bant '"Seç" butonları' diyordu; sayfadaki etiketler "Denemeyi Başlat" / "Pro'yu Seç" /
    // "Pro+'ya Yükselt" — kullanıcı tarif edilen düğmeyi bulamıyordu.
    expect(soy(PRICING_SRC)).not.toMatch(/"Seç" butonları/)
  })
})

// ─────────────────────────────── 4) Ham İngilizce hata mesajları ───────────────────────────────

describe('4) hata mesajları', () => {
  it('KRİTİK: Supabase hataları HAM İngilizce basılmaz — çeviri katmanından geçer', () => {
    // `return { error: error?.message }` ile "Invalid login credentials" / "User already
    // registered" doğrudan ekrana çıkıyordu.
    const s = soy(AUTHCTX_SRC)
    expect(s).toMatch(/authHatasiTurkce/)
    expect(s).not.toMatch(/error:\s*error\?\.message/)
  })

  it('DAVRANIŞSAL: gerçek Supabase metinleri Türkçe ve EYLEM SÖYLEYEN karşılığa çevrilir', () => {
    const c = authHatasiTurkce('Invalid login credentials')
    expect(c).toMatch(/e-posta|şifre/i)
    expect(c).not.toMatch(/invalid|credentials/i)

    expect(authHatasiTurkce('Email not confirmed')).toMatch(/doğrula/i)
    expect(authHatasiTurkce('User already registered')).toMatch(/kayıtlı/i)
    expect(authHatasiTurkce('Password should be at least 6 characters')).toMatch(/şifre/i)
    expect(authHatasiTurkce('For security purposes, you can only request this after 60 seconds')).toMatch(/saniye|bekle/i)
  })

  it('KARŞIT-KANIT: bilinmeyen hata YUTULMAZ — genel ama Türkçe bir karşılık döner', () => {
    // Aşırı-düzeltme koruması: tanınmayan mesajı boş/undefined döndürmek hatayı görünmez yapardı.
    const c = authHatasiTurkce('some brand new supabase failure xyz')
    expect(c.length).toBeGreaterThan(10)
    expect(c).toMatch(/[çğıöşüÇĞİÖŞÜ]/)
  })

  it('KRİTİK: giriş penceresi GELİŞTİRİCİ değişken adı sızdırmaz (VITE_SUPABASE_*)', () => {
    expect(soy(AUTHMODAL_SRC)).not.toMatch(/VITE_SUPABASE/)
  })
})

// ─────────────────────────────── 5) Şifre kuralı ───────────────────────────────

describe('5) şifre kuralı', () => {
  it('KRİTİK: kayıt ve şifre-yenileme AYNI kuralı uygular (6 vs 8 çelişkisi)', () => {
    // Kayıtta kabul edilen 6 karakterlik şifre, sıfırlama ekranında reddediliyordu.
    expect(SIFRE_KURALI.minUzunluk).toBe(8)
    expect(sifreGecerliMi('abc123')).toBe(false)
    expect(sifreGecerliMi('Abcdef12')).toBe(true)

    const modal = soy(AUTHMODAL_SRC)
    expect(modal).toMatch(/sifreGecerliMi|SIFRE_KURALI/)
    expect(modal).not.toMatch(/en az 6 karakter/)
    expect(soy(RESET_SRC)).toMatch(/sifreGecerliMi|SIFRE_KURALI/)
  })

  it('KARŞIT-KANIT: GİRİŞ yolunda katı kural DAYATILMAZ (eski 6 haneli şifreler kilitlenmesin)', () => {
    // Aşırı-düzeltme yönü: aynı alan hem giriş hem kayıt için kullanılıyor; girişte istemci
    // tarafı uzunluk dayatmak mevcut kullanıcıları kendi hesabından kilitlerdi.
    const modal = soy(AUTHMODAL_SRC)
    expect(modal).toMatch(/isSignup\s*&&|mode === 'signup'/)
  })
})

// ─────────────────────────────── 6) Türkçe karaktersiz metin ───────────────────────────────

describe('6) yama notları', () => {
  it('KRİTİK: "Son güncelleme" notları TÜRKÇE KARAKTERLİ yazılır (ASCII bakımsızlığı)', () => {
    // Ekranda "Bakim surumu: guncelleme altyapisi uctan uca dogrulandi" görünüyordu.
    // ⚠️ İlk yazımda anahtar adı yanlıştı (`patchNotes`); gerçek kaynak `PATCH = { notes: [...] }`.
    const notlar = soy(CONFIG_SRC).match(/export const PATCH[\s\S]{0,900}?as const/)?.[0] ?? ''
    expect(notlar.length).toBeGreaterThan(80)
    expect(notlar).not.toMatch(/guncelleme|surum[uü]?\b|degisiklik|dogrulan/i)
    expect(notlar).toMatch(/[çğıöşüÇĞİÖŞÜ]/)
  })
})

// ─────────────────────────────── 7) Sürüm karmaşası ───────────────────────────────

describe('7) sürüm gösterimi', () => {
  it('KRİTİK: ana sayfada İKİ FARKLI sürüm şeması yan yana durmaz', () => {
    // Hero'da aynı anda "Sürüm 2026.1 · Yayında" (channel) ve "v1.9.32" (version) görünüyordu.
    const s = soy(HOME_SRC)
    expect(s).not.toMatch(/CLIENT\.channel/)
  })

  it('KRİTİK: Android kartındaki AYRI sürüm numarası EKRANDA açıklanır (1.9.32 ↔ 2.3.18)', () => {
    // İki kart iki çok farklı sürüm gösteriyordu; sebebi hiçbir yerde yazmıyordu.
    // ⚠️ Yalnız config'te bir alan bulunması YETMEZ — sayfanın onu BASTIĞI da kilitlenir,
    // aksi halde açıklama tanımlanır ama kullanıcı yine göremezdi.
    const not = soy(CONFIG_SRC).match(/androidVersionNote:\s*'([^']+)'/)?.[1] ?? ''
    expect(not.length).toBeGreaterThan(30)
    expect(not).toMatch(/ayrı|bağımsız/i)
    expect(soy(DOWNLOAD_SRC)).toMatch(/androidVersionNote/)
  })
})
