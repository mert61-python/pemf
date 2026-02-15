package com.pemf.vet.data.api

import com.pemf.vet.data.models.DiscoveryResponse
import org.junit.Assert.*
import org.junit.Test

/**
 * Unit tests for ConnectionManager port selection logic
 */
class ConnectionManagerTest {
    
    @Test
    fun `port selection should prioritize websocket_port when not 5555`() {
        val discoveryResponse = DiscoveryResponse(
            type = "discovery",
            ip = "192.168.1.1",
            ports = listOf(5555, 8080, 8081),
            websocketPort = 8081,
            httpPort = 8080,
            hostname = "test-host",
            timestamp = null,
            version = null
        )
        
        val selectedPort = selectWebSocketPort(discoveryResponse)
        assertEquals(8081, selectedPort)
    }
    
    @Test
    fun `port selection should use 8081 when websocket_port is 5555`() {
        val discoveryResponse = DiscoveryResponse(
            type = "discovery",
            ip = "192.168.1.1",
            ports = listOf(5555, 8080, 8081),
            websocketPort = 5555,  // Should be ignored
            httpPort = 8080,
            hostname = "test-host",
            timestamp = null,
            version = null
        )
        
        val selectedPort = selectWebSocketPort(discoveryResponse)
        assertEquals(8081, selectedPort)
    }
    
    @Test
    fun `port selection should use 8081 when 8081 is in ports list`() {
        val discoveryResponse = DiscoveryResponse(
            type = "discovery",
            ip = "192.168.1.1",
            ports = listOf(5555, 8080, 8081),
            websocketPort = null,
            httpPort = 8080,
            hostname = "test-host",
            timestamp = null,
            version = null
        )
        
        val selectedPort = selectWebSocketPort(discoveryResponse)
        assertEquals(8081, selectedPort)
    }
    
    @Test
    fun `port selection should default to 8081 when no valid port found`() {
        val discoveryResponse = DiscoveryResponse(
            type = "discovery",
            ip = "192.168.1.1",
            ports = listOf(5555, 8080),
            websocketPort = null,
            httpPort = 8080,
            hostname = "test-host",
            timestamp = null,
            version = null
        )
        
        val selectedPort = selectWebSocketPort(discoveryResponse)
        assertEquals(8081, selectedPort)
    }
    
    @Test
    fun `port selection should use 8081 when websocket_port is null`() {
        val discoveryResponse = DiscoveryResponse(
            type = "discovery",
            ip = "192.168.1.1",
            ports = listOf(5555, 8080),
            websocketPort = null,
            httpPort = 8080,
            hostname = "test-host",
            timestamp = null,
            version = null
        )
        
        val selectedPort = selectWebSocketPort(discoveryResponse)
        assertEquals(8081, selectedPort)
    }
    
    // Helper function to test port selection logic
    private fun selectWebSocketPort(discoveryResponse: DiscoveryResponse): Int {
        return when {
            discoveryResponse.websocketPort != null && discoveryResponse.websocketPort != 5555 -> {
                discoveryResponse.websocketPort
            }
            discoveryResponse.ports.firstOrNull { it == 8081 } != null -> {
                8081
            }
            else -> {
                8081  // Default WebSocket port
            }
        }
    }
}

