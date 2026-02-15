"""Inspect predictor checkpoint structure"""
import torch
from pathlib import Path

checkpoint_path = Path('ai') / 'models' / 'checkpoints' / 'predictor' / 'best_model.pth'
print(f"Loading: {checkpoint_path.absolute()}")

checkpoint = torch.load(checkpoint_path, weights_only=False, map_location='cpu')

print("Checkpoint keys:", checkpoint.keys())
print(f"\nEpoch: {checkpoint.get('epoch')}")
print(f"Val loss: {checkpoint.get('val_loss')}")

print("\n" + "="*60)
print("BatchNorm running_mean sizes:")
print("="*60)

state_dict = checkpoint['model_state_dict']
for key in sorted(state_dict.keys()):
    if 'running_mean' in key:
        size = state_dict[key].shape[0]
        print(f"{key:50s} size={size}")
