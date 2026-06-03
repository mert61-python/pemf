# -*- coding: utf-8 -*-
"""
Responsive Utils - GUI Responsive Design Utilities
===================================================

Bu modül, GUI uygulamasının farklı ekran boyutları, çözünürlüklerde ve
fiziksel ekran boyutlarında (inç) tam responsive çalışmasını sağlar.

Önemli bileşenler
-----------------
* get_screen_info()              — ekran boyutu, ölçek faktörü ve tür bilgisi
* get_physical_screen_info()     — fiziksel DPI ve diyagonal inç bilgisi
* scale_value()                  — genel değer ölçekleyici (px, margin, spacing, vb.)
* get_responsive_pt()            — pt bazlı font boyutunu ölçekler
* get_responsive_font_size()     — px bazlı font boyutunu ölçekler
* scale_margins()                — margin/padding değerlerini ölçekler
* scale_stylesheet()             — ham QSS string içindeki font-size / min-width /
                                   min-height / padding / margin / border-radius
                                   değerlerini ölçekler
* RS                            — Merkezi stil fabrikası.
                                   Tüm hardcoded QSS string'lerini buradan alın;
                                   ekrana göre otomatik ölçeklenir.
* apply_responsive_widget_scaling() — tüm widget ağacını tarar ve ölçekler

@author: merta
@date: 2025-01-28  (v2: full padding/margin/border-radius scaling + new RS methods)
"""

import re
import sys
import time
import math
from typing import Optional, Tuple

from PyQt6.QtWidgets import (
    QSizePolicy, QSpacerItem, QApplication, QWidget,
    QLabel, QPushButton, QToolButton, QLineEdit, QTextEdit, QPlainTextEdit,
    QSpinBox, QDoubleSpinBox, QComboBox, QGroupBox, QTabWidget, QTabBar,
    QCheckBox, QRadioButton, QAbstractButton,
)

# ---------------------------------------------------------------------------
# Screen-info cache
# ---------------------------------------------------------------------------
_screen_info_cache: Optional[Tuple[int, int, float, str]] = None
_screen_info_cache_time: float = 0.0
_SCREEN_CACHE_TTL_SECONDS: float = 2.0

_physical_info_cache: Optional[Tuple[float, float]] = None  # (physical_dpi, diagonal_inches)


def _compute_screen_info() -> Tuple[int, int, float, str]:
    """Compute screen info once; cached by get_screen_info()."""
    app = QApplication.instance()
    if not app:
        return 1920, 1080, 1.0, "unknown"

    screen = app.primaryScreen()
    if not screen:
        return 1920, 1080, 1.0, "unknown"

    geometry = screen.availableGeometry()
    width = geometry.width()
    height = geometry.height()

    # Logical DPI for UI scaling
    logical_dpi = screen.logicalDotsPerInch()
    base_dpi = 96.0
    dpi_scale = logical_dpi / base_dpi

    # Physical DPI for true inch-based calculations
    physical_dpi = screen.physicalDotsPerInch()
    if physical_dpi < 50 or physical_dpi > 600:
        physical_dpi = logical_dpi  # fallback if OS reports garbage

    # Compute physical diagonal in inches (for tiny/large screen detection)
    phys_w = screen.physicalSize().width()   # mm
    phys_h = screen.physicalSize().height()  # mm
    if phys_w > 0 and phys_h > 0:
        diagonal_mm = math.sqrt(phys_w ** 2 + phys_h ** 2)
        diagonal_inches = diagonal_mm / 25.4
    else:
        # fallback: estimate from pixel count / physical DPI
        diagonal_inches = math.sqrt(width ** 2 + height ** 2) / max(physical_dpi, 96.0)

    # Resolution-based scale relative to 1920×1080 baseline
    base_width, base_height = 1920, 1080
    resolution_scale = min(width / base_width, height / base_height)

    # Combined scale: resolution only (Qt handles logical DPI natively via QT_ENABLE_HIGHDPI_SCALING)
    # We clamp this to a much tighter range (0.75 to 1.1) so large screens don't become comically huge.
    scale_factor = max(0.75, min(resolution_scale, 1.1))

    # Screen type by diagonal (inches) — more reliable than pixel width alone
    if diagonal_inches < 10:
        screen_type = "mobile"
    elif diagonal_inches < 14:
        screen_type = "tablet"
    elif diagonal_inches < 18:
        screen_type = "laptop"
    elif diagonal_inches < 27:
        screen_type = "desktop"
    else:
        screen_type = "ultrawide"

    # Fallback to pixel-width classification if physical size unknown
    if phys_w <= 0:
        if width < 1024:
            screen_type = "mobile"
        elif width < 1366:
            screen_type = "tablet"
        elif width < 1920:
            screen_type = "laptop"
        elif width < 2560:
            screen_type = "desktop"
        else:
            screen_type = "ultrawide"

    # Cache physical info for callers that need it
    global _physical_info_cache
    _physical_info_cache = (physical_dpi, diagonal_inches)

    return width, height, scale_factor, screen_type


def get_screen_info() -> Tuple[int, int, float, str]:
    """
    Return (width, height, scale_factor, screen_type) for the primary screen.
    Result is cached for 2 seconds.
    """
    global _screen_info_cache, _screen_info_cache_time
    try:
        now = time.monotonic()
        if _screen_info_cache is None or (now - _screen_info_cache_time) > _SCREEN_CACHE_TTL_SECONDS:
            _screen_info_cache = _compute_screen_info()
            _screen_info_cache_time = now
        return _screen_info_cache
    except Exception:
        return 1920, 1080, 1.0, "unknown"


def get_physical_screen_info() -> Tuple[float, float]:
    """
    Return (physical_dpi, diagonal_inches) for the primary screen.
    Triggers get_screen_info() if cache is empty.
    """
    if _physical_info_cache is None:
        get_screen_info()
    return _physical_info_cache or (96.0, 21.5)


def invalidate_screen_cache() -> None:
    """Force cache refresh on next call (call this on screen change events)."""
    global _screen_info_cache, _screen_info_cache_time, _physical_info_cache
    _screen_info_cache = None
    _screen_info_cache_time = 0.0
    _physical_info_cache = None


# ---------------------------------------------------------------------------
# Low-level scale helpers
# ---------------------------------------------------------------------------

_TYPE_MULTIPLIERS = {
    "mobile":    0.85,
    "tablet":    0.95,
    "laptop":    1.00,
    "desktop":   1.02,
    "ultrawide": 1.05,
}


