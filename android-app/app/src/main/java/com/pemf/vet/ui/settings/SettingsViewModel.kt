package com.pemf.vet.ui.settings

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.pemf.vet.data.local.PreferencesManager
import com.pemf.vet.data.models.ConnectionInfo
import com.pemf.vet.data.models.ConnectionState
import com.pemf.vet.data.repository.ConnectionRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class SettingsViewModel @Inject constructor(
    private val preferencesManager: PreferencesManager,
    private val connectionRepository: ConnectionRepository
) : ViewModel() {
    
    private val _serverIp = MutableStateFlow(preferencesManager.getServerIp() ?: "")
    val serverIp: StateFlow<String> = _serverIp.asStateFlow()
    
    private val _serverPort = MutableStateFlow(preferencesManager.getServerPort())
    val serverPort: StateFlow<Int> = _serverPort.asStateFlow()
    
    private val _autoDiscovery = MutableStateFlow(preferencesManager.isAutoDiscoveryEnabled())
    val autoDiscovery: StateFlow<Boolean> = _autoDiscovery.asStateFlow()
    
    val connectionInfo: StateFlow<ConnectionInfo> = connectionRepository.getConnectionInfo()
        .stateIn(
            scope = viewModelScope,
            started = SharingStarted.WhileSubscribed(5000),
            initialValue = ConnectionInfo(ConnectionState.DISCONNECTED)
        )
    
    fun updateServerIp(ip: String) {
        _serverIp.value = ip
        preferencesManager.saveServerIp(ip)
    }
    
    fun updateServerPort(port: Int) {
        _serverPort.value = port
        preferencesManager.saveServerPort(port)
    }
    
    fun setAutoDiscovery(enabled: Boolean) {
        _autoDiscovery.value = enabled
        preferencesManager.setAutoDiscovery(enabled)
    }
    
    fun connect() {
        viewModelScope.launch {
            if (_autoDiscovery.value) {
                connectionRepository.connect()
            } else {
                val ip = _serverIp.value
                val port = _serverPort.value
                if (ip.isNotEmpty() && isValidIp(ip) && isValidPort(port)) {
                    connectionRepository.connect(ip)
                }
            }
        }
    }
    
    fun disconnect() {
        connectionRepository.disconnect()
    }
    
    fun isValidIp(ip: String): Boolean {
        val ipPattern = "^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$"
        return ip.matches(Regex(ipPattern))
    }
    
    fun isValidPort(port: Int): Boolean {
        return port in 1..65535
    }
}

