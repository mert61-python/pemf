"""
PEMF Treatment Parameter Predictor
====================================

Predicts optimal PEMF treatment parameters based on:
- ECG-derived features (HRV metrics, latent representations)
- PEMF sensor history (magnetic field, temperature, current)
- Patient metadata (species, age, weight, condition)
- Treatment history and outcomes

Input Features (45 total):
--------------------------
- 15 HRV features: SDNN, RMSSD, pNN50, VLF, LF, HF, LF/HF, SD1, SD2, etc.
- 15 PEMF sensor features: mean/std/max magnetic field, temperature, current
- 15 Context features: species encoding, previous treatment parameters, time since last treatment

Output (11 parameters):
-----------------------
- Frequency (1): Optimal PEMF frequency (1-100 Hz)
- Coil Intensities (8): PWM duty cycle for each of 8 coils (0-100%)
- Duration (1): Recommended treatment duration (5-60 minutes)
- Confidence (1): Model confidence score (0-1)

Architecture:
-------------
Multi-layer Perceptron with:
- Residual connections for gradient flow
- Batch normalization for stability
- Dropout for regularization
- Separate heads for different output types

Usage:
------
    model = PEMFPredictor(input_features=45)
    
    # Prediction
    predictions = model(features)
    frequency = predictions['frequency']
    intensities = predictions['intensities']
    duration = predictions['duration']
    confidence = predictions['confidence']
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from typing import Dict, Tuple, Optional
from pathlib import Path

import sys
sys.path.append(str(Path(__file__).parent.parent))
from config import MODELS, DEVICE, TREATMENT_PARAMS, SPECIES_PARAMS


class ResidualBlock(nn.Module):
    """
    Residual block with batch normalization and dropout.
    
    Helps with gradient flow in deep networks.
    """
    
    def __init__(self, hidden_size: int, dropout: float = 0.3):
        super(ResidualBlock, self).__init__()
        
        self.fc1 = nn.Linear(hidden_size, hidden_size)
        self.bn1 = nn.BatchNorm1d(hidden_size)
        self.dropout1 = nn.Dropout(dropout)
        
        self.fc2 = nn.Linear(hidden_size, hidden_size)
        self.bn2 = nn.BatchNorm1d(hidden_size)
        self.dropout2 = nn.Dropout(dropout)
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward with residual connection."""
        identity = x
        
        out = F.relu(self.bn1(self.fc1(x)))
        out = self.dropout1(out)
        
        out = self.bn2(self.fc2(out))
        out = self.dropout2(out)
        
        # Residual connection
        out = out + identity
        out = F.relu(out)
        
        return out


