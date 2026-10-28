// Author: mertaygn, cglrgrkn
/**
 * D6.65 (B-7.16 · B-7.17 · B-7.31) — site tanıtım metinleri ürünün BUGÜNKÜ hâliyle aynı.
 *
 * 🔴 ÖLÇÜLEN (HEAD ebf1c3fe):
 *  (a) Ekran galerisi "Cihaz Kontrolü" açıklaması "8 bobin, frekans ve süre ayarı" / "8 coils …" (`i18n/*\/ekranlar.json`
 *      `ekran.kontrol.aciklama`). Ürün: STM32 7 bobin sürer (`apps/backend/servers/live_state.py` `STM_COIL_IDS = set(range(1, 8))`,
 *      firmware `NUM_COILS 7U`); 8. yuva ESP'dedir ve ESP KAPALI (Y37: site HEAD'i esas alır — 7 bobin STM; ESP'li karma kip ancak
 *      AÇIKÇA anılırsa 7 + 1 sayılabilir).
 *  (b) `FEATURES[0].icon = 'wifi'` ama `components/Icons.tsx` `ICONS`ta `wifi` yoktu → "Otomatik cihaz bağlantısı" kartı Ana sayfa ve
 *      Özellikler'de SİMGESİZ çiziliyordu (`Icon && …`).
 *  (c) Özellikler "Son güncelleme · v1.9.51" (`PATCH.version = CLIENT.version`, launcher) altında app 1.9.19 / mobil 2.3.20 notları
 *      (`icerik.surum.n1/n2`, 2026-08-22) duruyordu; launcher 1.9.51'in CHANGELOG bölümü bambaşka.
 *
 * ÖLÇÜT: (a) sayı backend topolojisinden türetilir (C2b: STM_COIL_IDS; ESP / karma / hibrit niteleyicisi varsa + ESP_COIL_IDS) — TR ve EN
 * kataloğunun TAMAMI taranır; (b) her `FEATURES[*].icon` `ICONS` anahtarı; (c) TR notun her biri CHANGELOG'un `## launcher <PATCH.version>`
 * bölümüyle en az bir 3 sözcüklük ifadeyi paylaşır (CHANGELOG ASCII Türkçe → iki taraf da harf-katlanır) ve bölümün tarihi sitedeki
 * sürüm tarihiyle aynı gün.
 */
import { describe, expect, it } from 'vitest'

import LIVE_STATE_SRC from '../../../backend/servers/live_state.py?raw'
import CHANGELOG_SRC from '../../../../CHANGELOG.md?raw'
import { EN, TR } from './_kaynakMetni'
import { FEATURES, PATCH } from '../config'
import { ICONS } from '../components/Icons'

function bobinTopolojisi(src: string): { stm: number; esp: number } {
  const stm = /^STM_COIL_IDS = set\(range\(1, (\d+)\)\)/m.exec(src)
  const esp = /^ESP_COIL_IDS = \{([\d, ]+)\}/m.exec(src)
  expect(stm, 'live_state.py STM_COIL_IDS tanımı bulunamadı — kapı bayat').not.toBeNull()
  expect(esp, 'live_state.py ESP_COIL_IDS tanımı bulunamadı — kapı bayat').not.toBeNull()
  return { stm: Number(stm![1]) - 1, esp: esp![1].split(',').filter((x) => x.trim()).length }
}

const KARMA = /\bESP\b|karma|hibrit|hybrid|mixed/i
/** "N bobin" / "N coils" (rakamla) — metindeki iddia edilen bobin sayıları. */
function bobinSayilari(metin: string): number[] {
  return [...metin.matchAll(/\b(\d+)\s*(?:bobin|coils?)\b/gi)].map((m) => Number(m[1]))
}

/** Türkçe harf katlama + noktalama temizliği (CHANGELOG ASCII yazımlı). */
export function katla(s: string): string[] {
  const harf: Record<string, string> = { ç: 'c', ğ: 'g', ı: 'i', i̇: 'i', ö: 'o', ş: 's', ü: 'u', â: 'a', î: 'i', û: 'u' }
  return s
    .replace(/İ/g, 'i')
    .replace(/I/g, 'ı')
    .toLowerCase()
    .replace(/[çğıöşüâîû]/g, (c) => harf[c] ?? c)
    .replace(/[^a-z0-9.]+/g, ' ')
    .split(' ')
    .map((w) => w.replace(/^\.+|\.+$/g, ''))
    .filter(Boolean)
}

function ucluler(s: string): Set<string> {
  const w = katla(s)
  const out = new Set<string>()
  for (let i = 0; i + 2 < w.length; i++) out.add(`${w[i]} ${w[i + 1]} ${w[i + 2]}`)
  return out
}

