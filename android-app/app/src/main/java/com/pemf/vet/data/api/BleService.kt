package com.pemf.vet.data.api

import android.bluetooth.BluetoothDevice
import android.content.Context
import android.util.Log
import com.pemf.vet.connection.PemfBleManager
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.launch
import no.nordicsemi.android.ble.ktx.suspend
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class BleService @Inject constructor(
    @ApplicationContext private val context: Context
) {
    private val manager = PemfBleManager(context)
    
    val statusUpdates: SharedFlow<String> = manager.statusFlow

    suspend fun connect(device: BluetoothDevice) {
        manager.connect(device)
            .retry(3, 100)
            .useAutoConnect(true)
            .timeout(10000)
            .suspend()
    }
    
    fun scanAndConnectBestSignal(scope: CoroutineScope) {
        try {
            val bluetoothManager = context.getSystemService(Context.BLUETOOTH_SERVICE) as android.bluetooth.BluetoothManager
            val adapter = bluetoothManager.adapter
            val scanner = adapter?.bluetoothLeScanner ?: return
            
            val settings = android.bluetooth.le.ScanSettings.Builder()
                .setScanMode(android.bluetooth.le.ScanSettings.SCAN_MODE_LOW_LATENCY)
                .build()
                
            val callback = object : android.bluetooth.le.ScanCallback() {
                override fun onScanResult(callbackType: Int, result: android.bluetooth.le.ScanResult?) {
                    val device = result?.device ?: return
                    val deviceName = try { device.name } catch(e: SecurityException) { null }
                    if (deviceName?.startsWith("PEMF") == true) {
                        try {
                           scanner.stopScan(this)
                           Log.d("BleService", "Found PEMF device: $deviceName, connecting...")
                           scope.launch { connect(device) }
                        } catch(e: SecurityException) { e.printStackTrace() }
                    }
                }
            }
            
            Log.d("BleService", "Starting BLE Scan for fallback...")
            scanner.startScan(null, settings, callback)
            
            // Stop scan after 10s
            scope.launch {
                kotlinx.coroutines.delay(10000)
                try { scanner.stopScan(callback) } catch(e: Exception) {}
            }
        } catch (e: SecurityException) {
            Log.e("BleService", "Permission missing for scan", e)
        } catch (e: Exception) {
            Log.e("BleService", "Scan failed", e)
        }
    }

    suspend fun disconnect() {
        manager.disconnect().suspend()
    }

    fun sendCommand(json: String) {
        manager.sendCommand(json)
    }

    fun isConnected(): Boolean {
        return manager.isConnected
    }
}
