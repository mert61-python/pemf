package expo.modules.apkinstaller

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.core.content.FileProvider
import expo.modules.kotlin.exception.Exceptions
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition
import java.io.File

/**
 * APK'yi DOGRUDAN Android paket yukleyicisine teslim eder.
 *
 * NEDEN YEREL BIR MODUL (2026-08-17, sahip bildirimi: "indirme bitince paylasma ekrani geliyor,
 * direkt yuklemeye gecmesi gerekiyor; paylasip napcak kullanici apk'yi"):
 *
 * Onceki yol `expo-sharing` idi ve ASLA calisamazdi: `Sharing.shareAsync` bir ACTION_SEND
 * niyeti uretir; Android paket yukleyicisi ACTION_SEND'i DEGIL, ACTION_VIEW/INSTALL_PACKAGE'i
 * karsilar. Bu yuzden secicide yalniz WhatsApp/Telegram/Drive gibi paylasim hedefleri cikiyordu.
 * `Linking.openURL` de ise yaramaz: RN ACTION_VIEW'a FLAG_GRANT_READ_URI_PERMISSION EKLEMEZ,
 * yukleyici content:// adresini okuyamaz. `expo-intent-launcher`in SDK 56 icin KARARLI surumu
 * yok (yalnizca canary) -> tibbi cihaz APK'sina canary native modul konmaz.
 *
 * Kalan dogru yol: dogru bayraklarla ACTION_VIEW'i kendimiz kurmak. Modul dis bagimlilik
 * icermez, uygulamanin kendi kaynagindadir ve tek is yapar.
 *
 * GUVENLIK: burasi bir kurulum KAPISI degil. Android, kurulu uygulamayla AYNI anahtarla
 * imzalanmamis APK'yi guncelleme olarak KABUL ETMEZ; asil dogrulama isletim sistemindedir.
 * Kullanici onayi da her zaman sistem tarafindan alinir (sessiz kurulum YOKTUR).
 */
class ApkInstallerModule : Module() {

  private val context: Context
    get() = appContext.reactContext ?: throw Exceptions.ReactContextLost()

  override fun definition() = ModuleDefinition {
    Name("ApkInstaller")

    /**
     * "Bilinmeyen kaynaklardan uygulama yukleme" izni verilmis mi?
     * Android 8 oncesinde boyle bir uygulama-basina izin yoktur -> her zaman true.
     */
    Function("kurulumIzniVarMi") {
      if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
        true
      } else {
        context.packageManager.canRequestPackageInstalls()
      }
    }

    /**
     * Izin ekranini DOGRUDAN bu uygulama icin acar. Kullaniciya "Ayarlar'a gidin, uygulamayi
     * bulun, izni acin" demek yerine tek dokunusla dogru ekrana goturur.
     */
    AsyncFunction("izinEkraniniAc") {
      if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return@AsyncFunction false
      val intent = Intent(
        Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
        Uri.parse("package:${context.packageName}")
      ).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
      baslat(intent)
      true
    }

    /**
     * APK'yi paket yukleyicisine gonderir. `yol` bir `file://` adresi ya da duz dosya yolu olabilir.
     *
     * FileProvider ZORUNLU: Android 7'den beri intent'e `file://` koymak FileUriExposedException
     * firlatir. FLAG_GRANT_READ_URI_PERMISSION olmadan da yukleyici dosyayi okuyamaz ("paket
     * ayristirilirken sorun olustu"). Ikisi de burada veriliyor.
     */
    AsyncFunction("apkKur") { yol: String ->
      val dosya = dosyayaCevir(yol)
      if (!dosya.exists()) return@AsyncFunction false
      val icerikUri = FileProvider.getUriForFile(
        context,
        "${context.packageName}.apkinstaller.fileprovider",
        dosya
      )
      val intent = Intent(Intent.ACTION_VIEW)
        .setDataAndType(icerikUri, "application/vnd.android.package-archive")
        .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
      baslat(intent)
      true
    }
  }

  /**
   * Mumkunse ETKIN EKRANDAN baslat: yukleyici kapaninca kullanici uygulamaya geri doner.
   * Etkin ekran yoksa (arka plan) uygulama baglamindan baslatilir; NEW_TASK zaten eklenmistir.
   */
  private fun baslat(intent: Intent) {
    val aktivite = appContext.currentActivity
    if (aktivite != null) {
      aktivite.startActivity(intent)
    } else {
      context.startActivity(intent)
    }
  }

  /** `file:///a/b.apk`, `/a/b.apk` ve `content://` olmayan her bicimi File'a cevirir. */
  private fun dosyayaCevir(yol: String): File {
    val uri = Uri.parse(yol)
    return if (uri.scheme == "file") File(requireNotNull(uri.path)) else File(yol)
  }
}
