package com.pemf.vet.data.api

import android.content.Context
import android.content.SharedPreferences
import com.google.gson.Gson
import com.google.gson.JsonSyntaxException
import com.pemf.vet.BuildConfig
import com.pemf.vet.data.models.*
import com.pemf.vet.data.repository.ESPRepository
import com.pemf.vet.data.repository.SessionRepository
import com.pemf.vet.data.repository.SensorRepository
import com.pemf.vet.utils.AppLogger
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import org.eclipse.paho.client.mqttv3.*
import org.eclipse.paho.client.mqttv3.persist.MemoryPersistence
import java.util.concurrent.Executors
import java.util.*
import javax.inject.Inject
import javax.inject.Singleton

/**
 * MQTT Service for HiveMQ Cloud connection
 * Replaces WebSocketService - Android app now connects directly to HiveMQ Cloud
 */
@Singleton
class MqttService @Inject constructor(
    @ApplicationContext private val context: Context,
    private val gson: Gson,
    private val espRepository: ESPRepository,
    private val sessionRepository: SessionRepository,
    private val sensorRepository: SensorRepository,
    private val bleService: BleService
) {
    private val TAG = "MqttService"
    
    // HiveMQ Cloud credentials (from BuildConfig - secure, not hardcoded)
    private val BROKER_URL = BuildConfig.MQTT_BROKER_URL
    private val BROKER_USER = BuildConfig.MQTT_BROKER_USER
    private val BROKER_PASS = BuildConfig.MQTT_BROKER_PASS
    
    // Persistent client ID for clean session = false (to receive retained messages)
    // Clean session = false requires a persistent client ID to maintain session state
    private val CLIENT_ID_PREF_KEY = "mqtt_client_id"
    private val prefs: SharedPreferences = context.getSharedPreferences("mqtt_prefs", Context.MODE_PRIVATE)
    
    private val CLIENT_ID: String
        get() {
            val savedId = prefs.getString(CLIENT_ID_PREF_KEY, null)
            return if (savedId != null) {
                savedId
            } else {
                val newId = "android_app_${UUID.randomUUID()}"
                prefs.edit().putString(CLIENT_ID_PREF_KEY, newId).apply()
                AppLogger.d(TAG, "Generated new persistent client ID: $newId")
                newId
            }
        }
    
    private var mqttClient: MqttClient? = null
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private var pingJob: Job? = null
    private var cleanupJob: Job? = null  // ✅ Periyodik ESP cleanup job
    private var consecutiveFailures = 0
    private val connectMutex = Mutex()
    private val MAX_CONSECUTIVE_FAILURES = 3  // Reduced from 10 for faster failure detection
    
    // ESP device timeout: 5 saniyede status mesajı gelmezse ESP offline kabul et (hızlı tepki için agresif)
    private val ESP_TIMEOUT_MS = 5_000L  // 5 seconds - aggressive timeout for fast disconnection detection
    
    // Connection state
    private val _connectionState = MutableStateFlow<ConnectionState>(ConnectionState.DISCONNECTED)
    val connectionState: StateFlow<ConnectionState> = _connectionState.asStateFlow()
    
    // Status updates (from status topic)
    private val _statusUpdates = MutableSharedFlow<StatusUpdatePayload>(replay = 0, extraBufferCapacity = 1)
    val statusUpdates: SharedFlow<StatusUpdatePayload> = _statusUpdates.asSharedFlow()
    
    // Sensor data updates (from sensors topic)
    private val _sensorDataUpdates = MutableSharedFlow<Map<String, SensorData>>(replay = 0, extraBufferCapacity = 1)
    val sensorDataUpdates: SharedFlow<Map<String, SensorData>> = _sensorDataUpdates.asSharedFlow()
    
    // ESP list updates (built from status and sensor topics)
    private val _espListUpdates = MutableSharedFlow<List<ESPDevice>>(replay = 0, extraBufferCapacity = 1)
    val espListUpdates: SharedFlow<List<ESPDevice>> = _espListUpdates.asSharedFlow()
    
    // ✅ Event updates (WiFi config success, errors, etc.)
    private val _eventUpdates = MutableSharedFlow<EventMessage>(replay = 0, extraBufferCapacity = 1)
    val eventUpdates: SharedFlow<EventMessage> = _eventUpdates.asSharedFlow()
    
    // Session updates - StateFlow kullanarak yeni abonelerin son durumu almasını sağla
    private val _sessionUpdates = MutableStateFlow<Session>(Session(active = false))
    val sessionUpdates: StateFlow<Session> = _sessionUpdates.asStateFlow()

    
    // Track ESP devices by ID
    private val espDevicesMap = mutableMapOf<String, ESPDevice>()
    
    // Store last treatment_update data to calculate remaining time
    private var lastTreatmentStartTime: String? = null
    private var lastTreatmentDuration = 0
    private var lastTreatmentPatientName: String? = null
    private var lastTreatmentTarget: String? = null
    private var lastTreatmentMode: String? = null
    
    // Command ID tracking for ACK mechanism
    private var commandIdCounter = 0
    private val pendingCommands = mutableMapOf<String, Pair<String, Long>>() // command_id -> (coil_id, timestamp)
    
    init {
        connect()
        startCleanupJob()  // ✅ Periyodik ESP cleanup başlat
    }
    
    /**
     * ✅ Periyodik ESP cleanup: Timeout olan ESP'leri DISCONNECTED yap ve SensorRepository'yi güncelle
     * Bu, retained messages'dan gelen eski ESP'lerin UI'da bağlı görünmesini önler
     */
    private fun startCleanupJob() {
        cleanupJob?.cancel()
        cleanupJob = scope.launch {
            while (isActive) {
                delay(2_000L) // Her 2 saniyede bir cleanup yap - çok responsive
                
                val currentTime = System.currentTimeMillis()
                var disconnectedCount = 0
                
                // ✅ Timeout olan ESP'leri DISCONNECTED yap (map'ten silme)
                espDevicesMap.forEach { (espId, device) ->
                    val age = currentTime - device.lastUpdate
                    if (age > ESP_TIMEOUT_MS && device.state == ConnectionState.CONNECTED) {
                        AppLogger.d(TAG, "ESP $espId timeout (last seen ${age / 1000}s ago), marking DISCONNECTED")
                        
                        // ✅ ESP state'ini DISCONNECTED yap
                        val disconnectedDevice = device.copy(
                            state = ConnectionState.DISCONNECTED,
                            pwmStatus = null  // PWM durumunu temizle
                        )
                        espDevicesMap[espId] = disconnectedDevice
                        espRepository.updateDevice(disconnectedDevice)
                        
                        // ✅ SensorRepository'yi güncelle - isConnected = false
                        val existingSensor = sensorRepository.sensorData.value[espId]
                        if (existingSensor != null) {
                            sensorRepository.updateSensorData(
                                espId,
                                existingSensor.copy(isConnected = false)
                            )
                        }
                        
                        disconnectedCount++
                    }
                }
                
                if (disconnectedCount > 0) {
                    AppLogger.d(TAG, "ESP cleanup: marked $disconnectedCount ESP(s) as DISCONNECTED")
                    updateESPList() // UI'yı güncelle
                }
            }
        }
    }
    
    fun connect(force: Boolean = false) {
        scope.launch {
            connectMutex.withLock {
                // Eğer zaten bağlı veya bağlanıyorsa, tekrar bağlanma
                if (!force &&
                    (_connectionState.value == ConnectionState.CONNECTED ||
                    _connectionState.value == ConnectionState.CONNECTING)) {
                    AppLogger.d(TAG, "Already connected or connecting, skipping")
                    return@withLock
                }

                if (force) {
                    AppLogger.d(TAG, "Force reconnect requested")
                }

                connectInternal()
            }
        }
    }

    private suspend fun connectInternal() {
            try {
                // Eski client'ı temizle (network değişikliği durumunda önemli)
                cleanupOldClient()
                
                _connectionState.value = ConnectionState.CONNECTING
                
                // Use standard MqttClient instead of MqttAndroidClient to avoid AlarmPingSender issues
                mqttClient = MqttClient(BROKER_URL, CLIENT_ID, MemoryPersistence())
                mqttClient?.setCallback(object : MqttCallbackExtended {
            override fun connectionLost(cause: Throwable?) {
                AppLogger.w(TAG, "MQTT connection lost", cause)
                _connectionState.value = ConnectionState.DISCONNECTED
                espRepository.disconnectAll()
                pingJob?.cancel()
                
                // Consecutive failure tracking
                consecutiveFailures++
                AppLogger.d(TAG, "Consecutive failures: $consecutiveFailures/$MAX_CONSECUTIVE_FAILURES")
                
                if (consecutiveFailures >= MAX_CONSECUTIVE_FAILURES) {
                    AppLogger.e(TAG, "Too many consecutive failures ($consecutiveFailures), connection error state")
                    _connectionState.value = ConnectionState.ERROR
                    return
                }

                // Paho MQTT isAutomaticReconnect=true will handle reconnection automatically
            }            override fun connectComplete(reconnect: Boolean, serverURI: String?) {
                AppLogger.d(TAG, "MQTT connect complete (reconnect=$reconnect, uri=$serverURI)")
                consecutiveFailures = 0 // Reset failure counter on success
                _connectionState.value = ConnectionState.CONNECTED_CLOUD

                // ✅ Reconnect sonrası tüm ESP'leri DISCONNECTED yap (retained message problem'i çöz)
                if (reconnect) {
                    AppLogger.d(TAG, "Reconnect detected, clearing all ESP states (retained message fix)")
                    espDevicesMap.clear()
                    espRepository.disconnectAll()
                }

                // Yeniden bağlandıktan sonra abonelikleri garanti altına al
                subscribeToTopics()
                
                // ✅ Tüm ESP'lerden fresh status iste (2 saniye sonra)
                scope.launch {
                    delay(2000)
                    requestStatusFromAllESPs()
                }
            }                    override fun messageArrived(topic: String, message: MqttMessage) {
                        try {
                            if (message.isRetained) {
                                // Cihazın durumunu "bilinmiyor" veya "beklemede" olarak işaretleyip, 
                                // eğer timeout süresi içinde canlı mesaj gelmezse listeden silinmesini sağlayabiliriz.
                                // Şimdilik sadece logluyoruz.
                            }
                            handleMqttMessage(topic, message)
                        } catch (e: Exception) {
                            AppLogger.e(TAG, "Error handling message", e)
                        }
                    }
                    
                    override fun deliveryComplete(token: IMqttDeliveryToken?) {
                        // Message delivery complete
                    }
                })
                
                val options = MqttConnectOptions().apply {
                    userName = BROKER_USER
                    password = BROKER_PASS.toCharArray()
                    // Clean session = false to receive retained messages (session status)
                    // This allows the app to receive the last session status when it connects
                    isCleanSession = false
                    connectionTimeout = 30  // 30 seconds connection timeout
                    keepAliveInterval = 60  // 60 seconds keepalive (ping interval)
                    isAutomaticReconnect = true  // Enable Paho's built-in auto-reconnect
                    maxReconnectDelay = 60000  // Max reconnect delay 60s
                    
                    // SSL/TLS settings for HiveMQ Cloud
                    try {
                        val sslContext = javax.net.ssl.SSLContext.getInstance("TLS")
                        sslContext.init(null, null, null)
                        socketFactory = sslContext.socketFactory
                    } catch (e: Exception) {
                        AppLogger.e(TAG, "Failed to initialize SSL context", e)
                        // Fallback to default
                        socketFactory = javax.net.ssl.SSLContext.getDefault().socketFactory
                    }
                }
                
                mqttClient?.connect(options)
                
                AppLogger.d(TAG, "MQTT connect() invoked, waiting for connectComplete callback")
            } catch (e: Exception) {
                AppLogger.e(TAG, "Failed to connect MQTT", e)
                _connectionState.value = ConnectionState.ERROR
                
                consecutiveFailures++
                AppLogger.d(TAG, "Consecutive failures after error: $consecutiveFailures/$MAX_CONSECUTIVE_FAILURES")
                
                if (consecutiveFailures >= MAX_CONSECUTIVE_FAILURES) {
                    AppLogger.e(TAG, "Too many consecutive failures, connection error state")
                }
                // Paho MQTT isAutomaticReconnect=true will handle reconnection automatically

                // Hata durumunda eski client'ı temizle
                cleanupOldClient()
            }
    }
    
    /**
     * Check if MQTT client is connected
     */
    fun isConnected(): Boolean {
        return mqttClient?.isConnected == true && _connectionState.value == ConnectionState.CONNECTED
    }
    
    /**
     * Manually trigger reconnection
     */
    suspend fun reconnect() {
        if (isConnected()) {
            AppLogger.d(TAG, "Already connected, skipping reconnect")
            return
        }
        AppLogger.d(TAG, "Manual reconnect triggered")
        connect()
    }
    
    /**
     * Eski MQTT client'ı temizle (network değişikliği durumunda önemli)
     * Bu, birden fazla client'ın aynı anda açık kalmasını önler
     * 
     * İyileştirmeler:
     * - Timeout ile blocking disconnect önlendi
     * - Callback'ler temizlenerek memory leak önlendi
     * - Tüm işlemler try-catch ile korundu
     */
    private suspend fun cleanupOldClient() {
        try {
            val oldClient = mqttClient
            if (oldClient != null) {
                AppLogger.d(TAG, "Cleaning up old MQTT client")
                
                // 1. Callback'leri kaldır (memory leak önleme)
                try {
                    oldClient.setCallback(null)
                    AppLogger.d(TAG, "Callbacks cleared")
                } catch (e: Exception) {
                    AppLogger.w(TAG, "Error clearing callbacks", e)
                }
                
                // 2. Disconnect ile timeout (network yoksa takılmasın)
                try {
                    if (oldClient.isConnected) {
                        withTimeoutOrNull(2000L) {
                            oldClient.disconnect(1000) // 1s disconnect timeout
                        }
                        AppLogger.d(TAG, "Old client disconnected")
                    }
                } catch (e: Exception) {
                    AppLogger.w(TAG, "Error disconnecting old client (ignoring)", e)
                }
                
                // 3. Client'ı kapat
                try {
                    oldClient.close()
                    AppLogger.d(TAG, "Old client closed")
                } catch (e: Exception) {
                    AppLogger.w(TAG, "Error closing old client (ignoring)", e)
                }
                
                // 4. Referansı temizle
                mqttClient = null
            }
        } catch (e: Exception) {
            AppLogger.e(TAG, "Error cleaning up old client", e)
            // Hata olsa bile referansı temizle
            mqttClient = null
        }
    }
    
    private fun subscribeToTopics() {
        try {
            // Subscribe to all coil sensors
            // Standard MqttClient.subscribe() signature: subscribe(topic: String, qos: Int)
            mqttClient?.subscribe("pemf/coil/+/sensors", 1)
            AppLogger.d(TAG, "Subscribed to pemf/coil/+/sensors")
            
            // Subscribe to all coil status
            mqttClient?.subscribe("pemf/coil/+/status", 1)
            AppLogger.d(TAG, "Subscribed to pemf/coil/+/status")
            
            // Subscribe to all coil ACK messages (command acknowledgments)
            mqttClient?.subscribe("pemf/coil/+/ack", 1)
            AppLogger.d(TAG, "Subscribed to pemf/coil/+/ack")
            
            // ✅ Subscribe to all coil events (WiFi config success, errors, etc.)
            mqttClient?.subscribe("pemf/coil/+/events", 1)
            AppLogger.d(TAG, "Subscribed to pemf/coil/+/events")
            
            // Subscribe to system session updates (Event-Based) - CRITICAL for receiving session status
            mqttClient?.subscribe("pemf/system/session", 1)
            AppLogger.d(TAG, "Subscribed to pemf/system/session - Session updates will be received")
        } catch (e: Exception) {
            AppLogger.e(TAG, "Failed to subscribe to topics", e)
        }
    }
    
    // Removed startCustomPing() - Paho MqttClient handles ping automatically via keepAliveInterval
    
    fun processJsonMessage(payload: String) {
        try {
            val json = gson.fromJson(payload, Map::class.java) as Map<*, *>
            
            // Infer type based on fields
            when {
                json.containsKey("object_temp") || json.containsKey("msg_type") && json["msg_type"] == "sensor" -> {
                    // Extract coil ID or infer? 
                    // Payload for sensor has coil_id
                     // We need to construct a topic-like string or just call handler
                     // But handler expects topic string currently.
                     // Refactor handleSensorData to not need topic
                     
                     // Quick fix: Construct fake topic
                     val coilId = json["coil_id"]
                     if (coilId != null) {
                         val topic = "pemf/coil/$coilId/sensors"
                         handleSensorData(topic, payload, false)
                     }
                }
                json.containsKey("pwm_active") -> {
                     val coilId = json["coil_id"]
                     if (coilId != null) {
                         val topic = "pemf/coil/$coilId/status"
                         handleStatusUpdate(topic, payload, false)
                     }
                }
                json.containsKey("command_id") -> {
                    // Command ACK
                    val coilId = json["coil_id"]
                     if (coilId != null) {
                         val topic = "pemf/coil/$coilId/ack"
                         handleCommandAck(topic, payload)
                     }
                }
            }
        } catch (e: Exception) {
            AppLogger.e(TAG, "Error processing generic JSON", e)
        }
    }

    private fun handleMqttMessage(topic: String, message: MqttMessage) {
        try {
            val payload = String(message.payload)
            val isRetained = message.isRetained
            
            // Eğer mesaj retained ise ve çok eskiyse (örn. server timestamp yok), güvenip güvenmeme kararı?
            // Şimdilik retained mesajları kabul ediyoruz ama logluyoruz.
            // Gerçek zamanlı olmayan retained mesajlar yanıltıcı olabilir.
            
            AppLogger.d(TAG, "MQTT message received: topic=$topic, retained=$isRetained, payload=$payload")
            
            when {
                topic.endsWith("/sensors") -> {
                    handleSensorData(topic, payload, isRetained)
                }
                topic.endsWith("/status") -> {
                    handleStatusUpdate(topic, payload, isRetained)
                }
                topic.endsWith("/ack") -> {
                    handleCommandAck(topic, payload)
                }
                topic.endsWith("/events") -> {
                    // ✅ Handle events (WiFi config success, errors, etc.)
                    handleEventMessage(topic, payload)
                }
                topic == "pemf/system/session" -> {
                    AppLogger.d(TAG, "Processing session update (retained=$isRetained)")
                    handleSessionUpdate(payload)
                }
            }
        } catch (e: Exception) {
            AppLogger.e(TAG, "Error handling MQTT message", e)
        }
    }
        private fun handleSensorData(topic: String, payload: String, isRetained: Boolean) {
        try {
            val coilIdStr = extractCoilIdFromTopic(topic) ?: return
            val coilIdInt = coilIdStr.toInt()
            val espId = "ESP_${String.format("%03d", coilIdInt)}"
            
            // ✅ Retained mesajları ignore et - Sensor data her zaman CANLI olmalı
            // Sensor data retained=false ile yayınlanıyor, ama yine de kontrol edelim
            if (isRetained) {
                AppLogger.d(TAG, "Ignoring retained sensor data from $espId")
                return
            }
            
            val json = gson.fromJson(payload, Map::class.java) as Map<*, *>
            // ✅ ESP'nin gönderdiği field isimlerini kullan
            val objectTemp = (json["object_temp"] as? Number)?.toFloat() ?: 0f
            val ambientTemp = (json["ambient_temp"] as? Number)?.toFloat() ?: 0f
            val magneticField = (json["magnetic_field"] as? Number)?.toFloat() ?: 0f
            val current = (json["current"] as? Number)?.toFloat() ?: 0f
            // voltage ve frequency ESP tarafından gönderilmiyor, varsayılan değer kullan
            val voltage = (json["voltage"] as? Number)?.toFloat() ?: 0f
            val frequency = (json["frequency"] as? Number)?.toFloat() ?: 0f

            // ✅ isConnected durumunu ESP device state'inden al
            val espDevice = espDevicesMap[espId]
            val isConnected = espDevice?.state?.isConnected() == true // Fix null safety

            val sensorData = SensorData(
                espId = espId,
                objectTemperature = objectTemp,
                ambientTemperature = ambientTemp,
                magneticField = magneticField,
                current = current,
                voltage = voltage,
                frequency = frequency,
                timestamp = System.currentTimeMillis(),
                isConnected = isConnected  // ✅ ESP device state'e göre ayarla
            )

            // Update repository directly
            sensorRepository.updateSensorData(espId, sensorData)
            
            // ✅ ESP device map'i güncelle - sensor data geldi = ESP canlı
            // CRITICAL FIX: Include sensorData in the ESPDevice update so the UI (SessionControl) receives it
            val existingDevice = espDevicesMap[espId] ?: ESPDevice(
                id = espId,
                state = ConnectionState.CONNECTED_CLOUD,
                sensorData = sensorData // Initialize with sensor data
            )
            espDevicesMap[espId] = existingDevice.copy(
                state = ConnectionState.CONNECTED_CLOUD,
                lastUpdate = System.currentTimeMillis(),
                sensorData = sensorData // Update with fresh sensor data
            )
            espRepository.updateDevice(espDevicesMap[espId]!!)
            
            // Emit to flow (optional if repository handles flow)
            scope.launch {
                _sensorDataUpdates.emit(mapOf(espId to sensorData))
            }
            
            // AppLogger.d(TAG, "Sensor data received for coil $coilIdStr")
        } catch (e: Exception) {
            AppLogger.e(TAG, "Error handling sensor data", e)
        }
    }
private fun handleStatusUpdate(topic: String, payload: String, isRetained: Boolean) {
        try {
            val coilId = extractCoilIdFromTopic(topic) ?: return
            val espId = "ESP_${String.format("%03d", coilId.toInt())}"
            
            // Parse payload
            val json = gson.fromJson(payload, Map::class.java) as Map<*, *>
            val pwmActive = (json["pwm_active"] as? Boolean) ?: false
            val fwVersion = json["fw_version"] as? String // ✅ Parse FW Version
            
            // Extract PWM Status
            val pwmStatus = if (pwmActive) {
                val startTimestampMs = (json["pwm_start_timestamp"] as? Number)?.toLong() ?: 0L
                val duration = (json["pwm_duration"] as? Number)?.toInt()
                
                // Calculate remaining time locally from start_timestamp
                val remainingTimeSeconds = if (startTimestampMs > 0 && duration != null && duration > 0) {
                    val durationMs = duration * 60L * 1000L  // Convert minutes to milliseconds
                    val endTimestampMs = startTimestampMs + durationMs
                    val currentTimeMs = System.currentTimeMillis()
                    val remainingMs = endTimestampMs - currentTimeMs
                    val remainingSeconds = (remainingMs / 1000).toInt()
                    
                    if (remainingSeconds > 0) {
                        remainingSeconds
                    } else {
                        null  // Session expired
                    }
                } else {
                    null
                }
                
                AppLogger.d(TAG, "PWM Status parsed: active=$pwmActive, duration=$duration, startTimestampMs=$startTimestampMs, remainingTimeSeconds=$remainingTimeSeconds")
                
                PWMStatus(
                    active = pwmActive,
                    frequency = (json["pwm_frequency"] as? Number)?.toInt() ?: 0,
                    // Handle both 'pwm_duty_cycle' (legacy) and 'pwm_duty' (ESP standard)
                    dutyCycle = ((json["pwm_duty"] ?: json["pwm_duty_cycle"]) as? Number)?.toInt() ?: 0,
                    duration = duration,
                    remainingTime = remainingTimeSeconds
                )
            } else {
                null
            }
            
            // Update ESP device map with fresh timestamp
            val existingDevice = espDevicesMap[espId] ?: ESPDevice(
                id = espId,
                state = ConnectionState.DISCONNECTED  // ✅ Varsayılan DISCONNECTED
            )

            // ✅ Bağlantı durumunu belirleme - Timestamp age kontrolü
            val mqttConnected = (json["mqtt_connected"] as? Boolean) ?: false
            
            // Timestamp kontrolünü kaldır - ESP uptime gönderiyor, epoch time değil!
            // Bu uyumsuzluk mesajların "eski" zannedilmesine ve cihazların DISCONNECTED görünmesine neden oluyor.
            // Sadece retained olmayan mesajları ve mqtt_connected bilgisini temel alacağız.
            
            val newState = if (!isRetained) {
                // ✅ Canlı mesaj - mqtt_connected field'ına GÜVENİLEBİLİR (veya direkt CONNECTED kabul edilebilir)
                // ESP status gönderiyorsa canlıdır, ancak ESP içindeki mqtt_connected flag'i daha doğrudur
                if (mqttConnected) ConnectionState.CONNECTED else ConnectionState.CONNECTED // Status atıyorsa canlıdır!
            } else {
                // Retained mesaj - şimdilik kabul et (UI test için), ama normalde ignore edilebilir
                AppLogger.d(TAG, "Retained status message for $espId")
                if (mqttConnected) ConnectionState.CONNECTED else ConnectionState.DISCONNECTED
            }

            val updatedDevice = existingDevice.copy(
                state = newState,
                pwmStatus = pwmStatus,
                lastUpdate = System.currentTimeMillis(),
                fwVersion = fwVersion ?: existingDevice.fwVersion // ✅ Update FW Version
            )
            espDevicesMap[espId] = updatedDevice
            espRepository.updateDevice(updatedDevice)
            
            // ✅ Update sensor repository - isConnected field'ını doğru ayarla
            val existingSensor = sensorRepository.sensorData.value[espId]
            if (existingSensor != null) {
                sensorRepository.updateSensorData(
                    espId,
                    existingSensor.copy(isConnected = (newState == ConnectionState.CONNECTED))
                )
            }
            
            // Update ESP list
            updateESPList()
            
            AppLogger.d(TAG, "Status update: espId=$espId, retained=$isRetained, mqttConnected=$mqttConnected, newState=$newState")
        } catch (e: Exception) {
            AppLogger.e(TAG, "Error handling status update", e)
        }
    }
    
    private fun handleCommandAck(topic: String, payload: String) {
        try {
            // Extract coil ID from topic: pemf/coil/1/ack -> 1
            val coilId = extractCoilIdFromTopic(topic) ?: return
            
            val json = gson.fromJson(payload, Map::class.java) as Map<*, *>
            val commandId = json["command_id"] as? String
            val success = (json["success"] as? Boolean) ?: false
            val command = json["command"] as? String
            
            if (commandId != null) {
                val pendingCommand = pendingCommands.remove(commandId)
                if (pendingCommand != null) {
                    val (coilIdFromCommand, timestamp) = pendingCommand
                    val elapsedTime = System.currentTimeMillis() - timestamp
                    AppLogger.d(TAG, "Command ACK received: command_id=$commandId, coil_id=$coilId, success=$success, command=$command, elapsed=${elapsedTime}ms")
                    
                    // If command was successful "start" command, optimistically update PWM status
                    // This ensures remaining time shows immediately without waiting for status update
                    if (success && command == "start") {
                        val espId = "ESP_${String.format("%03d", coilId.toInt())}"
                        val freq = (json["freq"] as? Number)?.toInt()
                        val duty = (json["duty"] as? Number)?.toInt()
                        val duration = (json["duration"] as? Number)?.toInt()
                        
                        // Calculate remaining time from start_at timestamp
                        val startAt = (json["start_at"] as? Number)?.toLong()
                        val remainingTimeSeconds = if (startAt != null && duration != null && duration > 0) {
                            val durationMs = duration * 60L * 1000L  // Convert minutes to milliseconds
                            val endTimestampMs = startAt + durationMs
                            val currentTimeMs = System.currentTimeMillis()
                            val remainingMs = endTimestampMs - currentTimeMs
                            val remainingSeconds = (remainingMs / 1000).toInt()
                            
                            if (remainingSeconds > 0) remainingSeconds else null
                        } else {
                            null
                        }
                        
                        AppLogger.d(TAG, "Optimistically updating PWM status: freq=$freq, duty=$duty, duration=$duration, remainingTime=$remainingTimeSeconds")
                        
                        // Update ESP device map with optimistic PWM status
                        val existingDevice = espDevicesMap[espId] ?: ESPDevice(
                            id = espId,
                            state = ConnectionState.CONNECTED_CLOUD
                        )
                        val updatedDevice = existingDevice.copy(
                            pwmStatus = PWMStatus(
                                active = true,
                                frequency = freq ?: 0,
                                dutyCycle = duty ?: 0,
                                duration = duration,
                                remainingTime = remainingTimeSeconds
                            )
                        )
                        espDevicesMap[espId] = updatedDevice
                        espRepository.updateDevice(updatedDevice)
                        
                        // Update ESP list to refresh UI
                        updateESPList()
                    } else if (success && command == "stop") {
                        // Optimistically clear PWM status for stop command
                        val espId = "ESP_${String.format("%03d", coilId.toInt())}"
                        val existingDevice = espDevicesMap[espId]
                        if (existingDevice != null) {
                            val updatedDevice = existingDevice.copy(pwmStatus = null)
                            espDevicesMap[espId] = updatedDevice
                            espRepository.updateDevice(updatedDevice)
                            updateESPList()
                        }
                    }
                } else {
                    AppLogger.d(TAG, "Command ACK received for unknown command: command_id=$commandId, coil_id=$coilId (may be from GUI)")
                }
            }
        } catch (e: Exception) {
            AppLogger.e(TAG, "Error handling command ACK", e)
        }
    }
    
    private fun extractCoilIdFromTopic(topic: String): String? {
        // Topic format: pemf/coil/1/sensors or pemf/coil/1/status
        val parts = topic.split("/")
        return if (parts.size >= 3 && parts[0] == "pemf" && parts[1] == "coil") {
            parts[2]
        } else {
            null
        }
    }
    
    private fun handleSessionUpdate(payload: String) {
        try {
            val json = gson.fromJson(payload, Map::class.java) as Map<*, *>
            
            val active = json["active"] as? Boolean ?: false
            
            // Timestamp kontrolü: Retained message age filter
            // Active=true durumunda eski mesajları reddet (5 dakika eşiği)
            // Active=false durumunda timestamp kontrolü yapma (session durdurulmuş)
            val messageTimestamp = (json["start_timestamp"] as? Number)?.toLong() ?: 0L
            val currentTime = System.currentTimeMillis()
            val messageAge = currentTime - messageTimestamp
            val MAX_MESSAGE_AGE_MS = 5 * 60 * 1000L  // 5 dakika
            
            // Eski retained message kontrolü (sadece active=true için)
            if (active && messageTimestamp > 0 && messageAge > MAX_MESSAGE_AGE_MS) {
                AppLogger.w(TAG, "Retained session message çok eski (${messageAge / 1000 / 60} dk), ignoring active=true session")
                // Eski session'ı ignore et, inactive state'e çevir
                scope.launch {
                    val inactiveSession = Session(active = false)
                    _sessionUpdates.value = inactiveSession
                    sessionRepository.updateSession(inactiveSession)
                }
                return
            }
            
            // Debug log
            if (messageTimestamp > 0) {
                AppLogger.d(TAG, "Session message age: ${messageAge / 1000} seconds, active=$active")
            }
            
            val session = if (active) {
                Session(
                    active = true,
                    patientName = json["patient_name"] as? String,
                    treatmentMode = (json["mode"] as? String)?.uppercase() ?: (json["treatment_mode"] as? String),
                    target = (json["target"] as? String) ?: (json["treatment_target"] as? String),
                    duration = (json["duration_minutes"] as? Number)?.toInt() ?: 0,
                    // start_timestamp'i al (Unix Epoch milliseconds)
                    startTimestamp = (json["start_timestamp"] as? Number)?.toLong() ?: 0L,
                    frequency = (json["frequency"] as? Number)?.toFloat() ?: 0f,
                    intensity = (json["intensity"] as? Number)?.toFloat() ?: 0f
                )
            } else {
                Session(active = false)
            }
            
            // UI'a gönder
            scope.launch {
                _sessionUpdates.value = session
                sessionRepository.updateSession(session)
            }
            
            if (active) {
                AppLogger.d(
                    TAG, 
                    "✅ GUI'den aktif seans alındı: mode=${session.treatmentMode}, " +
                    "patient=${session.patientName}, duration=${session.duration}min, " +
                    "freq=${session.frequency}Hz, intensity=${session.intensity}, " +
                    "target=${session.target}, timestamp=${session.startTimestamp}"
                )
            } else {
                AppLogger.d(TAG, "GUI'den seans durduruldu mesajı alındı")
            }
        } catch (e: Exception) {
            AppLogger.e(TAG, "Seans verisi işlenemedi", e)
        }
    }
    
    /**
     * ✅ Handle event messages (WiFi config success, errors, etc.)
     */
    private fun handleEventMessage(topic: String, payload: String) {
        try {
            // Extract coil ID from topic: pemf/coil/1/events -> 1
            val coilId = extractCoilIdFromTopic(topic) ?: return
            
            val json = gson.fromJson(payload, Map::class.java) as Map<*, *>
            
            val eventType = json["event_type"] as? String ?: ""
            val message = json["message"] as? String ?: ""
            val timestamp = (json["timestamp"] as? Number)?.toLong() ?: 0L
            val wifiConnected = json["wifi_connected"] as? Boolean ?: false
            val wifiSsid = json["wifi_ssid"] as? String
            val wifiIp = json["wifi_ip"] as? String
            
            val event = EventMessage(
                coilId = coilId.toInt(),
                eventType = eventType,
                message = message,
                timestamp = timestamp,
                wifiConnected = wifiConnected,
                wifiSsid = wifiSsid,
                wifiIp = wifiIp
            )
            
            // UI'a gönder
            scope.launch {
                _eventUpdates.emit(event)
            }
            
            AppLogger.d(TAG, "Event received: coilId=$coilId, type=$eventType, message=$message")
        } catch (e: Exception) {
            AppLogger.e(TAG, "Event verisi işlenemedi", e)
        }
    }
    
    private fun updateESPList() {
        scope.launch {
            // ✅ TEK KAYNAK TAKTİĞİ: Sadece gerçekten MQTT'ye bağlı ESP'leri göster
            // Retained messages eski verileri gösteriyor, ama ESP offline olabilir
            val connectedDevices = espDevicesMap.values
                .filter { it.connected } // Sadece mqtt_connected=true olanlar
                .sortedBy { it.id }
            
            _espListUpdates.emit(connectedDevices)
            AppLogger.d(TAG, "ESP list updated: ${connectedDevices.size} connected devices (filtered from ${espDevicesMap.size} total)")
        }
    }
    
    fun disconnect() {
        scope.launch {
            try {
                pingJob?.cancel()
                cleanupJob?.cancel()  // ✅ Cleanup job'ı iptal et
                cleanupOldClient()
                _connectionState.value = ConnectionState.DISCONNECTED
                espDevicesMap.clear()
            } catch (e: Exception) {
                AppLogger.e(TAG, "Error disconnecting MQTT", e)
            }
        }
    }
    
    /**
     * Network değişikliği algılandığında çağrılır
     * NOT: Paho client zaten isAutomaticReconnect = true olduğu için otomatik reconnect yapacak
     * Bu metod sadece loglama için kullanılıyor, manuel reconnect YAPMIYORUZ
     */
    fun onNetworkChanged() {
        AppLogger.d(TAG, "Network changed detected, Paho auto-reconnect is active")
        AppLogger.d(TAG, "Current state: ${_connectionState.value}, isConnected: ${mqttClient?.isConnected}")
        // Manuel reconnect YAPMA! Paho zaten otomatik bağlanacak
        // Bu çoklu reconnect ve race condition'ları önler
    }

    // Removed manual reconnect mechanism - using Paho's built-in isAutomaticReconnect=true
    
    // Session Control Commands - Android can now start/stop sessions
    /**
     * Android'den GUI'ye session başlatma komutu gönder
     */
    fun startSession(
        patientName: String,
        durationMinutes: Int,
        frequency: Float,
        intensity: Float,
        target: String,
        mode: String = "Manuel Tedavi"
    ) {
        scope.launch {
            try {
                val payload = mapOf(
                    "command" to "start_session",
                    "patient_name" to patientName,
                    "duration_minutes" to durationMinutes,
                    "frequency" to frequency,
                    "intensity" to intensity,
                    "target" to target,
                    "mode" to mode,
                    "timestamp" to System.currentTimeMillis()
                )
                
                val payloadJson = gson.toJson(payload)
                mqttClient?.publish("pemf/system/session/control", payloadJson.toByteArray(), 1, false)
                AppLogger.d(TAG, "Session start command sent: $patientName, ${durationMinutes}min")
            } catch (e: Exception) {
                AppLogger.e(TAG, "Failed to send session start command", e)
            }
        }
    }
    
    /**
     * Android'den GUI'ye session durdurma komutu gönder
     */
    fun stopSession() {
        scope.launch {
            val payload = mapOf(
                "command" to "stop_session",
                "timestamp" to System.currentTimeMillis()
            )
            // Use publishToTopic for Hybrid transport (MQTT/BLE)
            publishToTopic("pemf/system/session/control", payload)
            AppLogger.d(TAG, "Session stop command sent")
        }
    }
    
    // PWM Control Commands - Publish to MQTT topics
    fun startCoil(coilId: String, freq: Int, duty: Double, duration: Int) {
        publishControlCommand(coilId, "start", freq, duty, duration)
    }
    
    fun stopCoil(coilId: String) {
        publishControlCommand(coilId, "stop", null, null, null)
    }
    
    fun setCoilParams(coilId: String, freq: Int?, duty: Double?, duration: Int?) {
        publishControlCommand(coilId, "set_params", freq, duty, duration)
    }
    
    fun setParamsAllCoils(freq: Int, duty: Double, duration: Int) {
        // Sadece bağlı ESP'lere komut gönder (bireysel komutlar - tutarlılık için)
        val connectedDevices = espDevicesMap.values.filter { it.connected }
        
        if (connectedDevices.isEmpty()) {
            AppLogger.w(TAG, "setParamsAllCoils: No connected ESP devices found")
            return
        }
        
        // Her bağlı ESP'ye ayrı ayrı komut gönder (GUI donma sorununu önlemek için gecikme ile)
        scope.launch {
            var commandsSent = 0
            for (device in connectedDevices) {
                // ESP_001 -> 1, ESP_002 -> 2, etc.
                val coilNumber = device.id.replace("ESP_", "").toIntOrNull()
                if (coilNumber != null) {
                    // Use publishControlCommand for consistency (it handles command_id and ACK tracking)
                    publishControlCommand(device.id, "set_params", freq, duty, duration)
                    commandsSent++
                    
                    // GUI donma sorununu önlemek için 50ms gecikme
                    delay(50)
                }
            }
            
            AppLogger.d(TAG, "setParamsAllCoils: Sent to $commandsSent connected ESPs")
        }
    }
    
    fun startAllCoils(freq: Int, duty: Double, duration: Int) {
        // Sadece bağlı ESP'lere komut gönder
        val connectedDevices = espDevicesMap.values.filter { it.connected }
        
        if (connectedDevices.isEmpty()) {
            AppLogger.w(TAG, "startAllCoils: No connected ESP devices found")
            return
        }
        
        // Şu anki zaman + 2000ms buffer (NTP tabanlı senkronizasyon için)
        val targetStartTime = System.currentTimeMillis() + 2000
        
        // Her bağlı ESP'ye ayrı ayrı komut gönder (aynı start_at zamanı ile senkronizasyon için)
        // GUI donma sorununu önlemek için gecikme ile
        scope.launch {
            var commandsSent = 0
            for (device in connectedDevices) {
                // ESP_001 -> 1, ESP_002 -> 2, etc.
                val coilNumber = device.id.replace("ESP_", "").toIntOrNull()
                if (coilNumber != null) {
                    val topic = "pemf/coil/$coilNumber/control"
                    
                    // Generate unique command ID for ACK tracking
                    commandIdCounter++
                    val commandId = "cmd_all_${commandIdCounter}_${System.currentTimeMillis()}"
                    
                    val payload = mapOf(
                        "command" to "start",
                        "command_id" to commandId,
                        "freq" to freq,
                        "duty" to duty,
                        "duration" to duration,
                        "start_at" to targetStartTime  // NTP tabanlı senkronizasyon için hedef zaman
                    )
                    
                    // Track pending command for ACK
                    pendingCommands[commandId] = Pair(device.id, System.currentTimeMillis())
                    
                    publishToTopic(topic, payload)
                    commandsSent++
                    
                    // GUI donma sorununu önlemek için 50ms gecikme
                    delay(50)
                }
            }
            
            // Clean up old pending commands (older than 30 seconds)
            val currentTime = System.currentTimeMillis()
            pendingCommands.entries.removeAll { (_, value) ->
                currentTime - value.second > 30000
            }
            
            AppLogger.d(TAG, "startAllCoils: Sent to $commandsSent connected ESPs, targetStartTime=$targetStartTime (Unix Epoch ms)")
        }
    }
    
    fun stopAllCoils() {
        // Sadece bağlı ESP'lere komut gönder
        val connectedDevices = espDevicesMap.values.filter { it.connected }
        
        if (connectedDevices.isEmpty()) {
            AppLogger.w(TAG, "stopAllCoils: No connected ESP devices found")
            return
        }
        
        // Her bağlı ESP'ye ayrı ayrı komut gönder
        var commandsSent = 0
        for (device in connectedDevices) {
            // ESP_001 -> 1, ESP_002 -> 2, etc.
            val coilNumber = device.id.replace("ESP_", "").toIntOrNull()
            if (coilNumber != null) {
                val topic = "pemf/coil/$coilNumber/control"
                
                // Generate unique command ID for ACK tracking
                commandIdCounter++
                val commandId = "cmd_all_stop_${commandIdCounter}_${System.currentTimeMillis()}"
                
                val payload = mapOf(
                    "command" to "stop",
                    "command_id" to commandId
                )
                
                // Track pending command for ACK
                pendingCommands[commandId] = Pair(device.id, System.currentTimeMillis())
                
                publishToTopic(topic, payload)
                commandsSent++
            }
        }
        
        AppLogger.d(TAG, "stopAllCoils: Sent to $commandsSent connected ESPs")
    }

    fun updateFirmware(coilId: String, url: String) {
         val coilNumber = coilId.replace("ESP_", "").toIntOrNull() ?: return
         val topic = "pemf/coil/$coilNumber/control"
         
         val payload = mapOf(
            "command" to "UPDATE_FIRMWARE",
            "url" to url,
            "timestamp" to System.currentTimeMillis()
         )
         publishToTopic(topic, payload)
         AppLogger.d(TAG, "Sent Firmware Update command to $coilId with URL: $url")
    }

    
    private fun publishControlCommand(
        coilId: String,
        command: String,
        freq: Int?,
        duty: Double?,
        duration: Int?
    ) {
        // Convert ESP_001 to 1
        val coilNumber = coilId.replace("ESP_", "").toIntOrNull() ?: return
        val topic = "pemf/coil/$coilNumber/control"
        
        // Generate unique command ID for ACK tracking
        commandIdCounter++
        val commandId = "cmd_${coilNumber}_${commandIdCounter}_${System.currentTimeMillis()}"
        
        val payload = mutableMapOf<String, Any>(
            "command" to command,
            "command_id" to commandId
        )
        freq?.let { payload["freq"] = it }
        duty?.let { payload["duty"] = it }
        duration?.let { payload["duration"] = it }
        
        // Add start_at for start commands (NTP-based synchronization)
        if (command == "start") {
            val targetStartTime = System.currentTimeMillis() + 2000  // Current time + 2000ms buffer
            payload["start_at"] = targetStartTime
        }
        
        // Track pending command for ACK
        pendingCommands[commandId] = Pair(coilId, System.currentTimeMillis())
        
        // Clean up old pending commands (older than 30 seconds)
        val currentTime = System.currentTimeMillis()
        pendingCommands.entries.removeAll { (_, value) ->
            currentTime - value.second > 30000
        }
        
        publishToTopic(topic, payload)
    }
    
    private fun publishToTopic(topic: String, payload: Map<String, Any>) {
        val json = gson.toJson(payload)
        
        // Priority 1: MQTT
        if (mqttClient != null && _connectionState.value.isConnected()) {
            try {
                val message = MqttMessage(json.toByteArray())
                message.qos = 1
                
                mqttClient?.publish(topic, message)
                AppLogger.d(TAG, "Published to $topic: $json")
            } catch (e: Exception) {
                AppLogger.e(TAG, "Failed to publish to $topic", e)
            }
            return
        }
        
        // Priority 2: BLE Fallback
        // In offline mode, we send commands directly to the connected BLE device
        if (bleService.isConnected()) {
            AppLogger.d(TAG, "MQTT Offline -> Sending via BLE: $json")
            bleService.sendCommand(json)
            return
        }
        
        AppLogger.e(TAG, "No transport available (MQTT Disconnected, BLE Disconnected). Cannot publish to $topic")
    }
    
    /**
     * ✅ Tüm ESP'lerden fresh status iste
     * Reconnect sonrası retained message problem'i önlemek için
     */
    fun requestStatusFromAllESPs() {
        try {
            // FIX: Disabled blind polling of 1-8. 
            // Firmware sends status updates at 1Hz, so polling is redundant and causes spam.
            // Rely on passive discovery via heartbeat.
            AppLogger.d(TAG, "requestStatusFromAllESPs: Skipping blind poll (REMOVED to avoid spam)")
        } catch (e: Exception) {
            AppLogger.e(TAG, "Failed to request status from all ESPs", e)
        }
    }
    
    // Legacy methods for compatibility (no-op, data comes from MQTT automatically)
    fun requestStatus() {
        // Status updates come automatically via MQTT subscription
    }
    
    fun requestSensorData() {
        // Sensor data comes automatically via MQTT subscription
    }
    
    fun requestESPList() {
        // ESP list is built automatically from MQTT messages
    }
    
    fun cleanup() {
        disconnect()
        scope.cancel()
    }
}

