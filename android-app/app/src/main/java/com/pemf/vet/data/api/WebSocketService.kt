package com.pemf.vet.data.api

import com.pemf.vet.data.models.ConnectionState
import com.pemf.vet.data.models.ESPDevice
import com.pemf.vet.data.models.SensorData
import com.pemf.vet.data.models.Session
import com.pemf.vet.data.models.StatusUpdatePayload
import com.pemf.vet.utils.AppLogger
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import javax.inject.Inject
import javax.inject.Singleton

/**
 * WebSocket Service - DEPRECATED
 * 
 * This class is kept for backward compatibility only. All functionality has been
 * migrated to MqttService which connects directly to HiveMQ Cloud.
 * 
 * This wrapper delegates all calls to MqttService to maintain compatibility with
 * existing code that references WebSocketService.
 * 
 * @deprecated Use MqttService instead. This class will be removed in a future version.
 * @see MqttService
 */
@Deprecated(
    message = "Use MqttService instead",
    replaceWith = ReplaceWith("MqttService", "com.pemf.vet.data.api.MqttService")
)
@Singleton
class WebSocketService @Inject constructor(
    private val mqttService: MqttService
) {
    private val TAG = "WebSocketService"
    
    /**
     * Connection state flow - delegates to MqttService
     * @see MqttService.connectionState
     */
    val connectionState: StateFlow<ConnectionState> = mqttService.connectionState
    
    /**
     * Status updates flow - delegates to MqttService
     * @see MqttService.statusUpdates
     */
    val statusUpdates: SharedFlow<StatusUpdatePayload> = mqttService.statusUpdates
    
    /**
     * Sensor data updates flow - delegates to MqttService
     * @see MqttService.sensorDataUpdates
     */
    val sensorDataUpdates: SharedFlow<Map<String, SensorData>> = mqttService.sensorDataUpdates
    
    /**
     * ESP device list updates flow - delegates to MqttService
     * @see MqttService.espListUpdates
     */
    val espListUpdates: SharedFlow<List<ESPDevice>> = mqttService.espListUpdates
    
    /**
     * Session updates flow - delegates to MqttService
     * @see MqttService.sessionUpdates
     */
    val sessionUpdates: SharedFlow<Session> = mqttService.sessionUpdates
    
    /**
     * Connect to the server (delegates to MqttService)
     * 
     * Note: MqttService auto-connects on initialization, so serverIp and port
     * parameters are ignored. They are kept for backward compatibility.
     * 
     * @param serverIp Ignored - MqttService uses HiveMQ Cloud
     * @param port Ignored - MqttService uses port 8883 (SSL)
     * @see MqttService.connect
     */
    @Suppress("UNUSED_PARAMETER")
    fun connect(serverIp: String, port: Int) {
        AppLogger.d(TAG, "WebSocketService.connect() called - delegating to MqttService (parameters ignored)")
        mqttService.connect()
    }
    
    /**
     * Disconnect from the server (delegates to MqttService)
     * @see MqttService.disconnect
     */
    fun disconnect() {
        AppLogger.d(TAG, "WebSocketService.disconnect() called - delegating to MqttService")
        mqttService.disconnect()
    }
    
    /**
     * Request status update (delegates to MqttService)
     * 
     * Note: In MQTT mode, status updates come automatically via subscription.
     * This method is kept for backward compatibility.
     * 
     * @see MqttService.requestStatus
     */
    fun requestStatus() {
        mqttService.requestStatus()
    }
    
    /**
     * Request sensor data (delegates to MqttService)
     * 
     * Note: In MQTT mode, sensor data comes automatically via subscription.
     * This method is kept for backward compatibility.
     * 
     * @see MqttService.requestSensorData
     */
    fun requestSensorData() {
        mqttService.requestSensorData()
    }
    
    /**
     * Request ESP device list (delegates to MqttService)
     * 
     * Note: In MQTT mode, ESP list is built automatically from MQTT messages.
     * This method is kept for backward compatibility.
     * 
     * @see MqttService.requestESPList
     */
    fun requestESPList() {
        mqttService.requestESPList()
    }
    
    /**
     * Start PWM on a specific coil (delegates to MqttService)
     * 
     * @param coilId Coil ID in format "ESP_001", "ESP_002", etc.
     * @param freq Frequency in Hz (1-1000)
     * @param duty Duty cycle as percentage (0.1-99.9)
     * @param duration Duration in minutes (0 = unlimited)
     * @see MqttService.startCoil
     */
    fun startCoil(coilId: String, freq: Int, duty: Double, duration: Int) {
        AppLogger.d(TAG, "startCoil: coilId=$coilId, freq=$freq, duty=$duty, duration=$duration")
        mqttService.startCoil(coilId, freq, duty, duration)
    }
    
    /**
     * Stop PWM on a specific coil (delegates to MqttService)
     * 
     * @param coilId Coil ID in format "ESP_001", "ESP_002", etc.
     * @see MqttService.stopCoil
     */
    fun stopCoil(coilId: String) {
        AppLogger.d(TAG, "stopCoil: coilId=$coilId")
        mqttService.stopCoil(coilId)
    }
    
    /**
     * Set PWM parameters on a specific coil without starting (delegates to MqttService)
     * 
     * @param coilId Coil ID in format "ESP_001", "ESP_002", etc.
     * @param freq Frequency in Hz (1-1000), null to keep current
     * @param duty Duty cycle as percentage (0.1-99.9), null to keep current
     * @param duration Duration in minutes (0 = unlimited), null to keep current
     * @see MqttService.setCoilParams
     */
    fun setCoilParams(coilId: String, freq: Int?, duty: Double?, duration: Int?) {
        AppLogger.d(TAG, "setCoilParams: coilId=$coilId, freq=$freq, duty=$duty, duration=$duration")
        mqttService.setCoilParams(coilId, freq, duty, duration)
    }
    
    /**
     * Set PWM parameters on all coils without starting (delegates to MqttService)
     * 
     * @param freq Frequency in Hz (1-1000)
     * @param duty Duty cycle as percentage (0.1-99.9)
     * @param duration Duration in minutes (0 = unlimited)
     * @see MqttService.setParamsAllCoils
     */
    fun setParamsAllCoils(freq: Int, duty: Double, duration: Int) {
        AppLogger.d(TAG, "setParamsAllCoils: freq=$freq, duty=$duty, duration=$duration")
        mqttService.setParamsAllCoils(freq, duty, duration)
    }
    
    /**
     * Start PWM on all coils (delegates to MqttService)
     * 
     * @param freq Frequency in Hz (1-1000)
     * @param duty Duty cycle as percentage (0.1-99.9)
     * @param duration Duration in minutes (0 = unlimited)
     * @see MqttService.startAllCoils
     */
    fun startAllCoils(freq: Int, duty: Double, duration: Int) {
        AppLogger.d(TAG, "startAllCoils: freq=$freq, duty=$duty, duration=$duration")
        mqttService.startAllCoils(freq, duty, duration)
    }
    
    /**
     * Stop PWM on all coils (delegates to MqttService)
     * @see MqttService.stopAllCoils
     */
    fun stopAllCoils() {
        AppLogger.d(TAG, "stopAllCoils called")
        mqttService.stopAllCoils()
    }
    
    /**
     * Cleanup and disconnect (delegates to MqttService)
     * 
     * This method should be called when the service is no longer needed,
     * typically when the application is being destroyed.
     * 
     * @see MqttService.cleanup
     */
    fun cleanup() {
        AppLogger.d(TAG, "cleanup called - delegating to MqttService")
        mqttService.cleanup()
    }
}
