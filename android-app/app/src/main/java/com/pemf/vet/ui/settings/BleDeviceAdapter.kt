package com.pemf.vet.ui.settings

import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.ListAdapter
import androidx.recyclerview.widget.RecyclerView
import com.pemf.vet.databinding.ItemEspWifiDeviceBinding

class BleDeviceAdapter(
    private val onDeviceClick: (BleScanResult) -> Unit
) : ListAdapter<BleScanResult, BleDeviceAdapter.ViewHolder>(DiffCallback()) {

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        val binding = ItemEspWifiDeviceBinding.inflate(
            LayoutInflater.from(parent.context),
            parent,
            false
        )
        return ViewHolder(binding)
    }

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        val item = getItem(position)
        holder.bind(item)
    }

    inner class ViewHolder(private val binding: ItemEspWifiDeviceBinding) :
        RecyclerView.ViewHolder(binding.root) {

        fun bind(item: BleScanResult) {
            binding.textDeviceName.text = item.name ?: "Unknown Device"
            binding.textDeviceSSID.text = item.device.address // Mac Adresini gösterelim alt satırda
            binding.textDeviceStatus.text = "${item.rssi} dBm" // RSSI'yi burada göster
            
            // Tıklama olayını tüm kart veya buton üzerinden yönet
            binding.root.setOnClickListener {
                onDeviceClick(item)
            }
            binding.buttonConnect.setOnClickListener {
                onDeviceClick(item)
            }
        }
    }

    class DiffCallback : DiffUtil.ItemCallback<BleScanResult>() {
        override fun areItemsTheSame(oldItem: BleScanResult, newItem: BleScanResult): Boolean {
            return oldItem.device.address == newItem.device.address
        }

        override fun areContentsTheSame(oldItem: BleScanResult, newItem: BleScanResult): Boolean {
            return oldItem == newItem
        }
    }
}
