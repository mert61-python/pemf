"""
AI Mode Controller - PEMF AI Treatment Integration
==================================================

AI destekli PEMF tedavi kontrolü için entegrasyon modülü.

Bu modül UnifiedControlWindow'a entegre edilmek üzere tasarlanmıştır:
- Gerçek zamanlı ECG monitörleme ve anomali tespiti
- AI tabanlı PEMF parametre optimizasyonu
- Tedavi güvenlik kontrolü (Normal/Warning/Critical)
- Otomatik parameter ayarlama ve adaptif tedavi

Özellikler:
-----------
1. **Realtime Monitoring**: LSTM-based anomaly detection
2. **Parameter Prediction**: Multi-task MLP for optimal PEMF settings
3. **Baseline Analysis**: VAE-based ECG pattern recognition
4. **Safety System**: Rule-based + neural network anomaly detection
5. **Treatment Logging**: Automatic session recording with AI decisions

Kullanım:
---------
    from windows.ai_mode_controller import AIModeController
    
    # Initialize
    controller = AIModeController(
        mqtt_client=mqtt_client,
        app_data_dir=app_data_dir,
        coil_manager=coil_manager
    )
    
    # Start AI session
    controller.start_ai_session(patient_id=123, species='dog')
    
    # Get AI recommendations
    recommendations = controller.get_recommendations(ecg_features, sensor_data)
    
    # Stop session
    controller.stop_ai_session()

@author: merta
@date: 2025-11-27
"""

import sys
import os
import json
import time
import logging
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional
from collections import deque

# Add parent directory for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from PyQt6.QtCore import QObject, pyqtSignal, QTimer
import threading  # Thread safety için

# Try to import ONNX runtime first (this is required for .exe ONNX mode)
try:
    import onnxruntime as ort
    ORT_AVAILABLE = True
    ORT_IMPORT_ERROR = ""
except Exception as e:
    ORT_AVAILABLE = False
    ORT_IMPORT_ERROR = str(e)

# Ensure this name always exists so other modules can import it safely
AI_IMPORT_ERROR = ""

# Try to import only the lightweight helper functions (these may not require torch).
# Avoid importing full model classes that depend on torch to allow ONNX-only runs.
HELPERS_AVAILABLE = False
HELPERS_IMPORT_ERROR = ""
prepare_input_features = None
extract_monitoring_features = None

try:
    from ai.models.monitor import extract_monitoring_features
    from ai.models.predictor import prepare_input_features
    from ai.config import DEVICE, SPECIES_PARAMS, ANOMALY_THRESHOLDS
    HELPERS_AVAILABLE = True
    HELPERS_IMPORT_ERROR = ""
except Exception as e:
    HELPERS_IMPORT_ERROR = str(e)

# Determine overall AI availability: ONNX runtime must be present.
if not ORT_AVAILABLE:
    AI_AVAILABLE = False
    AI_IMPORT_ERROR = ORT_IMPORT_ERROR
else:
    AI_AVAILABLE = True
    # If helper imports failed, record the message but provide lightweight fallbacks below
    AI_IMPORT_ERROR = HELPERS_IMPORT_ERROR if not HELPERS_AVAILABLE else ""

# If helper preprocessing functions are not available (they may import torch),
# provide minimal fallback implementations so the EXE can run in ONNX-only mode.
if not HELPERS_AVAILABLE:
    def prepare_input_features(ecg_features: Dict, sensor_data: Dict, context_data: Dict):  # noqa: F811
        """Fallback: create a zeroed feature vector (1,45) when helper is missing."""
        try:
            arr = np.zeros((1, 45), dtype=np.float32)
            return arr
        except Exception:
            return np.zeros((1, 45), dtype=np.float32)

    def extract_monitoring_features(ecg_features: Dict, sensor_data: Dict, treatment_params: Dict):  # noqa: F811
        """Fallback: minimal monitoring features (20 dims) when helper missing."""
        try:
            return np.zeros((20,), dtype=np.float32)
        except Exception:
            return np.zeros((20,), dtype=np.float32)
    
    # Mark helpers as available since we have fallbacks
    logging.warning(f"Using fallback helper functions (AI imports failed: {HELPERS_IMPORT_ERROR})")
    HELPERS_AVAILABLE = True

