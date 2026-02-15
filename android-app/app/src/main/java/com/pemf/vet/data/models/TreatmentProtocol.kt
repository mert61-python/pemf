package com.pemf.vet.data.models

data class TreatmentProtocol(
    val id: String,
    val name: String,
    val description: String,
    val frequency: Int,    // Hz
    val dutyCycle: Double, // %
    val duration: Int,     // Dakika
    val iconResId: Int? = null // İleride ikon desteği için
)
