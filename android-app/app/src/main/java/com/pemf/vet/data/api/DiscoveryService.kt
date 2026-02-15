package com.pemf.vet.data.api

import android.content.Context
import android.net.wifi.WifiManager
import android.util.Log
import com.google.gson.Gson
import com.pemf.vet.data.models.DiscoveryResponse
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.*
import java.net.*
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class DiscoveryService @Inject constructor(
    @ApplicationContext private val context: Context,
    private val gson: Gson
) {
    private val TAG = "DiscoveryService"
    private val DISCOVERY_PORT = 5051
    private val DISCOVERY_TIMEOUT = 3000L // 3 seconds
    
    private var multicastLock: WifiManager.MulticastLock? = null
    
    init {
        val wifiManager = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager
        multicastLock = wifiManager?.createMulticastLock("PEMFDiscovery")
        multicastLock?.setReferenceCounted(true)
    }
    
    suspend fun discoverServer(): DiscoveryResponse? = withContext(Dispatchers.IO) {
        try {
            multicastLock?.acquire()
            
            val socket = DatagramSocket()
            socket.broadcast = true
            socket.soTimeout = DISCOVERY_TIMEOUT.toInt()
            
            // Send discovery request
            val request = mapOf("type" to "discovery")
            val requestJson = gson.toJson(request)
            val requestData = requestJson.toByteArray()
            
            val broadcastAddress = InetAddress.getByName("255.255.255.255")
            val packet = DatagramPacket(
                requestData,
                requestData.size,
                broadcastAddress,
                DISCOVERY_PORT
            )
            
            socket.send(packet)
            Log.d(TAG, "Discovery request sent")
            
            // Wait for response
            val buffer = ByteArray(1024)
            val responsePacket = DatagramPacket(buffer, buffer.size)
            
            try {
                socket.receive(responsePacket)
                val responseJson = String(responsePacket.data, 0, responsePacket.length)
                Log.d(TAG, "Discovery response received: $responseJson")
                
                val response = gson.fromJson(responseJson, DiscoveryResponse::class.java)
                socket.close()
                multicastLock?.release()
                
                return@withContext response
            } catch (e: SocketTimeoutException) {
                Log.d(TAG, "Discovery timeout")
                socket.close()
                multicastLock?.release()
                return@withContext null
            }
        } catch (e: Exception) {
            Log.e(TAG, "Discovery error", e)
            multicastLock?.release()
            return@withContext null
        }
    }
    
    fun cleanup() {
        multicastLock?.release()
    }
}

