// Author: mertaygn, cglrgrkn
/**
 * SADE DİL — kullanıcı-dostuluk denetimi 2. parti (2026-08-20).
 *
 * Hedef kitle veteriner hekim / klinik sahibi; yazılımcı DEĞİL. Derin tarama sitede aynı tek
 * indirilebilir dosya için BEŞ ayrı ad (client · İstemci · Launcher · PEMF Vet Client · hafif
 * kurulum) ve onlarca çevrilmemiş teknik terim ölçtü.
 *
 * KARAR (sahip onayı 2026-08-20):
 *   · Butonlar/başlıklar ARA KATMAN ADI KULLANMAZ → "PEMF Vet'i İndir". Kullanıcı uygulamayı
 *     indirir; mimariyi öğrenmek zorunda değildir (Steam/WhatsApp de anlatmaz).
 *   · Süreci anlatmak GEREKEN yerlerde (kurulum adımları, SSS) TEK ad: "başlatıcı".
 *   · İngilizce terimlerin Türkçesi kullanılır; kısaltmalar ilk geçtiği yerde açılır.
 *
 * ⚠️ `CLIENT` KOD TANIMLAYICISI kapsam DIŞI: config export adıdır, ekranda görünmez; yeniden
 * adlandırmak indirme adresleri/testleriyle ilgisiz bir kırılma riski olurdu. Kapılar yalnız
 * KULLANICIYA GÖRÜNEN metni ölçer.
 * ⚠️ YORUMLAR SOYULUR (bkz. metin-guveni.test.ts aynı gerekçe).
 */
import { describe, expect, it } from 'vitest'

import { kaynakSoy } from './_soyucu'

import HOME_SRC from '../pages/Home.tsx?raw'
import DOWNLOAD_SRC from '../pages/Download.tsx?raw'
import FEATURES_SRC from '../pages/Features.tsx?raw'
import PRICING_SRC from '../pages/Pricing.tsx?raw'
import SUPPORT_SRC from '../pages/Support.tsx?raw'
import ODEME_SRC from '../pages/Odeme.tsx?raw'
import LEGAL_SRC from '../pages/Legal.tsx?raw'
import HEADER_SRC from '../components/Header.tsx?raw'
import PACKAGE_SRC from '../components/PackageBuilder.tsx?raw'
import BUTTONS_SRC from '../components/DownloadButtons.tsx?raw'
import SHOTS_SRC from '../components/AppScreenshots.tsx?raw'
import MOCK_SRC from '../components/LauncherMock.tsx?raw'
import CONFIG_SRC from '../config.ts?raw'

/** ⚠️ ORTAK, STRING-BİLİNÇLİ soyucu: naif sürüm satır-SONU yorumlarını kaçırıyordu
 *  (`windowsTag: '…', // … client … Ev Sahibi …`) ve kapılar geliştirici notunu ekran metni
 *  sanıp yanlış-KIRMIZI yanıyordu — ilk koşuda ölçüldü. Bkz. `_soyucu.ts`. */
const soy = kaynakSoy

const EKRANLAR: ReadonlyArray<readonly [string, string]> = [
  ['Home', HOME_SRC],
  ['Download', DOWNLOAD_SRC],
  ['Features', FEATURES_SRC],
  ['Pricing', PRICING_SRC],
  ['Support', SUPPORT_SRC],
  ['Odeme', ODEME_SRC],
  ['Header', HEADER_SRC],
  ['PackageBuilder', PACKAGE_SRC],
  ['DownloadButtons', BUTTONS_SRC],
  ['AppScreenshots', SHOTS_SRC],
  ['LauncherMock', MOCK_SRC],
  ['config', CONFIG_SRC],
]

/** Her ekranda deseni arar; eşleşen ekran adlarını döndürür (hata mesajı işe yarasın). */
function nerede(desen: RegExp): string[] {
  return EKRANLAR.filter(([, src]) => desen.test(soy(src))).map(([ad]) => ad)
}

// ─────────────────────────────── Adlandırma ───────────────────────────────

