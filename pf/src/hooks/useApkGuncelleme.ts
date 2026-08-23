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

import { apiGet } from "@/services/apiClient";
import {
  apkIndir,
  kurulumuBaslat,
  kurulumErtelendiMi,
  kurulumErtelemesiniKaldir,
  type MobilSurum,
} from "@/services/mobileUpdate";

/**
 * Kurulum ekranını AÇMAK şu an güvenli mi? (cihazda tedavi sürüyor mu?)
 *
 * 🔴 TIBBİ GÜVENLİK — DENETİM BULGUSU 2026-08-17. `MobileUpdateBanner` süren seansta `return null`
 * ediyordu, ama `return null` bileşeni UNMOUNT ETMEZ: uçuştaki `guncelle()` promise'i sürüyor ve
 * indirme bitince `kurulumuBaslat` çalışıyordu → Android paket yükleyicisi **bobinler hastanın
 * üzerindeyken** operatörün seans ekranının üstüne tam ekran açılıyordu. Onaylanırsa uygulama
 * öldürülüp yeniden kurulur ve telefon kumandası seansın ORTASINDA kaybolur. Bandın kendi başlığı
 * bunu "kabul edilemez" diye tanımlıyordu; eksik olan uçuştaki işin durdurulmasıydı.
 *
 * ⚠️ NEDEN BANDIN `seansAktif` PROP'U YETMEZ: `MobileUpdateGate` `<Stack/>`in ve dolayısıyla
 * `LiveDataProvider`ın ÜSTÜNDE durur → context'e yapısal olarak erişemez. Kapı cihazın KENDİSİNE
 * sorulur, böylece AÇILIŞ KAPISI ve BANT aynı korumayı paylaşır (tek kaynak). Bandın görünürlük
 * kapısı KALDIRILMAZ; bu ondan bağımsız ikinci katmandır.
 *
 * ⚠️ BİLİNÇLİ FAIL-OPEN: seans durumu ÖĞRENİLEMEZSE kurulum ENGELLENMEZ. Fail-closed olsaydı
 * farklı ağdaki (ya da cihaza ulaşamayan) bir telefon bir daha ASLA güncellenemezdi — tıbbi bir
 * cihazın uzaktan kumandasını KALICI kilitlemek, sahibin açıkça yasakladığı sonuçtur (mobil 2.3.16:
 * "güncelleme ZORUNLU KILINAMAZ"). Yalnız POZİTİF kanıt (`is_active === true`) kurulumu erteler.
 *
 * ⚠️ Kısa `timeoutMs`: bu sorgu 128 MB'lık indirmeden SONRA yapılır; varsayılan 8 sn + GET
 * yeniden-denemesi en kötü ~16 sn sessiz bekleme demek olurdu. 2,5 sn ile en kötü ~5,4 sn.
 * Cihaz gerçekten erişilemezse rota/DNS yokluğunda bağlantı 1 sn'nin altında düşer.
 *
 * Kilit: `__tests__/useApkGuncelleme.seansKapisi.test.ts` (karşı-kanıt testleri dahil).
 */
async function seansSuruyorMu(): Promise<boolean> {
  try {
    // Denetim 2. tur [2.1] (2026-08-20): bobinler SEANSSIZ da çalışır (bobin panelinden
    // başlatılan sürüş `is_active`i değiştirmez; ControlScreen bunu `hardwareRunningOutOfSession`
    // banner'ıyla ayrı durum sayar). Yalnız `is_active`e bakmak, bobinler hayvanın üzerindeyken
    // yükleyicinin yine açılması demekti. Backend artık canlı-durumdan `hardware_running` taşıyor;
    // ikisi de POZİTİF-kanıt ilkesine tabi (eski backend alanı taşımaz → undefined → fail-open,
    // "güncelleme ZORUNLU KILINAMAZ" sahip kararı bozulmaz).
    const s = await apiGet<{ is_active?: boolean; hardware_running?: boolean } | null>("/session/active", null, {
      silent: true,
      timeoutMs: 2500,
    });
    return s?.is_active === true || s?.hardware_running === true;
  } catch {
    return false; // fail-open (yukarıdaki gerekçe)
  }
}

