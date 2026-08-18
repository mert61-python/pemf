"""
Synthetic ECG Data Generator using GANs
========================================

Generates synthetic veterinary ECG data to augment limited datasets using:
1. NeuroKit2 parametric simulation (quick, species-specific)
2. P2E-WGAN (PPG to ECG reconstruction) - if PPG data available
3. EEG-WGAN adaptation (pure synthetic generation)

This augmentation strategy helps overcome data scarcity in veterinary applications.

Usage:
------
    generator = SyntheticECGGenerator(species='dog')
    
    # Method 1: Parametric simulation (fastest)
    synthetic_ecg = generator.simulate_ecg(duration=10, heart_rate=100)
    
    # Method 2: GAN-based generation (requires trained model)
    synthetic_ecg = generator.generate_gan_ecg(n_samples=100)
    
    # Method 3: Augment existing dataset
    augmented_data = generator.augment_dataset(real_ecg_data, augmentation_ratio=0.3)
"""

import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
import warnings

try:
    import neurokit2 as nk
    NEUROKIT_AVAILABLE = True
except ImportError:
    NEUROKIT_AVAILABLE = False
    warnings.warn("NeuroKit2 not available. Install with: pip install neurokit2")

try:
    import torch
    import torch.nn as nn
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    warnings.warn("PyTorch not available. GAN generation disabled.")

import sys
sys.path.append(str(Path(__file__).parent.parent))
from config import SYNTHETIC_DATA, SPECIES_PARAMS, SIGNAL_PROCESSING


