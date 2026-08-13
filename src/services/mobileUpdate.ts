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

/**
 * APK'yı indir + BOYUT doğrula. Boyut tutmazsa dosyayı SİLER (yarım paket kurulmaya çalışılmaz).
 *
 * Dosya adı sürüm koduna bağlanır: bir önceki denemeden kalan bayat APK yeni sürüm sanılmaz
 * (launcher self-update'inde alınan dersin aynısı).
 */
export async function apkIndir(
  surum: MobilSurum,
  onIlerleme?: IlerlemeCb,
  deps: {
    createDownloadResumable?: typeof FileSystem.createDownloadResumable;
    getInfoAsync?: typeof FileSystem.getInfoAsync;
    deleteAsync?: typeof FileSystem.deleteAsync;
  } = {},
): Promise<IndirmeSonucu> {
  const hedef = `${FileSystem.cacheDirectory || ""}pemf-vet-${surum.versionCode}.apk`;
  const olustur = deps.createDownloadResumable ?? FileSystem.createDownloadResumable;
  const bilgiAl = deps.getInfoAsync ?? FileSystem.getInfoAsync;
  const sil = deps.deleteAsync ?? FileSystem.deleteAsync;

  try {
    const dl = olustur(surum.url, hedef, {}, (p) => {
      if (p.totalBytesExpectedToWrite > 0) {
        onIlerleme?.(p.totalBytesWritten / p.totalBytesExpectedToWrite);
      }
    });
    const sonuc = await dl.downloadAsync();
    if (!sonuc?.uri) return { ok: false, hata: "indirme" };

    const bilgi = (await bilgiAl(sonuc.uri)) as { exists?: boolean; size?: number };
    if (!bilgi?.exists || Number(bilgi.size) !== Number(surum.size)) {
      // Yarım/bozuk inen paketi kurmaya ÇALIŞMA → sil (kullanıcı anlaşılmaz bir kurulum
      // hatasıyla karşılaşmasın; sonraki denemede baştan iner).
      try { await sil(sonuc.uri, { idempotent: true }); } catch { /* yut */ }
      return { ok: false, hata: "boyut" };
    }
    return { ok: true, dosyaUri: sonuc.uri };
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