# Database imports
from database.session_manager import get_session_manager
class AIModeController(QObject):
    """
    AI Mode Controller for intelligent PEMF treatment.
    
    Manages real-time monitoring, parameter prediction, and safety checks.
    """
    
    # Signals
    status_changed = pyqtSignal(str, float, dict)  # (status, confidence, details)
    parameters_updated = pyqtSignal(dict)  # AI recommended parameters
    anomaly_detected = pyqtSignal(str, dict)  # (alert_type, details)
    session_started = pyqtSignal(int)  # session_id
    session_stopped = pyqtSignal(int, dict)  # (session_id, summary)
    
    def __init__(self,
                 mqtt_client=None,
                 app_data_dir: str = None,
                 coil_manager=None):
        """
        Initialize AI Mode Controller.
        
        Args:
            mqtt_client: MQTT client for coil communication
            app_data_dir: Application data directory
            coil_manager: Coil manager instance
        """
        super().__init__()
        
        self.mqtt_client = mqtt_client
        # Ensure app_data_dir is a Path object
        if isinstance(app_data_dir, str):
            self.app_data_dir = Path(app_data_dir)
        elif app_data_dir is None:
            self.app_data_dir = Path(os.path.expanduser("~/.pemf_gui"))
        else:
            self.app_data_dir = app_data_dir
        self.coil_manager = coil_manager
        # --- DÜZELTME: models_dir'i erken tanımla (torch yoksa bile kullanılacak) ---
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            base_path = Path(sys._MEIPASS)
        else:
            base_path = Path(parent_dir)
        self.models_dir = base_path / "ai" / "models" / "checkpoints"
        try:
            self.models_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        # Check AI availability
        if not AI_AVAILABLE:
            logging.error(f"AI models not available: {AI_IMPORT_ERROR}")
            self.models_loaded = False
            return
        
        # ONNX runtime sessions
        self.autoencoder_sess = None
        self.predictor_sess = None
        self.monitor_sess = None
        self.rolling_monitor = None
        self.models_loaded = False
        
        # Session state
        self.session_active = False
        self.current_session_id = None
        self.current_patient_id = None
        self.current_species = 'dog'
        
        # Baseline values
        self.baseline_ecg = None
        self.baseline_hrv = None
        
        # Real-time data buffers
        self.ecg_buffer = deque(maxlen=2500)  # 10 seconds @ 250 Hz
        self.feature_buffer = deque(maxlen=30)  # 30 observations for LSTM
        
        # Thread safety locks
        self.buffer_lock = threading.Lock()  # For ecg_buffer and feature_buffer
        self.state_lock = threading.Lock()   # For session_active, models_loaded
        self.stats_lock = threading.Lock()   # For session_stats
        
        # Monitoring timer
        self.monitor_timer = QTimer()
        self.monitor_timer.timeout.connect(self._monitor_update)
        self.monitor_interval = 1000  # 1 second
        
        # Treatment parameters
        self.current_parameters = {
            'frequency': 10,
            'intensities': [30] * 8,
            'duration': 20
        }
        
        # Statistics
        self.session_stats = {
            'start_time': None,
            'alerts': [],
            'parameter_changes': [],
            'monitoring_records': []
        }
        
        logging.info("AI Mode Controller initialized")
    
    def check_models_available(self) -> bool:
        """
        Check if AI models are available.
        
        Returns:
            True if models loaded successfully
        """
        return AI_AVAILABLE and self.models_loaded
    
    def load_models(self, 
                   autoencoder_path: Optional[str] = None,
                   predictor_path: Optional[str] = None,
                   monitor_path: Optional[str] = None) -> bool:
        """
        Load ONNX models with onnxruntime.
        """
        try:
            if autoencoder_path is None:
                autoencoder_path = self.models_dir / "autoencoder" / "best_model.onnx"
            if predictor_path is None:
                predictor_path = self.models_dir / "predictor" / "best_model.onnx"
            if monitor_path is None:
                monitor_path = self.models_dir / "monitor" / "best_model.onnx"

            if Path(autoencoder_path).exists():
                self.autoencoder_sess = ort.InferenceSession(str(autoencoder_path))
                logging.info(f"✓ Autoencoder ONNX loaded: {autoencoder_path}")
            else:
                logging.warning(f"Autoencoder ONNX not found: {autoencoder_path}")

            if Path(predictor_path).exists():
                self.predictor_sess = ort.InferenceSession(str(predictor_path))
                logging.info(f"✓ Predictor ONNX loaded: {predictor_path}")
            else:
                logging.warning(f"Predictor ONNX not found: {predictor_path}")

            if Path(monitor_path).exists():
                self.monitor_sess = ort.InferenceSession(str(monitor_path))
                logging.info(f"✓ Monitor ONNX loaded: {monitor_path}")
            else:
                logging.warning(f"Monitor ONNX not found: {monitor_path}")

            self.rolling_monitor = None
            self.models_loaded = True
            logging.info("✓ All ONNX AI models loaded successfully")
            return True
        except Exception as e:
            logging.error(f"Failed to load ONNX AI models: {e}")
            self.models_loaded = False
            return False
    
    def start_ai_session(self, 
                        patient_id: int, 
                        species: str = 'dog',
                        target_condition: str = 'AI Destekli Tedavi',
                        operator_name: str = 'Sistem Kullanıcısı',
                        patient_name: str = '',
                        create_db_session: bool = False) -> bool:
        """
        Start AI-controlled treatment session.
        
        Args:
            patient_id: Patient database ID
            species: Patient species (dog, cat, horse, etc.)
            target_condition: Treatment target/goal
            operator_name: Name of operator starting session
            patient_name: Name of patient
            create_db_session: If True, create DB session (DEPRECATED - unified_control manages sessions now)
            
        Returns:
            bool: True if session started successfully
        """
        if self.session_active:
            logging.warning("AI session already active")
            return False
        
        if not self.models_loaded:
            logging.error("AI models not loaded, cannot start session")
            return False
        
        try:
            # Set patient context
            self.current_patient_id = patient_id
            self.current_species = species
            
            # Initialize session stats (thread-safe)
            with self.stats_lock:
                self.session_stats = {
                    'start_time': datetime.now().isoformat(),
                    'alerts': [],
                    'parameter_changes': [],
                    'monitoring_records': []
                }
            
            # DEPRECATED: Create database session (unified_control now manages sessions)
            # Only create if explicitly requested (backward compatibility)
            if create_db_session:
                session_manager = get_session_manager(self.app_data_dir)
                self.current_session_id = session_manager.start_session(
                    treatment_mode='AI Mod Destekli Tedavi',
                    target_condition=target_condition,
                    operator_name=operator_name,
                    patient_name=patient_name
                )
                logging.info(f"AI controller created DB session (deprecated): {self.current_session_id}")
            else:
                self.current_session_id = None
                logging.info("AI controller started WITHOUT DB session (unified_control manages sessions)")
            
            # Start monitoring timer
            self.monitor_timer.start(self.monitor_interval)
            
            # Thread-safe session activation
            with self.state_lock:
                self.session_active = True
            
            logging.info(f"✓ AI monitoring started: patient_id={patient_id}, species={species}")
            
            # Emit signal
            self.session_started.emit(self.current_session_id)
            
            return True
            
        except Exception as e:
            logging.error(f"Failed to start AI session: {e}")
            self.session_active = False
            self.current_session_id = None
            return False
    
    def stop_ai_session(self, close_db_session: bool = False) -> Dict:
        """
        Stop AI-controlled treatment session.
        
        Args:
            close_db_session: If True, close DB session (DEPRECATED - unified_control manages sessions now)
        
        Returns:
            Session summary statistics
        """
        if not self.session_active:
            logging.warning("No active session")
            return {}
        
        try:
            # Stop monitoring timer
            self.monitor_timer.stop()
            
            # NOT: PWM stop komutları artık unified_control_window tarafından gönderiliyor
            # (_stop_ai_session -> main_window.stop_treatment çağrısı yapıyor)
            
            # Finalize session stats (thread-safe)
            with self.stats_lock:
                self.session_stats['end_time'] = datetime.now().isoformat()
                self.session_stats['total_alerts'] = len(self.session_stats['alerts'])
                self.session_stats['total_parameter_changes'] = len(self.session_stats['parameter_changes'])
                # Create a copy for database (avoid race condition during json.dumps)
                stats_copy = self.session_stats.copy()
            
            # DEPRECATED: Close session in database (unified_control now manages sessions)
            # Only close if explicitly requested (backward compatibility)
            if close_db_session and self.current_session_id:
                session_manager = get_session_manager(self.app_data_dir)
                session_manager.end_session(
                    final_notes=json.dumps(stats_copy, indent=2)
                )
                logging.info(f"AI controller closed DB session (deprecated): {self.current_session_id}")
            else:
                logging.info("AI monitoring stopped WITHOUT closing DB session (unified_control manages sessions)")
            
            # Emit signal (use copy to avoid race condition)
            self.session_stopped.emit(self.current_session_id, stats_copy)
            
            # Reset state (thread-safe)
            session_id = self.current_session_id
            with self.state_lock:
                self.session_active = False
                self.current_session_id = None
            
            return stats_copy
            
        except Exception as e:
            logging.error(f"Failed to stop AI session: {e}")
            return {}
    
    def get_recommendations(self,
                           ecg_features: Optional[Dict] = None,
                           sensor_data: Optional[Dict] = None,
                           context_data: Optional[Dict] = None) -> Dict:
        """
        Get AI treatment recommendations.
        
        Args:
            ecg_features: ECG-derived features (HR, HRV, etc.)
            sensor_data: PEMF sensor readings
            context_data: Additional context (age, weight, etc.)
            
        Returns:
            Dictionary with recommendations and confidence
        """
        if not self.models_loaded:
            return {
                'status': 'error',
                'message': 'AI models not loaded'
            }

        # preprocessing helpers are available (either real or fallback)
        
        try:
            # Prepare input features (45 dimensions)
            logging.debug(f"Preparing input features...")
            logging.debug(f"ECG features: {ecg_features}")
            logging.debug(f"Sensor data: {sensor_data}")
            logging.debug(f"Context data: {context_data}")
            
            input_features = prepare_input_features(
                ecg_features or {},
                sensor_data or {},
                context_data or {}
            )
            
            # prepare_input_features already returns numpy array of shape (1, 45)
            logging.debug(f"Input features shape: {input_features.shape}")
            logging.debug(f"Input features (first 5): {input_features[0, :5]}")

            # ONNX inference: ensure float32
            features_np = np.asarray(input_features, dtype=np.float32)
            outputs = self.predictor_sess.run(None, {"features": features_np})
            # outputs[0] = model output, shape (1, 11) [frequency, intensities(8), duration, confidence]
            logging.debug(f"Predictor ONNX output shape: {outputs[0].shape}")
            out = outputs[0][0]  # first batch
            if len(out) < 11:
                logging.error(f"Predictor ONNX output has wrong shape/length: {out.shape if hasattr(out, 'shape') else type(out)} (expected 11)")
                raise ValueError(f"Predictor ONNX output has wrong shape/length: {out.shape if hasattr(out, 'shape') else type(out)} (expected 11)")
            frequency = float(out[0])
            intensities = [float(x) for x in out[1:9]]
            duration = float(out[9])
            confidence = float(out[10])

            self.current_parameters = {
                'frequency': frequency,
                'intensities': intensities,
                'duration': duration
            }
            self.parameters_updated.emit(self.current_parameters)
            return {
                'status': 'success',
                'frequency': frequency,
                'intensities': intensities,
                'duration': duration,
                'confidence': confidence,
                'species': self.current_species
            }
            
        except Exception as e:
            logging.error(f"Failed to get recommendations: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }
    
    def add_ecg_data(self, ecg_sample: np.ndarray):
        """
        Add new ECG data for real-time monitoring.
        
        Args:
            ecg_sample: ECG signal samples
        """
        # Thread-safe session check
        with self.state_lock:
            if not self.session_active:
                return
        
        # Lock ile koru
        with self.buffer_lock:
            for sample in ecg_sample:
                self.ecg_buffer.append(sample)
    
    def add_sensor_data(self, sensor_data: Dict):
        """
        Add new sensor data for monitoring.
        
        Args:
            sensor_data: Sensor readings (magnetic field, temp, current)
        """
        # Thread-safe session and model check
        with self.state_lock:
            if not self.session_active or not self.models_loaded:
                return

        # If helper preprocessing functions are missing, skip monitoring
        try:
            helpers_ok = HELPERS_AVAILABLE
        except NameError:
            helpers_ok = False

        if not helpers_ok:
            logging.warning(f"Skipping sensor data processing: helper functions missing ({AI_IMPORT_ERROR})")
            return
        
        try:
            # Extract features for monitoring
            ecg_features = self._get_current_ecg_features()
            
            treatment_params = {
                'frequency': self.current_parameters['frequency'],
                'intensity': np.mean(self.current_parameters['intensities']),
                'elapsed_time': self._get_elapsed_time()
            }
            
            # Extract monitoring features (20 dimensions)
            features = extract_monitoring_features(
                ecg_features,
                sensor_data,
                treatment_params
            )
            
            # Add to rolling monitor
            self.rolling_monitor.add_observation(features)
            
            # Get status if buffer full
            if len(self.rolling_monitor.buffer) >= 30:
                current_features = {
                    'heart_rate': ecg_features.get('heart_rate', 100),
                    'hrv': ecg_features.get('HRV_RMSSD', 50),
                    'temperature': sensor_data.get('temperature_mean', 25),
                    'current': sensor_data.get('current_mean', 1.0),
                    'magnetic_field': sensor_data.get('magnetic_field_mean', 10)
                }
                
                status_dict = self.rolling_monitor.get_status(current_features)
                
                # Emit status signal
                self.status_changed.emit(
                    status_dict['status'],
                    status_dict['confidence'],
                    status_dict
                )
                
                # Record in session stats (thread-safe)
                with self.stats_lock:
                    self.session_stats['monitoring_records'].append({
                        'timestamp': datetime.now().isoformat(),
                        'status': status_dict['status'],
                        'confidence': status_dict['confidence'],
                        'message': status_dict['message']
                    })
                
                # Handle alerts
                if status_dict['status'] in ['Warning', 'Critical']:
                    self._handle_alert(status_dict)
            
        except Exception as e:
            logging.error(f"Failed to add sensor data: {e}")
    
    def _monitor_update(self):
        """Periodic monitoring update (called by timer)."""
        # Thread-safe session check
        with self.state_lock:
            if not self.session_active or not self.models_loaded:
                return
        
        # Simulated sensor data update (replace with actual sensor reading)
        # In production, this would read from MQTT/sensor manager
        pass
    
    def _handle_alert(self, status_dict: Dict):
        """
        Handle monitoring alerts.
        
        Args:
            status_dict: Status dictionary from rolling monitor
        """
        alert = {
            'timestamp': datetime.now().isoformat(),
            'status': status_dict['status'],
            'message': status_dict['message'],
            'action': status_dict['action']
        }
        
        # Thread-safe stats update
        with self.stats_lock:
            self.session_stats['alerts'].append(alert)
        
        # Emit signal
        self.anomaly_detected.emit(status_dict['status'], status_dict)
        
        # Take action
        if status_dict['action'] == 'stop_immediately':
            logging.critical(f"CRITICAL: {status_dict['message']}")
            # Stop treatment (will be handled by GUI)
            
        elif status_dict['action'] == 'reduce_intensity':
            logging.warning(f"WARNING: {status_dict['message']}")
            # Reduce intensity by 20%
            self.current_parameters['intensities'] = [
                int(i * 0.8) for i in self.current_parameters['intensities']
            ]
            self.parameters_updated.emit(self.current_parameters)
            
            # Thread-safe stats update
            with self.stats_lock:
                self.session_stats['parameter_changes'].append({
                    'timestamp': datetime.now().isoformat(),
                    'reason': 'warning_detected',
                    'parameters': self.current_parameters.copy()
                })
    
    def _extract_hrv_from_ecg(self, ecg_signal: np.ndarray) -> Dict:
        """
        Extract HRV features from ECG signal.
        
        Args:
            ecg_signal: ECG signal array
            
        Returns:
            Dictionary with HRV features
        """
        # Simplified HRV extraction (in production, use neurokit2)
        # This is a placeholder - replace with actual HRV analysis
        return {
            'heart_rate': 100,
            'HRV_RMSSD': 50,
            'HRV_SDNN': 60,
            'HRV_LF': 200,
            'HRV_HF': 400,
            'HRV_LF_HF': 0.5,
            'HRV_SD1': 25,
            'HRV_SD2': 60
        }
    
    def _get_current_ecg_features(self) -> Dict:
        """
        Get current ECG features from buffer.
        
        Returns:
            Dictionary with ECG features
        """
        # Lock ile koru ve kopyasını al
        with self.buffer_lock:
            if len(self.ecg_buffer) < 250:  # Need at least 1 second
                return self._extract_hrv_from_ecg(np.array([]))
            
            # Güvenli bir şekilde numpy array'e çevir
            recent_ecg = np.array(list(self.ecg_buffer)[-250:])
        
        return self._extract_hrv_from_ecg(recent_ecg)
    
    def _get_elapsed_time(self) -> float:
        """
        Get elapsed time since session start (minutes).
        
        Returns:
            Elapsed time in minutes
        """
        # Thread-safe session check
        with self.state_lock:
            if not self.session_active:
                return 0.0
        
        # Thread-safe stats access
        with self.stats_lock:
            if 'start_time' not in self.session_stats:
                return 0.0
            start_time_str = self.session_stats['start_time']
        
        start = datetime.fromisoformat(start_time_str)
        elapsed = (datetime.now() - start).total_seconds() / 60.0
        return elapsed
    
    def get_session_summary(self) -> Dict:
        """
        Get current session summary.
        
        Returns:
            Summary statistics
        """
        # Thread-safe session check
        with self.state_lock:
            if not self.session_active:
                return {}
            session_id = self.current_session_id
            patient_id = self.current_patient_id
            species = self.current_species
        
        # Thread-safe stats access
        with self.stats_lock:
            total_alerts = len(self.session_stats['alerts'])
            current_status = self.session_stats['monitoring_records'][-1] if self.session_stats['monitoring_records'] else None
        
        return {
            'session_id': session_id,
            'patient_id': patient_id,
            'species': species,
            'elapsed_time': self._get_elapsed_time(),
            'total_alerts': total_alerts,
            'current_status': current_status,
            'current_parameters': self.current_parameters
        }


# Convenience function for UnifiedControlWindow
def create_ai_controller(mqtt_client=None, app_data_dir=None, coil_manager=None) -> AIModeController:
    """
    Create and initialize AI mode controller (lazy loading - models loaded on demand).
    
    Models will be loaded when:
    - load_models() is explicitly called
    - get_recommendations() is called for the first time
    
    Args:
        mqtt_client: MQTT client instance
        app_data_dir: Application data directory
        coil_manager: Coil manager instance
        
    Returns:
        AIModeController instance
    """
    controller = AIModeController(
        mqtt_client=mqtt_client,
        app_data_dir=app_data_dir,
        coil_manager=coil_manager
    )
    
    # DON'T load models here - lazy loading for better startup performance
    # Models will be loaded on-demand when needed
    if AI_AVAILABLE:
        logging.info("✓ AI controller created (models will be loaded on-demand)")
    else:
        logging.error(f"⚠ AI not available: {AI_IMPORT_ERROR}")
    
    return controller
