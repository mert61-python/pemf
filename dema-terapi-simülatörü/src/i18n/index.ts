/**
 * DEMA SİMÜLATÖRÜ ÇOK DİLLİLİK (I18N · Y159) — EN BASİT GÜVENLİ YOL: i18next YOK (simülatör tek sayfa, ~80 metin, dil sayfa içinde
 * değişmez). Katalog `src/i18n/{tr,en}.json` — öteki yüzeylerle AYNI biçim (i18next JSON v4: iç içe anahtar, `{{ad}}`), AYNI kapılar.
 *
 * Dil: simülatörü açan uygulama dili URL'de `?dil=tr|en` olarak verir (iframe / WebView başlık taşıyamaz; `apiClient.dilParametresiEkle`)
 * ve dil değişince çerçeveyi yeniden yükler. Parametre yoksa tarayıcı dili (`tr*` → tr, diğer → en). Bayrak (`I18N_EN_ACIK`) KAPALIYKEN
 * her zaman tr. Eksik anahtar: Türkçe değere, o da yoksa anahtara düşer (boş metin yok); K-1 iki dilin anahtar eşliğini denetler.
 */
import tr from './tr.json';
import en from './en.json';
import { I18N_EN_ACIK } from './bayrak';

export type Dil = 'tr' | 'en';

type Yollar<T, O extends string = ''> = {
  [K in keyof T & string]: T[K] extends string ? `${O}${K}` : Yollar<T[K], `${O}${K}.`>;
}[keyof T & string];
export type Anahtar = Yollar<typeof tr>;

export function dileIndirge(yerel: string | null | undefined): Dil {
  const s = String(yerel ?? '').trim().toLowerCase().replace(/_/g, '-');
  if (!s) return 'tr';
  return s === 'tr' || s.startsWith('tr-') ? 'tr' : 'en';
}

export function etkinDil(parametre: string | null, yerel: string | null | undefined, enAcik: boolean = I18N_EN_ACIK): Dil {
  if (!enAcik) return 'tr';
  return parametre === 'tr' || parametre === 'en' ? parametre : dileIndirge(yerel);
}

function bul(kok: unknown, anahtar: string): string | undefined {
  let x: unknown = kok;
  for (const parca of anahtar.split('.')) {
    if (x && typeof x === 'object' && parca in (x as Record<string, unknown>)) x = (x as Record<string, unknown>)[parca];
    else return undefined;
  }
  return typeof x === 'string' ? x : undefined;
}

function sayfaDili(): Dil {
  try {
    return etkinDil(new URLSearchParams(globalThis.location?.search ?? '').get('dil'), globalThis.navigator?.language);
  } catch {
    return 'tr';
  }
}

export const DIL: Dil = sayfaDili();

/** Anahtar → metin (sayfa dilinde). `{{ad}}` yer tutucular `p`'den. */
export function t(anahtar: Anahtar, p?: Record<string, string | number>, dil: Dil = DIL): string {
  const m = bul(dil === 'en' ? en : tr, anahtar) ?? bul(tr, anahtar) ?? anahtar;
  return p ? m.replace(/\{\{\s*(\w+)\s*\}\}/g, (_x, ad: string) => (p[ad] === undefined ? '' : String(p[ad]))) : m;
}
