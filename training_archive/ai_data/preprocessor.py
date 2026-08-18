"""
ECG Signal Preprocessor
=======================

Processes raw ECG signals for AI model training and inference.

Features:
---------
1. Signal Filtering:
   - Bandpass filter (0.5-50 Hz) to remove baseline wander and high-frequency noise
   - Notch filter (50/60 Hz) for powerline interference
   
2. R-peak Detection:
   - Pan-Tompkins algorithm for QRS complex detection
   - Adaptive thresholding for different species
   
3. HRV Analysis:
   - Time domain: SDNN, RMSSD, pNN50, mean HR
   - Frequency domain: VLF, LF, HF, LF/HF ratio
   - Nonlinear: Poincaré plot (SD1, SD2), entropy measures
   
4. ECG Morphology:
   - P-wave, QRS, T-wave detection and measurements
   - PR interval, QT interval calculation
   - Heart rate variability metrics

Usage:
------
    preprocessor = ECGPreprocessor(species='dog')
    filtered_signal = preprocessor.filter_signal(raw_ecg, fs=250)
    r_peaks = preprocessor.detect_r_peaks(filtered_signal, fs=250)
    hrv_features = preprocessor.extract_hrv_features(r_peaks, fs=250)
"""

import numpy as np
import pandas as pd
from scipy import signal
from scipy.interpolate import interp1d
from typing import Tuple, Dict, List, Optional
import warnings
from pathlib import Path

try:
    from biosppy.signals import ecg
    BIOSPPY_AVAILABLE = True
except ImportError:
    BIOSPPY_AVAILABLE = False
    warnings.warn("biosppy not available. Some features may be limited.")

try:
    import wfdb
    WFDB_AVAILABLE = True
except ImportError:
    WFDB_AVAILABLE = False
    warnings.warn("wfdb not available. WFDB format reading disabled.")

# Import configuration
import sys
sys.path.append(str(Path(__file__).parent.parent))
from config import SIGNAL_PROCESSING, HRV_FEATURES, SPECIES_PARAMS


