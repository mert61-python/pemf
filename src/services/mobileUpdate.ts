// Author: mertaygn, cglrgrkn
/**
 * MOBİL OTO-GÜNCELLEME (2026-08-08 sahip isteği: "bir kere indirsin, hep güncel kalsın").
 *
 * Masaüstü client zaten kendini ve uygulamayı otomatik güncelliyordu; MOBİL tarafta hiçbir
 * mekanizma yoktu — kullanıcı yeni APK'yı siteden ELLE indirmek zorundaydı. Bu modül aynı yayın
 * altyapısını (GitHub Release + manifest.json) mobile taşır: YENİ SERVİS GEREKMEZ.
 *
 * AKIŞ: manifest'i çek → `versionCode` karşılaştır → APK'yı indir → BOYUT doğrula → kurulum
 * niyetini (intent) aç. Kullanıcı onaylar, Android kurar.
 *
 * ⚠️ GÜVENLİK MODELİ — NEDEN SHA256 DEĞİL, İMZA:
 * Masaüstü tarafında güven çıpası manifest'teki SHA256'dır. Mobilde 128 MB'lık bir APK'nın
 * SHA256'sını hesaplamak pratik DEĞİL: `expo-file-system` dosya-digest API'si sunmuyor ve dosyayı
 * belleğe alıp JS'te hash'lemek düşük bellekli telefonlarda çöker. Bu yüzden BURADA GÜVEN ÇIPASI
 * ANDROID'İN KENDİ APK İMZA DOĞRULAMASIDIR: Android, kurulu uygulamayla AYNI anahtarla
 * imzalanmamış bir APK'yı güncelleme olarak KABUL ETMEZ. Yayın anahtarı geliştiricinin
 * makinesindedir (%USERPROFILE%\.pemf-keys) → araya giren biri APK'yı değiştirse bile yeniden
 * imzalayamaz ve kurulum İŞLETİM SİSTEMİ tarafından reddedilir. Bu, sha256'dan zayıf değil:
 * anahtar-tabanlı ve merkezî bir doğrulama.
 * Boyut kontrolü ayrıca yapılır — yarım/bozuk inen dosyayı kurmaya çalışmayı önler.
 * (manifest'teki `sha256` masaüstü ile eşitlik ve ileride yerel doğrulama için KORUNUR.)
 */
import AsyncStorage from "@react-native-async-storage/async-storage";
import * as FileSystem from "expo-file-system/legacy";
import Constants from "expo-constants";
import { Platform } from "react-native";

/** Yayın manifest'i — masaüstü client ile AYNI dosya (tek kaynak, ayrı servis yok). */
export const MANIFEST_URL =
  "https://github.com/mert61-python/pemf-update/releases/download/client-app-v1.8.0/manifest.json";

export interface MobilSurum {
  version: string;
  versionCode: number;
  url: string;
  sha256: string;
  size: number;
  notes?: string;
}

export interface GuncellemeDurumu {
  varMi: boolean;
  surum?: MobilSurum;
  /** Teşhis için: neden güncelleme yok. */
  sebep?: "platform" | "manifest" | "guncel" | "eksik_alan";
}

/** Kurulu APK'nın versionCode'u (app.json → expo.android.versionCode). */
export function mevcutVersionCode(): number {
  const c = Constants.expoConfig as { android?: { versionCode?: number } } | null;
  return Number(c?.android?.versionCode ?? 0);
}

/**
 * Yeni sürüm var mı?
 *
 * ⚠️ AĞ HATASI SESSİZ: güncelleme kontrolü kullanıcıyı ASLA engellemez — internetsiz klinikte
 * uygulama normal açılmalı (masaüstündeki "çevrimdışıysa atla" ilkesinin aynısı).
 */
