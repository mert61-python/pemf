package com.pemf.vet.connection

import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothGattService
import android.content.Context
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.launch
import no.nordicsemi.android.ble.BleManager
import no.nordicsemi.android.ble.ktx.asFlow
import no.nordicsemi.android.ble.ktx.suspend
import java.util.UUID

class PemfBleManager(context: Context) : BleManager(context) {

    private val scope = CoroutineScope(Dispatchers.IO)

    // UUIDs
    val SERVICE_UUID: UUID = UUID.fromString("4fafc201-1fb5-459e-8fcc-c5c9c331914b")
    val COMMAND_CHAR_UUID: UUID = UUID.fromString("beb5483e-36e1-4688-b7f5-ea07361b26a8")
    val STATUS_CHAR_UUID: UUID = UUID.fromString("885e7834-31e8-467b-a36c-2f92f254923e")
    // Provisioning UUIDs
    val WIFI_SSID_UUID: UUID = UUID.fromString("c6f6696d-74d3-469a-8b3d-71b569502928")
    val WIFI_PASS_UUID: UUID = UUID.fromString("4466b8d7-06c8-47e9-a76f-22a912c9bf13")

    // Characteristics
    private var commandChar: BluetoothGattCharacteristic? = null
    private var statusChar: BluetoothGattCharacteristic? = null
    private var ssidChar: BluetoothGattCharacteristic? = null
    private var passChar: BluetoothGattCharacteristic? = null

    // Flows
    private val _statusFlow = MutableSharedFlow<String>()
    val statusFlow: SharedFlow<String> = _statusFlow.asSharedFlow()

    override fun getGattCallback(): BleManagerGattCallback {
        return PemfGattCallback()
    }

    private inner class PemfGattCallback : BleManagerGattCallback() {
        override fun isRequiredServiceSupported(gatt: BluetoothGatt): Boolean {
            val service: BluetoothGattService? = gatt.getService(SERVICE_UUID)
            if (service != null) {
                commandChar = service.getCharacteristic(COMMAND_CHAR_UUID)
                statusChar = service.getCharacteristic(STATUS_CHAR_UUID)
                ssidChar = service.getCharacteristic(WIFI_SSID_UUID)
                passChar = service.getCharacteristic(WIFI_PASS_UUID)
            }
            // Require basic chars. Provisioning chars might be optional depending on state, but we check all for now if we want robust checking.
            // Let's make provisioning optional so we can connect to fully configured devices too? 
            // For now, assume device always exposes them.
            return commandChar != null && statusChar != null
        }

        override fun initialize() {
            // Request High MTU for long strings (like SSID/Pass)
            requestMtu(512).enqueue()
            
            // Enable notifications
            statusChar?.let { char ->
                scope.launch {
                    setNotificationCallback(char).asFlow().collect {
                        // Handle incoming status JSON
                        val json = String(it.value ?: ByteArray(0))
                        _statusFlow.emit(json)
                    }
                }
                enableNotifications(char).enqueue()
            }
        }

        override fun onServicesInvalidated() {
            commandChar = null
            statusChar = null
            ssidChar = null
            passChar = null
        }
    }

    fun sendCommand(jsonCommand: String) {
        commandChar?.let { char ->
            writeCharacteristic(char, jsonCommand.toByteArray(), BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE)
                .split() // Split automatically if MTU is small
                .enqueue()
        } ?: Log.e("PemfBleManager", "Command characteristic not found!")
    }

    fun provisionWifi(ssid: String, pass: String) {
        if (ssidChar == null || passChar == null) {
            Log.e("PemfBleManager", "Provisioning characteristics not found!")
            return
        }

        // 1. Write SSID
        writeCharacteristic(ssidChar!!, ssid.toByteArray(), BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT)
            .split()
            .enqueue()
            
        // 2. Write Pass (This triggers connection on device side)
        // Add a small delay/queue ensures order
        writeCharacteristic(passChar!!, pass.toByteArray(), BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT)
            .split()
            .enqueue()
            
        Log.d("PemfBleManager", "Provisioning credentials sent.")
    }
}
