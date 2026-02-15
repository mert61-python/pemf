package com.pemf.vet.ui.system

import android.content.Context
import android.os.Bundle
import android.view.MenuItem
import android.widget.Toast
import androidx.activity.viewModels
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.google.android.material.textfield.TextInputEditText
import com.pemf.vet.R
import com.pemf.vet.databinding.ActivitySystemSettingsBinding
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.launch

/**
 * System-level settings activity
 * Provides access to advanced configuration options
 */
@AndroidEntryPoint
class SystemSettingsActivity : AppCompatActivity() {

    private lateinit var binding: ActivitySystemSettingsBinding
    private val viewModel: SystemSettingsViewModel by viewModels()

    enum class Target {
        PERMISSIONS,
        WIFI,
        LOCATION,
        MQTT,
        NETWORK
    }

    companion object {
        const val EXTRA_SETTING_TYPE = "setting_type"
        const val EXTRA_TARGET = "target"
        const val TYPE_MQTT_BROKER = "mqtt_broker"
        const val TYPE_DEVICE_NAME = "device_name"
        const val TYPE_NETWORK = "network"
        const val TYPE_ADVANCED = "advanced"
        
        fun launch(context: Context, target: Target) {
            val intent = android.content.Intent(context, SystemSettingsActivity::class.java)
            intent.putExtra(EXTRA_TARGET, target.name)
            context.startActivity(intent)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivitySystemSettingsBinding.inflate(layoutInflater)
        setContentView(binding.root)

        setupActionBar()
        setupClickListeners()
        observeViewModel()

        // Load settings based on intent extra
        val settingType = intent.getStringExtra(EXTRA_SETTING_TYPE)
        val targetStr = intent.getStringExtra(EXTRA_TARGET)
        
        if (targetStr != null) {
            val target = try {
                Target.valueOf(targetStr)
            } catch (e: IllegalArgumentException) {
                null
            }
            when (target) {
                Target.PERMISSIONS -> showPermissionsSettings()
                Target.WIFI -> showWiFiSettings()
                Target.LOCATION -> showLocationSettings()
                Target.MQTT -> showMqttBrokerSettings()
                Target.NETWORK -> showNetworkSettings()
                else -> showAllSettings()
            }
        } else {
            when (settingType) {
                TYPE_MQTT_BROKER -> showMqttBrokerSettings()
                TYPE_DEVICE_NAME -> showDeviceNameSettings()
                TYPE_NETWORK -> showNetworkSettings()
                TYPE_ADVANCED -> showAdvancedSettings()
                else -> showAllSettings()
            }
        }
    }

    private fun setupActionBar() {
        setSupportActionBar(binding.toolbar)
        supportActionBar?.apply {
            setDisplayHomeAsUpEnabled(true)
            title = getString(R.string.system_settings)
        }
    }

    private fun setupClickListeners() {
        binding.apply {
            btnMqttBroker.setOnClickListener { showMqttBrokerDialog() }
            btnMqttPort.setOnClickListener { showMqttPortDialog() }
            btnDeviceName.setOnClickListener { showDeviceNameDialog() }
            btnResetSettings.setOnClickListener { confirmResetSettings() }
            btnExportLogs.setOnClickListener { exportSystemLogs() }
        }
    }

    private fun observeViewModel() {
        lifecycleScope.launch {
            viewModel.systemSettings.collect { settings ->
                binding.apply {
                    tvMqttBrokerValue.text = settings.mqttBroker
                    tvMqttPortValue.text = settings.mqttPort.toString()
                    tvDeviceNameValue.text = settings.deviceName
                }
            }
        }
    }

    private fun showMqttBrokerSettings() {
        // Show only MQTT broker related settings
        showMqttBrokerDialog()
    }
    
    private fun showPermissionsSettings() {
        // Open system settings for permissions
        val intent = android.content.Intent(android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS)
        intent.data = android.net.Uri.parse("package:${packageName}")
        startActivity(intent)
    }
    
    private fun showWiFiSettings() {
        // Open WiFi settings
        val intent = android.content.Intent(android.provider.Settings.ACTION_WIFI_SETTINGS)
        startActivity(intent)
    }
    
    private fun showLocationSettings() {
        // Open location settings
        val intent = android.content.Intent(android.provider.Settings.ACTION_LOCATION_SOURCE_SETTINGS)
        startActivity(intent)
    }

    private fun showDeviceNameSettings() {
        // Show only device name settings
        showDeviceNameDialog()
    }

    private fun showNetworkSettings() {
        // Show network configuration
    }

    private fun showAdvancedSettings() {
        // Show advanced technical settings
    }

    private fun showAllSettings() {
        // Show all system settings
    }

    private fun showMqttBrokerDialog() {
        val input = TextInputEditText(this).apply {
            setText(viewModel.currentBroker)
            hint = getString(R.string.mqtt_broker_hint)
        }

        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.mqtt_broker)
            .setView(input)
            .setPositiveButton(R.string.save) { _, _ ->
                val broker = input.text.toString()
                viewModel.updateMqttBroker(broker)
            }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    private fun showMqttPortDialog() {
        val input = TextInputEditText(this).apply {
            setText(viewModel.currentPort.toString())
            hint = getString(R.string.mqtt_port_hint)
            inputType = android.text.InputType.TYPE_CLASS_NUMBER
        }

        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.mqtt_port)
            .setView(input)
            .setPositiveButton(R.string.save) { _, _ ->
                val port = input.text.toString().toIntOrNull() ?: 1883
                viewModel.updateMqttPort(port)
            }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    private fun showDeviceNameDialog() {
        val input = TextInputEditText(this).apply {
            setText(viewModel.currentDeviceName)
            hint = getString(R.string.device_name_hint)
        }

        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.device_name)
            .setView(input)
            .setPositiveButton(R.string.save) { _, _ ->
                val name = input.text.toString()
                viewModel.updateDeviceName(name)
            }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    private fun confirmResetSettings() {
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.reset_settings)
            .setMessage(R.string.reset_settings_confirmation)
            .setPositiveButton(R.string.reset) { _, _ ->
                viewModel.resetToDefaults()
                Toast.makeText(this, R.string.settings_reset_success, Toast.LENGTH_SHORT).show()
            }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    private fun exportSystemLogs() {
        lifecycleScope.launch {
            try {
                viewModel.exportLogs()
                Toast.makeText(
                    this@SystemSettingsActivity,
                    R.string.logs_exported_success,
                    Toast.LENGTH_SHORT
                ).show()
            } catch (e: Exception) {
                Toast.makeText(
                    this@SystemSettingsActivity,
                    R.string.logs_export_failed,
                    Toast.LENGTH_SHORT
                ).show()
            }
        }
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        if (item.itemId == android.R.id.home) {
            finish()
            return true
        }
        return super.onOptionsItemSelected(item)
    }
}