export async function guncellemeVarMi(fetchFn: typeof fetch = fetch): Promise<GuncellemeDurumu> {
  // iOS'ta doğrudan APK kurulumu YOKTUR (App Store/TestFlight yolu) → hiç deneme.
  if (Platform.OS !== "android") return { varMi: false, sebep: "platform" };
  try {
    const r = await fetchFn(MANIFEST_URL, { cache: "no-store" } as RequestInit);
    if (!r.ok) return { varMi: false, sebep: "manifest" };
    const m = (await r.json()) as { mobile?: { android?: Partial<MobilSurum> } };
    const a = m?.mobile?.android;
    if (!a?.url || !a?.versionCode || !a?.size) return { varMi: false, sebep: "eksik_alan" };
    if (Number(a.versionCode) <= mevcutVersionCode()) return { varMi: false, sebep: "guncel" };
    return { varMi: true, surum: a as MobilSurum };
  } catch {
    return { varMi: false, sebep: "manifest" };
  }
}

export type IlerlemeCb = (oran: number) => void;

export interface IndirmeSonucu {
  ok: boolean;
  dosyaUri?: string;
  hata?: "indirme" | "boyut";
}

/** Yarım kalan indirmenin izi (AsyncStorage). İndirme BAŞLAMADAN yazılır. */
const DEVAM_ANAHTARI = "@pemf_apk_indirme";

/**
 * Süreç öldürüldüğünde geriye kalan TEK iz. `resumeData` BURADA TUTULMAZ — kasıtlı:
 * uygulama çökerse/öldürülürse onu diske yazma fırsatı zaten olmaz. Devam noktası her
 * açılışta KISMİ DOSYANIN KENDİ BOYUTUNDAN türetilir (bkz. `apkIndir`).
 */
interface DevamKaydi {
  versionCode: number;
  url: string;
  fileUri: string;
}

async function devamOku(): Promise<DevamKaydi | null> {
  try {
    const ham = await AsyncStorage.getItem(DEVAM_ANAHTARI);
    return ham ? (JSON.parse(ham) as DevamKaydi) : null;
  } catch {
    return null;
  }
}
async function devamYaz(k: DevamKaydi): Promise<void> {
  try { await AsyncStorage.setItem(DEVAM_ANAHTARI, JSON.stringify(k)); } catch { /* yut */ }
}
async function devamSil(): Promise<void> {
  try { await AsyncStorage.removeItem(DEVAM_ANAHTARI); } catch { /* yut */ }
}

/**
 * APK'yı indir + BOYUT doğrula. Boyut tutmazsa dosyayı SİLER (yarım paket kurulmaya çalışılmaz).
 *
 * Dosya adı sürüm koduna bağlanır: bir önceki denemeden kalan bayat APK yeni sürüm sanılmaz
 * (launcher self-update'inde alınan dersin aynısı).
 *
 * ⚠️ KALDIĞI YERDEN DEVAM (2026-08-13, saha bildirimi: "%10'dayken kapatıp açınca 0'dan
 * başlıyor"). `createDownloadResumable` kullanılıyordu ama devam noktası HİÇ VERİLMİYORDU →
 * her açılış sıfırdan. 128 MB'lık paketi mobil veriyle baştan indirmek zaman ve kota kaybıdır.
 *
 * ⚠️ DEVAM NOKTASI `savable()`DEN DEĞİL, DİSKTEN TÜRETİLİR — bu KASITLI ve daha sağlamdır.
 * Android'de `resumeData` opak bir jeton değil, KISMİ DOSYANIN BAYT SAYISIDIR: yerel modül onu
 * `file.length().toString()` ile üretir ve devam ederken `Range: bytes=N-` başlığı olarak
 * gönderir (expo-file-system `FileSystemLegacyModule.kt`). Yani aynı değer diskteki dosyanın
 * boyutundan okunabilir. `pauseAsync()`e bağlanmak, uygulama ÇÖKERSE ya da sistem tarafından
 * ÖLDÜRÜLÜRSE — yani devam etmenin asıl gerekli olduğu durumda — kaydı yazma fırsatı bırakmazdı.
 * Diskteki dosya ise her koşulda oradadır. (Bu yol Android'e özgüdür; akışın tamamı zaten
 * Android'e kapılıdır — bkz. `guncellemeVarMi` ve `kurulumuBaslat`.)
 *
 * ⚠️ ARKA PLANDA DURAKLATILMAZ — sahip isteği: "başka uygulama açtığımda / ekran kilitlendiğinde
 * indirme güvenli şekilde TAMAMLANMALI". Yerel modül indirmeyi `Dispatchers.IO` üzerinde bir
 * coroutine'de yürütür (JS iş parçacığında DEĞİL) ve Android'de her ikisi de arka planda koşmaya
 * devam eder → indirme kendiliğinden tamamlanır. `AppState` ile duraklatmak, tamamlanacak bir
 * indirmeyi DURDURMAK olurdu; istenenin tam tersi. Sistem uygulamayı yine de öldürürse kısmi
 * dosya diskte kalır ve bir sonraki açılışta oradan sürer.
 *
 * ⚠️ Sunucu `Range`i yok sayarsa (200 döner) yerel modül gövdeyi mevcut dosyaya YİNE DE ekler
 * (`FileOutputStream(file, isResume)` — 206 denetimi yoktur). O durumda boyut tutmaz; aşağıdaki
 * boyut kapısı dosyayı SİLER ve kaydı temizler → sonraki deneme sıfırdan, temiz başlar.
 */
