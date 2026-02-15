package com.pemf.vet.ui.monitor

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.pemf.vet.data.api.MqttService
import com.pemf.vet.data.models.SensorData
import com.pemf.vet.data.models.UpdateInfo
import com.pemf.vet.data.models.ESPDevice
import com.pemf.vet.data.repository.ESPRepository
import com.pemf.vet.data.repository.SensorRepository
import com.pemf.vet.data.repository.UpdateRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class MonitorViewModel @Inject constructor(
    private val sensorRepository: SensorRepository,
    private val espRepository: ESPRepository,
    private val updateRepository: UpdateRepository,
    private val mqttService: MqttService
) : ViewModel() {
    
    val sensorData: StateFlow<Map<String, SensorData>> = sensorRepository.sensorData
        .stateIn(
            scope = viewModelScope,
            started = SharingStarted.WhileSubscribed(5000),
            initialValue = emptyMap()
        )
    
    // Listen for events (e.g., WiFi Disconnected / Offline Mode)
    val eventUpdates = mqttService.eventUpdates
        .shareIn(
            scope = viewModelScope,
            started = SharingStarted.WhileSubscribed(5000),
            replay = 0
        )
        
    // Exposed for UI to show update available icons
    private val _availableUpdates = MutableStateFlow<Map<String, UpdateInfo>>(emptyMap())
    val availableUpdates: StateFlow<Map<String, UpdateInfo>> = _availableUpdates.asStateFlow()
    
    init {
        mqttService.requestSensorData()
        monitorDevicesForUpdates()
    }
    
    private fun monitorDevicesForUpdates() {
        viewModelScope.launch {
            espRepository.devices.collect { devices: List<ESPDevice> ->
                for (device in devices) {
                    if (device.connected && device.fwVersion != null) {
                         // Avoid checking repeatedly
                         val currentMap = _availableUpdates.value
                         if (!currentMap.containsKey(device.id)) {
                             val info = updateRepository.checkForUpdates(device.fwVersion!!)
                             if (info != null) {
                                  _availableUpdates.value = currentMap + (device.id to info)
                             }
                         }
                    }
                }
            }
        }
    }
    
    fun triggerUpdate(deviceId: String) {
        val info = _availableUpdates.value[deviceId] ?: return
        mqttService.updateFirmware(deviceId, info.url)
    }
}

