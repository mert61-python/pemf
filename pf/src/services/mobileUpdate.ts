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
// ⚠️ STATİK import (2026-08-17): burada `await import("expo-sharing")` vardı ve Jest'te
// `A dynamic import callback was invoked without --experimental-vm-modules` ile PATLIYORDU →
// paylaşım YEDEĞİ hiçbir testle sınanamıyor, sessizce ölse fark edilmezdi. Yedek yolun kendisi
// bir emniyet ağı; sınanamayan emniyet ağı yok sayılır. Modül küçük ve zaten bağımlılıkta.
import * as Sharing from "expo-sharing";
import { Platform } from "react-native";

import { apkKur, izinEkraniniAc, kurulumIzniVarMi } from "../../modules/apk-installer";

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

/**
 * AÇILIŞ KAPISINDA "şimdilik devam et" denen sürüm (2026-08-16).
 *
 * ⚠️ KASITEN YALNIZ BELLEKTE — diske YAZILMAZ. Kullanıcı bir açılışta ertelediğinde uygulama
 * içindeki bant aynı güncellemeyi hemen yeniden dayatmasın diye vardır; ama SONRAKİ soğuk
 * açılışta kapı yeniden sorar. Kalıcı yazsaydık kullanıcı bir kez "sonra" deyip güncellemeyi
 * SONSUZA DEK kapatabilirdi — tıbbi cihazda düzeltme taşıyan bir yayının ulaşamaması demek.
 */
let _atlananVersionCode = 0;

/** Kapıda ertelenen sürümü işaretle (yalnız bu açılış için). */
export function guncellemeyiAtla(versionCode: number): void {
  _atlananVersionCode = Number(versionCode) || 0;
}

/** Bu açılışta bu sürüm ertelendi mi? */
export function atlandiMi(versionCode: number): boolean {
  return _atlananVersionCode > 0 && Number(versionCode) === _atlananVersionCode;
}

/** Yalnız testler için — modül durumunu sıfırlar. */
export function _atlamayiSifirla(): void {
  _atlananVersionCode = 0;
}

/**
 * [5.7a] KURULUM ERTELEMESİ (2. tur denetimi, sahip onayı 2026-08-20) — `atlandiMi`den AYRI bayrak.
 *
 * Kapı "Şimdilik devam et" ile kapatıldığında UÇUŞTA kalan `guncelle()` bundan habersizdi:
 * indirme bitince Android yükleyicisi kullanıcının o anki işinin ÜSTÜNE sormadan açılıyordu.
 * Bu bayrak yalnız OTOMATİK yükleyici açılışını keser; bandı SUSTURMAZ (paket hazır — kullanıcı
 * banttan "Güncelle"ye dokununca kurulur). `guncelle()` girişte bayrağı TEMİZLER: açık kullanıcı
 * niyeti ertelemeyi kaldırır — erteleme kalıcı kilide dönemez ("güncelleme ZORUNLU KILINAMAZ"ın
 * ayna kuralı). ⚠️ KASITEN yalnız bellekte — atlandiMi ile aynı gerekçe.
 */
let _kurulumErtelenenVC = 0;

/** Uçuştaki/hazır paketin kurulumunu bu açılışta OTOMATİK açma. */
export function kurulumunuErtele(versionCode: number): void {
  _kurulumErtelenenVC = Number(versionCode) || 0;
}

/** Bu sürümün otomatik kurulum açılışı ertelendi mi? */
export function kurulumErtelendiMi(versionCode: number): boolean {
  return _kurulumErtelenenVC > 0 && Number(versionCode) === _kurulumErtelenenVC;
}

/** Açık kullanıcı niyeti (yeni "Güncelle" dokunuşu) ertelemeyi kaldırır. */
export function kurulumErtelemesiniKaldir(versionCode: number): void {
  if (kurulumErtelendiMi(versionCode)) _kurulumErtelenenVC = 0;
}

