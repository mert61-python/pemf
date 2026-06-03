"""
NeuroKit2 Integration for Advanced ECG Analysis
=================================================

Integrates NeuroKit2 library for comprehensive biosignal processing.
NeuroKit2 provides state-of-the-art algorithms for ECG analysis,
complementing our custom preprocessing pipeline.

Features:
---------
- ECG simulation with realistic artifacts
- Advanced HRV analysis (time, frequency, nonlinear)
- Event-related and interval-related analysis
- ECG delineation (P, Q, R, S, T wave detection)
- Signal quality assessment
- Multi-method R-peak detection comparison

Reference:
----------
Makowski, D., Pham, T., Lau, Z. J., Brammer, J. C., Lespinasse, F.,
Pham, H., Schölzel, C., & Chen, S. A. (2021). NeuroKit2: A Python toolbox
for neurophysiological signal processing. Behavior Research Methods,
53(4), 1689–1696. https://doi.org/10.3758/s13428-020-01516-y

GitHub: https://github.com/neuropsychology/NeuroKit
Documentation: https://neuropsychology.github.io/NeuroKit/
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
import warnings

try:
    import neurokit2 as nk
    NEUROKIT_AVAILABLE = True
except ImportError:
    NEUROKIT_AVAILABLE = False
    warnings.warn("NeuroKit2 not installed. Install with: pip install neurokit2")

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from config import SIGNAL_PROCESSING, HRV_FEATURES, SPECIES_PARAMS


class NeuroKitECGAnalyzer:
    """
    Advanced ECG analysis using NeuroKit2 library.
    
    Complements our custom ECGPreprocessor with additional features:
    - Multiple R-peak detection algorithms
    - Comprehensive HRV analysis
    - ECG quality assessment
    - Delineation of all ECG waves
    """
    
    def __init__(self, species: str = 'dog', sampling_rate: int = 250):
        """
        Initialize NeuroKit2-based ECG analyzer.
        
        Args:
            species: Animal species
            sampling_rate: Sampling frequency in Hz
        """
        if not NEUROKIT_AVAILABLE:
            raise ImportError("NeuroKit2 required. Install: pip install neurokit2")
        
        self.species = species.lower()
        self.fs = sampling_rate
        
        if self.species in SPECIES_PARAMS:
            self.species_params = SPECIES_PARAMS[self.species]
        else:
            self.species_params = SPECIES_PARAMS['dog']
    
    def process_ecg_complete(self, ecg_signal: np.ndarray) -> Tuple[pd.DataFrame, Dict]:
        """
        Complete ECG processing pipeline using NeuroKit2.
        
        This method performs:
        1. Signal cleaning
        2. R-peak detection
        3. Quality assessment
        4. Heart rate calculation
        5. HRV feature extraction
        
        Args:
            ecg_signal: Raw ECG signal
            
        Returns:
            Tuple of (processed_signals DataFrame, info dictionary)
        """
        # Process ECG with NeuroKit2
        signals, info = nk.ecg_process(ecg_signal, sampling_rate=self.fs)
        
        return signals, info
    
    def compare_peak_detectors(self, ecg_signal: np.ndarray) -> Dict[str, np.ndarray]:
        """
        Compare different R-peak detection algorithms.
        
        NeuroKit2 supports multiple methods:
        - neurokit: Default NeuroKit algorithm
        - pantompkins1985: Classic Pan-Tompkins
        - hamilton2002: Hamilton's method
        - elgendi2010: Elgendi's method
        - engzeemod2012: Modified Engzee
        
        Args:
            ecg_signal: ECG signal
            
        Returns:
            Dictionary with method names as keys and R-peak indices as values
        """
        methods = ['neurokit', 'pantompkins1985', 'hamilton2002', 'elgendi2010']
        results = {}
        
        # Clean signal first
        ecg_cleaned = nk.ecg_clean(ecg_signal, sampling_rate=self.fs)
        
        for method in methods:
            try:
                _, rpeaks = nk.ecg_peaks(ecg_cleaned, sampling_rate=self.fs, method=method)
                results[method] = rpeaks['ECG_R_Peaks']
                print(f"{method}: {len(rpeaks['ECG_R_Peaks'])} peaks detected")
            except Exception as e:
                print(f"{method} failed: {e}")
        
        return results
    
    def extract_hrv_comprehensive(self, ecg_signal: np.ndarray) -> pd.DataFrame:
        """
        Extract comprehensive HRV features using NeuroKit2.
        
        Includes:
        - Time domain: RMSSD, SDNN, pNN50, etc.
        - Frequency domain: VLF, LF, HF, LF/HF ratio
        - Nonlinear: SD1, SD2, Sample Entropy, DFA
        
        Args:
            ecg_signal: ECG signal
            
        Returns:
            DataFrame with all HRV metrics
        """
        # Process ECG
        signals, info = nk.ecg_process(ecg_signal, sampling_rate=self.fs)
        
        # Extract HRV features
        hrv = nk.hrv(signals, sampling_rate=self.fs, show=False)
        
        return hrv
    
    def delineate_waves(self, ecg_signal: np.ndarray) -> Tuple[pd.DataFrame, Dict]:
        """
        Detect and delineate P, Q, R, S, T waves.
        
        This identifies:
        - P-wave onset and offset
        - Q-wave
        - R-peak
        - S-wave
        - T-wave onset, peak, and offset
        
        Args:
            ecg_signal: ECG signal
            
        Returns:
            Tuple of (delineation DataFrame, wave information)
        """
        # Process ECG first
        signals, info = nk.ecg_process(ecg_signal, sampling_rate=self.fs)
        
        # Delineate waves
        _, waves = nk.ecg_delineate(ecg_signal, info['ECG_R_Peaks'], 
                                     sampling_rate=self.fs, method='dwt')
        
        return signals, waves
    
    def assess_signal_quality(self, ecg_signal: np.ndarray) -> Dict[str, float]:
        """
        Assess ECG signal quality.
        
        Quality indicators:
        - Signal-to-noise ratio
        - Baseline wander
        - Powerline interference
        - Muscle artifacts
        
        Args:
            ecg_signal: ECG signal
            
        Returns:
            Dictionary of quality metrics
        """
        # NeuroKit2's quality assessment
        quality = nk.ecg_quality(ecg_signal, sampling_rate=self.fs)
        
        # Additional custom metrics
        metrics = {
            'quality_score': np.mean(quality),
            'poor_quality_percentage': np.sum(quality == 0) / len(quality) * 100
        }
        
        # Signal statistics
        metrics['snr_estimate'] = np.mean(ecg_signal) / np.std(ecg_signal)
        metrics['baseline_drift'] = np.polyfit(np.arange(len(ecg_signal)), ecg_signal, 1)[0]
        
        return metrics
    
    def extract_heartbeats(self, ecg_signal: np.ndarray, 
                          before: float = 0.2, 
                          after: float = 0.4) -> Dict:
        """
        Extract and analyze individual heartbeats.
        
        Args:
            ecg_signal: ECG signal
            before: Time before R-peak to include (seconds)
            after: Time after R-peak to include (seconds)
            
        Returns:
            Dictionary containing individual heartbeats and statistics
        """
        # Process ECG
        signals, info = nk.ecg_process(ecg_signal, sampling_rate=self.fs)
        
        # Extract heartbeats
        heartbeats = nk.ecg_segment(signals, info['ECG_R_Peaks'], 
                                    sampling_rate=self.fs)
        
        # Calculate heartbeat statistics
        beat_stats = {
            'n_beats': len(heartbeats),
            'mean_beat': None,
            'std_beat': None
        }
        
        if heartbeats:
            # Stack all beats for analysis
            beat_signals = [beat['Signal'].values for beat in heartbeats.values()]
            
            # Find minimum length to align
            min_len = min(len(b) for b in beat_signals)
            beat_matrix = np.array([b[:min_len] for b in beat_signals])
            
            beat_stats['mean_beat'] = np.mean(beat_matrix, axis=0)
            beat_stats['std_beat'] = np.std(beat_matrix, axis=0)
            beat_stats['beat_matrix'] = beat_matrix
        
        return beat_stats
    
    def analyze_event_related(self, ecg_signal: np.ndarray, 
                             events: List[int]) -> pd.DataFrame:
        """
        Analyze ECG in response to specific events (event-related analysis).
        
        Useful for analyzing physiological responses to stimuli, treatments, etc.
        
        Args:
            ecg_signal: ECG signal
            events: List of event timestamps (in samples)
            
        Returns:
            DataFrame with event-related metrics
        """
        # Process ECG
        signals, info = nk.ecg_process(ecg_signal, sampling_rate=self.fs)
        
        # Create epochs around events
        epochs = nk.epochs_create(signals, events, sampling_rate=self.fs,
                                 epochs_start=-1.0, epochs_end=4.0)
        
        # Analyze each epoch
        event_metrics = nk.bio_analyze(epochs, sampling_rate=self.fs)
        
        return event_metrics
    
    def analyze_interval_related(self, ecg_signal: np.ndarray) -> pd.DataFrame:
        """
        Analyze ECG over entire recording (interval-related analysis).
        
        Calculates aggregate metrics over the full signal duration.
        
        Args:
            ecg_signal: ECG signal
            
        Returns:
            DataFrame with interval-related metrics
        """
        # Process ECG
        signals, info = nk.ecg_process(ecg_signal, sampling_rate=self.fs)
        
        # Analyze full recording
        metrics = nk.ecg_analyze(signals, sampling_rate=self.fs)
        
        return metrics
    
    def generate_report(self, ecg_signal: np.ndarray, 
                       patient_info: Optional[Dict] = None,
                       save_path: Optional[str] = None) -> Dict:
        """
        Generate comprehensive ECG analysis report.
        
        Args:
            ecg_signal: ECG signal
            patient_info: Optional patient metadata
            save_path: Optional path to save report
            
        Returns:
            Dictionary containing all analysis results
        """
        report = {
            'patient_info': patient_info or {},
            'signal_info': {
                'sampling_rate': self.fs,
                'duration': len(ecg_signal) / self.fs,
                'species': self.species
            }
        }
        
        # Process ECG
        print("Processing ECG signal...")
        signals, info = nk.ecg_process(ecg_signal, sampling_rate=self.fs)
        report['processing_info'] = info
        
        # Quality assessment
        print("Assessing signal quality...")
        report['quality'] = self.assess_signal_quality(ecg_signal)
        
        # HRV analysis
        print("Extracting HRV features...")
        report['hrv'] = self.extract_hrv_comprehensive(ecg_signal)
        
        # Delineation
        print("Delineating ECG waves...")
        _, waves = self.delineate_waves(ecg_signal)
        report['waves'] = waves
        
        # Interval analysis
        print("Performing interval analysis...")
        report['interval_metrics'] = self.analyze_interval_related(ecg_signal)
        
        # Summary statistics
        report['summary'] = {
            'mean_hr': np.mean(signals['ECG_Rate'].dropna()),
            'hr_variability': np.std(signals['ECG_Rate'].dropna()),
            'n_beats': len(info['ECG_R_Peaks']),
            'recording_quality': 'Good' if report['quality']['quality_score'] > 0.7 else 'Fair'
        }
        
        print("\n=== ECG Analysis Report ===")
        print(f"Species: {self.species}")
        print(f"Duration: {report['signal_info']['duration']:.2f} seconds")
        print(f"Mean HR: {report['summary']['mean_hr']:.1f} bpm")
        print(f"HR Variability (SD): {report['summary']['hr_variability']:.1f} bpm")
        print(f"Total Beats: {report['summary']['n_beats']}")
        print(f"Quality: {report['summary']['recording_quality']}")
        
        if save_path:
            import json
            # Convert DataFrame to dict for JSON serialization
            report_serializable = {
                k: v.to_dict() if isinstance(v, pd.DataFrame) else v
                for k, v in report.items()
            }
            with open(save_path, 'w') as f:
                json.dump(report_serializable, f, indent=2, default=str)
            print(f"\nReport saved to: {save_path}")
        
        return report
    
    def visualize_analysis(self, ecg_signal: np.ndarray, show: bool = True):
        """
        Create comprehensive visualization of ECG analysis.
        
        Args:
            ecg_signal: ECG signal
            show: Whether to display plots
        """
        # Process ECG
        signals, info = nk.ecg_process(ecg_signal, sampling_rate=self.fs)
        
        # Plot ECG with detected features
        nk.ecg_plot(signals, info, sampling_rate=self.fs)
        
        if show:
            import matplotlib.pyplot as plt
            plt.show()


def compare_with_custom_preprocessor():
    """
    Compare NeuroKit2 with our custom ECGPreprocessor.
    
    Demonstrates when to use each approach.
    """
    print("\n=== NeuroKit2 vs Custom Preprocessor ===\n")
    
    print("Use NeuroKit2 when:")
    print("  ✓ Need quick prototyping and testing")
    print("  ✓ Want comprehensive HRV analysis with minimal code")
    print("  ✓ Need ECG simulation for synthetic data")
    print("  ✓ Require wave delineation (P, Q, S, T detection)")
    print("  ✓ Want to compare multiple peak detection algorithms")
    print("  ✓ Need event-related or interval-related analysis")
    
    print("\nUse Custom ECGPreprocessor when:")
    print("  ✓ Need fine-tuned control over filtering parameters")
    print("  ✓ Working with species-specific adaptations")
    print("  ✓ Require integration with existing PEMF sensor data")
    print("  ✓ Want to minimize dependencies")
    print("  ✓ Need optimized performance for real-time processing")
    
    print("\nRecommendation:")
    print("  → Use NeuroKit2 for initial analysis and validation")
    print("  → Use Custom Preprocessor for production PEMF system")
    print("  → Combine both for comprehensive research analysis")


def main():
    """
    Demonstrate NeuroKit2 integration.
    """
    if not NEUROKIT_AVAILABLE:
        print("NeuroKit2 not installed.")
        print("Install with: pip install neurokit2")
        return
    
    print("=== NeuroKit2 ECG Analysis Demo ===\n")
    
    # Generate synthetic dog ECG
    print("Generating synthetic dog ECG...")
    ecg = nk.ecg_simulate(duration=30, sampling_rate=250, heart_rate=100, noise=0.02)
    print(f"Signal length: {len(ecg)} samples ({len(ecg)/250:.1f} seconds)\n")
    
    # Initialize analyzer
    analyzer = NeuroKitECGAnalyzer(species='dog', sampling_rate=250)
    
    # Test 1: Complete processing
    print("Test 1: Complete ECG processing...")
    signals, info = analyzer.process_ecg_complete(ecg)
    print(f"  Detected {len(info['ECG_R_Peaks'])} R-peaks")
    print(f"  Mean HR: {signals['ECG_Rate'].mean():.1f} bpm\n")
    
    # Test 2: Compare peak detectors
    print("Test 2: Comparing R-peak detection methods...")
    peak_results = analyzer.compare_peak_detectors(ecg)
    print()
    
    # Test 3: HRV analysis
    print("Test 3: Comprehensive HRV analysis...")
    hrv = analyzer.extract_hrv_comprehensive(ecg)
    print(f"  HRV metrics extracted: {len(hrv.columns)} features")
    print(f"  RMSSD: {hrv['HRV_RMSSD'].values[0]:.2f} ms")
    print(f"  SDNN: {hrv['HRV_SDNN'].values[0]:.2f} ms\n")
    
    # Test 4: Signal quality
    print("Test 4: Signal quality assessment...")
    quality = analyzer.assess_signal_quality(ecg)
    for metric, value in quality.items():
        print(f"  {metric}: {value:.4f}")
    print()
    
    # Test 5: Generate full report
    print("Test 5: Generating comprehensive report...")
    report = analyzer.generate_report(ecg, patient_info={'name': 'Test Dog', 'breed': 'Labrador'})
    
    print("\n✓ All tests completed!")
    
    # Show comparison
    compare_with_custom_preprocessor()


if __name__ == "__main__":
    main()
