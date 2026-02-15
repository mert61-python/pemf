package com.pemf.vet.ui.monitor

import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.ListAdapter
import androidx.recyclerview.widget.RecyclerView
import com.pemf.vet.R
import com.pemf.vet.data.models.SensorData
import com.pemf.vet.databinding.ItemSensorDataBinding

class SensorDataAdapter : ListAdapter<SensorData, SensorDataAdapter.ViewHolder>(DiffCallback()) {
    
    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        val binding = ItemSensorDataBinding.inflate(
            LayoutInflater.from(parent.context),
            parent,
            false
        )
        return ViewHolder(binding)
    }
    
    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        holder.bind(getItem(position))
    }
    
    class ViewHolder(private val binding: ItemSensorDataBinding) :
        RecyclerView.ViewHolder(binding.root) {
        
        fun bind(sensorData: SensorData) {
            // Convert ESP_001 to Bobin 1, ESP_002 to Bobin 2, etc.
            val coilNumber = sensorData.espId.replace("ESP_", "").toIntOrNull() ?: 0
            binding.textESPId.text = "Bobin $coilNumber"
            
            if (sensorData.isConnected) {
                binding.textConnectionStatus.text = "Bağlı"
                binding.textConnectionStatus.setTextColor(android.graphics.Color.parseColor("#4CAF50")) // Green
                
                // ✅ Sensör değerlerini göster
                binding.textCurrent.visibility = android.view.View.VISIBLE
                binding.textTemperature.visibility = android.view.View.VISIBLE
                binding.textMagneticField.visibility = android.view.View.VISIBLE
                binding.layoutCurrent.visibility = android.view.View.VISIBLE
                binding.layoutTemperature.visibility = android.view.View.VISIBLE
                binding.layoutMagneticField.visibility = android.view.View.VISIBLE
                
                binding.textCurrent.text = String.format("%.2f A", sensorData.current)
                binding.textTemperature.text = String.format("%.2f °C", sensorData.objectTemperature)
                // Manyetik alan değerini virgülden sonra 2 basamak olarak formatla
                binding.textMagneticField.text = String.format("%.2f mT", sensorData.magneticField)
            } else {
                binding.textConnectionStatus.text = "Bağlı Değil"
                binding.textConnectionStatus.setTextColor(android.graphics.Color.parseColor("#F44336")) // Red
                
                // ✅ Sensör bağlı değilse değerleri gizle
                binding.textCurrent.visibility = android.view.View.GONE
                binding.textTemperature.visibility = android.view.View.GONE
                binding.textMagneticField.visibility = android.view.View.GONE
                binding.layoutCurrent.visibility = android.view.View.GONE
                binding.layoutTemperature.visibility = android.view.View.GONE
                binding.layoutMagneticField.visibility = android.view.View.GONE
            }
        }
    }
    
    class DiffCallback : DiffUtil.ItemCallback<SensorData>() {
        override fun areItemsTheSame(oldItem: SensorData, newItem: SensorData): Boolean {
            return oldItem.espId == newItem.espId
        }
        
        override fun areContentsTheSame(oldItem: SensorData, newItem: SensorData): Boolean {
            return oldItem == newItem
        }
    }
}

