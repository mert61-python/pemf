package com.pemf.vet.data.api

import android.content.Context
import com.pemf.vet.data.models.ConnectionInfo
import com.pemf.vet.data.models.ConnectionState
import com.pemf.vet.utils.AppLogger
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class ConnectionManager @Inject constructor(
    private val mqttService: MqttService,
    private val bleService: BleService, // New service
    @ApplicationContext private val context: Context
) {
    private val TAG = "ConnManager"
    private val scope = CoroutineScope(Dispatchers.IO)
    
    // Unified State Flow
    private val _connectionInfo = MutableStateFlow(
        ConnectionInfo(ConnectionState.DISCONNECTED)
    )
    
    // Combine flows from MQTT and BLE
    fun getConnectionInfo(): Flow<ConnectionInfo> {
        return _connectionInfo.asStateFlow()
    }
    
    init {
        // Monitor MQTT
        scope.launch {
            mqttService.connectionState.collect { mqttState ->
                handleTransportStateChange(mqttState, true)
            }
        }
        
        // Monitor BLE Data and pipe to MqttService (Unified Processing)
        scope.launch {
            bleService.statusUpdates.collect { json ->
                AppLogger.d(TAG, "BLE Data Rx: $json")
                mqttService.processJsonMessage(json)
                
                // If we receive data, we are connected locally
                if (_connectionInfo.value.state != ConnectionState.CONNECTED_CLOUD) {
                    _connectionInfo.value = ConnectionInfo(ConnectionState.CONNECTED_LOCAL, transport = "BLE")
                }
            }
        }
    }
    
    private fun handleTransportStateChange(state: ConnectionState, isMqtt: Boolean) {
        val current = _connectionInfo.value.state
        
        if (isMqtt) {
            if (state == ConnectionState.CONNECTED_CLOUD || state == ConnectionState.CONNECTED) {
                 AppLogger.d(TAG, "Switched to CLOUD (MQTT)")
                _connectionInfo.value = ConnectionInfo(ConnectionState.CONNECTED_CLOUD, transport = "MQTT")
                
                // If we were on BLE, disconnect it (save battery/conflict)
                // Optional: Keep it as hot standby? User preference.
                // For now, simple switch:
                scope.launch { bleService.disconnect() }
            } else if (state == ConnectionState.DISCONNECTED || state == ConnectionState.ERROR) {
                 AppLogger.w(TAG, "MQTT Disconnected. Triggering BLE Fallback...")
                 // Fallback to BLE
                 bleService.scanAndConnectBestSignal(scope)
            }
        }
    }
    
    fun sendCommand(json: String) {
        val state = _connectionInfo.value.state
        if (state == ConnectionState.CONNECTED_CLOUD) {
            // How to send via MQTT? MqttService needs a publish method
            // Assuming mqttService.publish("pemf/control/...", json)
            // But logic might be inside ESPRepository
        } else if (state == ConnectionState.CONNECTED_LOCAL) {
            bleService.sendCommand(json)
        }
    }
    
    // Start Hybrid Auto-Connect
    suspend fun connect(targetIp: String? = null): Boolean {
        // 1. Try MQTT
        AppLogger.d(TAG, "Attempting MQTT Connect...")
        mqttService.connect()
        
        // Wait a bit
        delay(2000)
        
        if (mqttService.isConnected()) {
             return true
        }
        
        // 2. Fallback to BLE?
        // This usually requires a UI interaction to select device ("Scanning...")
        // We will return false here and let the UI decide to show "Switch to Bluetooth?"
        return false
    }
    
    fun disconnect() {
        mqttService.disconnect()
        scope.launch { bleService.disconnect() }
        _connectionInfo.value = ConnectionInfo(ConnectionState.DISCONNECTED)
    }
}


