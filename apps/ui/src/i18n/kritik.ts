/**
 * GÜVENLİK METİNLERİ — ÇEVİRİ SİSTEMİNDEN BAĞIMSIZ GÖRÜNÜRLÜK (T11a, Ö.4-Y8).
 *
 * ACİL DURDUR ve benzeri kritik etiketler katalog bozuk, anahtar eksik, i18n başlatılamamış ya da çeviri boş dönmüş olsa bile BOŞ
 * KALMAZ: `kritikMetin()` önce katalogdan okur, olmazsa aşağıdaki SABİT iki dilli yedeği kullanır. Bu modül react-i18next'i KULLANMAZ
 * (Suspense / hazır-değil durumu yok); bileşen dil değişimini `useKritikDil()` ile izler — o da başarısız olursa yedek dilde kalır.
 *
 * ⚠️ `KRITIK_YEDEK` değerleri katalogdaki (`tr|en/guvenlik.json`) değerlerle BİREBİR AYNI olmalı; K-5 kapısı (`tests/test_i18n_kritik_K5.py`)
 * eşliği ve `i18n/kritik-anahtarlar.json` listesini denetler. Yeni kritik anahtar: katalog (tr + en) + bu tablo + liste BİRLİKTE.
 */
import { useEffect, useState } from "react";
import i18n from "i18next";
import type { Dil } from "./durum";

export const KRITIK_YEDEK = {
  tr: {
    "guvenlik.acilDurdur.dugme": "🚨 ACİL DURDUR",
    "guvenlik.acilDurdur.dugmeBobin_one": "🚨 ACİL DURDUR ({{count}} bobin)",
    "guvenlik.acilDurdur.dugmeBobin_other": "🚨 ACİL DURDUR ({{count}} bobin)",
    "guvenlik.acilDurdur.dugmeTeyitsiz": "🚨 ACİL DURDUR (teyitsiz)",
    "guvenlik.acilDurdur.dugmeBaglantiYok": "🚨 ACİL DURDUR (bağlantı yok)",
    "guvenlik.acilDurdur.durduruluyor": "🚨 DURDURULUYOR…",
    "guvenlik.acilDurdur.erisimEtiketi": "Acil durdur",
    "guvenlik.acilDurdur.erisimIpucu": "Tüm bobinleri anında durdurur ve aktif seansı sonlandırır",
    "guvenlik.acilDurdur.tumBobinlerEtiketi": "Tüm bobinleri acil durdur",
    "guvenlik.acilDurdur.tumBobinlerDugme": "🚨 TÜM BOBİNLERİ ACİL DURDUR",
    "guvenlik.acilDurdur.seansKartiEtiketi": "Acil durdurma — tüm bobinleri anında durdur",
    "guvenlik.acilDurdur.gonderiliyor": "Acil durdurma gönderiliyor…",
    "guvenlik.acilDurdur.durduruldu": "Tüm bobinler durduruldu ✓",
    "guvenlik.acilDurdur.teyitsizBaslik": "⚠️ ACİL DURDURMA DOĞRULANAMADI",
    "guvenlik.acilDurdur.teyitsizGovde": "Donanımın durduğu teyit edilemedi. Bobinler hâlâ çalışıyor olabilir — cihazı fiziksel güç düğmesinden kapatın.",
    "guvenlik.acilDurdur.kartRedBaslik": "⛔ KART STOP'U REDDETTİ",
    "guvenlik.acilDurdur.kartRedGovde": "Cihaz kartı STOP komutunu reddetti — bobinler durmamış olabilir. Cihazın gücünü kesin ya da USB kablosunu çıkarın.",
  },
  en: {
    "guvenlik.acilDurdur.dugme": "🚨 EMERGENCY STOP",
    "guvenlik.acilDurdur.dugmeBobin_one": "🚨 EMERGENCY STOP ({{count}} coil)",
    "guvenlik.acilDurdur.dugmeBobin_other": "🚨 EMERGENCY STOP ({{count}} coils)",
    "guvenlik.acilDurdur.dugmeTeyitsiz": "🚨 EMERGENCY STOP (unconfirmed)",
    "guvenlik.acilDurdur.dugmeBaglantiYok": "🚨 EMERGENCY STOP (no connection)",
    "guvenlik.acilDurdur.durduruluyor": "🚨 STOPPING…",
    "guvenlik.acilDurdur.erisimEtiketi": "Emergency stop",
    "guvenlik.acilDurdur.erisimIpucu": "Stops all coils immediately and ends the active session",
    "guvenlik.acilDurdur.tumBobinlerEtiketi": "Emergency stop all coils",
    "guvenlik.acilDurdur.tumBobinlerDugme": "🚨 EMERGENCY STOP ALL COILS",
    "guvenlik.acilDurdur.seansKartiEtiketi": "Emergency stop — stop all coils immediately",
    "guvenlik.acilDurdur.gonderiliyor": "Sending emergency stop…",
    "guvenlik.acilDurdur.durduruldu": "All coils stopped ✓",
    "guvenlik.acilDurdur.teyitsizBaslik": "⚠️ EMERGENCY STOP NOT CONFIRMED",
    "guvenlik.acilDurdur.teyitsizGovde": "Could not confirm that the hardware stopped. The coils may still be running — switch the device off with its physical power button.",
    "guvenlik.acilDurdur.kartRedBaslik": "⛔ BOARD REJECTED THE STOP",
    "guvenlik.acilDurdur.kartRedGovde": "The device board rejected the STOP command — the coils may not have stopped. Cut the device's power or unplug the USB cable.",
  },
} as const;

