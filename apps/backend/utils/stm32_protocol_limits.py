# Author: mertaygn, cglrgrkn
"""Shared STM32 protocol limits for GUI, AI Pro, headless, and API paths."""

from __future__ import annotations

import math

# ⚠️ BAYAT SABİT DÜZELTİLDİ 2026-09-11: burada `STM32_NUM_COILS = 5` yazıyordu ve
# 2026-09-10'daki 7-bobin geçişinde GÜNCELLENMEMİŞTİ. Bugün hiçbir yerde kullanılmıyor
# (grep: yalnız bu tanım) — yani zarar vermedi, ama okuyana YANLIŞ ÖĞRETİYORDU.
#
# ⚠️ TEK KAYNAK `servers/live_state.STM_COIL_IDS` / `ESP_COIL_IDS`tir. Buradan import
# edilmiyor çünkü `utils/` katmanı `servers/`e bağımlı olmamalı (katman tersine dönerdi);
# bunun yerine `tests/test_bobin_sayisi_tek_kaynak.py` ikisinin AYRIŞMASINI kırmızı yapar.
STM32_NUM_COILS = 7  # bobin 1-7 (seri/DDS)
ESP_NUM_COILS = 1  # yalnız slot 8 (MQTT) — ⚠️ ADET, en büyük kimlik DEĞİL

STM32_DUTY_MIN_RATIO = 0.0
# Backend'de STM duty tavanı YOK (Y9 — geri EKLENMEZ). Duty üst sınırı FIRMWARE'dedir ve
# TAŞIYICIDIR: kart kip tavanının üstünü NACK'ler (main.c DUTY_MAX_BIPOLAR 0,5 /
# DUTY_MAX_UNIPOLAR 1,0 — D1.101 · Y20) ve ISR bipolar darbeyi tpp/2 − DDS_BIPOLAR_GAP_TICKS
# ile kıstırır (shoot-through; unipolar tpp − 1). AI Pro kendi %50 model politikasını
# yukarıda uygular (AI_PRO_DUTY_MAX_RATIO).
STM32_DUTY_MAX_RATIO = None
AI_PRO_DUTY_MAX_RATIO = 0.50
ESP_LIVE_DUTY_MAX_RATIO = 1.0

PHASE_MIN_DEG = 0.0
PHASE_MAX_DEG = 360.0

FREQ_MIN_HZ = 1.0
DDS_ISR_HZ = 50000.0
DDS_MIN_TICKS_PER_PERIOD = 2.0
FREQ_MAX_HZ = DDS_ISR_HZ / DDS_MIN_TICKS_PER_PERIOD

# ⚠️ ESP (bugün yalnız slot 8 — `live_state.ESP_COIL_IDS = {8}`) FREKANS TAVANI = EN KISITLI ESP olan 8266'ya göre (donanım-uyum denetimi
# D-3, 2026-08-19; sahip talebi: "8266'ya göre ayarla"). Doğrulandı — İKİ ESP de 1000 Hz sınırlı:
#   · 8266: `constrain(freq,1,1000)` (CoilController.cpp:215/278/353) VE dogrulama `f > 1000.0f`
#     komutu TAMAMEN REDDEDER (esp8266_pemf_coil.ino:512,615 → NACK, bobin BAŞLAMAZ). En katı uç.
#   · S3  : `constrain(cmd.frequency,1,1000)` (CoilController.cpp:279) — sessizce 1000'e KIRPAR.
# STM (1-7) tavanı çok daha yüksek (FREQ_MAX_HZ=25000). Backend ESP yoluna 1000 tavanını ÖNDEN
# uygularsa: hem 8266'nın reddini (bobin hiç çalışmaz) hem S3'ün sessiz kırpmasını (komut≠telemetri)
# önler → tüm ESP dizisi tutarlı davranır. Değer 8266 firmware sınırıyla birebir; değişirse
# firmware constrain'leri de güncellenmeli (test_stm32_source_parity mantığı).
ESP_FREQ_MAX_HZ = 1000.0

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


def normalize_esp_frequency_hz(freq) -> float:
    """ESP (bobin 6-8) frekans normalize — firmware `constrain(freq, 1, 1000)` sınırı (D-3).
    STM yolu için `normalize_frequency_hz` (25000 tavanı); ESP için AYRI çünkü ESP DDS 1000 Hz
    üstünü süremez ve backend sessiz kırpma yerine önden clamp etmeli (komut=telemetri tutarlılığı)."""
    return clamp_float(freq, FREQ_MIN_HZ, ESP_FREQ_MAX_HZ, default=100.0)


def normalize_duration_minutes(duration) -> int:
    # D1.96 (B-1.33 · S-1.5): 0 < süre < 1 dk YUKARI yuvarlanır (1 dk). `int()` 0,5'i 0'a kesiyordu → çağıran "süre
    # verilmedi" sayıp 120 dk'lık GÖZETİMSİZ kapağı uyguluyordu (30 sn istenip 120 dk). Protokol sınırları DEĞİŞMEDİ.
    try:
        if 0.0 < float(duration) < 1.0:
            return max(DURATION_MIN_MINUTES, 1)
    except (TypeError, ValueError, OverflowError):
        pass
    try:
        numeric = int(duration)
    except (TypeError, ValueError, OverflowError):
        # DENETIM P3: OverflowError YAKALANMIYORDU → duration=float('inf') gelirse int() coker
        # ve istisna cagirana (update_coil → /api/coil/{id}/control) sizardi. Diger normalize_*
        # yardimcilari clamp_float uzerinden inf/nan'i zaten guvenle ele aliyor; bu yalniz burada
        # eksikti. NaN da ValueError verir ve ayni dala duser → guvenli varsayilan.
        numeric = DURATION_MIN_MINUTES
    return max(DURATION_MIN_MINUTES, min(DURATION_MAX_MINUTES, numeric))
