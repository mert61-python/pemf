"""
ECG Variational Autoencoder (VAE)
==================================

Learns compressed representation of ECG signals to:
1. Establish baseline ECG patterns for each animal
2. Extract meaningful features for treatment prediction
3. Detect anomalies by reconstruction error
4. Generate synthetic ECG variations

Architecture:
------------
Input: ECG signal (2500 samples @ 250 Hz = 10 seconds)
Encoder: 1D CNN → Latent space (32 dimensions)
Decoder: 1D Transposed CNN → Reconstructed ECG

The latent space captures species-specific cardiac patterns and individual
variations, which can be used for treatment personalization.

Usage:
------
    model = ECGAutoencoder(input_length=2500, latent_dim=32)
    
    # Training
    reconstructed, mu, logvar = model(ecg_batch)
    loss = model.loss_function(reconstructed, ecg_batch, mu, logvar)
    
    # Feature extraction
    features = model.encode(ecg_signal)
    
    # Anomaly detection
    reconstruction_error = model.reconstruction_error(ecg_signal)
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from typing import Tuple, Optional, Dict
from pathlib import Path

import sys
sys.path.append(str(Path(__file__).parent.parent))
from ai.config import MODELS, DEVICE, TRAINING


class ECGEncoder(nn.Module):
    """
    1D Convolutional Encoder for ECG signals.
    
    Progressively downsamples the ECG signal while extracting
    hierarchical features.
    """
    
    def __init__(self, input_length: int = 2500, latent_dim: int = 32):
        super(ECGEncoder, self).__init__()
        
        config = MODELS['ecg_autoencoder']
        hidden_layers = config['hidden_layers']
        dropout = config['dropout']
        
        # 1D Convolutional layers with batch norm and dropout
        self.conv1 = nn.Conv1d(1, hidden_layers[0], kernel_size=15, stride=2, padding=7)
        self.bn1 = nn.BatchNorm1d(hidden_layers[0])
        self.dropout1 = nn.Dropout(dropout)
        
        self.conv2 = nn.Conv1d(hidden_layers[0], hidden_layers[1], kernel_size=11, stride=2, padding=5)
        self.bn2 = nn.BatchNorm1d(hidden_layers[1])
        self.dropout2 = nn.Dropout(dropout)
        
        self.conv3 = nn.Conv1d(hidden_layers[1], hidden_layers[2], kernel_size=7, stride=2, padding=3)
        self.bn3 = nn.BatchNorm1d(hidden_layers[2])
        self.dropout3 = nn.Dropout(dropout)
        
        self.conv4 = nn.Conv1d(hidden_layers[2], hidden_layers[3], kernel_size=5, stride=2, padding=2)
        self.bn4 = nn.BatchNorm1d(hidden_layers[3])
        self.dropout4 = nn.Dropout(dropout)
        
        # Calculate flattened size after convolutions
        self.flattened_size = self._get_flattened_size(input_length, hidden_layers)
        
        # Latent space projections (for VAE)
        self.fc_mu = nn.Linear(self.flattened_size, latent_dim)
        self.fc_logvar = nn.Linear(self.flattened_size, latent_dim)
    
    def _get_flattened_size(self, input_length: int, hidden_layers: list) -> int:
        """Calculate output size after convolutional layers."""
        size = input_length
        # 4 conv layers with stride 2
        for _ in range(4):
            size = (size + 2 * 0 - 1) // 2 + 1  # Formula for conv output size
        return size * hidden_layers[-1]
    
    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Forward pass through encoder.
        
        Args:
            x: Input ECG (batch_size, 1, signal_length)
            
        Returns:
            Tuple of (mu, logvar) for latent distribution
        """
        # Convolutional layers with ReLU activation
        x = F.relu(self.bn1(self.conv1(x)))
        x = self.dropout1(x)
        
        x = F.relu(self.bn2(self.conv2(x)))
        x = self.dropout2(x)
        
        x = F.relu(self.bn3(self.conv3(x)))
        x = self.dropout3(x)
        
        x = F.relu(self.bn4(self.conv4(x)))
        x = self.dropout4(x)
        
        # Flatten
        x = x.view(x.size(0), -1)
        
        # Project to latent space
        mu = self.fc_mu(x)
        logvar = self.fc_logvar(x)
        
        return mu, logvar


