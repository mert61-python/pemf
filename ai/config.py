"""
AI System Configuration
Contains all configuration parameters for the PEMF AI system including
dataset URLs, model hyperparameters, and system paths.
"""

import logging
import os

try:
    import torch
except ImportError:
    torch = None
from pathlib import Path

logger = logging.getLogger(__name__)

# ==================== DIRECTORY STRUCTURE ====================
BASE_DIR = Path(__file__).parent

# Program Files içinde yazma izni (PermissionError) hatası almamak için 
# çalışma zamanı (runtime) dosyaları kullanıcı dizininde (APPDATA) saklanmalıdır.
_app_data_base = Path(os.environ.get("APPDATA", os.path.expanduser("~"))) / "PEMF_GUI" / "ai"

DATA_DIR = _app_data_base / "data" / "datasets"
MODELS_DIR = _app_data_base / "models" / "saved_models"
LOGS_DIR = _app_data_base / "logs"
RESULTS_DIR = _app_data_base / "results"

# Create directories if they don't exist
try:
    for directory in [DATA_DIR, MODELS_DIR, LOGS_DIR, RESULTS_DIR]:
        directory.mkdir(parents=True, exist_ok=True)
except Exception:
    pass

# ==================== DATASET CONFIGURATION ====================
DATASETS = {
    "physiozoo": {
        "name": "PhysioZoo",
        "url": "https://physionet.org/static/published-projects/",
        "github": "https://github.com/physiozoo/physiozoo",
        "description": "Dog, rabbit, and mouse ECG database with MATLAB toolbox (MHRV)",
        "species": ["dog", "rabbit", "mouse"],
        "format": "wfdb",
        "local_path": DATA_DIR / "physiozoo",
        "features": ["HRV time/freq/nonlinear", "R-peak detection", "RR filtering", "DFA", "MSE"]
    },
    "zenodo_paws": {
        "name": "Zenodo Paws in Pain",
        "url": "https://zenodo.org/record/",
        "description": "Dog pain assessment with ECG correlation",
        "species": ["dog"],
        "format": "csv",
        "local_path": DATA_DIR / "zenodo_paws"
    },
    "mitbih": {
        "name": "MIT-BIH Arrhythmia Database",
        "url": "https://physionet.org/content/mitdb/1.0.0/",
        "description": "Human ECG for transfer learning",
        "species": ["human"],
        "format": "wfdb",
        "local_path": DATA_DIR / "mitbih"
    },
    "alivecor": {
        "name": "AliveCor Veterinary",
        "url": "https://www.alivecor.com/",
        "description": "Veterinary ECG validation dataset",
        "species": ["dog", "cat"],
        "format": "proprietary",
        "local_path": DATA_DIR / "alivecor"
    }
}

# ==================== SYNTHETIC DATA GENERATION (GAN) ====================
SYNTHETIC_DATA = {
    "enabled": True,  # Enable synthetic data augmentation
    "methods": {
        "p2e_wgan": {
            "name": "P2E-WGAN (PPG to ECG)",
            "github": "https://github.com/khuongav/P2E-WGAN-ecg-ppg-reconstruction",
            "description": "Generate ECG from PPG using Wasserstein GAN-GP",
            "use_case": "Data augmentation when ECG unavailable but PPG exists",
            "paper": "ACM SAC 2021",
            "architecture": "1D CNN Generator/Discriminator with feature-based loss"
        },
        "eeg_wgan": {
            "name": "EEG/ECG WGAN-GP",
            "github": "https://github.com/JoshParkSJ/eeg-wgan",
            "description": "Generate synthetic biosignals (EEG/ECG) with WGAN-GP",
            "use_case": "Augment limited veterinary ECG datasets",
            "paper": "https://arxiv.org/abs/2402.09453",
            "architecture": "WGAN-GP with gradient penalty for stable training"
        },
        "neurokit2_simulation": {
            "name": "NeuroKit2 Synthetic ECG",
            "github": "https://github.com/neuropsychology/NeuroKit",
            "description": "Simulate realistic ECG signals with custom parameters",
            "use_case": "Generate species-specific synthetic ECG for testing",
            "features": ["Adjustable HR", "Noise control", "Artifact injection"]
        }
    },
    "augmentation_ratio": 0.3,  # 30% synthetic data in training set
    "validation_only_real": True  # Use only real data for validation
}

