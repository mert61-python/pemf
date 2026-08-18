"""
Data Module - Dataset management and preprocessing
==================================================

This module handles:
- Downloading ECG datasets (PhysioZoo, Zenodo, MIT-BIH)
- Signal preprocessing and filtering
- Feature extraction (HRV, ECG morphology)
- Data augmentation and balancing
- Synthetic data generation using GANs and parametric models

Components:
-----------
- downloader: Dataset acquisition from PhysioNet and Zenodo
- preprocessor: Signal processing and feature extraction
- synthetic_generator: GAN-based and parametric ECG synthesis
- augmentor: Data augmentation techniques (TODO)
- loader: DataLoader implementations for PyTorch (TODO)

External Tools Integration:
---------------------------
- NeuroKit2: Advanced biosignal processing (2000+ GitHub stars)
  GitHub: https://github.com/neuropsychology/NeuroKit
  Features: ECG simulation, HRV analysis, wave delineation
  
- PhysioZoo MHRV: MATLAB toolbox for HRV analysis
  GitHub: https://github.com/physiozoo/mhrv
  Features: Animal ECG support, comprehensive HRV metrics
  
- P2E-WGAN: PPG to ECG reconstruction
  GitHub: https://github.com/khuongav/P2E-WGAN-ecg-ppg-reconstruction
  
- EEG-WGAN: Biosignal synthesis with WGAN-GP
  GitHub: https://github.com/JoshParkSJ/eeg-wgan
"""

from .downloader import DatasetDownloader
from .preprocessor import ECGPreprocessor
from .synthetic_generator import SyntheticECGGenerator, WGAN_ECG_Generator

__all__ = [
    "DatasetDownloader", 
    "ECGPreprocessor",
    "SyntheticECGGenerator",
    "WGAN_ECG_Generator"
]
