# -*- coding: utf-8 -*-
"""
Hardware-Aware Window Mixin
============================
Herhangi bir QMainWindow alt sınıfı bu mixin'i miras alarak
"Donanım-Farkındalıklı (Hardware-Aware)" UI adaptasyonunu kazanır.

Kullanım (herhangi bir pencere sınıfı için)::

    from utils.hardware_aware_mixin import HardwareAwareMixin
    from utils.device_profile import DeviceCategory

    class MyWindow(QMainWindow, HardwareAwareMixin):
        def __init__(self):
            super().__init__()
            # ── Adım A: Pencere boyutunu profile göre ayarla ──────────
            self._setup_window_for_profile()
            # ── Adım B: Arayüzü oluştur (widget'lar burada yaratılır) ─
            self._init_ui()
            # ── Adım C: Profil adaptasyonlarını uygula ────────────────
            self._apply_device_profile_adaptations()

Sınıf içinde cihaz profiline ulaşmak için::

    profile = self.device_profile          # DeviceProfile nesnesi
    if profile.is_compact:                 # COMPACT_TOUCH mı?
        self.some_label.hide()
    elif profile.is_tv:                    # LARGE_TV mı?
        self.some_btn.setMinimumHeight(profile.min_button_height)

Mixin'in sağladığı özellikler
------------------------------
* device_profile  (property)  — önbelleğe alınmış DeviceProfile
* _setup_window_for_profile() — pencere boyut/konum kurulumu
* _apply_device_profile_adaptations() — tam UI adaptasyon şeması

    Delegasyon ağacı:
        _apply_device_profile_adaptations()
            ├── _apply_profile_to_layouts(profile)   ← her kategori
            ├── _adapt_for_compact_touch(profile)    ← yalnızca COMPACT
            ├── _adapt_for_large_tv(profile)         ← yalnızca LARGE_TV
            └── [STANDARD_DESKTOP layout yeterli]

* _on_screen_changed() — primaryScreenChanged'e bağlanır; profil + UI
                          otomatik yenilenir.

Notlar
------
* _init_ui() alt sınıf tarafından sağlanmalıdır (mixin oluşturmaz).
* _adapt_for_compact_touch / _adapt_for_large_tv metotlarını alt sınıf
  override edebilir; super() çağrısıyla temel davranışı koruyabilir.
* Python MRO'ya uygun; QMainWindow ile birlikte çalışır.

@author  : merta
@version : 1.0
"""
from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtWidgets import QApplication, QLayout
from PyQt6.QtCore    import Qt

logger = logging.getLogger(__name__)


