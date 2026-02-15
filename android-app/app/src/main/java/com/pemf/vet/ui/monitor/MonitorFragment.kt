package com.pemf.vet.ui.monitor

import android.graphics.Color
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.fragment.app.Fragment
import androidx.fragment.app.viewModels
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.GridLayoutManager
import com.github.mikephil.charting.components.XAxis
import com.github.mikephil.charting.components.YAxis
import com.github.mikephil.charting.data.Entry
import com.github.mikephil.charting.data.LineData
import com.github.mikephil.charting.data.LineDataSet
import com.github.mikephil.charting.formatter.ValueFormatter
import com.github.mikephil.charting.interfaces.datasets.ILineDataSet
import com.pemf.vet.databinding.FragmentMonitorBinding
import com.pemf.vet.data.models.SensorData
import com.pemf.vet.data.models.UpdateInfo // Import UpdateInfo
import com.google.android.material.dialog.MaterialAlertDialogBuilder // Import Dialog
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.launch

@AndroidEntryPoint
class MonitorFragment : Fragment() {
    private var _binding: FragmentMonitorBinding? = null
    private val binding get() = _binding!!
    
    private val viewModel: MonitorViewModel by viewModels()
    private lateinit var sensorAdapter: SensorDataAdapter
    
    // Chart data storage - her ESP için ayrı entry listesi
    // ArrayDeque kullanıyoruz çünkü removeFirst() O(1) performans sağlar
    private val chartEntries = mutableMapOf<String, ArrayDeque<Entry>>()
    
    // Grafik güncelleme kontrolü - saniyede 1 kere güncelle
    private var lastChartUpdateTime = 0L
    private val CHART_UPDATE_INTERVAL = 1000L // 1 saniye
    private val MAX_CHART_DATA_POINTS = 15 // Son 15 saniye (saniyede 1 veri)
    private var chartTimeCounter = 0f // Zaman ekseni için sayaç
    
