package com.pemf.vet.ui.sessioncontrol

import android.os.Handler
import android.os.Looper
import android.view.LayoutInflater
import android.view.ViewGroup
import android.content.res.ColorStateList
import android.graphics.Color
import androidx.core.content.ContextCompat
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.ListAdapter
import androidx.recyclerview.widget.RecyclerView
import com.pemf.vet.R
import com.pemf.vet.data.models.ESPDevice
import com.pemf.vet.databinding.ItemEspDeviceBinding

class ESPDeviceAdapter(
    private val onStartClick: (String, Int, Double, Int) -> Unit,
    private val onStopClick: (String) -> Unit
) : ListAdapter<ESPDevice, ESPDeviceAdapter.ViewHolder>(DiffCallback()) {
    
    private val viewHolders = mutableSetOf<ViewHolder>()
    
    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        val binding = ItemEspDeviceBinding.inflate(
            LayoutInflater.from(parent.context),
            parent,
            false
        )
        val holder = ViewHolder(binding, onStartClick, onStopClick)
        viewHolders.add(holder)
        return holder
    }
    
    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        holder.bind(getItem(position))
    }
    
    override fun onViewRecycled(holder: ViewHolder) {
        super.onViewRecycled(holder)
        holder.stopCountdownTimer()
        viewHolders.remove(holder)
    }
    
    override fun onDetachedFromRecyclerView(recyclerView: RecyclerView) {
        super.onDetachedFromRecyclerView(recyclerView)
        // Stop all timers when RecyclerView is detached
        viewHolders.forEach { it.stopCountdownTimer() }
        viewHolders.clear()
    }
    
    /**
     * Update slider values for all ESP devices
     * Called when "Apply to All" button is clicked
     */
    fun updateAllSliders(freq: Int, duty: Double, duration: Int) {
        // Update all currently visible ViewHolders
        viewHolders.forEach { holder ->
            holder.updateSliderValues(freq, duty, duration)
        }
    }
    
    // ✅ Optimized payload-based binding - only update changed parts
    override fun onBindViewHolder(holder: ViewHolder, position: Int, payloads: MutableList<Any>) {
        if (payloads.isNotEmpty() && payloads[0] is List<*>) {
            // Partial update - MUCH faster than full bind()
            val changes = payloads[0] as List<*>
            val device = getItem(position)
            
            // IMPORTANT: Update currentDevice reference for button clicks
            holder.updateCurrentDevice(device)
            
            // ✅ Update only changed parts - no slider manipulation
            if (changes.contains("connection")) {
                holder.updateConnectionStatus(device.connected)
            }
            if (changes.contains("pwm_status")) {
                holder.updatePWMStatus(device.pwmStatus, device.connected)
            }
            if (changes.contains("temperature")) {
                holder.updateTemperature(device.sensorData?.objectTemperature)
            }
            if (changes.contains("sensors")) {
                holder.updateSensorData(device.sensorData)
            }
        } else {
            // Full bind - only on first load or major changes
            holder.bind(getItem(position))
        }
    }
    
    class ViewHolder(
        private val binding: ItemEspDeviceBinding,
        private val onStartClick: (String, Int, Double, Int) -> Unit,
        private val onStopClick: (String) -> Unit
    ) : RecyclerView.ViewHolder(binding.root) {
        
        private var currentDevice: ESPDevice? = null
        private var isUpdatingFromServer = false
        private var isInitialized = false // Track if slider values have been initialized
        
        // Countdown timer for PWM remaining time
        private val countdownHandler = Handler(Looper.getMainLooper())
        private var countdownRunnable: Runnable? = null
        private var remainingTimeSeconds: Int? = null
        
        // Store default button state
        private val defaultStartText = binding.buttonStart.text
        private val defaultStartTint = binding.buttonStart.backgroundTintList
        
        init {
            // Initialize slider values only once when ViewHolder is created
            isUpdatingFromServer = true
            binding.seekBarFrequency.progress = 100 // 100 Hz (0-1000 Hz aralığı)
            binding.editTextFrequency.setText("100")
            binding.seekBarDuty.progress = 499 // 50.0%
            binding.editTextDuty.setText("50.0")
            binding.seekBarDuration.progress = 0
            binding.editTextDuration.setText("0")
            isUpdatingFromServer = false
            isInitialized = true
            // Frequency slider (0-1000 Hz)
            binding.seekBarFrequency.setOnSeekBarChangeListener(object : android.widget.SeekBar.OnSeekBarChangeListener {
                override fun onProgressChanged(seekBar: android.widget.SeekBar?, progress: Int, fromUser: Boolean) {
                    if (fromUser && !isUpdatingFromServer) {
                        val freq = progress // 0-1000 Hz
                        binding.editTextFrequency.setText(freq.toString())
                    }
                }
                override fun onStartTrackingTouch(seekBar: android.widget.SeekBar?) {}
                override fun onStopTrackingTouch(seekBar: android.widget.SeekBar?) {}
            })
            
            // Frequency EditText - update slider when value changes
            binding.editTextFrequency.setOnFocusChangeListener { _, hasFocus ->
                if (!hasFocus) {
                    // User finished editing, update slider
                    val text = binding.editTextFrequency.text.toString()
                    val freq = text.toIntOrNull()?.coerceIn(0, 1000) ?: 100
                    isUpdatingFromServer = true
                    binding.seekBarFrequency.progress = freq.coerceIn(0, 1000)
                    binding.editTextFrequency.setText(freq.toString())
                    isUpdatingFromServer = false
                }
            }
            
            // Duty slider (0.1-99.9%)
            binding.seekBarDuty.setOnSeekBarChangeListener(object : android.widget.SeekBar.OnSeekBarChangeListener {
                override fun onProgressChanged(seekBar: android.widget.SeekBar?, progress: Int, fromUser: Boolean) {
                    if (fromUser && !isUpdatingFromServer) {
                        val duty = (progress + 1) / 10.0 // 0.1-99.9%
                        binding.editTextDuty.setText(String.format("%.1f", duty))
                    }
                }
                override fun onStartTrackingTouch(seekBar: android.widget.SeekBar?) {}
                override fun onStopTrackingTouch(seekBar: android.widget.SeekBar?) {}
            })
            
            // Duty EditText - update slider when value changes
            binding.editTextDuty.setOnFocusChangeListener { _, hasFocus ->
                if (!hasFocus) {
                    // User finished editing, update slider
                    val text = binding.editTextDuty.text.toString()
                    val duty = text.toDoubleOrNull()?.coerceIn(0.1, 99.9) ?: 50.0
                    isUpdatingFromServer = true
                    val dutyProgress = ((duty * 10).toInt() - 1).coerceIn(0, 998)
                    binding.seekBarDuty.progress = dutyProgress
                    binding.editTextDuty.setText(String.format("%.1f", duty))
                    isUpdatingFromServer = false
                }
            }
            
            // Duration slider (0-9999 minutes, 0 = unlimited)
            binding.seekBarDuration.setOnSeekBarChangeListener(object : android.widget.SeekBar.OnSeekBarChangeListener {
                override fun onProgressChanged(seekBar: android.widget.SeekBar?, progress: Int, fromUser: Boolean) {
                    if (fromUser && !isUpdatingFromServer) {
                        binding.editTextDuration.setText(progress.toString())
                    }
                }
                override fun onStartTrackingTouch(seekBar: android.widget.SeekBar?) {}
                override fun onStopTrackingTouch(seekBar: android.widget.SeekBar?) {}
            })
            
            // Duration EditText - update slider when value changes
            binding.editTextDuration.setOnFocusChangeListener { _, hasFocus ->
                if (!hasFocus) {
                    // User finished editing, update slider
                    val text = binding.editTextDuration.text.toString()
                    val duration = text.toIntOrNull()?.coerceIn(0, 9999) ?: 0
                    isUpdatingFromServer = true
                    binding.seekBarDuration.progress = duration
                    binding.editTextDuration.setText(duration.toString())
                    isUpdatingFromServer = false
                }
            }
            
            // Start button
            binding.buttonStart.setOnClickListener {
                currentDevice?.let { device ->
                    // Read values from EditText (more accurate than slider)
                    val freqText = binding.editTextFrequency.text.toString()
                    val dutyText = binding.editTextDuty.text.toString()
                    val durationText = binding.editTextDuration.text.toString()
                    
                    val freq = freqText.toIntOrNull()?.coerceIn(0, 1000) ?: binding.seekBarFrequency.progress
                    val duty = dutyText.toDoubleOrNull()?.coerceIn(0.1, 99.9) ?: ((binding.seekBarDuty.progress + 1) / 10.0)
                    val duration = durationText.toIntOrNull()?.coerceIn(0, 9999) ?: binding.seekBarDuration.progress
                    
                    onStartClick(device.id, freq, duty, duration)
                }
            }
            
            // Stop button
            binding.buttonStop.setOnClickListener {
                currentDevice?.let { device ->
                    android.util.Log.d("ESPDeviceAdapter", "Stop button clicked for device: ${device.id}, enabled: ${binding.buttonStop.isEnabled}")
                    onStopClick(device.id)
                } ?: run {
                    android.util.Log.e("ESPDeviceAdapter", "Stop button clicked but currentDevice is null")
                }
            }
        }
        
        fun bind(device: ESPDevice) {
            // Check if this is a different device - if so, reset slider values
            val isDifferentDevice = currentDevice?.id != device.id
            currentDevice = device
            
            // If this is a different device, reset slider values to defaults
            if (isDifferentDevice && isInitialized) {
                isUpdatingFromServer = true
                binding.seekBarFrequency.progress = 100 // 100 Hz (0-1000 Hz aralığı)
                binding.editTextFrequency.setText("100")
                binding.seekBarDuty.progress = 499 // 50.0%
                binding.editTextDuty.setText("50.0")
                binding.seekBarDuration.progress = 0
                binding.editTextDuration.setText("0")
                isUpdatingFromServer = false
            }
            
            // Convert ESP_001 to Bobin 1, ESP_002 to Bobin 2, etc.
            val coilNumber = device.id.replace("ESP_", "").toIntOrNull() ?: 0
            binding.textESPId.text = "Bobin $coilNumber"
            binding.textConnectionStatus.text = if (device.connected) "Bağlı" else "Bağlantısız"
            
            val statusColor = if (device.connected) {
                ContextCompat.getColor(binding.root.context, R.color.status_connected)
            } else {
                ContextCompat.getColor(binding.root.context, R.color.status_disconnected)
            }
            binding.indicatorConnectionStatus.setBackgroundColor(statusColor)
            
            // PWM Status - Her zaman göster
            updatePWMStatus(device.pwmStatus, device.connected)
            
            // Temperature
            device.sensorData?.let { sensor ->
                binding.textObjectTemperature.text = "${sensor.objectTemperature}°C"
                binding.layoutTemperature.visibility = ViewGroup.VISIBLE
            } ?: run {
                binding.layoutTemperature.visibility = ViewGroup.GONE
            }
        }
        
        // Partial update methods - update only specific parts without touching sliders
        fun updateCurrentDevice(device: ESPDevice) {
            currentDevice = device
        }
        
        fun updateConnectionStatus(connected: Boolean) {
            binding.textConnectionStatus.text = if (connected) "Bağlı" else "Bağlantısız"
            val statusColor = if (connected) {
                ContextCompat.getColor(binding.root.context, R.color.status_connected)
            } else {
                ContextCompat.getColor(binding.root.context, R.color.status_disconnected)
            }
            binding.indicatorConnectionStatus.setBackgroundColor(statusColor)
        }
        
        fun updatePWMStatus(pwm: com.pemf.vet.data.models.PWMStatus?, connected: Boolean) {
            if (pwm != null) {
                binding.textPWMStatus.text = if (pwm.active) "Aktif" else "Pasif"
                if (pwm.active && pwm.frequency > 0) {
                    binding.textPWMFrequency.text = "${pwm.frequency} Hz"
                    binding.layoutPWMFrequency.visibility = ViewGroup.VISIBLE
                } else {
                    binding.layoutPWMFrequency.visibility = ViewGroup.GONE
                }
                if (pwm.active && pwm.dutyCycle > 0) {
                    binding.textPWMDutyCycle.text = "${pwm.dutyCycle}%"
                    binding.layoutPWMDutyCycle.visibility = ViewGroup.VISIBLE
                } else {
                    binding.layoutPWMDutyCycle.visibility = ViewGroup.GONE
                }
                
                // Update remaining time display and start/stop countdown timer
                updateRemainingTime(pwm.active, pwm.remainingTime, pwm.duration)
                
                binding.layoutPWMStatus.visibility = ViewGroup.VISIBLE
                
                // ✅ UI Improvement: Show active state on start button
                if (pwm.active) {
                    binding.buttonStart.text = "ÇALIŞIYOR"
                    binding.buttonStart.backgroundTintList = ColorStateList.valueOf(Color.parseColor("#4CAF50")) // Green
                    binding.buttonStart.isEnabled = false // Locked but green
                } else {
                    binding.buttonStart.text = defaultStartText
                    binding.buttonStart.backgroundTintList = defaultStartTint
                    binding.buttonStart.isEnabled = connected
                }
                
                binding.buttonStop.isEnabled = connected // Stop butonu her zaman tıklanabilir (cihaz bağlıyken)
            } else {
                binding.textPWMStatus.text = "Pasif"
                binding.layoutPWMFrequency.visibility = ViewGroup.GONE
                binding.layoutPWMDutyCycle.visibility = ViewGroup.GONE
                stopCountdownTimer()
                binding.layoutPWMRemainingTime.visibility = ViewGroup.GONE
                binding.layoutPWMStatus.visibility = ViewGroup.VISIBLE
                
                // Reset Button
                binding.buttonStart.text = defaultStartText
                binding.buttonStart.backgroundTintList = defaultStartTint
                binding.buttonStart.isEnabled = connected
                
                binding.buttonStop.isEnabled = connected
            }
        }
        
        private fun formatRemainingTime(seconds: Int): String {
            if (seconds <= 0) return ""
            val minutes = seconds / 60
            val secs = seconds % 60
            return "Kalan: $minutes:${String.format("%02d", secs)}"
        }
        
        private fun updateRemainingTime(isActive: Boolean, remainingTime: Int?, duration: Int?) {
            android.util.Log.d("ESPDeviceAdapter", "updateRemainingTime: isActive=$isActive, duration=$duration, remainingTime=$remainingTime")
            
            // Stop timer if PWM is not active or no duration/remaining time
            // IMPORTANT: If duration is 0 or null, clear remaining time even if it's provided
            if (!isActive || duration == null || duration <= 0) {
                android.util.Log.d("ESPDeviceAdapter", "updateRemainingTime: Hiding (isActive=$isActive, duration=$duration)")
                stopCountdownTimer()
                binding.layoutPWMRemainingTime.visibility = ViewGroup.GONE
                remainingTimeSeconds = null
                return
            }
            
            // If duration > 0 but remainingTime is null, also clear (shouldn't happen but be safe)
            if (remainingTime == null || remainingTime <= 0) {
                android.util.Log.d("ESPDeviceAdapter", "updateRemainingTime: Hiding (remainingTime=$remainingTime)")
                stopCountdownTimer()
                binding.layoutPWMRemainingTime.visibility = ViewGroup.GONE
                remainingTimeSeconds = null
                return
            }
            
            // Sync with WebSocket value (drift prevention)
            // If timer is running and new value is significantly different, restart timer
            val currentValue = remainingTimeSeconds
            val significantDiff = currentValue != null && kotlin.math.abs(currentValue - remainingTime) > 2
            remainingTimeSeconds = remainingTime
            
            // Show and update display
            val formatted = formatRemainingTime(remainingTime)
            if (formatted.isNotEmpty()) {
                binding.textPWMRemainingTime.text = formatted
                binding.layoutPWMRemainingTime.visibility = ViewGroup.VISIBLE
                
                // Start countdown timer if not already running, or restart if significant drift
                if (countdownRunnable == null || significantDiff) {
                    if (significantDiff) {
                        stopCountdownTimer()
                    }
                    startCountdownTimer()
                }
            } else {
                stopCountdownTimer()
                binding.layoutPWMRemainingTime.visibility = ViewGroup.GONE
            }
        }
        
        private fun startCountdownTimer() {
            stopCountdownTimer() // Stop any existing timer
            
            countdownRunnable = object : Runnable {
                override fun run() {
                    val current = remainingTimeSeconds
                    if (current != null && current > 0) {
                        // Decrement and update display
                        remainingTimeSeconds = current - 1
                        val formatted = formatRemainingTime(remainingTimeSeconds!!)
                        if (formatted.isNotEmpty()) {
                            binding.root.post {
                                binding.textPWMRemainingTime.text = formatted
                            }
                            // Schedule next update
                            countdownHandler.postDelayed(this, 1000)
                        } else {
                            // Time expired
                            stopCountdownTimer()
                            binding.root.post {
                                binding.layoutPWMRemainingTime.visibility = ViewGroup.GONE
                            }
                        }
                    } else {
                        stopCountdownTimer()
                        binding.root.post {
                            binding.layoutPWMRemainingTime.visibility = ViewGroup.GONE
                        }
                    }
                }
            }
            countdownHandler.postDelayed(countdownRunnable!!, 1000)
        }
        
        fun stopCountdownTimer() {
            countdownRunnable?.let {
                countdownHandler.removeCallbacks(it)
                countdownRunnable = null
            }
        }
        
        fun updateTemperature(temperature: Float?) {
            temperature?.let { temp ->
                binding.textObjectTemperature.text = "${temp}°C"
                binding.layoutTemperature.visibility = ViewGroup.VISIBLE
            } ?: run {
                binding.layoutTemperature.visibility = ViewGroup.GONE
            }
        }
        
        // ✅ Update all sensor data at once
        fun updateSensorData(sensorData: com.pemf.vet.data.models.SensorData?) {
            sensorData?.let { sensor ->
                binding.textObjectTemperature.text = String.format("%.1f°C", sensor.objectTemperature)
                binding.layoutTemperature.visibility = ViewGroup.VISIBLE
                // TODO: Add more sensor displays (current, magnetic field, etc.) if needed
            } ?: run {
                binding.layoutTemperature.visibility = ViewGroup.GONE
            }
        }
        
        /**
         * Update slider values without triggering user input callbacks
         * Called when "Apply to All" button is clicked
         */
        fun updateSliderValues(freq: Int, duty: Double, duration: Int) {
            isUpdatingFromServer = true
            
            // Update frequency slider and text
            val freqClamped = freq.coerceIn(0, 1000)
            binding.seekBarFrequency.progress = freqClamped
            binding.editTextFrequency.setText(freqClamped.toString())
            
            // Update duty slider and text
            val dutyClamped = duty.coerceIn(0.1, 99.9)
            val dutyProgress = ((dutyClamped * 10).toInt() - 1).coerceIn(0, 998)
            binding.seekBarDuty.progress = dutyProgress
            binding.editTextDuty.setText(String.format("%.1f", dutyClamped))
            
            // Update duration slider and text
            val durationClamped = duration.coerceIn(0, 120)
            binding.seekBarDuration.progress = durationClamped
            binding.editTextDuration.setText(durationClamped.toString())
            
            isUpdatingFromServer = false
        }
    }
    
    // ✅ Optimized DiffCallback with granular change detection
    class DiffCallback : DiffUtil.ItemCallback<ESPDevice>() {
        override fun areItemsTheSame(oldItem: ESPDevice, newItem: ESPDevice): Boolean {
            return oldItem.id == newItem.id
        }
        
        override fun areContentsTheSame(oldItem: ESPDevice, newItem: ESPDevice): Boolean {
            // ✅ Comprehensive equality check - only fields that affect UI
            return oldItem.connected == newItem.connected &&
                    oldItem.state == newItem.state &&
                    oldItem.pwmStatus == newItem.pwmStatus &&
                    oldItem.sensorData?.objectTemperature == newItem.sensorData?.objectTemperature &&
                    oldItem.sensorData?.ambientTemperature == newItem.sensorData?.ambientTemperature &&
                    oldItem.sensorData?.current == newItem.sensorData?.current &&
                    oldItem.sensorData?.magneticField == newItem.sensorData?.magneticField
        }
        
        override fun getChangePayload(oldItem: ESPDevice, newItem: ESPDevice): Any? {
            // ✅ Granular payload for partial updates - massive performance boost
            val changes = mutableListOf<String>()
            
            // Connection state change
            if (oldItem.connected != newItem.connected || oldItem.state != newItem.state) {
                changes.add("connection")
            }
            
            // PWM status change (active, frequency, duty, remaining time)
            if (oldItem.pwmStatus != newItem.pwmStatus) {
                changes.add("pwm_status")
            }
            
            // Temperature change
            if (oldItem.sensorData?.objectTemperature != newItem.sensorData?.objectTemperature) {
                changes.add("temperature")
            }
            
            // Sensor data changes (current, magnetic field, etc.)
            if (oldItem.sensorData?.current != newItem.sensorData?.current ||
                oldItem.sensorData?.magneticField != newItem.sensorData?.magneticField ||
                oldItem.sensorData?.ambientTemperature != newItem.sensorData?.ambientTemperature) {
                changes.add("sensors")
            }
            
            return if (changes.isEmpty()) null else changes
        }
    }
}

