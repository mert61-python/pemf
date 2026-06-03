"""
Dataset Classes for Training
=============================

PyTorch Dataset implementations for:
1. ECG signals from PhysioZoo, MIT-BIH, Zenodo
2. HRV features extracted from ECG
3. PEMF sensor data (magnetic field, temperature, current)
4. Treatment parameters and outcomes

Supports:
---------
- Data loading from multiple sources
- Normalization and standardization
- Data augmentation (noise, scaling, shifting)
- Train/val/test splitting
- Caching for faster loading

Usage:
------
    # ECG Autoencoder dataset
    dataset = ECGDataset(
        data_dir='data/physioZoo/',
        species='dog',
        signal_length=2500
    )
    
    # PEMF Predictor dataset
    dataset = PEMFPredictorDataset(
        ecg_features_file='features.csv',
        treatment_labels_file='labels.csv'
    )
    
    # Realtime Monitor dataset
    dataset = MonitoringDataset(
        sequences_dir='data/sequences/',
        sequence_length=30
    )
"""

import torch
from torch.utils.data import Dataset, DataLoader, random_split
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, List, Tuple, Union

import sys
sys.path.append(str(Path(__file__).parent.parent))
# Import from parent config
import config as parent_config
SIGNAL_PROCESSING = parent_config.SIGNAL_PROCESSING
HRV_FEATURES = parent_config.HRV_FEATURES
SPECIES_PARAMS = parent_config.SPECIES_PARAMS


