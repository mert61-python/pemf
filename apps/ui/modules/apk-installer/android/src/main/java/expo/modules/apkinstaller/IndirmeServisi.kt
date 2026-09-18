package expo.modules.apkinstaller

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat

/**
 * GUNCELLEME INDIRME ON-PLAN SERVISI (2026-08-27, saha bildirimi: "ekrani kilitleyince /
 * arka plana alinca indirme kesiliyor").
 *
 * NEDEN: expo-file-system indirmeyi Dispatchers.IO coroutine'inde yurutur ve teknik olarak
 * arka planda surer — ama modern Android (Doze / App Standby / OEM pil katilleri) ekran
 * kilitlenince ya da uygulama arka plana alininca surecin AG ERISIMINI askiya alabilir ya da
 * sureci OLDUREBILIR. 128 MB'lik paketin "arka planda tamamlanmasi" (sahip istegi 2026-08-14)
 * ancak bir ON-PLAN SERVISI ile guvenceye alinir: dataSync tipli FGS, surec + ag erisimini
 * indirme boyunca canli tutar.
 *
 * KAPSAM BILINCLI DAR: servis HICBIR IS YAPMAZ — indirme yine expo-file-system'dedir. Buradaki
 * tek is, "indirme suruyor" bildirimiyle surece on-plan onceligi kazandirmaktir. Indirme bitince
 * JS tarafi servisi durdurur; JS olurse bile START_NOT_STICKY oldugu icin servis hortlamaz.
 *
 * BILDIRIM IZNI (Android 13+): POST_NOTIFICATIONS izni istemiyoruz — izin yoksa bildirim
 * GORUNMEZ ama servis yine on-plan calisir (cerceve, startForeground'u iznin yoklugunda da
 * kabul eder). Kullaniciya izin diyalogu dayatmamak bilincli: guncelleme bir kolayliktir.
 */
class IndirmeServisi : Service() {

  override fun onBind(intent: Intent?): IBinder? = null

  override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
    // ⚠️ SAHA ÇÖKMESİ 2026-08-29 (Galaxy S23, Android 16 / API 36) — ÖLÇÜLDÜ:
    //
    //   17:37:01.916  ActivityManager: Background started FGS: Allowed [uidState: TOP]
    //   17:37:01.924  ActivityManager: Bringing down service while still waiting for start foreground
    //   17:37:01.939  FATAL: ForegroundServiceDidNotStartInTimeException
    //
    // 23 milisaniye. İzin sorunu YOK (FGS "Allowed", uygulama TOP). Olan şu: JS tarafı servisi
    // başlatıyor, indirme İŞİ ERKEN BİTİYOR (ör. APK zaten tam inmiş → hızlı dönüş) ve `finally`
    // bloğu `stopService` çağırıyor. `startForegroundService()` çağrıldıktan sonra servis
    // `startForeground()` ÇAĞIRMADAN indirilirse Android süreci ÖLDÜRÜR — kullanıcı "Güncelle"ye
    // basar basmaz uygulama kapanıyordu.
    //
    // KURAL: `startForeground` bu metodun İLK işi olmalı ve HER YOLDA çağrılmalı — durdurma
    // isteğiyle gelinse bile. Önce çağır, sonra dur (`stopSelf`); ters sıra çökme demektir.
    val kanalId = "pemf_guncelleme_indirme"
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
      val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
      // IMPORTANCE_LOW: ses/titresim yok — indirme bildirimi sessiz bir durum gostergesidir.
      nm.createNotificationChannel(
        NotificationChannel(kanalId, "Guncelleme indirme", NotificationManager.IMPORTANCE_LOW)
      )
    }
    val bildirim = NotificationCompat.Builder(this, kanalId)
      .setContentTitle(intent?.getStringExtra("baslik") ?: "Guncelleme indiriliyor")
      .setContentText("Paket arka planda indiriliyor; uygulamayi kapatabilirsiniz.")
      .setSmallIcon(android.R.drawable.stat_sys_download)
      .setOngoing(true)
      .build()
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
      startForeground(BILDIRIM_ID, bildirim, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
    } else {
      startForeground(BILDIRIM_ID, bildirim)
    }

    // Durdurma isteği: `startForeground` YUKARIDA çağrıldı, borç kapandı — artık güvenle durabiliriz.
    // Servis hiç yaratılmamışken bile bu yol çalışır: dur-niyeti servisi yaratır, servis kendini
    // ön plana alır ve hemen kapanır. Çerçevenin gördüğü sıra her zaman start → foreground → stop.
    if (intent?.getBooleanExtra(EXTRA_DUR, false) == true) {
      if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
        stopForeground(STOP_FOREGROUND_REMOVE)
      } else {
        @Suppress("DEPRECATION")
        stopForeground(true)
      }
      stopSelf()
    }
    return START_NOT_STICKY
  }

  companion object {
    const val BILDIRIM_ID = 4127

    /** Dur-niyeti işareti — bkz. `onStartCommand` başındaki çökme notu. */
    const val EXTRA_DUR = "dur"
  }
}
