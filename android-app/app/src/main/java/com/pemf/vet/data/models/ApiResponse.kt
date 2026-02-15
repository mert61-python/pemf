package com.pemf.vet.data.models

import com.google.gson.annotations.SerializedName

data class SystemStatusResponse(
    @SerializedName("timestamp")
    val timestamp: String,
    @SerializedName("system_status")
    val systemStatus: String,
    @SerializedName("treatment_active")
    val treatmentActive: Boolean,
    @SerializedName("current_parameters")
    val currentParameters: CurrentParameters,
    @SerializedName("websocket_clients")
    val websocketClients: Int
)

data class CurrentParameters(
    @SerializedName("frequency")
    val frequency: Float,
    @SerializedName("intensity")
    val intensity: Float,
    @SerializedName("duration")
    val duration: Int
)

data class DiscoveryResponse(
    @SerializedName("type")
    val type: String,
    @SerializedName("ip")
    val ip: String,
    @SerializedName("ports")
    val ports: List<Int>,
    @SerializedName("websocket_port")
    val websocketPort: Int?,
    @SerializedName("http_port")
    val httpPort: Int,
    @SerializedName("hostname")
    val hostname: String,
    @SerializedName("timestamp")
    val timestamp: String?,
    @SerializedName("version")
    val version: String?
)

data class WebSocketMessage(
    @SerializedName("type")
    val type: String,
    @SerializedName("payload")
    val payload: Any?
)

data class StatusUpdatePayload(
    @SerializedName("timestamp")
    val timestamp: String,
    @SerializedName("system_status")
    val systemStatus: String,
    @SerializedName("treatment_active")
    val treatmentActive: Boolean,
    @SerializedName("current_parameters")
    val currentParameters: CurrentParameters?,
    @SerializedName("connection_count")
    val connectionCount: Int?,
    @SerializedName("websocket_clients")
    val websocketClients: Int?
)

data class SensorDataPayload(
    @SerializedName("esps")
    val esps: List<ESPSensorData>?  // Python sunucu LIST gönderiyor, Map değil!
)

data class ESPSensorData(
    @SerializedName("esp_id")
    val espId: String?,
    @SerializedName("coil_id")
    val coilId: Int?,
    @SerializedName("object_temp")
    val objectTemp: Float?,
    @SerializedName("ambient_temp")
    val ambientTemp: Float?,
    @SerializedName("magnetic_field")
    val magneticField: Float?,
    @SerializedName("current")
    val current: Float?,
    @SerializedName("voltage")
    val voltage: Float?,
    @SerializedName("frequency")
    val frequency: Float?,
    @SerializedName("esp_status")
    val espStatus: String?,
    @SerializedName("data_age")
    val dataAge: Double?,
    @SerializedName("timestamp")
    val timestamp: Long?
)

data class ESPListPayload(
    @SerializedName("esps")
    val esps: List<ESPInfo>?,
    @SerializedName("timestamp")
    val timestamp: String?
)

data class ESPInfo(
    @SerializedName("esp_id")
    val espId: String,
    @SerializedName("coil_id")
    val coilId: Int?,
    @SerializedName("online")
    val online: Boolean,
    @SerializedName("last_seen")
    val lastSeen: Double?,
    @SerializedName("data_age")
    val dataAge: Double?,
    @SerializedName("sensor_data")
    val sensorData: ESPInfoSensorData?,
    @SerializedName("pwm_status")
    val pwmStatus: ESPPWMStatus?
)

data class ESPPWMStatus(
    @SerializedName("active")
    val active: Boolean?,
    @SerializedName("frequency")
    val frequency: Int?,
    @SerializedName("duty_cycle")
    val dutyCycle: Int?,
    @SerializedName("duration")
    val duration: Int?,
    @SerializedName("remaining_time")
    val remainingTime: Int?
)

data class ESPInfoSensorData(
    @SerializedName("object_temp")
    val objectTemp: Float?,
    @SerializedName("ambient_temp")
    val ambientTemp: Float?,
    @SerializedName("magnetic_field")
    val magneticField: Float?,
    @SerializedName("current")
    val current: Float?,
    @SerializedName("voltage")
    val voltage: Float?,
    @SerializedName("frequency")
    val frequency: Float?,
    @SerializedName("sensors_ok")
    val sensorsOk: Boolean?,
    @SerializedName("timestamp")
    val timestamp: Long?
)

data class TreatmentUpdatePayload(
    @SerializedName("active")
    val active: Boolean,
    @SerializedName("start_time")
    val startTime: String?,
    @SerializedName("duration")
    val duration: Int?,
    @SerializedName("frequency")
    val frequency: Float?,
    @SerializedName("intensity")
    val intensity: Float?,
    @SerializedName("target")
    val target: String?,
    @SerializedName("treatment_mode")
    val treatmentMode: String?,
    @SerializedName("patient_name")
    val patientName: String?,
    @SerializedName("session_id")
    val sessionId: Int?,
    @SerializedName("active_esps")
    val activeESPs: List<String>?
)