class HardwareAwareMixin:
    """
    Donanım-farkındalıklı pencere davranışı sağlayan mixin.

    QMainWindow (veya QWidget) ile birlikte kullanılır.
    Python MRO gerekliliği nedeniyle __init__ içinde super().__init__()
    MUTLAKA çağrılmalıdır.
    """

    # ── Önbellek: aynı nesne üzerinde profil sadece bir kez çekilir ──────
    _hw_profile = None

    # =========================================================================
    # PUBLIC PROPERTY
    # =========================================================================

    @property
    def device_profile(self):
        """
        Mevcut DeviceProfile nesnesini döndür.

        İlk erişimde detect_device_profile() çağrılır, sonuç önbelleğe
        alınır.  QApplication oluşturulmadan önce erişilirse güvenli
        STANDARD_DESKTOP fallback'i döner.
        """
        if self._hw_profile is None:
            self._hw_profile = self._fetch_profile()
        return self._hw_profile

    # =========================================================================
    # ADIM A: Pencere boyutu ve konumlandırma
    # =========================================================================

    def _setup_window_for_profile(self) -> None:
        """
        Cihaz profiline göre pencere başlangıç boyutunu ve konumunu ayarla.

        Kurallar:
            COMPACT_TOUCH    → Maksimize; dokunmatik panel tam ekran kullanır.
            LARGE_TV         → Maksimize; TV'de pencereli mod anlamsız.
            STANDARD_DESKTOP → Ekranın %85'i kadar, ortada konumlandırılmış.

        Çağırma zamanı:
            __init__ içinde, _init_ui()'dan ÖNCE.
        """
        try:
            from utils.responsive_utils import get_screen_info
            profile                     = self.device_profile
            width, height, _, _         = get_screen_info()

            if profile.is_compact:
                # ── COMPACT_TOUCH: minimum boyut + maximized ──────────────
                self.setMinimumSize(600, 400)
                self.showMaximized()

            elif profile.is_tv:
                # ── LARGE_TV: daha büyük minimum + maximized ──────────────
                self.setMinimumSize(1024, 768)
                self.showMaximized()

            else:
                # ── STANDARD_DESKTOP: ekranın %85'i, ortada ──────────────
                win_w = int(width  * 0.85)
                win_h = int(height * 0.85)
                self.resize(win_w, win_h)
                self.setMinimumSize(900, 650)
                self.move(
                    (width  - win_w) // 2,
                    (height - win_h) // 2,
                )

            logger.debug(
                "_setup_window_for_profile: %s (%.1f″)",
                profile.category.value, profile.diagonal_inches,
            )

        except Exception as exc:
            logger.warning("_setup_window_for_profile hatası: %s", exc)
            self.resize(1280, 900)
            self.setMinimumSize(900, 650)

    # =========================================================================
    # ADIM B+C: Profil adaptasyonlarının ana giriş noktası
    # =========================================================================

    def _apply_device_profile_adaptations(self) -> None:
        """
        Cihaz profiline göre tüm UI elemanlarını uyarla.

        Çağırma zamanı:
            _init_ui() TAMAMLANDIKTAN hemen sonra — widget'lar var olmalıdır.
            apply_responsive_widget_scaling()'den ÖNCE çağrılmalıdır.

        Delegasyon mimarisi::

            _apply_device_profile_adaptations()
                ├── _apply_profile_to_layouts(profile)   ← ORTAK
                ├── _adapt_for_compact_touch(profile)    ← COMPACT_TOUCH
                └── _adapt_for_large_tv(profile)         ← LARGE_TV
                    [STANDARD_DESKTOP için layout yeterli]
        """
        try:
            profile = self.device_profile

            # Her kategori için layout spacing/margin
            self._apply_profile_to_layouts(profile)

            if profile.is_compact:
                self._adapt_for_compact_touch(profile)
            elif profile.is_tv:
                self._adapt_for_large_tv(profile)
            # STANDARD_DESKTOP: _apply_profile_to_layouts yeterli

            logger.info(
                "Device-profile adaptasyonu tamamlandı: %s (%.1f″)",
                profile.category.value, profile.diagonal_inches,
            )

        except Exception as exc:
            logger.warning(
                "_apply_device_profile_adaptations hatası: %s", exc, exc_info=True
            )

    # =========================================================================
    # ORTAK: Her kategori için layout güncelleme
    # =========================================================================

    def _apply_profile_to_layouts(self, profile) -> None:
        """
        Profilden gelen spacing ve margin değerlerini ana layout'lara yaz.

        DeviceProfile.__post_init__() bu değerleri kategori + ekran
        boyutuna göre önceden hesaplamıştır; burada sadece atıyoruz.

        Override edilebilir; super() çağrısı temel layout'ları günceller,
        alt sınıf ek layout'lar için ekleme yapabilir.
        """
        # ── Central Widget layout ────────────────────────────────────────
        central = self.centralWidget()          # type: ignore[attr-defined]
        if central and central.layout():
            central.layout().setContentsMargins(
                profile.layout_margin, profile.layout_margin,
                profile.layout_margin, profile.layout_margin,
            )
            central.layout().setSpacing(profile.layout_spacing)

        # ── Tab widget içindeki her tab'ın layout'u ───────────────────────
        tab_widget = getattr(self, "tab_widget", None)
        if tab_widget is not None:
            for i in range(tab_widget.count()):
                tab = tab_widget.widget(i)
                if tab and tab.layout():
                    tab.layout().setContentsMargins(
                        profile.content_margin, profile.content_margin,
                        profile.content_margin, profile.content_margin,
                    )
                    tab.layout().setSpacing(profile.layout_spacing)

    # =========================================================================
    # COMPACT_TOUCH adaptasyonları  (<10 inç dokunmatik panel)
    # =========================================================================

    def _adapt_for_compact_touch(self, profile) -> None:
        """
        COMPACT_TOUCH'a özgü UI değişiklikleri.

        Temel ilkeler:
            • Tüm tıklanabilir öğeler parmak güvenli minimum yüksekliğe çekilir.
            • İkincil / dekoratif widget'lar hide() ile gizlenir (yer kazanımı).
            • Tab başlıkları kısaltılır (uzun isimler sekme çubuğuna sığmaz).
            • ComboBox ve SpinBox minimum yükseklikleri artırılır.

        Override notu:
            Alt sınıf bu metodu override edip super() çağırmalıdır;
            böylece alt sınıfa özgü widget'ları da uyarlayabilir::

                def _adapt_for_compact_touch(self, profile):
                    super()._adapt_for_compact_touch(profile)
                    self.my_extra_btn.setMinimumHeight(profile.touch_safe_btn_height)
        """
        btn_h = profile.touch_safe_btn_height     # örn. 60–64 px

        # ── 1. Genel buton tarama ────────────────────────────────────────
        # Bilinen buton attribute isimlerini tara ve minimum yüksekliği uygula
        _btn_attrs = (
            "auto_start_btn", "auto_stop_btn",
            "ai_start_btn",   "ai_stop_btn",   "ai_calculate_btn",
            "apply_all_btn",  "start_all_btn",  "stop_all_btn",
            "btn_calibrate",  "btn_start_ai_pro", "btn_reset_pwms",
            "btn_hardware_selftest", "param_table_button",
            "delete_selected_patient_btn", "delete_all_patients_btn",
        )
        for attr in _btn_attrs:
            btn = getattr(self, attr, None)
            if btn is not None:
                btn.setMinimumHeight(btn_h)

        # Bobin kontrol sözlüğü (coil_controls) varsa
        coil_controls = getattr(self, "coil_controls", {})
        for controls in coil_controls.values():
            for key in ("start_btn", "stop_btn"):
                btn = controls.get(key)
                if btn:
                    btn.setMinimumHeight(btn_h)

        # ── 2. İkincil widget'ları gizle ─────────────────────────────────
        #
        # NEDEN: Küçük ekranda içerik alanı kısıtlıdır.  Kullanıcı için
        # kritik olmayan bilgi/dekorasyon eleman'ları kaldırılır.
        #
        _hide_attrs = (
            "param_table_button",   # Tablo butonu kiosk'ta kullanışsız
            "status_subtext",       # Header alt başlık
            "patient_status_label", # Hasta durum alt etiketi
            "ai_message_label",     # AI öneri açıklama mesajı
        )
        for attr in _hide_attrs:
            widget = getattr(self, attr, None)
            if widget is not None:
                widget.hide()

        # ── 3. Tab başlıklarını kısalt ────────────────────────────────────
        _tab_names = {
            " Otomatik Mod":              "Otomatik",
            " Manuel Mod":                "Manuel",
            " PEMF AI Mod":               "AI",
            " AI Pro":                    "AI Pro",
            " Kedi Hastalık Analizi":     "Hastalık",
            " Kedi Retikülosit Sayımı":   "Retik.",
            " Kedi Görüntü Analizi":      "Görüntü",
        }
        tab_widget = getattr(self, "tab_widget", None)
        if tab_widget is not None:
            for i in range(tab_widget.count()):
                full = tab_widget.tabText(i)
                tab_widget.setTabText(i, _tab_names.get(full, full))

        # ── 4. ComboBox minimum yükseklikleri ─────────────────────────────
        _cb_attrs = (
            "patient_combo", "target_combo",
            "ai_patient_combo", "ai_target_combo", "cb_organ_select",
        )
        for attr in _cb_attrs:
            cb = getattr(self, attr, None)
            if cb:
                cb.setMinimumHeight(btn_h - 4)

        # ── 5. SpinBox minimum yükseklikleri ──────────────────────────────
        _sb_attrs = (
            "auto_frequency_spin", "auto_duration_spin",
            "auto_intensity_spin", "auto_duty_cycle_spin",
            "master_freq_spin",    "master_duty_spin",
            "master_duration_spin", "spin_ai_pro_duration",
        )
        for attr in _sb_attrs:
            sb = getattr(self, attr, None)
            if sb:
                sb.setMinimumHeight(btn_h - 8)

        for controls in coil_controls.values():
            for key in ("freq_spin", "duty_spin", "duration_spin"):
                sb = controls.get(key)
                if sb:
                    sb.setMinimumHeight(max(32, btn_h - 10))

        logger.debug(
            "COMPACT_TOUCH adaptasyonu: btn_h=%d, spacing=%d",
            btn_h, profile.layout_spacing,
        )

    # =========================================================================
    # LARGE_TV adaptasyonları  (>32 inç büyük ekran TV)
    # =========================================================================

    def _adapt_for_large_tv(self, profile) -> None:
        """
        LARGE_TV'ye özgü UI değişiklikleri.

        Temel ilkeler:
            • Tüm font boyutları uzaktan okunabilir seviyeye çıkarılır.
            • Buton yükseklikleri artırılır (görsel netlik için).
            • Ek padding ile widget'lar sıkışık görünmez.
            • Header ve status bar bilgileri daha büyük gösterilir.

        Override notu:
            Alt sınıf bu metodu override edip super() çağırmalıdır::

                def _adapt_for_large_tv(self, profile):
                    super()._adapt_for_large_tv(profile)
                    self.my_chart.setMinimumHeight(profile.min_button_height * 3)
        """
        btn_h   = profile.min_button_height  # örn. 56–80 px
        f_title = profile.title_font_pt      # örn. 18 pt
        f_base  = profile.base_font_pt       # örn. 13 pt
        f_small = profile.small_font_pt      # örn. 11 pt

        # ── 1. Aksiyon butonları ──────────────────────────────────────────
        _btn_attrs = (
            "auto_start_btn", "auto_stop_btn",
            "ai_start_btn",   "ai_stop_btn",   "ai_calculate_btn",
            "apply_all_btn",  "start_all_btn",  "stop_all_btn",
            "btn_calibrate",  "btn_start_ai_pro", "btn_reset_pwms",
            "btn_hardware_selftest",
        )
        for attr in _btn_attrs:
            btn = getattr(self, attr, None)
            if btn is not None:
                btn.setMinimumHeight(btn_h)
                # Mevcut stylesheet'e font-size enjekte et
                btn.setStyleSheet(
                    btn.styleSheet()
                    + f"\nQPushButton {{ font-size: {f_base}pt; }}"
                )

        coil_controls = getattr(self, "coil_controls", {})
        for controls in coil_controls.values():
            for key in ("start_btn", "stop_btn"):
                btn = controls.get(key)
                if btn:
                    btn.setMinimumHeight(btn_h)

        # ── 2. Başlık ve durum etiketleri ────────────────────────────────
        _label_styles: dict[str, str] = {
            "status_text":       f"color:#ffffff; font-size:{f_title}pt; font-weight:700;",
            "status_subtext":    f"color:rgba(255,255,255,0.6); font-size:{f_base}pt;",
            "patient_info_label":f"color:#ffffff; font-size:{f_base}pt; font-weight:700;",
        }
        for attr, style in _label_styles.items():
            lbl = getattr(self, attr, None)
            if lbl:
                lbl.setStyleSheet(style)

        # ── 3. Bobin kartı etiketleri ─────────────────────────────────────
        for controls in coil_controls.values():
            for key in ("status_label", "temp_label"):
                lbl = controls.get(key)
                if lbl:
                    lbl.setStyleSheet(
                        lbl.styleSheet() + f"\nfont-size: {f_small}pt;"
                    )

        # ── 4. Sayaç / progress etiketleri ───────────────────────────────
        _countdown_attrs = ("progress_label", "remaining_time_label",
                            "lbl_ai_pro_countdown")
        for attr in _countdown_attrs:
            lbl = getattr(self, attr, None)
            if lbl:
                lbl.setStyleSheet(
                    lbl.styleSheet()
                    + f"\nfont-size: {f_title}pt; font-weight: 700;"
                )

        # ── 5. ComboBox ve SpinBox ────────────────────────────────────────
        tv_cb_h = max(btn_h - 6, 48)
        _cb_attrs = ("patient_combo", "target_combo",
                     "ai_patient_combo", "ai_target_combo", "cb_organ_select")
        for attr in _cb_attrs:
            cb = getattr(self, attr, None)
            if cb:
                cb.setMinimumHeight(tv_cb_h)

        tv_sb_h = max(btn_h - 8, 44)
        _sb_attrs = (
            "auto_frequency_spin", "auto_duration_spin",
            "auto_intensity_spin", "auto_duty_cycle_spin",
            "master_freq_spin",    "master_duty_spin",
            "master_duration_spin",
        )
        for attr in _sb_attrs:
            sb = getattr(self, attr, None)
            if sb:
                sb.setMinimumHeight(tv_sb_h)

        for controls in coil_controls.values():
            for key in ("freq_spin", "duty_spin", "duration_spin"):
                sb = controls.get(key)
                if sb:
                    sb.setMinimumHeight(max(40, tv_sb_h - 4))

        # ── 6. AI öneri etiketleri ────────────────────────────────────────
        for attr in ("ai_freq_value", "ai_intensity_value", "ai_duration_value"):
            lbl = getattr(self, attr, None)
            if lbl:
                lbl.setStyleSheet(
                    lbl.styleSheet()
                    + f"\nfont-size: {f_base}pt; font-weight: bold;"
                )

        # ── 7. Status bar ─────────────────────────────────────────────────
        status_bar = getattr(self, "status_bar", None)
        if status_bar:
            status_bar.setStyleSheet(
                status_bar.styleSheet()
                + f"\nQStatusBar {{ font-size: {f_small}pt; }}"
            )

        logger.debug(
            "LARGE_TV adaptasyonu: btn_h=%d, title=%dpt, base=%dpt, small=%dpt",
            btn_h, f_title, f_base, f_small,
        )

    # =========================================================================
    # Ekran değişimi — sinyal bağlantısı kurucusu
    # =========================================================================

    def _connect_screen_change_signal(self) -> None:
        """
        QApplication.primaryScreenChanged sinyalini _on_screen_changed'e bağla.

        __init__ içinde (tercihen _setup_window_for_profile'dan önce)
        çağrılmalıdır.  Kullanıcı monitör değiştirirse profil ve UI
        otomatik yenilenir.
        """
        app = QApplication.instance()
        if app:
            try:
                app.primaryScreenChanged.connect(self._on_screen_changed)
            except Exception as exc:
                logger.warning("primaryScreenChanged bağlanamadı: %s", exc)

    def _on_screen_changed(self, _screen=None) -> None:
        """
        Birincil ekran değiştiğinde profili ve UI'ı yenile.

        Qt sinyali: primaryScreenChanged(QScreen*)
        Profil önbelleği temizlenir, yeni ekrana göre yeniden
        tespit edilir ve _apply_device_profile_adaptations() tekrar çalışır.
        """
        try:
            from utils.device_profile import invalidate_profile
            invalidate_profile()
            self._hw_profile = None          # instance önbelleğini de temizle
            self._apply_device_profile_adaptations()
            logger.info(
                "Ekran değişti → profil güncellendi: %s",
                self.device_profile.category.value,
            )
        except Exception as exc:
            logger.warning("_on_screen_changed hatası: %s", exc, exc_info=True)

    # =========================================================================
    # İç yardımcı
    # =========================================================================

    @staticmethod
    def _fetch_profile():
        """detect_device_profile() için güvenli wrapper."""
        try:
            from utils.device_profile import detect_device_profile
            return detect_device_profile()
        except Exception as exc:
            logger.warning(
                "Profil alınamadı: %s — STANDARD_DESKTOP döndürülüyor.", exc
            )
            # Güvenli fallback: sıfırdan DeviceProfile oluştur
            from utils.device_profile import DeviceProfile, DeviceCategory
            return DeviceProfile(
                category        = DeviceCategory.STANDARD_DESKTOP,
                diagonal_inches = 21.5,
                physical_dpi    = 96.0,
                screen_width    = 1920,
                screen_height   = 1080,
                scale_factor    = 1.0,
                screen_type     = "desktop",
            )
