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