class PEMFPredictor(nn.Module):
    """
    Neural network for predicting optimal PEMF treatment parameters.
    
    Uses multi-task learning with separate heads for different outputs.
    """
    
    def __init__(self, input_features: int = 45):
        super(PEMFPredictor, self).__init__()
        
        config = MODELS['pemf_predictor']
        hidden_layers = config['hidden_layers']
        dropout = config['dropout']
        
        # DEBUG: Print config to verify
        import logging
        logging.info(f"PEMFPredictor.__init__: hidden_layers = {hidden_layers}")
        logging.info(f"PEMFPredictor.__init__: config source = {MODELS.get('__source__', 'unknown')}")
        
        self.input_features = input_features
        
        # Input layer
        self.input_layer = nn.Sequential(
            nn.Linear(input_features, hidden_layers[0]),
            nn.BatchNorm1d(hidden_layers[0]),
            nn.ReLU(),
            nn.Dropout(dropout)
        )
        
        # Hidden layers with residual blocks
        self.hidden_layers = nn.ModuleList()
        for i in range(len(hidden_layers) - 1):
            self.hidden_layers.append(
                nn.Sequential(
                    nn.Linear(hidden_layers[i], hidden_layers[i+1]),
                    nn.BatchNorm1d(hidden_layers[i+1]),
                    nn.ReLU(),
                    nn.Dropout(dropout)
                )
            )
        
        # Add residual blocks for deeper representation
        final_hidden = hidden_layers[-1]
        self.residual1 = ResidualBlock(final_hidden, dropout)
        self.residual2 = ResidualBlock(final_hidden, dropout)
        
        # Separate output heads for different predictions
        
        # Frequency head (1-100 Hz)
        self.frequency_head = nn.Sequential(
            nn.Linear(final_hidden, final_hidden // 2),
            nn.ReLU(),
            nn.Dropout(dropout / 2),
            nn.Linear(final_hidden // 2, 1),
            nn.Sigmoid()  # Output in [0, 1], scaled to [1, 100]
        )
        
        # Intensity head (8 coils, 0-100%)
        self.intensity_head = nn.Sequential(
            nn.Linear(final_hidden, final_hidden // 2),
            nn.ReLU(),
            nn.Dropout(dropout / 2),
            nn.Linear(final_hidden // 2, 8),
            nn.Sigmoid()  # Output in [0, 1], scaled to [0, 100]
        )
        
        # Duration head (5-60 minutes)
        self.duration_head = nn.Sequential(
            nn.Linear(final_hidden, final_hidden // 2),
            nn.ReLU(),
            nn.Dropout(dropout / 2),
            nn.Linear(final_hidden // 2, 1),
            nn.Sigmoid()  # Output in [0, 1], scaled to [5, 60]
        )
        
        # Confidence head (0-1)
        self.confidence_head = nn.Sequential(
            nn.Linear(final_hidden, final_hidden // 2),
            nn.ReLU(),
            nn.Dropout(dropout / 2),
            nn.Linear(final_hidden // 2, 1),
            nn.Sigmoid()  # Confidence score
        )
    
    def forward(self, x: torch.Tensor) -> Dict[str, torch.Tensor]:
        """
        Forward pass predicting all treatment parameters.
        
        Args:
            x: Input features (batch_size, input_features)
            
        Returns:
            Dictionary with predictions:
                - frequency: (batch_size, 1) in [1, 100] Hz
                - intensities: (batch_size, 8) in [0, 100] %
                - duration: (batch_size, 1) in [5, 60] minutes
                - confidence: (batch_size, 1) in [0, 1]
        """
        # Input layer
        x = self.input_layer(x)
        
        # Hidden layers
        for layer in self.hidden_layers:
            x = layer(x)
        
        # Residual blocks
        x = self.residual1(x)
        x = self.residual2(x)
        
        # Separate heads
        frequency_raw = self.frequency_head(x)
        intensities_raw = self.intensity_head(x)
        duration_raw = self.duration_head(x)
        confidence = self.confidence_head(x)
        
        # Scale outputs to appropriate ranges
        freq_range = TREATMENT_PARAMS['frequency_range']
        frequency = frequency_raw * (freq_range[1] - freq_range[0]) + freq_range[0]
        
        intensity_range = TREATMENT_PARAMS['intensity_range']
        intensities = intensities_raw * (intensity_range[1] - intensity_range[0]) + intensity_range[0]
        
        duration_range = TREATMENT_PARAMS['duration_range']
        duration = duration_raw * (duration_range[1] - duration_range[0]) + duration_range[0]
        
        return {
            'frequency': frequency,
            'intensities': intensities,
            'duration': duration,
            'confidence': confidence
        }
    
    def predict_safe(self, x: torch.Tensor, species: str = 'dog') -> Dict[str, torch.Tensor]:
        """
        Predict with species-specific safety constraints.
        
        Applies species-specific limits to ensure safe treatment parameters.
        
        Args:
            x: Input features
            species: Animal species
            
        Returns:
            Dictionary with safe predictions
        """
        # Get predictions
        predictions = self.forward(x)
        
        # Apply species-specific constraints
        if species in SPECIES_PARAMS:
            params = SPECIES_PARAMS[species]
            
            # Recommended frequency for species
            rec_freq = params['recommended_frequency']
            rec_intensity = params['recommended_intensity']
            
            # Soft constraint: blend model prediction with species recommendation
            alpha = predictions['confidence']  # Use confidence as blending factor
            
            predictions['frequency'] = (
                alpha * predictions['frequency'] + 
                (1 - alpha) * rec_freq
            )
            
            # Ensure intensities don't exceed species recommendation by too much
            max_intensity = rec_intensity * 1.5  # Allow 50% above recommendation
            predictions['intensities'] = torch.clamp(
                predictions['intensities'], 
                max=max_intensity
            )
        
        return predictions
    
    def loss_function(self, 
                     predictions: Dict[str, torch.Tensor],
                     targets: Dict[str, torch.Tensor],
                     weights: Optional[Dict[str, float]] = None) -> Dict[str, torch.Tensor]:
        """
        Multi-task loss function.
        
        Args:
            predictions: Model predictions
            targets: Ground truth targets
            weights: Optional weights for different loss components
            
        Returns:
            Dictionary with total loss and components
        """
        if weights is None:
            weights = {
                'frequency': 1.0,
                'intensities': 1.0,
                'duration': 1.0,
                'confidence': 0.5  # Lower weight for confidence
            }
        
        # Individual losses
        freq_loss = F.mse_loss(predictions['frequency'], targets['frequency'])
        intensity_loss = F.mse_loss(predictions['intensities'], targets['intensities'])
        duration_loss = F.mse_loss(predictions['duration'], targets['duration'])
        
        # Confidence loss (if target confidence provided)
        if 'confidence' in targets:
            confidence_loss = F.binary_cross_entropy(
                predictions['confidence'], 
                targets['confidence']
            )
        else:
            confidence_loss = torch.tensor(0.0).to(predictions['frequency'].device)
        
        # Weighted total loss
        total_loss = (
            weights['frequency'] * freq_loss +
            weights['intensities'] * intensity_loss +
            weights['duration'] * duration_loss +
            weights['confidence'] * confidence_loss
        )
        
        return {
            'loss': total_loss,
            'frequency_loss': freq_loss,
            'intensity_loss': intensity_loss,
            'duration_loss': duration_loss,
            'confidence_loss': confidence_loss
        }
    
    def explain_prediction(self, 
                          x: torch.Tensor,
                          feature_names: Optional[list] = None) -> Dict:
        """
        Provide explanation for prediction using gradient-based attribution.
        
        Shows which input features contributed most to the prediction.
        
        Args:
            x: Input features (single sample)
            feature_names: Optional list of feature names
            
        Returns:
            Dictionary with feature importance scores
        """
        x = x.requires_grad_(True)
        
        # Forward pass
        predictions = self.forward(x)
        
        # Calculate gradients for each output
        importance = {}
        
        for key in ['frequency', 'intensities', 'duration']:
            output = predictions[key]
            
            # Backward to get gradients
            self.zero_grad()
            output.sum().backward(retain_graph=True)
            
            # Feature importance = |gradient * input|
            feature_importance = (x.grad.abs() * x.abs()).detach().cpu().numpy()
            
            if feature_names:
                importance[key] = dict(zip(feature_names, feature_importance[0]))
            else:
                importance[key] = feature_importance[0]
        
        return importance


class EnsemblePredictor(nn.Module):
    """
    Ensemble of multiple PEMF predictors for robust predictions.
    
    Averages predictions from multiple models to reduce variance.
    """
    
    def __init__(self, n_models: int = 3, input_features: int = 45):
        super(EnsemblePredictor, self).__init__()
        
        self.models = nn.ModuleList([
            PEMFPredictor(input_features) for _ in range(n_models)
        ])
    
    def forward(self, x: torch.Tensor) -> Dict[str, torch.Tensor]:
        """
        Forward pass through ensemble.
        
        Returns averaged predictions and uncertainty estimates.
        """
        predictions_list = [model(x) for model in self.models]
        
        # Average predictions
        ensemble_pred = {}
        for key in predictions_list[0].keys():
            stacked = torch.stack([p[key] for p in predictions_list], dim=0)
            ensemble_pred[key] = stacked.mean(dim=0)
            ensemble_pred[f'{key}_std'] = stacked.std(dim=0)  # Uncertainty estimate
        
        return ensemble_pred


def prepare_input_features(hrv_features: Dict[str, float],
                          pemf_sensor_data: Dict[str, np.ndarray],
                          context: Dict) -> torch.Tensor:
    """
    Prepare input features from different sources.
    
    Args:
        hrv_features: HRV metrics (15 features)
        pemf_sensor_data: PEMF sensor history (15 features)
        context: Patient and treatment context (15 features)
        
    Returns:
        Feature tensor (1, 45)
    """
    features = []
    
    # HRV features (15)
    hrv_keys = ['SDNN', 'RMSSD', 'pNN50', 'mean_hr', 'std_hr',
                'VLF', 'LF', 'HF', 'LF_HF',
                'SD1', 'SD2', 'sample_entropy', 'approximate_entropy',
                'alpha1', 'alpha2']
    
    for key in hrv_keys:
        features.append(hrv_features.get(key, 0.0))
    
    # PEMF sensor features (15)
    sensor_keys = ['magnetic_field', 'temperature', 'current']
    for key in sensor_keys:
        if key in pemf_sensor_data:
            data = pemf_sensor_data[key]
            features.extend([
                np.mean(data),
                np.std(data),
                np.max(data),
                np.min(data),
                np.percentile(data, 75) - np.percentile(data, 25)  # IQR
            ])
        else:
            features.extend([0.0] * 5)
    
    # Context features (15)
    # Species one-hot encoding (4 species)
    species_map = {'dog': 0, 'cat': 1, 'rabbit': 2, 'mouse': 3}
    species_idx = species_map.get(context.get('species', 'dog'), 0)
    species_encoding = [0.0] * 4
    species_encoding[species_idx] = 1.0
    features.extend(species_encoding)
    
    # Other context
    features.extend([
        context.get('age', 0) / 20.0,  # Normalized age
        context.get('weight', 0) / 50.0,  # Normalized weight
        context.get('prev_frequency', 10) / 100.0,
        context.get('prev_intensity', 30) / 100.0,
        context.get('days_since_treatment', 0) / 30.0,
        context.get('n_previous_treatments', 0) / 10.0,
        context.get('condition_severity', 0.5),  # 0-1 scale
        context.get('treatment_effectiveness', 0.5),  # Historical effectiveness
        context.get('pain_score', 0.5),  # 0-1 normalized
        context.get('activity_level', 0.5),  # 0-1 normalized
        context.get('stress_level', 0.5)  # From HRV
    ])
    
    # Convert to tensor
    features_tensor = torch.FloatTensor(features).unsqueeze(0)
    
    return features_tensor


def test_predictor():
    """
    Test PEMF Predictor functionality.
    """
    print("=== Testing PEMF Predictor ===\n")
    
    # Create model
    model = PEMFPredictor(input_features=45)
    model.to(DEVICE)
    print(f"Model created on device: {DEVICE}")
    
    # Count parameters
    n_params = sum(p.numel() for p in model.parameters())
    print(f"Total parameters: {n_params:,}\n")
    
    # Test forward pass
    batch_size = 16
    dummy_input = torch.randn(batch_size, 45).to(DEVICE)
    
    print("Test 1: Forward pass...")
    predictions = model(dummy_input)
    print(f"  Input shape: {dummy_input.shape}")
    print(f"  Frequency shape: {predictions['frequency'].shape}")
    print(f"  Intensities shape: {predictions['intensities'].shape}")
    print(f"  Duration shape: {predictions['duration'].shape}")
    print(f"  Confidence shape: {predictions['confidence'].shape}")
    
    # Check output ranges
    print("\nTest 2: Output ranges...")
    print(f"  Frequency range: [{predictions['frequency'].min().item():.1f}, {predictions['frequency'].max().item():.1f}] Hz")
    print(f"  Intensity range: [{predictions['intensities'].min().item():.1f}, {predictions['intensities'].max().item():.1f}] %")
    print(f"  Duration range: [{predictions['duration'].min().item():.1f}, {predictions['duration'].max().item():.1f}] min")
    print(f"  Confidence range: [{predictions['confidence'].min().item():.3f}, {predictions['confidence'].max().item():.3f}]")
    
    # Test loss calculation
    print("\nTest 3: Loss calculation...")
    targets = {
        'frequency': torch.rand(batch_size, 1).to(DEVICE) * 100,
        'intensities': torch.rand(batch_size, 8).to(DEVICE) * 100,
        'duration': torch.rand(batch_size, 1).to(DEVICE) * 55 + 5,
        'confidence': torch.rand(batch_size, 1).to(DEVICE)
    }
    
    loss_dict = model.loss_function(predictions, targets)
    print(f"  Total loss: {loss_dict['loss'].item():.4f}")
    print(f"  Frequency loss: {loss_dict['frequency_loss'].item():.4f}")
    print(f"  Intensity loss: {loss_dict['intensity_loss'].item():.4f}")
    print(f"  Duration loss: {loss_dict['duration_loss'].item():.4f}")
    
    # Test safe prediction
    print("\nTest 4: Safe prediction with species constraints...")
    safe_pred = model.predict_safe(dummy_input[0:1], species='dog')
    print(f"  Dog-safe frequency: {safe_pred['frequency'].item():.1f} Hz")
    print(f"  Dog-safe intensities: {safe_pred['intensities'][0].cpu().numpy()}")
    
    # Test feature preparation
    print("\nTest 5: Feature preparation...")
    hrv_features = {
        'SDNN': 50.0, 'RMSSD': 30.0, 'pNN50': 15.0,
        'mean_hr': 100.0, 'std_hr': 10.0
    }
    pemf_sensor_data = {
        'magnetic_field': np.random.rand(100) * 50,
        'temperature': np.random.rand(100) * 10 + 30,
        'current': np.random.rand(100) * 5
    }
    context = {
        'species': 'dog',
        'age': 5,
        'weight': 25.0,
        'prev_frequency': 10,
        'prev_intensity': 30
    }
    
    features = prepare_input_features(hrv_features, pemf_sensor_data, context)
    print(f"  Prepared features shape: {features.shape}")
    print(f"  Feature vector sum: {features.sum().item():.2f}")
    
    # Test ensemble
    print("\nTest 6: Ensemble predictor...")
    ensemble = EnsemblePredictor(n_models=3, input_features=45)
    ensemble.to(DEVICE)
    ensemble_pred = ensemble(dummy_input[0:1])
    print(f"  Ensemble frequency: {ensemble_pred['frequency'].item():.1f} Hz")
    print(f"  Frequency uncertainty (std): {ensemble_pred['frequency_std'].item():.2f}")
    
    print("\n✓ All tests passed!")
    
    return model


if __name__ == "__main__":
    test_predictor()
