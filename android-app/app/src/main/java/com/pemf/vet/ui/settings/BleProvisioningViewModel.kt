package com.pemf.vet.ui.settings

import android.bluetooth.BluetoothDevice
import android.content.Context
import android.os.Handler
import android.os.Looper
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.pemf.vet.connection.PemfBleManager
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import no.nordicsemi.android.support.v18.scanner.BluetoothLeScannerCompat
import no.nordicsemi.android.support.v18.scanner.ScanCallback
import no.nordicsemi.android.support.v18.scanner.ScanResult
import no.nordicsemi.android.support.v18.scanner.ScanSettings
import java.util.UUID
import javax.inject.Inject

data class BleScanResult(
    val device: BluetoothDevice,
    val rssi: Int,
    val name: String? = null
)

@HiltViewModel
class BleProvisioningViewModel @Inject constructor(
    @ApplicationContext private val context: Context
) : ViewModel() {

    private val _scannedDevices = MutableStateFlow<List<BleScanResult>>(emptyList())
    val scannedDevices: StateFlow<List<BleScanResult>> = _scannedDevices.asStateFlow()

    private val _isScanning = MutableStateFlow(false)
    val isScanning: StateFlow<Boolean> = _isScanning.asStateFlow()
    
    // Basit bir manager referansı (ViewModel scope'u içinde yaşayacak)
    // Gerçek uygulamada bu bir Singleton Service (BleService) içinde yönetilmelidir,
    // ancak burada provisioning için geçici bir instance oluşturuyoruz.
    private var bleManager: PemfBleManager? = null

    private val scanner = BluetoothLeScannerCompat.getScanner()
    private val scanSettings = ScanSettings.Builder()
        .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
        .build()
        
    // Bulunan cihazları map'leyip duplikasyonu önlemek için
    private val foundDeviceMap = mutableMapOf<String, BleScanResult>()
    
    // PEMF Service UUID (Filter için)
    private val PEMF_SERVICE_UUID = "4fafc201-1fb5-459e-8fcc-c5c9c331914b"

    private val scanCallback = object : ScanCallback() {
        override fun onScanResult(callbackType: Int, result: ScanResult) {
            val device = result.device
            val name = result.scanRecord?.deviceName ?: device.name ?: "Bilinmeyen Cihaz"
            
            // Sadece PEMF isimlilere odaklanalım veya Service UUID ile filtreleyelim
            // Şimdilik isimde "PEMF" geçenleri alalım
            if (name.contains("PEMF", true)) {
                val scanResult = BleScanResult(device, result.rssi, name)
                foundDeviceMap[device.address] = scanResult
                _scannedDevices.value = foundDeviceMap.values.toList().sortedByDescending { it.rssi }
            }
        }

        override fun onBatchScanResults(results: MutableList<ScanResult>) {
             results.forEach { result ->
                val device = result.device
                val name = result.scanRecord?.deviceName ?: device.name ?: "Bilinmeyen Cihaz"
                 if (name.contains("PEMF", true)) {
                    val scanResult = BleScanResult(device, result.rssi, name)
                    foundDeviceMap[device.address] = scanResult
                }
             }
             _scannedDevices.value = foundDeviceMap.values.toList().sortedByDescending { it.rssi }
        }

        override fun onScanFailed(errorCode: Int) {
            _isScanning.value = false
        }
    }

    fun startScan() {
        if (_isScanning.value) return

        foundDeviceMap.clear()
        _scannedDevices.value = emptyList()
        
        scanner.startScan(null, scanSettings, scanCallback)
        _isScanning.value = true
        
        // 10 saniye sonra durdur
        Handler(Looper.getMainLooper()).postDelayed({
            stopScan()
        }, 10000)
    }

    fun stopScan() {
        if (!_isScanning.value) return
        scanner.stopScan(scanCallback)
        _isScanning.value = false
    }

    fun connectAndProvision(device: BluetoothDevice, ssid: String, pass: String) {
        // Yeni bir manager oluştur (veya mevcutu temizle)
        bleManager?.disconnect()?.enqueue()
        bleManager = PemfBleManager(context)
        
        bleManager?.connect(device)
            ?.retry(3, 100)
            ?.useAutoConnect(false)
            ?.done { 
                // Bağlandı, Provisioning yap
                // Ufak bir gecikme
                Handler(Looper.getMainLooper()).postDelayed({
                     bleManager?.provisionWifi(ssid, pass)
                }, 500)
            }
            ?.enqueue()
    }
    
    override fun onCleared() {
        super.onCleared()
        stopScan()
        bleManager?.disconnect()?.enqueue()
    }
}
