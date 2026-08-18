"""
Training Configuration Management
==================================

Centralized configuration for training experiments.

Provides:
---------
- Training hyperparameters (learning rate, batch size, epochs)
- Model-specific configurations
- Data augmentation settings
- Optimizer and scheduler configurations
- Experiment tracking metadata

Usage:
------
    config = TrainingConfig(
        model_type='autoencoder',
        batch_size=32,
        learning_rate=0.001,
        epochs=100
    )
    
    # Get optimizer
    optimizer = config.get_optimizer(model)
    
    # Get scheduler
    scheduler = config.get_scheduler(optimizer)
    
    # Save config
    config.save('config.json')
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional, Union
from dataclasses import dataclass, asdict
import torch
import torch.optim as optim

import sys
# Add both ai/ and gui/ to path
ai_dir = Path(__file__).parent.parent  # ai/
gui_dir = ai_dir.parent  # gui/
sys.path.insert(0, str(gui_dir))
sys.path.insert(0, str(ai_dir))

# Import from parent config
import config as parent_config
DEVICE = parent_config.DEVICE
MODELS = parent_config.MODELS
TRAINING = parent_config.TRAINING


@dataclass
class TrainingConfig:
    """
    Training configuration dataclass.
    """
    # Model settings
    model_type: str = 'autoencoder'  # 'autoencoder', 'predictor', 'monitor'
    
    # Training hyperparameters
    batch_size: int = 32
    learning_rate: float = 0.001
    epochs: int = 100
    weight_decay: float = 0.0001
    
    # Optimizer settings
    optimizer_type: str = 'adam'  # 'adam', 'adamw', 'sgd'
    beta1: float = 0.9
    beta2: float = 0.999
    momentum: float = 0.9  # for SGD
    
    # Scheduler settings
    scheduler_type: str = 'cosine'  # 'cosine', 'step', 'plateau', 'none'
    scheduler_patience: int = 5  # for ReduceLROnPlateau
    scheduler_factor: float = 0.5
    scheduler_step_size: int = 10  # for StepLR
    
    # Training features
    mixed_precision: bool = True
    gradient_accumulation_steps: int = 1
    max_grad_norm: float = 1.0
    
    # Early stopping
    early_stopping: bool = True
    early_stopping_patience: int = 10
    early_stopping_min_delta: float = 0.0001
    
    # Data settings
    train_ratio: float = 0.7
    val_ratio: float = 0.15
    num_workers: int = 0
    pin_memory: bool = True
    
    # Data augmentation
    augment_data: bool = True
    augment_noise_level: float = 0.05
    augment_scale_range: tuple = (0.8, 1.2)
    
    # Regularization
    dropout: float = 0.1
    label_smoothing: float = 0.0
    
    # Checkpointing
    save_every: int = 5
    keep_best_only: bool = False
    
    # Device
    device: str = str(DEVICE)
    
    # Random seed
    seed: int = 42
    
    # Experiment metadata
    experiment_name: str = 'experiment'
    description: str = ''
    tags: list = None
    
    def __post_init__(self):
        """Validate configuration."""
        if self.tags is None:
            self.tags = []
        
        # Validate model type
        valid_models = ['autoencoder', 'predictor', 'monitor']
        if self.model_type not in valid_models:
            raise ValueError(f"model_type must be one of {valid_models}")
        
        # Validate optimizer
        valid_optimizers = ['adam', 'adamw', 'sgd']
        if self.optimizer_type not in valid_optimizers:
            raise ValueError(f"optimizer_type must be one of {valid_optimizers}")
        
        # Validate scheduler
        valid_schedulers = ['cosine', 'step', 'plateau', 'none']
        if self.scheduler_type not in valid_schedulers:
            raise ValueError(f"scheduler_type must be one of {valid_schedulers}")
        
        # Set mixed precision based on device
        if 'cpu' in self.device.lower():
            self.mixed_precision = False
    
    def get_optimizer(self, model: torch.nn.Module) -> torch.optim.Optimizer:
        """
        Create optimizer from configuration.
        
        Args:
            model: PyTorch model
            
        Returns:
            Optimizer instance
        """
        if self.optimizer_type == 'adam':
            optimizer = optim.Adam(
                model.parameters(),
                lr=self.learning_rate,
                betas=(self.beta1, self.beta2),
                weight_decay=self.weight_decay
            )
        elif self.optimizer_type == 'adamw':
            optimizer = optim.AdamW(
                model.parameters(),
                lr=self.learning_rate,
                betas=(self.beta1, self.beta2),
                weight_decay=self.weight_decay
            )
        elif self.optimizer_type == 'sgd':
            optimizer = optim.SGD(
                model.parameters(),
                lr=self.learning_rate,
                momentum=self.momentum,
                weight_decay=self.weight_decay
            )
        else:
            raise ValueError(f"Unknown optimizer type: {self.optimizer_type}")
        
        return optimizer
    
    def get_scheduler(self, optimizer: torch.optim.Optimizer) -> Optional[Any]:
        """
        Create learning rate scheduler from configuration.
        
        Args:
            optimizer: Optimizer instance
            
        Returns:
            Scheduler instance or None
        """
        if self.scheduler_type == 'none':
            return None
        
        if self.scheduler_type == 'cosine':
            scheduler = optim.lr_scheduler.CosineAnnealingLR(
                optimizer,
                T_max=self.epochs
            )
        elif self.scheduler_type == 'step':
            scheduler = optim.lr_scheduler.StepLR(
                optimizer,
                step_size=self.scheduler_step_size,
                gamma=self.scheduler_factor
            )
        elif self.scheduler_type == 'plateau':
            scheduler = optim.lr_scheduler.ReduceLROnPlateau(
                optimizer,
                mode='min',
                patience=self.scheduler_patience,
                factor=self.scheduler_factor
            )
        else:
            raise ValueError(f"Unknown scheduler type: {self.scheduler_type}")
        
        return scheduler
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert config to dictionary.
        
        Returns:
            Configuration dictionary
        """
        return asdict(self)
    
    def save(self, filepath: Union[str, Path]):
        """
        Save configuration to JSON file.
        
        Args:
            filepath: Path to save configuration
        """
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
        
        print(f"✓ Configuration saved: {filepath}")
    
    @classmethod
    def load(cls, filepath: Union[str, Path]) -> 'TrainingConfig':
        """
        Load configuration from JSON file.
        
        Args:
            filepath: Path to configuration file
            
        Returns:
            TrainingConfig instance
        """
        filepath = Path(filepath)
        
        with open(filepath, 'r') as f:
            config_dict = json.load(f)
        
        # Convert tuple strings back to tuples
        if 'augment_scale_range' in config_dict and isinstance(config_dict['augment_scale_range'], list):
            config_dict['augment_scale_range'] = tuple(config_dict['augment_scale_range'])
        
        config = cls(**config_dict)
        print(f"✓ Configuration loaded: {filepath}")
        
        return config