def _effective_scale(extra_multiplier: float = 1.0) -> float:
    """Return the combined DPI + screen-type + extra multiplier (capped 0.65–2.0)."""
    _, _, scale_factor, screen_type = get_screen_info()
    type_mult = _TYPE_MULTIPLIERS.get(screen_type, 1.0)
    return max(0.65, min(scale_factor * type_mult * extra_multiplier, 2.0))


def scale_value(base: int, min_ratio: float = 0.4, max_ratio: float = 2.0,
                extra_multiplier: float = 1.0) -> int:
    """
    General-purpose responsive value scaler.

    Use for any numeric dimension: padding, margin, spacing, border-radius,
    button heights, etc.

    Args:
        base:             Reference value at 1920×1080 96-DPI laptop baseline.
        min_ratio:        Minimum output as fraction of base (default 0.4).
        max_ratio:        Maximum output as fraction of base (default 2.0).
        extra_multiplier: Additional factor on top of the screen scale.

    Returns:
        int: Scaled value, clamped to [base*min_ratio, base*max_ratio].
    """
    try:
        eff = _effective_scale(extra_multiplier)
        scaled = base * eff
        lo = max(1, int(base * min_ratio))
        hi = int(base * max_ratio)
        return max(lo, min(int(scaled), hi))
    except Exception:
        return base


def get_responsive_pt(base_pt: int, screen_type: Optional[str] = None) -> int:
    """
    Scale a **point-based** font size to the current screen.

    Args:
        base_pt:     Base pt size at 1920×1080 96-DPI (\"laptop\" baseline).
        screen_type: Optional override; auto-detected when None.

    Returns:
        int: Scaled pt value, never below 7.
    """
    try:
        if screen_type is None:
            _, _, scale_factor, screen_type = get_screen_info()
        else:
            _, _, scale_factor, _ = get_screen_info()

        multiplier = _TYPE_MULTIPLIERS.get(screen_type, 1.0)
        scaled = base_pt * scale_factor * multiplier
        return max(7, min(int(scaled), int(base_pt * 2.0)))
    except Exception:
        return base_pt


def get_responsive_font_size(base_size: int, screen_type: Optional[str] = None) -> int:
    """
    Scale a **pixel-based** font size to the current screen.

    Args:
        base_size:   Base px size at 1920×1080 96-DPI.
        screen_type: Optional override.

    Returns:
        int: Scaled px value, min 8.
    """
    try:
        if screen_type is None:
            _, _, scale_factor, screen_type = get_screen_info()
        else:
            _, _, scale_factor, _ = get_screen_info()

        multiplier = _TYPE_MULTIPLIERS.get(screen_type, 1.0)
        scaled = base_size * scale_factor * multiplier
        return max(8, min(int(scaled), int(base_size * 2.0)))
    except Exception:
        return base_size


def scale_margins(widget, base_margin: int) -> int:
    """
    Scale a margin/padding value to the current screen.

    Returns an int, min max(2, base*0.3), max base*2.
    """
    try:
        _, _, scale_factor, screen_type = get_screen_info()
        multiplier = _TYPE_MULTIPLIERS.get(screen_type, 1.0)
        scaled = base_margin * scale_factor * multiplier
        min_margin = max(2, int(base_margin * 0.3))
        max_margin = int(base_margin * 2.0)
        return max(min_margin, min(int(scaled), max_margin))
    except Exception:
        return base_margin


def get_responsive_spacing(base_spacing: int, screen_type: Optional[str] = None) -> int:
    """Return a spacing value scaled for the current (or given) screen type."""
    try:
        if screen_type is None:
            _, _, _, screen_type = get_screen_info()
        multiplier = _TYPE_MULTIPLIERS.get(screen_type, 1.0)
        return max(1, int(base_spacing * multiplier))
    except Exception:
        return base_spacing


def scale_font(widget, base_size: int) -> None:
    """Set widget's font to base_size scaled for the current screen."""
    try:
        _, _, scale_factor, screen_type = get_screen_info()
        multiplier = _TYPE_MULTIPLIERS.get(screen_type, 1.0)
        scaled = base_size * scale_factor * multiplier
        min_size = max(8, int(base_size * 0.6))
        max_size = int(base_size * 2.0)
        final_size = max(min_size, min(int(scaled), max_size))
        font = widget.font()
        font.setPointSizeF(final_size)
        widget.setFont(font)
    except Exception:
        font = widget.font()
        font.setPointSizeF(base_size)
        widget.setFont(font)


# ---------------------------------------------------------------------------
# scale_stylesheet — extended version supporting padding/margin/border-radius
# ---------------------------------------------------------------------------

# Primary pattern: font-size, min-width, min-height (existing)
_SS_FONT_DIM_PATTERN = re.compile(
    r"(font-size|min-width|min-height):\s*(\d+(?:\.\d+)?)\s*(px|pt)"
)

# Padding/margin shorthand: single value  e.g.  padding: 8px
_SS_PAD_SINGLE = re.compile(
    r"(padding|margin):\s*(\d+(?:\.\d+)?)\s*px(?!\s+\d)"  # only single-value form
)

# Padding/margin with up to 4 values: padding: 8px 12px 8px 12px
_SS_PAD_MULTI = re.compile(
    r"(padding|margin):\s*((?:\d+(?:\.\d+)?px\s*){2,4})"
)

# Individual side declarations: margin-top, padding-left, etc.
_SS_SIDE_MARGIN = re.compile(
    r"((?:margin|padding)-(?:top|bottom|left|right)):\s*(\d+(?:\.\d+)?)\s*px"
)

# border-radius
_SS_BORDER_RADIUS = re.compile(
    r"(border-radius):\s*(\d+(?:\.\d+)?)\s*px"
)

# spacing (Qt proprietary, rare but used in some QSS)
_SS_SPACING = re.compile(
    r"(spacing):\s*(\d+(?:\.\d+)?)\s*px"
)


