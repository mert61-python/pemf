"""
PyTorch modellerini ONNX formatına dönüştürme scripti.
Autoencoder, Predictor, Monitor modelleri için .onnx dosyaları üretir.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import torch
import os
from pathlib import Path

# Model classlarını import et
from ai.models.autoencoder import ECGAutoencoder
from ai.models.predictor import PEMFPredictor
from ai.models.monitor import RealtimeMonitor

# Cihaz
DEVICE = torch.device('cpu')

# Klasörler
BASE = Path(__file__).parent / 'models' / 'checkpoints'


# 1. Autoencoder
print('Exporting Autoencoder...')
autoencoder = ECGAutoencoder()
ckpt_ae = torch.load(BASE / 'autoencoder' / 'best_model.pth', map_location=DEVICE)
autoencoder.load_state_dict(ckpt_ae['model_state_dict'])
autoencoder.eval()

dummy_ecg = torch.randn(1, 1, 2500)  # (batch, channel, length)
torch.onnx.export(
    autoencoder,
    dummy_ecg,
    str(BASE / 'autoencoder' / 'best_model.onnx'),
    input_names=['ecg'],
    output_names=['reconstructed', 'mu', 'logvar'],
    dynamic_axes={'ecg': {0: 'batch_size'}},
    opset_version=17
)
print('Autoencoder exported.')


# 2. Predictor
print('Exporting Predictor...')
predictor = PEMFPredictor()
ckpt_pred = torch.load(BASE / 'predictor' / 'best_model.pth', map_location=DEVICE)
predictor.load_state_dict(ckpt_pred['model_state_dict'])
predictor.eval()

# Wrapper to flatten output for ONNX export
import torch.nn as nn
class PredictorONNXWrapper(nn.Module):
    def __init__(self, model):
        super().__init__()
        self.model = model
    def forward(self, x):
        out = self.model(x)
        # out: dict with keys 'frequency', 'intensities', 'duration', 'confidence'
        # Each is (batch, 1) or (batch, 8)
        return torch.cat([
            out['frequency'],           # (batch, 1)
            out['intensities'],         # (batch, 8)
            out['duration'],            # (batch, 1)
            out['confidence']           # (batch, 1)
        ], dim=1)  # (batch, 11)

predictor_onnx = PredictorONNXWrapper(predictor)

dummy_features = torch.randn(1, 45)  # (batch, features)
torch.onnx.export(
    predictor_onnx,
    dummy_features,
    str(BASE / 'predictor' / 'best_model.onnx'),
    input_names=['features'],
    output_names=['output'],
    dynamic_axes={'features': {0: 'batch_size'}, 'output': {0: 'batch_size'}},
    opset_version=17
)
print('Predictor exported.')

# 3. Monitor
print('Exporting Monitor...')
monitor = RealtimeMonitor()
ckpt_mon = torch.load(BASE / 'monitor' / 'best_model.pth', map_location=DEVICE)
monitor.load_state_dict(ckpt_mon['model_state_dict'])
monitor.eval()

dummy_seq = torch.randn(1, 30, 20)  # (batch, seq_len, features)
torch.onnx.export(
    monitor,
    dummy_seq,
    str(BASE / 'monitor' / 'best_model.onnx'),
    input_names=['sequence'],
    output_names=['output'],
    dynamic_axes={'sequence': {0: 'batch_size'}},
    opset_version=17
)
print('Monitor exported.')

print('\nTüm modeller başarıyla ONNX formatına dönüştürüldü.')
