package com.pemf.vet.data.models

import android.os.Parcelable
import kotlinx.parcelize.Parcelize

@Parcelize
data class ESPDevice(
    val id: String, // ESP_001 to ESP_008
    val state: ConnectionState = ConnectionState.DISCONNECTED,
    val pwmStatus: PWMStatus? = null,
    val sensorData: SensorData? = null,
    val lastUpdate: Long = System.currentTimeMillis(),
    val fwVersion: String? = null // Added for OTA
) : Parcelable {
    val connected: Boolean
        get() = state.isConnected()
}

@Parcelize
data class PWMStatus(
    val active: Boolean = false,
    val frequency: Int = 0, // Hz
    val dutyCycle: Int = 0, // Percentage
    val duration: Int? = null, // Minutes (optional)
    val remainingTime: Int? = null // Seconds (optional)
) : Parcelable