# ==================== EXTERNAL TOOLS & LIBRARIES ====================
EXTERNAL_TOOLS = {
    "physiozoo_mhrv": {
        "name": "PhysioZoo MHRV Toolbox",
        "language": "MATLAB",
        "github": "https://github.com/physiozoo/mhrv",
        "features": [
            "WFDB wrappers (gqrs, rdsamp, rdann, wrann)",
            "ECG peak detection (rqrs - configurable for animals)",
            "HRV time domain (AVNN, SDNN, RMSSD, pNNx)",
            "HRV frequency domain (VLF, LF, HF with Lomb/AR/Welch/FFT)",
            "HRV nonlinear (DFA alpha1/alpha2, Sample Entropy, MSE, Poincaré SD1/SD2)",
            "RR interval filtering (ectopic beat detection)",
            "Fragmentation analysis"
        ],
        "python_alternative": "Use biosppy, wfdb, neurokit2 for equivalent functionality"
    },
    "neurokit2": {
        "name": "NeuroKit2",
        "language": "Python",
        "github": "https://github.com/neuropsychology/NeuroKit",
        "pip": "pip install neurokit2",
        "features": [
            "ECG processing (simulate, process, analyze, delineate P/Q/S/T waves)",
            "HRV analysis (all standard metrics)",
            "PPG, RSP, EDA, EMG, EOG support",
            "Event-related and interval-related analysis",
            "Signal simulation with realistic artifacts",
            "Complexity measures (entropy, fractal dimensions)",
            "2000+ stars, actively maintained"
        ],
        "integration": "Use as primary biosignal processing library alongside biosppy"
    }
}

# ==================== SIGNAL PROCESSING PARAMETERS ====================
SIGNAL_PROCESSING = {
    "sampling_rate": 250,  # Hz - Standard for veterinary ECG
    "bandpass_filter": {
        "lowcut": 0.5,  # Hz - Remove baseline wander
        "highcut": 50.0,  # Hz - Remove high-frequency noise
        "order": 4  # Butterworth filter order
    },
    "notch_filter": {
        "freq": 50.0,  # Hz - Remove powerline interference (50Hz EU, 60Hz US)
        "quality_factor": 30.0
    },
    "window_size": 10,  # seconds - ECG analysis window
    "overlap": 0.5  # 50% overlap between windows
}

# ==================== HRV FEATURE EXTRACTION ====================
HRV_FEATURES = {
    "time_domain": [
        "SDNN",      # Standard deviation of NN intervals
        "RMSSD",     # Root mean square of successive differences
        "pNN50",     # Percentage of NN intervals > 50ms different
        "mean_hr",   # Mean heart rate
        "std_hr"     # Standard deviation of heart rate
    ],
    "frequency_domain": [
        "VLF",       # Very low frequency power (0.003-0.04 Hz)
        "LF",        # Low frequency power (0.04-0.15 Hz)
        "HF",        # High frequency power (0.15-0.4 Hz)
        "LF_HF"      # LF/HF ratio (autonomic balance)
    ],
    "nonlinear": [
        "SD1",       # Poincaré plot - short-term variability
        "SD2",       # Poincaré plot - long-term variability
        "sample_entropy",  # Complexity measure
        "approximate_entropy"  # Regularity measure
    ]
}