def scale_stylesheet(stylesheet: str, extra_multiplier: float = 1.0,
                     scale_padding: bool = True,
                     scale_border_radius: bool = True) -> str:
    """
    Scale every ``font-size``, ``min-width``, ``min-height`` declaration
    inside *stylesheet* by the current screen's responsive factor.

    With ``scale_padding=True`` (default) also scales ``padding``, ``margin``,
    ``margin-top/bottom/left/right``, ``padding-top/bottom/left/right``.

    With ``scale_border_radius=True`` (default) also scales ``border-radius``.

    Args:
        stylesheet:          Raw QSS string.
        extra_multiplier:    Additional multiplier on top of the screen factor.
        scale_padding:       Whether to scale padding/margin values.
        scale_border_radius: Whether to scale border-radius values.

    Returns:
        str: Rescaled QSS string, safe to pass to ``setStyleSheet()``.
    """
    if not stylesheet:
        return stylesheet
    try:
        eff = _effective_scale(extra_multiplier)

        # -- font-size / min-width / min-height ---------------------------------
        def _sub_font_dim(match: re.Match) -> str:
            prop  = match.group(1)
            value = float(match.group(2))
            unit  = match.group(3)
            if prop == "font-size":
                scaled = max(7.0, min(value * eff, value * 2.0))
                return f"font-size: {int(round(scaled))}px" if unit == "px" else f"font-size: {int(round(scaled))}pt"
            scaled = max(10.0, min(value * eff, value * 2.0))
            return f"{prop}: {int(round(scaled))}{unit}"

        result = _SS_FONT_DIM_PATTERN.sub(_sub_font_dim, stylesheet)

        if scale_padding:
            # -- individual side margin/padding ---------------------------------
            def _sub_side(m: re.Match) -> str:
                prop  = m.group(1)
                value = float(m.group(2))
                scaled = max(0.0, min(value * eff, value * 2.0))
                return f"{prop}: {int(round(scaled))}px"
            result = _SS_SIDE_MARGIN.sub(_sub_side, result)

            # -- multi-value padding/margin (2-4 values) ------------------------
            def _sub_multi(m: re.Match) -> str:
                prop   = m.group(1)
                values = re.findall(r"(\d+(?:\.\d+)?)px", m.group(2))
                scaled = " ".join(
                    f"{max(0, int(round(float(v) * eff)))}px"
                    for v in values
                )
                return f"{prop}: {scaled}"
            result = _SS_PAD_MULTI.sub(_sub_multi, result)

            # -- single-value padding/margin ------------------------------------
            def _sub_single(m: re.Match) -> str:
                prop  = m.group(1)
                value = float(m.group(2))
                scaled = max(0.0, min(value * eff, value * 2.0))
                return f"{prop}: {int(round(scaled))}px"
            result = _SS_PAD_SINGLE.sub(_sub_single, result)

        if scale_border_radius:
            def _sub_radius(m: re.Match) -> str:
                value  = float(m.group(2))
                # border-radius should not shrink below 3px
                scaled = max(3.0, min(value * eff, value * 2.0))
                return f"border-radius: {int(round(scaled))}px"
            result = _SS_BORDER_RADIUS.sub(_sub_radius, result)

        # -- spacing ------------------------------------------------------------
        def _sub_spacing(m: re.Match) -> str:
            value  = float(m.group(2))
            scaled = max(0.0, min(value * eff, value * 2.0))
            return f"spacing: {int(round(scaled))}px"
        result = _SS_SPACING.sub(_sub_spacing, result)

        return result
    except Exception:
        return stylesheet


# ---------------------------------------------------------------------------
# Helper to compute a line-height-like value used in fixed-height props
# ---------------------------------------------------------------------------

def _screen_type_multiplier() -> float:
    """Return the current screen-type multiplier (no DPI)."""
    _, _, _, screen_type = get_screen_info()
    return _TYPE_MULTIPLIERS.get(screen_type, 1.0)


# ---------------------------------------------------------------------------
# RS — Responsive Styles (centralized QSS string factory)
# ---------------------------------------------------------------------------

