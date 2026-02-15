package com.pemf.vet.data.repository

import com.pemf.vet.data.models.SensorData
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class SensorRepository @Inject constructor() {

    private val _sensorData = MutableStateFlow<Map<String, SensorData>>(emptyMap())
    val sensorData: StateFlow<Map<String, SensorData>> = _sensorData.asStateFlow()

    init {
        // 2x4 Grid yapısını korumak için başlangıçta 8 boş sensör verisi ekle
        val initialMap = mutableMapOf<String, SensorData>()
        for (i in 1..8) {
            val id = "ESP_${String.format("%03d", i)}"
            initialMap[id] = SensorData(espId = id, isConnected = false)
        }
        _sensorData.value = initialMap
    }

    fun updateSensorData(espId: String, data: SensorData) {
        _sensorData.update { currentMap ->
            currentMap + (espId to data)
        }
    }
    
    fun updateAllSensorData(dataMap: Map<String, SensorData>) {
        _sensorData.update { currentMap ->
            currentMap + dataMap
        }
    }
}

