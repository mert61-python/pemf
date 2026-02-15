package com.pemf.vet.utils

import android.content.Context
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.ProcessLifecycleOwner
import com.pemf.vet.data.models.ConnectionState
import com.pemf.vet.data.repository.ConnectionRepository
import com.pemf.vet.data.repository.SessionRepository
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.launch
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Merkezi bildirim yönetimi sınıfı
 * Repository'lerdeki bildirim mantığını buraya taşıyarak tek bir gözlemci ile yönetir
 * Bu, arka plandan dönüldüğünde tekrarlanan bildirim sorununu çözer
 */
@Singleton
class AppNotificationManager @Inject constructor(
    @ApplicationContext private val context: Context,
    private val connectionRepository: ConnectionRepository,
    private val sessionRepository: SessionRepository
) {
    private var connectionObserverJob: Job? = null
    private var sessionObserverJob: Job? = null
    
    private var lastConnectionState: ConnectionState? = null
    private var lastSessionActive: Boolean? = null
    private var lastNotificationTime: Long = 0
    
    // Minimum bildirim aralığı (ms) - spam'i önlemek için
    // Increased from 3s to 30s to prevent notification spam when app is closed
    private val MIN_NOTIFICATION_INTERVAL = 30000L
    
    /**
     * Bildirimleri gözlemlemeye başla
     * PemfApplication.onCreate() içinde bir kez çağrılmalı
     */
    fun startObserving(scope: CoroutineScope) {
        stopObserving() // Önceki gözlemcileri temizle
        
        // Bağlantı durumu değişikliklerini gözlemle
        connectionObserverJob = scope.launch {
            connectionRepository.getConnectionInfo()
                .map { it.state }
                .distinctUntilChanged()
                .collect { state ->
                    handleConnectionStateChange(state)
                }
        }
        
        // Seans durumu değişikliklerini gözlemle
        sessionObserverJob = scope.launch {
            sessionRepository.getActiveSession()
                .map { it.active }
                .distinctUntilChanged()
                .collect { isActive ->
                    handleSessionStateChange(isActive)
                }
        }
        
        AppLogger.d("AppNotificationManager", "Started observing for notifications")
    }
    
    /**
     * Bildirimleri gözlemlemeyi durdur
     */
    fun stopObserving() {
        connectionObserverJob?.cancel()
        sessionObserverJob?.cancel()
        connectionObserverJob = null
        sessionObserverJob = null
    }
    
    private fun handleConnectionStateChange(state: ConnectionState) {
        // Uygulama background'dayken connection notification gösterme (spam önleme)
        if (!isAppInForeground()) {
            AppLogger.d("AppNotificationManager", "App in background, skipping connection notification (state=$state)")
            lastConnectionState = state // State'i güncelle ama bildirim gönderme
            return
        }
        
        // Durum gerçekten değiştiyse ve spam değilse bildirim gönder
        if (lastConnectionState != state && canSendNotification()) {
            when (state) {
                ConnectionState.CONNECTED -> {
                    // Sadece önceki durum DISCONNECTED veya ERROR ise bildirim göster
                    if (lastConnectionState == ConnectionState.DISCONNECTED || 
                        lastConnectionState == ConnectionState.ERROR) {
                        NotificationHelper.showConnectionNotification(
                            context,
                            connected = true,
                            serverIp = null // IP bilgisi varsa buraya eklenebilir
                        )
                        lastNotificationTime = System.currentTimeMillis()
                        AppLogger.d("AppNotificationManager", "Sent CONNECTED notification")
                    }
                }
                ConnectionState.DISCONNECTED -> {
                    // Sadece önceki durum CONNECTED ise bildirim göster
                    if (lastConnectionState == ConnectionState.CONNECTED) {
                        NotificationHelper.showConnectionNotification(
                            context,
                            connected = false
                        )
                        lastNotificationTime = System.currentTimeMillis()
                        AppLogger.d("AppNotificationManager", "Sent DISCONNECTED notification")
                    }
                }
                else -> {
                    // CONNECTING, ERROR durumlarında bildirim gösterme
                }
            }
            lastConnectionState = state
        }
    }
    
    private fun handleSessionStateChange(isActive: Boolean) {
        // Durum gerçekten değiştiyse ve spam değilse bildirim gönder
        if (lastSessionActive != isActive && canSendNotification()) {
            if (isActive) {
                // Tedavi başladı
                // Not: Hasta adı ve süre bilgisi için Session nesnesine erişmek gerekiyor
                // Şimdilik basit bildirim gönderiyoruz
                NotificationHelper.showTreatmentStartedNotification(
                    context,
                    patientName = null,
                    duration = null
                )
                lastNotificationTime = System.currentTimeMillis()
                AppLogger.d("AppNotificationManager", "Sent TREATMENT STARTED notification")
            } else if (lastSessionActive == true) {
                // Tedavi durdu (önceden aktifti, şimdi değil)
                NotificationHelper.showTreatmentStoppedNotification(context)
                lastNotificationTime = System.currentTimeMillis()
                AppLogger.d("AppNotificationManager", "Sent TREATMENT STOPPED notification")
            }
            lastSessionActive = isActive
        }
    }
    
    /**
     * Bildirim spam'ini önlemek için kontrol
     */
    private fun canSendNotification(): Boolean {
        val now = System.currentTimeMillis()
        return (now - lastNotificationTime) >= MIN_NOTIFICATION_INTERVAL
    }
    
    /**
     * Uygulamanın foreground'da olup olmadığını kontrol et
     */
    private fun isAppInForeground(): Boolean {
        return ProcessLifecycleOwner.get().lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)
    }
}
