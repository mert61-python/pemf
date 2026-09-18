// Author: mertaygn, cglrgrkn
/**
 * APK'yı DOĞRUDAN Android paket yükleyicisine teslim eden yerel modülün JS yüzü.
 *
 * ⚠️ `requireOptionalNativeModule` KASITLI: modül herhangi bir nedenle kaydolmazsa (autolinking
 * atlar, eski bir APK'da yoktur) `null` döner ve çağıran taraf paylaşım yedeğine düşer. Fırlatan
 * `requireNativeModule` kullanılsaydı, import ANINDA patlar ve güncelleme akışının tamamı ölürdü.
 * Bkz. `services/mobileUpdate.ts::kurulumuBaslat`.
 */
import { requireOptionalNativeModule } from "expo-modules-core";
import { Platform } from "react-native";

interface ApkInstallerNative {
  kurulumIzniVarMi(): boolean;
  izinEkraniniAc(): Promise<boolean>;
  apkKur(yol: string): Promise<boolean>;
  sha256(yol: string): Promise<string>;
  // Eski APK'larda bu ikisi YOKTUR (2026-08-27'de eklendi) — çağıran taraf yokluğu tolere eder.
  indirmeServisiniBaslat?(baslik: string | null): Promise<boolean>;
  indirmeServisiniDurdur?(): Promise<boolean>;
}

const yerli =
  Platform.OS === "android" ? requireOptionalNativeModule<ApkInstallerNative>("ApkInstaller") : null;

/** Native modül gerçekten yüklü mü? (Yedek yola düşmek gerekip gerekmediğini söyler.) */
export function apkKuruculVarMi(): boolean {
  return yerli !== null;
}

/**
 * "Bilinmeyen kaynaklardan uygulama yükleme" izni verilmiş mi?
 * Modül yoksa `true` döner — izinsizliği varsaymak, yükleyiciyi hiç denememeye yol açardı.
 */
export function kurulumIzniVarMi(): boolean {
  try {
    return yerli ? yerli.kurulumIzniVarMi() : true;
  } catch {
    return true;
  }
}

/** İzin ekranını DOĞRUDAN bu uygulama için açar (kullanıcı Ayarlar'da uygulama aramasın). */
export async function izinEkraniniAc(): Promise<boolean> {
  try {
    return yerli ? await yerli.izinEkraniniAc() : false;
  } catch {
    return false;
  }
}

/** APK'yı paket yükleyicisine gönderir. Başarısızlıkta `false` — çağıran yedeğe düşer. */
export async function apkKur(dosyaUri: string): Promise<boolean> {
  try {
    return yerli ? await yerli.apkKur(dosyaUri) : false;
  } catch {
    return false;
  }
}

/**
 * Dosyanın SHA-256 özeti (küçük harf hex). Modül yoksa ya da hata olursa BOŞ dize döner.
 *
 * ⚠️ Boş dönüş "doğrulama YAPILAMADI" demektir, "doğrulandı" DEĞİL. Çağıran bunu ayırt etmeli:
 * hash alınamıyorsa (eski APK'da modül yok) eski davranış sürer — güncellemeyi hash alınamadı
 * diye engellemek, sahadaki eski sürümleri kalıcı olarak güncellenemez yapardı.
 */
export async function dosyaSha256(dosyaUri: string): Promise<string> {
  try {
    return yerli ? await yerli.sha256(dosyaUri) : "";
  } catch {
    return "";
  }
}

/**
 * İndirme süresince ön-plan servisini başlat (ekran kilidi/arka plan indirmeyi kesmesin —
 * saha bildirimi 2026-08-27). Servis bir GÜVENCEDİR: yokluğu/başarısızlığı indirmeyi düşürmez,
 * yalnız arka plan dayanıklılığı eski (kırılgan) davranışa düşer.
 */
export async function indirmeServisiniBaslat(baslik: string | null): Promise<boolean> {
  try {
    return yerli?.indirmeServisiniBaslat ? await yerli.indirmeServisiniBaslat(baslik) : false;
  } catch {
    return false;
  }
}

/** Ön-plan servisini durdur (indirme bitti/düştü — bildirim kalkar). */
export async function indirmeServisiniDurdur(): Promise<boolean> {
  try {
    return yerli?.indirmeServisiniDurdur ? await yerli.indirmeServisiniDurdur() : false;
  } catch {
    return false;
  }
}
