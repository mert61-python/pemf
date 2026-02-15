package com.pemf.vet.data.repository

import com.pemf.vet.data.models.ConnectionState
import com.pemf.vet.data.models.ESPDevice
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class ESPRepository @Inject constructor() {

    // SSOT: All app listens here
    private val _devices = MutableStateFlow<List<ESPDevice>>(emptyList())
    val devices: StateFlow<List<ESPDevice>> = _devices.asStateFlow()

    fun updateDevice(device: ESPDevice) {
        _devices.update { currentList ->
            val index = currentList.indexOfFirst { it.id == device.id }
            if (index != -1) {
                val mutableList = currentList.toMutableList()
                mutableList[index] = device
                mutableList
            } else {
                currentList + device
            }
        }
    }

    fun updateDeviceState(deviceId: String, newState: ConnectionState) {
        _devices.update { currentList ->
            currentList.map { device ->
                if (device.id == deviceId) {
                    device.copy(state = newState, lastUpdate = System.currentTimeMillis())
                } else {
                    device
                }
            }
        }
    }
    
    fun setDevices(newDevices: List<ESPDevice>) {
        _devices.value = newDevices
    }

    fun removeDevice(deviceId: String) {
        _devices.update { currentList ->
            currentList.filter { it.id != deviceId }
        }
    }
    
    fun disconnectAll() {
        _devices.update { currentList ->
            currentList.map { it.copy(state = ConnectionState.DISCONNECTED) }
        }
    }
    
    fun getCurrentDevices(): List<ESPDevice> = _devices.value
}