export async function apkIndir(
  surum: MobilSurum,
  onIlerleme?: IlerlemeCb,
  deps: {
    createDownloadResumable?: typeof FileSystem.createDownloadResumable;
    getInfoAsync?: typeof FileSystem.getInfoAsync;
    deleteAsync?: typeof FileSystem.deleteAsync;
    devamOku?: typeof devamOku;
    devamYaz?: typeof devamYaz;
    devamSil?: typeof devamSil;
  } = {},
): Promise<IndirmeSonucu> {
  const hedef = `${FileSystem.cacheDirectory || ""}pemf-vet-${surum.versionCode}.apk`;
  const olustur = deps.createDownloadResumable ?? FileSystem.createDownloadResumable;
  const bilgiAl = deps.getInfoAsync ?? FileSystem.getInfoAsync;
  const sil = deps.deleteAsync ?? FileSystem.deleteAsync;
  const oku = deps.devamOku ?? devamOku;
  const yaz = deps.devamYaz ?? devamYaz;
  const kayitSil = deps.devamSil ?? devamSil;

  const beklenen = Number(surum.size);

  // Kayıt yalnız AYNI sürüm + AYNI adres için geçerli; sürüm/adres değiştiyse yarım dosya çöptür.
  const kayit = await oku();
  const ayniIs = !!kayit && kayit.versionCode === surum.versionCode && kayit.url === surum.url;
  if (kayit && !ayniIs) {
    await kayitSil();
    try { await sil(kayit.fileUri, { idempotent: true }); } catch { /* yut */ }
  }

  try {
    // Diskteki kısmi dosya → devam noktası.
    let devamBaytlari: string | undefined;
    if (ayniIs) {
      const kismi = (await bilgiAl(hedef)) as { exists?: boolean; size?: number };
      const boyut = Number(kismi?.size ?? 0);
      if (kismi?.exists && boyut === beklenen) {
        // Uygulama indirme BİTTİKTEN sonra, kurulum onayı verilmeden kapanmış → yeniden indirme.
        await kayitSil();
        return { ok: true, dosyaUri: hedef };
      }
      if (kismi?.exists && boyut > 0 && boyut < beklenen) {
        devamBaytlari = String(boyut);
      } else if (kismi?.exists) {
        // 0 bayt ya da beklenenden BÜYÜK (önceki başarısız ekleme) → çöp; sıfırdan.
        try { await sil(hedef, { idempotent: true }); } catch { /* yut */ }
      }
    }

    // ⚠️ Kayıt indirme BAŞLAMADAN yazılır: süreç öldürülürse yazma fırsatı bir daha gelmez.
    await yaz({ versionCode: surum.versionCode, url: surum.url, fileUri: hedef });

    const baslangic = Number(devamBaytlari ?? 0);
    const dl = olustur(
      surum.url,
      hedef,
      {},
      (p) => {
        // ⚠️ İlerleme, devam edilen indirmede de 0'dan değil KALDIĞI YERDEN gösterilmeli
        // (kullanıcının gördüğü yüzde geri gitmesin). Yerel modül `resumeData`yı sayaçlarına
        // zaten ekliyor; toplam beklenen bilinmiyorsa manifest boyutuna düşülür.
        const toplam = p.totalBytesExpectedToWrite > 0 ? p.totalBytesExpectedToWrite : beklenen;
        const yazilan = p.totalBytesWritten > 0 ? p.totalBytesWritten : baslangic;
        if (toplam > 0) onIlerleme?.(Math.min(1, yazilan / toplam));
      },
      devamBaytlari,
    );

    const sonuc = await dl.downloadAsync();
    if (!sonuc?.uri) return { ok: false, hata: "indirme" };

    const bilgi = (await bilgiAl(sonuc.uri)) as { exists?: boolean; size?: number };
    if (!bilgi?.exists || Number(bilgi.size) !== beklenen) {
      // Yarım/bozuk inen paketi kurmaya ÇALIŞMA → sil (kullanıcı anlaşılmaz bir kurulum
      // hatasıyla karşılaşmasın; sonraki denemede baştan, temiz iner).
      try { await sil(sonuc.uri, { idempotent: true }); } catch { /* yut */ }
      await kayitSil();
      return { ok: false, hata: "boyut" };
    }
    await kayitSil(); // tamamlandı → yarım-indirme izi kalmasın
    return { ok: true, dosyaUri: sonuc.uri };
  } catch {
    // ⚠️ Kayıt ve kısmi dosya BİLEREK bırakılır: ağ koptuğunda bir sonraki deneme kaldığı
    // yerden sürebilsin (asıl istenen davranış). Bozuk dosyayı boyut kapısı zaten eliyor.
    return { ok: false, hata: "indirme" };
  }
}

