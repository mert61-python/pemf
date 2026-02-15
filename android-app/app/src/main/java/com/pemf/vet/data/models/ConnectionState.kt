package com.pemf.vet.data.models

enum class ConnectionState {
    DISCONNECTED,
    CONNECTING,
    CONNECTED,      // General/Legacy Connected (usually Cloud/MQTT)
    CONNECTED_CLOUD, // Cloud/MQTT specific
    CONNECTED_LOCAL, // BLE/Local specific
    ERROR
}

// Helper extension to treat all as "Connected"
fun ConnectionState.isConnected() = this == ConnectionState.CONNECTED || 
                                    this == ConnectionState.CONNECTED_CLOUD || 
                                    this == ConnectionState.CONNECTED_LOCAL

data class ConnectionInfo(
    val state: ConnectionState,
    val serverIp: String? = null,
    val serverPort: Int? = null, // Or BLE Device Name
    val errorMessage: String? = null,
    val transport: String = "MQTT" // MQTT or BLE
)

