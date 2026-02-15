package com.pemf.vet.data.api

import com.pemf.vet.data.models.SystemStatusResponse
import retrofit2.http.GET

interface PemfApiService {
    @GET("/api/status")
    suspend fun getSystemStatus(): SystemStatusResponse
    
    @GET("/discovery")
    suspend fun getDiscoveryInfo(): com.pemf.vet.data.models.DiscoveryResponse
}

