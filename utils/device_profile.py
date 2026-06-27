# -*- coding: utf-8 -*-
"""
Device Profile — Donanım Farkındalıklı (Hardware-Aware) Cihaz Profili
======================================================================

Bu modül, fiziksel ekran boyutunu (inç cinsinden) esas alarak uygulamayı
çalıştıran cihazı 3 kategoriden birine atar ve her kategoriye özgü UI
parametrelerini hesaplar.

Kategoriler:
    COMPACT_TOUCH    < 10 inç  → Kiosk / Endüstriyel Dokunmatik Panel
    STANDARD_DESKTOP 10–32 inç → Standart Ofis Monitörü / Dizüstü Bilgisayar
    LARGE_TV         > 32 inç  → Büyük Ekran TV / Video Duvarı

Kullanım::

    # main.py içinde — QApplication başlatıldıktan hemen sonra
    from utils.device_profile import detect_device_profile
    profile = detect_device_profile()
    app.setProperty("device_profile", profile)

    # Herhangi bir pencere / widget içinde
    from utils.device_profile import detect_device_profile, DeviceCategory
    profile = detect_device_profile()
    if profile.category == DeviceCategory.COMPACT_TOUCH:
        self.btn.setMinimumHeight(profile.min_button_height)

Notlar:
    • detect_device_profile() QApplication BAŞLATILDIKTAN sonra
      çağrılmalıdır — QScreen API'si QApplication gerektirir.
    • Sonuç uygulama ömrü boyunca önbelleğe alınır.
    • Ekran değişiminde invalidate_profile() + detect_device_profile()
      çağrısı yapın.

@author: merta
@version: 1.0  (Hardware-Aware Architecture)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


# ── Cihaz Kategorisi ─────────────────────────────────────────────────────────

class DeviceCategory(Enum):
    """Fiziksel ekran boyutuna göre cihaz sınıflandırması."""
    COMPACT_TOUCH    = "COMPACT_TOUCH"     # < 10 inç
    STANDARD_DESKTOP = "STANDARD_DESKTOP"  # 10–32 inç
    LARGE_TV         = "LARGE_TV"          # > 32 inç


# ── Cihaz Profili Veri Sınıfı ────────────────────────────────────────────────

@dataclass
class DeviceProfile:
    """
    Bir cihazın fiziksel ekran özelliklerine dayalı tüm UI parametrelerini
    tek bir nesnede depolar.

    Doğrudan oluşturma yerine detect_device_profile() kullanın.
    Türetilmiş alanlar __post_init__ içinde otomatik hesaplanır.
    """

    # ── Ölçüm verileri (dışarıdan verilir) ───────────────────────────────────
    category:        DeviceCategory
    diagonal_inches: float
    physical_dpi:    float
    screen_width:    int
    screen_height:   int
    scale_factor:    float
    screen_type:     str  # responsive_utils çıktısı: mobile/tablet/laptop/desktop/ultrawide

    # ── Türetilmiş UI parametreleri (post_init'te hesaplanır) ─────────────────

    # Buton boyutları
    min_button_height:    int  = field(default=44,  init=False)
    touch_safe_btn_height: int = field(default=60,  init=False)

    # Layout aralıkları
    layout_spacing:   int = field(default=12, init=False)
    layout_margin:    int = field(default=16, init=False)
    content_margin:   int = field(default=24, init=False)

    # Tipografi
    base_font_pt:  int = field(default=10, init=False)
    title_font_pt: int = field(default=14, init=False)
    small_font_pt: int = field(default=8,  init=False)

    # Görünürlük / Gizleme
    hide_secondary_widgets: bool = field(default=False, init=False)
    hide_subtitle_labels:   bool = field(default=False, init=False)
    compact_header:         bool = field(default=False, init=False)

    # TV özel ek padding
    tv_padding_extra: int = field(default=0, init=False)

    # ── Hesaplama ─────────────────────────────────────────────────────────────

    def __post_init__(self) -> None:
        """
        Kategoriye göre tüm UI parametrelerini hesapla.

        Değerler responsive_utils.scale_value / get_responsive_pt üzerinden
        geçirildiğinden ekranın mantıksal DPI/çözünürlüğü de hesaba katılır —
        yalnızca fiziksel kategori değil, gerçek render ölçeği de yansır.
        """
        # Lokal import — responsive_utils QApplication gerektirir; bu metot
        # ancak __init__'den (dolayısıyla QApplication'dan) SONRA çağrılır.
        from utils.responsive_utils import scale_value as _sv, get_responsive_pt as _pt

        if self.category == DeviceCategory.COMPACT_TOUCH:
            # ── 7–10 inç Kiosk / Endüstriyel Dokunmatik Panel ──────────────
            # Parmak erişimi için büyük butonlar, geniş dokunma hedefleri.
            # Ekranda yer kazanmak için ikincil widget'lar gizlenir.
            self.min_button_height    = _sv(60,  min_ratio=0.85, max_ratio=1.25)
            self.touch_safe_btn_height= _sv(64,  min_ratio=0.85, max_ratio=1.30)
            self.layout_spacing       = _sv(5,   min_ratio=0.50, max_ratio=1.20)
            self.layout_margin        = _sv(8,   min_ratio=0.50, max_ratio=1.20)
            self.content_margin       = _sv(10,  min_ratio=0.50, max_ratio=1.20)
            self.base_font_pt         = _pt(10)
            self.title_font_pt        = _pt(12)
            self.small_font_pt        = _pt(8)
            self.hide_secondary_widgets = True   # İkincil widget'ları gizle
            self.hide_subtitle_labels   = True   # Alt başlıkları gizle
            self.compact_header         = True   # Header'ı daralt
            self.tv_padding_extra       = 0

        elif self.category == DeviceCategory.STANDARD_DESKTOP:
            # ── 10–32 inç Standart Monitör / Dizüstü ────────────────────────
            # Dengeli değerler — mevcut davranışla aynı, tam uyumluluk.
            self.min_button_height    = _sv(40,  min_ratio=0.70, max_ratio=1.30)
            self.touch_safe_btn_height= _sv(44,  min_ratio=0.70, max_ratio=1.30)
            self.layout_spacing       = _sv(12,  min_ratio=0.50, max_ratio=1.50)
            self.layout_margin        = _sv(16,  min_ratio=0.50, max_ratio=1.50)
            self.content_margin       = _sv(24,  min_ratio=0.50, max_ratio=1.50)
            self.base_font_pt         = _pt(10)
            self.title_font_pt        = _pt(14)
            self.small_font_pt        = _pt(8)
            self.hide_secondary_widgets = False
            self.hide_subtitle_labels   = False
            self.compact_header         = False
            self.tv_padding_extra       = 0

        elif self.category == DeviceCategory.LARGE_TV:
            # ── 40–65 inç Büyük Ekran TV ─────────────────────────────────────
            # Uzaktan izlenebilir büyük yazı, geniş padding.
            # Ekranda boşluk kalmaması için margin/spacing artırılır.
            self.min_button_height    = _sv(56,  min_ratio=0.85, max_ratio=1.80)
            self.touch_safe_btn_height= _sv(60,  min_ratio=0.85, max_ratio=1.80)
            self.layout_spacing       = _sv(20,  min_ratio=0.80, max_ratio=2.50)
            self.layout_margin        = _sv(28,  min_ratio=0.80, max_ratio=2.50)
            self.content_margin       = _sv(40,  min_ratio=0.80, max_ratio=2.50)
            self.base_font_pt         = _pt(13)
            self.title_font_pt        = _pt(18)
            self.small_font_pt        = _pt(11)
            self.hide_secondary_widgets = False
            self.hide_subtitle_labels   = False
            self.compact_header         = False
            self.tv_padding_extra       = _sv(16, min_ratio=0.80, max_ratio=2.50)

    # ── Yardımcılar ───────────────────────────────────────────────────────────

    @property
    def is_compact(self) -> bool:
        """Kısa yol: COMPACT_TOUCH kategorisinde mi?"""
        return self.category == DeviceCategory.COMPACT_TOUCH

    @property
    def is_tv(self) -> bool:
        """Kısa yol: LARGE_TV kategorisinde mi?"""
        return self.category == DeviceCategory.LARGE_TV

    @property
    def is_desktop(self) -> bool:
        """Kısa yol: STANDARD_DESKTOP kategorisinde mi?"""
        return self.category == DeviceCategory.STANDARD_DESKTOP

    def __str__(self) -> str:
        return (
            f"DeviceProfile({self.category.value}, "
            f"{self.diagonal_inches:.1f}″, "
            f"{self.screen_width}×{self.screen_height}, "
            f"DPI={self.physical_dpi:.0f})"
        )


# ── Modül seviyesi önbellek ───────────────────────────────────────────────────

_current_profile: Optional[DeviceProfile] = None


def detect_device_profile(force_refresh: bool = False) -> DeviceProfile:
    """
    Fiziksel ekran bilgisine dayalı cihaz profilini tespit et ve döndür.

    responsive_utils.get_physical_screen_info() üzerinden elde edilen
    diyagonal inç değerine göre kategorilendirme yapılır:

        diagonal_inches < 10    → COMPACT_TOUCH
        10 ≤ diagonal_inches ≤ 32 → STANDARD_DESKTOP
        diagonal_inches > 32    → LARGE_TV

    Sonuç uygulama ömrü boyunca önbelleğe alınır.  Ekran değişikliği
    sonrasında invalidate_profile() çağırarak yenileme yapın.

    Args:
        force_refresh: True ise önbelleği yok sayıp yeniden hesapla.

    Returns:
        DeviceProfile: Tüm türetilmiş UI parametrelerini içeren nesne.

    Raises:
        Hiçbir şey — hata durumunda STANDARD_DESKTOP ile güvenli fallback.

    Örnek::

        app = QApplication(sys.argv)
        profile = detect_device_profile()
        # → DeviceProfile(STANDARD_DESKTOP, 24.0″, 1920×1080, DPI=96)
    """
    global _current_profile

    if _current_profile is not None and not force_refresh:
        return _current_profile

    try:
        from utils.responsive_utils import (
            get_physical_screen_info,
            get_screen_info,
            invalidate_screen_cache,
        )

        if force_refresh:
            invalidate_screen_cache()

        physical_dpi, diagonal_inches = get_physical_screen_info()
        width, height, scale_factor, screen_type = get_screen_info()

        # Kategori belirle
        if diagonal_inches < 10.0:
            category = DeviceCategory.COMPACT_TOUCH
        elif diagonal_inches <= 32.0:
            category = DeviceCategory.STANDARD_DESKTOP
        else:
            category = DeviceCategory.LARGE_TV

        _current_profile = DeviceProfile(
            category=category,
            diagonal_inches=diagonal_inches,
            physical_dpi=physical_dpi,
            screen_width=width,
            screen_height=height,
            scale_factor=scale_factor,
            screen_type=screen_type,
        )

        logger.info(
            "Cihaz profili tespit edildi → %s | %.1f″ | %.0f DPI | %d×%d px",
            _current_profile.category.value,
            diagonal_inches,
            physical_dpi,
            width,
            height,
        )

    except Exception as exc:
        # Güvenli fallback: hiçbir zaman crash olmaz, standart değerlerle devam eder.
        logger.warning(
            "Cihaz profili belirlenemedi (%s); STANDARD_DESKTOP varsayılanı kullanılıyor.",
            exc,
        )
        try:
            from utils.responsive_utils import get_screen_info
            w, h, sf, st = get_screen_info()
        except Exception:
            w, h, sf, st = 1920, 1080, 1.0, "desktop"

        _current_profile = DeviceProfile(
            category=DeviceCategory.STANDARD_DESKTOP,
            diagonal_inches=21.5,
            physical_dpi=96.0,
            screen_width=w,
            screen_height=h,
            scale_factor=sf,
            screen_type=st,
        )

    return _current_profile


def invalidate_profile() -> None:
    """
    Ekran değişimi gibi olaylardan sonra profil önbelleğini sıfırla.

    Bir sonraki detect_device_profile() çağrısında yeniden hesaplanır.
    main.py içinde app.primaryScreenChanged sinyaline bağlanması önerilir.
    """
    global _current_profile
    _current_profile = None
    logger.debug("Cihaz profili önbelleği temizlendi.")
