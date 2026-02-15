package com.pemf.vet.ui.system

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.pemf.vet.data.repository.SettingsRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

data class SystemSettings(
    val mqttBroker: String = "192.168.4.1",
    val mqttPort: Int = 1883,
    val deviceName: String = "PEMF-Device"
)

@HiltViewModel
class SystemSettingsViewModel @Inject constructor(
    private val settingsRepository: SettingsRepository
) : ViewModel() {

    private val _systemSettings = MutableStateFlow(SystemSettings())
    val systemSettings: StateFlow<SystemSettings> = _systemSettings.asStateFlow()

    val currentBroker: String
        get() = _systemSettings.value.mqttBroker

    val currentPort: Int
        get() = _systemSettings.value.mqttPort

    val currentDeviceName: String
        get() = _systemSettings.value.deviceName

    init {
        loadSettings()
    }

    private fun loadSettings() {
        viewModelScope.launch {
            try {
                val broker = settingsRepository.getMqttBroker()
                val port = settingsRepository.getMqttPort()
                val deviceName = settingsRepository.getDeviceName()
                
                _systemSettings.value = SystemSettings(
                    mqttBroker = broker,
                    mqttPort = port,
                    deviceName = deviceName
                )
            } catch (e: Exception) {
                // Use defaults on error
            }
        }
    }

    fun updateMqttBroker(broker: String) {
        viewModelScope.launch {
            try {
                settingsRepository.setMqttBroker(broker)
                _systemSettings.value = _systemSettings.value.copy(mqttBroker = broker)
            } catch (e: Exception) {
                // Handle error
            }
        }
    }

    fun updateMqttPort(port: Int) {
        viewModelScope.launch {
            try {
                settingsRepository.setMqttPort(port)
                _systemSettings.value = _systemSettings.value.copy(mqttPort = port)
            } catch (e: Exception) {
                // Handle error
            }
        }
    }

    fun updateDeviceName(name: String) {
        viewModelScope.launch {
            try {
                settingsRepository.setDeviceName(name)
                _systemSettings.value = _systemSettings.value.copy(deviceName = name)
            } catch (e: Exception) {
                // Handle error
            }
        }
    }

    fun resetToDefaults() {
        viewModelScope.launch {
            try {
                settingsRepository.resetToDefaults()
                _systemSettings.value = SystemSettings()
            } catch (e: Exception) {
                // Handle error
            }
        }
    }

    suspend fun exportLogs() {
        // Implement log export functionality
        settingsRepository.exportSystemLogs()
    }
}
