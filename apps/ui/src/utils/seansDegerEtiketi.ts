// Author: mertaygn, cglrgrkn
/**
 * SEANS DEĞERLERİ → GÖRÜNEN AD (I18N-P1 kapanış taraması).
 *
 * `mode` ("Manuel" | "Otomatik" | "AI") ve `target_condition` (`AUTO_TARGETS` değerleri) seansa / literatür aramasına GİDEN ve DB'ye yazılan
 * VERİdir — Türkçe kalır, dil değişince DEĞİŞMEZ. Ekrana basılırken (geçmiş kartı, seans detayı, aktif seans kartı, ana ekran, KPI mod
 * dağılımı) değer → katalog anahtarı ile çevrilir; bilinmeyen değer (serbest metin, eski kayıt, "AI") AYNEN gösterilir.
 * Python karşılığı: `apps/backend/utils/seans_durum.py::mod_etiketi / hedef_etiketi` (PDF + CSV) — tablolar
 * `tests/test_seans_mod_hedef_etiketi_P1.py` ile ANAHTAR ANAHTAR karşılaştırılır.
 */
import type { TFunction } from "i18next";

/** Hedef durumunun GÖRÜNEN adı. ⚠️ Değer (TR) `targetCondition` olarak seansa / literatür aramasına (auto_preset) GİDER → DEĞİŞMEZ. */
export const hedefEtiketi = (t: TFunction, hedef: string): string => {
  switch (hedef) {
    case "Doku İyileşmesi": return t("kontrol.hedef.dokuIyilesmesi");
    case "Eklem Ağrısı": return t("kontrol.hedef.eklemAgrisi");
    case "Kas Spazmı": return t("kontrol.hedef.kasSpazmi");
    case "Kırık İyileşmesi": return t("kontrol.hedef.kirikIyilesmesi");
    case "Enflamasyon Azaltma": return t("kontrol.hedef.enflamasyonAzaltma");
    case "Sinir Rejenerasyonu": return t("kontrol.hedef.sinirRejenerasyonu");
    case "Bağ Dokusu Tamiri": return t("kontrol.hedef.bagDokusuTamiri");
    case "Ödem Azaltma": return t("kontrol.hedef.odemAzaltma");
    default: return hedef;
  }
};

/** Seans modunun GÖRÜNEN adı. ⚠️ Değer (`Manuel` / `Otomatik` / `AI`) seansa / DB'ye GİDER → DEĞİŞMEZ; "AI" iki dilde aynıdır. */
export const modEtiketi = (t: TFunction, mod: string): string => {
  switch (mod) {
    case "Manuel": return t("kontrol.sekme.manuel");
    case "Otomatik": return t("kontrol.sekme.otomatik");
    default: return mod;
  }
};
