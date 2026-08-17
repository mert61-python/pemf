// Author: mertaygn, cglrgrkn
/**
 * APK indirme + kurulum akışı — AÇILIŞ KAPISI ve uygulama içi BANT aynı kancayı kullanır.
 *
 * 2026-08-16'da açılış kapısı eklenince (bkz. `MobileUpdateGate`) indirme/kurulum mantığı iki
 * yere kopyalanacaktı. Kopya, hata metinlerinin ve — daha önemlisi — hata DAVRANIŞININ zamanla
 * ayrışması demektir (ör. "boyut" hatasında dosyanın silinmesi bir yolda unutulur). Tek kaynak.
 */
import { useCallback, useState } from "react";

import { apkIndir, kurulumuBaslat, type MobilSurum } from "@/services/mobileUpdate";

export interface ApkGuncelleme {
  /** 0..1 indirme oranı; `null` = indirme yürümüyor. */
  oran: number | null;
  /** Kullanıcıya gösterilecek hata; boş = hata yok. */
  hata: string;
  /** İndir + kurulum niyetini aç. */
  guncelle: () => Promise<void>;
}

export function useApkGuncelleme(surum: MobilSurum | null): ApkGuncelleme {
  const [oran, setOran] = useState<number | null>(null);
  const [hata, setHata] = useState("");

  const guncelle = useCallback(async () => {
    if (!surum) return;
    setHata("");
    setOran(0);
    const ind = await apkIndir(surum, setOran);
    setOran(null);
    if (!ind.ok || !ind.dosyaUri) {
      // ⚠️ "boyut" ve "indirme" AYRI metinler: ilkinde bağlantı vardı ama paket eksik indi
      // (tekrar denemek işe yarar), ikincisinde bağlantı hiç kurulamadı. Tek bir "hata oldu"
      // mesajı kullanıcıya ne yapacağını söylemez.
      setHata(
        ind.hata === "boyut"
          ? "İndirme eksik kaldı. Bağlantınızı kontrol edip tekrar deneyin."
          : "Güncelleme indirilemedi.",
      );
      return;
    }
    const acildi = await kurulumuBaslat(ind.dosyaUri);
    if (!acildi) {
      setHata("Kurulum açılamadı. Ayarlar'dan bu uygulamaya 'bilinmeyen kaynak' izni verin.");
    }
  }, [surum]);

  return { oran, hata, guncelle };
}