export type KritikTemel = keyof typeof KRITIK_YEDEK.tr;
/** Çoğul anahtar kökleri (`_one` / `_other` olmadan) de çağrılabilir: `kritikMetin("guvenlik.acilDurdur.dugmeBobin", { count })`. */
type CogulKoku<T> = T extends `${infer K}_one` ? K : never; // çıplak tür parametresi → birleşim üzerinde DAĞILIR
export type KritikAnahtar = KritikTemel | CogulKoku<KritikTemel>;

function etkinKritikDil(): Dil {
  try {
    return i18n.language === "en" ? "en" : "tr";
  } catch {
    return "tr";
  }
}

function doldur(sablon: string, p?: Record<string, unknown>): string {
  if (!p) return sablon;
  return sablon.replace(/\{\{\s*(\w+)\s*\}\}/g, (_m, ad: string) => (p[ad] === undefined || p[ad] === null ? "" : String(p[ad])));
}

function yedek(anahtar: KritikAnahtar, dil: Dil, p?: Record<string, unknown>): string {
  const tablo = KRITIK_YEDEK[dil] as Record<string, string>;
  let k: string = anahtar;
  if (!(k in tablo)) {
    const n = Number(p?.count);
    k = `${anahtar}_${n === 1 ? "one" : "other"}`;
  }
  const s = tablo[k] ?? (KRITIK_YEDEK.tr as Record<string, string>)[k] ?? "🚨 ACİL DURDUR / EMERGENCY STOP";
  return doldur(s, p);
}

/** Kritik metin: katalogdan; anahtar yok / boş / başlatma bozuk → sabit yedek. ASLA boş dönmez, ASLA atmaz. */
export function kritikMetin(anahtar: KritikAnahtar, p?: Record<string, unknown>): string {
  const dil = etkinKritikDil();
  try {
    if (i18n.isInitialized && i18n.exists(anahtar, p as never)) {
      const m = (i18n.t as unknown as (k: string, o?: object) => unknown)(anahtar, p);
      if (typeof m === "string" && m.trim() !== "" && m !== anahtar) return m;
    }
  } catch {
    /* yedeğe düş */
  }
  return yedek(anahtar, dil, p);
}

/** Kritik bileşenin dil değişiminde yeniden çizilmesi için abonelik (react-i18next'siz; hata → sessizce yedek dilde kalır). */
export function useKritikDil(): Dil {
  const [dil, setDil] = useState<Dil>(etkinKritikDil);
  useEffect(() => {
    const dinle = (l: string) => setDil(l === "en" ? "en" : "tr");
    try {
      i18n.on("languageChanged", dinle);
    } catch {
      return undefined;
    }
    return () => {
      try {
        i18n.off("languageChanged", dinle);
      } catch {
        /* yok say */
      }
    };
  }, []);
  return dil;
}