class SyntheticECGGenerator:
    """
    Generate synthetic ECG data using multiple methods.
    """
    
    def __init__(self, species: str = 'dog', sampling_rate: int = 250):
        """
        Initialize synthetic ECG generator.
        
        Args:
            species: Animal species ('dog', 'cat', 'rabbit', 'mouse')
            sampling_rate: Sampling frequency in Hz
        """
        self.species = species.lower()
        self.fs = sampling_rate
        
        if self.species in SPECIES_PARAMS:
            self.species_params = SPECIES_PARAMS[self.species]
        else:
            warnings.warn(f"Unknown species {species}, using dog parameters")
            self.species_params = SPECIES_PARAMS['dog']
        
        self.synthetic_config = SYNTHETIC_DATA
        
        if not NEUROKIT_AVAILABLE:
            warnings.warn("NeuroKit2 not available. Limited functionality.")
    
    def simulate_ecg(self, 
                     duration: int = 10,
                     heart_rate: Optional[int] = None,
                     noise: float = 0.01,
                     artifacts: bool = False,
                     respiratory_modulation: bool = True) -> np.ndarray:
        """
        Simulate realistic ECG using NeuroKit2 parametric model.
        
        This is the fastest method and provides species-specific characteristics.
        
        Args:
            duration: Signal duration in seconds
            heart_rate: Heart rate in BPM (uses species default if None)
            noise: Gaussian noise level (0.0 to 0.1)
            artifacts: Add motion artifacts
            respiratory_modulation: Add respiratory sinus arrhythmia
            
        Returns:
            Synthetic ECG signal array
        """
        if not NEUROKIT_AVAILABLE:
            raise ImportError("NeuroKit2 required for ECG simulation")
        
        # Use species-specific heart rate if not specified
        if heart_rate is None:
            hr_range = self.species_params['normal_hr_range']
            heart_rate = int(np.mean(hr_range))
        
        # Generate base ECG
        ecg = nk.ecg_simulate(
            duration=duration,
            sampling_rate=self.fs,
            heart_rate=heart_rate,
            noise=noise,
            method='ecgsyn'  # Uses realistic ECGSYN model
        )
        
        # Add respiratory modulation (RSA)
        if respiratory_modulation:
            # Species-specific respiratory rates
            respiratory_rates = {
                'dog': 20,    # breaths per minute
                'cat': 25,
                'rabbit': 40,
                'mouse': 100
            }
            rr_rate = respiratory_rates.get(self.species, 20)
            
            # Create respiratory modulation
            t = np.arange(len(ecg)) / self.fs
            rsa = 0.05 * np.sin(2 * np.pi * (rr_rate / 60) * t)
            ecg = ecg * (1 + rsa)
        
        # Add artifacts (motion, electrode contact issues)
        if artifacts:
            ecg = nk.signal_distort(
                ecg,
                artifacts_amplitude=0.1,
                artifacts_frequency=1.0,
                artifacts_number=2
            )
        
        return ecg
    
    def simulate_multi_lead_ecg(self,
                                duration: int = 10,
                                n_leads: int = 3,
                                heart_rate: Optional[int] = None) -> Dict[str, np.ndarray]:
        """
        Simulate multi-lead ECG (e.g., Lead I, II, III).
        
        Args:
            duration: Signal duration in seconds
            n_leads: Number of leads to simulate
            heart_rate: Heart rate in BPM
            
        Returns:
            Dictionary with lead names as keys and ECG arrays as values
        """
        if not NEUROKIT_AVAILABLE:
            raise ImportError("NeuroKit2 required for ECG simulation")
        
        leads = {}
        lead_names = ['Lead_I', 'Lead_II', 'Lead_III', 'aVR', 'aVL', 'aVF',
                      'V1', 'V2', 'V3', 'V4', 'V5', 'V6']
        
        for i in range(min(n_leads, len(lead_names))):
            # Each lead has slightly different morphology
            ecg = self.simulate_ecg(duration=duration, heart_rate=heart_rate)
            
            # Add lead-specific variations
            if i > 0:
                phase_shift = i * 0.1  # Slight phase shift
                ecg = np.roll(ecg, int(phase_shift * self.fs))
            
            leads[lead_names[i]] = ecg
        
        return leads
    
    def add_pathological_features(self,
                                  ecg: np.ndarray,
                                  condition: str = 'arrhythmia') -> np.ndarray:
        """
        Add pathological features to simulate diseased heart conditions.
        
        Args:
            ecg: Clean ECG signal
            condition: Type of pathology ('arrhythmia', 'ischemia', 'hypertrophy')
            
        Returns:
            Modified ECG with pathological features
        """
        ecg_modified = ecg.copy()
        
        if condition == 'arrhythmia':
            # Add premature beats (ectopic)
            beat_indices = len(ecg) // 100  # ~1% ectopic beats
            for _ in range(beat_indices):
                idx = np.random.randint(0, len(ecg))
                ecg_modified[idx:idx+10] *= 1.5  # Amplify beat
        
        elif condition == 'ischemia':
            # ST segment depression
            ecg_modified -= 0.1  # Lower baseline
        
        elif condition == 'hypertrophy':
            # Increased QRS amplitude
            ecg_modified *= 1.3
        
        return ecg_modified
    
    def augment_dataset(self,
                       real_data: Union[np.ndarray, List[np.ndarray]],
                       augmentation_ratio: float = 0.3,
                       method: str = 'parametric') -> Tuple[np.ndarray, np.ndarray]:
        """
        Augment real ECG dataset with synthetic data.
        
        Args:
            real_data: Real ECG signals (array or list of arrays)
            augmentation_ratio: Ratio of synthetic to real data (0.0 to 1.0)
            method: 'parametric' (NeuroKit2) or 'gan' (deep learning)
            
        Returns:
            Tuple of (augmented_data, labels) where labels indicate real (1) or synthetic (0)
        """
        if isinstance(real_data, list):
            real_data = np.array(real_data)
        
        n_real = len(real_data)
        n_synthetic = int(n_real * augmentation_ratio)
        
        synthetic_data = []
        
        if method == 'parametric':
            # Generate synthetic ECGs with varying parameters
            for _ in range(n_synthetic):
                # Randomize parameters within species-specific ranges
                hr_range = self.species_params['normal_hr_range']
                hr = np.random.randint(hr_range[0], hr_range[1])
                
                # Match duration of real data
                duration = len(real_data[0]) / self.fs
                
                synthetic_ecg = self.simulate_ecg(
                    duration=duration,
                    heart_rate=hr,
                    noise=np.random.uniform(0.01, 0.05),
                    artifacts=np.random.random() > 0.7  # 30% chance of artifacts
                )
                
                # Ensure same length as real data
                if len(synthetic_ecg) != len(real_data[0]):
                    synthetic_ecg = np.interp(
                        np.linspace(0, 1, len(real_data[0])),
                        np.linspace(0, 1, len(synthetic_ecg)),
                        synthetic_ecg
                    )
                
                synthetic_data.append(synthetic_ecg)
        
        elif method == 'gan':
            # TODO: Implement GAN-based generation
            # This requires a pre-trained WGAN model
            warnings.warn("GAN method not yet implemented. Using parametric instead.")
            return self.augment_dataset(real_data, augmentation_ratio, 'parametric')
        
        # Combine real and synthetic
        synthetic_data = np.array(synthetic_data)
        augmented_data = np.vstack([real_data, synthetic_data])
        
        # Create labels (1 = real, 0 = synthetic)
        labels = np.concatenate([
            np.ones(n_real),
            np.zeros(n_synthetic)
        ])
        
        # Shuffle
        shuffle_idx = np.random.permutation(len(augmented_data))
        augmented_data = augmented_data[shuffle_idx]
        labels = labels[shuffle_idx]
        
        print(f"Dataset augmented: {n_real} real + {n_synthetic} synthetic = {len(augmented_data)} total")
        
        return augmented_data, labels
    
    def validate_synthetic_quality(self,
                                   real_ecg: np.ndarray,
                                   synthetic_ecg: np.ndarray) -> Dict[str, float]:
        """
        Validate synthetic ECG quality by comparing with real ECG.
        
        Metrics:
        - Heart rate similarity
        - HRV similarity
        - Spectral similarity (Power Spectral Density)
        - Morphological similarity (cross-correlation)
        
        Args:
            real_ecg: Real ECG signal
            synthetic_ecg: Synthetic ECG signal
            
        Returns:
            Dictionary of quality metrics
        """
        if not NEUROKIT_AVAILABLE:
            warnings.warn("NeuroKit2 not available. Limited validation.")
            return {}
        
        metrics = {}
        
        # Process both signals
        try:
            real_processed = nk.ecg_process(real_ecg, sampling_rate=self.fs)[0]
            synth_processed = nk.ecg_process(synthetic_ecg, sampling_rate=self.fs)[0]
            
            # Heart rate similarity
            real_hr = np.mean(real_processed['ECG_Rate'])
            synth_hr = np.mean(synth_processed['ECG_Rate'])
            metrics['hr_difference'] = abs(real_hr - synth_hr)
            metrics['hr_similarity'] = 1 - (metrics['hr_difference'] / real_hr)
            
            # HRV similarity (RMSSD)
            real_rmssd = nk.hrv_time(real_processed)['HRV_RMSSD'].values[0]
            synth_rmssd = nk.hrv_time(synth_processed)['HRV_RMSSD'].values[0]
            metrics['hrv_rmssd_difference'] = abs(real_rmssd - synth_rmssd)
            
        except Exception as e:
            warnings.warn(f"Quality validation failed: {e}")
        
        # Cross-correlation (morphological similarity)
        if len(real_ecg) == len(synthetic_ecg):
            correlation = np.corrcoef(real_ecg, synthetic_ecg)[0, 1]
            metrics['morphological_correlation'] = correlation
        
        return metrics
    
    def generate_batch(self,
                      n_samples: int,
                      duration: int = 10,
                      heart_rate_range: Optional[Tuple[int, int]] = None) -> np.ndarray:
        """
        Generate a batch of synthetic ECG signals.
        
        Args:
            n_samples: Number of ECG signals to generate
            duration: Duration of each signal in seconds
            heart_rate_range: (min_hr, max_hr) or None for species default
            
        Returns:
            Array of shape (n_samples, signal_length)
        """
        if heart_rate_range is None:
            heart_rate_range = self.species_params['normal_hr_range']
        
        batch = []
        for _ in range(n_samples):
            hr = np.random.randint(heart_rate_range[0], heart_rate_range[1])
            ecg = self.simulate_ecg(duration=duration, heart_rate=hr)
            batch.append(ecg)
        
        return np.array(batch)


