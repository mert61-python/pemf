package com.pemf.vet.services

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import com.pemf.vet.R
import com.pemf.vet.data.api.MqttService
import com.pemf.vet.data.models.ConnectionState
import com.pemf.vet.ui.MainActivity
import com.pemf.vet.utils.AppLogger
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.launchIn
import kotlinx.coroutines.flow.onEach
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * ✅ Foreground Service for MQTT Connection
 * Keeps MQTT connection alive when app is in background
 * 
 * Android 8.0+ requires Foreground Service for background work
 * This service shows a persistent notification and keeps MQTT connected
 */
@AndroidEntryPoint
class MqttForegroundService : Service() {
    
    @Inject
    lateinit var mqttService: MqttService
    
    private val scope = CoroutineScope(Dispatchers.Main + SupervisorJob())
    private val TAG = "MqttForegroundService"
    
    companion object {
        private const val NOTIFICATION_ID = 1001
        private const val CHANNEL_ID = "mqtt_connection_channel"
        
        fun start(context: Context) {
            val intent = Intent(context, MqttForegroundService::class.java)
            try {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    context.startForegroundService(intent)
                } else {
                    context.startService(intent)
                }
            } catch (e: Exception) {
                // Android 12+ ForegroundServiceStartNotAllowedException
                // Background start restriction. Log it and ignore.
                // Service will be started later when Activity is in foreground.
                AppLogger.e("MqttForegroundService", "Failed to start service: ${e.message}")
            }
        }
        
        fun stop(context: Context) {
            val intent = Intent(context, MqttForegroundService::class.java)
            context.stopService(intent)
        }
    }
    
    override fun onCreate() {
        super.onCreate()
        AppLogger.d(TAG, "Service created")
        
        // Create notification channel (Android 8.0+)
        createNotificationChannel()
        
        // Start as foreground service
        startForeground(NOTIFICATION_ID, buildNotification(ConnectionState.CONNECTING))
        
        // Observe connection state and update notification
        observeConnectionState()
        
        // Ensure MQTT is connected
        scope.launch {
            if (!mqttService.isConnected()) {
                mqttService.connect(force = false)
            }
        }
    }
    
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        AppLogger.d(TAG, "Service started")
        return START_STICKY // Service will be restarted if killed
    }
    
    override fun onBind(intent: Intent?): IBinder? = null
    
    override fun onDestroy() {
        super.onDestroy()
        AppLogger.d(TAG, "Service destroyed")
        scope.cancel()
    }
    
    private fun observeConnectionState() {
        mqttService.connectionState
            .onEach { state ->
                updateNotification(state)
            }
            .launchIn(scope)
    }
    
    private fun updateNotification(state: ConnectionState) {
        val notification = buildNotification(state)
        val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        notificationManager.notify(NOTIFICATION_ID, notification)
    }
    
    private fun buildNotification(state: ConnectionState): Notification {
        // Intent to open MainActivity when notification is tapped
        val pendingIntent = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        
        val (title, text, icon) = when (state) {
            ConnectionState.CONNECTED, ConnectionState.CONNECTED_CLOUD, ConnectionState.CONNECTED_LOCAL -> Triple(
                "PEMF Bağlı",
                "Bobinler bağlı ve senkronize",
                R.drawable.ic_connection_success
            )
            ConnectionState.CONNECTING -> Triple(
                "PEMF Bağlanıyor",
                "Bobinlere bağlanılıyor...",
                R.drawable.ic_connection_pending
            )
            ConnectionState.DISCONNECTED -> Triple(
                "PEMF Bağlantı Kesildi",
                "Bağlantı kayboldu. Yeniden deneniyor...",
                R.drawable.ic_connection_error
            )
            ConnectionState.ERROR -> Triple(
                "PEMF Bağlantı Hatası",
                "Bağlanılamadı. Ağ ayarlarını kontrol edin.",
                R.drawable.ic_connection_error
            )
        }
        
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle(title)
            .setContentText(text)
            .setSmallIcon(icon)
            .setContentIntent(pendingIntent)
            .setOngoing(true) // Cannot be dismissed by user
            .setPriority(NotificationCompat.PRIORITY_LOW) // Low priority for less intrusive
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .build()
    }
    
    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "MQTT Bağlantısı",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "PEMF cihaz bağlantısını aktif tutar"
                setShowBadge(false)
            }
            
            val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            notificationManager.createNotificationChannel(channel)
        }
    }
}