describe('adlandırma: tek ürün, tek ad', () => {
  it('KRİTİK: "client / Client\'ı / client içinden" kullanıcı metninde GEÇMEZ', () => {
    // Beş ayrı ad kullanıcıya beş ayrı şeymiş gibi görünüyordu.
    expect(nerede(/[Cc]lient['’]/)).toEqual([])
    expect(nerede(/client içinden/i)).toEqual([])
    expect(nerede(/hafif client/i)).toEqual([])
  })

  it('KRİTİK: "İstemci(yi)" ve "Launcher" ekran metninde GEÇMEZ', () => {
    expect(nerede(/İstemciyi İndir/)).toEqual([])
    expect(nerede(/tek istemci/i)).toEqual([])
    expect(nerede(/>\s*Launcher\s*</)).toEqual([])
    // Yasal belgeler de aynı adı kullanır (sözleşmede "istemcisi" yazıyordu).
    expect(soy(LEGAL_SRC)).not.toMatch(/sitesi, istemcisi/)
  })

  it('KRİTİK: indirme çağrıları ÜRÜN adını kullanır ("PEMF Vet\'i İndir")', () => {
    expect(soy(HEADER_SRC)).toMatch(/PEMF Vet['’]i İndir/)
  })

  it('KARŞIT-KANIT: süreci anlatan yerlerde TEK ara-katman adı "başlatıcı" KULLANILIR', () => {
    // Aşırı-sadeleştirme koruması: adı tamamen silmek, "indirdiğim küçük program neydi?"
    // sorusunu cevapsız bırakırdı. Kurulum adımları + SSS bunu bir kez tanımlar.
    const cfg = soy(CONFIG_SRC)
    expect(cfg).toMatch(/başlatıcı/i)
    expect(cfg).toMatch(/PEMFVetClient-Setup/) // indirilen dosyanın GERÇEK adı SSS'te durur
  })

  it('KARŞIT-KANIT: `CLIENT` kod tanımlayıcısı DURUYOR (indirme adresleri ona bağlı)', () => {
    expect(soy(CONFIG_SRC)).toMatch(/export const CLIENT/)
  })
})

// ─────────────────────────────── Jargon ───────────────────────────────

describe('jargon: Türkçe karşılık', () => {
  it('KRİTİK: "Real-time" ekranda geçmez (aynı sayfada Türkçesi de kullanılıyordu)', () => {
    expect(nerede(/Real-time/)).toEqual([])
  })

  it('KRİTİK: kısaltmalar açıklamasız BIRAKILMAZ (DB · KPI · SLA · FGS · KIRC · CKD)', () => {
    const cfg = soy(CONFIG_SRC)
    expect(cfg).not.toMatch(/Hasta DB/)
    expect(cfg).not.toMatch(/\bKPI\b/)
    expect(cfg).not.toMatch(/\+ SLA|· SLA/)
    // Bilimsel kısaltmalar KALABİLİR ama yanında Türkçe açıklama olmalı.
    // ⚠️ İlk yazımda açıklama yalnız kısaltmadan SONRA aranıyordu; oysa doğal Türkçede açıklama
    // ÖNCE gelir ("Kedide yüz ifadesinden ağrı skoru (FGS)") — kapı yanlış-KIRMIZI veriyordu.
    // Ölçüt artık: kısaltmayı içeren SATIRDA yeterli Türkçe açıklama bulunması.
    for (const k of ['FGS', 'KIRC', 'CKD']) {
      for (const satir of cfg.split('\n')) {
        if (!satir.includes(k)) continue
        const turkceHarf = (satir.match(/[a-zçğıöşü]/g) ?? []).length
        expect(turkceHarf).toBeGreaterThan(25)
      }
    }
  })

  it('KRİTİK: geliştirici argosu ekranda geçmez (next-next · setup · Dashboard · watchdog · SHA-256)', () => {
    expect(nerede(/next-next/i)).toEqual([])
    expect(nerede(/setup['’]?ı tamamlar/i)).toEqual([])
    expect(nerede(/Dashboard/)).toEqual([])
    expect(nerede(/watchdog/i)).toEqual([])
    expect(nerede(/SHA-256/)).toEqual([])
  })

  it('KRİTİK: profil adı "Ev Sahibi" DEĞİL "Evcil Hayvan Sahibi" (mülk sahibi çağrışımı)', () => {
    // Kayıt formu zaten "Evcil Hayvan Sahibi" diyordu; kurulum profili "Ev Sahibi" diyordu.
    // ⚠️ İlk kapı yalnız üç KALIBI arıyordu ('Ev Sahibi' / >Ev Sahibi< / Ev Sahibi,) ve
    // 'Ev Sahibi profili · 1 cihaz' gibi altı kullanım kaçtı — düzeltmenin kendisi bunu
    // ortaya çıkardı. Artık "Evcil Hayvan " ile başlamayan HER geçiş yakalanır.
    expect(nerede(/(?<!Evcil Hayvan )Ev Sahibi/)).toEqual([])
    expect(soy(CONFIG_SRC)).toMatch(/Evcil Hayvan Sahibi/)
  })

  it('KRİTİK: "AI Pro"nun NE YAPTIĞI en az bir yerde tanımlanır (klinik risk algısı)', () => {
    // Yasal sorumluluk metninde bile geçen özelliğin ne olduğu hiçbir sayfada yazmıyordu.
    const cfg = soy(CONFIG_SRC)
    expect(cfg).toMatch(/AI Pro/)
    expect(cfg).toMatch(/sensör(den| geri)[^.'"]{0,120}(otomat|kendi)/i)
  })

  it('KARŞIT-KANIT: ürün/marka adları SİLİNMEZ (PEMF · AI Pro · iyzico gerekli terimler)', () => {
    // Aşırı-sadeleştirme yönü: her İngilizce sözcüğü atmak marka ve zorunlu sağlayıcı adını da
    // silerdi. Bunlar KALIR.
    expect(soy(CONFIG_SRC)).toMatch(/PEMF/)
    expect(soy(ODEME_SRC)).toMatch(/iyzico/)
  })
})

// ─────────────────────────────── Tutarlılık ───────────────────────────────

describe('tutarlılık: aynı şeye tek ad', () => {
  it('KRİTİK: "seviye" satın-alma metninde kullanılmaz (plan ile karışıyordu)', () => {
    expect(nerede(/[Ss]eviye karşılaştırması|seviyeye \(|Seviyeye dahil/)).toEqual([])
  })

  it('KRİTİK: "parola" ve "şifre" karışık kullanılmaz — tek terim "şifre"', () => {
    expect(nerede(/[Pp]arola/)).toEqual([])
  })
})
