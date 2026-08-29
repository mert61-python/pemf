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
 * ⚠️ GÜVENLİK MODELİ — ÜÇ KATMAN (güncellendi 2026-08-23):
 *   1. KAYNAK PİNİ (`kaynakGuvenli`): adres yalnız yayın deposunun kendi yolu ya da GitHub nesne
 *      depoları olabilir. Masaüstündeki `net.rs::validate_download_source` ikizi.
 *   2. SHA256 (yerel modül): indirilen paket kurulumdan ÖNCE doğrulanır. Eskiden bu YOKTU ve
 *      "128 MB'ın hash'i mobilde pratik değil" diye gerekçelendirilmişti — doğru gerekçe ama
 *      yanlış sonuç: hash JS'te değil, YEREL modülde 1 MB'lık tamponla AKITILARAK alınır (sabit
 *      bellek). Yayındaki manifest'in kendi notu zaten "SHA256 doğrular" diye söz veriyordu;
 *      artık kod o sözü gerçekten tutuyor. Hash hesaplanamıyorsa (eski APK'da modül yok) akış
 *      SÜRER — doğrulanamıyor diye engellemek sahadaki eski sürümleri kilitlerdi.
 *   3. ANDROID İMZA DOĞRULAMASI: Android, kurulu uygulamayla AYNI anahtarla imzalanmamış bir
 *      APK'yı güncelleme olarak KABUL ETMEZ. Yayın anahtarı geliştiricinin makinesindedir
 *      (%USERPROFILE%\.pemf-keys) → araya giren biri paketi değiştirse bile yeniden imzalayamaz.
 * Boyut kontrolü ayrıca yapılır — yarım/bozuk inen dosyayı kurmaya çalışmayı önler.
 */
import AsyncStorage from "@react-native-async-storage/async-storage";
import * as FileSystem from "expo-file-system/legacy";
import Constants from "expo-constants";
// ⚠️ STATİK import (2026-08-17): burada `await import("expo-sharing")` vardı ve Jest'te
// `A dynamic import callback was invoked without --experimental-vm-modules` ile PATLIYORDU →
// paylaşım YEDEĞİ hiçbir testle sınanamıyor, sessizce ölse fark edilmezdi. Yedek yolun kendisi
// bir emniyet ağı; sınanamayan emniyet ağı yok sayılır. Modül küçük ve zaten bağımlılıkta.
import * as Sharing from "expo-sharing";
import { AppState, Platform } from "react-native";

import {
  apkKur,
  dosyaSha256,
  indirmeServisiniBaslat,
  indirmeServisiniDurdur,
  izinEkraniniAc,
  kurulumIzniVarMi,
} from "../../modules/apk-installer";

/**
 * İndirme sürerken ekranı uyanık tut (2026-08-27 saha bildirimi: "ekranı kilitleyince
 * indirme kesiliyor"). Otomatik ekran kilidi, kesintinin EN SIK tetikleyicisi — indirme
 * boyunca ekran kendiliğinden kilitlenmezse vaka sınıfının çoğu hiç doğmaz.
 *
 * ⚠️ `require` KASITLI (statik import değil): `expo-keep-awake` import ANINDA yerel modül
 * ister; jest'te bu, mobileUpdate'i dolaylı içe aktaran ONLARCA test dosyasına mock dayatırdı.
 * Uyanık tutma bir KOLAYLIKTIR — hiçbir ortamda yokluğu indirmeyi düşüremez (hepsi yutulur).
 */
function ekraniUyanikTut(ac: boolean): void {
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const ka = require("expo-keep-awake");
    if (ac) void ka.activateKeepAwakeAsync?.("pemf-apk-indirme")?.catch?.(() => {});
    else void ka.deactivateKeepAwake?.("pemf-apk-indirme")?.catch?.(() => {});
  } catch {
    /* keep-awake yoksa (jest/eski ortam) sessizce geç */
  }
}

/** Yayın manifest'i — masaüstü client ile AYNI dosya (tek kaynak, ayrı servis yok). */
export const MANIFEST_URL =
  "https://github.com/mert61-python/pemf-update/releases/download/client-app-v1.8.0/manifest.json";