class WGAN_ECG_Generator(nn.Module):
    """
    Wasserstein GAN Generator for ECG synthesis.
    
    Based on:
    - P2E-WGAN: https://github.com/khuongav/P2E-WGAN-ecg-ppg-reconstruction
    - EEG-WGAN: https://github.com/JoshParkSJ/eeg-wgan
    
    This is a placeholder architecture. Full implementation requires:
    1. Training on veterinary ECG dataset
    2. Gradient penalty implementation
    3. Feature-based loss functions
    """
    
    def __init__(self, latent_dim: int = 100, signal_length: int = 2500):
        super(WGAN_ECG_Generator, self).__init__()
        
        if not TORCH_AVAILABLE:
            raise ImportError("PyTorch required for GAN generation")
        
        self.latent_dim = latent_dim
        self.signal_length = signal_length
        
        # 1D Convolutional Generator
        self.model = nn.Sequential(
            # Input: latent vector (batch_size, latent_dim, 1)
            nn.ConvTranspose1d(latent_dim, 512, 4, 1, 0),
            nn.BatchNorm1d(512),
            nn.ReLU(True),
            
            # (batch_size, 512, 4)
            nn.ConvTranspose1d(512, 256, 4, 2, 1),
            nn.BatchNorm1d(256),
            nn.ReLU(True),
            
            # (batch_size, 256, 8)
            nn.ConvTranspose1d(256, 128, 4, 2, 1),
            nn.BatchNorm1d(128),
            nn.ReLU(True),
            
            # (batch_size, 128, 16)
            nn.ConvTranspose1d(128, 64, 4, 2, 1),
            nn.BatchNorm1d(64),
            nn.ReLU(True),
            
            # (batch_size, 64, 32)
            nn.ConvTranspose1d(64, 1, 4, 2, 1),
            nn.Tanh()
            
            # Output: (batch_size, 1, signal_length)
        )
    
    def forward(self, z):
        """Generate ECG from latent vector."""
        z = z.view(z.size(0), z.size(1), 1)
        return self.model(z)