# ==================== PEMF SENSOR FEATURES ====================
PEMF_FEATURES = {
    "magnetic_field": {
        "unit": "mT",  # millitesla
        "range": [0, 100],  # Expected range
        "features": ["mean", "std", "max", "min", "trend"]
    },
    "temperature": {
        "unit": "°C",
        "range": [20, 80],  # Safe operating range
        "features": ["mean", "std", "max", "delta"]
    },
    "current": {
        "unit": "A",
        "range": [0, 30],  # Maximum current
        "features": ["mean", "std", "max", "rms"]
    },
    "pwm": {
        "unit": "%",
        "range": [0, 100],
        "features": ["mean", "std", "duty_cycle"]
    }
}

# ==================== TREATMENT PARAMETERS ====================
TREATMENT_PARAMS = {
    "frequency_range": [50, 150],  # Hz - PEMF frequency range (minimum 50 Hz - cihaz kısıtı)
    "intensity_range": [0, 100],  # % - PWM duty cycle range
    "duration_range": [5, 60],    # minutes
    "coil_count": 8,              # Number of available coils
    "default_frequency": 50,      # Hz - Safe default (cihaz minimumu)
    "default_intensity": 30       # % - Conservative start
}

# ==================== MODEL ARCHITECTURES ====================
MODELS = {
    "ecg_autoencoder": {
        "input_size": 2500,  # 10 seconds at 250 Hz
        "hidden_layers": [512, 256, 128, 64],
        "latent_dim": 32,
        "activation": "relu",
        "dropout": 0.2,
        "batch_norm": True
    },
    "pemf_predictor": {
        "input_features": 45,  # 15 HRV + 15 PEMF sensor + 15 context
        "hidden_layers": [256, 128, 64, 32],
        "output_size": 11,  # freq(1) + 8_intensities + duration(1) + confidence(1)
        "activation": "relu",
        "dropout": 0.3,
        "batch_norm": True
    },
    "realtime_monitor": {
        "sequence_length": 30,  # 30 time steps
        "input_features": 20,   # Combined ECG + PEMF features
        "lstm_hidden": 64,
        "lstm_layers": 2,
        "output_size": 3,  # Normal, Warning, Critical
        "dropout": 0.2,
        "bidirectional": True
    }
}

# ==================== TRAINING CONFIGURATION ====================
TRAINING = {
    "batch_size": 32,
    "epochs": 100,
    "learning_rate": 0.001,
    "weight_decay": 1e-5,
    "scheduler": {
        "type": "ReduceLROnPlateau",
        "patience": 10,
        "factor": 0.5,
        "min_lr": 1e-6
    },
    "early_stopping": {
        "patience": 20,
        "min_delta": 0.001
    },
    "validation_split": 0.2,
    "test_split": 0.1,
    "random_seed": 42
}

# ==================== DEVICE CONFIGURATION ====================
def get_device():
    """
    Returns 'cpu' for GUI/ONNX-only builds (no torch dependency).
    """
    if torch is not None:
        if hasattr(torch, 'cuda') and torch.cuda.is_available():
            device = torch.device("cuda")
            logger.info("Using GPU: %s", torch.cuda.get_device_name(0))
        elif hasattr(torch, 'backends') and hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            device = torch.device("mps")
            logger.info("Using Apple Silicon GPU")
        else:
            device = torch.device("cpu")
            logger.info("Using CPU")
        return device
    else:
        logger.info("Torch not available, using CPU (ONNX/GUI mode)")
        return 'cpu'

DEVICE = get_device()

