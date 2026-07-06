"""Shared STM32 protocol limits for GUI, AI Pro, headless, and API paths."""

from __future__ import annotations

import math


STM32_NUM_COILS = 5
ESP_NUM_COILS = 8

STM32_DUTY_MIN_RATIO = 0.0
# No Python-side max duty clamp. Firmware/timer output saturates physically at
# one tick below the period; AI Pro applies its own 50% model policy upstream.
STM32_DUTY_MAX_RATIO = None
AI_PRO_DUTY_MAX_RATIO = 0.50
ESP_LIVE_DUTY_MAX_RATIO = 1.0

PHASE_MIN_DEG = 0.0
PHASE_MAX_DEG = 360.0

FREQ_MIN_HZ = 1.0
DDS_ISR_HZ = 50000.0
DDS_MIN_TICKS_PER_PERIOD = 2.0
FREQ_MAX_HZ = DDS_ISR_HZ / DDS_MIN_TICKS_PER_PERIOD

DURATION_MIN_MINUTES = 0
DURATION_MAX_MINUTES = 9999


def clamp_float(value, minimum: float, maximum: float | None = None, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = default
    if not math.isfinite(numeric):
        numeric = default
    if numeric < minimum:
        return minimum
    if maximum is not None and numeric > maximum:
        return maximum
    return numeric


def duty_percent_to_ratio(percent, *, max_ratio: float | None = STM32_DUTY_MAX_RATIO) -> float:
    return clamp_float(float(percent) / 100.0, STM32_DUTY_MIN_RATIO, max_ratio)


def normalize_duty_ratio(ratio, *, max_ratio: float | None = STM32_DUTY_MAX_RATIO) -> float:
    return clamp_float(ratio, STM32_DUTY_MIN_RATIO, max_ratio)


def normalize_ai_pro_duty_ratio(ratio) -> float:
    return normalize_duty_ratio(ratio, max_ratio=AI_PRO_DUTY_MAX_RATIO)


def normalize_phase_deg(phase) -> float:
    return clamp_float(phase, PHASE_MIN_DEG, PHASE_MAX_DEG)


def normalize_frequency_hz(freq) -> float:
    return clamp_float(freq, FREQ_MIN_HZ, FREQ_MAX_HZ, default=100.0)


def normalize_duration_minutes(duration) -> int:
    try:
        numeric = int(duration)
    except (TypeError, ValueError):
        numeric = DURATION_MIN_MINUTES
    return max(DURATION_MIN_MINUTES, min(DURATION_MAX_MINUTES, numeric))