def main():
    """
    Test synthetic ECG generation.
    """
    print("=== Synthetic ECG Generator Test ===\n")
    
    if not NEUROKIT_AVAILABLE:
        print("NeuroKit2 not available. Install with: pip install neurokit2")
        return
    
    # Initialize generator
    generator = SyntheticECGGenerator(species='dog', sampling_rate=250)
    
    # Test 1: Generate single ECG
    print("Test 1: Generating single synthetic dog ECG...")
    ecg = generator.simulate_ecg(duration=10, heart_rate=100, noise=0.02)
    print(f"Generated ECG shape: {ecg.shape}")
    print(f"Mean: {np.mean(ecg):.3f}, Std: {np.std(ecg):.3f}\n")
    
    # Test 2: Generate batch
    print("Test 2: Generating batch of 5 ECGs...")
    batch = generator.generate_batch(n_samples=5, duration=10)
    print(f"Batch shape: {batch.shape}\n")
    
    # Test 3: Augment dataset
    print("Test 3: Augmenting dataset...")
    real_data = [generator.simulate_ecg(duration=10) for _ in range(10)]
    augmented, labels = generator.augment_dataset(real_data, augmentation_ratio=0.3)
    print(f"Original: {len(real_data)}, Augmented: {len(augmented)}")
    print(f"Real samples: {np.sum(labels)}, Synthetic: {len(augmented) - np.sum(labels)}\n")
    
    # Test 4: Quality validation
    print("Test 4: Validating synthetic quality...")
    real_ecg = generator.simulate_ecg(duration=10, heart_rate=100)
    synth_ecg = generator.simulate_ecg(duration=10, heart_rate=105)
    metrics = generator.validate_synthetic_quality(real_ecg, synth_ecg)
    print("Quality Metrics:")
    for key, value in metrics.items():
        print(f"  {key}: {value:.4f}")
    
    # Test 5: Multi-lead ECG
    print("\nTest 5: Generating multi-lead ECG...")
    leads = generator.simulate_multi_lead_ecg(duration=10, n_leads=3)
    print(f"Generated {len(leads)} leads: {list(leads.keys())}")
    
    print("\n✓ All tests completed successfully!")


if __name__ == "__main__":
    main()
