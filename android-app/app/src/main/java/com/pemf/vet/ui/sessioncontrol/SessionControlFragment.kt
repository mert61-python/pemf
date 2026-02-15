package com.pemf.vet.ui.sessioncontrol

import android.os.Bundle
import android.os.CountDownTimer
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.fragment.app.Fragment
import androidx.fragment.app.viewModels
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import com.pemf.vet.databinding.FragmentSessionControlBinding
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.launch
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter
import java.time.format.DateTimeParseException

@AndroidEntryPoint
class SessionControlFragment : Fragment() {
    private var _binding: FragmentSessionControlBinding? = null
    private val binding get() = _binding!!
    
    private val viewModel: SessionControlViewModel by viewModels()
    private lateinit var espAdapter: ESPDeviceAdapter
    private lateinit var protocolAdapter: ProtocolAdapter
    
    // Yerel sayaç için timer
    private var countdownTimer: CountDownTimer? = null

    // Animation objects
    private var pulseAnimator: android.animation.ObjectAnimator? = null
    
    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        _binding = FragmentSessionControlBinding.inflate(inflater, container, false)
        return binding.root
    }
    
    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        
        setupRecyclerView()
        setupProtocolRecyclerView() // ✅ New protocols setup
        setupMasterControls()
        setupObservers()
    }
    
    override fun onResume() {
        super.onResume()
        // Arka plandan dönüldüğünde verileri yenile
        viewModel.refreshSessionData()
    }
    
    private fun setupRecyclerView() {
        espAdapter = ESPDeviceAdapter(
            onStartClick = { coilId, freq, duty, duration ->
                viewModel.startCoil(coilId, freq, duty, duration)
            },
            onStopClick = { coilId ->
                viewModel.stopCoil(coilId)
            }
        )
        binding.recyclerViewESPDevices.apply {
            // ✅ 1x8 Liste görünümü - kartlar birbirine girmiyor
            layoutManager = LinearLayoutManager(context)
            adapter = espAdapter
        }
    }

    private fun setupProtocolRecyclerView() {
        protocolAdapter = ProtocolAdapter(viewModel.protocols) { protocol ->
            // Update UI sliders creates a visual feedback of settings applied
            viewModel.setMasterFrequency(protocol.frequency)
            viewModel.setMasterDuty(protocol.dutyCycle)
            viewModel.setMasterDuration(protocol.duration)
            
            // Optional: Show a toast or snackbar
            com.google.android.material.snackbar.Snackbar.make(
                binding.root, 
                "${protocol.name} parametreleri yüklendi. Başlatmak için 'Tümünü Başlat'a basın.", 
                com.google.android.material.snackbar.Snackbar.LENGTH_SHORT
            ).show()
        }
        
        binding.recyclerProtocols.apply {
            layoutManager = LinearLayoutManager(context, LinearLayoutManager.HORIZONTAL, false)
            adapter = protocolAdapter
        }
    }
    
    private fun setupMasterControls() {
        // Master Frequency Slider (0-1000 Hz)
        binding.seekBarMasterFrequency.setOnSeekBarChangeListener(object : android.widget.SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: android.widget.SeekBar?, progress: Int, fromUser: Boolean) {
                if (fromUser) {
                    val freq = progress // 0-1000 Hz
                    binding.textMasterFrequencyValue.text = "$freq Hz"
                    viewModel.setMasterFrequency(freq)
                }
            }
            override fun onStartTrackingTouch(seekBar: android.widget.SeekBar?) {}
            override fun onStopTrackingTouch(seekBar: android.widget.SeekBar?) {}
        })
        
        // Master Duty Slider (0.1-99.9%)
        binding.seekBarMasterDuty.setOnSeekBarChangeListener(object : android.widget.SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: android.widget.SeekBar?, progress: Int, fromUser: Boolean) {
                if (fromUser) {
                    val duty = (progress + 1) / 10.0 // 0.1-99.9%
                    binding.textMasterDutyValue.text = String.format("%.1f%%", duty)
                    viewModel.setMasterDuty(duty)
                }
            }
            override fun onStartTrackingTouch(seekBar: android.widget.SeekBar?) {}
            override fun onStopTrackingTouch(seekBar: android.widget.SeekBar?) {}
        })
        
        // Master Duration Slider (0-9999 minutes, 0 = unlimited)
        binding.seekBarMasterDuration.setOnSeekBarChangeListener(object : android.widget.SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: android.widget.SeekBar?, progress: Int, fromUser: Boolean) {
                if (fromUser) {
                    if (progress == 0) {
                        binding.textMasterDurationValue.text = "Süresiz"
                    } else {
                        binding.textMasterDurationValue.text = "${progress} dk"
                    }
                    viewModel.setMasterDuration(progress)
                }
            }
            override fun onStartTrackingTouch(seekBar: android.widget.SeekBar?) {}
            override fun onStopTrackingTouch(seekBar: android.widget.SeekBar?) {}
        })
        
        // Master Control Buttons
        binding.buttonApplyToAll.setOnClickListener {
            val freq = binding.seekBarMasterFrequency.progress // 0-1000 Hz
            val duty = (binding.seekBarMasterDuty.progress + 1) / 10.0
            val duration = binding.seekBarMasterDuration.progress
            viewModel.applyToAllCoils(freq, duty, duration)
            // Update all ESP device sliders in the RecyclerView
            espAdapter.updateAllSliders(freq, duty, duration)
        }
        
        binding.buttonStartAll.setOnClickListener {
            val freq = binding.seekBarMasterFrequency.progress // 0-1000 Hz
            val duty = (binding.seekBarMasterDuty.progress + 1) / 10.0
            val duration = binding.seekBarMasterDuration.progress
            viewModel.startAllCoils(freq, duty, duration)
        }
        
        binding.buttonStopAll.setOnClickListener {
            viewModel.stopAllCoils()
        }
        
        // Observe master parameters from ViewModel
        viewLifecycleOwner.lifecycleScope.launch {
            viewModel.masterFrequency.collect { freq ->
                binding.seekBarMasterFrequency.progress = freq.coerceIn(0, 1000)
                binding.textMasterFrequencyValue.text = "$freq Hz"
            }
        }
        
        viewLifecycleOwner.lifecycleScope.launch {
            viewModel.masterDuty.collect { duty ->
                val progress = ((duty * 10).toInt() - 1).coerceIn(0, 998)
                binding.seekBarMasterDuty.progress = progress
                binding.textMasterDutyValue.text = String.format("%.1f%%", duty)
            }
        }
        
        viewLifecycleOwner.lifecycleScope.launch {
            viewModel.masterDuration.collect { duration ->
                binding.seekBarMasterDuration.progress = duration.coerceIn(0, 120)
                if (duration == 0) {
                    binding.textMasterDurationValue.text = "Süresiz"
                } else {
                    binding.textMasterDurationValue.text = "${duration} dk"
                }
            }
        }
    }
    
    private fun setupObservers() {
        viewLifecycleOwner.lifecycleScope.launch {
            viewModel.espDevices.collect { devices ->
                espAdapter.submitList(devices)
            }
        }
        
        viewLifecycleOwner.lifecycleScope.launch {
            viewModel.activeSession.collect { session ->
                updateSessionInfo(session)
            }
        }
    }
    
    private fun updateSessionInfo(session: com.pemf.vet.data.models.Session?) {
        if (session != null && session.active) {
            // UI Bilgilerini Doldur (Statik kısımlar)
            binding.textSessionStatus.text = "Aktif"
            binding.textPatientName.text = session.patientName ?: "Bilinmiyor"
            
            // ✅ Tedavi modunu göster (AUTOMATIC, AI, veya Manuel)
            val modeText = when (session.treatmentMode?.uppercase()) {
                "AUTOMATIC" -> "Otomatik Mod"
                "AI" -> "AI Mod"
                "MANUAL", "MANUEL" -> "Manuel Mod"
                else -> session.treatmentMode ?: "Bilinmiyor"
            }
            binding.textTreatmentMode.text = modeText
            
            binding.textFrequency.text = "${session.frequency} Hz"
            binding.textIntensity.text = "${session.intensity} mT"
            binding.textDuration.text = "${session.duration} dakika"
            binding.textTreatmentTarget.text = session.target ?: "-"
            
            // Start time'ı formatla (backward compatibility için)
            if (session.startTimestamp > 0) {
                val startTimeStr = java.time.Instant.ofEpochMilli(session.startTimestamp)
                    .atZone(java.time.ZoneId.systemDefault())
                    .format(DateTimeFormatter.ofPattern("dd/MM/yyyy HH:mm:ss"))
                binding.textStartTime.text = "Tarih:$startTimeStr"
            } else {
                binding.textStartTime.text = formatStartTime(session.startTime)
            }
            
            binding.layoutSessionInfo.visibility = View.VISIBLE
            binding.textNoActiveSession.visibility = View.GONE

            // --- YEREL SAYAÇ BAŞLATMA ---
            if (session.startTimestamp > 0 && session.duration > 0) {
                startLocalTimer(session.startTimestamp, session.duration)
            }
            
            // ✅ Start Pulsing Animation
            startPulsingAnimation()
            
            // ----------------------------
        } else {
            // Seans bitti, sayacı durdur
            stopLocalTimer()
            stopPulsingAnimation()
            
            binding.layoutSessionInfo.visibility = View.GONE
            binding.textNoActiveSession.visibility = View.VISIBLE
        }
    }
    
    // --- Visual Feedback Animation ---
    private fun startPulsingAnimation() {
        binding.imagePulsingIndicator.visibility = View.VISIBLE
        
        if (pulseAnimator == null) {
            pulseAnimator = android.animation.ObjectAnimator.ofPropertyValuesHolder(
                binding.imagePulsingIndicator,
                android.animation.PropertyValuesHolder.ofFloat("scaleX", 1.2f),
                android.animation.PropertyValuesHolder.ofFloat("scaleY", 1.2f),
                android.animation.PropertyValuesHolder.ofFloat("alpha", 0.5f)
            ).apply {
                duration = 800
                repeatCount = android.animation.ObjectAnimator.INFINITE
                repeatMode = android.animation.ObjectAnimator.REVERSE
                interpolator = android.view.animation.AccelerateDecelerateInterpolator()
            }
        }
        
        if (pulseAnimator?.isRunning == false) {
            pulseAnimator?.start()
        }
    }

    private fun stopPulsingAnimation() {
        pulseAnimator?.cancel()
        binding.imagePulsingIndicator.visibility = View.GONE
        binding.imagePulsingIndicator.scaleX = 1f
        binding.imagePulsingIndicator.scaleY = 1f
        binding.imagePulsingIndicator.alpha = 1f
    }
    
    // --- YENİ FONKSİYON: Yerel Sayaç ---
    private fun startLocalTimer(startTimestamp: Long, durationMinutes: Int) {
        // Varsa eski sayacı durdur
        stopLocalTimer()

        val durationMillis = durationMinutes * 60 * 1000L
        val endTime = startTimestamp + durationMillis
        
        // Şu anki zaman ile bitiş zamanı arasındaki farkı hesapla
        // NTP kullandığımız için sistem saatleri senkronize kabul edilir
        val now = System.currentTimeMillis()
        val millisUntilFinished = endTime - now

        if (millisUntilFinished > 0) {
            countdownTimer = object : CountDownTimer(millisUntilFinished, 1000) {
                override fun onTick(millisUntilFinished: Long) {
                    // Kalan süreyi formatla (dk:sn)
                    val minutes = millisUntilFinished / 1000 / 60
                    val seconds = (millisUntilFinished / 1000) % 60
                    
                    // UI güncelle
                    if (_binding != null) {
                        binding.textRemainingTime.text = String.format("%02d:%02d", minutes, seconds)
                    }
                }

                override fun onFinish() {
                    if (_binding != null) {
                        binding.textRemainingTime.text = "00:00"
                    }
                }
            }.start()
        } else {
            binding.textRemainingTime.text = "00:00"
        }
    }

    private fun stopLocalTimer() {
        countdownTimer?.cancel()
        countdownTimer = null
    }
    
    private fun formatStartTime(startTime: String?): String {
        if (startTime == null || startTime.isEmpty()) {
            return "-"
        }
        
        try {
            // Try to parse ISO format (e.g., "2025-11-15T03:52:53.630" or "2025-11-15T03:52:53")
            val dateTime = if (startTime.contains("T")) {
                // ISO format with or without milliseconds
                val formatter = if (startTime.contains(".")) {
                    DateTimeFormatter.ISO_LOCAL_DATE_TIME
                } else {
                    DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss")
                }
                LocalDateTime.parse(startTime, formatter)
            } else {
                // Try other common formats
                LocalDateTime.parse(startTime, DateTimeFormatter.ISO_LOCAL_DATE_TIME)
            }
            
            // Format: "Tarih:gün/ay/yıl Saat:saat:Dakika:Saniye"
            val dateFormatter = DateTimeFormatter.ofPattern("dd/MM/yyyy")
            val timeFormatter = DateTimeFormatter.ofPattern("HH:mm:ss")
            
            return "Tarih:${dateTime.format(dateFormatter)} Saat:${dateTime.format(timeFormatter)}"
        } catch (e: DateTimeParseException) {
            // If parsing fails, return original string
            return startTime
        }
    }
    
    override fun onDestroyView() {
        super.onDestroyView()
        stopLocalTimer() // Fragment kapanırsa sayacı temizle
        _binding = null
    }
}