class RS:
    """
    Centralized QSS string factory for PEMF Vet GUI.

    **Tüm hardcoded ``setStyleSheet`` çağrıları RS üzerinden geçmeli.**
    Her metot, ``get_responsive_pt`` + ``scale_stylesheet`` kombinasyonunu
    kullanarak mevcut ekrana göre ölçeklenmiş, tam bir QSS string döndürür.

    Kullanım::

        from utils.responsive_utils import RS, get_responsive_pt, scale_value

        label.setStyleSheet(RS.text("#6cffb0", base_pt=14, bold=True))
        esp_widget.setStyleSheet(RS.esp_item_bg())
        self.silent_mode_btn.setStyleSheet(RS.silent_mode_btn(active=True))
        center_panel.setStyleSheet(RS.center_panel())
        self.st_progress.setStyleSheet(RS.progress_bar())
    """

    # ------------------------------------------------------------------
    # Generic text helpers
    # ------------------------------------------------------------------

    @staticmethod
    def text(
        color: str = "#fff",
        base_pt: int = 10,
        bold: bool = False,
        extra: str = "",
    ) -> str:
        """Return a minimal colour + font-size + optional bold style string."""
        pt = get_responsive_pt(base_pt)
        weight = "font-weight: bold;" if bold else ""
        return f"color: {color}; font-size: {pt}pt; {weight} {extra}".strip()

    @staticmethod
    def html_span(text: str, color: str = "#fff", base_pt: int = 17,
                  bold: bool = True) -> str:
        """
        Return a full ``<b style='...'>text</b>`` HTML string for QLabel.

        Replaces hardcoded ``"<b style='color:#fff;font-size:22px;'>Başlık</b>"``
        patterns throughout the GUI.

        Usage::

            title_label.setText(RS.html_span("Sistem Durumu"))
            info_title.setText(RS.html_span("Sistem Bilgileri"))
        """
        pt = get_responsive_pt(base_pt)
        weight = "font-weight:bold;" if bold else ""
        tag = "b" if bold else "span"
        return f"<{tag} style='color:{color};font-size:{pt}pt;{weight}'>{text}</{tag}>"

    @staticmethod
    def html_value_span(text: str, color: str, base_px: int = 14,
                        bold: bool = True) -> str:
        """
        Inline HTML span for value labels inside rows / status bars.

        Replaces ``f"<span style='color:{c}; font-size:14px;'>{v}</span>"``
        patterns.
        """
        px = get_responsive_font_size(base_px)
        weight = "font-weight:bold;" if bold else ""
        return f"<span style='color:{color}; font-size:{px}px;{weight}'>{text}</span>"

    # ------------------------------------------------------------------
    # ESP container / background styles
    # ------------------------------------------------------------------

    @staticmethod
    def esp_container() -> str:
        """Outer QWidget that holds all bobin (ESP) status cards."""
        return scale_stylesheet("""
            background: rgba(61, 32, 107, 0.3);
            border: 1px solid #6c2b8f;
            border-radius: 12px;
            padding: 12px;
            margin: 5px 0;
        """)

    @staticmethod
    def esp_item_bg() -> str:
        """Individual bobin status card background."""
        return scale_stylesheet("""
            background: rgba(45, 24, 90, 0.6);
            border: 1px solid #4a2c7a;
            border-radius: 8px;
            padding: 8px;
            margin: 2px;
        """)

    @staticmethod
    def esp_sensor_details_bg() -> str:
        """Sensor detail sub-panel inside a bobin card."""
        return scale_stylesheet("""
            background: rgba(30, 20, 50, 0.5);
            border-radius: 6px;
            padding: 6px;
            margin-top: 4px;
        """)

    # ------------------------------------------------------------------
    # ESP text / indicator styles
    # ------------------------------------------------------------------

    @staticmethod
    def esp_title(base_pt: int = 11) -> str:
        """Bobin card title (e.g. '🔌 Bobin 1')."""
        return RS.text("#fff", base_pt, bold=True)

    @staticmethod
    def esp_indicator(color: str = "#888888", base_pt: int = 12) -> str:
        """Coloured '●' status dot inside a bobin card."""
        return f"color: {color}; font-size: {get_responsive_pt(base_pt)}pt;"

    @staticmethod
    def esp_info_label(base_pt: int = 9) -> str:
        """Static key labels (WiFi:, MQTT:, Sensörler: …) in bobin cards."""
        return RS.text("#ccc", base_pt)

    @staticmethod
    def esp_status_text(color: str, base_pt: int = 9) -> str:
        """Dynamic status value label inside bobin cards."""
        return f"color: {color}; font-size: {get_responsive_pt(base_pt)}pt;"

    @staticmethod
    def esp_sensor_detail(color: str, base_pt: int = 8) -> str:
        """Individual sensor name labels (temp / magnetic / current)."""
        return f"color: {color}; font-size: {get_responsive_pt(base_pt)}pt;"

    # ------------------------------------------------------------------
    # ESP panel section header
    # ------------------------------------------------------------------

    @staticmethod
    def section_title(color: str = "#6cffb0", base_pt: int = 12) -> str:
        """Panel section header label (e.g. '📡 Bobin Bağlantı Durumu')."""
        pt = get_responsive_pt(base_pt)
        return (
            f"color: {color}; font-size: {pt}pt; "
            f"font-weight: bold; margin: 10px 0;"
        )

    @staticmethod
    def no_esp_label(base_pt: int = 11) -> str:
        """'Bobin bulunamadı / aranıyor' placeholder label style."""
        pt = get_responsive_pt(base_pt)
        padding = scale_value(20)
        return (
            f"color: #ffa500; font-size: {pt}pt; "
            f"text-align: center; padding: {padding}px;"
        )

    @staticmethod
    def esp_section_title(base_px: int = 16) -> str:
        """
        ESP/bobin panel section title.

        Usage::

            esp_title.setStyleSheet(RS.esp_section_title())
        """
        px = get_responsive_font_size(base_px)
        margin = scale_value(10)
        return (
            f"color: #6cffb0; font-size: {px}px; "
            f"font-weight: bold; margin: {margin}px 0;"
        )

    # ------------------------------------------------------------------
    # Top-bar elements
    # ------------------------------------------------------------------

    @staticmethod
    def connection_status_label(base_pt: int = 10) -> str:
        """STM32 / bağlantı durum badge (sarı çerçeveli)."""
        pt = get_responsive_pt(base_pt)
        pv = scale_value(6)
        ph = scale_value(14)
        return (
            f"color: #f59e0b; font-size: {pt}pt; font-weight: 600; "
            f"padding: {pv}px {ph}px; "
            f"background: rgba(245, 158, 11, 0.12); "
            f"border-radius: {scale_value(8)}px; "
            f"border: 1px solid rgba(245, 158, 11, 0.3);"
        )

    @staticmethod
    def icon_emoji(base_pt: int = 25) -> str:
        """Emoji / icon label font-size only (e.g. logo area '💚')."""
        return f"font-size: {get_responsive_pt(base_pt)}pt;"

    # ------------------------------------------------------------------
    # Silent mode button
    # ------------------------------------------------------------------

    @staticmethod
    def silent_mode_btn(active: bool, base_pt: int = 12) -> str:
        """
        Full QSS for the 🔊/🔇 silent mode button.

        Args:
            active: True → sessiz mod açık (kırmızı), False → kapalı (mavi).
        """
        pt = get_responsive_pt(base_pt)
        if active:
            gradient = "stop:0 #ff6b6b, stop:1 #ff8e8e"
        else:
            gradient = "stop:0 #4a90e2, stop:1 #7bb3f0"
        return scale_stylesheet(f"""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, {gradient});
            color: white;
            border: none;
            border-radius: 8px;
            font-size: {pt}pt;
            font-weight: bold;
            padding: 8px 12px;
            margin-left: 16px;
            min-width: 40px;
        """)

    # ------------------------------------------------------------------
    # Treatment / seans status
    # ------------------------------------------------------------------

    @staticmethod
    def treatment_status_bg(stopped: bool = True, base_pt: int = 12) -> str:
        """QWidget/QLabel stylesheet for the seans status badge."""
        pt = get_responsive_pt(base_pt)
        pv = scale_value(4)
        ph = scale_value(16)
        mt = scale_value(6)
        bg = "#fecaca" if stopped else "#d1fae5"
        return (
            f"background: {bg}; border-radius: {scale_value(6)}px; "
            f"padding: {pv}px {ph}px; margin-top: {mt}px; font-size: {pt}pt;"
        )

    @staticmethod
    def treatment_status_html(stopped: bool = True, base_pt: int = 12) -> str:
        """HTML string for ``self.st_status.setText(...)`` calls."""
        pt = get_responsive_pt(base_pt)
        if stopped:
            color, text = "#ef4444", "Durduruldu"
        else:
            color, text = "#22c55e", "● Aktif"
        return (
            f"<span style='color:{color}; font-size: {pt}pt; "
            f"font-weight: bold;'>{text}</span>"
        )

    # ------------------------------------------------------------------
    # Initial / waiting status badge
    # ------------------------------------------------------------------

    @staticmethod
    def initial_status_badge(base_pt: int = 12) -> str:
        """
        Responsive style for the initial '● Beklemede' status badge.

        Usage::

            self.st_status.setStyleSheet(RS.initial_status_badge())
        """
        pt = get_responsive_pt(base_pt)
        pv = scale_value(4)
        ph = scale_value(16)
        mt = scale_value(6)
        r  = scale_value(6)
        return (
            f"background: #f3f4f6; border-radius: {r}px; "
            f"padding: {pv}px {ph}px; margin-top: {mt}px; font-size: {pt}pt;"
        )

    @staticmethod
    def initial_status_html(base_pt: int = 12) -> str:
        """HTML for the initial '● Beklemede' status label."""
        pt = get_responsive_pt(base_pt)
        return (
            f"<span style='color:#6b7280; font-size: {pt}pt; "
            f"font-weight: bold;'>● Beklemede</span>"
        )

    # ------------------------------------------------------------------
    # Validation labels
    # ------------------------------------------------------------------

    @staticmethod
    def validation_label(color: str = "#ffa726", base_pt: int = 8) -> str:
        """Inline validation message label style."""
        pt = get_responsive_pt(base_pt)
        return (
            f"color: {color}; font-size: {pt}pt; "
            f"margin-left: {scale_value(2)}px; margin-top: {scale_value(2)}px;"
        )

    @staticmethod
    def validation_label_inline(color: str = "#ffa726", base_pt: int = 8) -> str:
        """Validation message label under an input field."""
        pt = get_responsive_pt(base_pt)
        return f"color: {color}; font-size: {pt}pt; margin-left: 2px; margin-top: 2px;"

    # ------------------------------------------------------------------
    # System info / data rows
    # ------------------------------------------------------------------

    @staticmethod
    def info_row_value(base_pt: int = 9) -> str:
        """Value label in the system-info card rows (white, bold)."""
        return RS.text("#ffffff", base_pt, bold=True)

    @staticmethod
    def info_row_label(base_pt: int = 8) -> str:
        """Label in system-info data row (e.g. '🔄 Yazılım Sürümü:')."""
        pt = get_responsive_pt(base_pt)
        return f"color: #bdb8e3; font-size: {pt}pt;"

    @staticmethod
    def info_row_label_px(base_px: int = 11) -> str:
        """
        Label in system-info data rows using px units.

        Replaces hardcoded ``"color: #bdb8e3; font-size: 11px;"`` in add_info_row.
        """
        px = get_responsive_font_size(base_px)
        return f"color: #bdb8e3; font-size: {px}px;"

    @staticmethod
    def info_row_value_px(base_px: int = 14) -> str:
        """
        Bold value label in system-info rows using px units.

        Replaces hardcoded ``"color: #fff; font-size: 14px; font-weight: bold;"``
        in add_info_row.
        """
        px = get_responsive_font_size(base_px)
        return f"color: #ffffff; font-size: {px}px; font-weight: bold;"

    @staticmethod
    def info_row_version_px(base_px: int = 12) -> str:
        """Version/HW info value label style."""
        px = get_responsive_font_size(base_px)
        return f"color: #ffffff; font-size: {px}px; font-weight: bold;"

    # ------------------------------------------------------------------
    # Progress bar (QProgressBar full QSS)
    # ------------------------------------------------------------------

    @staticmethod
    def progress_bar(base_pt: int = 9) -> str:
        """
        Complete QSS block for a ``QProgressBar``.
        Use as: ``self.st_progress.setStyleSheet(RS.progress_bar())``
        """
        pt = get_responsive_pt(base_pt)
        return scale_stylesheet(f"""
            QProgressBar {{
                border: none;
                border-radius: 7px;
                background-color: #2d1b69;
                text-align: center;
                color: white;
                font-weight: bold;
                font-size: {pt}pt;
            }}
            QProgressBar::chunk {{
                background-color: #3b82f6;
                border-top-left-radius: 7px;
                border-bottom-left-radius: 7px;
                border-top-right-radius: 0px;
                border-bottom-right-radius: 0px;
                margin: 0px;
            }}
        """)

    # ------------------------------------------------------------------
    # Notification card
    # ------------------------------------------------------------------

    @staticmethod
    def notification_card(base_padding: int = 16, base_margin_top: int = 12) -> str:
        """Outer notification card QWidget style."""
        p = scale_value(base_padding)
        m = scale_value(base_margin_top)
        return scale_stylesheet(f"""
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 #3d206b, stop:1 #6c2b8f
            );
            border-radius: 16px;
            padding: {p}px;
            margin-top: {m}px;
        """)

    # ------------------------------------------------------------------
    # Top bar widget
    # ------------------------------------------------------------------

    @staticmethod
    def top_bar_widget(margin_top: int = 8, margin_side: int = 32) -> str:
        """Top bar outer widget — transparent, rounded."""
        mt = scale_value(margin_top)
        ms = scale_value(margin_side)
        return scale_stylesheet(f"""
            background: transparent;
            border-radius: 18px;
            margin: {mt}px {ms}px 0 {ms}px;
            padding: 0;
        """)

    @staticmethod
    def clock_label(base_pt: int = 15) -> str:
        """Clock text in the top bar."""
        pt = get_responsive_pt(base_pt)
        ml = scale_value(24)
        return f"""
            color: #fff;
            font-size: {pt}px;
            margin-left: {ml}px;
            background: transparent;
            border-radius: 0;
        """

    # ------------------------------------------------------------------
    # Sidebar / scroll / separators
    # ------------------------------------------------------------------

    @staticmethod
    def sidebar_widget() -> str:
        """Sidebar outer widget — purple gradient, compact top padding."""
        return scale_stylesheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #2d185a, stop:1 #6c2b8f);
            padding: 6px 12px 12px 12px;
            border-radius: 16px;
        """)

    @staticmethod
    def sidebar_title(base_pt: int = 13) -> str:
        """Sidebar section title (e.g. 'Sistem Parametreleri')."""
        pt = get_responsive_pt(base_pt)
        return f"color: #fff; font-size: {pt}pt; font-weight: bold; margin: 0;"

    @staticmethod
    def scroll_area() -> str:
        """Scroll area — transparent bg, thin modern vertical scroll bar."""
        _sb_w = max(4, scale_value(6, min_ratio=0.5, max_ratio=2.0))
        _sb_r = max(2, _sb_w // 2)
        _sb_min_h = scale_value(30, min_ratio=0.5)
        return f"""
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                width: {_sb_w}px;
                background: transparent;
                margin: 0;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(255, 255, 255, 0.15);
                border-radius: {_sb_r}px;
                min-height: {_sb_min_h}px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: rgba(255, 255, 255, 0.3);
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: transparent;
            }}
            QScrollBar:horizontal {{
                height: 0px;
            }}
        """

    @staticmethod
    def separator(color: str = "#6c2b8f") -> str:
        """Thin colored horizontal line in the sidebar."""
        type_mult = _screen_type_multiplier()
        h = max(1, int(2 * type_mult))
        m = scale_value(4)
        return f"background: {color}; margin: {m}px 0; min-height: {h}px;"

    @staticmethod
    def field_label(base_pt: int = 11) -> str:
        """Input field label (white, bold)."""
        pt = get_responsive_pt(base_pt)
        ml = scale_value(2)
        mb = scale_value(3)
        return f"color: #fff; font-size: {pt}pt; font-weight: bold; margin-left: {ml}px; margin-bottom: {mb}px;"

    @staticmethod
    def line_edit(base_pt: int = 10) -> str:
        """QLineEdit — dark bg, rounded, white text."""
        pt = get_responsive_pt(base_pt)
        return scale_stylesheet(f"""
            background: #3d206b; color: white; border: none; border-radius: 8px;
            padding: 3px 10px; font-size: {pt}pt;
        """)

    # ------------------------------------------------------------------
    # Buttons — gradient
    # ------------------------------------------------------------------

    @staticmethod
    def save_patient_btn(base_pt: int = 16) -> str:
        """Green gradient save patient button."""
        pt = get_responsive_pt(base_pt)
        return scale_stylesheet(f"""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #28a745, stop:1 #20c997);
            color: white;
            border: none;
            border-radius: 12px;
            font-size: {pt}px;
            font-weight: bold;
            padding: 10px 20px;
            min-height: 50px;
            margin: 15px 0;
        """)

    @staticmethod
    def ble_add_btn(base_pt: int = 13) -> str:
        """Purple gradient BLE add device button."""
        pt = get_responsive_pt(base_pt)
        return scale_stylesheet(f"""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #7c3aed, stop:1 #6c2b8f);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: {pt}px;
            font-weight: bold;
            padding: 8px 12px;
            margin: 6px 0;
        """)

    @staticmethod
    def user_manual_btn(base_pt: int = 16) -> str:
        """Purple gradient user manual button."""
        pt = get_responsive_pt(base_pt)
        return scale_stylesheet(f"""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #6c2b8f, stop:1 #9b4ec8);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: {pt}px;
            font-weight: bold;
            padding: 8px 12px;
            margin-left: 16px;
            min-width: 40px;
        """)

    @staticmethod
    def emergency_stop_btn(base_pt: int = 18) -> str:
        """Red gradient emergency stop button in top bar."""
        pt = get_responsive_pt(base_pt)
        return scale_stylesheet(f"""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ff5e62, stop:1 #ff9966);
            color: white;
            border: none;
            border-radius: 12px;
            font-size: {pt}px;
            font-weight: bold;
            padding: 12px 32px;
            margin-left: 32px;
        """)

    # ------------------------------------------------------------------
    # STM connection status label (dynamic colors)
    # ------------------------------------------------------------------

    @staticmethod
    def connection_status_stm(color: str = "#f59e0b", base_pt: int = 10) -> str:
        """Dynamic STM32 connection status badge."""
        pt = get_responsive_pt(base_pt)
        pv = scale_value(6)
        ph = scale_value(14)
        r = scale_value(8)
        rgb = _hex_to_rgb(color)
        rgb_str = ",".join(str(int(x * 255)) for x in rgb)
        return (
            f"color:{color}; font-size: {pt}pt; font-weight:600; "
            f"padding:{pv}px {ph}px; background:rgba({rgb_str},0.12); "
            f"border-radius:{r}px; border:1px solid rgba({rgb_str},0.3);"
        )

    @staticmethod
    def status_bar_connected() -> str:
        """Status bar style when STM connected."""
        return "color: #22c55e; font-weight: bold;"

    @staticmethod
    def status_bar_disconnected() -> str:
        """Status bar style when STM disconnected."""
        return "color: gray;"

    # ------------------------------------------------------------------
    # Nav bar
    # ------------------------------------------------------------------

    @staticmethod
    def nav_btn(base_pt: int = 11) -> str:
        """
        Nav bar button — direct f-string QSS so hover/pressed rules are not
        mangled by scale_stylesheet, and text is never clipped.
        """
        pt  = get_responsive_pt(base_pt)
        pv  = scale_value(4)
        ph  = scale_value(8)
        mh  = scale_value(54)  # artırıldı: metin kesilmesini önler
        r   = scale_value(7)
        return (
            f"QPushButton {{"
            f"  background: transparent; color: #fff; border: none;"
            f"  font-size: {pt}pt; font-weight: bold;"
            f"  padding: {pv}px {ph}px; min-height: {mh}px;"
            f"  text-align: center;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background: rgba(255,255,255,0.12); border-radius: {r}px;"
            f"}}"
            f"QPushButton:pressed {{"
            f"  background: rgba(255,255,255,0.22); border-radius: {r}px;"
            f"}}"
        )

    @staticmethod
    def nav_widget() -> str:
        """Navigation bar outer widget — height guaranteed so text never clips."""
        mh = scale_value(68)  # artırıldı: metin kesilmesini önler
        r  = scale_value(12)
        return (
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #2d185a,stop:1 #6c2b8f);"
            f"border-radius: {r}px; min-height: {mh}px;"
        )

    # ------------------------------------------------------------------
    # Smart Treatment Card
    # ------------------------------------------------------------------

    @staticmethod
    def treatment_card() -> str:
        """Active seans smart treatment card."""
        return scale_stylesheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #3d206b, stop:1 #6c2b8f);
            border-radius: 14px;
            padding: 18px 16px;
        """)

    @staticmethod
    def treatment_card_title(base_pt: int = 14) -> str:
        """Title label inside treatment card (e.g. '~ Aktif Seans')."""
        pt = get_responsive_pt(base_pt)
        return f"color: #6cffb0; font-size: {pt}px; font-weight: bold;"

    @staticmethod
    def treatment_row_label(base_pt: int = 14) -> str:
        """Row label inside treatment card (e.g. 'Frekans:', 'Süre:')."""
        pt = get_responsive_pt(base_pt)
        return f"color: #fff; font-size: {pt}px; font-weight: bold;"

    @staticmethod
    def treatment_row_value(base_pt: int = 14) -> str:
        """Row value label inside treatment card."""
        pt = get_responsive_pt(base_pt)
        return f"font-size: {pt}px; font-weight: bold;"

    @staticmethod
    def treatment_time_icon(base_pt: int = 14) -> str:
        """⏱ or ⏰ icon in treatment card."""
        pt = get_responsive_pt(base_pt)
        return f"color: #fff; font-size: {pt}px; font-weight: bold;"

    # ------------------------------------------------------------------
    # KPI cards
    # ------------------------------------------------------------------

    @staticmethod
    def kpi_card() -> str:
        """Transparent outer KPI card widget."""
        return "background: transparent;"

    @staticmethod
    def kpi_title(base_pt: int = 15) -> str:
        """KPI section title."""
        pt = get_responsive_pt(base_pt)
        return f"color: #fff; font-size: {pt}px; font-weight: bold;"

    @staticmethod
    def kpi_widget(bg: str) -> str:
        """Single KPI value widget (colored background)."""
        return scale_stylesheet(f"""
            background: {bg}; border-radius: 8px; padding: 6px 10px;
        """)

    @staticmethod
    def kpi_icon(base_pt: int = 18) -> str:
        """Icon label inside a KPI widget."""
        pt = get_responsive_pt(base_pt)
        return f"color: #fff; font-size: {pt}px;"

    @staticmethod
    def kpi_label(color: str, base_pt: int = 13) -> str:
        """Text label inside a KPI widget."""
        pt = get_responsive_pt(base_pt)
        return f"color: {color}; font-size: {pt}px; font-weight: bold;"

    # ------------------------------------------------------------------
    # Center panel
    # ------------------------------------------------------------------

    @staticmethod
    def center_panel() -> str:
        """Dark translucent center panel widget."""
        return scale_stylesheet("""
            background: rgba(40,20,80,0.85);
            border-radius: 24px;
        """)

    @staticmethod
    def center_section_title(base_pt: int = 17) -> str:
        """Section title inside the center panel (HTML label)."""
        pt = get_responsive_pt(base_pt)
        return f"<b style='color:#fff;font-size: {pt}pt;'>"

    # ------------------------------------------------------------------
    # Coil buttons (grid)
    # ------------------------------------------------------------------

    @staticmethod
    def coil_btn(base_pt: int = 14) -> str:
        """
        Full QSS for a coil toggle button in the 8-button grid.
        Includes normal, checked, hover, pressed, and disabled states.
        """
        pt = get_responsive_pt(base_pt)
        pv = scale_value(18)
        r  = scale_value(14)
        return f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1ed6b5, stop:1 #3ed6b5);
                color: white;
                border: none;
                border-radius: {r}px;
                font-size: {pt}pt;
                font-weight: bold;
                padding: {pv}px 0;
            }}
            QPushButton:checked {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ff6b6b, stop:1 #ff8e8e);
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #3ed6b5, stop:1 #5ed6b5);
            }}
            QPushButton:pressed {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #00b894, stop:1 #00cec9);
            }}
            QPushButton:disabled {{
                background: rgba(100, 100, 100, 0.3);
                color: rgba(255, 255, 255, 0.4);
            }}
        """

    @staticmethod
    def stop_all_btn(base_pt: int = 16) -> str:
        """
        Big red 'Bobin Kapat!' button below the coil grid.
        Includes hover state.
        """
        pt = get_responsive_pt(base_pt)
        pv = scale_value(18)
        r  = scale_value(14)
        mt = scale_value(18)
        return f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ff5e62, stop:1 #ff9966);
                color: white;
                border: none;
                border-radius: {r}px;
                font-size: {pt}pt;
                font-weight: bold;
                padding: {pv}px 0;
                margin-top: {mt}px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #e45357, stop:1 #ff7f50);
            }}
        """

    # ------------------------------------------------------------------
    # Info panel (right side)
    # ------------------------------------------------------------------

    @staticmethod
    def info_panel() -> str:
        """Dark translucent right-side info panel."""
        return scale_stylesheet("""
            background: rgba(40,20,80,0.85);
            border-radius: 24px;
        """)

    @staticmethod
    def info_row_container() -> str:
        """
        Her info satırını saran pill kapsayıcı widget stili.
        Yarı şeffaf koyu arka plan + yuvarlatılmış köşeler.
        """
        r  = scale_value(10)
        pv = scale_value(6)
        ph = scale_value(10)
        return (
            f"background: rgba(0,0,0,0.18);"
            f"border-radius: {r}px;"
            f"padding: {pv}px {ph}px;"
        )

    @staticmethod
    def info_row_label_pill(base_px: int = 13) -> str:
        """
        Sol label pill stili (emoji + metin).
        Hafif arka planlı, ince kenarlıklı pill.
        """
        px = get_responsive_font_size(base_px)
        r  = scale_value(8)
        pv = scale_value(4)
        ph = scale_value(8)
        return (
            f"color: #d4ccf5;"
            f"font-size: {px}px;"
            f"background: rgba(255,255,255,0.07);"
            f"border-radius: {r}px;"
            f"padding: {pv}px {ph}px;"
        )

    @staticmethod
    def info_row_value_pill(base_px: int = 13) -> str:
        """
        Sağ value pill stili.
        Koyu arka plan + beyaz kalın metin.
        """
        px = get_responsive_font_size(base_px)
        r  = scale_value(8)
        pv = scale_value(4)
        ph = scale_value(10)
        return (
            f"color: #ffffff;"
            f"font-size: {px}px;"
            f"font-weight: bold;"
            f"background: rgba(0,0,0,0.28);"
            f"border-radius: {r}px;"
            f"padding: {pv}px {ph}px;"
        )

    @staticmethod
    def system_info_card() -> str:
        """System info card inside the info panel (gradient)."""
        return scale_stylesheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #3d206b, stop:1 #6c2b8f);
            border-radius: 16px;
            padding: 16px;
            margin-top: 12px;
        """)

    @staticmethod
    def status_row_widget() -> str:
        """Widget wrapper for status row — transparent."""
        return "background: transparent;"

    @staticmethod
    def status_label() -> str:
        """Status label HTML with default colors."""
        return "color: #bdb8e3; font-size: 10pt;"

    # ------------------------------------------------------------------
    # Notification panel inner styles
    # ------------------------------------------------------------------

    @staticmethod
    def notification_panel_inner() -> str:
        """Inner notification panel — transparent."""
        return """
            background: transparent;
            border-radius: 0px;
            padding: 0px;
            margin-top: 0px;
        """

    @staticmethod
    def notification_title(base_pt: int = 11) -> str:
        """Title inside the notification card."""
        pt = get_responsive_pt(base_pt)
        mb = scale_value(6)
        return f"color: #ffffff; font-size: {pt}pt; font-weight: bold; margin-bottom: {mb}px;"

    # ------------------------------------------------------------------
    # Empty state placeholder (e.g. notification panel when no messages)
    # ------------------------------------------------------------------

    @staticmethod
    def empty_state_label(base_pt: int = 9) -> str:
        """Muted italic label shown when a list/panel is empty."""
        pt = get_responsive_pt(base_pt)
        p = scale_value(12)
        return (
            f"color: rgba(255,255,255,0.35); font-size: {pt}pt; "
            f"font-style: italic; padding: {p}px; text-align: center;"
        )

    # ------------------------------------------------------------------
    # Parameter section titles
    # ------------------------------------------------------------------

    @staticmethod
    def param_title(base_pt: int = 16) -> str:
        """Sidebar parameter section title (e.g. '⚙️ Hasta Kaydı')."""
        pt = get_responsive_pt(base_pt)
        m = scale_value(10)
        return f"color: #6cffb0; font-size: {pt}px; font-weight: bold; margin: {m}px 0;"

    # ------------------------------------------------------------------
    # Gateway status widget style
    # ------------------------------------------------------------------

    @staticmethod
    def gateway_widget() -> str:
        """Gateway status widget — transparent inner."""
        return "background: transparent; border: none;"

    # ------------------------------------------------------------------
    # Status-row make_status_label helper
    # ------------------------------------------------------------------

    @staticmethod
    def status_make_html(label: str, value: str, value_color: str,
                         label_base_px: int = 13, value_base_px: int = 14) -> str:
        """
        Generate HTML for a status row label + colored value.

        Replaces hardcoded::

            f"<span style='color:#bdb8e3;font-size:13px;'>{label}</span> "
            f"<span style='color:{color}; font-size:14px; font-weight:bold;'>{value}</span>"
        """
        lp = get_responsive_font_size(label_base_px)
        vp = get_responsive_font_size(value_base_px)
        return (
            f"<span style='color:#bdb8e3;font-size:{lp}px;'>{label}</span> "
            f"<span style='color:{value_color}; font-size:{vp}px; font-weight:bold;'>{value}</span>"
        )

    @staticmethod
    def connection_status_stm(color: str = "#22c55e") -> str:
        """Connection status label for STM32 (dynamic color)."""
        pt = get_responsive_pt(10)
        p_h = scale_value(14)
        p_v = scale_value(6)
        r = scale_value(8)
        
        # Parse rgb from hex
        h = color.lstrip('#')
        try:
            rgb = tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
            bg = f"rgba({rgb[0]},{rgb[1]},{rgb[2]},0.12)"
            border = f"rgba({rgb[0]},{rgb[1]},{rgb[2]},0.3)"
        except:
            bg = "rgba(34,197,94,0.12)"
            border = "rgba(34,197,94,0.3)"
            
        return f"""
            color: {color}; font-size: {pt}pt; font-weight: 600; 
            padding: {p_v}px {p_h}px; background: {bg}; 
            border-radius: {r}px; border: 1px solid {border};
        """

    @staticmethod
    def connection_status_label() -> str:
        """Standard connection status label."""
        return RS.connection_status_stm(color="#f59e0b")
        
    @staticmethod
    def status_bar_connected() -> str:
        """Status bar stylesheet when connected."""
        pt = get_responsive_pt(9)
        return f"color: #22c55e; font-weight: bold; font-size: {pt}pt;"
        
    @staticmethod
    def status_bar_disconnected() -> str:
        """Status bar stylesheet when disconnected."""
        pt = get_responsive_pt(9)
        return f"color: gray; font-size: {pt}pt;"


# ---------------------------------------------------------------------------
# Helper: convert hex colour to RGB tuple (0..1)
# ---------------------------------------------------------------------------

def _hex_to_rgb(hex_color: str) -> tuple:
    """
    Convert a hex colour string to an (R, G, B) tuple with values 0..1.
    Falls back to (1, 1, 1) on parse failure.
    """
    h = hex_color.lstrip('#')
    try:
        return tuple(int(h[i:i+2], 16) / 255.0 for i in (0, 2, 4))
    except (ValueError, IndexError):
        return (1.0, 1.0, 1.0)


# ---------------------------------------------------------------------------
# Widget-tree helpers
# ---------------------------------------------------------------------------

def make_resizable(widget, horizontal: bool = True, vertical: bool = True) -> None:
    """Make a widget expand in the given directions."""
    policy = QSizePolicy(
        QSizePolicy.Policy.Expanding if horizontal else QSizePolicy.Policy.Fixed,
        QSizePolicy.Policy.Expanding if vertical else QSizePolicy.Policy.Fixed,
    )
    policy.setHeightForWidth(widget.sizePolicy().hasHeightForWidth())
    widget.setSizePolicy(policy)


def create_stretch() -> QSpacerItem:
    """Create a vertical stretch spacer."""
    return QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)


def create_horizontal_stretch() -> QSpacerItem:
    """Create a horizontal stretch spacer."""
    return QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)


def apply_responsive_layout(widget, base_margins=(16, 16, 16, 16), base_spacing: int = 8) -> None:
    """Apply responsive margin + spacing to the widget's layout."""
    try:
        _, _, _, screen_type = get_screen_info()
        scaled_margins = tuple(scale_margins(widget, m) for m in base_margins)
        scaled_spacing = get_responsive_spacing(base_spacing, screen_type)
        if hasattr(widget, "layout") and widget.layout():
            widget.layout().setContentsMargins(*scaled_margins)
            widget.layout().setSpacing(scaled_spacing)
    except Exception:
        pass


