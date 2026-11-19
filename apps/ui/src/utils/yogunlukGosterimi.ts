import i18n from "i18next";
import { ondalikMetni } from "@/i18n/dil";
// Author: mertaygn, cglrgrkn
/**
 * D1.89 · B-6.27 (+ İNCELEME-2 §10 #5 · İG-6.47 sınıfı) — yoğunluk gösteriminin TEK KAYNAĞI.
 *
 * Üç FARKLI sayı vardır ve etiket hangisinin gösterildiğini söyler:
 *   - ÖLÇÜLEN (`measuredIntensityMt`, koşu özeti `field_avg`): STM'e bağlı alan sensörünün gördüğü |B| (mT);
 *   - KAYIT (`intensityMt`, `intensity_mt`): operatörün yazdığı reçete — cihaza GÖNDERİLMEZ (STM/ESP paketi mT taşımaz);
 *   - DUTY TEMSİLİ (`dutyTemsilYuzde`): AI Pro'nun bobin 1 plan duty'si (%). mT DEĞİLDİR.
 *
 * ÖLÇÜLEN KUSUR: Ana Ekran ve Geçmiş reçeteyi etiketsiz "Yoğunluk 1.5 mT" diye gösteriyordu (hekim uygulanan alan
 * sanıyordu); hiçbir ekran koşunun ölçülen alanını göstermiyordu; AI Pro'da bobin 1 duty'si (%37) "37 mT" görünüyordu;
 * reçetesiz kayıt "0 mT" yazıyordu. ⚠️ Ölçüm/reçete yoksa sayı UYDURULMAZ: "—".
 */

export type YogunlukTuru = "olculen" | "kayit" | "odak" | "duty" | "yok";

export interface YogunlukGosterimi {
  tur: YogunlukTuru;
  deger: string;
}

interface CanliSeans {
  intensityMt?: number | null;
  measuredIntensityMt?: number | null;
  dutyTemsilYuzde?: number | null;
  /** ODD K-11: AI Pro ODAK seansında seçilen doz (mT, mühür) ve planın sürdüğü bobin sayısı (backend `odakDozMt` / `odakBobinSayisi`). */
  odakDozMt?: number | null;
  odakBobinSayisi?: number | null;
}

const sayi = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

/** Canlı seans kartları (Ana Ekran, Kontrol): önce ölçülen, yoksa reçete, yoksa (AI Pro) duty temsili, yoksa "—". */
export function canliYogunluk(at: CanliSeans | null | undefined): YogunlukGosterimi {
  const olculen = at?.measuredIntensityMt;
  if (sayi(olculen)) return { tur: "olculen", deger: `${ondalikMetni(olculen, 2)} mT` }; // Y306: ondalık ayırıcı dile göre
  const recete = at?.intensityMt;
  if (sayi(recete) && recete > 0) return { tur: "kayit", deger: `${recete} mT` };
  const odak = at?.odakDozMt;
  if (sayi(odak) && odak > 0) {
    const n = sayi(at?.odakBobinSayisi) ? at!.odakBobinSayisi! : 0;
    return { tur: "odak", deger: i18n.t("kontrol.yogunluk.odakDeger", { doz: ondalikMetni(odak, 2), count: n }) };
  }
  const duty = at?.dutyTemsilYuzde;
  if (sayi(duty)) return { tur: "duty", deger: `%${duty}` };
  return { tur: "yok", deger: "—" };
}

/** Kayıt görünümleri (Geçmiş, Seans Detayı): reçete; yoksa / 0 ise "—" (reçetesiz seans "0 mT" DEĞİLDİR). */
export function kayitYogunlugu(mt: number | null | undefined): string {
  return sayi(mt) && mt > 0 ? `${mt} mT` : "—";
}

/** Koşu özetindeki ölçülen alan ortalaması; hiç ölçülmediyse (backend `None`) "—". */
export function olculenAlanOrt(mt: number | null | undefined): string {
  return sayi(mt) ? `${mt.toFixed(2)} mT` : "—";
}

export const YOGUNLUK_ETIKETI: Record<YogunlukTuru, string> = {
  get olculen() { return i18n.t("kontrol.yogunluk.olculen"); },
  get kayit() { return i18n.t("kontrol.yogunluk.kayit"); },
  get odak() { return i18n.t("kontrol.yogunluk.odak"); },
  get duty() { return i18n.t("kontrol.yogunluk.duty"); },
  get yok() { return i18n.t("kontrol.yogunluk.kayit"); },
};

/** Seans kartının BÜYÜK harfli etiketleri (mevcut "YOĞUNLUK (kayıt)/(ölçülen)" dizeleri korunur). */
export const YOGUNLUK_ETIKETI_BUYUK: Record<YogunlukTuru, string> = {
  get olculen() { return i18n.t("kontrol.yogunluk.olculenBuyuk"); },
  get kayit() { return i18n.t("kontrol.yogunluk.kayitBuyuk"); },
  get odak() { return i18n.t("kontrol.yogunluk.odakBuyuk"); },
  get duty() { return i18n.t("kontrol.yogunluk.dutyBuyuk"); },
  get yok() { return i18n.t("kontrol.yogunluk.kayitBuyuk"); },
};