export interface ApkGuncelleme {
  /** 0..1 indirme oranı; `null` = indirme yürümüyor. */
  oran: number | null;
  /** Kullanıcının BİR ŞEY YAPMASI gereken durum; boş = yok. */
  hata: string;
  /** Bilgilendirme (hata değil), ör. kurulum ekranı açıldı. */
  bilgi: string;
  /** Kurulum ekranı en az bir kez açıldı mı? (Arayüz "Tekrar dene" diyebilsin.) */
  kurulumAcildi: boolean;
  /** [5.7c] Paket TAM indi mi? (oran===null "hiç başlamadı"yı "tamamlandı"dan ayıramaz —
   *  kapı erteleme kararını buna göre verir: hazır paketin bandı SUSTURULMAZ.) */
  paketHazir: boolean;
  /** İndir + kurulumu aç. */
  guncelle: () => Promise<void>;
}

export function useApkGuncelleme(surum: MobilSurum | null): ApkGuncelleme {
  const [oran, setOran] = useState<number | null>(null);
  const [hata, setHata] = useState("");
  const [bilgi, setBilgi] = useState("");
  const [kurulumAcildi, setKurulumAcildi] = useState(false);
  const [paketHazir, setPaketHazir] = useState(false);

  const guncelle = useCallback(async () => {
    if (!surum) return;
    // [5.7a] Açık kullanıcı niyeti: 'Güncelle'ye (yeniden) dokunmak ertelemeyi KALDIRIR —
    // erteleme yalnız kapı kapatılırken uçuşta kalan işi bağlar, kalıcı kilit değildir.
    kurulumErtelemesiniKaldir(surum.versionCode);
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
        ind.hata === "sunucu"
          // ⚠️ AYRI METİN (denetim 2026-08-23): sunucu 2xx dışı yanıt verdi — varlık silinmiş ya
          // da yanlış etikete taşınmış olabilir. Burada "bağlantınızı kontrol edin" demek
          // kullanıcıyı işe yaramayacak bir döngüye sokar: tekrar denemek DURUMU DEĞİŞTİRMEZ.
          ? "Güncelleme paketine şu an ulaşılamıyor (sunucu hatası). Bağlantınızla ilgili değil; kısa süre sonra tekrar deneyin."
          : ind.hata === "boyut"
            ? "İndirme eksik kaldı. Bağlantınızı kontrol edip tekrar deneyin."
            : "Güncelleme indirilemedi. Bağlantınızı kontrol edip tekrar deneyin.",
      );
      return;
    }
    setPaketHazir(true);

    // 🔴 TIBBİ GÜVENLİK KAPISI — kurulumdan HEMEN ÖNCE sorulur (bkz. seansSuruyorMu).
    // ⚠️ SIRA KRİTİK: indirme başlarken seans yoktu ama BİTERKEN olabilir (128 MB, dakikalar).
    // Başlangıçtaki duruma güvenmek bulgunun kendisiydi. İndirme ENGELLENMEZ — paket diskte hazır
    // bekler ve seans bitince hazır-dosya hızlı yolu tek bayt bile yeniden indirmez.
    if (await seansSuruyorMu()) {
      setBilgi(
        "Güncelleme indirildi ama cihazda tedavi sürüyor (seans ya da çalışan bobin) — kurulum " +
          "ekranı açılmadı. Bobinler durduktan sonra 'Güncelle'ye dokunun; paket hazır, yeniden indirilmeyecek.",
      );
      return;
    }

    // [5.7a] ERTELEME KAPISI — seans kapısından SONRA (tıbbi metin öncelikli), kurulumdan ÖNCE.
    // Kapı "Şimdilik devam et" ile kapatıldıysa UÇUŞTAKİ bu iş yükleyiciyi kullanıcının o anki
    // işinin üstüne SORMADAN açamaz; paket diskte hazır bekler, bant susturulmadığı için
    // kullanıcı hazır olduğunda tek dokunuşla (yeniden indirmeden) kurar.
    if (kurulumErtelendiMi(surum.versionCode)) {
      setBilgi(
        "Güncelleme indirildi ve hazır — güncellemeyi ertelediğiniz için kurulum ekranı açılmadı. " +
          "Hazır olduğunuzda 'Güncelle'ye dokunun; paket yeniden indirilmeyecek.",
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

  return { oran, hata, bilgi, kurulumAcildi, paketHazir, guncelle };
}