class ECGDataset(Dataset):
    """
    Dataset for ECG Autoencoder training.
    
    Loads raw ECG signals for unsupervised baseline learning.
    """
    
    def __init__(self,
                 data_dir: Union[str, Path],
                 species: str = 'dog',
                 signal_length: int = 2500,
                 sampling_rate: int = 250,
                 normalize: bool = True,
                 augment: bool = False,
                 cache: bool = True):
        """
        Initialize ECG dataset.
        
        Args:
            data_dir: Directory containing ECG files
            species: Animal species
            signal_length: Expected signal length (samples)
            sampling_rate: Sampling rate (Hz)
            normalize: Normalize signals to [-1, 1]
            augment: Apply data augmentation
            cache: Cache preprocessed signals
        """
        self.data_dir = Path(data_dir)
        self.species = species
        self.signal_length = signal_length
        self.sampling_rate = sampling_rate
        self.normalize = normalize
        self.augment = augment
        
        # Load file paths
        self.ecg_files = self._load_file_list()
        
        # Cache
        self.cache = cache
        self.cached_data = {} if cache else None
        
        print(f"✓ ECGDataset initialized: {len(self.ecg_files)} samples")
    
    def _load_file_list(self) -> List[Path]:
        """Load list of ECG files."""
        extensions = ['.npy', '.npz', '.mat', '.csv']
        files = []
        
        for ext in extensions:
            files.extend(list(self.data_dir.glob(f"**/*{ext}")))
        
        return files
    
    def _load_ecg_signal(self, filepath: Path) -> np.ndarray:
        """
        Load ECG signal from file.
        
        Args:
            filepath: Path to ECG file
            
        Returns:
            ECG signal array
        """
        ext = filepath.suffix
        
        if ext == '.npy':
            signal = np.load(filepath)
        elif ext == '.npz':
            data = np.load(filepath)
            signal = data['ecg'] if 'ecg' in data else data[data.files[0]]
        elif ext == '.csv':
            df = pd.read_csv(filepath)
            signal = df.values.flatten() if len(df.columns) == 1 else df.iloc[:, 0].values
        elif ext == '.mat':
            try:
                from scipy.io import loadmat
                mat = loadmat(filepath)
                # Try common field names
                for key in ['ecg', 'signal', 'data', 'val']:
                    if key in mat:
                        signal = mat[key].flatten()
                        break
                else:
                    # Use first non-metadata field
                    signal = list(mat.values())[0].flatten()
            except:
                raise ValueError(f"Failed to load .mat file: {filepath}")
        else:
            raise ValueError(f"Unsupported file type: {ext}")
        
        return signal
    
    def _preprocess_signal(self, signal: np.ndarray) -> np.ndarray:
        """
        Preprocess ECG signal.
        
        Args:
            signal: Raw ECG signal
            
        Returns:
            Preprocessed signal
        """
        # Resample or pad to target length
        if len(signal) > self.signal_length:
            # Take center segment
            start = (len(signal) - self.signal_length) // 2
            signal = signal[start:start + self.signal_length]
        elif len(signal) < self.signal_length:
            # Zero-pad
            pad_width = self.signal_length - len(signal)
            signal = np.pad(signal, (pad_width // 2, pad_width - pad_width // 2), mode='constant')
        
        # Normalize to [-1, 1]
        if self.normalize:
            signal = signal - np.mean(signal)
            max_val = np.max(np.abs(signal))
            if max_val > 0:
                signal = signal / max_val
        
        return signal
    
    def _augment_signal(self, signal: np.ndarray) -> np.ndarray:
        """
        Apply data augmentation.
        
        Args:
            signal: ECG signal
            
        Returns:
            Augmented signal
        """
        # Random amplitude scaling (0.8-1.2x)
        if np.random.rand() < 0.5:
            scale = np.random.uniform(0.8, 1.2)
            signal = signal * scale
        
        # Random noise (SNR = 20-40 dB)
        if np.random.rand() < 0.5:
            snr_db = np.random.uniform(20, 40)
            signal_power = np.mean(signal ** 2)
            noise_power = signal_power / (10 ** (snr_db / 10))
            noise = np.random.normal(0, np.sqrt(noise_power), signal.shape)
            signal = signal + noise
        
        # Random baseline wander
        if np.random.rand() < 0.3:
            wander_freq = np.random.uniform(0.1, 0.5)
            t = np.arange(len(signal)) / self.sampling_rate
            wander = 0.1 * np.sin(2 * np.pi * wander_freq * t)
            signal = signal + wander
        
        return signal
    
    def __len__(self) -> int:
        return len(self.ecg_files)
    
    def __getitem__(self, idx: int) -> torch.Tensor:
        """
        Get ECG signal.
        
        Args:
            idx: Sample index
            
        Returns:
            ECG tensor (1, signal_length)
        """
        # Check cache
        if self.cache and idx in self.cached_data:
            signal = self.cached_data[idx]
        else:
            # Load and preprocess
            filepath = self.ecg_files[idx]
            signal = self._load_ecg_signal(filepath)
            signal = self._preprocess_signal(signal)
            
            # Cache
            if self.cache:
                self.cached_data[idx] = signal
        
        # Augmentation (only during training)
        if self.augment:
            signal = self._augment_signal(signal.copy())
        
        # Convert to tensor
        signal_tensor = torch.FloatTensor(signal).unsqueeze(0)  # (1, signal_length)
        
        return signal_tensor


class PEMFPredictorDataset(Dataset):
    """
    Dataset for PEMF Predictor training.
    
    Loads HRV features + context → PEMF treatment parameters.
    """
    
    def __init__(self,
                 features_file: Union[str, Path],
                 labels_file: Union[str, Path],
                 species: str = 'dog',
                 normalize: bool = True):
        """
        Initialize predictor dataset.
        
        Args:
            features_file: CSV with input features (45 columns)
            labels_file: CSV with treatment parameters (11 columns)
            species: Animal species
            normalize: Normalize features
        """
        self.features_file = Path(features_file)
        self.labels_file = Path(labels_file)
        self.species = species
        self.normalize = normalize
        
        # Load data
        self.features = pd.read_csv(features_file).values
        self.labels = pd.read_csv(labels_file).values
        
        assert len(self.features) == len(self.labels), "Features and labels must have same length"
        
        # Normalization parameters
        if self.normalize:
            self.feature_mean = self.features.mean(axis=0)
            self.feature_std = self.features.std(axis=0) + 1e-8
        
        print(f"✓ PEMFPredictorDataset initialized: {len(self.features)} samples")
    
    def __len__(self) -> int:
        return len(self.features)
    
    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Get feature-label pair.
        
        Args:
            idx: Sample index
            
        Returns:
            Tuple of (features, labels) tensors
        """
        features = self.features[idx]
        labels = self.labels[idx]
        
        # Normalize features
        if self.normalize:
            features = (features - self.feature_mean) / self.feature_std
        
        features_tensor = torch.FloatTensor(features)
        labels_tensor = torch.FloatTensor(labels)
        
        return features_tensor, labels_tensor


class MonitoringDataset(Dataset):
    """
    Dataset for Realtime Monitor training.
    
    Loads sequences of ECG + PEMF features → status labels.
    """
    
    def __init__(self,
                 sequences_dir: Union[str, Path],
                 sequence_length: int = 30,
                 input_features: int = 20):
        """
        Initialize monitoring dataset.
        
        Args:
            sequences_dir: Directory with sequence files
            sequence_length: Length of each sequence
            input_features: Number of input features
        """
        self.sequences_dir = Path(sequences_dir)
        self.sequence_length = sequence_length
        self.input_features = input_features
        
        # Load sequences
        self.sequence_files = list(self.sequences_dir.glob("*.npz"))
        
        print(f"✓ MonitoringDataset initialized: {len(self.sequence_files)} sequences")
    
    def __len__(self) -> int:
        return len(self.sequence_files)
    
    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        """
        Get monitoring sequence.
        
        Args:
            idx: Sample index
            
        Returns:
            Dictionary with sequence, status, anomaly_scores
        """
        filepath = self.sequence_files[idx]
        data = np.load(filepath)
        
        sequence = data['sequence']  # (sequence_length, input_features)
        status = data['status']  # scalar (0=Normal, 1=Warning, 2=Critical)
        
        # Optional anomaly scores
        if 'anomaly_scores' in data:
            anomaly_scores = data['anomaly_scores']  # (5,)
        else:
            anomaly_scores = np.zeros(5)
        
        return {
            'sequence': torch.FloatTensor(sequence),
            'status': torch.tensor(int(status), dtype=torch.long),
            'anomaly_scores': torch.FloatTensor(anomaly_scores)
        }


def create_data_loaders(dataset: Dataset,
                       train_ratio: float = 0.7,
                       val_ratio: float = 0.15,
                       batch_size: int = 32,
                       num_workers: int = 0,
                       shuffle: bool = True) -> Tuple[DataLoader, DataLoader, DataLoader]:
    """
    Create train/val/test data loaders with automatic splitting.
    
    Args:
        dataset: PyTorch dataset
        train_ratio: Training set ratio
        val_ratio: Validation set ratio
        batch_size: Batch size
        num_workers: Number of data loading workers
        shuffle: Shuffle training data
        
    Returns:
        Tuple of (train_loader, val_loader, test_loader)
    """
    total_size = len(dataset)
    train_size = int(train_ratio * total_size)
    val_size = int(val_ratio * total_size)
    test_size = total_size - train_size - val_size
    
    train_dataset, val_dataset, test_dataset = random_split(
        dataset, 
        [train_size, val_size, test_size],
        generator=torch.Generator().manual_seed(42)
    )
    
    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        num_workers=num_workers,
        pin_memory=True
    )
    
    val_loader = DataLoader(
        val_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=True
    )
    
    test_loader = DataLoader(
        test_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=True
    )
    
    print(f"✓ Data loaders created:")
    print(f"  Train: {len(train_dataset)} samples ({train_size // batch_size} batches)")
    print(f"  Val:   {len(val_dataset)} samples ({val_size // batch_size} batches)")
    print(f"  Test:  {len(test_dataset)} samples ({test_size // batch_size} batches)")
    
    return train_loader, val_loader, test_loader


def test_datasets():
    """
    Test dataset implementations.
    """
    print("=== Testing Datasets ===\n")
    
    # Create dummy data directory
    test_dir = Path("test_data")
    test_dir.mkdir(exist_ok=True)
    
    # Create dummy ECG files
    print("Test 1: ECGDataset...")
    for i in range(10):
        ecg = np.random.randn(2500)
        np.save(test_dir / f"ecg_{i}.npy", ecg)
    
    ecg_dataset = ECGDataset(
        data_dir=test_dir,
        signal_length=2500,
        augment=True
    )
    
    sample = ecg_dataset[0]
    print(f"  Sample shape: {sample.shape}")
    print(f"  Dataset size: {len(ecg_dataset)}")
    
    # Test predictor dataset
    print("\nTest 2: PEMFPredictorDataset...")
    features = np.random.randn(100, 45)
    labels = np.random.randn(100, 11)
    
    pd.DataFrame(features).to_csv(test_dir / "features.csv", index=False)
    pd.DataFrame(labels).to_csv(test_dir / "labels.csv", index=False)
    
    predictor_dataset = PEMFPredictorDataset(
        features_file=test_dir / "features.csv",
        labels_file=test_dir / "labels.csv"
    )
    
    features, labels = predictor_dataset[0]
    print(f"  Features shape: {features.shape}")
    print(f"  Labels shape: {labels.shape}")
    print(f"  Dataset size: {len(predictor_dataset)}")
    
    # Test monitoring dataset
    print("\nTest 3: MonitoringDataset...")
    sequences_dir = test_dir / "sequences"
    sequences_dir.mkdir(exist_ok=True)
    
    for i in range(10):
        sequence = np.random.randn(30, 20)
        status = np.random.randint(0, 3)
        anomaly_scores = np.random.rand(5)
        
        np.savez(
            sequences_dir / f"seq_{i}.npz",
            sequence=sequence,
            status=status,
            anomaly_scores=anomaly_scores
        )
    
    monitor_dataset = MonitoringDataset(
        sequences_dir=sequences_dir,
        sequence_length=30
    )
    
    sample_dict = monitor_dataset[0]
    print(f"  Sequence shape: {sample_dict['sequence'].shape}")
    print(f"  Status: {sample_dict['status'].item()}")
    print(f"  Dataset size: {len(monitor_dataset)}")
    
    # Test data loaders
    print("\nTest 4: Data loaders...")
    train_loader, val_loader, test_loader = create_data_loaders(
        ecg_dataset,
        batch_size=4,
        num_workers=0
    )
    
    batch = next(iter(train_loader))
    print(f"  Train batch shape: {batch.shape}")
    
    # Cleanup
    import shutil
    shutil.rmtree(test_dir)
    
    print("\n✓ All tests passed!")


if __name__ == "__main__":
    test_datasets()