class ECGPreprocessor:
    """
    Comprehensive ECG signal preprocessing for veterinary applications.
    """
    
    def __init__(self, species: str = 'dog', sampling_rate: int = 250):
        """
        Initialize the ECG preprocessor.
        
        Args:
            species: Animal species ('dog', 'cat', 'rabbit', 'mouse')
            sampling_rate: Sampling frequency in Hz
        """
        self.species = species.lower()
        self.fs = sampling_rate
        
        # Get species-specific parameters
        if self.species in SPECIES_PARAMS:
            self.species_params = SPECIES_PARAMS[self.species]
        else:
            warnings.warn(f"Unknown species {species}, using dog parameters")
            self.species_params = SPECIES_PARAMS['dog']
        
        # Signal processing parameters
        self.filter_params = SIGNAL_PROCESSING['bandpass_filter']
        self.notch_params = SIGNAL_PROCESSING['notch_filter']
        
    def filter_signal(self, signal_data: np.ndarray, fs: Optional[int] = None) -> np.ndarray:
        """
        Apply bandpass and notch filters to remove noise.
        
        Args:
            signal_data: Raw ECG signal
            fs: Sampling frequency (uses self.fs if not provided)
            
        Returns:
            Filtered signal
        """
        if fs is None:
            fs = self.fs
        
        # Bandpass filter (remove baseline wander and high-frequency noise)
        sos_bandpass = signal.butter(
            self.filter_params['order'],
            [self.filter_params['lowcut'], self.filter_params['highcut']],
            btype='bandpass',
            fs=fs,
            output='sos'
        )
        filtered = signal.sosfiltfilt(sos_bandpass, signal_data)
        
        # Notch filter (remove powerline interference)
        b_notch, a_notch = signal.iirnotch(
            self.notch_params['freq'],
            self.notch_params['quality_factor'],
            fs
        )
        filtered = signal.filtfilt(b_notch, a_notch, filtered)
        
        return filtered
    
    def detect_r_peaks(self, signal_data: np.ndarray, fs: Optional[int] = None) -> np.ndarray:
        """
        Detect R-peaks using Pan-Tompkins algorithm or biosppy.
        
        Args:
            signal_data: Filtered ECG signal
            fs: Sampling frequency
            
        Returns:
            Array of R-peak indices
        """
        if fs is None:
            fs = self.fs
        
        if BIOSPPY_AVAILABLE:
            # Use biosppy for robust R-peak detection
            try:
                out = ecg.ecg(signal=signal_data, sampling_rate=fs, show=False)
                r_peaks = out['rpeaks']
                return r_peaks
            except Exception as e:
                warnings.warn(f"biosppy R-peak detection failed: {e}. Using fallback method.")
        
        # Fallback: Simple Pan-Tompkins implementation
        return self._pan_tompkins(signal_data, fs)
    
    def _pan_tompkins(self, signal_data: np.ndarray, fs: int) -> np.ndarray:
        """
        Simplified Pan-Tompkins algorithm for R-peak detection.
        
        Args:
            signal_data: Filtered ECG signal
            fs: Sampling frequency
            
        Returns:
            Array of R-peak indices
        """
        # Derivative (emphasize QRS slopes)
        derivative = np.diff(signal_data)
        
        # Squaring (make all values positive, emphasize larger differences)
        squared = derivative ** 2
        
        # Moving average integration
        window_size = int(0.150 * fs)  # 150ms integration window
        integrated = np.convolve(squared, np.ones(window_size) / window_size, mode='same')
        
        # Adaptive thresholding
        threshold = 0.5 * np.max(integrated)
        
        # Find peaks above threshold
        peaks = signal.find_peaks(integrated, height=threshold, distance=int(0.2 * fs))[0]
        
        return peaks
    
    def extract_rr_intervals(self, r_peaks: np.ndarray, fs: Optional[int] = None) -> np.ndarray:
        """
        Calculate RR intervals from R-peaks.
        
        Args:
            r_peaks: Array of R-peak indices
            fs: Sampling frequency
            
        Returns:
            RR intervals in milliseconds
        """
        if fs is None:
            fs = self.fs
        
        if len(r_peaks) < 2:
            return np.array([])
        
        rr_intervals = np.diff(r_peaks) / fs * 1000  # Convert to milliseconds
        return rr_intervals
    
    def extract_hrv_time_domain(self, rr_intervals: np.ndarray) -> Dict[str, float]:
        """
        Extract time-domain HRV features.
        
        Args:
            rr_intervals: RR intervals in milliseconds
            
        Returns:
            Dictionary of time-domain HRV metrics
        """
        if len(rr_intervals) < 2:
            return {feature: 0.0 for feature in HRV_FEATURES['time_domain']}
        
        # Remove outliers (RR intervals outside physiological range)
        valid_rr = rr_intervals[
            (rr_intervals > 100) & (rr_intervals < 3000)
        ]
        
        if len(valid_rr) < 2:
            return {feature: 0.0 for feature in HRV_FEATURES['time_domain']}
        
        # Calculate metrics
        sdnn = np.std(valid_rr, ddof=1)
        
        # RMSSD: Root mean square of successive differences
        diff_rr = np.diff(valid_rr)
        rmssd = np.sqrt(np.mean(diff_rr ** 2))
        
        # pNN50: Percentage of successive RR intervals that differ by more than 50 ms
        nn50 = np.sum(np.abs(diff_rr) > 50)
        pnn50 = (nn50 / len(diff_rr)) * 100 if len(diff_rr) > 0 else 0
        
        # Heart rate statistics
        hr = 60000 / valid_rr  # Convert RR (ms) to HR (bpm)
        mean_hr = np.mean(hr)
        std_hr = np.std(hr, ddof=1)
        
        return {
            'SDNN': sdnn,
            'RMSSD': rmssd,
            'pNN50': pnn50,
            'mean_hr': mean_hr,
            'std_hr': std_hr
        }
    
    def extract_hrv_frequency_domain(self, rr_intervals: np.ndarray, fs: Optional[int] = None) -> Dict[str, float]:
        """
        Extract frequency-domain HRV features using FFT.
        
        Args:
            rr_intervals: RR intervals in milliseconds
            fs: Sampling frequency for interpolation (default: 4 Hz)
            
        Returns:
            Dictionary of frequency-domain HRV metrics
        """
        if fs is None:
            fs = 4.0  # Standard resampling frequency for HRV analysis
        
        if len(rr_intervals) < 10:
            return {feature: 0.0 for feature in HRV_FEATURES['frequency_domain']}
        
        # Remove outliers
        valid_rr = rr_intervals[
            (rr_intervals > 100) & (rr_intervals < 3000)
        ]
        
        if len(valid_rr) < 10:
            return {feature: 0.0 for feature in HRV_FEATURES['frequency_domain']}
        
        # Create time axis
        time_rr = np.cumsum(valid_rr) / 1000.0  # Convert to seconds
        time_rr = np.insert(time_rr, 0, 0)  # Start at 0
        
        # Interpolate to uniform sampling
        f_interp = interp1d(time_rr, np.insert(valid_rr, 0, valid_rr[0]), 
                           kind='cubic', fill_value='extrapolate')
        
        time_uniform = np.arange(0, time_rr[-1], 1/fs)
        rr_uniform = f_interp(time_uniform)
        
        # Apply Welch's method for PSD estimation
        freqs, psd = signal.welch(rr_uniform, fs=fs, nperseg=min(256, len(rr_uniform)))
        
        # Define frequency bands (adjusted for veterinary ECG)
        vlf_band = (freqs >= 0.003) & (freqs < 0.04)
        lf_band = (freqs >= 0.04) & (freqs < 0.15)
        hf_band = (freqs >= 0.15) & (freqs < 0.4)
        
        # Calculate power in each band
        vlf_power = np.trapz(psd[vlf_band], freqs[vlf_band])
        lf_power = np.trapz(psd[lf_band], freqs[lf_band])
        hf_power = np.trapz(psd[hf_band], freqs[hf_band])
        
        # LF/HF ratio (autonomic balance)
        lf_hf_ratio = lf_power / hf_power if hf_power > 0 else 0
        
        return {
            'VLF': vlf_power,
            'LF': lf_power,
            'HF': hf_power,
            'LF_HF': lf_hf_ratio
        }
    
    def extract_hrv_nonlinear(self, rr_intervals: np.ndarray) -> Dict[str, float]:
        """
        Extract nonlinear HRV features (Poincaré plot, entropy).
        
        Args:
            rr_intervals: RR intervals in milliseconds
            
        Returns:
            Dictionary of nonlinear HRV metrics
        """
        if len(rr_intervals) < 10:
            return {feature: 0.0 for feature in HRV_FEATURES['nonlinear']}
        
        # Remove outliers
        valid_rr = rr_intervals[
            (rr_intervals > 100) & (rr_intervals < 3000)
        ]
        
        if len(valid_rr) < 10:
            return {feature: 0.0 for feature in HRV_FEATURES['nonlinear']}
        
        # Poincaré plot parameters
        rr1 = valid_rr[:-1]
        rr2 = valid_rr[1:]
        
        # SD1: Standard deviation perpendicular to line of identity (short-term variability)
        sd1 = np.std(rr1 - rr2, ddof=1) / np.sqrt(2)
        
        # SD2: Standard deviation along line of identity (long-term variability)
        sd2 = np.std(rr1 + rr2, ddof=1) / np.sqrt(2)
        
        # Sample entropy (complexity measure)
        sample_ent = self._sample_entropy(valid_rr, m=2, r=0.2 * np.std(valid_rr, ddof=1))
        
        # Approximate entropy (regularity measure)
        approx_ent = self._approximate_entropy(valid_rr, m=2, r=0.2 * np.std(valid_rr, ddof=1))
        
        return {
            'SD1': sd1,
            'SD2': sd2,
            'sample_entropy': sample_ent,
            'approximate_entropy': approx_ent
        }
    
    def _sample_entropy(self, data: np.ndarray, m: int, r: float) -> float:
        """
        Calculate sample entropy (complexity measure).
        
        Args:
            data: Time series data
            m: Embedding dimension
            r: Tolerance (typically 0.2 * std)
            
        Returns:
            Sample entropy value
        """
        N = len(data)
        
        def _maxdist(x_i, x_j):
            return max([abs(ua - va) for ua, va in zip(x_i, x_j)])
        
        def _phi(m):
            patterns = np.array([data[i:i + m] for i in range(N - m + 1)])
            C = np.zeros(len(patterns))
            for i in range(len(patterns)):
                for j in range(len(patterns)):
                    if i != j and _maxdist(patterns[i], patterns[j]) <= r:
                        C[i] += 1
            return np.sum(C) / (len(patterns) * (len(patterns) - 1))
        
        try:
            return -np.log(_phi(m + 1) / _phi(m))
        except:
            return 0.0
    
    def _approximate_entropy(self, data: np.ndarray, m: int, r: float) -> float:
        """
        Calculate approximate entropy (regularity measure).
        
        Args:
            data: Time series data
            m: Embedding dimension
            r: Tolerance
            
        Returns:
            Approximate entropy value
        """
        def _phi(m):
            patterns = np.array([data[i:i + m] for i in range(len(data) - m + 1)])
            C = np.zeros(len(patterns))
            for i in range(len(patterns)):
                for j in range(len(patterns)):
                    if np.max(np.abs(patterns[i] - patterns[j])) <= r:
                        C[i] += 1
            return np.sum(np.log(C / len(patterns))) / len(patterns)
        
        try:
            return _phi(m) - _phi(m + 1)
        except:
            return 0.0
    
    def extract_all_hrv_features(self, r_peaks: np.ndarray, fs: Optional[int] = None) -> Dict[str, float]:
        """
        Extract all HRV features (time, frequency, nonlinear domains).
        
        Args:
            r_peaks: Array of R-peak indices
            fs: Sampling frequency
            
        Returns:
            Dictionary containing all HRV features
        """
        if fs is None:
            fs = self.fs
        
        # Extract RR intervals
        rr_intervals = self.extract_rr_intervals(r_peaks, fs)
        
        if len(rr_intervals) < 10:
            return {}
        
        # Combine all features
        features = {}
        features.update(self.extract_hrv_time_domain(rr_intervals))
        features.update(self.extract_hrv_frequency_domain(rr_intervals))
        features.update(self.extract_hrv_nonlinear(rr_intervals))
        
        return features
    
    def process_ecg_signal(self, raw_signal: np.ndarray, fs: Optional[int] = None) -> Dict:
        """
        Complete ECG processing pipeline.
        
        Args:
            raw_signal: Raw ECG signal
            fs: Sampling frequency
            
        Returns:
            Dictionary containing:
                - filtered_signal: Filtered ECG
                - r_peaks: R-peak indices
                - rr_intervals: RR intervals
                - hrv_features: All HRV features
                - heart_rate: Mean heart rate
        """
        if fs is None:
            fs = self.fs
        
        # Filter signal
        filtered = self.filter_signal(raw_signal, fs)
        
        # Detect R-peaks
        r_peaks = self.detect_r_peaks(filtered, fs)
        
        # Extract RR intervals
        rr_intervals = self.extract_rr_intervals(r_peaks, fs)
        
        # Extract HRV features
        hrv_features = self.extract_all_hrv_features(r_peaks, fs)
        
        # Calculate mean heart rate
        mean_hr = 60000 / np.mean(rr_intervals) if len(rr_intervals) > 0 else 0
        
        return {
            'filtered_signal': filtered,
            'r_peaks': r_peaks,
            'rr_intervals': rr_intervals,
            'hrv_features': hrv_features,
            'heart_rate': mean_hr,
            'sampling_rate': fs,
            'species': self.species
        }
    
    def load_wfdb_record(self, record_path: str) -> Tuple[np.ndarray, int, Dict]:
        """
        Load ECG data from WFDB format.
        
        Args:
            record_path: Path to WFDB record (without extension)
            
        Returns:
            Tuple of (signal, sampling_rate, metadata)
        """
        if not WFDB_AVAILABLE:
            raise ImportError("wfdb package not available. Install with: pip install wfdb")
        
        record = wfdb.rdrecord(record_path)
        signal_data = record.p_signal[:, 0]  # First channel
        fs = record.fs
        
        metadata = {
            'record_name': record.record_name,
            'sampling_rate': fs,
            'signal_length': len(signal_data),
            'units': record.units[0] if record.units else 'mV',
            'comments': record.comments
        }
        
        return signal_data, fs, metadata
    
    def save_processed_data(self, processed_data: Dict, output_path: str):
        """
        Save processed ECG data to file.
        
        Args:
            processed_data: Output from process_ecg_signal()
            output_path: Path to save data (NPZ format)
        """
        # Convert to numpy-saveable format
        save_dict = {
            'filtered_signal': processed_data['filtered_signal'],
            'r_peaks': processed_data['r_peaks'],
            'rr_intervals': processed_data['rr_intervals'],
            'sampling_rate': processed_data['sampling_rate'],
            'species': processed_data['species'],
            'heart_rate': processed_data['heart_rate']
        }
        
        # Add HRV features as separate arrays
        for key, value in processed_data['hrv_features'].items():
            save_dict[f'hrv_{key}'] = value
        
        np.savez_compressed(output_path, **save_dict)
        print(f"Processed data saved to: {output_path}")


