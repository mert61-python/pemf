package com.pemf.vet.data.repository

import com.pemf.vet.data.api.ConnectionManager
import com.pemf.vet.data.models.ConnectionInfo
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.distinctUntilChanged
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class ConnectionRepository @Inject constructor(
    private val connectionManager: ConnectionManager
) {
    fun getConnectionInfo(): Flow<ConnectionInfo> {
        return connectionManager.getConnectionInfo()
            .distinctUntilChanged { old, new -> old.state == new.state }
    }
    
    // Legacy support or new simplified connect
    suspend fun connect(ip: String? = null): Boolean {
        return connectionManager.connect(ip)
    }
    
    fun disconnect() {
        connectionManager.disconnect()
    }
}

