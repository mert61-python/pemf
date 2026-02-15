"""
Generate Synthetic Test Data for AI Models
==========================================

Creates realistic synthetic data for training and testing:
1. ECG signals with HRV features (for Autoencoder)
2. HRV + Sensor + Context features (for Predictor)
3. Time-series monitoring data (for Monitor)

Usage:
------
    python generate_test_data.py --output_dir data/test_data --n_samples 500

Data will be saved to:
    - ecg_signals.npy: ECG time series (n_samples, 2500)
    - hrv_features.csv: HRV metrics
    - predictor_features.csv: All input features for predictor
    - predictor_targets.csv: Target PEMF parameters
    - monitor_sequences.npy: Time sequences (n_sequences, seq_len, n_features)
    - monitor_labels.csv: Status labels
"""

import argparse
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Tuple
import sys

# Add parent directory
sys.path.insert(0, str(Path(__file__).parent))
from config import TRAINING


def generate_ecg_signal(
    duration: float = 10.0,
    sampling_rate: int = 250,
    heart_rate: float = 100.0,
    noise_level: float = 0.1
) -> np.ndarray:
    """
    Generate synthetic ECG signal.
    
    Args:
        duration: Signal duration in seconds
        sampling_rate: Samples per second
        heart_rate: Heart rate in BPM
        noise_level: Noise amplitude
        
    Returns:
        ECG signal array
    """
    n_samples = int(duration * sampling_rate)
    t = np.linspace(0, duration, n_samples)
    
    # Heart rate in Hz
    hr_hz = heart_rate / 60.0
    
    # Generate PQRST complex components
    # P wave
    p_wave = 0.15 * np.sin(2 * np.pi * hr_hz * t + 0)
    
    # QRS complex (dominant sharp peak)
    qrs_complex = 1.5 * np.sin(2 * np.pi * hr_hz * 5 * t) * np.exp(-5 * (t % (1/hr_hz) - 0.15)**2 / 0.01)
    
    # T wave
    t_wave = 0.3 * np.sin(2 * np.pi * hr_hz * t - np.pi/3)
    
    # Combine
    ecg = p_wave + qrs_complex + t_wave
    
    # Add baseline wander (respiration artifact)
    baseline = 0.05 * np.sin(2 * np.pi * 0.3 * t)
    
    # Add noise
    noise = noise_level * np.random.randn(n_samples)
    
    ecg_signal = ecg + baseline + noise
    
    # Normalize to [-1, 1]
    ecg_signal = (ecg_signal - ecg_signal.mean()) / (ecg_signal.std() + 1e-8)
    ecg_signal = np.clip(ecg_signal, -3, 3) / 3
    
    return ecg_signal


def generate_hrv_features(heart_rate: float, stress_level: float = 0.5) -> dict:
    """
    Generate realistic HRV features based on heart rate and stress.
    
    Args:
        heart_rate: Heart rate in BPM
        stress_level: Stress level 0-1 (higher = more stressed)
        
    Returns:
        Dictionary of HRV features
    """
    # Time-domain features
    sdnn = 50 * (1 - stress_level) + np.random.randn() * 10  # ms
    rmssd = 40 * (1 - stress_level) + np.random.randn() * 8
    pnn50 = 20 * (1 - stress_level) + np.random.randn() * 5
    
    mean_hr = heart_rate + np.random.randn() * 5
    std_hr = 10 * (1 - stress_level) + np.random.randn() * 3
    
    # Frequency-domain features
    vlf = 100 + np.random.randn() * 30
    lf = 200 * (1 + stress_level) + np.random.randn() * 50
    hf = 400 * (1 - stress_level) + np.random.randn() * 80
    lf_hf = lf / (hf + 1e-8)
    
    # Nonlinear features
    sd1 = rmssd / np.sqrt(2)
    sd2 = np.sqrt(2 * sdnn**2 - 0.5 * rmssd**2)
    
    sample_entropy = 1.5 - stress_level + np.random.randn() * 0.3
    approximate_entropy = 1.2 - stress_level * 0.5 + np.random.randn() * 0.2
    
    # DFA (Detrended Fluctuation Analysis)
    alpha1 = 1.0 + np.random.randn() * 0.2
    alpha2 = 1.0 + np.random.randn() * 0.15
    
    return {
        'SDNN': max(0, sdnn),
        'RMSSD': max(0, rmssd),
        'pNN50': max(0, min(100, pnn50)),
        'mean_hr': max(40, min(200, mean_hr)),
        'std_hr': max(0, std_hr),
        'VLF': max(0, vlf),
        'LF': max(0, lf),
        'HF': max(0, hf),
        'LF_HF': max(0, lf_hf),
        'SD1': max(0, sd1),
        'SD2': max(0, sd2),
        'sample_entropy': max(0, sample_entropy),
        'approximate_entropy': max(0, approximate_entropy),
        'alpha1': max(0, alpha1),
        'alpha2': max(0, alpha2)
    }