/** Yalnız testler için — modül durumunu sıfırlar. */
export function _kurulumErtelemesiniSifirla(): void {
  _kurulumErtelenenVC = 0;
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
/**
 * SÜREN indirme (2026-08-17). Açılış kapısında indirmeye başlayıp "Şimdilik devam et" diyen
 * kullanıcı, içerideki bantta yine "Güncelle"ye basabilir. Koruma olmadan AYNI dosyaya İKİ
 * yazıcı açılır: boyut tutmaz, dosya silinir ve kullanıcı sebepsiz "İndirme eksik kaldı" görür.
 * Aynı sürüm için ikinci çağrı, YENİ indirme başlatmak yerine sürene abone olur → bant, kapının
 * bıraktığı yüzdeden devam eder (kullanıcı yüzdenin sıfırlandığını görmez).
 */
interface SurenIndirme {
  anahtar: string;
  aboneler: Set<IlerlemeCb>;
  sonOran: number;
  sozu: Promise<IndirmeSonucu>;
}
let _suren: SurenIndirme | null = null;

/** Yalnız testler için — süren indirme durumunu sıfırlar. */
export function _indirmeyiSifirla(): void {
  _suren = null;
}

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
  const anahtar = `${surum.versionCode}|${surum.url}`;

  if (_suren && _suren.anahtar === anahtar) {
    if (onIlerleme) {
      _suren.aboneler.add(onIlerleme);
      onIlerleme(_suren.sonOran); // yeni abone MEVCUT yüzdeyi görsün, 0'dan başlamasın
    }
    try {
      return await _suren.sozu;
    } finally {
      if (onIlerleme) _suren?.aboneler.delete(onIlerleme);
    }
  }

  const durum: SurenIndirme = {
    anahtar,
    aboneler: new Set(onIlerleme ? [onIlerleme] : []),
    sonOran: 0,
    sozu: undefined as unknown as Promise<IndirmeSonucu>,
  };
  durum.sozu = _apkIndirGercek(
    surum,
    (o) => {
      durum.sonOran = o;
      durum.aboneler.forEach((f) => f(o));
    },
    deps,
  );
  _suren = durum;
  try {
    return await durum.sozu;
  } finally {
    if (_suren === durum) _suren = null;
  }
}

