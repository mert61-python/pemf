/**
 * TÜR GÜVENLİ ANAHTARLAR (T2): `t("…")` yalnız TR kataloğunda VAR olan anahtarı kabul eder → yanlış / eksik anahtar
 * `npm run typecheck`te kırmızı. Dinamik anahtar gerekiyorsa KURALLAR.md §Dinamik anahtar (tür eşlemesi + K-3 izin listesi).
 */
import "i18next";
import type { trKaynak } from "./kaynaklar";

declare module "i18next" {
  interface CustomTypeOptions {
    defaultNS: "translation";
    resources: { translation: typeof trKaynak };
    returnNull: false;
  }
}
