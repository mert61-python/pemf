package com.pemf.vet.data.repository

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton

private val Context.dataStore: DataStore<Preferences> by preferencesDataStore(name = "settings")

@Singleton
class SettingsRepository @Inject constructor(
    @ApplicationContext private val context: Context
) {
    private object PreferencesKeys {
        val MQTT_BROKER = stringPreferencesKey("mqtt_broker")
        val MQTT_PORT = intPreferencesKey("mqtt_port")
        val DEVICE_NAME = stringPreferencesKey("device_name")
    }

    private companion object {
        const val DEFAULT_BROKER = "192.168.4.1"
        const val DEFAULT_PORT = 1883
        const val DEFAULT_DEVICE_NAME = "PEMF-Device"
    }

    suspend fun getMqttBroker(): String {
        return context.dataStore.data.map { preferences ->
            preferences[PreferencesKeys.MQTT_BROKER] ?: DEFAULT_BROKER
        }.first()
    }

    suspend fun setMqttBroker(broker: String) {
        context.dataStore.edit { preferences ->
            preferences[PreferencesKeys.MQTT_BROKER] = broker
        }
    }

    suspend fun getMqttPort(): Int {
        return context.dataStore.data.map { preferences ->
            preferences[PreferencesKeys.MQTT_PORT] ?: DEFAULT_PORT
        }.first()
    }

    suspend fun setMqttPort(port: Int) {
        context.dataStore.edit { preferences ->
            preferences[PreferencesKeys.MQTT_PORT] = port
        }
    }

    suspend fun getDeviceName(): String {
        return context.dataStore.data.map { preferences ->
            preferences[PreferencesKeys.DEVICE_NAME] ?: DEFAULT_DEVICE_NAME
        }.first()
    }

    suspend fun setDeviceName(name: String) {
        context.dataStore.edit { preferences ->
            preferences[PreferencesKeys.DEVICE_NAME] = name
        }
    }

    suspend fun resetToDefaults() {
        context.dataStore.edit { preferences ->
            preferences.clear()
        }
    }

    suspend fun exportSystemLogs() {
        // Export logs to external storage
        val logFile = File(context.getExternalFilesDir(null), "pemf_logs.txt")
        try {
            // Collect logs from various sources
            val logs = buildString {
                appendLine("PEMF System Logs")
                appendLine("Generated: ${System.currentTimeMillis()}")
                appendLine("---")
                appendLine("MQTT Broker: ${getMqttBroker()}")
                appendLine("MQTT Port: ${getMqttPort()}")
                appendLine("Device Name: ${getDeviceName()}")
                // Add more log sources as needed
            }
            logFile.writeText(logs)
        } catch (e: Exception) {
            throw Exception("Failed to export logs: ${e.message}")
        }
    }
}
