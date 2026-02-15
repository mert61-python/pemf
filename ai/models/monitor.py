"""
Real-time Treatment Monitoring System
======================================

LSTM-based anomaly detection during PEMF treatment for patient safety.

Monitors:
---------
1. ECG features (HR, HRV changes)
2. PEMF sensor data (magnetic field, temperature, current)
3. Treatment parameters (frequency, intensity changes)
4. Temporal patterns and trends

Alerts when:
------------
- Heart rate deviates >30% from baseline
- HRV drops >50% (stress indicator)
- Temperature rises >15°C (overheating)
- Current spikes >150% (electrical issue)
- Magnetic field drift >20% (coil malfunction)

Architecture:
-------------
Bidirectional LSTM for temporal pattern learning
Input: Time series of ECG + PEMF features (sequence_length=30)
Output: 3-class classification (Normal, Warning, Critical)

Usage:
------
    monitor = RealtimeMonitor(input_features=20, sequence_length=30)
    
    # During treatment (real-time)
    status = monitor.predict_status(feature_sequence)
    
    if status == 'Critical':
        # Stop treatment immediately
        stop_treatment()
    elif status == 'Warning':
        # Alert veterinarian
        alert_vet()
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from typing import Dict, List, Tuple, Optional
from collections import deque
from pathlib import Path
import warnings

import sys
sys.path.append(str(Path(__file__).parent.parent))
from config import MODELS, DEVICE, ANOMALY_THRESHOLDS, SPECIES_PARAMS


class RealtimeMonitor(nn.Module):
    """
    LSTM-based real-time monitoring for treatment safety.
    
    Detects anomalies in physiological and sensor data streams.
    """
    
    def __init__(self, 
                 input_features: int = 20,
                 sequence_length: int = 30,
                 hidden_size: int = 64,
                 num_layers: int = 2):
        super(RealtimeMonitor, self).__init__()
        
        config = MODELS['realtime_monitor']
        self.input_features = input_features
        self.sequence_length = sequence_length
        self.hidden_size = config['lstm_hidden']
        self.num_layers = config['lstm_layers']
        self.dropout = config['dropout']
        self.bidirectional = config['bidirectional']
        
        # Bidirectional LSTM
        self.lstm = nn.LSTM(
            input_size=input_features,
            hidden_size=self.hidden_size,
            num_layers=self.num_layers,
            dropout=self.dropout if self.num_layers > 1 else 0,
            bidirectional=self.bidirectional,
            batch_first=True
        )
        
        # Calculate LSTM output size
        lstm_output_size = self.hidden_size * (2 if self.bidirectional else 1)
        
        # Attention mechanism for focusing on important time steps
        self.attention = nn.Sequential(
            nn.Linear(lstm_output_size, lstm_output_size // 2),
            nn.Tanh(),
            nn.Linear(lstm_output_size // 2, 1)
        )
        
        # Classification head
        self.classifier = nn.Sequential(
            nn.Linear(lstm_output_size, lstm_output_size // 2),
            nn.ReLU(),
            nn.Dropout(self.dropout),
            nn.Linear(lstm_output_size // 2, lstm_output_size // 4),
            nn.ReLU(),
            nn.Dropout(self.dropout),
            nn.Linear(lstm_output_size // 4, 3)  # Normal, Warning, Critical
        )
        
        # Regression head for specific anomaly scores
        self.anomaly_scorer = nn.Sequential(
            nn.Linear(lstm_output_size, lstm_output_size // 2),
            nn.ReLU(),
            nn.Dropout(self.dropout),
            nn.Linear(lstm_output_size // 2, 5),  # 5 anomaly scores
            nn.Sigmoid()
        )
    
    def forward(self, x: torch.Tensor) -> Dict[str, torch.Tensor]:
        """
        Forward pass through monitor.
        
        Args:
            x: Input sequence (batch_size, sequence_length, input_features)
            
        Returns:
            Dictionary with:
                - status_logits: (batch_size, 3) for Normal/Warning/Critical
                - status_probs: (batch_size, 3) softmax probabilities
                - anomaly_scores: (batch_size, 5) specific anomaly scores
                - attention_weights: (batch_size, sequence_length) attention weights
        """
        batch_size = x.size(0)
        
        # LSTM forward pass
        lstm_out, (hidden, cell) = self.lstm(x)
        # lstm_out shape: (batch_size, sequence_length, lstm_output_size)
        
        # Attention mechanism
        attention_scores = self.attention(lstm_out)  # (batch_size, sequence_length, 1)
        attention_weights = F.softmax(attention_scores, dim=1)
        
        # Weighted sum of LSTM outputs
        context = torch.sum(attention_weights * lstm_out, dim=1)  # (batch_size, lstm_output_size)
        
        # Classification
        status_logits = self.classifier(context)
        status_probs = F.softmax(status_logits, dim=1)
        
        # Anomaly scores
        anomaly_scores = self.anomaly_scorer(context)
        
        return {
            'status_logits': status_logits,
            'status_probs': status_probs,
            'anomaly_scores': anomaly_scores,
            'attention_weights': attention_weights.squeeze(-1)
        }
    
    def predict_status(self, x: torch.Tensor) -> Tuple[str, float, Dict]:
        """
        Predict treatment status with confidence.
        
        Args:
            x: Input sequence
            
        Returns:
            Tuple of (status_str, confidence, details)
        """
        with torch.no_grad():
            outputs = self.forward(x)
            
            status_probs = outputs['status_probs']
            status_idx = torch.argmax(status_probs, dim=1).item()
            confidence = status_probs[0, status_idx].item()
            
            status_map = {0: 'Normal', 1: 'Warning', 2: 'Critical'}
            status = status_map[status_idx]
            
            # Get specific anomaly scores
            anomaly_scores = outputs['anomaly_scores'][0].cpu().numpy()
            anomaly_names = ['hr_anomaly', 'hrv_anomaly', 'temp_anomaly', 
                            'current_anomaly', 'field_anomaly']
            
            details = {
                'status': status,
                'confidence': confidence,
                'status_probabilities': {
                    'Normal': status_probs[0, 0].item(),
                    'Warning': status_probs[0, 1].item(),
                    'Critical': status_probs[0, 2].item()
                },
                'anomaly_scores': dict(zip(anomaly_names, anomaly_scores)),
                'attention_weights': outputs['attention_weights'][0].cpu().numpy()
            }
        
        return status, confidence, details
    
    def loss_function(self,
                     predictions: Dict[str, torch.Tensor],
                     targets: Dict[str, torch.Tensor],
                     weights: Optional[Dict[str, float]] = None) -> Dict[str, torch.Tensor]:
        """
        Combined loss for classification and anomaly detection.
        
        Args:
            predictions: Model outputs
            targets: Ground truth labels
            weights: Optional loss weights
            
        Returns:
            Dictionary with loss components
        """
        if weights is None:
            weights = {
                'status': 1.0,
                'anomaly': 0.5
            }
        
        # Classification loss (cross-entropy)
        status_loss = F.cross_entropy(
            predictions['status_logits'], 
            targets['status']
        )
        
        # Anomaly score loss (MSE)
        if 'anomaly_scores' in targets:
            anomaly_loss = F.mse_loss(
                predictions['anomaly_scores'],
                targets['anomaly_scores']
            )
        else:
            anomaly_loss = torch.tensor(0.0).to(predictions['status_logits'].device)
        
        # Total loss
        total_loss = (
            weights['status'] * status_loss +
            weights['anomaly'] * anomaly_loss
        )
        
        return {
            'loss': total_loss,
            'status_loss': status_loss,
            'anomaly_loss': anomaly_loss
        }


class RollingMonitor:
    """
    Rolling window monitor for continuous real-time analysis.
    
    Maintains a buffer of recent observations and provides
    real-time status updates.
    """
    
    def __init__(self,
                 model: RealtimeMonitor,
                 sequence_length: int = 30,
                 input_features: int = 20,
                 species: str = 'dog'):
        """
        Initialize rolling monitor.
        
        Args:
            model: Trained RealtimeMonitor model
            sequence_length: Length of sequence buffer
            input_features: Number of input features
            species: Animal species for thresholds
        """
        self.model = model
        self.model.eval()
        
        self.sequence_length = sequence_length
        self.input_features = input_features
        self.species = species
        
        # Rolling buffer
        self.buffer = deque(maxlen=sequence_length)
        
        # Baseline values for comparison
        self.baseline = {
            'hr': None,
            'hrv': None,
            'temp': None,
            'current': None,
            'field': None
        }
        
        # Alert history
        self.alert_history = []
        
        # Thresholds
        self.thresholds = ANOMALY_THRESHOLDS
        self.species_params = SPECIES_PARAMS.get(species, SPECIES_PARAMS['dog'])
    
    def set_baseline(self, ecg_features: Dict, sensor_data: Dict):
        """
        Set baseline values from pre-treatment measurements.
        
        Args:
            ecg_features: ECG-derived features (HR, HRV, etc.)
            sensor_data: PEMF sensor baseline
        """
        self.baseline['hr'] = ecg_features.get('heart_rate', 100)
        self.baseline['hrv'] = ecg_features.get('HRV_RMSSD', 50)
        self.baseline['temp'] = sensor_data.get('temperature', 25)
        self.baseline['current'] = sensor_data.get('current', 1.0)
        self.baseline['field'] = sensor_data.get('magnetic_field', 10)
        
        print(f"✓ Baseline set: HR={self.baseline['hr']:.1f} bpm, "
              f"HRV={self.baseline['hrv']:.1f} ms")
    
    def add_observation(self, features: np.ndarray):
        """
        Add new observation to rolling buffer.
        
        Args:
            features: Feature vector (input_features,)
        """
        self.buffer.append(features)
    
    def check_rule_based_anomalies(self, current_features: Dict) -> List[str]:
        """
        Rule-based anomaly detection (backup to neural network).
        
        Args:
            current_features: Current measurement values
            
        Returns:
            List of detected anomaly messages
        """
        alerts = []
        
        # Heart rate deviation
        if self.baseline['hr'] is not None:
            hr = current_features.get('heart_rate', self.baseline['hr'])
            hr_dev = abs(hr - self.baseline['hr']) / self.baseline['hr']
            
            if hr_dev > self.thresholds['hr_deviation']:
                alerts.append(f"⚠️ Heart rate deviation: {hr_dev*100:.1f}%")
        
        # HRV drop
        if self.baseline['hrv'] is not None:
            hrv = current_features.get('hrv', self.baseline['hrv'])
            hrv_ratio = hrv / self.baseline['hrv']
            
            if hrv_ratio < (1 - self.thresholds['hrv_drop']):
                alerts.append(f"⚠️ HRV dropped to {hrv_ratio*100:.1f}% of baseline")
        
        # Temperature rise
        if self.baseline['temp'] is not None:
            temp = current_features.get('temperature', self.baseline['temp'])
            temp_rise = temp - self.baseline['temp']
            
            if temp_rise > self.thresholds['temperature_rise']:
                alerts.append(f"🔥 Temperature rose {temp_rise:.1f}°C")
        
        # Current spike
        if self.baseline['current'] is not None:
            current = current_features.get('current', self.baseline['current'])
            current_ratio = current / self.baseline['current']
            
            if current_ratio > self.thresholds['current_spike']:
                alerts.append(f"⚡ Current spike: {current_ratio:.1f}x baseline")
        
        # Magnetic field drift
        if self.baseline['field'] is not None:
            field = current_features.get('magnetic_field', self.baseline['field'])
            field_dev = abs(field - self.baseline['field']) / self.baseline['field']
            
            if field_dev > self.thresholds['magnetic_field_drift']:
                alerts.append(f"🧲 Magnetic field drift: {field_dev*100:.1f}%")
        
        return alerts
    
    def get_status(self, current_features: Dict) -> Dict:
        """
        Get current treatment status.
        
        Combines neural network prediction with rule-based checks.
        
        Args:
            current_features: Current feature dictionary
            
        Returns:
            Status dictionary with recommendations
        """
        # Check if buffer is full
        if len(self.buffer) < self.sequence_length:
            return {
                'status': 'Initializing',
                'confidence': 0.0,
                'message': f'Collecting data... ({len(self.buffer)}/{self.sequence_length})',
                'action': 'continue'
            }
        
        # Prepare sequence tensor
        sequence = np.array(list(self.buffer))
        sequence_tensor = torch.FloatTensor(sequence).unsqueeze(0).to(DEVICE)
        
        # Neural network prediction
        status, confidence, details = self.model.predict_status(sequence_tensor)
        
        # Rule-based checks
        rule_alerts = self.check_rule_based_anomalies(current_features)
        
        # Combine assessments
        if rule_alerts or status == 'Critical':
            final_status = 'Critical'
            action = 'stop_immediately'
            message = 'Critical condition detected! ' + '; '.join(rule_alerts)
        elif status == 'Warning':
            final_status = 'Warning'
            action = 'reduce_intensity'
            message = 'Warning: Physiological changes detected'
        else:
            final_status = 'Normal'
            action = 'continue'
            message = 'Treatment proceeding normally'
        
        # Log alert
        if final_status != 'Normal':
            self.alert_history.append({
                'status': final_status,
                'confidence': confidence,
                'message': message,
                'timestamp': len(self.alert_history)
            })
        
        return {
            'status': final_status,
            'confidence': confidence,
            'message': message,
            'action': action,
            'neural_prediction': details,
            'rule_alerts': rule_alerts,
            'buffer_size': len(self.buffer)
        }


def extract_monitoring_features(ecg_features: Dict,
                               sensor_data: Dict,
                               treatment_params: Dict) -> np.ndarray:
    """
    Extract features for real-time monitoring (20 features).
    
    Args:
        ecg_features: ECG-derived features
        sensor_data: PEMF sensor readings
        treatment_params: Current treatment parameters
        
    Returns:
        Feature vector (20,)
    """
    features = []
    
    # ECG features (8)
    features.extend([
        ecg_features.get('heart_rate', 0) / 200.0,  # Normalized HR
        ecg_features.get('HRV_RMSSD', 0) / 100.0,
        ecg_features.get('HRV_SDNN', 0) / 100.0,
        ecg_features.get('HRV_LF', 0) / 1000.0,
        ecg_features.get('HRV_HF', 0) / 1000.0,
        ecg_features.get('HRV_LF_HF', 0) / 5.0,
        ecg_features.get('HRV_SD1', 0) / 100.0,
        ecg_features.get('HRV_SD2', 0) / 100.0
    ])
    
    # PEMF sensor features (9)
    features.extend([
        sensor_data.get('magnetic_field_mean', 0) / 100.0,
        sensor_data.get('magnetic_field_std', 0) / 10.0,
        sensor_data.get('magnetic_field_max', 0) / 100.0,
        sensor_data.get('temperature_mean', 0) / 80.0,
        sensor_data.get('temperature_std', 0) / 10.0,
        sensor_data.get('temperature_max', 0) / 80.0,
        sensor_data.get('current_mean', 0) / 30.0,
        sensor_data.get('current_std', 0) / 5.0,
        sensor_data.get('current_max', 0) / 30.0
    ])
    
    # Treatment parameters (3)
    features.extend([
        treatment_params.get('frequency', 10) / 100.0,
        treatment_params.get('intensity', 30) / 100.0,
        treatment_params.get('elapsed_time', 0) / 60.0  # Minutes
    ])
    
    return np.array(features, dtype=np.float32)


def test_monitor():
    """
    Test Realtime Monitor functionality.
    """
    print("=== Testing Realtime Monitor ===\n")
    
    # Create model
    model = RealtimeMonitor(input_features=20, sequence_length=30)
    model.to(DEVICE)
    print(f"Model created on device: {DEVICE}")
    
    # Count parameters
    n_params = sum(p.numel() for p in model.parameters())
    print(f"Total parameters: {n_params:,}\n")
    
    # Test forward pass
    batch_size = 8
    seq_length = 30
    input_features = 20
    dummy_input = torch.randn(batch_size, seq_length, input_features).to(DEVICE)
    
    print("Test 1: Forward pass...")
    outputs = model(dummy_input)
    print(f"  Input shape: {dummy_input.shape}")
    print(f"  Status logits shape: {outputs['status_logits'].shape}")
    print(f"  Status probs shape: {outputs['status_probs'].shape}")
    print(f"  Anomaly scores shape: {outputs['anomaly_scores'].shape}")
    print(f"  Attention weights shape: {outputs['attention_weights'].shape}")
    
    # Test prediction
    print("\nTest 2: Status prediction...")
    status, confidence, details = model.predict_status(dummy_input[0:1])
    print(f"  Predicted status: {status}")
    print(f"  Confidence: {confidence:.3f}")
    print(f"  Anomaly scores: {details['anomaly_scores']}")
    
    # Test rolling monitor
    print("\nTest 3: Rolling monitor...")
    rolling = RollingMonitor(model, sequence_length=30, species='dog')
    
    # Set baseline
    ecg_baseline = {'heart_rate': 100, 'HRV_RMSSD': 50}
    sensor_baseline = {'temperature': 25, 'current': 1.0, 'magnetic_field': 10}
    rolling.set_baseline(ecg_baseline, sensor_baseline)
    
    # Add observations
    print("\n  Adding observations...")
    for i in range(35):
        features = np.random.rand(20)
        rolling.add_observation(features)
        
        if i >= 30:  # Buffer full
            current_features = {
                'heart_rate': 100 + np.random.randn() * 5,
                'hrv': 50 + np.random.randn() * 5,
                'temperature': 25 + i * 0.5,  # Gradual temperature rise
                'current': 1.0 + np.random.randn() * 0.1,
                'magnetic_field': 10 + np.random.randn()
            }
            
            status_dict = rolling.get_status(current_features)
            if i == 34:  # Print last status
                print(f"\n  Final status: {status_dict['status']}")
                print(f"  Message: {status_dict['message']}")
                print(f"  Action: {status_dict['action']}")
    
    # Test feature extraction
    print("\nTest 4: Feature extraction...")
    ecg_features = {
        'heart_rate': 100, 'HRV_RMSSD': 30, 'HRV_SDNN': 50,
        'HRV_LF': 200, 'HRV_HF': 400, 'HRV_LF_HF': 0.5,
        'HRV_SD1': 25, 'HRV_SD2': 60
    }
    sensor_data = {
        'magnetic_field_mean': 15, 'magnetic_field_std': 2, 'magnetic_field_max': 20,
        'temperature_mean': 35, 'temperature_std': 3, 'temperature_max': 40,
        'current_mean': 2.5, 'current_std': 0.5, 'current_max': 3.5
    }
    treatment_params = {
        'frequency': 10, 'intensity': 30, 'elapsed_time': 15
    }
    
    features = extract_monitoring_features(ecg_features, sensor_data, treatment_params)
    print(f"  Extracted features shape: {features.shape}")
    print(f"  Feature range: [{features.min():.3f}, {features.max():.3f}]")
    
    print("\n✓ All tests passed!")
    
    return model


if __name__ == "__main__":
    test_monitor()