/**
 * İndirilen APK'yı sistem kurulumuna teslim et (Android). Kullanıcı onaylar, Android kurar.
 *
 * ⚠️ NEDEN `expo-intent-launcher` DEĞİL: doğrudan `INSTALL_PACKAGE` niyeti daha temiz bir akış
 * verirdi, AMA o paketin KARARLI sürümü SDK 57 içindir; bu proje SDK 56'da (diğer tüm expo
 * paketleri `~56.x`). SDK 56 için yalnız canary sürümler var. Sürümü uyuşmayan bir NATIVE modülü
 * tıbbi cihaz APK'sına koymak kabul edilemez: modül kaydolmazsa özellik SESSİZCE çalışmaz ve bunu
 * ancak sahada fark ederiz. `expo-sharing` zaten `~56` ile pinli ve projede KURULU → sürüm riski
 * yok. Sistem seçicisi açılır, kullanıcı "Paket yükleyici"yi seçer.
 * (SDK 57'ye geçildiğinde `expo-intent-launcher` ile tek-adıma indirilebilir.)
 *
 * ⚠️ Asıl güvenlik kapısı değişmedi: Android, kurulu uygulamayla AYNI anahtarla imzalanmamış bir
 * APK'yı güncelleme olarak KABUL ETMEZ (bkz. modül başlığı).
 */
export async function kurulumuBaslat(dosyaUri: string): Promise<boolean> {
  if (Platform.OS !== "android") return false;
  try {
    const Sharing = await import("expo-sharing");
    if (!(await Sharing.isAvailableAsync())) return false;
    await Sharing.shareAsync(dosyaUri, {
      mimeType: "application/vnd.android.package-archive",
      dialogTitle: "Güncellemeyi kur",
    });
    return true;
  } catch {
    return false;
  }
}
