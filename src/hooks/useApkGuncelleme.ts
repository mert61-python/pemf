// Author: mertaygn, cglrgrkn
/**
 * APK indirme + kurulum akışı — AÇILIŞ KAPISI ve uygulama içi BANT aynı kancayı kullanır.
 *
 * 2026-08-16'da açılış kapısı eklenince indirme/kurulum mantığı iki yere kopyalanacaktı. Kopya,
 * hata metinlerinin ve — daha önemlisi — hata DAVRANIŞININ zamanla ayrışması demektir. Tek kaynak.
 *
 * ⚠️ 2026-08-17: kurulum artık `KurulumSonucu` döndürüyor (paylaşım sayfası yerine doğrudan paket
 * yükleyici). Her sonucun kullanıcıya söylediği şey FARKLI olmalı — "bir hata oldu" demek,
 * kullanıcının izni açması gerektiğini gizler ve akışı çıkmaza sokar.
 */
import { useCallback, useState } from "react";

import { apkIndir, kurulumuBaslat, type MobilSurum } from "@/services/mobileUpdate";

export interface ApkGuncelleme {
  /** 0..1 indirme oranı; `null` = indirme yürümüyor. */
  oran: number | null;
  /** Kullanıcının BİR ŞEY YAPMASI gereken durum; boş = yok. */
  hata: string;
  /** Bilgilendirme (hata değil), ör. kurulum ekranı açıldı. */
  bilgi: string;
  /** Kurulum ekranı en az bir kez açıldı mı? (Arayüz "Tekrar dene" diyebilsin.) */
  kurulumAcildi: boolean;
  /** İndir + kurulumu aç. */
  guncelle: () => Promise<void>;
}

export function useApkGuncelleme(surum: MobilSurum | null): ApkGuncelleme {
  const [oran, setOran] = useState<number | null>(null);
  const [hata, setHata] = useState("");
  const [bilgi, setBilgi] = useState("");
  const [kurulumAcildi, setKurulumAcildi] = useState(false);

  const guncelle = useCallback(async () => {
    if (!surum) return;
    setHata("");
    setBilgi("");
    setOran(0);
    // ⚠️ Aynı sürüm zaten iniyorsa `apkIndir` YENİ indirme başlatmaz, sürene abone olur ve
    // ilerlemeyi kaldığı yerden verir (bkz. mobileUpdate.ts::_suren).
    const ind = await apkIndir(surum, setOran);
    setOran(null);
    if (!ind.ok || !ind.dosyaUri) {
      // ⚠️ "boyut" ve "indirme" AYRI metinler: ilkinde bağlantı vardı ama paket eksik indi
      // (tekrar denemek işe yarar), ikincisinde bağlantı hiç kurulamadı. Tek bir "hata oldu"
      // mesajı kullanıcıya ne yapacağını söylemez.
      setHata(
        ind.hata === "boyut"
          ? "İndirme eksik kaldı. Bağlantınızı kontrol edip tekrar deneyin."
          : "Güncelleme indirilemedi. Bağlantınızı kontrol edip tekrar deneyin.",
      );
      return;
    }

    switch (await kurulumuBaslat(ind.dosyaUri)) {
      case "acildi":
        setKurulumAcildi(true);
        setBilgi("Kurulum başlatıldı — telefonunuzun onayını bekleyin. Vazgeçerseniz bu ekrandan tekrar deneyebilirsiniz.");
        break;
      case "izin_gerekli":
        // İzin ekranı zaten açıldı; kullanıcı ne yapacağını ve sonra nereye döneceğini bilmeli.
        setHata("Kurulum için izin gerekiyor. Açılan ekranda bu uygulamaya izin verip tekrar deneyin.");
        break;
      case "paylasim":
        // Yerel modül kaydolmamış (olmaması gereken durum). Sessizce "oldu" demek YANLIŞ olurdu:
        // kullanıcı paylaşım sayfası görüyor ve kurulumun neden açılmadığını bilmeli.
        setKurulumAcildi(true);
        setBilgi("Kurulum ekranı açılamadı; dosyayı kaydedip telefonunuzdan elle kurabilirsiniz.");
        break;
      default:
        setHata("Kurulum açılamadı. Telefon ayarlarından bu uygulamaya 'bilinmeyen kaynak' izni verip tekrar deneyin.");
    }
  }, [surum]);

  return { oran, hata, bilgi, kurulumAcildi, guncelle };
}