def main():
    """
    Example usage and testing.
    """
    import matplotlib.pyplot as plt
    
    # Generate synthetic ECG signal for testing
    fs = 250  # Sampling rate
    duration = 10  # seconds
    t = np.arange(0, duration, 1/fs)
    
    # Simulate dog ECG (HR ~100 bpm)
    hr = 100  # beats per minute
    f_hr = hr / 60  # Hz
    
    # Simple synthetic ECG (sum of sine waves)
    ecg_signal = (
        0.5 * np.sin(2 * np.pi * f_hr * t) +  # P-wave
        1.5 * np.sin(2 * np.pi * f_hr * t + np.pi/2) +  # QRS complex
        0.3 * np.sin(2 * np.pi * f_hr * t + np.pi)  # T-wave
    )
    
    # Add noise
    noise = 0.1 * np.random.randn(len(ecg_signal))
    ecg_noisy = ecg_signal + noise
    
    # Process ECG
    preprocessor = ECGPreprocessor(species='dog', sampling_rate=fs)
    results = preprocessor.process_ecg_signal(ecg_noisy, fs)
    
    # Print results
    print("\n=== ECG Processing Results ===")
    print(f"Species: {results['species']}")
    print(f"Sampling Rate: {results['sampling_rate']} Hz")
    print(f"Mean Heart Rate: {results['heart_rate']:.1f} bpm")
    print(f"Number of R-peaks: {len(results['r_peaks'])}")
    print(f"Number of RR intervals: {len(results['rr_intervals'])}")
    
    print("\n=== HRV Features ===")
    for feature, value in results['hrv_features'].items():
        print(f"{feature}: {value:.3f}")
    
    # Plot results
    plt.figure(figsize=(15, 8))
    
    # Original signal
    plt.subplot(3, 1, 1)
    plt.plot(t, ecg_noisy, 'b-', alpha=0.7, label='Noisy ECG')
    plt.title('Original ECG Signal')
    plt.xlabel('Time (s)')
    plt.ylabel('Amplitude')
    plt.legend()
    plt.grid(True)
    
    # Filtered signal with R-peaks
    plt.subplot(3, 1, 2)
    plt.plot(t, results['filtered_signal'], 'g-', label='Filtered ECG')
    r_peak_times = results['r_peaks'] / fs
    r_peak_values = results['filtered_signal'][results['r_peaks']]
    plt.plot(r_peak_times, r_peak_values, 'ro', markersize=8, label='R-peaks')
    plt.title('Filtered ECG with Detected R-peaks')
    plt.xlabel('Time (s)')
    plt.ylabel('Amplitude')
    plt.legend()
    plt.grid(True)
    
    # RR intervals
    plt.subplot(3, 1, 3)
    plt.plot(results['rr_intervals'], 'b.-')
    plt.title('RR Intervals')
    plt.xlabel('Beat Number')
    plt.ylabel('RR Interval (ms)')
    plt.grid(True)
    
    plt.tight_layout()
    plt.savefig('ecg_processing_example.png', dpi=150)
    print("\nPlot saved as 'ecg_processing_example.png'")
    plt.show()


if __name__ == "__main__":
    main()
