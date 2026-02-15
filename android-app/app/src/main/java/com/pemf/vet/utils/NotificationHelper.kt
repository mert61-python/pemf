package com.pemf.vet.utils

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import com.pemf.vet.R
import com.pemf.vet.data.models.ConnectionState
import com.pemf.vet.ui.MainActivity

object NotificationHelper {
    private const val CHANNEL_ID_CONNECTION = "pemf_connection"
    private const val CHANNEL_ID_TREATMENT = "pemf_treatment"
    private const val CHANNEL_ID_PWM = "pemf_pwm"
    private const val CHANNEL_ID_SERVICE = "pemf_mqtt_service"
    
    const val CHANNEL_MQTT = CHANNEL_ID_SERVICE
    
    private const val CHANNEL_NAME_CONNECTION = "Bağlantı Bildirimleri"
    private const val CHANNEL_NAME_TREATMENT = "Tedavi Bildirimleri"
    private const val CHANNEL_NAME_PWM = "PWM Bildirimleri"
    private const val CHANNEL_NAME_SERVICE = "Arka Plan Bağlantısı"
    
    private const val NOTIFICATION_ID_CONNECTION = 1001
    private const val NOTIFICATION_ID_TREATMENT = 1002
    private const val NOTIFICATION_ID_PWM = 1003
    const val FOREGROUND_NOTIFICATION_ID = 1100
    
