/** TÜR GÜVENLİ ANAHTARLAR (site): `t("…")` yalnız TR kataloğunda VAR olan anahtarı kabul eder → yanlış anahtar `tsc -b`de kırmızı. */
import 'i18next'
import type { trKaynak } from './kaynaklar'

declare module 'i18next' {
  interface CustomTypeOptions {
    defaultNS: 'translation'
    resources: { translation: typeof trKaynak }
    returnNull: false
  }
}