/**
 * İNDİRME KAYNAĞI PİNİ — masaüstü `launcher/core/src/net.rs::validate_download_source` ikizi.
 *
 * ⚠️ Bu kapı olmadan manifest'in `mobile.android.url` alanını etkileyebilen herkes sahadaki tüm
 * telefonlara istediği adresten — `usesCleartextTraffic` açık olduğu için düz `http://` dahil —
 * 128 MB'lık keyfi içerik indirtebilirdi. Masaüstü tarafında bu pin 2026-08-04 denetiminde
 * konmuştu; mobil taraf o gün atlanmıştı (denetim 2026-08-23, bulgu M1).
 *
 * Kabul edilen: repo-yolu pinli `github.com` **veya** açıkça sayılmış GitHub nesne depoları.
 * ⚠️ `.githubusercontent.com` JOKERİ KABUL EDİLMEZ — oraya ücretsiz bir hesap keyfi bayt koyabilir
 * (masaüstünde joker yalnız *yönlendirme hedefleri* için geçerli, kaynak URL'ler için değil).
 */
const IZINLI_NESNE_DEPOLARI = ["objects.githubusercontent.com", "release-assets.githubusercontent.com"];
const YAYIN_REPO_YOLU = "/mert61-python/pemf-update/";

/**
 * Yol, istemci-tarafı normalizasyonuyla bizim gördüğümüzden BAŞKA bir yere çözülebilir mi?
 *
 * ⚠️ HAM METİN üzerinde çalışır, `new URL(...).pathname` üzerinde DEĞİL — ölçülerek öyle yazıldı:
 * WHATWG ayrıştırıcısı `\` karakterini sessizce `/`'a çeviriyor, yani ayrıştırılmış yolu denetlemek
 * o vakayı hiç göremez. İndiriciye giden şey zaten HAM dizedir; onu bizim ayrıştırıcımızın değil,
 * indiricinin ayrıştırıcısı çözecek. İki ayrıştırıcının aynı kararı vereceğine güvenmek yerine
 * şüpheli yazımı baştan reddediyoruz (masaüstü `net.rs::path_has_traversal` ile aynı yaklaşım).
 */