    fun createNotificationChannels(context: Context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val notificationManager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            
            // Connection Channel
            val connectionChannel = NotificationChannel(
                CHANNEL_ID_CONNECTION,
                CHANNEL_NAME_CONNECTION,
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Bağlantı durumu bildirimleri"
                enableVibration(true)
                enableLights(true)
            }
            
            // Treatment Channel
            val treatmentChannel = NotificationChannel(
                CHANNEL_ID_TREATMENT,
                CHANNEL_NAME_TREATMENT,
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Tedavi başlatma ve durdurma bildirimleri"
                enableVibration(true)
                enableLights(true)
            }
            
            // PWM Channel
            val pwmChannel = NotificationChannel(
                CHANNEL_ID_PWM,
                CHANNEL_NAME_PWM,
                NotificationManager.IMPORTANCE_DEFAULT
            ).apply {
                description = "Bobin PWM durumu bildirimleri"
                enableVibration(false)
                enableLights(true)
            }
            // Foreground Service Channel
            val serviceChannel = NotificationChannel(
                CHANNEL_ID_SERVICE,
                CHANNEL_NAME_SERVICE,
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "MQTT bağlantısını arka planda korur"
                setShowBadge(false)
            }
            
            notificationManager.createNotificationChannel(connectionChannel)
            notificationManager.createNotificationChannel(treatmentChannel)
            notificationManager.createNotificationChannel(pwmChannel)
            notificationManager.createNotificationChannel(serviceChannel)
        }
    }
    
    private fun getPendingIntent(context: Context): PendingIntent {
        val intent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
        }
        return PendingIntent.getActivity(
            context,
            0,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
    }
    
    fun showConnectionNotification(context: Context, connected: Boolean, serverIp: String? = null) {
        val notificationManager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        
        val title = if (connected) "Bağlantı Kuruldu" else "Bağlantı Kesildi"
        val message = if (connected) {
            if (serverIp != null) "Sunucuya bağlandı: $serverIp" else "Sunucuya bağlandı"
        } else {
            "Sunucu bağlantısı kesildi"
        }
        val icon = if (connected) R.drawable.pemf_heart_emf_icon else android.R.drawable.ic_dialog_alert
        
        val notification = NotificationCompat.Builder(context, CHANNEL_ID_CONNECTION)
            .setSmallIcon(icon)
            .setContentTitle(title)
            .setContentText(message)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(getPendingIntent(context))
            .build()
        
        notificationManager.notify(NOTIFICATION_ID_CONNECTION, notification)
    }
    
    fun showTreatmentStartedNotification(context: Context, patientName: String? = null, duration: Int? = null) {
        val notificationManager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        
        val message = buildString {
            if (patientName != null) {
                append("Hasta: $patientName")
            }
            if (duration != null) {
                if (isNotEmpty()) append(" • ")
                append("Süre: $duration dk")
            }
            if (isEmpty()) {
                append("Tedavi başlatıldı")
            }
        }
        
        val notification = NotificationCompat.Builder(context, CHANNEL_ID_TREATMENT)
            .setSmallIcon(R.drawable.pemf_heart_emf_icon)
            .setContentTitle("Tedavi Başlatıldı")
            .setContentText(message)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(getPendingIntent(context))
            .build()
        
        notificationManager.notify(NOTIFICATION_ID_TREATMENT, notification)
    }
    
    fun showTreatmentStoppedNotification(context: Context) {
        val notificationManager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        
        val notification = NotificationCompat.Builder(context, CHANNEL_ID_TREATMENT)
            .setSmallIcon(R.drawable.pemf_heart_emf_icon)
            .setContentTitle("Tedavi Durduruldu")
            .setContentText("Tedavi seansı sonlandırıldı")
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(getPendingIntent(context))
            .build()
        
        notificationManager.notify(NOTIFICATION_ID_TREATMENT, notification)
    }
    
    fun showPWMStartedNotification(context: Context, coilName: String) {
        val notificationManager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        
        val notification = NotificationCompat.Builder(context, CHANNEL_ID_PWM)
            .setSmallIcon(R.drawable.pemf_heart_emf_icon)
            .setContentTitle("PWM Başlatıldı")
            .setContentText("$coilName için PWM aktif edildi")
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .setAutoCancel(true)
            .setContentIntent(getPendingIntent(context))
            .build()
        
        notificationManager.notify(NOTIFICATION_ID_PWM, notification)
    }
    
    fun showPWMStoppedNotification(context: Context, coilName: String) {
        val notificationManager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        
        val notification = NotificationCompat.Builder(context, CHANNEL_ID_PWM)
            .setSmallIcon(R.drawable.pemf_heart_emf_icon)
            .setContentTitle("PWM Durduruldu")
            .setContentText("$coilName için PWM durduruldu")
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .setAutoCancel(true)
            .setContentIntent(getPendingIntent(context))
            .build()
        
        notificationManager.notify(NOTIFICATION_ID_PWM, notification)
    }

    fun buildMqttForegroundNotification(
        context: Context,
        state: ConnectionState
    ): Notification {
        val (title, message, icon) = when (state) {
            ConnectionState.CONNECTED -> Triple(
                "MQTT Bağlı",
                "Cihazlar ile bağlantı korunuyor",
                R.drawable.pemf_heart_emf_icon
            )
            ConnectionState.CONNECTING -> Triple(
                "MQTT Bağlantısı Kuruluyor",
                "Sunucuya bağlanılıyor...",
                R.drawable.pemf_heart_emf_icon
            )
            ConnectionState.DISCONNECTED, ConnectionState.ERROR -> Triple(
                "MQTT Bağlantısı Kapalı",
                "Otomatik yeniden bağlanma deneniyor",
                android.R.drawable.stat_notify_sync_noanim
            )
            else -> Triple(
                "MQTT Durumu Bilinmiyor",
                "Bağlantı durumu güncelleniyor",
                android.R.drawable.stat_sys_warning
            )
        }

        return NotificationCompat.Builder(context, CHANNEL_ID_SERVICE)
            .setSmallIcon(icon)
            .setOngoing(true)
            .setContentTitle(title)
            .setContentText(message)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setContentIntent(getPendingIntent(context))
            .build()
    }

    fun updateMqttForegroundNotification(context: Context, state: ConnectionState) {
        val notificationManager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val notification = buildMqttForegroundNotification(context, state)
        notificationManager.notify(FOREGROUND_NOTIFICATION_ID, notification)
    }
}

