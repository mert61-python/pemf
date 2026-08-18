# Training Examples

Complete training scripts for all model architectures.

## Quick Start

### 1. Train ECG Autoencoder

```bash
python train_autoencoder.py --data_dir data/physioZoo --epochs 100 --batch_size 32
```

### 2. Train PEMF Predictor

```bash
python train_predictor.py --features features.csv --labels labels.csv --epochs 150
```

### 3. Train Realtime Monitor

```bash
python train_monitor.py --sequences_dir data/sequences --epochs 100
```

## Training Options

### Common Options
- `--epochs`: Number of training epochs (default: 100)
- `--batch_size`: Batch size (default: 32)
- `--learning_rate`: Learning rate (default: 0.001)
- `--device`: Training device (default: cuda/cpu auto-detect)
- `--save_dir`: Checkpoint directory (default: checkpoints/)
- `--log_dir`: TensorBoard logs (default: logs/)

### Model-Specific Options

**Autoencoder:**
- `--latent_dim`: Latent space dimension (default: 32)
- `--beta`: KL divergence weight (default: 1.0)

**Predictor:**
- `--hidden_size`: Hidden layer size (default: 256)
- `--num_residual_blocks`: Number of residual blocks (default: 3)

**Monitor:**
- `--sequence_length`: Input sequence length (default: 30)
- `--num_layers`: LSTM layers (default: 2)

## Hyperparameter Optimization

Run hyperparameter search with Optuna:

```bash
python hyperparameter_search.py --model autoencoder --n_trials 50
```

## TensorBoard Visualization

Monitor training in real-time:

```bash
tensorboard --logdir logs/
```

Open browser: http://localhost:6006

## Output Files

After training:
- `checkpoints/best_model.pth` - Best model weights
- `checkpoints/checkpoint_epoch_*.pth` - Periodic checkpoints
- `checkpoints/training_history.json` - Loss curves and metrics
- `checkpoints/config.json` - Training configuration
- `checkpoints/training_history.png` - Loss plots
- `checkpoints/reconstructions.png` - Model visualizations
