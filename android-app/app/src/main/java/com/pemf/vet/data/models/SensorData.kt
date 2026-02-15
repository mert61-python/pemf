package com.pemf.vet.data.models

import android.os.Parcelable
import kotlinx.parcelize.Parcelize

@Parcelize
data class SensorData(
    val espId: String,
    val objectTemperature: Float = 0f, // °C
    val ambientTemperature: Float = 0f, // °C
    val magneticField: Float = 0f, // mT
    val current: Float = 0f, // A
    val voltage: Float = 0f, // V
    val frequency: Float = 0f, // Hz
    val timestamp: Long = System.currentTimeMillis(),
    val isConnected: Boolean = false
) : Parcelable

