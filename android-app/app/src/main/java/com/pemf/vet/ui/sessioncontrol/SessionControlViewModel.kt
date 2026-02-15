package com.pemf.vet.ui.sessioncontrol

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.pemf.vet.data.api.MqttService
import com.pemf.vet.data.models.ConnectionState
import com.pemf.vet.data.models.ESPDevice
import com.pemf.vet.data.models.Session
import com.pemf.vet.data.repository.ESPRepository
import com.pemf.vet.data.repository.SessionRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.*
import javax.inject.Inject

import com.pemf.vet.data.models.TreatmentProtocol

@HiltViewModel
class SessionControlViewModel @Inject constructor(
    private val espRepository: ESPRepository,
    private val sessionRepository: SessionRepository,
    private val mqttService: MqttService
) : ViewModel() {
    
    // ✅ Hazır Tedavi Protokolleri
    val protocols = listOf(
        TreatmentProtocol("p1", "Artrit / Kireçlenme", "Eklem ağrıları ve kronik inflamasyon için", 50, 50.0, 30),
        TreatmentProtocol("p2", "Kırık İyileşmesi", "Kemik kaynamasını hızlandırmak için", 75, 40.0, 45),
        TreatmentProtocol("p3", "Akut Ağrı", "Ani gelişen travma ve ağrılar için", 100, 70.0, 20),
        TreatmentProtocol("p4", "Derin Rahatlama", "Stres azaltma ve kas gevşetme", 10, 30.0, 60),
        TreatmentProtocol("p5", "Yara İyileşmesi", "Yumuşak doku hasarları için", 25, 50.0, 40)
    )

    // ✅ TÜM ESP'leri göster (bağlı ve bağlantısız)
    // Kullanıcı hangi ESP'nin bağlı olmadığını görebilmeli
    val espDevices: StateFlow<List<ESPDevice>> = espRepository.devices
        .stateIn(
            scope = viewModelScope,
            started = SharingStarted.WhileSubscribed(5000),
            initialValue = emptyList()
        )
    
    val activeSession: StateFlow<Session?> = sessionRepository.getActiveSession()
        .map { if (it.active) it else null }
        .stateIn(
            scope = viewModelScope,
            started = SharingStarted.WhileSubscribed(5000),
            initialValue = null
        )
    
    // Master parameters for bulk control
    private val _masterFrequency = MutableStateFlow(100)
    val masterFrequency: StateFlow<Int> = _masterFrequency.asStateFlow()
    
    private val _masterDuty = MutableStateFlow(50.0)
    val masterDuty: StateFlow<Double> = _masterDuty.asStateFlow()
    
    private val _masterDuration = MutableStateFlow(0) // 0 = unlimited
    val masterDuration: StateFlow<Int> = _masterDuration.asStateFlow()
    
    init {
        // espRepository.requestESPList() removed as it is now auto-managed by MqttService/ESPRepository
    }
    
    // PWM Control Functions
    // Single source of truth: PWM status comes only from ESP devices
    fun startCoil(coilId: String, freq: Int, duty: Double, duration: Int) {
        // Send command to server - ESP will update its status and broadcast it
        mqttService.startCoil(coilId, freq, duty, duration)
    }
    
    fun stopCoil(coilId: String) {
        android.util.Log.d("SessionControlViewModel", "stopCoil called for coilId: $coilId")
        // Send command to server - ESP will update its status and broadcast it
        mqttService.stopCoil(coilId)
    }
    
    fun setCoilParams(coilId: String, freq: Int?, duty: Double?, duration: Int?) {
        mqttService.setCoilParams(coilId, freq, duty, duration)
    }
    
    fun applyToAllCoils(freq: Int, duty: Double, duration: Int) {
        // Update master parameters
        _masterFrequency.value = freq
        _masterDuty.value = duty
        _masterDuration.value = duration
        // Send set_params_all command to update parameters for all connected ESPs
        // Server will only send to connected ESPs
        mqttService.setParamsAllCoils(freq, duty, duration)
    }
    
    fun startAllCoils(freq: Int, duty: Double, duration: Int) {
        // Update master parameters
        _masterFrequency.value = freq
        _masterDuty.value = duty
        _masterDuration.value = duration
        // Send command - ESP devices will update their status and broadcast it
        mqttService.startAllCoils(freq, duty, duration)
    }
    
    fun stopAllCoils() {
        // Send command - ESP devices will update their status and broadcast it
        mqttService.stopAllCoils()
    }
    
    // Master parameter setters
    fun setMasterFrequency(freq: Int) {
        _masterFrequency.value = freq.coerceIn(0, 1000)
    }
    
    fun setMasterDuty(duty: Double) {
        _masterDuty.value = duty.coerceIn(0.1, 99.9)
    }
    
    fun setMasterDuration(duration: Int) {
        _masterDuration.value = duration.coerceIn(0, 9999)
    }
    
    /**
     * Arka plandan dönüldüğünde verileri yenile
     * MQTT zaten StateFlow ile son durumu sağlıyor, buraya ek işlem gerekmiyor
     * Gerekirse ESP listesi yeniden sorgulanabilir
     */
    fun refreshSessionData() {
        // StateFlow otomatik olarak son değeri yayar, ek bir işlem gerekmiyor
        // Gerekirse ESP listesi güncellenebilir
        mqttService.requestStatus()
    }
}

