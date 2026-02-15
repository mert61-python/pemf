package com.pemf.vet.ui.sessioncontrol

import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.recyclerview.widget.RecyclerView
import com.pemf.vet.data.models.TreatmentProtocol
import com.pemf.vet.databinding.ItemProtocolBinding

class ProtocolAdapter(
    private val protocols: List<TreatmentProtocol>,
    private val onProtocolClick: (TreatmentProtocol) -> Unit
) : RecyclerView.Adapter<ProtocolAdapter.ViewHolder>() {

    class ViewHolder(val binding: ItemProtocolBinding) : RecyclerView.ViewHolder(binding.root)

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        val binding = ItemProtocolBinding.inflate(
            LayoutInflater.from(parent.context),
            parent,
            false
        )
        return ViewHolder(binding)
    }

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        val protocol = protocols[position]
        holder.binding.apply {
            textProtocolName.text = protocol.name
            textProtocolDesc.text = protocol.description
            textProtocolDetails.text = "${protocol.frequency}Hz • ${protocol.dutyCycle.toInt()}% • ${protocol.duration}dk"
            
            cardProtocol.setOnClickListener {
                onProtocolClick(protocol)
            }
        }
    }

    override fun getItemCount() = protocols.size
}