async function _apkIndirGercek(
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
    // ⚠️ 2026-08-17 SAHA BİLDİRİMİ — "geri çıkma tuşuna bastım, tekrar yüzde 0'dan başladı".
    // TAM inmiş dosya artık KAYITTAN BAĞIMSIZ tanınır. Eskiden bu kontrol `ayniIs` kapısının
    // içindeydi, kayıt ise indirme BİTİNCE siliniyordu (`kayitSil`) → kurulumu onaylamadan çıkan
    // kullanıcı "Güncelle"ye bir daha bastığında hazır duran 128 MB'ı SIFIRDAN indiriyordu.
    // Hızlı yol ölüydü; dosyanın kendisi tek doğru kanıttır (ad zaten sürüm koduna bağlı).
    const hazir = (await bilgiAl(hedef)) as { exists?: boolean; size?: number };
    if (hazir?.exists && Number(hazir.size) === beklenen) {
      await kayitSil();
      return { ok: true, dosyaUri: hedef };
    }

    // Diskteki kısmi dosya → devam noktası.
    let devamBaytlari: string | undefined;
    if (ayniIs) {
      const kismi = hazir;
      const boyut = Number(kismi?.size ?? 0);
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

/** `kurulumuBaslat` sonucu — arayüz kullanıcıya ne söyleyeceğini buradan bilir. */
export type KurulumSonucu =
  /** Paket yükleyici açıldı; onay kullanıcıda. */
  | "acildi"
  /** "Bilinmeyen kaynak" izni yok; izin ekranı açıldı, kullanıcı izni verip tekrar denemeli. */
  | "izin_gerekli"
  /** Yükleyici açılamadı, paylaşım sayfasına düşüldü (yedek yol). */
  | "paylasim"
  /** Hiçbir yol açılamadı. */
  | "hata";

/**
 * İndirilen APK'yı sistem kurulumuna teslim et (Android). Kullanıcı onaylar, Android kurar.
 *
 * ⚠️ 2026-08-17 SAHA BİLDİRİMİ — "indirme bitince paylaşma ekranı geliyor, direkt yüklemeye
 * geçmesi gerekiyor; paylaşıp napcak kullanıcı apk'yı". Haklı: eski yol `expo-sharing` idi ve
 * **hiçbir zaman çalışamazdı**. `shareAsync` bir ACTION_SEND niyeti üretir; Android paket
 * yükleyicisi ACTION_SEND'i DEĞİL, ACTION_VIEW/INSTALL_PACKAGE'ı karşılar → seçicide yalnız
 * WhatsApp/Telegram/Drive çıkıyordu. Eski yorumdaki "kullanıcı 'Paket yükleyici'yi seçer"
 * varsayımı YANLIŞTI.
 *
 * Çözüm: `modules/apk-installer` — uygulamanın KENDİ yerel modülü, doğru bayraklarla ACTION_VIEW
 * kurar (FileProvider + FLAG_GRANT_READ_URI_PERMISSION). Dış bağımlılık yok; `expo-intent-launcher`
 * hâlâ SDK 56 için yalnız canary ve tıbbi cihaz APK'sına canary native modül konmaz.
 *
 * ⚠️ PAYLAŞIM YEDEĞİ DURUYOR: yerel modül herhangi bir nedenle kaydolmazsa özellik SESSİZCE
 * ölmesin diye. Yedek "kötü ama hiç yoktan iyi" bir yoldur; sonuç `"paylasim"` olarak DÖNER ki
 * arayüz kullanıcıya doğru şeyi söyleyebilsin.
 *
 * ⚠️ Asıl güvenlik kapısı değişmedi: Android, kurulu uygulamayla AYNI anahtarla imzalanmamış bir
 * APK'yı güncelleme olarak KABUL ETMEZ (bkz. modül başlığı). Sessiz kurulum YOKTUR.
 */
/* [17. parti — adversaryal inceleme] ÇİFT-YÜKLEYİCİ YARIŞI: kapı indirme uçuştayken "Şimdilik
 * devam et" + banttan "Güncelle" dokunuşu, aynı indirme sözüne abone İKİ kanca örneğini (kapının
 * ölü örneği + bandınki) aynı anda kurulum kapısından geçirebilir — iki ACTION_VIEW niyeti (izin
 * yoksa izin ekranı iki kez). Aynı URI için UÇUŞTAKİ açılış sözü paylaşılır: iki çağrı tek
 * yükleyici niyetine düşer; söz çözülünce yeni çağrı yine açar ("Kurulumu tekrar aç" bozulmaz). */
let _acilisSozu: { uri: string; sozu: Promise<KurulumSonucu> } | null = null;

export async function kurulumuBaslat(dosyaUri: string): Promise<KurulumSonucu> {
  if (_acilisSozu && _acilisSozu.uri === dosyaUri) return _acilisSozu.sozu;

  const sozu = _kurulumuBaslatIc(dosyaUri).finally(() => {
    _acilisSozu = null;
  });
  _acilisSozu = { uri: dosyaUri, sozu };
  return sozu;
}

async function _kurulumuBaslatIc(dosyaUri: string): Promise<KurulumSonucu> {
  if (Platform.OS !== "android") return "hata";

  // 1) İzin kapısı — "bilinmeyen kaynak" kapalıyken yükleyiciyi açmak kullanıcıya anlaşılmaz bir
  //    ret gösterir. Doğrudan doğru ayar ekranına götür.
  if (!kurulumIzniVarMi()) {
    await izinEkraniniAc();
    return "izin_gerekli";
  }

  // 2) ASIL YOL — doğrudan paket yükleyici.
  if (await apkKur(dosyaUri)) return "acildi";

  // 3) YEDEK — yerel modül yoksa paylaşım sayfası (kullanıcı dosyayı bir yere kaydedip elle
  //    kurabilir). Tek başına yeterli değil, ama akışı tamamen ölü bırakmaktan iyidir.
  try {
    if (!(await Sharing.isAvailableAsync())) return "hata";
    await Sharing.shareAsync(dosyaUri, {
      mimeType: "application/vnd.android.package-archive",
      dialogTitle: "Güncellemeyi kur",
    });
    return "paylasim";
  } catch {
    return "hata";
  }
}
