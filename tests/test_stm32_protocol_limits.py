# Author: mertaygn, cglrgrkn
"""Audit P1 (test-boşluğu): stm32_protocol_limits — donanıma giden parametreleri sınırlayan TEK
güvenlik katmanı, 0 testi vardı. clamp_float'ın NaN/inf guard'ı veya AI_PRO_DUTY_MAX=0.50 bir
refactorda regrese olursa (inf frekans firmware'e / duty tavanı 1.0'a) sessizce üretime giderdi.
Donanımsız saf birim testler."""

import math

from utils.stm32_protocol_limits import (
    AI_PRO_DUTY_MAX_RATIO,
    DURATION_MAX_MINUTES,
    FREQ_MAX_HZ,
    FREQ_MIN_HZ,
    PHASE_MAX_DEG,
    clamp_float,
    duty_percent_to_ratio,
    normalize_ai_pro_duty_ratio,
    normalize_duration_minutes,
    normalize_frequency_hz,
    normalize_phase_deg,
)


def test_clamp_float_bounds():
    assert clamp_float(5, 0, 10) == 5
    assert clamp_float(-3, 0, 10) == 0  # alt sınır
    assert clamp_float(99, 0, 10) == 10  # üst sınır
    assert clamp_float(7, 0, None) == 7  # üst sınır yok


def test_clamp_float_non_finite_and_invalid_go_to_default():
    # KRİTİK: NaN/inf firmware'e GİTMEMELİ → default'a düşer
    assert clamp_float(float("nan"), 0, 100, default=42) == 42
    assert clamp_float(float("inf"), 0, 100, default=42) == 42
    assert clamp_float(float("-inf"), 0, 100, default=42) == 42
    assert clamp_float("abc", 0, 100, default=42) == 42
    assert clamp_float(None, 0, 100, default=42) == 42


def test_normalize_frequency_hz():
    assert normalize_frequency_hz(100) == 100.0
    assert normalize_frequency_hz(0) == FREQ_MIN_HZ  # alt sınır
    assert normalize_frequency_hz(10**9) == FREQ_MAX_HZ  # inf-frekans firmware'e gitmez
    assert normalize_frequency_hz(float("inf")) == 100.0  # non-finite → default 100
    assert normalize_frequency_hz("xxx") == 100.0  # geçersiz → default


def test_ai_pro_duty_max_ratio_is_enforced():
    # AI Pro OTONOM tedavi duty tavanı = 0.50; regrese olursa yüksek-duty otonom sürüş olur
    assert AI_PRO_DUTY_MAX_RATIO == 0.50
    assert normalize_ai_pro_duty_ratio(0.9) == 0.50  # tavan kesiliyor
    assert normalize_ai_pro_duty_ratio(1.0) == 0.50
    assert normalize_ai_pro_duty_ratio(0.3) == 0.3  # tavan altı korunur
    assert normalize_ai_pro_duty_ratio(-0.1) == 0.0  # alt sınır


def test_normalize_duration_minutes_saturation():
    assert normalize_duration_minutes(30) == 30
    assert normalize_duration_minutes(-5) == 0  # alt sınır
    assert normalize_duration_minutes(999999) == DURATION_MAX_MINUTES  # üst doygunluk (9999)
    assert normalize_duration_minutes("abc") == 0  # geçersiz → min


def test_normalize_phase_deg():
    assert normalize_phase_deg(180) == 180.0
    assert normalize_phase_deg(-10) == 0.0
    assert normalize_phase_deg(720) == PHASE_MAX_DEG


def test_duty_percent_to_ratio():
    assert duty_percent_to_ratio(50) == 0.5
    assert duty_percent_to_ratio(-10) == 0.0  # alt sınır
    assert duty_percent_to_ratio(0) == 0.0
