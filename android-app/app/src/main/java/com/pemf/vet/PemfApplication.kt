package com.pemf.vet

import android.app.Application
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.os.Build
import android.util.Log
import androidx.annotation.RequiresApi
import androidx.lifecycle.DefaultLifecycleObserver
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.ProcessLifecycleOwner
import androidx.work.Configuration
import com.pemf.vet.data.api.MqttService
import com.pemf.vet.utils.AppLogger
import com.pemf.vet.utils.AppNotificationManager
import com.pemf.vet.utils.CrashReporter
import com.pemf.vet.utils.NotificationHelper
import com.pemf.vet.services.MqttForegroundService
import dagger.hilt.android.EntryPointAccessors
import dagger.hilt.android.HiltAndroidApp
import dagger.hilt.EntryPoint
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import javax.inject.Inject
import androidx.hilt.work.HiltWorkerFactory
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.delay

@HiltAndroidApp
class PemfApplication : Application(), DefaultLifecycleObserver, Configuration.Provider {
        @Inject lateinit var workerFactory: HiltWorkerFactory
        override val workManagerConfiguration: Configuration by lazy {
            Configuration.Builder()
                .setMinimumLoggingLevel(Log.INFO)
                .setWorkerFactory(workerFactory)
                .build()
        }
    companion object {
        @Volatile
        private var instance: PemfApplication? = null
        
        fun getInstance(): PemfApplication {
            return instance ?: throw IllegalStateException("Application not initialized")
        }
    }
    
    @EntryPoint
    @InstallIn(SingletonComponent::class)
    interface MqttServiceEntryPoint {
        fun mqttService(): MqttService
    }
    
    @EntryPoint
    @InstallIn(SingletonComponent::class)
    interface NotificationManagerEntryPoint {
        fun notificationManager(): AppNotificationManager
    }
    
    private var networkCallback: ConnectivityManager.NetworkCallback? = null
    
    override fun onCreate() {
        super<Application>.onCreate()
        instance = this
        
        // Create notification channels
        NotificationHelper.createNotificationChannels(this)
        
        // Initialize crash reporting
        setupCrashReporting()
        
        // Setup network monitoring (Hilt injection tamamlandıktan sonra)
        // Postpone to ensure Hilt components are initialized
        android.os.Handler(mainLooper).post {
            setupNetworkMonitoring()
            startNotificationManager()
            // ✅ Start MQTT Foreground Service - keeps connection alive in background
            MqttForegroundService.start(this)
            // Removed MqttReconnectWorker - Paho auto-reconnect is sufficient
        }
        
        // Uygulama yaşam döngüsünü dinlemeye başla (foreground/background detection)
        ProcessLifecycleOwner.get().lifecycle.addObserver(this)
    }

    /**
     * Merkezi bildirim yöneticisini başlat
     * Tek bir gözlemci ile tüm bildirimleri yönetir, tekrarlanan bildirim sorununu çözer
     */
    private fun startNotificationManager() {
        try {
            val entryPoint = EntryPointAccessors.fromApplication(
                applicationContext,
                NotificationManagerEntryPoint::class.java
            )
            val notificationManager = entryPoint.notificationManager()
            
            // ProcessLifecycleOwner ile uygulama kapanana kadar aktif kalacak scope
            // GlobalScope yerine CoroutineScope(SupervisorJob() + Dispatchers.Main) kullan
            val appScope = kotlinx.coroutines.CoroutineScope(
                kotlinx.coroutines.SupervisorJob() + kotlinx.coroutines.Dispatchers.Main
            )
            notificationManager.startObserving(appScope)
            
            AppLogger.d("PemfApplication", "AppNotificationManager started")
        } catch (e: Exception) {
            AppLogger.e("PemfApplication", "Failed to start AppNotificationManager", e)
        }
    }
    
    /**
     * Uygulama ön plana (foreground) geldiğinde çalışır
     * ✅ Force reconnect: App kapanıp açıldığında eski bağlantıları temizle
     */
    override fun onStart(owner: LifecycleOwner) {
        AppLogger.d("PemfApplication", "App entered foreground, forcing MQTT reconnect")
        
        // Hilt EntryPoint kullanarak MqttService'e eriş
        try {
            val entryPoint = EntryPointAccessors.fromApplication(
                applicationContext,
                MqttServiceEntryPoint::class.java
            )
            val mqttService = entryPoint.mqttService()
            
            // ✅ Force reconnect with cleanup
            CoroutineScope(Dispatchers.IO).launch {
                try {
                    delay(500) // Küçük delay - app tam açılsın
                    if (!mqttService.isConnected()) {
                        AppLogger.d("PemfApplication", "MQTT not connected, forcing reconnect")
                        mqttService.connect(force = true)
                    } else {
                        AppLogger.d("PemfApplication", "MQTT already connected, requesting fresh status")
                        // Bağlıysa bile fresh status iste (retained message problem fix)
                        mqttService.requestStatusFromAllESPs()
                    }
                } catch (e: Exception) {
                    AppLogger.e("PemfApplication", "Failed to reconnect on foreground", e)
                }
            }
        } catch (e: Exception) {
            AppLogger.e("PemfApplication", "Failed to access MqttService on foreground", e)
        }
    }
    