def apply_responsive_widget_scaling(root_widget: QWidget, scale_multiplier: float = 1.0) -> None:
    """
    Recursively scale widget fonts and QSS ``font-size`` declarations.

    Stores the original font size and stylesheet as Qt widget properties so
    subsequent calls always scale from the *original* baseline (idempotent).
    """
    try:
        _, _, scale_factor, screen_type = get_screen_info()
        effective_scale = max(0.65, min(scale_factor * scale_multiplier, 2.0))

        text_widgets = (
            QLabel, QPushButton, QToolButton,
            QLineEdit, QTextEdit, QPlainTextEdit,
            QSpinBox, QDoubleSpinBox, QComboBox,
            QGroupBox, QTabWidget, QTabBar,
            QCheckBox, QRadioButton, QAbstractButton,
        )

        for widget in [root_widget, *root_widget.findChildren(QWidget)]:
            if not isinstance(widget, text_widgets):
                continue

            font = widget.font()

            # ── persist baseline point size ─────────────────────────────
            base_point_size = widget.property("_responsive_base_point_size")
            if base_point_size is None:
                point_size = font.pointSizeF()
                if point_size <= 0:
                    point_size = float(get_responsive_font_size(10, screen_type))
                base_point_size = float(point_size)
                widget.setProperty("_responsive_base_point_size", base_point_size)

            # ── persist baseline stylesheet ─────────────────────────────
            if widget.property("_responsive_base_stylesheet") is None:
                widget.setProperty("_responsive_base_stylesheet", widget.styleSheet())

            # ── apply scaled font ───────────────────────────────────────
            target_size = max(8.0, min(base_point_size * effective_scale,
                                       base_point_size * 2.0))
            font.setPointSizeF(target_size)
            widget.setFont(font)

            # ── apply scaled stylesheet ─────────────────────────────────
            base_stylesheet = widget.property("_responsive_base_stylesheet")
            if isinstance(base_stylesheet, str) and base_stylesheet:
                widget.setStyleSheet(
                    scale_stylesheet(base_stylesheet,
                                     extra_multiplier=scale_multiplier,
                                     scale_padding=True,
                                     scale_border_radius=True)
                )

    except Exception:
        pass