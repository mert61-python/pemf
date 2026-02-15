package com.pemf.vet.ui.settings

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.util.Log
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import android.widget.Toast
import android.provider.Settings
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.core.content.ContextCompat
import androidx.fragment.app.Fragment
import androidx.fragment.app.viewModels
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.repeatOnLifecycle
import androidx.recyclerview.widget.LinearLayoutManager
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.google.android.material.textfield.TextInputEditText
import com.pemf.vet.R
import com.pemf.vet.data.api.MqttService
import com.pemf.vet.data.models.ConnectionState
import com.pemf.vet.databinding.FragmentSettingsBinding
import com.pemf.vet.ui.system.SystemSettingsActivity
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.launch
import javax.inject.Inject

@AndroidEntryPoint
class SettingsFragment : Fragment() {
    private var _binding: FragmentSettingsBinding? = null
    private val binding get() = _binding!!
    
    private val bleViewModel: BleProvisioningViewModel by viewModels()
    private lateinit var bleDeviceAdapter: BleDeviceAdapter
    
    @Inject
    lateinit var mqttService: MqttService
    
    private val TAG = "SettingsFragment"
    
    // İzin verildikten sonra çalıştırılacak işlem
    private var pendingPermissionCallback: (() -> Unit)? = null
    
    // Progress dialog
    private var progressDialog: AlertDialog? = null
    private var progressTextView: TextView? = null
    private var progressStepView: TextView? = null
    private var progressDescriptionView: TextView? = null
    
    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        _binding = FragmentSettingsBinding.inflate(inflater, container, false)
        return binding.root
    }
    
    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        
        setupAppInfo()
        setupRecyclerView()
        setupObservers()
        setupClickListeners()
    }
    
    
    private fun setupAppInfo() {
        try {
            val packageInfo = requireContext().packageManager.getPackageInfo(requireContext().packageName, 0)
            
            // App Version
            binding.textAppVersion.text = packageInfo.versionName ?: "1.0.0"
            
            // Build Number
            @Suppress("DEPRECATION")
            binding.textBuildNumber.text = packageInfo.versionCode.toString()
            
            // Android Version
            binding.textAndroidVersion.text = "Android ${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT})"
            
            // MQTT Status
            viewLifecycleOwner.lifecycleScope.launch {
                viewLifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) {
                    mqttService.connectionState.collect { state ->
                        when (state) {
                            ConnectionState.CONNECTED, ConnectionState.CONNECTED_CLOUD, ConnectionState.CONNECTED_LOCAL -> {
                                binding.textMqttStatus.text = "Bağlı"
                                binding.textMqttStatus.setTextColor(
                                    ContextCompat.getColor(requireContext(), R.color.status_connected)
                                )
                            }
                            ConnectionState.CONNECTING -> {
                                binding.textMqttStatus.text = "Bağlanıyor..."
                                binding.textMqttStatus.setTextColor(
                                    ContextCompat.getColor(requireContext(), R.color.text_secondary)
                                )
                            }
                            ConnectionState.DISCONNECTED -> {
                                binding.textMqttStatus.text = "Bağlı Değil"
                                binding.textMqttStatus.setTextColor(
                                    ContextCompat.getColor(requireContext(), R.color.status_disconnected)
                                )
                            }
                            ConnectionState.ERROR -> {
                                binding.textMqttStatus.text = "Hata"
                                binding.textMqttStatus.setTextColor(
                                    ContextCompat.getColor(requireContext(), R.color.status_disconnected)
                                )
                            }
                        }
                    }
                }
            }
        } catch (e: PackageManager.NameNotFoundException) {
            binding.textAppVersion.text = "1.0.0"
            binding.textBuildNumber.text = "1"
        }
    }
    
    private fun setupRecyclerView() {
        bleDeviceAdapter = BleDeviceAdapter { scanResult ->
            showWiFiProvisioningDialog(scanResult)
        }
        
        binding.recyclerViewESPDevices.apply {
            layoutManager = LinearLayoutManager(requireContext())
            adapter = bleDeviceAdapter
        }
    }
    
    private fun setupObservers() {
        viewLifecycleOwner.lifecycleScope.launch {
            viewLifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) {
                // BLE Scan Durumu
                launch {
                    bleViewModel.isScanning.collect { isScanning ->
                        binding.buttonScanESP.isEnabled = !isScanning
                        binding.buttonScanESP.text = if (isScanning) "PEMF Cihazları Aranıyor..." else "BLE ile PEMF Cihazı Ara"
                        if (isScanning) {
                            binding.layoutEmptyState.visibility = View.GONE
                            // binding.progressBarScan.visibility = View.VISIBLE
                        } else {
                            // binding.progressBarScan.visibility = View.GONE
                        }
                    }
                }

                // Bulunan Cihazlar
                launch {
                    bleViewModel.scannedDevices.collect { devices ->
                        bleDeviceAdapter.submitList(devices)
                        binding.layoutEmptyState.visibility = if (devices.isEmpty() && !bleViewModel.isScanning.value) {
                            View.VISIBLE
                        } else {
                            View.GONE
                        }
                    }
                }
            }
        }
    }
    
    private fun setupClickListeners() {
        binding.buttonScanESP.setOnClickListener {
            // BLE Taramasını başlat
            if (checkAllPermissions()) {
                checkBluetoothAndScan()
            } else {
                requestAllPermissions()
            }
        }
    }

    private fun showWiFiProvisioningDialog(scanResult: BleScanResult) {
        val dialogView = layoutInflater.inflate(R.layout.dialog_wifi_simplified, null)
        val editTextSSID = dialogView.findViewById<TextInputEditText>(R.id.editTextSSID)
        val editTextPassword = dialogView.findViewById<TextInputEditText>(R.id.editTextPassword)
        val textHelp = dialogView.findViewById<TextView>(R.id.textHelp)
        
        textHelp?.text = "⚡ ${scanResult.name} cihazına bağlanılıyor.\n\n" +
            "Cihazın bağlanacağı WiFi ağının adını ve şifresini girin."
        
        MaterialAlertDialogBuilder(requireContext())
            .setTitle("WiFi Kurulumu (BLE)")
            .setView(dialogView)
            .setPositiveButton("Ayarları Gönder") { _, _ ->
                val ssid = editTextSSID.text?.toString()?.trim() ?: ""
                val password = editTextPassword.text?.toString()?.trim() ?: ""
                
                if (ssid.isEmpty()) {
                    Toast.makeText(requireContext(), "WiFi adı gerekli", Toast.LENGTH_SHORT).show()
                    return@setPositiveButton
                }
                
                Toast.makeText(requireContext(), "Bilgiler gönderiliyor...", Toast.LENGTH_SHORT).show()
                bleViewModel.connectAndProvision(scanResult.device, ssid, password)
            }
            .setNegativeButton("İptal", null)
            .show()
    }
    
    /**
     * Tüm gerekli izinleri kontrol et
     */
    private fun checkAllPermissions(): Boolean {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            // Android 12+ için BLUETOOTH_SCAN ve BLUETOOTH_CONNECT
            val hasScan = ContextCompat.checkSelfPermission(
                requireContext(),
                Manifest.permission.BLUETOOTH_SCAN
            ) == PackageManager.PERMISSION_GRANTED
            
            val hasConnect = ContextCompat.checkSelfPermission(
                requireContext(),
                Manifest.permission.BLUETOOTH_CONNECT
            ) == PackageManager.PERMISSION_GRANTED
            
            hasScan && hasConnect
        } else {
            // Android 11 ve altı için ACCESS_FINE_LOCATION
            ContextCompat.checkSelfPermission(
                requireContext(),
                Manifest.permission.ACCESS_FINE_LOCATION
            ) == PackageManager.PERMISSION_GRANTED
        }
    }
    
    /**
     * Tüm gerekli izinleri tek seferde iste
     */
    private fun requestAllPermissions() {
        val permissionsToRequest = mutableListOf<String>()
        
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            // Android 12+
            if (ContextCompat.checkSelfPermission(requireContext(), 
                Manifest.permission.BLUETOOTH_SCAN) != PackageManager.PERMISSION_GRANTED) {
                permissionsToRequest.add(Manifest.permission.BLUETOOTH_SCAN)
            }
            if (ContextCompat.checkSelfPermission(requireContext(), 
                Manifest.permission.BLUETOOTH_CONNECT) != PackageManager.PERMISSION_GRANTED) {
                permissionsToRequest.add(Manifest.permission.BLUETOOTH_CONNECT)
            }
        } else {
            // Android 11 ve altı
            if (ContextCompat.checkSelfPermission(requireContext(), 
                Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
                permissionsToRequest.add(Manifest.permission.ACCESS_FINE_LOCATION)
            }
        }
        
        if (permissionsToRequest.isEmpty()) {
            // Tüm izinler zaten verilmiş
            pendingPermissionCallback?.invoke()
            pendingPermissionCallback = null
            // updatePermissionCardVisibility() // Removed from view
            return
        }
        
        // Açıklama göster ve izinleri iste
        showPermissionRationaleAndRequest(permissionsToRequest.toTypedArray())
    }
    
    /**
     * İzin açıklamasını göster ve izinleri iste
     */
    private fun showPermissionRationaleAndRequest(permissions: Array<String>) {
        MaterialAlertDialogBuilder(requireContext())
            .setTitle("Bluetooth İzinleri Gerekli")
            .setMessage(
                "PEMF cihazlarını bulup ayarlamak için Bluetooth tarama ve bağlantı izinlerine ihtiyacımız var.\n\n" +
                "Android 11 ve altı cihazlarda Bluetooth taraması için Konum izni de gereklidir."
            )
            .setPositiveButton("İzin Ver") { _, _ ->
                allPermissionsLauncher.launch(permissions)
            }
            .setNegativeButton("İptal") { _, _ ->
                Toast.makeText(
                    requireContext(),
                    "İzin olmadan işlem yapılamaz",
                    Toast.LENGTH_LONG
                ).show()
            }
            .show()
    }
    
    /**
     * Tüm izinler için launcher
     */
    private val allPermissionsLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions ->
        val allGranted = permissions.values.all { it }
        
        if (allGranted) {
            Toast.makeText(requireContext(), "✅ İzinler verildi", Toast.LENGTH_SHORT).show()
            pendingPermissionCallback?.invoke()
            pendingPermissionCallback = null
            
            // Hemen taramayı başlatabiliriz
            checkBluetoothAndScan()
        } else {
            showPermissionDeniedHelp()
        }
    }

    private val enableBluetoothLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == android.app.Activity.RESULT_OK) {
            bleViewModel.startScan()
        } else {
            Toast.makeText(requireContext(), "Bluetooth açılmadı, tarama yapılamıyor", Toast.LENGTH_SHORT).show()
        }
    }
    
    // REDUNDANT FUNCTION REMOVED (setupClickListeners is already defined above)

    private fun checkBluetoothAndScan() {
        val bluetoothManager = requireContext().getSystemService(android.content.Context.BLUETOOTH_SERVICE) as? android.bluetooth.BluetoothManager
        val adapter = bluetoothManager?.adapter
        
        if (adapter != null && !adapter.isEnabled) {
            // Bluetooth kapalı, açılmasını iste
            val intent = Intent(android.bluetooth.BluetoothAdapter.ACTION_REQUEST_ENABLE)
            enableBluetoothLauncher.launch(intent)
        } else {
            // Bluetooth açık veya adapter yok, taramayı dene
            bleViewModel.startScan()
        }
    }
    private fun showPermissionDeniedHelp() {
        MaterialAlertDialogBuilder(requireContext())
            .setTitle("İzin Gerekli")
            .setMessage(
                "Gerekli izinler verilmediği için cihaz taraması yapılamıyor.\n\n" +
                "Lütfen Ayarlar'dan Bluetooth ve Konum (eski cihazlar için) izinlerini kontrol edin."
            )
            .setPositiveButton("Ayarlara Git") { _, _ ->
                openAppSettings()
            }
            .setNegativeButton("Tamam", null)
            .show()
    }
    private fun openAppSettings() {
        try {
            val intent = Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                data = Uri.fromParts("package", requireContext().packageName, null)
            }
            startActivity(intent)
        } catch (e: Exception) {
            Toast.makeText(requireContext(), "Ayarlar açılamadı", Toast.LENGTH_SHORT).show()
        }
    }

    private fun openSystemSettingsAssistant(target: SystemSettingsActivity.Target) {
        SystemSettingsActivity.launch(requireContext(), target)
    }
    
    override fun onDestroyView() {
        super.onDestroyView()
        _binding = null
    }
}