    /**
     * Network monitoring'i başlat
     */
    private fun setupNetworkMonitoring() {
        try {
            // Hilt EntryPoint kullanarak MqttService'e eriş
            val entryPoint = EntryPointAccessors.fromApplication(
                applicationContext,
                MqttServiceEntryPoint::class.java
            )
            val mqttService = entryPoint.mqttService()
            
            val connectivityManager = getSystemService(ConnectivityManager::class.java)
            
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
                // Android 7.0+ için NetworkCallback kullan
                // Önceki network transport type'ını takip et
                var previousTransportType: Int? = null
                
                networkCallback = object : ConnectivityManager.NetworkCallback() {
                    override fun onAvailable(network: Network) {
                        AppLogger.d("PemfApplication", "Network available")
                        // onAvailable'da hemen reconnect yapma
                        // MQTT client zaten isAutomaticReconnect = true olduğu için otomatik bağlanacak
                        // Sadece log kaydet
                    }
                    
                    override fun onLost(network: Network) {
                        AppLogger.d("PemfApplication", "Network lost")
                        // Network kaybolduğunda MQTT client otomatik olarak bağlantıyı keser
                        // isAutomaticReconnect = true olduğu için network geri geldiğinde otomatik bağlanır
                        previousTransportType = null // Reset transport type
                    }
                    
                    override fun onCapabilitiesChanged(
                        network: Network,
                        networkCapabilities: NetworkCapabilities
                    ) {
                        val hasInternet = networkCapabilities.hasCapability(
                            NetworkCapabilities.NET_CAPABILITY_INTERNET
                        ) && networkCapabilities.hasCapability(
                            NetworkCapabilities.NET_CAPABILITY_VALIDATED
                        )
                        
                        if (hasInternet) {
                            // Mevcut transport type'ını belirle
                            val currentTransportType = when {
                                networkCapabilities.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) -> 
                                    NetworkCapabilities.TRANSPORT_WIFI
                                networkCapabilities.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) -> 
                                    NetworkCapabilities.TRANSPORT_CELLULAR
                                networkCapabilities.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET) -> 
                                    NetworkCapabilities.TRANSPORT_ETHERNET
                                else -> -1
                            }
                            
                            // Network type değiştiğinde veya ilk kez internet geldiğinde MQTT reconnect
                            val transportChanged = previousTransportType != null && previousTransportType != currentTransportType
                            val networkRestored = previousTransportType == null // Internet geri geldi
                            
                            if (transportChanged || networkRestored) {
                                val transportName = when (currentTransportType) {
                                    NetworkCapabilities.TRANSPORT_WIFI -> "WiFi"
                                    NetworkCapabilities.TRANSPORT_CELLULAR -> "Cellular"
                                    NetworkCapabilities.TRANSPORT_ETHERNET -> "Ethernet"
                                    else -> "Unknown"
                                }
                                
                                if (transportChanged) {
                                    AppLogger.d("PemfApplication", "Network type changed to $transportName, forcing MQTT reconnect")
                                } else {
                                    AppLogger.d("PemfApplication", "Network restored ($transportName), forcing MQTT reconnect")
                                }
                                
                                // ✅ Force reconnect: cleanup old client and reconnect with new network
                                CoroutineScope(Dispatchers.IO).launch {
                                    try {
                                        if (!mqttService.isConnected()) {
                                            mqttService.connect(force = true)
                                            AppLogger.d("PemfApplication", "MQTT force reconnect initiated")
                                        } else {
                                            AppLogger.d("PemfApplication", "MQTT already connected, skipping reconnect")
                                        }
                                    } catch (e: Exception) {
                                        AppLogger.e("PemfApplication", "Failed to reconnect MQTT", e)
                                    }
                                }
                            } else {
                                AppLogger.d("PemfApplication", "Network capabilities changed but transport type unchanged, skipping MQTT reconnect")
                            }
                            
                            previousTransportType = currentTransportType
                        } else {
                            previousTransportType = null
                        }
                    }
                }
                
                val networkRequest = NetworkRequest.Builder()
                    .addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                    .addCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
                    .build()
                
                connectivityManager.registerNetworkCallback(networkRequest, networkCallback!!)
                AppLogger.d("PemfApplication", "Network monitoring started")
            }
        } catch (e: Exception) {
            AppLogger.e("PemfApplication", "Failed to setup network monitoring", e)
        }
    }
    
    override fun onTerminate() {
        super.onTerminate()
        // Network callback'i kaldır
        try {
            networkCallback?.let {
                val connectivityManager = getSystemService(ConnectivityManager::class.java)
                connectivityManager.unregisterNetworkCallback(it)
            }
        } catch (e: Exception) {
            AppLogger.e("PemfApplication", "Error unregistering network callback", e)
        }
    }
    
    private fun setupCrashReporting() {
        // Set up uncaught exception handler
        Thread.setDefaultUncaughtExceptionHandler { thread, throwable ->
            // Log the crash
            CrashReporter.recordException(throwable)
            
            // Call the default handler (system will show crash dialog)
            val defaultHandler = Thread.getDefaultUncaughtExceptionHandler()
            defaultHandler?.uncaughtException(thread, throwable)
        }
        
        // TODO: Initialize Firebase Crashlytics when Firebase is added:
        // FirebaseCrashlytics.getInstance().setCrashlyticsCollectionEnabled(!BuildConfig.DEBUG)
    }
}