class ECGDecoder(nn.Module):
    """
    1D Transposed Convolutional Decoder for ECG signals.
    
    Reconstructs ECG signal from latent representation.
    """
    
    def __init__(self, latent_dim: int = 32, output_length: int = 2500):
        super(ECGDecoder, self).__init__()
        
        config = MODELS['ecg_autoencoder']
        hidden_layers = config['hidden_layers'][::-1]  # Reverse for decoder
        dropout = config['dropout']
        
        # Calculate initial size for decoder
        self.initial_size = output_length // (2 ** 4)  # 4 upsample layers
        
        # Project latent to decoder input
        self.fc = nn.Linear(latent_dim, self.initial_size * hidden_layers[0])
        
        # Transposed convolutions for upsampling
        self.deconv1 = nn.ConvTranspose1d(hidden_layers[0], hidden_layers[1], 
                                         kernel_size=5, stride=2, padding=2, output_padding=1)
        self.bn1 = nn.BatchNorm1d(hidden_layers[1])
        self.dropout1 = nn.Dropout(dropout)
        
        self.deconv2 = nn.ConvTranspose1d(hidden_layers[1], hidden_layers[2], 
                                         kernel_size=7, stride=2, padding=3, output_padding=1)
        self.bn2 = nn.BatchNorm1d(hidden_layers[2])
        self.dropout2 = nn.Dropout(dropout)
        
        self.deconv3 = nn.ConvTranspose1d(hidden_layers[2], hidden_layers[3], 
                                         kernel_size=11, stride=2, padding=5, output_padding=1)
        self.bn3 = nn.BatchNorm1d(hidden_layers[3])
        self.dropout3 = nn.Dropout(dropout)
        
        self.deconv4 = nn.ConvTranspose1d(hidden_layers[3], 1, 
                                         kernel_size=15, stride=2, padding=7, output_padding=1)
    
    def forward(self, z: torch.Tensor) -> torch.Tensor:
        """
        Forward pass through decoder.
        
        Args:
            z: Latent vector (batch_size, latent_dim)
            
        Returns:
            Reconstructed ECG (batch_size, 1, signal_length)
        """
        # Project and reshape
        x = F.relu(self.fc(z))
        x = x.view(x.size(0), -1, self.initial_size)
        
        # Transposed convolutions with ReLU
        x = F.relu(self.bn1(self.deconv1(x)))
        x = self.dropout1(x)
        
        x = F.relu(self.bn2(self.deconv2(x)))
        x = self.dropout2(x)
        
        x = F.relu(self.bn3(self.deconv3(x)))
        x = self.dropout3(x)
        
        # Final layer with tanh activation (output in [-1, 1])
        x = torch.tanh(self.deconv4(x))
        
        return x


