"""
Training Example: ECG Autoencoder
==================================

Complete training pipeline for ECG Autoencoder model.

This example demonstrates:
1. Data loading from PhysioZoo/MIT-BIH
2. Dataset preparation and augmentation
3. Model initialization
4. Training with validation
5. Model evaluation and visualization
6. Checkpoint saving

Usage:
------
    python train_autoencoder.py --data_dir data/physioZoo --epochs 100
"""

import torch
import argparse
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))

from ai.models import ECGAutoencoder
from ai.training import (
    Trainer,
    TrainingConfig,
    ECGDataset,
    create_data_loaders,
    get_default_config
)
from ai.config import DEVICE


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Train ECG Autoencoder')
    
    # Data
    parser.add_argument('--data_dir', type=str, required=True,
                       help='Directory containing ECG data')
    parser.add_argument('--species', type=str, default='dog',
                       choices=['dog', 'cat', 'rabbit', 'mouse'],
                       help='Animal species')
    
    # Training
    parser.add_argument('--epochs', type=int, default=100,
                       help='Number of training epochs')
    parser.add_argument('--batch_size', type=int, default=32,
                       help='Batch size')
    parser.add_argument('--learning_rate', type=float, default=0.001,
                       help='Learning rate')
    
    # Model
    parser.add_argument('--latent_dim', type=int, default=32,
                       help='Latent space dimension')
    parser.add_argument('--beta', type=float, default=1.0,
                       help='KL divergence weight')
    
    # Output
    parser.add_argument('--save_dir', type=str, default='checkpoints/autoencoder',
                       help='Directory to save checkpoints')
    parser.add_argument('--log_dir', type=str, default='logs/autoencoder',
                       help='TensorBoard log directory')
    
    # Hardware
    parser.add_argument('--device', type=str, default=str(DEVICE),
                       help='Training device')
    parser.add_argument('--num_workers', type=int, default=0,
                       help='Number of data loading workers')
    
    return parser.parse_args()


def visualize_reconstructions(model, test_loader, device, save_path=None):
    """
    Visualize model reconstructions.
    
    Args:
        model: Trained autoencoder
        test_loader: Test data loader
        device: Device
        save_path: Path to save figure (optional)
    """
    model.eval()
    
    # Get batch
    batch = next(iter(test_loader))
    signals = batch.to(device)
    
    # Forward pass
    with torch.no_grad():
        reconstructed, mu, logvar = model(signals)
    
    # Plot 4 examples
    fig, axes = plt.subplots(4, 2, figsize=(12, 10))
    
    for i in range(4):
        # Original
        axes[i, 0].plot(signals[i, 0].cpu().numpy())
        axes[i, 0].set_title(f'Original {i+1}')
        axes[i, 0].set_ylabel('Amplitude')
        if i == 3:
            axes[i, 0].set_xlabel('Samples')
        
        # Reconstructed
        axes[i, 1].plot(reconstructed[i, 0].cpu().numpy())
        axes[i, 1].set_title(f'Reconstructed {i+1}')
        if i == 3:
            axes[i, 1].set_xlabel('Samples')
    
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=150)
        print(f"✓ Reconstructions saved: {save_path}")
    else:
        plt.show()
    
    plt.close()


def main():
    """Main training function."""
    args = parse_args()
    
    print(f"\n{'='*60}")
    print(f"ECG Autoencoder Training")
    print(f"{'='*60}")
    print(f"Data directory: {args.data_dir}")
    print(f"Species: {args.species}")
    print(f"Epochs: {args.epochs}")
    print(f"Batch size: {args.batch_size}")
    print(f"Learning rate: {args.learning_rate}")
    print(f"Latent dim: {args.latent_dim}")
    print(f"Device: {args.device}")
    print(f"{'='*60}\n")
    
    # 1. Create dataset
    print("Step 1: Loading data...")
    dataset = ECGDataset(
        data_dir=args.data_dir,
        species=args.species,
        signal_length=2500,
        augment=True,
        cache=True
    )
    
    # 2. Create data loaders
    print("\nStep 2: Creating data loaders...")
    train_loader, val_loader, test_loader = create_data_loaders(
        dataset,
        batch_size=args.batch_size,
        num_workers=args.num_workers
    )
    
    # 3. Create model
    print("\nStep 3: Initializing model...")
    model = ECGAutoencoder(
        signal_length=2500,
        latent_dim=args.latent_dim
    )
    model.initialize_weights()
    model.print_summary()
    
    # 4. Create training configuration
    print("\nStep 4: Setting up training...")
    config = get_default_config('autoencoder')
    config.learning_rate = args.learning_rate
    config.batch_size = args.batch_size
    config.epochs = args.epochs
    config.device = args.device
    
    # Get optimizer and scheduler
    optimizer = config.get_optimizer(model)
    scheduler = config.get_scheduler(optimizer)
    
    # 5. Create trainer
    trainer = Trainer(
        model=model,
        optimizer=optimizer,
        device=args.device,
        mixed_precision=config.mixed_precision,
        gradient_accumulation_steps=config.gradient_accumulation_steps,
        max_grad_norm=config.max_grad_norm
    )
    
    # Set scheduler and early stopping
    if scheduler:
        trainer.set_scheduler(scheduler)
    
    if config.early_stopping:
        trainer.set_early_stopping(
            patience=config.early_stopping_patience,
            min_delta=config.early_stopping_min_delta
        )
    
    # 6. Train model
    print("\nStep 5: Training model...")
    history = trainer.train(
        train_loader=train_loader,
        val_loader=val_loader,
        epochs=args.epochs,
        save_dir=args.save_dir,
        save_every=config.save_every,
        log_dir=args.log_dir
    )
    
    # 7. Test model
    print("\nStep 6: Testing model...")
    test_metrics = trainer.test(test_loader)
    
    # 8. Visualize results
    print("\nStep 7: Visualizing results...")
    save_dir = Path(args.save_dir)
    
    # Plot training history
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    
    # Loss curves
    axes[0].plot(history['train_loss'], label='Train')
    axes[0].plot(history['val_loss'], label='Validation')
    axes[0].set_xlabel('Epoch')
    axes[0].set_ylabel('Loss')
    axes[0].set_title('Training History')
    axes[0].legend()
    axes[0].grid(True)
    
    # Learning rate
    axes[1].plot(history['learning_rates'])
    axes[1].set_xlabel('Epoch')
    axes[1].set_ylabel('Learning Rate')
    axes[1].set_title('Learning Rate Schedule')
    axes[1].set_yscale('log')
    axes[1].grid(True)
    
    plt.tight_layout()
    plt.savefig(save_dir / 'training_history.png', dpi=150)
    print(f"✓ Training history saved: {save_dir / 'training_history.png'}")
    
    # Visualize reconstructions
    visualize_reconstructions(
        model,
        test_loader,
        args.device,
        save_path=save_dir / 'reconstructions.png'
    )
    
    # 9. Save final model
    print("\nStep 8: Saving final model...")
    model.save_weights(save_dir / 'final_model.pth')
    
    # Save config
    config.save(save_dir / 'config.json')
    
    print(f"\n{'='*60}")
    print(f"Training Complete!")
    print(f"{'='*60}")
    print(f"Best validation loss: {trainer.best_val_loss:.6f}")
    print(f"Test loss: {test_metrics['loss']:.6f}")
    print(f"Model saved to: {save_dir}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
