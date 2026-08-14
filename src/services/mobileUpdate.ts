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
import { AppState, Platform, type AppStateStatus } from "react-native";

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

/** Yarım kalan indirmenin devam bilgisi (AsyncStorage). */
const DEVAM_ANAHTARI = "@pemf_apk_indirme";

/** `DownloadResumable.savable()` çıktısı + hangi sürüme ait olduğu. */
interface DevamKaydi {
  versionCode: number;
  url: string;
  fileUri: string;
  options?: object;
  resumeData?: string;
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
 * ⚠️ KALDIĞI YERDEN DEVAM (2026-08-13, saha bildirimi). Eskiden indirme %10'dayken uygulama
 * kapatılıp yeniden açıldığında SIFIRDAN başlıyordu: `createDownloadResumable` kullanılıyordu
 * ama devam bilgisi (`savable()`) HİÇ SAKLANMIYORDU — oysa expo-file-system'in kendi belgesi
 * tam olarak bunu öneriyor. 122 MB'lık bir paketi mobil veriyle baştan indirmek hem zaman hem
 * kota kaybıdır.
 *
 * ⚠️ ARKA PLAN GÜVENLİĞİ: uygulama arka plana alındığında ya da EKRAN KİLİTLENDİĞİNDE JS
 * yürütmesi işletim sistemi tarafından kısılır; indirme sessizce ASILI kalabilir. Bu yüzden
 * `AppState` dinlenir: arka plana geçişte indirme DURAKLATILIR ve devam bilgisi diske yazılır
 * (kayıp yok, bozuk dosya yok), öne dönüşte KALDIĞI YERDEN sürer.
 *
 * ⚠️ DÜRÜST SINIR: uygulama arka plandayken indirme SÜRMEZ. Gerçek arka plan indirmesi bir
 * NATIVE arka-plan görevi modülü ister (WorkManager tabanlı). Bu projede SDK sürümü uyuşan
 * böyle bir modül YOK ve sürümü uyuşmayan native modülü tıbbi cihaz APK'sına koymak, aynı
 * gerekçeyle (bkz. `kurulumuBaslat` notu) kabul edilmiyor. Duraklat-devam et, ulaşılabilir ve
 * VERİ KAYBETMEYEN davranıştır.
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
    appState?: Pick<typeof AppState, "addEventListener">;
  } = {},
): Promise<IndirmeSonucu> {
  const hedef = `${FileSystem.cacheDirectory || ""}pemf-vet-${surum.versionCode}.apk`;
  const olustur = deps.createDownloadResumable ?? FileSystem.createDownloadResumable;
  const bilgiAl = deps.getInfoAsync ?? FileSystem.getInfoAsync;
  const sil = deps.deleteAsync ?? FileSystem.deleteAsync;
  const oku = deps.devamOku ?? devamOku;
  const yaz = deps.devamYaz ?? devamYaz;
  const kayitSil = deps.devamSil ?? devamSil;
  const durum = deps.appState ?? AppState;

  // Kayıt yalnız AYNI sürüm + AYNI adres için geçerlidir; sürüm değiştiyse yarım dosya çöptür.
  const kayit = await oku();
  const devamEdilebilir =
    !!kayit && kayit.versionCode === surum.versionCode && kayit.url === surum.url && !!kayit.resumeData;
  if (kayit && !devamEdilebilir) {
    await kayitSil();
    try { await sil(kayit.fileUri, { idempotent: true }); } catch { /* yut */ }
  }

  let duraklatildi = false;
  let dl: FileSystem.DownloadResumable | null = null;

  try {
    dl = olustur(
      surum.url,
      hedef,
      {},
      (p) => {
        if (p.totalBytesExpectedToWrite > 0) {
          onIlerleme?.(p.totalBytesWritten / p.totalBytesExpectedToWrite);
        }
      },
      devamEdilebilir ? kayit?.resumeData : undefined,
    );

    // Arka plana/kilit ekranına geçişte DURAKLAT + diske yaz; öne dönüşte döngü devam ettirir.
    let oneDon: (() => void) | null = null;
    const abone = durum.addEventListener("change", (s: AppStateStatus) => {
      if (s === "active") {
        oneDon?.();
        oneDon = null;
        return;
      }
      if (duraklatildi || !dl) return;
      duraklatildi = true;
      void (async () => {
        try {
          const kaydedilebilir = await dl!.pauseAsync();
          await yaz({ ...kaydedilebilir, versionCode: surum.versionCode } as DevamKaydi);
        } catch { /* duraklatılamadıysa indirme kendi hatasıyla düşer */ }
      })();
    });

    try {
      let sonuc = devamEdilebilir ? await dl.resumeAsync() : await dl.downloadAsync();

      // Duraklatıldıysa `resumeAsync/downloadAsync` sonuçsuz döner → ÖNE DÖNÜNCE devam et.
      while (!sonuc?.uri && duraklatildi) {
        await new Promise<void>((cozumle) => { oneDon = cozumle; });
        duraklatildi = false;
        sonuc = await dl.resumeAsync();
      }

      if (!sonuc?.uri) return { ok: false, hata: "indirme" };

      const bilgi = (await bilgiAl(sonuc.uri)) as { exists?: boolean; size?: number };
      if (!bilgi?.exists || Number(bilgi.size) !== Number(surum.size)) {
        // Yarım/bozuk inen paketi kurmaya ÇALIŞMA → sil (kullanıcı anlaşılmaz bir kurulum
        // hatasıyla karşılaşmasın; sonraki denemede baştan iner).
        try { await sil(sonuc.uri, { idempotent: true }); } catch { /* yut */ }
        await kayitSil();
        return { ok: false, hata: "boyut" };
      }
      await kayitSil(); // tamamlandı → yarım-indirme kaydı kalmasın
      return { ok: true, dosyaUri: sonuc.uri };
    } finally {
      abone.remove();
    }
  } catch {
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