# ==================== SPECIES-SPECIFIC PARAMETERS ====================
# Audit P3 (UYARI — güvenlik-tuzağı): Bu sözlük YALNIZCA ml_training_archive eğitim scriptlerince
# okunur; ÜRETİM backend'i (hybrid_recommender) KULLANMAZ. recommended_frequency değerleri
# (dog=10/cat=15/rabbit=20/mouse=25 Hz) cihaz donanım-MİNİMUMU 50 Hz'in ALTINDADIR → bir öneri
# motoruna/seans-başlatmaya BAĞLAMA (cihaz-altı frekans üretir). Silinecekse ml_training_archive
# import'larıyla (predictor/monitor/preprocessor/synthetic_generator/neurokit_integration) BİRLİKTE.
SPECIES_PARAMS = {
    "dog": {
        "normal_hr_range": [60, 140],  # bpm - varies by size
        "qrs_duration": [0.05, 0.08],  # seconds
        "pr_interval": [0.06, 0.13],   # seconds
        "qt_interval": [0.15, 0.25],   # seconds
        "recommended_frequency": 10,   # Hz - PEMF
        "recommended_intensity": 30    # % - Starting point
    },
    "cat": {
        "normal_hr_range": [120, 220],  # bpm
        "qrs_duration": [0.03, 0.06],
        "pr_interval": [0.05, 0.09],
        "qt_interval": [0.12, 0.18],
        "recommended_frequency": 15,
        "recommended_intensity": 25
    },
    "rabbit": {
        "normal_hr_range": [180, 250],  # bpm
        "qrs_duration": [0.02, 0.04],
        "pr_interval": [0.04, 0.07],
        "qt_interval": [0.10, 0.15],
        "recommended_frequency": 20,
        "recommended_intensity": 20
    },
    "mouse": {
        "normal_hr_range": [450, 750],  # bpm
        "qrs_duration": [0.01, 0.02],
        "pr_interval": [0.02, 0.04],
        "qt_interval": [0.05, 0.08],
        "recommended_frequency": 25,
        "recommended_intensity": 15
    }
}

# ==================== ANOMALY DETECTION THRESHOLDS ====================
ANOMALY_THRESHOLDS = {
    "hr_deviation": 0.3,  # 30% deviation from baseline
    "hrv_drop": 0.5,      # 50% drop in HRV indicates stress
    "temperature_rise": 15,  # °C - Coil overheating threshold
    "current_spike": 1.5,    # x times baseline - Protection threshold
    "magnetic_field_drift": 0.2  # 20% drift from target
}

# ==================== REPORT GENERATION ====================
REPORT_CONFIG = {
    "format": "html",  # html, pdf, json
    "include_graphs": True,
    "graph_dpi": 300,
    "sections": [
        "patient_info",
        "pre_treatment_ecg",
        "treatment_parameters",
        "realtime_monitoring",
        "post_treatment_ecg",
        "effectiveness_analysis",
        "recommendations"
    ],
    "language": "tr"  # Turkish for veterinary reports
}

# ==================== LOGGING CONFIGURATION ====================
LOGGING = {
    "level": "INFO",  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    "handlers": {
        "console": True,
        "file": True,
        "file_path": LOGS_DIR / "ai_system.log"
    },
    "max_bytes": 10485760,  # 10 MB
    "backup_count": 5
}

# ==================== API KEYS (if needed for cloud datasets) ====================
API_KEYS = {
    "physionet": os.environ.get("PHYSIONET_API_KEY", ""),
    "zenodo": os.environ.get("ZENODO_API_KEY", ""),
}

# ==================== PERFORMANCE OPTIMIZATION ====================
PERFORMANCE = {
    "num_workers": 4,  # DataLoader workers
    "pin_memory": False,
    "prefetch_factor": 2,
    "persistent_workers": True,
    "cache_preprocessed": True,  # Cache preprocessed signals
    "cache_dir": DATA_DIR / "cache"
}

if __name__ == "__main__":
    print("AI Configuration Loaded Successfully")
    print(f"Base Directory: {BASE_DIR}")
    print(f"Data Directory: {DATA_DIR}")
    print(f"Models Directory: {MODELS_DIR}")
    print(f"Device: {DEVICE}")
    print(f"\nAvailable Datasets: {list(DATASETS.keys())}")
    print(f"Available Models: {list(MODELS.keys())}")
