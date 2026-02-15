package com.pemf.vet.data.models

/**
 * Event message from ESP devices
 * Topic: pemf/coil/{coilId}/events
 */
data class EventMessage(
    val coilId: Int,
    val eventType: String,  // e.g., "wifi_config_success", "wifi_connected", "error", etc.
    val message: String,
    val timestamp: Long,
    val wifiConnected: Boolean,
    val wifiSsid: String?,
    val wifiIp: String?
)