    // ESP renkleri (8 ESP için farklı renkler)
    private val espColors = listOf(
        Color.parseColor("#6366f1"), // Indigo
        Color.parseColor("#22c55e"), // Green
        Color.parseColor("#ef4444"), // Red
        Color.parseColor("#f59e0b"), // Orange
        Color.parseColor("#8b5cf6"), // Purple
        Color.parseColor("#06b6d4"), // Cyan
        Color.parseColor("#ec4899"), // Pink
        Color.parseColor("#14b8a6")  // Teal
    )
    
    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        _binding = FragmentMonitorBinding.inflate(inflater, container, false)
        return binding.root
    }
    
    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        
        setupChart()
        setupRecyclerView()
        setupObservers()
    }
    
    override fun onResume() {
        super.onResume()
        // ViewPager2'de fragment geri geldiğinde adapter'ı yeniden güncelle
        if (_binding != null) {
            viewModel.sensorData.value.let { sensorDataMap ->
                if (sensorDataMap.isNotEmpty()) {
                    val sensorDataList = sensorDataMap.values.toList()
                    sensorAdapter.submitList(sensorDataList)
                }
            }
        }
    }
    
    private fun setupChart() {
        binding.chartSensorData.apply {
            description.isEnabled = false
            setTouchEnabled(true)
            setDragEnabled(true)
            setScaleEnabled(true)
            setPinchZoom(true)
            setBackgroundColor(Color.WHITE)
            
            axisLeft.apply {
                textColor = Color.BLACK
                setDrawGridLines(true)
                axisMinimum = 0f
                // Manyetik alan değerlerini virgülden sonra 2 basamak olarak formatla
                valueFormatter = object : ValueFormatter() {
                    override fun getFormattedValue(value: Float): String {
                        return String.format("%.2f", value)
                    }
                }
            }
            
            axisRight.isEnabled = false
            
            xAxis.apply {
                position = XAxis.XAxisPosition.BOTTOM
                textColor = Color.BLACK
                setDrawGridLines(true)
                granularity = 1f // Her saniyede bir işaret
                axisMinimum = 0f
            }
            
            legend.isEnabled = true
            legend.textSize = 12f
        }
    }
    
    private fun setupRecyclerView() {
        if (!::sensorAdapter.isInitialized) {
            sensorAdapter = SensorDataAdapter()
        }
        binding.recyclerViewSensorData.apply {
            if (layoutManager == null) {
                val gridLayoutManager = GridLayoutManager(context, 2) // 2 sütun grid
                gridLayoutManager.orientation = GridLayoutManager.VERTICAL
                layoutManager = gridLayoutManager
            }
            if (adapter == null) {
                adapter = sensorAdapter
            }
            setHasFixedSize(false) // GridLayoutManager için false olmalı (dinamik içerik)
        }
    }
    
    private fun setupObservers() {
        viewLifecycleOwner.lifecycleScope.launch {
            viewModel.sensorData.collect { sensorDataMap ->
                if (_binding != null && view != null) {
                    updateSensorData(sensorDataMap)
                }
            }
        }
        
        viewLifecycleOwner.lifecycleScope.launch {
            viewModel.availableUpdates.collect { updates: Map<String, UpdateInfo> ->
                if (_binding != null && updates.isNotEmpty()) {
                    val entry = updates.entries.first()
                    showUpdateDialog(entry.key, entry.value)
                }
            }
        }
        
        // Listen for system events (Offline Mode Notification)
        viewLifecycleOwner.lifecycleScope.launch {
            viewModel.eventUpdates.collect { event ->
                if (event.eventType == "wifi_disconnected") {
                    context?.let { ctx ->
                        MaterialAlertDialogBuilder(ctx)
                            .setTitle("Bağlantı Uyarısı")
                            .setMessage("WiFi Bağlantısı Koptu!\nSistem otomatik olarak Offline Moda (BLE) geçti.\nKontrole devam edebilirsiniz.")
                            .setPositiveButton("Tamam", null)
                            .show()
                    }
                }
            }
        }
    }
    
    private fun showUpdateDialog(deviceId: String, info: UpdateInfo) {
        // Prevent stacking dialogs (logic simplified for demo)
        context?.let { ctx ->
             MaterialAlertDialogBuilder(ctx)
                .setTitle("Cihaz Güncellemesi Mevcut") // Update Available
                .setMessage("$deviceId için yeni bir yazılım sürümü (${info.version}) bulundu.\n\nYenilikler:\n${info.releaseNotes}") // A new firmware version...
                .setPositiveButton("Şimdi Güncelle") { _, _ -> // Update Now
                    viewModel.triggerUpdate(deviceId)
                }
                .setNegativeButton("Daha Sonra", null) // Later
                .show()
        }
    }

    private fun updateSensorData(sensorDataMap: Map<String, SensorData>) {
        if (_binding == null || view == null) {
            return // Fragment view yoksa güncelleme yapma
        }
        
        // Update RecyclerView - view hazır olduğunda güncelle
        val sensorDataList = sensorDataMap.values.toList()
        binding.recyclerViewSensorData.post {
            if (_binding != null) {
                sensorAdapter.submitList(sensorDataList)
            }
        }
        
        // Update chart
        updateChart(sensorDataMap)
    }
    
    private fun updateChart(sensorDataMap: Map<String, SensorData>) {
        if (_binding == null || view == null) {
            return // Fragment view yoksa güncelleme yapma
        }
        
        if (sensorDataMap.isEmpty()) {
            binding.chartSensorData.data = null
            binding.chartSensorData.invalidate()
            return
        }
        
        // Saniyede 1 kere güncelle
        val currentTime = System.currentTimeMillis()
        if (currentTime - lastChartUpdateTime < CHART_UPDATE_INTERVAL) {
            return // Henüz 1 saniye geçmedi, güncelleme
        }
        lastChartUpdateTime = currentTime
        
        // ✅ Sadece bağlı olan bobillerin verilerini çiz (isConnected = true kontrolü)
        val sortedESPs = sensorDataMap.values
            .filter { it.isConnected }  // ✅ Sadece bağlı ESP'ler
            .sortedBy { it.espId }
        
        // ✅ Bağlı olmayan ESP'lerin chartEntries'den temizle (legend'da gösterilmemesi için)
        val connectedESPIds = sortedESPs.map { it.espId }.toSet()
        val espIdsToRemove = chartEntries.keys.filter { it !in connectedESPIds }
        espIdsToRemove.forEach { chartEntries.remove(it) }
        
        sortedESPs.forEachIndexed { index, sensorData ->
            val espId = sensorData.espId
            
            // Her bobin için entry listesi oluştur
            if (!chartEntries.containsKey(espId)) {
                chartEntries[espId] = ArrayDeque()
            }
            
            val entries = chartEntries[espId] ?: ArrayDeque()
            
            // Zaman ekseni için sayaç kullan (sonsuza kadar devam eder)
            // Manyetik alan değerini ekle
            entries.addLast(Entry(chartTimeCounter, sensorData.magneticField))
            
            // Son 15 saniyenin verisini tut (MAX_CHART_DATA_POINTS = 15)
            if (entries.size > MAX_CHART_DATA_POINTS) {
                entries.removeFirst()
            }
            
            chartEntries[espId] = entries
        }
        
        // Zaman sayacını artır (her güncellemede 1 saniye)
        chartTimeCounter += 1f
        
        // Sadece bağlı olan bobiller için LineDataSet oluştur (legend'da sadece bunlar gösterilecek)
        val dataSets: MutableList<ILineDataSet> = mutableListOf()
        
        sortedESPs.forEachIndexed { index, sensorData ->
            val espId = sensorData.espId
            val entries = chartEntries[espId] ?: return@forEachIndexed
            
            if (entries.isNotEmpty()) {
                // ESP ID'yi "Bobin X" formatına çevir
                val coilNumber = espId.replace("ESP_", "").toIntOrNull() ?: 0
                val displayName = "Bobin $coilNumber"
                
                // Renk ataması - coil numarasına göre sabit renk (1-8 arası)
                val colorIndex = (coilNumber - 1).coerceIn(0, espColors.size - 1)
                val color = espColors[colorIndex]
                
                val dataSet = LineDataSet(entries, displayName).apply {
                    this.color = color
                    valueTextColor = Color.BLACK
                    lineWidth = 2f
                    setCircleColor(color)
                    circleRadius = 3f
                    setDrawCircleHole(false)
                    mode = LineDataSet.Mode.CUBIC_BEZIER
                    setDrawValues(false) // Değerleri gösterme (performans için)
                }
                dataSets.add(dataSet)
            }
        }
        
        // Grafiği güncelle
        if (dataSets.isNotEmpty()) {
            val lineData = LineData(dataSets)
            binding.chartSensorData.data = lineData
            
            // X eksenini görünür aralığa göre ayarla (son 15 saniye)
            val minX = (chartTimeCounter - MAX_CHART_DATA_POINTS).coerceAtLeast(0f)
            val maxX = chartTimeCounter
            binding.chartSensorData.xAxis.axisMinimum = minX
            binding.chartSensorData.xAxis.axisMaximum = maxX
            
            binding.chartSensorData.invalidate()
        }
    }
    
    override fun onDestroyView() {
        super.onDestroyView()
        _binding = null
    }
}

