"""
Training Module - Complete training pipeline
============================================

This module provides:
- Unified Trainer for all model types
- Dataset and DataLoader implementations
- Training configuration management
- Hyperparameter optimization with Optuna
- Training examples and utilities

Components:
-----------
- trainer: Main training loop with AMP, gradient accumulation, early stopping
- datasets: ECGDataset, PEMFPredictorDataset, MonitoringDataset
- config: TrainingConfig with optimizer/scheduler creation
- hyperparameter_search: Optuna-based hyperparameter optimization

Quick Start:
------------
    from ai.training import Trainer, TrainingConfig, ECGDataset, create_data_loaders
    
    # Setup
    config = TrainingConfig(model_type='autoencoder')
    dataset = ECGDataset(data_dir='data/')
    train_loader, val_loader, test_loader = create_data_loaders(dataset)
    
    # Train
    model = ECGAutoencoder()
    optimizer = config.get_optimizer(model)
    trainer = Trainer(model, optimizer)
    trainer.train(train_loader, val_loader, epochs=100, save_dir='checkpoints/')
"""

from .trainer import Trainer
from .datasets import (
    ECGDataset,
    PEMFPredictorDataset,
    MonitoringDataset,
    create_data_loaders
)
from .config import (
    TrainingConfig,
    get_default_config
)
from .hyperparameter_search import (
    HyperparameterOptimizer,
    suggest_autoencoder_params,
    suggest_predictor_params,
    suggest_monitor_params
)

__all__ = [
    # Trainer
    'Trainer',
    
    # Datasets
    'ECGDataset',
    'PEMFPredictorDataset',
    'MonitoringDataset',
    'create_data_loaders',
    
    # Configuration
    'TrainingConfig',
    'get_default_config',
    
    # Hyperparameter optimization
    'HyperparameterOptimizer',
    'suggest_autoencoder_params',
    'suggest_predictor_params',
    'suggest_monitor_params'
]