def get_default_config(model_type: str) -> TrainingConfig:
    """
    Get default training configuration for model type.
    
    Args:
        model_type: 'autoencoder', 'predictor', or 'monitor'
        
    Returns:
        TrainingConfig with defaults
    """
    if model_type == 'autoencoder':
        return TrainingConfig(
            model_type='autoencoder',
            batch_size=32,
            learning_rate=0.001,
            epochs=100,
            optimizer_type='adam',
            scheduler_type='cosine',
            early_stopping_patience=15,
            augment_data=True,
            experiment_name='ecg_autoencoder'
        )
    
    elif model_type == 'predictor':
        return TrainingConfig(
            model_type='predictor',
            batch_size=64,
            learning_rate=0.0005,
            epochs=150,
            optimizer_type='adamw',
            scheduler_type='plateau',
            early_stopping_patience=20,
            dropout=0.2,
            weight_decay=0.001,
            experiment_name='pemf_predictor'
        )
    
    elif model_type == 'monitor':
        return TrainingConfig(
            model_type='monitor',
            batch_size=32,
            learning_rate=0.0005,
            epochs=100,
            optimizer_type='adam',
            scheduler_type='step',
            scheduler_step_size=20,
            early_stopping_patience=15,
            dropout=0.3,
            experiment_name='realtime_monitor'
        )
    
    else:
        raise ValueError(f"Unknown model type: {model_type}")


def test_training_config():
    """
    Test training configuration.
    """
    print("=== Testing Training Configuration ===\n")
    
    # Test default configs
    print("Test 1: Default configurations...")
    for model_type in ['autoencoder', 'predictor', 'monitor']:
        config = get_default_config(model_type)
        print(f"  {model_type}: LR={config.learning_rate}, epochs={config.epochs}")
    
    # Test custom config
    print("\nTest 2: Custom configuration...")
    config = TrainingConfig(
        model_type='autoencoder',
        batch_size=16,
        learning_rate=0.01,
        epochs=50,
        experiment_name='test_experiment',
        tags=['test', 'custom']
    )
    print(f"  Batch size: {config.batch_size}")
    print(f"  Learning rate: {config.learning_rate}")
    print(f"  Epochs: {config.epochs}")
    
    # Test optimizer creation
    print("\nTest 3: Optimizer creation...")
    model = torch.nn.Linear(10, 5)
    optimizer = config.get_optimizer(model)
    print(f"  Optimizer: {optimizer.__class__.__name__}")
    print(f"  Learning rate: {optimizer.param_groups[0]['lr']}")
    
    # Test scheduler creation
    print("\nTest 4: Scheduler creation...")
    scheduler = config.get_scheduler(optimizer)
    if scheduler:
        print(f"  Scheduler: {scheduler.__class__.__name__}")
    else:
        print(f"  No scheduler")
    
    # Test save/load
    print("\nTest 5: Save and load...")
    test_path = Path("test_config.json")
    config.save(test_path)
    
    loaded_config = TrainingConfig.load(test_path)
    print(f"  Loaded batch size: {loaded_config.batch_size}")
    print(f"  Loaded LR: {loaded_config.learning_rate}")
    
    # Cleanup
    test_path.unlink()
    
    # Test validation
    print("\nTest 6: Configuration validation...")
    try:
        invalid_config = TrainingConfig(model_type='invalid')
        print("  ✗ Validation failed!")
    except ValueError as e:
        print(f"  ✓ Validation passed: {e}")
    
    print("\n✓ All tests passed!")


if __name__ == "__main__":
    test_training_config()
