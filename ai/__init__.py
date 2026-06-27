"""
AI Module for PEMF Veterinary Treatment System
==============================================

This module provides AI-powered analysis and recommendations for PEMF treatments
using veterinary ECG data and real-time sensor monitoring.

Modules:
--------
- data: Dataset downloading and preprocessing
- models: Neural network architectures
- training: Model training pipelines
- inference: Real-time prediction and monitoring
- utils: Utility functions and helpers

Author: PEMF AI System
Version: 1.0.0
"""

__version__ = "1.0.0"
__author__ = "PEMF AI System"

from . import config

__all__ = ["config"]
