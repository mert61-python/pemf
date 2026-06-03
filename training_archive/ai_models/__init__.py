"""
Models Module - Neural network architectures
============================================

This module contains:
- ECG Autoencoder for baseline establishment
- PEMF Effect Predictor for treatment recommendations
- Realtime Monitor for anomaly detection

Architectures:
--------------
- autoencoder: Variational Autoencoder for ECG pattern learning
- predictor: Multi-layer perceptron for treatment parameter prediction
- monitor: LSTM-based real-time anomaly detection
- base_model: Common base classes and utilities
"""

from .base_model import BaseModel, EarlyStopping
from .autoencoder import (
    ECGEncoder,
    ECGDecoder,
    ECGAutoencoder
)
from .predictor import (
    ResidualBlock,
    PEMFPredictor,
    EnsemblePredictor,
    prepare_input_features
)
from .monitor import (
    RealtimeMonitor,
    RollingMonitor,
    extract_monitoring_features
)

__all__ = [
    # Base utilities
    'BaseModel',
    'EarlyStopping',
    
    # Autoencoder
    'ECGEncoder',
    'ECGDecoder',
    'ECGAutoencoder',
    
    # Predictor
    'ResidualBlock',
    'PEMFPredictor',
    'EnsemblePredictor',
    'prepare_input_features',
    
    # Monitor
    'RealtimeMonitor',
    'RollingMonitor',
    'extract_monitoring_features'
]
