package com.pemf.vet.ui.home

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.pemf.vet.data.models.ConnectionInfo
import com.pemf.vet.data.models.ConnectionState
import com.pemf.vet.data.models.Session
import com.pemf.vet.data.repository.ConnectionRepository
import com.pemf.vet.data.repository.SessionRepository
import com.pemf.vet.data.local.PreferencesManager
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class HomeViewModel @Inject constructor(
    private val connectionRepository: ConnectionRepository,
    private val sessionRepository: SessionRepository,
    private val preferencesManager: PreferencesManager
) : ViewModel() {
    
    val connectionInfo: StateFlow<ConnectionInfo> = connectionRepository.getConnectionInfo()
        .stateIn(
            scope = viewModelScope,
            started = SharingStarted.WhileSubscribed(5000),
            initialValue = ConnectionInfo(ConnectionState.DISCONNECTED)
        )
    
    val activeSession: StateFlow<Session?> = sessionRepository.getActiveSession()
        .map { if (it.active) it else null }
        .stateIn(
            scope = viewModelScope,
            started = SharingStarted.WhileSubscribed(5000),
            initialValue = null
        )
    
    fun connectToServer() {
        viewModelScope.launch {
            if (preferencesManager.isAutoDiscoveryEnabled()) {
                connectionRepository.connect()
            } else {
                val ip = preferencesManager.getServerIp()
                // val port = preferencesManager.getServerPort() // Port is set globally in MQTT config or ignored
                if (ip != null) {
                    connectionRepository.connect(ip)
                }
            }
        }
    }
    
    fun connectWithIp(ip: String, port: Int) {
        viewModelScope.launch {
            connectionRepository.connect(ip)
        }
    }
}

