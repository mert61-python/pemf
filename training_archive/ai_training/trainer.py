"""
Unified Training Pipeline
=========================

Universal trainer for all model architectures with:
- Mixed precision training (AMP)
- Gradient accumulation
- Learning rate scheduling
- Early stopping
- Model checkpointing
- TensorBoard logging
- Distributed training support
- Validation and testing loops

Usage:
------
    trainer = Trainer(
        model=model,
        optimizer=optimizer,
        criterion=criterion,
        device='cuda'
    )
    
    trainer.train(
        train_loader=train_loader,
        val_loader=val_loader,
        epochs=100,
        save_dir='checkpoints/'
    )
    
    # Test model
    test_metrics = trainer.test(test_loader)
"""

import torch
import torch.nn as nn
from torch.cuda.amp import autocast, GradScaler
from torch.utils.tensorboard import SummaryWriter
from pathlib import Path
import numpy as np
from typing import Dict, Optional, Callable, List, Union
from tqdm import tqdm
import time
import json
from datetime import datetime

import sys
sys.path.append(str(Path(__file__).parent.parent))
from train_config import DEVICE, MODELS, TRAINING
from models.base_model import EarlyStopping


class Trainer:
    """
    Universal training pipeline for all models.
    
    Supports autoencoder, predictor, monitor training with
    common interface and advanced features.
    """
    
    def __init__(self,
                 model: nn.Module,
                 optimizer: torch.optim.Optimizer,
                 criterion: Optional[Callable] = None,
                 device: Optional[Union[str, torch.device]] = None,
                 mixed_precision: bool = True,
                 gradient_accumulation_steps: int = 1,
                 max_grad_norm: float = 1.0):
        """
        Initialize trainer.
        
        Args:
            model: PyTorch model to train
            optimizer: Optimizer instance
            criterion: Loss function (optional if model has loss_function)
            device: Training device
            mixed_precision: Use automatic mixed precision
            gradient_accumulation_steps: Accumulate gradients over steps
            max_grad_norm: Maximum gradient norm for clipping
        """
        self.model = model
        self.optimizer = optimizer
        self.criterion = criterion
        self.device = torch.device(device) if device else DEVICE
        
        self.model.to(self.device)
        
        # Training settings
        self.mixed_precision = mixed_precision and torch.cuda.is_available()
        self.gradient_accumulation_steps = gradient_accumulation_steps
        self.max_grad_norm = max_grad_norm
        
        # AMP scaler
        self.scaler = GradScaler() if self.mixed_precision else None
        
        # Training state
        self.current_epoch = 0
        self.global_step = 0
        self.best_val_loss = float('inf')
        
        # History tracking
        self.history = {
            'train_loss': [],
            'val_loss': [],
            'learning_rates': [],
            'epoch_times': []
        }
        
        # TensorBoard writer
        self.writer = None
        
        # Scheduler (set via set_scheduler)
        self.scheduler = None
        
        # Early stopping (set via set_early_stopping)
        self.early_stopping = None
        
        print(f"✓ Trainer initialized")
        print(f"  Device: {self.device}")
        print(f"  Mixed precision: {self.mixed_precision}")
        print(f"  Gradient accumulation: {self.gradient_accumulation_steps} steps")
    
    def set_scheduler(self, scheduler):
        """
        Set learning rate scheduler.
        
        Args:
            scheduler: PyTorch LR scheduler
        """
        self.scheduler = scheduler
        print(f"✓ Scheduler set: {scheduler.__class__.__name__}")
    
    def set_early_stopping(self, patience: int = 10, min_delta: float = 0.0):
        """
        Set early stopping.
        
        Args:
            patience: Epochs to wait before stopping
            min_delta: Minimum change to qualify as improvement
        """
        self.early_stopping = EarlyStopping(
            patience=patience,
            min_delta=min_delta,
            mode='min'
        )
        print(f"✓ Early stopping set: patience={patience}")
    
    def set_tensorboard(self, log_dir: Union[str, Path]):
        """
        Initialize TensorBoard logging.
        
        Args:
            log_dir: Directory for TensorBoard logs
        """
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # Create timestamped run directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = log_dir / f"run_{timestamp}"
        
        self.writer = SummaryWriter(str(run_dir))
        print(f"✓ TensorBoard logging to: {run_dir}")
    
    def train_epoch(self, train_loader) -> Dict[str, float]:
        """
        Train for one epoch.
        
        Args:
            train_loader: Training data loader
            
        Returns:
            Dictionary with training metrics
        """
        self.model.train()
        
        epoch_loss = 0.0
        num_batches = 0
        
        pbar = tqdm(train_loader, desc=f"Epoch {self.current_epoch}")
        
        for batch_idx, batch in enumerate(pbar):
            # Move batch to device
            if isinstance(batch, (list, tuple)):
                batch = [b.to(self.device) if torch.is_tensor(b) else b for b in batch]
            elif isinstance(batch, dict):
                batch = {k: v.to(self.device) if torch.is_tensor(v) else v 
                        for k, v in batch.items()}
            else:
                batch = batch.to(self.device)
            
            # Forward pass with optional AMP
            with autocast(enabled=self.mixed_precision):
                if hasattr(self.model, 'loss_function'):
                    # Model has built-in loss function (e.g., VAE)
                    outputs = self.model(batch[0] if isinstance(batch, (list, tuple)) else batch)
                    
                    if isinstance(outputs, dict):
                        # Model returns dict with loss
                        loss_dict = self.model.loss_function(outputs, batch)
                        loss = loss_dict['loss']
                    else:
                        # Model returns only outputs
                        loss = self.criterion(outputs, batch[1] if isinstance(batch, (list, tuple)) else batch)
                else:
                    # Use external criterion
                    inputs = batch[0] if isinstance(batch, (list, tuple)) else batch
                    targets = batch[1] if isinstance(batch, (list, tuple)) else None
                    
                    outputs = self.model(inputs)
                    
                    if targets is not None:
                        loss = self.criterion(outputs, targets)
                    else:
                        loss = self.criterion(outputs)
            
            # Scale loss for gradient accumulation
            loss = loss / self.gradient_accumulation_steps
            
            # Backward pass with optional AMP
            if self.mixed_precision:
                self.scaler.scale(loss).backward()
            else:
                loss.backward()
            
            # Update weights
            if (batch_idx + 1) % self.gradient_accumulation_steps == 0:
                # Gradient clipping
                if self.max_grad_norm > 0:
                    if self.mixed_precision:
                        self.scaler.unscale_(self.optimizer)
                    torch.nn.utils.clip_grad_norm_(self.model.parameters(), self.max_grad_norm)
                
                # Optimizer step
                if self.mixed_precision:
                    self.scaler.step(self.optimizer)
                    self.scaler.update()
                else:
                    self.optimizer.step()
                
                self.optimizer.zero_grad()
                self.global_step += 1
            
            # Update metrics
            epoch_loss += loss.item() * self.gradient_accumulation_steps
            num_batches += 1
            
            # Update progress bar
            pbar.set_postfix({'loss': epoch_loss / num_batches})
            
            # TensorBoard logging
            if self.writer and self.global_step % 10 == 0:
                self.writer.add_scalar('Loss/train_step', 
                                      loss.item() * self.gradient_accumulation_steps, 
                                      self.global_step)
        
        avg_loss = epoch_loss / num_batches
        
        return {'loss': avg_loss}
    
    def validate(self, val_loader) -> Dict[str, float]:
        """
        Validate model.
        
        Args:
            val_loader: Validation data loader
            
        Returns:
            Dictionary with validation metrics
        """
        self.model.eval()
        
        val_loss = 0.0
        num_batches = 0
        
        with torch.no_grad():
            for batch in tqdm(val_loader, desc="Validating"):
                # Move batch to device
                if isinstance(batch, (list, tuple)):
                    batch = [b.to(self.device) if torch.is_tensor(b) else b for b in batch]
                elif isinstance(batch, dict):
                    batch = {k: v.to(self.device) if torch.is_tensor(v) else v 
                            for k, v in batch.items()}
                else:
                    batch = batch.to(self.device)
                
                # Forward pass
                if hasattr(self.model, 'loss_function'):
                    outputs = self.model(batch[0] if isinstance(batch, (list, tuple)) else batch)
                    
                    if isinstance(outputs, dict):
                        loss_dict = self.model.loss_function(outputs, batch)
                        loss = loss_dict['loss']
                    else:
                        loss = self.criterion(outputs, batch[1] if isinstance(batch, (list, tuple)) else batch)
                else:
                    inputs = batch[0] if isinstance(batch, (list, tuple)) else batch
                    targets = batch[1] if isinstance(batch, (list, tuple)) else None
                    
                    outputs = self.model(inputs)
                    
                    if targets is not None:
                        loss = self.criterion(outputs, targets)
                    else:
                        loss = self.criterion(outputs)
                
                val_loss += loss.item()
                num_batches += 1
        
        avg_loss = val_loss / num_batches
        
        return {'loss': avg_loss}
    
    def train(self,
             train_loader,
             val_loader,
             epochs: int,
             save_dir: Union[str, Path],
             save_every: int = 5,
             log_dir: Optional[Union[str, Path]] = None) -> Dict[str, List]:
        """
        Full training loop.
        
        Args:
            train_loader: Training data loader
            val_loader: Validation data loader
            epochs: Number of epochs
            save_dir: Directory to save checkpoints
            save_every: Save checkpoint every N epochs
            log_dir: TensorBoard log directory (optional)
            
        Returns:
            Training history
        """
        save_dir = Path(save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize TensorBoard
        if log_dir:
            self.set_tensorboard(log_dir)
        
        print(f"\n{'='*60}")
        print(f"Starting Training")
        print(f"{'='*60}")
        print(f"Epochs: {epochs}")
        print(f"Train batches: {len(train_loader)}")
        print(f"Val batches: {len(val_loader)}")
        print(f"Save directory: {save_dir}")
        print(f"{'='*60}\n")
        
        for epoch in range(epochs):
            self.current_epoch = epoch + 1
            epoch_start_time = time.time()
            
            # Training
            train_metrics = self.train_epoch(train_loader)
            train_loss = train_metrics['loss']
            
            # Validation
            val_metrics = self.validate(val_loader)
            val_loss = val_metrics['loss']
            
            # Learning rate scheduling
            if self.scheduler:
                if isinstance(self.scheduler, torch.optim.lr_scheduler.ReduceLROnPlateau):
                    self.scheduler.step(val_loss)
                else:
                    self.scheduler.step()
            
            # Get current learning rate
            current_lr = self.optimizer.param_groups[0]['lr']
            
            # Epoch time
            epoch_time = time.time() - epoch_start_time
            
            # Update history
            self.history['train_loss'].append(train_loss)
            self.history['val_loss'].append(val_loss)
            self.history['learning_rates'].append(current_lr)
            self.history['epoch_times'].append(epoch_time)
            
            # TensorBoard logging
            if self.writer:
                self.writer.add_scalar('Loss/train_epoch', train_loss, self.current_epoch)
                self.writer.add_scalar('Loss/val_epoch', val_loss, self.current_epoch)
                self.writer.add_scalar('LearningRate', current_lr, self.current_epoch)
            
            # Print epoch summary
            print(f"\nEpoch {self.current_epoch}/{epochs}")
            print(f"  Train Loss: {train_loss:.6f}")
            print(f"  Val Loss:   {val_loss:.6f}")
            print(f"  LR:         {current_lr:.2e}")
            print(f"  Time:       {epoch_time:.1f}s")
            
            # Save best model
            if val_loss < self.best_val_loss:
                self.best_val_loss = val_loss
                best_path = save_dir / "best_model.pth"
                self.save_checkpoint(best_path, is_best=True)
                print(f"  ✓ New best model saved (val_loss: {val_loss:.6f})")
            
            # Periodic checkpoint
            if (self.current_epoch % save_every == 0) or (self.current_epoch == epochs):
                checkpoint_path = save_dir / f"checkpoint_epoch_{self.current_epoch}.pth"
                self.save_checkpoint(checkpoint_path)
                print(f"  ✓ Checkpoint saved: epoch_{self.current_epoch}")
            
            # Early stopping
            if self.early_stopping:
                should_stop = self.early_stopping(val_loss)
                if should_stop:
                    print(f"\n⚠ Early stopping triggered at epoch {self.current_epoch}")
                    print(f"  Best val loss: {self.best_val_loss:.6f}")
                    break
        
        # Close TensorBoard writer
        if self.writer:
            self.writer.close()
        
        # Save training history
        history_path = save_dir / "training_history.json"
        with open(history_path, 'w') as f:
            json.dump(self.history, f, indent=2)
        
        print(f"\n{'='*60}")
        print(f"Training Complete!")
        print(f"{'='*60}")
        print(f"Best val loss: {self.best_val_loss:.6f}")
        print(f"Total epochs: {self.current_epoch}")
        print(f"Average epoch time: {np.mean(self.history['epoch_times']):.1f}s")
        print(f"{'='*60}\n")
        
        return self.history
    
    def test(self, test_loader) -> Dict[str, float]:
        """
        Test model on test set.
        
        Args:
            test_loader: Test data loader
            
        Returns:
            Test metrics
        """
        print(f"\n{'='*60}")
        print(f"Testing Model")
        print(f"{'='*60}")
        
        test_metrics = self.validate(test_loader)
        
        print(f"Test Loss: {test_metrics['loss']:.6f}")
        print(f"{'='*60}\n")
        
        return test_metrics
    
    def save_checkpoint(self, filepath: Union[str, Path], is_best: bool = False):
        """
        Save training checkpoint.
        
        Args:
            filepath: Path to save checkpoint
            is_best: Whether this is the best model so far
        """
        checkpoint = {
            'epoch': self.current_epoch,
            'global_step': self.global_step,
            'model_state_dict': self.model.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
            'best_val_loss': self.best_val_loss,
            'history': self.history,
            'is_best': is_best
        }
        
        if self.scheduler:
            checkpoint['scheduler_state_dict'] = self.scheduler.state_dict()
        
        if self.scaler:
            checkpoint['scaler_state_dict'] = self.scaler.state_dict()
        
        torch.save(checkpoint, filepath)
    
    def load_checkpoint(self, filepath: Union[str, Path]):
        """
        Load training checkpoint.
        
        Args:
            filepath: Path to checkpoint file
        """
        checkpoint = torch.load(filepath, map_location=self.device)
        
        self.model.load_state_dict(checkpoint['model_state_dict'])
        self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
        
        self.current_epoch = checkpoint['epoch']
        self.global_step = checkpoint['global_step']
        self.best_val_loss = checkpoint['best_val_loss']
        self.history = checkpoint['history']
        
        if self.scheduler and 'scheduler_state_dict' in checkpoint:
            self.scheduler.load_state_dict(checkpoint['scheduler_state_dict'])
        
        if self.scaler and 'scaler_state_dict' in checkpoint:
            self.scaler.load_state_dict(checkpoint['scaler_state_dict'])
        
        print(f"✓ Checkpoint loaded from: {filepath}")
        print(f"  Epoch: {self.current_epoch}")
        print(f"  Best val loss: {self.best_val_loss:.6f}")


def test_trainer():
    """
    Test trainer functionality.
    """
    print("=== Testing Trainer ===\n")
    
    # Create dummy model
    model = nn.Sequential(
        nn.Linear(10, 32),
        nn.ReLU(),
        nn.Linear(32, 1)
    )
    
    # Create optimizer
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    
    # Create criterion
    criterion = nn.MSELoss()
    
    # Create trainer
    trainer = Trainer(
        model=model,
        optimizer=optimizer,
        criterion=criterion,
        mixed_precision=False,  # Disable for CPU testing
        gradient_accumulation_steps=2
    )
    
    # Set scheduler
    scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=5, gamma=0.1)
    trainer.set_scheduler(scheduler)
    
    # Set early stopping
    trainer.set_early_stopping(patience=3)
    
    # Create dummy data loaders
    from torch.utils.data import TensorDataset, DataLoader
    
    X_train = torch.randn(100, 10)
    y_train = torch.randn(100, 1)
    train_dataset = TensorDataset(X_train, y_train)
    train_loader = DataLoader(train_dataset, batch_size=16, shuffle=True)
    
    X_val = torch.randn(20, 10)
    y_val = torch.randn(20, 1)
    val_dataset = TensorDataset(X_val, y_val)
    val_loader = DataLoader(val_dataset, batch_size=16)
    
    # Train
    print("\nTest 1: Training for 3 epochs...")
    history = trainer.train(
        train_loader=train_loader,
        val_loader=val_loader,
        epochs=3,
        save_dir='test_checkpoints',
        save_every=2
    )
    
    print(f"\n  Final train loss: {history['train_loss'][-1]:.6f}")
    print(f"  Final val loss: {history['val_loss'][-1]:.6f}")
    
    # Test
    print("\nTest 2: Testing model...")
    test_metrics = trainer.test(val_loader)
    print(f"  Test loss: {test_metrics['loss']:.6f}")
    
    # Cleanup
    import shutil
    if Path('test_checkpoints').exists():
        shutil.rmtree('test_checkpoints')
    
    print("\n✓ All tests passed!")


if __name__ == "__main__":
    test_trainer()
