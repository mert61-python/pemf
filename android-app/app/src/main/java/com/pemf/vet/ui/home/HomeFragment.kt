package com.pemf.vet.ui.home

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Toast
import androidx.core.content.ContextCompat
import androidx.fragment.app.Fragment
import androidx.fragment.app.viewModels
import androidx.lifecycle.lifecycleScope
import com.pemf.vet.R
import com.pemf.vet.data.models.ConnectionState
import com.pemf.vet.databinding.FragmentHomeBinding
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.launch

@AndroidEntryPoint
class HomeFragment : Fragment() {
    private var _binding: FragmentHomeBinding? = null
    private val binding get() = _binding!!
    
    private val viewModel: HomeViewModel by viewModels()
    
    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        _binding = FragmentHomeBinding.inflate(inflater, container, false)
        return binding.root
    }
    
    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        
        setupObservers()
        setupClickListeners()
    }
    
    private fun setupObservers() {
        viewLifecycleOwner.lifecycleScope.launch {
            viewModel.connectionInfo.collect { connectionInfo ->
                if (_binding != null) {
                    updateConnectionStatus(connectionInfo)
                    updateButtonState(connectionInfo)
                }
            }
        }
    }
    
    private fun setupClickListeners() {
        binding.buttonStartSession.setOnClickListener {
            viewModel.connectToServer()
        }
    }
    
    private fun updateConnectionStatus(connectionInfo: com.pemf.vet.data.models.ConnectionInfo) {
        when (connectionInfo.state) {
            ConnectionState.CONNECTED, ConnectionState.CONNECTED_CLOUD, ConnectionState.CONNECTED_LOCAL -> {
                binding.textConnectionStatus.text = getString(R.string.connected)
                binding.textConnectionStatus.setTextColor(
                    ContextCompat.getColor(requireContext(), R.color.status_connected)
                )
            }
            ConnectionState.CONNECTING -> {
                binding.textConnectionStatus.text = getString(R.string.connecting)
                binding.textConnectionStatus.setTextColor(
                    ContextCompat.getColor(requireContext(), R.color.status_warning)
                )
            }
            ConnectionState.DISCONNECTED -> {
                binding.textConnectionStatus.text = getString(R.string.disconnected)
                binding.textConnectionStatus.setTextColor(
                    ContextCompat.getColor(requireContext(), R.color.text_secondary)
                )
            }
            ConnectionState.ERROR -> {
                binding.textConnectionStatus.text = connectionInfo.errorMessage ?: getString(R.string.error)
                binding.textConnectionStatus.setTextColor(
                    ContextCompat.getColor(requireContext(), R.color.status_disconnected)
                )
            }
        }
    }
    
    private fun updateButtonState(connectionInfo: com.pemf.vet.data.models.ConnectionInfo) {
        when (connectionInfo.state) {
            ConnectionState.CONNECTED, ConnectionState.CONNECTED_CLOUD, ConnectionState.CONNECTED_LOCAL -> {
                binding.buttonStartSession.text = "Bağlı"
                binding.buttonStartSession.isEnabled = false
                binding.buttonStartSession.backgroundTintList = ContextCompat.getColorStateList(
                    requireContext(), R.color.status_connected
                )
            }
            ConnectionState.CONNECTING -> {
                binding.buttonStartSession.text = "Bağlanıyor..."
                binding.buttonStartSession.isEnabled = false
                binding.buttonStartSession.backgroundTintList = ContextCompat.getColorStateList(
                    requireContext(), R.color.status_warning
                )
            }
            ConnectionState.DISCONNECTED -> {
                binding.buttonStartSession.text = getString(R.string.start_session)
                binding.buttonStartSession.isEnabled = true
                binding.buttonStartSession.backgroundTintList = ContextCompat.getColorStateList(
                    requireContext(), R.color.primary_blue
                )
            }
            ConnectionState.ERROR -> {
                binding.buttonStartSession.text = getString(R.string.start_session)
                binding.buttonStartSession.isEnabled = true
                binding.buttonStartSession.backgroundTintList = ContextCompat.getColorStateList(
                    requireContext(), R.color.primary_blue
                )
            }
        }
    }
    
    override fun onDestroyView() {
        super.onDestroyView()
        _binding = null
    }
}