class ECGAutoencoder(nn.Module):
    """
    Variational Autoencoder for ECG signals.
    
    Combines encoder and decoder with VAE reparameterization trick.
    """
    
    def __init__(self, input_length: int = 2500, latent_dim: int = 32):
        super(ECGAutoencoder, self).__init__()
        
        self.input_length = input_length
        self.latent_dim = latent_dim
        
        self.encoder = ECGEncoder(input_length, latent_dim)
        self.decoder = ECGDecoder(latent_dim, input_length)
    
    def reparameterize(self, mu: torch.Tensor, logvar: torch.Tensor) -> torch.Tensor:
        """
        Reparameterization trick for VAE.
        
        z = mu + epsilon * sigma, where epsilon ~ N(0,1)
        """
        std = torch.exp(0.5 * logvar)
        eps = torch.randn_like(std)
        return mu + eps * std
    
    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Forward pass through full autoencoder.
        
        Args:
            x: Input ECG (batch_size, 1, signal_length)
            
        Returns:
            Tuple of (reconstructed, mu, logvar)
        """
        # Encode
        mu, logvar = self.encoder(x)
        
        # Reparameterize
        z = self.reparameterize(mu, logvar)
        
        # Decode
        reconstructed = self.decoder(z)
        
        return reconstructed, mu, logvar
    
    def encode(self, x: torch.Tensor, return_distribution: bool = False):
        """
        Encode ECG to latent representation.
        
        Args:
            x: Input ECG
            return_distribution: If True, returns (mu, logvar), else returns z
            
        Returns:
            Latent representation or distribution parameters
        """
        mu, logvar = self.encoder(x)
        
        if return_distribution:
            return mu, logvar
        else:
            return self.reparameterize(mu, logvar)
    
    def decode(self, z: torch.Tensor) -> torch.Tensor:
        """
        Decode latent representation to ECG.
        
        Args:
            z: Latent vector
            
        Returns:
            Reconstructed ECG
        """
        return self.decoder(z)
    
    def loss_function(self, 
                     reconstructed: torch.Tensor, 
                     original: torch.Tensor,
                     mu: torch.Tensor, 
                     logvar: torch.Tensor,
                     kl_weight: float = 1.0) -> Dict[str, torch.Tensor]:
        """
        VAE loss function: Reconstruction loss + KL divergence.
        
        Args:
            reconstructed: Output from decoder
            original: Original input
            mu: Mean of latent distribution
            logvar: Log variance of latent distribution
            kl_weight: Weight for KL term (beta-VAE)
            
        Returns:
            Dictionary with total loss and components
        """
        # Pad reconstructed if size mismatch
        if reconstructed.shape[-1] != original.shape[-1]:
            diff = original.shape[-1] - reconstructed.shape[-1]
            reconstructed = F.pad(reconstructed, (0, diff), mode='replicate')
        
        # Reconstruction loss (MSE)
        recon_loss = F.mse_loss(reconstructed, original, reduction='sum') / original.size(0)
        
        # KL divergence loss
        # KL(N(mu, sigma) || N(0, 1)) = -0.5 * sum(1 + log(sigma^2) - mu^2 - sigma^2)
        kl_loss = -0.5 * torch.sum(1 + logvar - mu.pow(2) - logvar.exp()) / original.size(0)
        
        # Total loss
        total_loss = recon_loss + kl_weight * kl_loss
        
        return {
            'loss': total_loss,
            'reconstruction_loss': recon_loss,
            'kl_loss': kl_loss
        }
    
    def reconstruction_error(self, x: torch.Tensor) -> torch.Tensor:
        """
        Calculate reconstruction error for anomaly detection.
        
        High reconstruction error indicates the signal is different from
        learned patterns (potential anomaly).
        
        Args:
            x: Input ECG
            
        Returns:
            Reconstruction error per sample
        """
        with torch.no_grad():
            reconstructed, _, _ = self.forward(x)
            
            # Pad reconstructed if size mismatch
            if reconstructed.shape[-1] != x.shape[-1]:
                diff = x.shape[-1] - reconstructed.shape[-1]
                reconstructed = F.pad(reconstructed, (0, diff), mode='replicate')
            
            error = F.mse_loss(reconstructed, x, reduction='none')
            error = error.view(error.size(0), -1).mean(dim=1)
        
        return error
    
    def generate(self, n_samples: int = 1, device: str = 'cpu') -> torch.Tensor:
        """
        Generate new ECG samples by sampling from latent space.
        
        Args:
            n_samples: Number of samples to generate
            device: Device to generate on
            
        Returns:
            Generated ECG signals
        """
        with torch.no_grad():
            # Sample from standard normal
            z = torch.randn(n_samples, self.latent_dim).to(device)
            
            # Decode
            generated = self.decoder(z)
        
        return generated
    
    def interpolate(self, ecg1: torch.Tensor, ecg2: torch.Tensor, 
                   n_steps: int = 10) -> torch.Tensor:
        """
        Interpolate between two ECG signals in latent space.
        
        Useful for understanding latent space structure and generating
        variations between two patterns.
        
        Args:
            ecg1: First ECG signal
            ecg2: Second ECG signal
            n_steps: Number of interpolation steps
            
        Returns:
            Interpolated ECG signals
        """
        with torch.no_grad():
            # Encode both signals
            z1 = self.encode(ecg1)
            z2 = self.encode(ecg2)
            
            # Interpolate in latent space
            alphas = torch.linspace(0, 1, n_steps).to(ecg1.device)
            interpolated_z = []
            
            for alpha in alphas:
                z_interp = (1 - alpha) * z1 + alpha * z2
                interpolated_z.append(z_interp)
            
            interpolated_z = torch.cat(interpolated_z, dim=0)
            
            # Decode interpolated latent vectors
            interpolated_ecg = self.decoder(interpolated_z)
        
        return interpolated_ecg
    
    def get_latent_statistics(self, dataloader) -> Dict[str, torch.Tensor]:
        """
        Calculate mean and std of latent space from dataset.
        
        Useful for understanding the learned representation.
        
        Args:
            dataloader: DataLoader with ECG samples
            
        Returns:
            Dictionary with mean and std of latent space
        """
        latent_vectors = []
        
        with torch.no_grad():
            for batch in dataloader:
                if isinstance(batch, (tuple, list)):
                    batch = batch[0]
                
                mu, _ = self.encoder(batch.to(DEVICE))
                latent_vectors.append(mu.cpu())
        
        latent_vectors = torch.cat(latent_vectors, dim=0)
        
        return {
            'mean': latent_vectors.mean(dim=0),
            'std': latent_vectors.std(dim=0),
            'min': latent_vectors.min(dim=0)[0],
            'max': latent_vectors.max(dim=0)[0]
        }


def test_autoencoder():
    """
    Test ECG Autoencoder functionality.
    """
    print("=== Testing ECG Autoencoder ===\n")
    
    # Create model
    model = ECGAutoencoder(input_length=2500, latent_dim=32)
    model.to(DEVICE)
    print(f"Model created on device: {DEVICE}")
    
    # Count parameters
    n_params = sum(p.numel() for p in model.parameters())
    print(f"Total parameters: {n_params:,}\n")
    
    # Test forward pass
    batch_size = 8
    dummy_input = torch.randn(batch_size, 1, 2500).to(DEVICE)
    
    print("Test 1: Forward pass...")
    reconstructed, mu, logvar = model(dummy_input)
    print(f"  Input shape: {dummy_input.shape}")
    print(f"  Reconstructed shape: {reconstructed.shape}")
    print(f"  Latent mu shape: {mu.shape}")
    print(f"  Latent logvar shape: {logvar.shape}")
    
    # Test loss
    print("\nTest 2: Loss calculation...")
    loss_dict = model.loss_function(reconstructed, dummy_input, mu, logvar)
    print(f"  Total loss: {loss_dict['loss'].item():.4f}")
    print(f"  Reconstruction loss: {loss_dict['reconstruction_loss'].item():.4f}")
    print(f"  KL loss: {loss_dict['kl_loss'].item():.4f}")
    
    # Test encoding
    print("\nTest 3: Encoding...")
    latent = model.encode(dummy_input)
    print(f"  Latent representation shape: {latent.shape}")
    print(f"  Latent mean: {latent.mean().item():.4f}")
    print(f"  Latent std: {latent.std().item():.4f}")
    
    # Test decoding
    print("\nTest 4: Decoding...")
    decoded = model.decode(latent)
    print(f"  Decoded shape: {decoded.shape}")
    
    # Test generation
    print("\nTest 5: Generation...")
    generated = model.generate(n_samples=4, device=DEVICE)
    print(f"  Generated {generated.shape[0]} samples")
    print(f"  Generated shape: {generated.shape}")
    
    # Test reconstruction error
    print("\nTest 6: Reconstruction error...")
    errors = model.reconstruction_error(dummy_input)
    print(f"  Reconstruction errors: {errors}")
    print(f"  Mean error: {errors.mean().item():.4f}")
    
    # Test interpolation
    print("\nTest 7: Interpolation...")
    ecg1 = dummy_input[0:1]
    ecg2 = dummy_input[1:2]
    interpolated = model.interpolate(ecg1, ecg2, n_steps=5)
    print(f"  Interpolated shape: {interpolated.shape}")
    
    print("\n✓ All tests passed!")
    
    return model


if __name__ == "__main__":
    test_autoencoder()