function yolKacisiVar(hamYol: string): boolean {
  const s = hamYol.split(/[?#]/)[0];
  const k = s.toLowerCase();
  if (k.includes("%2e") || k.includes("%2f") || k.includes("%5c") || s.includes("\\")) return true;
  // Baştaki '/' yüzünden ilk parça daima boştur; onu atla.
  return s.split("/").slice(1).some((p) => p === "." || p === ".." || p === "");
}

export function kaynakGuvenli(url: string): boolean {
  if (typeof url !== "string" || !url) return false;
  let u: URL;
  try {
    u = new URL(url);
  } catch {
    return false;
  }
  if (u.protocol !== "https:") return false;
  // Ham yol: şemadan sonraki ilk '/'den itibaren (authority hariç).
  const semasiz = url.slice(url.indexOf("://") + 3);
  const kesme = semasiz.search(/[/?#]/);
  if (yolKacisiVar(kesme < 0 ? "" : semasiz.slice(kesme))) return false;
  if (IZINLI_NESNE_DEPOLARI.includes(u.hostname)) return true;
  // `github.com` yalnız BİZİM repo yolumuzla; "GitHub'da bir yer" yetmez.
  return u.hostname === "github.com" && u.pathname.startsWith(YAYIN_REPO_YOLU);
}

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
    // ⚠️ FAIL-CLOSED: pinsiz/şüpheli adres "güncelleme YOK" sayılır. Güncellemeyi kaybetmek,
    // yanlış kaynaktan 128 MB indirmekten iyidir (masaüstü paritesi — bkz. kaynakGuvenli).
    if (!kaynakGuvenli(String(a.url))) return { varMi: false, sebep: "eksik_alan" };

    // ⚠️ TİP DOĞRULAMASI (denetim 2026-08-23, M8). Eskiden `Number(a.versionCode) <= mevcut`
    // karşılaştırması yapılıyordu; sayısal olmayan ama truthy bir değerde (`"v29"`, `{}`)
    // `Number()` NaN olur ve NaN ile yapılan HER karşılaştırma false döner → "güncel" kontrolü
    // ATLANIR ve güncelleme VAR denir (fail-open). Manifest'in `mobile` bloğu üretilmiyor, elle
    // düzenleniyor (`CARRY_ONLY`) — yani bu gerçekçi bir yayın kazası. Sonuç: her soğuk açılışta
    // 128 MB indirilir, Android reddeder ve döngü tekrarlar; üstelik erteleme bayrağı da tutmaz
    // (`atlandiMi` içinde `Number(...) || 0` → hep 0), yani bandı susturmanın yolu kalmaz.
    // ⚠️ `Number(true) === 1`: boolean tip kapısını sessizce geçerdi. Manifest sayısal alanları
    // yalnız sayı ya da sayı-metni olabilir; başka her tip biçim hatasıdır.
    const sayisalTip = (v: unknown) => typeof v === "number" || typeof v === "string";
    if (!sayisalTip(a.versionCode) || !sayisalTip(a.size)) return { varMi: false, sebep: "eksik_alan" };
    const vc = Number(a.versionCode);
    const boyut = Number(a.size);
    if (!Number.isInteger(vc) || vc <= 0) return { varMi: false, sebep: "eksik_alan" };
    if (!Number.isFinite(boyut) || boyut <= 0) return { varMi: false, sebep: "eksik_alan" };
    if (typeof a.version !== "string" || !a.version) return { varMi: false, sebep: "eksik_alan" };

    if (vc <= mevcutVersionCode()) return { varMi: false, sebep: "guncel" };
    // ⚠️ NORMALİZE EDİLMİŞ değer döner: ham `versionCode` dosya adına (`pemf-vet-<vc>.apk`) ve
    // erteleme anahtarına giriyor; metin kalırsa erteleme hiçbir zaman eşleşmez.
    return { varMi: true, surum: { ...(a as MobilSurum), versionCode: vc, size: boyut } };
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
  hata?: "indirme" | "boyut" | "sunucu" | "butunluk";
}

/**
 * KESİNTİ SONRASI OTOMATİK DEVAM (2026-08-27, saha bildirimi: "ekranı kilitleyince /
 * arka plana alınca indirme kesiliyor, sürekli kesilmesin").
 *
 * ⚠️ Bu DURAKLATMA DEĞİLDİR — o bilerek yok (bkz. `_apkIndirGercek` başlığı ve casus test).
 * Buradaki mekanizma tam tersi: indirme İSTEMSİZ düştüğünde (Doze ağı askıya aldı, OEM pil
 * katili soketi kesti) kullanıcıya "tekrar deneyin" demek yerine KALDIĞI BAYTTAN kendiliğinden
 * sürdürmek. Her deneme diskteki kısmi dosyadan devam eder → kesinti ne kadar sık olursa olsun
 * İLERLEME HEP BİRİKİR; kayıp yalnız kesinti anındaki soket tamponudur.
 *
 * - Uygulama ÖN-PLANDAYSA kısa nefes (3 sn) sonra hemen devam edilir.
 * - ARKA PLANDAYSA deneme hakkı boşa yakılmaz: 'active' olana kadar (tavan 30 dk) beklenir —
 *   `AppState` aboneliği YALNIZ bu anda, geçici olarak kurulur (casus test mutlu-yolda
 *   AppState'e hiç abone olunmadığını kilitlemeye devam eder).
 * - TIKANMA BEKÇİSİ: askıya alınan ağda `downloadAsync` reddedilmeden SONSUZA DEK askıda
 *   kalabilir. Ön-plandayken 90 sn boyunca TEK BAYT ilerleme yoksa deneme `pauseAsync` ile
 *   düşürülür (yerel iş iptal olur, söz reddedilir) ve döngü diskten devamla yeni deneme açar.
 */
const AZAMI_YENIDEN_DENEME = 40;
const AKTIF_NEFES_MS = 3_000;
const ARKA_PLAN_TAVANI_MS = 30 * 60 * 1000;
const TIKANMA_ESIGI_MS = 90_000;
const TIKANMA_KONTROL_MS = 15_000;

function _uygulamaDurumu(): string {
  // Test mock'ları `currentState` taşımaz → bilinmiyorsa "active" varsay (fail-open:
  // yanlışlıkla beklemek, yanlışlıkla denemekten kötüdür — deneme zaten zararsız).
  return (AppState as { currentState?: string }).currentState ?? "active";
}

/** Kesinti sonrası yeni denemeden önce bekle (üstteki blok yorumun gerekçesiyle). */
async function _kesintiSonrasiBekle(): Promise<void> {
  if (_uygulamaDurumu() === "active") {
    await new Promise((coz) => setTimeout(coz, AKTIF_NEFES_MS));
    return;
  }
  await new Promise<void>((coz) => {
    let abonelik: { remove(): void } | null = null;
    const bitir = () => {
      clearTimeout(tavan);
      try { abonelik?.remove(); } catch { /* yut */ }
      coz();
    };
    const tavan = setTimeout(bitir, ARKA_PLAN_TAVANI_MS);
    try {
      abonelik = AppState.addEventListener("change", (d: string) => {
        if (d === "active") bitir();
      }) as { remove(): void };
    } catch {
      bitir(); // AppState yoksa bekleme atlanır — deneme yine de yapılır
    }
  });
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

/** `apkIndir`/`_apkIndirGercek` test-enjeksiyon noktaları (tek tip — ikisi aynı sözleşme). */
interface IndirmeDeps {
  createDownloadResumable?: typeof FileSystem.createDownloadResumable;
  getInfoAsync?: typeof FileSystem.getInfoAsync;
  deleteAsync?: typeof FileSystem.deleteAsync;
  devamOku?: typeof devamOku;
  devamYaz?: typeof devamYaz;
  devamSil?: typeof devamSil;
  readDirectoryAsync?: typeof FileSystem.readDirectoryAsync;
  sha256Hesapla?: typeof dosyaSha256;
  /** Test kancası: kesinti-sonrası yeniden deneme sayısı (varsayılan AZAMI_YENIDEN_DENEME). */
  azamiYenidenDeneme?: number;
  /** Test kancası: denemeler arası bekleme (varsayılan _kesintiSonrasiBekle). */
  kesintiBekle?: () => Promise<void>;
}

export async function apkIndir(
  surum: MobilSurum,
  onIlerleme?: IlerlemeCb,
  deps: IndirmeDeps = {},
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
  deps: IndirmeDeps = {},
): Promise<IndirmeSonucu> {
  const hedef = `${FileSystem.cacheDirectory || ""}pemf-vet-${surum.versionCode}.apk`;
  const olustur = deps.createDownloadResumable ?? FileSystem.createDownloadResumable;
  const bilgiAl = deps.getInfoAsync ?? FileSystem.getInfoAsync;
  const sil = deps.deleteAsync ?? FileSystem.deleteAsync;
  const oku = deps.devamOku ?? devamOku;
  const yaz = deps.devamYaz ?? devamYaz;
  const kayitSil = deps.devamSil ?? devamSil;

  const beklenen = Number(surum.size);

  // ⚠️ ESKİ PAKETLERİ TEMİZLE (denetim 2026-08-23, M7). Başarı yolunda yalnız AsyncStorage izi
  // siliniyor, ~128 MB'lık APK bırakılıyordu; eski dosyayı silen tek yol (`kayit && !ayniIs`) bir
  // sonraki sürümde `kayit === null` olduğu için HİÇ çalışmıyordu. Kurulum başarılı olunca
  // uygulamanın versionCode'u dosyanınkine eşitlenir → `guncellemeVarMi` "güncel" der → `apkIndir`
  // o sürüm için bir daha çağrılmaz, yani temizlik penceresi kapanır. Her yayında bir dosya
  // birikiyordu; depolaması dolu bir telefonda bu, bir sonraki güncellemenin İNEMEMESİNE varır.
  //
  // ⚠️ Yalnız BİZİM ürettiğimiz ad kalıbı ve YALNIZ bu indirmenin hedefi DIŞINDAKİLER silinir.
  // Hata yutulur: temizlik bir kolaylıktır, güncellemeyi düşürmesi kabul edilemez.
  {
    const dizinOku = deps.readDirectoryAsync ?? FileSystem.readDirectoryAsync;
    const kokDizin = FileSystem.cacheDirectory || "";
    try {
      const adlar = await dizinOku(kokDizin);
      const bizim = /^pemf-vet-\d+\.apk$/;
      await Promise.all(
        (adlar || [])
          .filter((ad) => bizim.test(ad) && `${kokDizin}${ad}` !== hedef)
          .map((ad) => sil(`${kokDizin}${ad}`, { idempotent: true }).catch(() => {})),
      );
    } catch { /* dizin okunamadı → temizlik atlanır, indirme sürer */ }
  }

  // Kayıt yalnız AYNI sürüm + AYNI adres için geçerli; sürüm/adres değiştiyse yarım dosya çöptür.
  const kayit = await oku();
  const ayniIs = !!kayit && kayit.versionCode === surum.versionCode && kayit.url === surum.url;
  if (kayit && !ayniIs) {
    await kayitSil();
    try { await sil(kayit.fileUri, { idempotent: true }); } catch { /* yut */ }
  }

  // ⚠️ İlk denemede dış bloktaki `ayniIs` geçerli; SONRAKİ denemelerde kayıt bu işin kendisi
  // tarafından yazılmış olur → devam hakkı her denemede yeniden türetilir (aksi hâlde ilk
  // deneme "farklı iş"le başlayan bir indirme, kesintiden sonra hep sıfırdan başlardı).
  const birDeneme = async (devamEdilebilir: boolean): Promise<IndirmeSonucu> => {
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
    if (devamEdilebilir) {
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
    let sonIlerlemeMs = Date.now();
    const dl = olustur(
      surum.url,
      hedef,
      {},
      (p) => {
        sonIlerlemeMs = Date.now(); // tıkanma bekçisi için: bayt aktığı sürece deneme sağlıklı
        // ⚠️ İlerleme, devam edilen indirmede de 0'dan değil KALDIĞI YERDEN gösterilmeli
        // (kullanıcının gördüğü yüzde geri gitmesin). Yerel modül `resumeData`yı sayaçlarına
        // zaten ekliyor; toplam beklenen bilinmiyorsa manifest boyutuna düşülür.
        const toplam = p.totalBytesExpectedToWrite > 0 ? p.totalBytesExpectedToWrite : beklenen;
        const yazilan = p.totalBytesWritten > 0 ? p.totalBytesWritten : baslangic;
        if (toplam > 0) onIlerleme?.(Math.min(1, yazilan / toplam));
      },
      devamBaytlari,
    );

    // TIKANMA BEKÇİSİ: askıya alınmış ağda `downloadAsync` reddedilmeden SONSUZA DEK bekleyebilir
    // (arka planda ağı kesilen soket, ön-plana dönüşte hep hata fırlatmıyor — bazen sadece susuyor).
    // Ön-plandayken 90 sn hiç bayt akmadıysa yerel işi `pauseAsync` ile düşür → söz reddedilir →
    // dış döngü diskteki kısmi dosyadan YENİ denemeyle sürer. ⚠️ Bu, arka-plan DURAKLATMASI
    // DEĞİLDİR (o bilerek yok — üstteki başlık): yalnız ÖLÜ bir denemenin enkazı kaldırılıyor.
    const bekci = setInterval(() => {
      if (_uygulamaDurumu() === "active" && Date.now() - sonIlerlemeMs > TIKANMA_ESIGI_MS) {
        clearInterval(bekci);
        void (dl as { pauseAsync?: () => Promise<unknown> }).pauseAsync?.()?.catch?.(() => {});
      }
    }, TIKANMA_KONTROL_MS);

    let sonuc: Awaited<ReturnType<typeof dl.downloadAsync>>;
    try {
      sonuc = await dl.downloadAsync();
    } finally {
      clearInterval(bekci);
    }
    if (!sonuc?.uri) return { ok: false, hata: "indirme" };

    // ⚠️ HTTP DURUMU DENETLENİR (denetim 2026-08-23). Yerel katman gövdeyi durumdan BAĞIMSIZ
    // olarak dosyaya yazar: manifest'teki varlık silinmiş/yanlış etikete taşınmışsa (yayında
    // yaşanmış bir durum) 404 HTML'i APK olarak diske iner. Eskiden bu yalnız boyut kapısına
    // takılıyor ve kullanıcıya "bağlantınızı kontrol edip tekrar deneyin" deniyordu — tekrar
    // denemek ASLA işe yaramaz. Ayrı sonuç kodu, arayüzün doğru şeyi söylemesini sağlar.
    // 416 özellikle önemlidir: devam edilen indirmede gövde kısmi dosyanın SONUNA eklenir.
    // ⚠️ Durum BİLİNMİYORSA (alan yok) akış değişmez — arkada boyut kapısı zaten duruyor.
    const durum = (sonuc as { status?: number }).status;
    if (typeof durum === "number" && (durum < 200 || durum >= 300)) {
      try { await sil(sonuc.uri, { idempotent: true }); } catch { /* yut */ }
      await kayitSil();
      return { ok: false, hata: "sunucu" };
    }

    const bilgi = (await bilgiAl(sonuc.uri)) as { exists?: boolean; size?: number };
    if (!bilgi?.exists || Number(bilgi.size) !== beklenen) {
      // Yarım/bozuk inen paketi kurmaya ÇALIŞMA → sil (kullanıcı anlaşılmaz bir kurulum
      // hatasıyla karşılaşmasın; sonraki denemede baştan, temiz iner).
      try { await sil(sonuc.uri, { idempotent: true }); } catch { /* yut */ }
      await kayitSil();
      return { ok: false, hata: "boyut" };
    }
    // ⚠️ BÜTÜNLÜK DOĞRULAMASI (denetim 2026-08-23, M11). Boyut kapısı yeterli DEĞİL: aynı boyutta
    // farklı içerik (yarım-devam karışımı, bozuk aktarım) kolayca oluşur. Yayındaki manifest'in
    // kendi notu zaten "SHA256 doğrular" diye söz veriyordu; kod o sözü tutmuyordu ve APK,
    // güncelleme zincirindeki TEK doğrulanmayan varlıktı (launcher paketleri doğrulanıyor).
    //
    // ⚠️ Hash HESAPLANAMIYORSA (eski APK'da yerel modül yok → boş dize) ya da manifest sha
    // taşımıyorsa akış SÜRER: doğrulanamıyor diye engellemek, sahadaki eski sürümleri kalıcı
    // olarak güncellenemez yapardı. Yani bu kapı yalnız AÇIKÇA yanlış olanı eler.
    const sha = deps.sha256Hesapla ?? dosyaSha256;
    const beklenenSha = String(surum.sha256 || "").toLowerCase();
    if (beklenenSha) {
      const gercek = (await sha(sonuc.uri)).toLowerCase();
      if (gercek && gercek !== beklenenSha) {
        try { await sil(sonuc.uri, { idempotent: true }); } catch { /* yut */ }
        await kayitSil();
        return { ok: false, hata: "butunluk" };
      }
    }
    await kayitSil(); // tamamlandı → yarım-indirme izi kalmasın
    return { ok: true, dosyaUri: sonuc.uri };
  } catch {
    // ⚠️ Kayıt ve kısmi dosya BİLEREK bırakılır: ağ koptuğunda bir sonraki deneme kaldığı
    // yerden sürebilsin (asıl istenen davranış). Bozuk dosyayı boyut kapısı zaten eliyor.
    return { ok: false, hata: "indirme" };
  }
  };

  // ── KESİNTİ-SONRASI OTOMATİK DEVAM DÖNGÜSÜ (gerekçe: dosya başındaki blok yorum) ──
  // Yalnız "indirme" (ağ) hatası yeniden denenir: "sunucu"/"boyut"/"butunluk" DETERMİNİSTİK
  // sonuçlardır — tekrar etmek durumu değiştirmez, arayüz doğru metni hemen göstermelidir.
  // Ekran, indirme boyunca uyanık tutulur; ön-plan servisi arka planda ağı canlı tutar
  // (ikisi de kolaylık: yokluğu akışı düşürmez).
  const azami = deps.azamiYenidenDeneme ?? AZAMI_YENIDEN_DENEME;
  const bekle = deps.kesintiBekle ?? _kesintiSonrasiBekle;
  ekraniUyanikTut(true);
  // ⚠️ Başlatma sözü TUTULUR ve durdurmadan önce beklenir — saha çökmesi 2026-08-29
  // (Galaxy S23 / Android 16): indirme çok hızlı bittiğinde (ör. APK zaten tam inmiş) durdurma,
  // başlatma daha yerli tarafa varmadan gönderiliyordu. Çerçeve `startForegroundService()` borcunu
  // ödenmemiş sayıp uygulamayı öldürüyordu — kullanıcı "Güncelle"ye basar basmaz kapanma.
  // Servis tarafı da ayrıca sağlamlaştırıldı (IndirmeServisi: startForeground her yolda ilk iş),
  // ama sırayı burada da korumak iki tarafı birbirine bağımlı olmaktan çıkarır.
  const servisSozu = Promise.resolve(
    indirmeServisiniBaslat?.(`PEMF Vet ${surum.version} indiriliyor`),
  ).catch(() => {});
  try {
    for (let deneme = 0; ; deneme++) {
      const sonuc = await birDeneme(deneme === 0 ? ayniIs : true);
      if (sonuc.ok || sonuc.hata !== "indirme" || deneme >= azami) return sonuc;
      await bekle();
    }
  } finally {
    ekraniUyanikTut(false);
    await servisSozu;
    await Promise.resolve(indirmeServisiniDurdur?.()).catch(() => {});
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
