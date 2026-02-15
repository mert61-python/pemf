"""
Base Model Utilities
====================

Common utilities for all neural network models.

Provides:
---------
1. BaseModel class with standard methods
2. Weight initialization strategies
3. Model save/load with checkpoints
4. Training state management
5. Model summary and diagnostics

Usage:
------
    class MyModel(BaseModel):
        def __init__(self):
            super().__init__()
            self.network = nn.Sequential(...)
        
        def forward(self, x):
            return self.network(x)
    
    model = MyModel()
    model.initialize_weights()
    model.save_checkpoint('model.pth', epoch=10)
    model.load_checkpoint('model.pth')
"""

import torch
import torch.nn as nn
from pathlib import Path
import json
from typing import Dict, Any, Optional, Union
from datetime import datetime
import numpy as np

import sys
sys.path.append(str(Path(__file__).parent.parent))
from config import DEVICE, MODELS


class BaseModel(nn.Module):
    """
    Base class for all models with common utilities.
    """
    
    def __init__(self):
        super(BaseModel, self).__init__()
        self.device = DEVICE
        self.training_history = {
            'train_loss': [],
            'val_loss': [],
            'epoch': 0,
            'best_val_loss': float('inf')
        }
    
    def initialize_weights(self, method: str = 'kaiming'):
        """
        Initialize model weights with specified method.
        
        Args:
            method: 'kaiming', 'xavier', 'normal', 'uniform'
        """
        for name, module in self.named_modules():
            if isinstance(module, (nn.Conv1d, nn.Linear)):
                if method == 'kaiming':
                    nn.init.kaiming_normal_(module.weight, mode='fan_out', nonlinearity='relu')
                elif method == 'xavier':
                    nn.init.xavier_normal_(module.weight)
                elif method == 'normal':
                    nn.init.normal_(module.weight, mean=0, std=0.02)
                elif method == 'uniform':
                    nn.init.uniform_(module.weight, a=-0.1, b=0.1)
                
                if module.bias is not None:
                    nn.init.constant_(module.bias, 0)
            
            elif isinstance(module, (nn.BatchNorm1d, nn.LayerNorm)):
                nn.init.constant_(module.weight, 1)
                nn.init.constant_(module.bias, 0)
            
            elif isinstance(module, (nn.LSTM, nn.GRU)):
                for param_name, param in module.named_parameters():
                    if 'weight_ih' in param_name:
                        nn.init.kaiming_normal_(param)
                    elif 'weight_hh' in param_name:
                        nn.init.orthogonal_(param)
                    elif 'bias' in param_name:
                        nn.init.constant_(param, 0)
    
    def count_parameters(self, trainable_only: bool = True) -> int:
        """
        Count model parameters.
        
        Args:
            trainable_only: Count only trainable parameters
            
        Returns:
            Number of parameters
        """
        if trainable_only:
            return sum(p.numel() for p in self.parameters() if p.requires_grad)
        else:
            return sum(p.numel() for p in self.parameters())
    
    def get_model_summary(self) -> Dict[str, Any]:
        """
        Get comprehensive model summary.
        
        Returns:
            Dictionary with model information
        """
        total_params = self.count_parameters(trainable_only=False)
        trainable_params = self.count_parameters(trainable_only=True)
        
        # Get layer information
        layers = []
        for name, module in self.named_modules():
            if len(list(module.children())) == 0 and len(list(module.parameters())) > 0:
                layer_params = sum(p.numel() for p in module.parameters())
                layers.append({
                    'name': name,
                    'type': module.__class__.__name__,
                    'parameters': layer_params
                })
        
        return {
            'model_name': self.__class__.__name__,
            'total_parameters': total_params,
            'trainable_parameters': trainable_params,
            'non_trainable_parameters': total_params - trainable_params,
            'layers': layers,
            'device': str(self.device),
            'training_epoch': self.training_history['epoch'],
            'best_val_loss': self.training_history['best_val_loss']
        }
    
    def print_summary(self):
        """
        Print formatted model summary.
        """
        summary = self.get_model_summary()
        
        print(f"\n{'='*60}")
        print(f"Model: {summary['model_name']}")
        print(f"{'='*60}")
        print(f"Total parameters:       {summary['total_parameters']:>15,}")
        print(f"Trainable parameters:   {summary['trainable_parameters']:>15,}")
        print(f"Non-trainable params:   {summary['non_trainable_parameters']:>15,}")
        print(f"Device:                 {summary['device']:>15}")
        print(f"Training epoch:         {summary['training_epoch']:>15}")
        print(f"Best validation loss:   {summary['best_val_loss']:>15.6f}")
        print(f"{'='*60}")
        
        print(f"\nLayer breakdown:")
        print(f"{'Name':<30} {'Type':<20} {'Parameters':>10}")
        print(f"{'-'*60}")
        for layer in summary['layers'][:20]:  # Show first 20 layers
            print(f"{layer['name']:<30} {layer['type']:<20} {layer['parameters']:>10,}")
        
        if len(summary['layers']) > 20:
            print(f"... ({len(summary['layers']) - 20} more layers)")
        print(f"{'-'*60}\n")
    
    def save_checkpoint(self,
                       filepath: Union[str, Path],
                       epoch: int,
                       optimizer: Optional[torch.optim.Optimizer] = None,
                       scheduler: Optional[Any] = None,
                       metadata: Optional[Dict] = None):
        """
        Save model checkpoint with training state.
        
        Args:
            filepath: Path to save checkpoint
            epoch: Current training epoch
            optimizer: Optimizer state (optional)
            scheduler: LR scheduler state (optional)
            metadata: Additional metadata to save
        """
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        checkpoint = {
            'model_name': self.__class__.__name__,
            'epoch': epoch,
            'model_state_dict': self.state_dict(),
            'training_history': self.training_history,
            'timestamp': datetime.now().isoformat(),
            'device': str(self.device)
        }
        
        if optimizer is not None:
            checkpoint['optimizer_state_dict'] = optimizer.state_dict()
        
        if scheduler is not None:
            checkpoint['scheduler_state_dict'] = scheduler.state_dict()
        
        if metadata is not None:
            checkpoint['metadata'] = metadata
        
        torch.save(checkpoint, filepath)
        print(f"✓ Checkpoint saved: {filepath}")
    
    def load_checkpoint(self,
                       filepath: Union[str, Path],
                       optimizer: Optional[torch.optim.Optimizer] = None,
                       scheduler: Optional[Any] = None,
                       strict: bool = True) -> Dict:
        """
        Load model checkpoint.
        
        Args:
            filepath: Path to checkpoint file
            optimizer: Optimizer to load state into (optional)
            scheduler: Scheduler to load state into (optional)
            strict: Strictly enforce state dict keys match
            
        Returns:
            Checkpoint metadata
        """
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"Checkpoint not found: {filepath}")
        
        checkpoint = torch.load(filepath, map_location=self.device)
        
        # Load model state
        self.load_state_dict(checkpoint['model_state_dict'], strict=strict)
        
        # Load training history
        if 'training_history' in checkpoint:
            self.training_history = checkpoint['training_history']
        
        # Load optimizer state
        if optimizer is not None and 'optimizer_state_dict' in checkpoint:
            optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
        
        # Load scheduler state
        if scheduler is not None and 'scheduler_state_dict' in checkpoint:
            scheduler.load_state_dict(checkpoint['scheduler_state_dict'])
        
        print(f"✓ Checkpoint loaded: {filepath}")
        print(f"  Epoch: {checkpoint['epoch']}")
        print(f"  Model: {checkpoint['model_name']}")
        
        return checkpoint
    
    def save_weights(self, filepath: Union[str, Path]):
        """
        Save only model weights (no training state).
        
        Args:
            filepath: Path to save weights
        """
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        torch.save(self.state_dict(), filepath)
        print(f"✓ Weights saved: {filepath}")
    
    def load_weights(self, filepath: Union[str, Path], strict: bool = True):
        """
        Load only model weights.
        
        Args:
            filepath: Path to weights file
            strict: Strictly enforce state dict keys match
        """
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"Weights file not found: {filepath}")
        
        state_dict = torch.load(filepath, map_location=self.device)
        self.load_state_dict(state_dict, strict=strict)
        print(f"✓ Weights loaded: {filepath}")
    
    def freeze_layers(self, layer_names: Optional[list] = None):
        """
        Freeze model layers (stop gradient updates).
        
        Args:
            layer_names: List of layer names to freeze (None = freeze all)
        """
        if layer_names is None:
            # Freeze all parameters
            for param in self.parameters():
                param.requires_grad = False
            print(f"✓ All layers frozen")
        else:
            # Freeze specific layers
            for name, param in self.named_parameters():
                if any(layer_name in name for layer_name in layer_names):
                    param.requires_grad = False
            print(f"✓ Layers frozen: {layer_names}")
    
    def unfreeze_layers(self, layer_names: Optional[list] = None):
        """
        Unfreeze model layers (enable gradient updates).
        
        Args:
            layer_names: List of layer names to unfreeze (None = unfreeze all)
        """
        if layer_names is None:
            # Unfreeze all parameters
            for param in self.parameters():
                param.requires_grad = True
            print(f"✓ All layers unfrozen")
        else:
            # Unfreeze specific layers
            for name, param in self.named_parameters():
                if any(layer_name in name for layer_name in layer_names):
                    param.requires_grad = True
            print(f"✓ Layers unfrozen: {layer_names}")
    
    def get_device(self) -> torch.device:
        """
        Get device where model is located.
        
        Returns:
            torch.device
        """
        return next(self.parameters()).device
    
    def to_device(self, device: Optional[Union[str, torch.device]] = None):
        """
        Move model to specified device.
        
        Args:
            device: Target device (default: DEVICE from config)
        """
        if device is None:
            device = DEVICE
        
        self.device = torch.device(device)
        self.to(self.device)
        print(f"✓ Model moved to: {self.device}")
    
    def export_to_onnx(self,
                      filepath: Union[str, Path],
                      input_shape: tuple,
                      input_names: list = None,
                      output_names: list = None):
        """
        Export model to ONNX format.
        
        Args:
            filepath: Output ONNX file path
            input_shape: Input tensor shape (without batch dimension)
            input_names: Names for input tensors
            output_names: Names for output tensors
        """
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        # Create dummy input
        dummy_input = torch.randn(1, *input_shape).to(self.device)
        
        # Export
        torch.onnx.export(
            self,
            dummy_input,
            filepath,
            input_names=input_names or ['input'],
            output_names=output_names or ['output'],
            opset_version=11,
            export_params=True
        )
        
        print(f"✓ Model exported to ONNX: {filepath}")
    
    def calculate_flops(self, input_shape: tuple) -> int:
        """
        Estimate model FLOPs (floating point operations).
        
        Args:
            input_shape: Input tensor shape
            
        Returns:
            Estimated FLOPs
        """
        # Simplified FLOP estimation
        total_flops = 0
        
        for module in self.modules():
            if isinstance(module, nn.Conv1d):
                # Conv1d FLOPs = 2 * input_channels * output_channels * kernel_size * output_length
                total_flops += (2 * module.in_channels * module.out_channels * 
                               module.kernel_size[0] * (input_shape[-1] // module.stride[0]))
            
            elif isinstance(module, nn.Linear):
                # Linear FLOPs = 2 * input_features * output_features
                total_flops += 2 * module.in_features * module.out_features
            
            elif isinstance(module, nn.LSTM):
                # LSTM FLOPs (per timestep) = 4 * (input_size + hidden_size) * hidden_size
                seq_length = input_shape[1] if len(input_shape) > 1 else 1
                total_flops += (4 * (module.input_size + module.hidden_size) * 
                               module.hidden_size * seq_length * module.num_layers)
        
        return total_flops


class EarlyStopping:
    """
    Early stopping to prevent overfitting.
    """
    
    def __init__(self,
                 patience: int = 10,
                 min_delta: float = 0.0,
                 mode: str = 'min'):
        """
        Initialize early stopping.
        
        Args:
            patience: Number of epochs to wait before stopping
            min_delta: Minimum change to qualify as improvement
            mode: 'min' or 'max' (minimize or maximize metric)
        """
        self.patience = patience
        self.min_delta = min_delta
        self.mode = mode
        
        self.counter = 0
        self.best_value = float('inf') if mode == 'min' else float('-inf')
        self.should_stop = False
    
    def __call__(self, current_value: float) -> bool:
        """
        Check if training should stop.
        
        Args:
            current_value: Current metric value
            
        Returns:
            True if should stop training
        """
        if self.mode == 'min':
            improved = current_value < (self.best_value - self.min_delta)
        else:
            improved = current_value > (self.best_value + self.min_delta)
        
        if improved:
            self.best_value = current_value
            self.counter = 0
        else:
            self.counter += 1
            if self.counter >= self.patience:
                self.should_stop = True
        
        return self.should_stop


def test_base_model():
    """
    Test base model utilities.
    """
    print("=== Testing Base Model Utilities ===\n")
    
    # Create simple test model
    class TestModel(BaseModel):
        def __init__(self):
            super().__init__()
            self.conv1 = nn.Conv1d(1, 16, kernel_size=3)
            self.lstm = nn.LSTM(16, 32, num_layers=2, batch_first=True)
            self.fc = nn.Linear(32, 10)
        
        def forward(self, x):
            x = self.conv1(x)
            x = x.transpose(1, 2)
            x, _ = self.lstm(x)
            x = self.fc(x[:, -1, :])
            return x
    
    model = TestModel()
    model.to_device()
    
    print("Test 1: Model initialization and summary...")
    model.initialize_weights('kaiming')
    model.print_summary()
    
    print("\nTest 2: Parameter counting...")
    total = model.count_parameters(trainable_only=False)
    trainable = model.count_parameters(trainable_only=True)
    print(f"  Total parameters: {total:,}")
    print(f"  Trainable parameters: {trainable:,}")
    
    print("\nTest 3: Layer freezing...")
    model.freeze_layers(['conv1'])
    frozen_count = sum(1 for p in model.parameters() if not p.requires_grad)
    print(f"  Frozen parameters: {frozen_count}")
    
    model.unfreeze_layers(['conv1'])
    trainable_count = sum(1 for p in model.parameters() if p.requires_grad)
    print(f"  Trainable parameters after unfreeze: {trainable_count}")
    
    print("\nTest 4: Save/load checkpoint...")
    checkpoint_path = Path(__file__).parent / "test_checkpoint.pth"
    optimizer = torch.optim.Adam(model.parameters())
    
    model.save_checkpoint(checkpoint_path, epoch=5, optimizer=optimizer)
    
    # Create new model and load checkpoint
    model2 = TestModel()
    optimizer2 = torch.optim.Adam(model2.parameters())
    checkpoint = model2.load_checkpoint(checkpoint_path, optimizer=optimizer2)
    
    print(f"  Loaded epoch: {checkpoint['epoch']}")
    
    # Cleanup
    checkpoint_path.unlink()
    
    print("\nTest 5: Weights save/load...")
    weights_path = Path(__file__).parent / "test_weights.pth"
    model.save_weights(weights_path)
    
    model2.load_weights(weights_path)
    
    # Cleanup
    weights_path.unlink()
    
    print("\nTest 6: Early stopping...")
    early_stop = EarlyStopping(patience=3, mode='min')
    
    val_losses = [1.0, 0.9, 0.85, 0.84, 0.84, 0.84, 0.84]
    for epoch, loss in enumerate(val_losses):
        should_stop = early_stop(loss)
        print(f"  Epoch {epoch}: loss={loss:.2f}, counter={early_stop.counter}, stop={should_stop}")
        if should_stop:
            break
    
    print("\nTest 7: FLOP estimation...")
    input_shape = (1, 100)
    flops = model.calculate_flops(input_shape)
    print(f"  Estimated FLOPs: {flops:,}")
    
    print("\n✓ All tests passed!")


if __name__ == "__main__":
    test_base_model()
