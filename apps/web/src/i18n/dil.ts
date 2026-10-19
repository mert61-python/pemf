/**
 * SİTE DİL SEÇİMİ (Y161, T3/T4) — saf kurallar (React / i18next İÇERMEZ).
 *
 * İlk ziyaret tarayıcı dilidir (`tr*` → tr, diğer → en); üst menüdeki dil düğmesiyle değişir ve bu tarayıcıda hatırlanır
 * (`localStorage` `pemf.dil` — uygulamayla aynı anahtar adı). Bayrak (`I18N_EN_ACIK`) KAPALIYKEN etkin dil HER ZAMAN tr ve düğme gizli.
 * `<html lang>` etkin dile eşitlenir (ekran okuyucu + arama motoru doğru dili görsün).
 */
import { I18N_EN_ACIK } from './bayrak'

export type Dil = 'tr' | 'en'
export const DIL_DEPO_ANAHTARI = 'pemf.dil'

let _bayrakTesti: boolean | null = null

/** YALNIZ TEST: bayrağı geçici açar / kapatır (`null` = gerçek bayrak). Üretim kodu ÇAĞIRMAZ — K-5 kapısı denetler. */
export function __bayrakTestiAyarla(v: boolean | null): void {
  _bayrakTesti = v
}

export function bayrakAcik(): boolean {
  return _bayrakTesti ?? I18N_EN_ACIK
}

export function gecerliDil(x: unknown): Dil | null {
  return x === 'tr' || x === 'en' ? x : null
}

export function dileIndirge(yerel: string | null | undefined): Dil {
  const s = String(yerel ?? '').trim().toLowerCase().replace(/_/g, '-')
  if (!s) return 'tr'
  return s === 'tr' || s.startsWith('tr-') ? 'tr' : 'en'
}

export function etkinDil(secim: unknown, yerel: string | null | undefined, enAcik: boolean = bayrakAcik()): Dil {
  if (!enAcik) return 'tr'
  return gecerliDil(secim) ?? dileIndirge(yerel)
}

export function dilSecimiGorunur(enAcik: boolean = bayrakAcik()): boolean {
  return enAcik
}

export function tarayiciYereli(): string | null {
  try {
    return globalThis.navigator?.language || null
  } catch {
    return null
  }
}

export function kayitliDil(): Dil | null {
  try {
    return gecerliDil(globalThis.localStorage?.getItem(DIL_DEPO_ANAHTARI))
  } catch {
    return null
  }
}

/** Seçimi bu tarayıcıya yazar; yazılamazsa (gizli pencere, kapalı depo) false. */
export function dilKaydet(d: Dil): boolean {
  try {
    globalThis.localStorage?.setItem(DIL_DEPO_ANAHTARI, d)
    return true
  } catch {
    return false
  }
}

/** `<html lang>` etkin dile eşitlenir (belge yoksa — SSR / test — sessizce geçilir). */
export function htmlDiliAyarla(d: Dil, belge: { documentElement?: { lang: string } } | undefined = globalThis.document): void {
  try {
    if (belge?.documentElement) belge.documentElement.lang = d
  } catch {
    /* yok say */
  }
}