function changelogBolumu(md: string, baslik: string): { tarih: string; govde: string } | null {
  const satirlar = md.split(/\r?\n/)
  const bas = satirlar.findIndex((s) => s.startsWith(`## ${baslik} — `))
  if (bas < 0) return null
  const son = satirlar.findIndex((s, i) => i > bas && s.startsWith('## '))
  const tarih = /— (\d{4}-\d{2}-\d{2})/.exec(satirlar[bas])?.[1] ?? ''
  return { tarih, govde: satirlar.slice(bas, son < 0 ? undefined : son).join('\n') }
}

const AYLAR_TR = ['Oca', 'Şub', 'Mar', 'Nis', 'May', 'Haz', 'Tem', 'Ağu', 'Eyl', 'Eki', 'Kas', 'Ara']

describe('D6.65 (a) · site bobin sayısı backend topolojisiyle aynı', () => {
  const { stm, esp } = bobinTopolojisi(LIVE_STATE_SRC)

  it('ön koşul: topoloji okunur (7 STM + 1 ESP yuvası)', () => {
    expect(stm).toBeGreaterThan(0)
    expect(esp).toBeGreaterThanOrEqual(0)
  })

  it('KRİTİK: TR ve EN kataloğundaki her "N bobin / N coils" = STM bobin sayısı (karma kip AÇIKÇA anılıyorsa STM + ESP)', () => {
    const sorun: string[] = []
    for (const [dil, kat] of [['tr', TR], ['en', EN]] as const) {
      for (const [k, v] of Object.entries(kat)) {
        const izinli = KARMA.test(v) ? new Set([stm, stm + esp]) : new Set([stm])
        for (const n of bobinSayilari(v)) if (!izinli.has(n)) sorun.push(`${dil}:${k}: ${n} bobin — ${JSON.stringify(v)}`)
      }
    }
    expect(sorun, `ürün ${stm} bobini STM'den sürer (ESP kapalı; karma kip yalnız açıkça anılırsa ${stm + esp})`).toEqual([])
  })

  it('KARŞIT: desen "8 bobin"i yakalar; karma niteleyiciyle 7 + 1 geçer', () => {
    expect(bobinSayilari('8 bobin, frekans ve süre ayarı')).toEqual([8])
    expect(bobinSayilari('8 coils, frequency')).toEqual([8])
    expect(KARMA.test('7 STM + 1 ESP bobini (karma kip)')).toBe(true)
    expect(KARMA.test('7 bobin, frekans ve süre ayarı')).toBe(false)
  })
})

describe('D6.65 (b) · özellik kartı simgeleri çözülür', () => {
  it('KRİTİK: her FEATURES[*].icon ICONS anahtarı (kart simgesiz çizilmez)', () => {
    const eksik = FEATURES.map((f) => f.icon).filter((i) => !(i in ICONS))
    expect(eksik, `ICONS'ta olmayan simge(ler): ${eksik.join(', ')}`).toEqual([])
  })
})

describe('D6.65 (c) · "Son güncelleme" notları o sürümün CHANGELOG bölümünden', () => {
  const bolum = changelogBolumu(CHANGELOG_SRC, `launcher ${PATCH.version}`)

  it(`ön koşul: CHANGELOG'da "## launcher ${PATCH.version} — <tarih>" bölümü var ve tarihi sitedeki sürüm tarihiyle aynı gün`, () => {
    expect(bolum, `CHANGELOG.md'de launcher ${PATCH.version} bölümü yok`).not.toBeNull()
    const [y, a, g] = bolum!.tarih.split('-').map(Number)
    expect(TR['icerik.indir.surumTarihi'], 'sitedeki sürüm tarihi CHANGELOG bölümünün günü değil').toBe(`${g} ${AYLAR_TR[a - 1]} ${y}`)
  })

  it('KRİTİK: her TR sürüm notu o bölümle en az bir 3 sözcüklük ifadeyi paylaşır (başka sürümün notu DEĞİL)', () => {
    const kaynak = ucluler(bolum!.govde)
    const notlar = Object.entries(TR).filter(([k]) => /^icerik\.surum\.n\d+$/.test(k))
    expect(notlar.length, 'icerik.surum.n* notu bulunamadı — kapı bayat').toBeGreaterThan(0)
    const yabanci = notlar.filter(([, v]) => ![...ucluler(v)].some((u) => kaynak.has(u))).map(([k, v]) => `${k}: ${v}`)
    expect(yabanci, `launcher ${PATCH.version} bölümünde karşılığı olmayan not(lar)`).toEqual([])
  })

  it('KARŞIT: eski app 1.9.19 notu launcher bölümüyle eşleşmez; katlama Türkçe harfleri ASCII yazımla buluşturur', () => {
    const kaynak = ucluler(bolum!.govde)
    const eski = 'Güvenlik ve kayıt doğruluğu sürümü: bobin bir komutu reddederse artık ekranda sebebiyle görünür.'
    expect([...ucluler(eski)].some((u) => kaynak.has(u))).toBe(false)
    expect(katla('Kurulabilir paket varken görünür DEĞİŞİKLİK')).toEqual(['kurulabilir', 'paket', 'varken', 'gorunur', 'degisiklik'])
  })
})
