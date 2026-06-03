from PyQt6.QtWidgets import QWidget, QLabel, QSizePolicy
from PyQt6.QtCore import Qt, QRect, pyqtSignal
from PyQt6.QtGui import QPixmap
from utils.responsive_utils import scale_value as _sv_ril


class ResponsiveImageLabel(QWidget):
    """
    A QWidget that dynamically scales its QPixmap to fill the available space
    while strictly maintaining the aspect ratio of the image.

    Architecture (2-layer):
        _bg_label   — always fills the full widget → carries border, background-color,
                       border-radius, placeholder text.  Border never shrinks.
        _image_label — transparent, no border → painted on top of _bg_label, centred,
                        sized to the scaled pixmap.  Hidden when no pixmap is set.

    Default mode (set_constrain_width=False):
        _bg_label fills the full widget — original behaviour, no change.

    Constrain-width mode (set_constrain_width=True):
        When an image is loaded, _bg_label is shrunk to wrap tightly around the
        scaled image bounds (centred inside the widget).  The styled border and
        background follow the *actual* image area — no wide black bars on the
        sides for portrait/narrow images.  When no image is set the placeholder
        border reverts to full-widget mode automatically.
    """
    
    scaled_size_changed = pyqtSignal(int, int)

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(
            _sv_ril(200, min_ratio=0.5, max_ratio=1.5),
            _sv_ril(200, min_ratio=0.5, max_ratio=1.5),
        )

        self._placeholder_text = text
        self._constrain_width: bool = False   # opt-in tight-wrap feature
        self._in_update: bool = False          # re-entrancy guard

        # ── Layer 1: background + border + placeholder text ──────────────
        self._bg_label = QLabel(text, self)
        self._bg_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # ── Layer 2: image (transparent, no border) ──────────────────────
        self._image_label = QLabel(self)
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setStyleSheet("background: transparent; border: none;")
        self._image_label.hide()  # hidden until a pixmap is loaded

        self._pixmap: QPixmap | None = None
        self._cached_scaled_pixmap: QPixmap | None = None

    # ── Public API ────────────────────────────────────────────────────────

    def set_constrain_width(self, enabled: bool) -> None:
        """
        When True: the dashed-border/background layer wraps tightly around the
        scaled image so there are no empty bars beside the image.
        When False (default): background fills the full widget (original behaviour).

        Safe to call at any time; geometry is updated immediately.
        """
        self._constrain_width = enabled
        if self._pixmap and not self._pixmap.isNull():
            self._update_pixmap()
        else:
            # No image — always show full-widget placeholder.
            self._bg_label.setGeometry(0, 0, self.width(), self.height())

    def setAlignment(self, alignment):
        self._bg_label.setAlignment(alignment)
        self._image_label.setAlignment(alignment)

    def setStyleSheet(self, style: str):
        """Route the full style (border, background, color…) to _bg_label only."""
        self._bg_label.setStyleSheet(style)
        # Keep the image layer transparent so the bg shows through letterbox bars.
        self._image_label.setStyleSheet("background: transparent; border: none;")

    def setText(self, text: str):
        self._placeholder_text = text
        # Only show placeholder when there is no image loaded.
        if not (self._pixmap and not self._pixmap.isNull()):
            self._bg_label.setText(text)

    def setPixmap(self, pixmap: QPixmap):
        self._pixmap = pixmap
        if self._pixmap and not self._pixmap.isNull():
            self._bg_label.setText("")   # hide placeholder while image is shown
            self._image_label.show()
        else:
            self._bg_label.setText(self._placeholder_text)
            self._image_label.hide()
            # Image cleared — restore full-widget border.
            self._bg_label.setGeometry(0, 0, self.width(), self.height())
        self._update_pixmap()

    # ── Qt events ─────────────────────────────────────────────────────────

    def resizeEvent(self, event):
        """Re-scale image and reposition layers whenever the widget is resized."""
        super().resizeEvent(event)
        if self._pixmap and not self._pixmap.isNull():
            self._update_pixmap()
        else:
            # No image: background always covers the whole widget.
            self._bg_label.setGeometry(0, 0, self.width(), self.height())

    # ── Internal helpers ──────────────────────────────────────────────────

    def _update_pixmap(self):
        """
        Scale the stored pixmap to fit the current widget size (KeepAspectRatio),
        then position both layers.

        Default mode:   _bg_label fills the entire widget (border never shrinks).
        Constrain mode: _bg_label shrinks to the scaled-image rect so the styled
                        border wraps tightly — no wide black bars beside the image.
        """
        if self._in_update:
            return
        if not (self._pixmap and not self._pixmap.isNull()):
            return

        self._in_update = True
        try:
            widget_size = self.size()

            # Always use the original full-resolution pixmap as source so
            # successive resize events never degrade quality.
            self._cached_scaled_pixmap = self._pixmap.scaled(
                widget_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

            scaled_size = self._cached_scaled_pixmap.size()
            self._image_label.setPixmap(self._cached_scaled_pixmap)

            # Centre the image label within the widget.
            x = (widget_size.width()  - scaled_size.width())  // 2
            y = (widget_size.height() - scaled_size.height()) // 2
            self._image_label.setGeometry(
                QRect(x, y, scaled_size.width(), scaled_size.height())
            )

            if self._constrain_width:
                # Tight mode: border frame follows the actual image bounds.
                # The area outside the frame is transparent → parent background
                # shows through, giving a clean professional look.
                self._bg_label.setGeometry(
                    x, y, scaled_size.width(), scaled_size.height()
                )
            else:
                # Legacy mode: background fills entire widget (original behaviour).
                self._bg_label.setGeometry(
                    0, 0, widget_size.width(), widget_size.height()
                )
            
            # Sinyali tetikle: gerçek resmi render ettiğimiz boyutları gönder
            self.scaled_size_changed.emit(scaled_size.width(), scaled_size.height())
        finally:
            self._in_update = False