def generate_predictor_data(n_samples: int = 500) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Generate training data for PEMF Predictor.
    
    Returns:
        (features_df, targets_df)
    """
    species_list = ['dog', 'cat', 'rabbit', 'mouse']
    
    features_list = []
    targets_list = []
    
    for _ in range(n_samples):
        # Random species and parameters
        species = np.random.choice(species_list)
        age = np.random.uniform(1, 15)
        weight = np.random.uniform(1, 50)
        
        # Baseline heart rate depends on species
        if species == 'dog':
            base_hr = np.random.uniform(70, 120)
        elif species == 'cat':
            base_hr = np.random.uniform(140, 220)
        elif species == 'rabbit':
            base_hr = np.random.uniform(180, 250)
        else:  # mouse
            base_hr = np.random.uniform(450, 650)
        
        stress_level = np.random.uniform(0.2, 0.8)
        
        # Generate HRV features
        hrv = generate_hrv_features(base_hr, stress_level)
        
        # PEMF sensor data (simulate previous treatment effects)
        magnetic_field = np.random.uniform(5, 25, 5)
        temperature = np.random.uniform(20, 40, 5)
        current = np.random.uniform(1, 4, 5)
        
        # Context
        prev_frequency = np.random.uniform(5, 50)
        prev_intensity = np.random.uniform(10, 80)
        days_since = np.random.randint(1, 30)
        n_prev_treatments = np.random.randint(0, 20)
        condition_severity = np.random.uniform(0.2, 0.9)
        treatment_effectiveness = np.random.uniform(0.3, 0.9)
        pain_score = condition_severity * 0.7 + np.random.uniform(0, 0.2)
        activity_level = 1 - pain_score + np.random.uniform(-0.2, 0.2)
        
        # Create feature row (45 features)
        features = list(hrv.values())  # 15 HRV features
        
        # Sensor stats (15 features)
        for sensor_data in [magnetic_field, temperature, current]:
            features.extend([
                np.mean(sensor_data),
                np.std(sensor_data),
                np.max(sensor_data),
                np.min(sensor_data),
                np.percentile(sensor_data, 75) - np.percentile(sensor_data, 25)
            ])
        
        # Context (15 features: 4 species + 11 others)
        species_encoding = [1 if species == s else 0 for s in species_list]
        features.extend(species_encoding)
        features.extend([
            age / 20.0,
            weight / 50.0,
            prev_frequency / 100.0,
            prev_intensity / 100.0,
            days_since / 30.0,
            n_prev_treatments / 10.0,
            condition_severity,
            treatment_effectiveness,
            pain_score,
            activity_level,
            stress_level
        ])
        
        features_list.append(features)
        
        # Generate target PEMF parameters based on features
        # Lower stress/pain → lower frequency/intensity
        target_freq = 10 + (1 - stress_level) * 30 + np.random.randn() * 5
        target_duration = 20 + condition_severity * 20 + np.random.randn() * 5
        
        # Intensity profile (8 coils)
        base_intensity = 30 + (1 - pain_score) * 30
        intensities = [base_intensity + np.random.randn() * 5 for _ in range(8)]
        
        # Confidence (higher for typical cases)
        confidence = 0.7 + (1 - abs(stress_level - 0.5) * 2) * 0.2
        
        targets = [target_freq] + intensities + [target_duration, confidence]
        targets_list.append(targets)
    
    # Create DataFrames
    feature_cols = (
        list(generate_hrv_features(100).keys()) +
        [f'{sensor}_{stat}' for sensor in ['mag_field', 'temp', 'current'] 
         for stat in ['mean', 'std', 'max', 'min', 'iqr']] +
        [f'species_{s}' for s in species_list] +
        ['age_norm', 'weight_norm', 'prev_freq_norm', 'prev_int_norm',
         'days_since_norm', 'n_prev_norm', 'condition_severity',
         'treatment_effectiveness', 'pain_score', 'activity_level', 'stress_level']
    )
    
    target_cols = ['frequency'] + [f'intensity_{i}' for i in range(8)] + ['duration', 'confidence']
    
    features_df = pd.DataFrame(features_list, columns=feature_cols)
    targets_df = pd.DataFrame(targets_list, columns=target_cols)
    
    return features_df, targets_df


def generate_monitor_data(n_sequences: int = 200, seq_length: int = 30) -> Tuple[np.ndarray, pd.DataFrame]:
    """
    Generate time-series monitoring data.
    
    Returns:
        (sequences array, labels dataframe)
    """
    sequences = []
    labels = []
    
    for _ in range(n_sequences):
        # Random initial state
        base_hr = np.random.uniform(80, 150)
        base_hrv = np.random.uniform(30, 70)
        base_temp = np.random.uniform(25, 30)
        base_current = np.random.uniform(1.5, 2.5)
        base_field = np.random.uniform(10, 15)
        
        # Random trend (normal, warning, or critical)
        status = np.random.choice(['normal', 'warning', 'critical'], p=[0.6, 0.3, 0.1])
        
        sequence = []
        
        for t in range(seq_length):
            # Time-dependent changes
            if status == 'normal':
                hr_change = np.random.randn() * 2
                hrv_change = np.random.randn() * 2
                temp_change = t * 0.1 + np.random.randn() * 0.3
                field_drift = np.random.randn() * 0.5
            elif status == 'warning':
                hr_change = t * 0.5 + np.random.randn() * 3
                hrv_change = -t * 0.3 + np.random.randn() * 2
                temp_change = t * 0.3 + np.random.randn() * 0.5
                field_drift = t * 0.1 + np.random.randn() * 1
            else:  # critical
                hr_change = t * 1.0 + np.random.randn() * 5
                hrv_change = -t * 0.6 + np.random.randn() * 3
                temp_change = t * 0.5 + np.random.randn() * 1
                field_drift = t * 0.2 + np.random.randn() * 2
            
            # Current values
            hr = base_hr + hr_change
            hrv = max(10, base_hrv + hrv_change)
            temp = base_temp + temp_change
            current = base_current + np.random.randn() * 0.2
            field = base_field + field_drift
            
            # Feature vector (20 features)
            features = [
                hr / 150.0,  # Normalized HR
                hrv / 100.0,  # Normalized HRV
                (hr - base_hr) / 50.0,  # HR change
                (hrv - base_hrv) / 50.0,  # HRV change
                temp / 40.0,  # Normalized temp
                (temp - base_temp) / 20.0,  # Temp change
                current / 4.0,  # Normalized current
                field / 25.0,  # Normalized field
                (field - base_field) / 10.0,  # Field drift
                t / seq_length,  # Time progress
                np.random.rand(),  # Frequency (placeholder)
                np.random.rand(),  # Intensity (placeholder)
            ]
            # Additional features (8 more to reach 20)
            features.extend([np.random.rand() for _ in range(8)])
            
            sequence.append(features)
        
        sequences.append(sequence)
        
        # Label
        if status == 'normal':
            label = {'status': 0, 'status_name': 'Normal'}
        elif status == 'warning':
            label = {'status': 1, 'status_name': 'Warning'}
        else:
            label = {'status': 2, 'status_name': 'Critical'}
        
        labels.append(label)
    
    sequences = np.array(sequences, dtype=np.float32)
    labels_df = pd.DataFrame(labels)
    
    return sequences, labels_df


def main():
    parser = argparse.ArgumentParser(description='Generate synthetic test data for AI models')
    parser.add_argument('--output_dir', type=str, default='data/test_data',
                       help='Output directory for generated data')
    parser.add_argument('--n_ecg', type=int, default=500,
                       help='Number of ECG signals to generate')
    parser.add_argument('--n_predictor', type=int, default=500,
                       help='Number of predictor samples to generate')
    parser.add_argument('--n_monitor', type=int, default=200,
                       help='Number of monitor sequences to generate')
    
    args = parser.parse_args()
    
    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("="*60)
    print("Generating Synthetic Test Data")
    print("="*60)
    
    # 1. Generate ECG signals
    print(f"\n1. Generating {args.n_ecg} ECG signals...")
    ecg_signals = []
    hrv_features_list = []
    
    for i in range(args.n_ecg):
        if (i + 1) % 100 == 0:
            print(f"   Progress: {i+1}/{args.n_ecg}")
        
        # Random parameters
        hr = np.random.uniform(60, 180)
        stress = np.random.uniform(0.2, 0.8)
        noise = np.random.uniform(0.05, 0.15)
        
        # Generate signal
        ecg = generate_ecg_signal(duration=10.0, heart_rate=hr, noise_level=noise)
        ecg_signals.append(ecg)
        
        # Generate corresponding HRV features
        hrv = generate_hrv_features(hr, stress)
        hrv_features_list.append(hrv)
    
    ecg_signals = np.array(ecg_signals, dtype=np.float32)
    hrv_df = pd.DataFrame(hrv_features_list)
    
    # Save
    np.save(output_dir / 'ecg_signals.npy', ecg_signals)
    hrv_df.to_csv(output_dir / 'hrv_features.csv', index=False)
    print(f"   ✓ Saved: ecg_signals.npy {ecg_signals.shape}")
    print(f"   ✓ Saved: hrv_features.csv {hrv_df.shape}")
    
    # 2. Generate predictor data
    print(f"\n2. Generating {args.n_predictor} predictor samples...")
    features_df, targets_df = generate_predictor_data(args.n_predictor)
    
    features_df.to_csv(output_dir / 'predictor_features.csv', index=False)
    targets_df.to_csv(output_dir / 'predictor_targets.csv', index=False)
    print(f"   ✓ Saved: predictor_features.csv {features_df.shape}")
    print(f"   ✓ Saved: predictor_targets.csv {targets_df.shape}")
    
    # 3. Generate monitor data
    print(f"\n3. Generating {args.n_monitor} monitor sequences...")
    sequences, labels_df = generate_monitor_data(args.n_monitor, seq_length=30)
    
    np.save(output_dir / 'monitor_sequences.npy', sequences)
    labels_df.to_csv(output_dir / 'monitor_labels.csv', index=False)
    print(f"   ✓ Saved: monitor_sequences.npy {sequences.shape}")
    print(f"   ✓ Saved: monitor_labels.csv {labels_df.shape}")
    
    # Summary
    print("\n" + "="*60)
    print("Data Generation Complete")
    print("="*60)
    print(f"Output directory: {output_dir.absolute()}")
    print(f"\nFiles created:")
    for file in output_dir.glob('*'):
        print(f"  - {file.name}")
    print("="*60)


if __name__ == "__main__":
    main()
