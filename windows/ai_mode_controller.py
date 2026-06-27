"""
AI Mode Controller - Target-Based Literature Protocols
=====================================================

This module provides a simplified AI integration for PEMF treatment.
It intentionally avoids ECG/HRV/sensor-model inference and returns
recommendations based only on the selected session target.

@author: merta
@date: 2026-03-18
"""

import os
import sys
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional

from PyQt6.QtCore import QObject, pyqtSignal

# Add parent directory for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

try:
    from ai.hybrid_recommender import get_literature_recommendation
    AI_AVAILABLE = True
    AI_IMPORT_ERROR = ""
except Exception as e:
    get_literature_recommendation = None
    AI_AVAILABLE = False
    AI_IMPORT_ERROR = str(e)


class AIModeController(QObject):
    """Minimal AI controller using only literature protocols by target."""

    # Kept for backward compatibility with UnifiedControlWindow connections
    status_changed = pyqtSignal(str, float, dict)  # (status, confidence, details)
    parameters_updated = pyqtSignal(dict)
    anomaly_detected = pyqtSignal(str, dict)
    session_started = pyqtSignal(int)
    session_stopped = pyqtSignal(int, dict)

    def __init__(self, mqtt_client=None, app_data_dir: str = None, coil_manager=None):
        super().__init__()

        self.mqtt_client = mqtt_client
        self.coil_manager = coil_manager

        if isinstance(app_data_dir, str):
            self.app_data_dir = Path(app_data_dir)
        elif app_data_dir is None:
            self.app_data_dir = Path(os.path.expanduser("~/.pemf_gui"))
        else:
            self.app_data_dir = app_data_dir

        # Keep names expected by existing UI code
        self.models_loaded = AI_AVAILABLE
        self.session_active = False
        self.current_session_id = None
        self.current_patient_id = None
        self.current_species = "dog"

        self.current_parameters = {
            "frequency": 10.0,
            "intensities": [30.0] * 8,
            "duration": 20.0,
        }

        self.session_stats = {
            "start_time": None,
            "end_time": None,
            "alerts": [],
            "parameter_changes": [],
            "monitoring_records": [],
            "mode": "target_only_literature",
        }

        logging.info("AI Mode Controller initialized (target-only literature mode)")

    def check_models_available(self) -> bool:
        """Compatibility method; no model files are required in this mode."""
        return AI_AVAILABLE

    def load_models(self,
                   autoencoder_path: Optional[str] = None,
                   predictor_path: Optional[str] = None,
                   monitor_path: Optional[str] = None) -> bool:
        """Compatibility method; returns availability for target-only mode."""
        self.models_loaded = AI_AVAILABLE
        return self.models_loaded

    def start_ai_session(self,
                        patient_id: int,
                        species: str = "dog",
                        target_condition: str = "AI Destekli Tedavi",
                        operator_name: str = "Sistem Kullanicisi",
                        patient_name: str = "",
                        create_db_session: bool = False) -> bool:
        """Start an AI session state without ECG/sensor monitoring."""
        if not AI_AVAILABLE:
            logging.error(f"AI not available: {AI_IMPORT_ERROR}")
            return False

        if self.session_active:
            logging.warning("AI session already active")
            return False

        self.current_patient_id = patient_id
        self.current_species = species or "dog"
        self.current_session_id = 0
        self.session_active = True

        self.session_stats = {
            "start_time": datetime.now().isoformat(),
            "end_time": None,
            "alerts": [],
            "parameter_changes": [],
            "monitoring_records": [],
            "mode": "target_only_literature",
            "target_condition": target_condition,
            "operator_name": operator_name,
            "patient_name": patient_name,
            "create_db_session": bool(create_db_session),
        }

        self.status_changed.emit(
            "Normal",
            1.0,
            {"message": "AI seansi aktif (literatur hedef modu)"}
        )
        self.session_started.emit(self.current_session_id)

        logging.info(
            "AI session started in target-only mode: "
            f"patient_id={patient_id}, species={self.current_species}, target={target_condition}"
        )
        return True

    def stop_ai_session(self, close_db_session: bool = False) -> Dict:
        """Stop AI session and return summary."""
        if not self.session_active:
            logging.warning("No active AI session")
            return {}

        self.session_stats["end_time"] = datetime.now().isoformat()
        self.session_stats["total_alerts"] = len(self.session_stats.get("alerts", []))
        self.session_stats["total_parameter_changes"] = len(self.session_stats.get("parameter_changes", []))
        self.session_stats["close_db_session"] = bool(close_db_session)

        summary = dict(self.session_stats)
        session_id = self.current_session_id if self.current_session_id is not None else 0

        self.session_active = False
        self.current_session_id = None

        self.session_stopped.emit(session_id, summary)
        logging.info("AI session stopped in target-only mode")
        return summary

    def get_recommendations(self,
                           treatment_target: str,
                           patient_info: Optional[Dict] = None,
                           context_data: Optional[Dict] = None) -> Dict:
        """
        Get literature-based recommendations using only session target.

        Args:
            treatment_target: Session goal selected in AI tab
            patient_info: Kept for API compatibility, ignored by design
            context_data: Kept for API compatibility, ignored by design
        """
        if not AI_AVAILABLE or not callable(get_literature_recommendation):
            return {
                "status": "error",
                "message": f"AI module unavailable: {AI_IMPORT_ERROR}",
            }

        try:
            recommendation = get_literature_recommendation(
                treatment_target=treatment_target,
                app_data_dir=self.app_data_dir,
            )

            frequency = float(recommendation["freq"])
            duty = float(recommendation["duty"])
            duration = float(recommendation["duration"])
            evidence = recommendation.get("evidence", "unknown")

            confidence_map = {
                "high": 0.95,
                "medium": 0.85,
                "interpolated": 0.70,
                "unknown": 0.60,
            }
            confidence = float(confidence_map.get(evidence, 0.60))

            self.current_parameters = {
                "frequency": frequency,
                "intensities": [duty] * 8,
                "duration": duration,
            }

            self.parameters_updated.emit(self.current_parameters)
            self.status_changed.emit(
                "Normal",
                confidence,
                {
                    "message": "Literatur protokolu uygulandi",
                    "source": recommendation.get("source", "literature_exact"),
                    "evidence": evidence,
                    "target": recommendation.get("target", ""),
                },
            )

            return {
                "status": "success",
                "frequency": frequency,
                "intensities": [duty] * 8,
                "duration": duration,
                "confidence": confidence,
                "source": recommendation.get("source", "literature_exact"),
                "evidence": evidence,
                "target": recommendation.get("target", ""),
                "species": self.current_species,
            }

        except Exception as e:
            logging.error(f"Failed to generate target-only recommendation: {e}")
            return {
                "status": "error",
                "message": str(e),
            }

    def get_session_summary(self) -> Dict:
        """Return current AI session summary."""
        if not self.session_active:
            return {}

        start_time = self.session_stats.get("start_time")
        elapsed_min = 0.0
        if start_time:
            try:
                elapsed_min = (datetime.now() - datetime.fromisoformat(start_time)).total_seconds() / 60.0
            except Exception:
                elapsed_min = 0.0

        return {
            "session_id": self.current_session_id,
            "patient_id": self.current_patient_id,
            "species": self.current_species,
            "elapsed_time": elapsed_min,
            "total_alerts": 0,
            "current_status": {"status": "Normal", "confidence": 1.0},
            "current_parameters": self.current_parameters,
            "mode": "target_only_literature",
        }


# Convenience function for UnifiedControlWindow
def create_ai_controller(mqtt_client=None, app_data_dir=None, coil_manager=None) -> AIModeController:
    """Create AI controller with target-only literature behavior."""
    controller = AIModeController(
        mqtt_client=mqtt_client,
        app_data_dir=app_data_dir,
        coil_manager=coil_manager,
    )

    if AI_AVAILABLE:
        logging.info("AI controller created (target-only literature mode)")
    else:
        logging.error(f"AI not available: {AI_IMPORT_ERROR}")

    return controller
