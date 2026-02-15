package com.pemf.vet.data.local

import android.content.Context
import android.content.SharedPreferences
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class PreferencesManager @Inject constructor(
    @ApplicationContext private val context: Context
) {
    private val prefs: SharedPreferences = context.getSharedPreferences(
        "pemf_prefs",
        Context.MODE_PRIVATE
    )
    
    private val KEY_SERVER_IP = "server_ip"
    private val KEY_SERVER_PORT = "server_port"
    private val KEY_AUTO_DISCOVERY = "auto_discovery"
    
    fun saveServerIp(ip: String) {
        prefs.edit().putString(KEY_SERVER_IP, ip).apply()
    }
    
    fun getServerIp(): String? {
        return prefs.getString(KEY_SERVER_IP, null)
    }
    
    fun saveServerPort(port: Int) {
        prefs.edit().putInt(KEY_SERVER_PORT, port).apply()
    }
    
    fun getServerPort(): Int {
        return prefs.getInt(KEY_SERVER_PORT, 8081)
    }
    
    fun setAutoDiscovery(enabled: Boolean) {
        prefs.edit().putBoolean(KEY_AUTO_DISCOVERY, enabled).apply()
    }
    
    fun isAutoDiscoveryEnabled(): Boolean {
        return prefs.getBoolean(KEY_AUTO_DISCOVERY, true)
    }
}

