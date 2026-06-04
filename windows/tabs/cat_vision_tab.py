# -*- coding: utf-8 -*-
"""
Created on Mon May  4 22:29:58 2026

@author: merta
"""

# -*- coding: utf-8 -*-
"""
Cat Vision Tab
==============
İki iç sekme:
  1. 🐱 Landmark + Segmentation  — YOLO-pose (FGS) ve YOLOv8m-seg eş zamanlı çalışır
  2. 🌡 Thermal                  — GhostNetV2 ONNX binary sınıflandırma

Konvansiyonlar (cat_disease_tab.py ile uyumlu):
  - YOLO / ONNX importları yalnızca run() içinde (lazy) — GUI bloke olmaz
  - device='cpu' / CPUExecutionProvider zorlanır (LattePanda CUDA kilitleniyor)
  - progress_update.emit(): 10 → import, 30 → model yükle, 60 → inference,
                            90 → görsel işle, 100 → bitti

@author: cat_vision
"""

# [RESP-PATCHED] responsive_utils entegrasyonu — responsive_patch.py tarafından eklendi
from utils.responsive_utils import (
    scale_value,
    get_responsive_pt,
    get_responsive_font_size,
    scale_stylesheet,
    apply_responsive_widget_scaling,
)

def _sv(base: int, mn: float = 0.4, mx: float = 2.0) -> int:
    """scale_value kısayolu — patch tarafından oluşturuldu."""
    return scale_value(base, min_ratio=mn, max_ratio=mx)

def _pt(base: int) -> int:
    """get_responsive_pt kısayolu — patch tarafından oluşturuldu."""
    return get_responsive_pt(base)

def _ss(css: str) -> str:
    """scale_stylesheet kısayolu — patch tarafından oluşturuldu."""
    return scale_stylesheet(css, scale_padding=True, scale_border_radius=True)

import os
import sys
import logging
import tempfile
import threading
from utils.model_downloader import download_model_sync

_landmark_model = None
_seg_model = None
_thermal_predictor = None
_vision_models_lock = threading.Lock()
_pending_lock = threading.Lock()

def _get_landmark_model():
    global _landmark_model
    with _vision_models_lock:
        if _landmark_model is None:
            from ultralytics import YOLO
            model_path = download_model_sync("ai_hub/cat_landmark/yolo26m-pose.onnx")
            _landmark_model = YOLO(model_path, task="pose")
        return _landmark_model

def _get_seg_model():
    global _seg_model
    with _vision_models_lock:
        if _seg_model is None:
            from ultralytics import YOLO
            model_path = download_model_sync("ai_hub/cat_segmentation/yolov8m-seg.onnx")
            _seg_model = YOLO(model_path, task="segment")
        return _seg_model

def _get_thermal_predictor():
    global _thermal_predictor
    with _vision_models_lock:
        if _thermal_predictor is None:
            from cat_thermal.inference_cat_thermal import CatThermalPredictor
            _thermal_predictor = CatThermalPredictor(model_name="GhostNetV2")
        return _thermal_predictor


from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QFileDialog, QProgressBar, QGroupBox, QTabWidget,
    QSlider,
)
from utils.responsive_label import ResponsiveImageLabel
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage

logger = logging.getLogger("CatVisionTab")

# Inference modülleri — artık ai_hub/ altında
current_dir = os.path.dirname(os.path.abspath(__file__))
ai_hub_dir = os.path.join(current_dir, "..", "..", "ai_hub")
if ai_hub_dir not in sys.path:
    sys.path.insert(0, ai_hub_dir)



# ══════════════════════════════════════════════════════════════
# Thread 1 — Landmark (YOLO-pose + FGS)
# ══════════════════════════════════════════════════════════════
class LandmarkInferenceThread(QThread):
    """YOLO-pose ile keypoint tespiti → compute_fgs → annotated QImage emit."""

    inference_finished = pyqtSignal(dict, QImage)
    progress_update    = pyqtSignal(int)
    error_occurred     = pyqtSignal(str)

    def __init__(self, image_path: str, parent=None):
        super().__init__(parent)
        self.image_path = image_path

    def run(self):
        self.progress_update.emit(10)
        try:
            import cv2
            import numpy as np
            self.progress_update.emit(20)

            model = _get_landmark_model()
            self.progress_update.emit(50)

            results = model.predict(self.image_path, conf=0.25, device="cpu", verbose=False)
            self.progress_update.emit(65)

            img = cv2.imread(self.image_path)
            fgs_result: dict = {}

            if results and len(results) > 0:
                r = results[0]
                if (r.keypoints is not None and len(r.keypoints.xy) > 0 and 
                    r.boxes is not None and len(r.boxes) > 0):
                    
                    kp_xy = r.keypoints.xy[0].cpu().numpy()  # shape: (N, 2)

                    # Keypoint'leri bbox'a normalize et
                    x1, y1, x2, y2 = r.boxes[0].xyxy[0].cpu().numpy()
                    bw = max(x2 - x1, 1.0)
                    bh = max(y2 - y1, 1.0)
                    kp_norm = kp_xy.copy()
                    kp_norm[:, 0] = (kp_norm[:, 0] - x1) / bw
                    kp_norm[:, 1] = (kp_norm[:, 1] - y1) / bh

                    # FGS hesapla — mevcut fonksiyon, sadece import edilir
                    from cat_landmark.inference_cat_landmark import compute_fgs
                    fgs_result = compute_fgs(kp_norm)

                    # Keypoint'leri görsel üzerine çiz
                    for pt in kp_xy:
                        px, py = int(pt[0]), int(pt[1])
                        if px > 0 or py > 0:
                            cv2.circle(img, (px, py), 4, (0, 255, 80), -1)

            self.progress_update.emit(90)

            # BGR → RGB → QImage
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            h, w, _ = rgb.shape
            q_img = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888).copy()

        except Exception as exc:
            logger.error("Landmark thread hatası: %s", exc, exc_info=True)
            self.error_occurred.emit(str(exc))
            self.progress_update.emit(100)
            return

        self.progress_update.emit(100)
        self.inference_finished.emit(fgs_result, q_img)


# ══════════════════════════════════════════════════════════════
# Thread 2 — Segmentation (YOLOv8m-seg)
# ══════════════════════════════════════════════════════════════
class SegmentationInferenceThread(QThread):
    """YOLOv8m-seg ile kedi maskesi → overlay QImage + özet metin emit."""

    inference_finished = pyqtSignal(str, QImage)
    progress_update    = pyqtSignal(int)
    error_occurred     = pyqtSignal(str)

    def __init__(self, image_path: str, conf: float = 0.25, iou: float = 0.7, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.conf = conf
        self.iou  = iou

    def run(self):
        self.progress_update.emit(10)
        try:
            import cv2
            import numpy as np
            self.progress_update.emit(20)

            model = _get_seg_model()
            self.progress_update.emit(50)

            results = model.predict(
                source=self.image_path,
                conf=self.conf,
                iou=self.iou,
                imgsz=640,
                device="cpu",
                verbose=False,
            )
            self.progress_update.emit(70)

            img = cv2.imread(self.image_path)
            r = results[0]
            lines = []

            if r.boxes is not None and len(r.boxes) > 0:
                n = len(r.boxes)
                lines.append(f"🐱  {n} kedi tespit edildi")
                for i, box in enumerate(r.boxes):
                    conf_pct = float(box.conf[0]) * 100
                    lines.append(f"  Kedi {i + 1}: %{conf_pct:.1f}")
            else:
                lines.append("Kedi tespit edilmedi.")

            # Mask overlay
            if r.masks is not None and len(r.masks) > 0:
                for mask_data in r.masks.data:
                    mask_np = mask_data.cpu().numpy()
                    mask_resized = cv2.resize(
                        mask_np, (img.shape[1], img.shape[0]),
                        interpolation=cv2.INTER_NEAREST,
                    )
                    colored = np.zeros_like(img)
                    colored[:, :, 1] = 160  # yeşil kanal
                    blend = cv2.addWeighted(img, 0.55, colored, 0.45, 0)
                    img = np.where(
                        mask_resized[:, :, None] > 0.5, blend, img
                    ).astype(np.uint8)

            self.progress_update.emit(90)

            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            h, w, _ = rgb.shape
            q_img = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888).copy()

        except Exception as exc:
            logger.error("Segmentation thread hatası: %s", exc, exc_info=True)
            self.error_occurred.emit(str(exc))
            self.progress_update.emit(100)
            return

        self.progress_update.emit(100)
        self.inference_finished.emit("\n".join(lines), q_img)


# ══════════════════════════════════════════════════════════════
# Thread 3 — Thermal (GhostNetV2 ONNX)
# ══════════════════════════════════════════════════════════════
class ThermalInferenceThread(QThread):
    """GhostNetV2 ONNX ile termal görüntü sınıflandırması."""

    inference_finished = pyqtSignal(dict)   # {label, prob_sick, confidence}
    progress_update    = pyqtSignal(int)
    error_occurred     = pyqtSignal(str)

    def __init__(self, image_path: str, threshold: float = 0.5, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.threshold  = threshold

    def run(self):
        self.progress_update.emit(10)
        try:
            self.progress_update.emit(30)
            
            predictor = _get_thermal_predictor()
            result    = predictor.predict(self.image_path, threshold=self.threshold)
            self.progress_update.emit(90)

        except Exception as exc:
            logger.error("Thermal thread hatası: %s", exc, exc_info=True)
            self.error_occurred.emit(str(exc))
            self.progress_update.emit(100)
            return

        self.progress_update.emit(100)
        self.inference_finished.emit(result)


# ══════════════════════════════════════════════════════════════
# Panel 1 — Landmark + Segmentation (eş zamanlı)
# ══════════════════════════════════════════════════════════════
class LandmarkSegPanel(QWidget):
    """Landmark ve Segmentation modellerini tek görüntüde aynı anda çalıştırır."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_image_path: str | None = None
        self._pending = 0           # Tamamlanmayı bekleyen thread sayısı
        self._landmark_thread = None
        self._seg_thread      = None
        self._init_ui()

    # ── UI kurulumu ──────────────────────────────────────────────
    def _init_ui(self):
        layout = QVBoxLayout(self)
        _m = _sv(10); _spacing = _sv(8)
        layout.setContentsMargins(_m, _m, _m, _m)
        layout.setSpacing(_spacing)

        # Başlık
        title = QLabel("🐱 Nokta İşareti / FGS  +  🔍 Segmentasyon")
        title.setStyleSheet(_ss(
            f"font-size: 11pt; font-weight: bold; color: #a78bfa;"))
        layout.addWidget(title)

        # Butonlar
        btn_row = QHBoxLayout()

        self.btn_load = QPushButton("📂  Görüntü Yükle")
        self.btn_load.setStyleSheet(_ss(
            f"padding: 5px 12px; font-size: 9pt; background-color: #334155; "
            f"color: white; border-radius: 5px;"
        ))
        self.btn_load.clicked.connect(self._load_image)
        btn_row.addWidget(self.btn_load)

        self.btn_snapshot = QPushButton("📸  AI Pro Anlık Görüntü")
        self.btn_snapshot.setStyleSheet(_ss(
            f"padding: 5px 12px; font-size: 9pt; background-color: #1e3a5f; "
            f"color: white; border-radius: 5px;"
        ))
        self.btn_snapshot.setToolTip("AI Pro kamerası açıkken son kareyi alır.")
        self.btn_snapshot.setEnabled(False)
        btn_row.addWidget(self.btn_snapshot)

        self.btn_analyze = QPushButton("▶  Her İkisini Çalıştır")
        self.btn_analyze.setStyleSheet(_ss(
            f"padding: 5px 12px; font-size: 9pt; background-color: #7c3aed; color: white; "
            f"border-radius: 5px; font-weight: bold;"
        ))
        self.btn_analyze.setEnabled(False)
        self.btn_analyze.clicked.connect(self._start_both)
        btn_row.addWidget(self.btn_analyze)

        layout.addLayout(btn_row)

        # Progress çubuklarının ayrı satırları
        prog_row = QHBoxLayout()
        prog_row.setSpacing(15)

        lm_col = QVBoxLayout()
        lm_col.addWidget(QLabel("⏳ Nokta İşareti:"))
        self.lm_progress = QProgressBar()
        self.lm_progress.setVisible(False)
        lm_col.addWidget(self.lm_progress)
        prog_row.addLayout(lm_col)

        seg_col = QVBoxLayout()
        seg_col.addWidget(QLabel("⏳ Segmentasyon:"))
        self.seg_progress = QProgressBar()
        self.seg_progress.setVisible(False)
        seg_col.addWidget(self.seg_progress)
        prog_row.addLayout(seg_col)

        layout.addLayout(prog_row)

        # ── İçerik: Preview (sol) + Sonuçlar (sağ) ───────────────
        content_row = QHBoxLayout()
        content_row.setSpacing(12)

        # Sol: iki önizleme
        self.preview_widget = QWidget()
        preview_col = QVBoxLayout(self.preview_widget)
        preview_col.setContentsMargins(0, 0, 0, 0)
        preview_col.setSpacing(8)

        lbl_lm = QLabel("🐱 Nokta İşareti (annotated):")
        lbl_lm.setStyleSheet(_ss(
            f"color: #a78bfa; font-size: 9pt; font-weight: bold;"))
        preview_col.addWidget(lbl_lm)

        self.lm_preview = ResponsiveImageLabel("Görüntü yüklenmedi")
        self.lm_preview.set_constrain_width(True)
        self.lm_preview.setMinimumHeight(_sv(150))
        self.lm_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lm_preview.setStyleSheet(_ss(
            "background-color: rgba(0,0,0,80); border: 2px dashed #7c3aed; "
            f"border-radius: 8px; color: #94a3b8;"
        ))
        preview_col.addWidget(self.lm_preview, stretch=1)

        lbl_seg = QLabel("🔍 Segmentasyon (maske):")
        lbl_seg.setStyleSheet(_ss(
            f"color: #10b981; font-size: 9pt; font-weight: bold;"))
        preview_col.addWidget(lbl_seg)

        self.seg_preview = ResponsiveImageLabel("Görüntü yüklenmedi")
        self.seg_preview.set_constrain_width(True)
        self.seg_preview.setMinimumHeight(_sv(150))
        self.seg_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.seg_preview.setStyleSheet(_ss(
            "background-color: rgba(0,0,0,80); border: 2px dashed #10b981; "
            f"border-radius: 8px; color: #94a3b8;"
        ))
        preview_col.addWidget(self.seg_preview, stretch=1)

        content_row.addWidget(self.preview_widget, stretch=1)

        from PyQt6.QtWidgets import QScrollArea
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent;")

        right_widget = QWidget()
        result_col = QVBoxLayout(right_widget)
        result_col.setSpacing(10)
        result_col.setContentsMargins(0, 0, 0, 0)

        # FGS grubu
        fgs_group = QGroupBox("📊 FGS Sonucu (Kedi Yüz Ağrı Ölçeği)")
        fgs_group.setStyleSheet(_ss(
            f"QGroupBox {{ color: #a78bfa; font-size: 10pt; font-weight: bold; border: 1px solid #a78bfa; "
            f"border-radius: 6px; margin-top: 8px; padding-top: 6px; }}"
            f"QGroupBox::title {{ subcontrol-origin: margin; left: 8px; }}"
        ))
        fgs_inner = QVBoxLayout(fgs_group)

        self.fgs_badge = QLabel("—")
        self.fgs_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.fgs_badge.setMinimumHeight(28)
        self.fgs_badge.setMaximumHeight(38)
        self.fgs_badge.setWordWrap(True)
        self.fgs_badge.setStyleSheet(_ss(
            f"font-size: 9pt; font-weight: bold; "
            f"padding: 4px 8px; "
            f"border-radius: 6px; background-color: rgba(0,0,0,60); color: white;"
        ))
        fgs_inner.addWidget(self.fgs_badge)

        self.fgs_detail = QTextEdit()
        self.fgs_detail.setReadOnly(True)
        self.fgs_detail.setMinimumHeight(_sv(200))
        self.fgs_detail.setMaximumHeight(_sv(350))
        self.fgs_detail.setPlaceholderText("FGS detayları burada görünecek...")
        self.fgs_detail.setStyleSheet(
            f"font-size: 10pt; background-color: rgba(0,0,0,80); color: white; "
            f"border: 1px solid #6d28d9; border-radius: 5px; padding: 6px;"
        )
        fgs_inner.addWidget(self.fgs_detail)
        result_col.addWidget(fgs_group)

        # Segmentation sonuç grubu
        seg_group = QGroupBox("🔍 Segmentasyon Sonucu")
        seg_group.setStyleSheet(_ss(
            f"QGroupBox {{ color: #10b981; font-size: 10pt; font-weight: bold; border: 1px solid #10b981; "
            f"border-radius: 6px; margin-top: 8px; padding-top: 6px; }}"
            f"QGroupBox::title {{ subcontrol-origin: margin; left: 8px; }}"
        ))
        seg_inner = QVBoxLayout(seg_group)

        self.seg_result_area = QTextEdit()
        self.seg_result_area.setReadOnly(True)
        self.seg_result_area.setMinimumHeight(_sv(150))
        self.seg_result_area.setMaximumHeight(_sv(250))
        self.seg_result_area.setPlaceholderText("Tespit sonuçları burada görünecek...")
        self.seg_result_area.setStyleSheet(
            f"font-size: 10pt; background-color: rgba(0,0,0,80); color: white; "
            f"border: 1px solid #059669; border-radius: 5px; padding: 6px;"
        )
        seg_inner.addWidget(self.seg_result_area)
        result_col.addWidget(seg_group)

        result_col.addStretch()
        scroll.setWidget(right_widget)
        apply_responsive_widget_scaling(self)  # [RESP-PATCHED]
        content_row.addWidget(scroll, stretch=2)
        layout.addLayout(content_row, stretch=1)

    # ── Snapshot (AI Pro kamerasından) ───────────────────────────
    def set_snapshot(self, q_img: QImage):
        """Dışarıdan gelen QImage'ı geçici dosyaya yazar ve önizlemeyi günceller."""
        old = getattr(self, "_temp_snapshot_path", None)
        if old and os.path.exists(old):
            try:
                os.unlink(old)
            except OSError:
                pass

        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        tmp.close()
        q_img.save(tmp.name, "JPEG")
        self._temp_snapshot_path = tmp.name
        self.selected_image_path = tmp.name

        # Ön-ölçekleme YAPILMIYOR — ResponsiveImageLabel kendi boyutuna göre ölçekler.
        pix = QPixmap.fromImage(q_img)
        self.lm_preview.setPixmap(pix)
        self.seg_preview.setPixmap(pix)
        self.btn_analyze.setEnabled(True)
        self.fgs_badge.setText("—")
        self.fgs_detail.clear()
        self.seg_result_area.clear()
        logger.info("Snapshot alındı → %s", tmp.name)

    # ── Dosya yükle ──────────────────────────────────────────────
    def _load_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Görüntü Seç", "",
            "Resim Dosyaları (*.png *.jpg *.jpeg *.bmp *.tiff)",
        )
        if not path:
            return
        self.selected_image_path = path
        pix = QPixmap(path)
        self.lm_preview.setPixmap(pix)
        self.seg_preview.setPixmap(pix)
        self.btn_analyze.setEnabled(True)
        self.fgs_badge.setText("—")
        self.fgs_detail.clear()
        self.seg_result_area.clear()

    # ── Her iki modeli eş zamanlı başlat ─────────────────────────
    def _start_both(self):
        if not self.selected_image_path:
            return

        self.btn_analyze.setEnabled(False)
        self.btn_load.setEnabled(False)
        self._pending = 2

        # Önce Landmark thread başlar
        self.lm_progress.setValue(0)
        self.lm_progress.setVisible(True)
        self._landmark_thread = LandmarkInferenceThread(self.selected_image_path)
        self._landmark_thread.progress_update.connect(self.lm_progress.setValue)
        self._landmark_thread.inference_finished.connect(self._on_landmark_done_seq)
        self._landmark_thread.error_occurred.connect(self._on_landmark_err_seq)
        self._landmark_thread.start()

    def _start_seg_seq(self):
        self.seg_progress.setValue(0)
        self.seg_progress.setVisible(True)
        self._seg_thread = SegmentationInferenceThread(self.selected_image_path)
        self._seg_thread.progress_update.connect(self.seg_progress.setValue)
        self._seg_thread.inference_finished.connect(self._on_seg_done)
        self._seg_thread.error_occurred.connect(
            lambda e: self._on_thread_error("Segmentation", e)
        )
        self._seg_thread.start()

    def _on_landmark_done_seq(self, fgs_dict: dict, q_img: QImage):
        self._on_landmark_done(fgs_dict, q_img)
        self._start_seg_seq()

    def _on_landmark_err_seq(self, err: str):
        self._on_thread_error("Landmark", err)
        self._start_seg_seq()

    # ── Thread callbackleri ───────────────────────────────────────
    # ── Çeviri sözlükleri ────────────────────────────────────────
    _AU_TR = {
        "AU1_Ear_Position":       "AU1 Kulak Pozisyonu",
        "AU2_Orbital_Tightening": "AU2 Göz Çevresi Gerilimi",
        "AU3_Muzzle_Tension":     "AU3 Burun/Ağız Gerilimi",
        "AU4_Whisker_Position":   "AU4 Bıyık Pozisyonu",
        "AU5_Head_Position":      "AU5 Baş Pozisyonu",
    }
    _DESC_TR = {
        "Flattened & rotated outwardly": "Düzleşmiş ve dışa dönük",
        "Slightly flattened":            "Hafifçe düzleşmiş",
        "Natural/neutral":               "Doğal / nötr",
        "Open":                          "Açık",
        "Slightly closed":               "Hafifçe kapalı",
        "Closed/squinted":               "Kapalı / kısılmış",
        "Relaxed, round":                "Gevşek, yuvarlak",
        "Slightly tense":                "Hafif gergin",
        "Tense, angular":                "Gergin, köşeli",
        "Straight, stiff & forward":     "Düz, gergin ve öne dönük",
        "Slightly backward":             "Hafifçe geriye dönük",
        "Backward/flat":                 "Geriye / düz yatmış",
        "Raised & upright":              "Yukarı kaldırılmış, dik",
        "Below shoulders, lowered":      "Omuzların altında, aşağıda",
        "Level with body":               "Vücutla aynı hizada",
    }
    _PAIN_LEVEL_TR = {
        "No Pain":  "Ağrı Yok",
        "Mild":     "Hafif Ağrı",
        "Moderate": "Orta Şiddetli Ağrı",
        "Severe":   "Şiddetli Ağrı",
    }

    def _on_landmark_done(self, fgs_dict: dict, q_img: QImage):
        # Ön-ölçekleme YAPILMIYOR — ResponsiveImageLabel widget boyutuna göre
        # orantılı ölçeklemeyi zaten kendi içinde yönetir.
        pix = QPixmap.fromImage(q_img)
        self.lm_preview.setPixmap(pix)
        self.lm_progress.setVisible(False)

        # FIX: model "fgs_total" anahtarı döndürüyor, "total" değil
        total = fgs_dict.get("fgs_total", fgs_dict.get("total", None))

        if total is not None:
            if total < 4:
                color, badge_text = "#22c55e", f"🟢 Ağrı Yok  ({total}/10)"
            elif total <= 7:
                color, badge_text = "#f59e0b", f"🟡 Orta Ağrı  ({total}/10)"
            else:
                color, badge_text = "#ef4444", f"🔴 Şiddetli Ağrı  ({total}/10)"

            self.fgs_badge.setText(badge_text)
            self.fgs_badge.setStyleSheet(
                f"font-size: 9.5pt; font-weight: bold; "
                f"padding: 4px 8px; "
                f"border-radius: 6px; "
                f"background-color: {color}22; color: {color};"
            )

            # ── Detay metnini Türkçe ve okunabilir biçimde oluştur ──
            pain_level_raw = fgs_dict.get("pain_level", "")
            pain_level_tr  = self._PAIN_LEVEL_TR.get(pain_level_raw, pain_level_raw)
            pain_flag      = "✅ Ağrı var" if fgs_dict.get("pain") else "✅ Ağrı yok"

            detail_lines = [
                f"Ağrı Seviyesi : {pain_level_tr}",
                f"Durum         : {pain_flag}",
                f"Toplam Skor   : {total} / 10",
                "─" * 38,
            ]

            action_units = fgs_dict.get("action_units", {})
            if isinstance(action_units, dict):
                for au_key, au_data in action_units.items():
                    if not isinstance(au_data, dict):
                        continue
                    score = au_data.get("score", "?")
                    desc  = au_data.get("description", "")
                    au_name_tr = self._AU_TR.get(au_key, au_key)
                    desc_tr    = self._DESC_TR.get(desc, desc)
                    detail_lines.append(f"• {au_name_tr}: {score}/2  —  {desc_tr}")

            self.fgs_detail.setText("\n".join(detail_lines))

        else:
            self.fgs_badge.setText("⚠️ Kilit Nokta Tespit Edilemedi")
            self.fgs_badge.setStyleSheet(
                "font-size: 10pt; font-weight: bold; padding: 6px 10px; border-radius: 8px;"
                " background-color: rgba(245,158,11,0.15); color: #f59e0b;"
            )
            # Ham veriyi düzgün satırlara dök (debug için)
            lines = []
            for k, v in fgs_dict.items():
                lines.append(f"{k}: {v}")
            self.fgs_detail.setText("\n".join(lines) if lines else "Veri yok")

        self._finish_one()

    def _on_seg_done(self, summary: str, q_img: QImage):
        pix = QPixmap.fromImage(q_img)
        self.seg_preview.setPixmap(pix)
        self.seg_result_area.setText(summary)
        self.seg_progress.setVisible(False)
        self._finish_one()

    def _on_thread_error(self, model_name: str, error_msg: str):
        if model_name == "Landmark":
            self.fgs_badge.setText(f"❌ Hata")
            self.fgs_detail.setText(error_msg)
            self.lm_progress.setVisible(False)
        else:
            self.seg_result_area.setText(f"❌ Hata: {error_msg}")
            self.seg_progress.setVisible(False)
        self._finish_one()

    def _finish_one(self):
        """Her thread bittiğinde çağrılır; ikisi de bitince butonları aç."""
        with _pending_lock:
            self._pending -= 1
            if self._pending <= 0:
                self._pending = 0
                self.btn_analyze.setEnabled(True)
                self.btn_load.setEnabled(True)

    def closeEvent(self, event):
        for attr in ("_landmark_thread", "_seg_thread"):
            t = getattr(self, attr, None)
            if t is not None and t.isRunning():
                t.quit()
                t.wait(3000)
        super().closeEvent(event)


# ══════════════════════════════════════════════════════════════
# Panel 2 — Thermal
# ══════════════════════════════════════════════════════════════
class ThermalPanel(QWidget):
    """GhostNetV2 ONNX ile termal görüntü binary sınıflandırması."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_image_path: str | None = None
        self._thread = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        _m = _sv(10); _spacing = _sv(8)
        layout.setContentsMargins(_m, _m, _m, _m)
        layout.setSpacing(_spacing)

        title = QLabel("🌡 Termal Analiz (GhostNetV2 ONNX)")
        title.setStyleSheet(_ss(
            f"font-size: 11pt; font-weight: bold; color: #f97316;"))
        layout.addWidget(title)

        # Butonlar
        btn_row = QHBoxLayout()

        self.btn_load = QPushButton("📂  Termal Görüntü Yükle")
        self.btn_load.setStyleSheet(_ss(
            f"padding: 5px 12px; font-size: 9pt; background-color: #334155; "
            f"color: white; border-radius: 5px;"
        ))
        self.btn_load.clicked.connect(self._load_image)
        btn_row.addWidget(self.btn_load)

        self.btn_analyze = QPushButton("🔥  Analiz Et")
        self.btn_analyze.setStyleSheet(_ss(
            f"padding: 5px 12px; font-size: 9pt; background-color: #c2410c; color: white; "
            f"border-radius: 5px; font-weight: bold;"
        ))
        self.btn_analyze.setEnabled(False)
        self.btn_analyze.clicked.connect(self._start_inference)
        btn_row.addWidget(self.btn_analyze)

        layout.addLayout(btn_row)

        # Eşik slider
        thresh_row = QHBoxLayout()
        thresh_lbl = QLabel("Eşik Değeri:")
        thresh_lbl.setStyleSheet(_ss(f"font-size: 9pt; color: #e2e8f0;"))
        thresh_row.addWidget(thresh_lbl)
        self.threshold_slider = QSlider(Qt.Orientation.Horizontal)
        self.threshold_slider.setRange(10, 90)
        self.threshold_slider.setValue(50)
        self.threshold_slider.setTickInterval(10)
        self.threshold_slider.valueChanged.connect(
            lambda v: self.threshold_label.setText(f"{v / 100:.2f}")
        )
        thresh_row.addWidget(self.threshold_slider)
        self.threshold_label = QLabel("0.50")
        self.threshold_label.setMinimumWidth(38)
        self.threshold_label.setStyleSheet(_ss(f"font-size: 9pt; font-weight: bold; color: #f97316;"))
        thresh_row.addWidget(self.threshold_label)
        layout.addLayout(thresh_row)

        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # İçerik
        content_row = QHBoxLayout()
        content_row.setSpacing(12)

        self.thermal_preview_widget = QWidget()
        thermal_preview_lay = QVBoxLayout(self.thermal_preview_widget)
        thermal_preview_lay.setContentsMargins(0, 0, 0, 0)
        
        self.image_preview = ResponsiveImageLabel("Görüntü yüklenmedi")
        self.image_preview.set_constrain_width(True)
        self.image_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_preview.setStyleSheet(_ss(
            "background-color: rgba(0,0,0,80); border: 2px dashed #f97316; "
            f"border-radius: 8px; color: #94a3b8;"
        ))
        thermal_preview_lay.addWidget(self.image_preview)
        
        content_row.addWidget(self.thermal_preview_widget, stretch=1)

        right_col = QVBoxLayout()
        right_col.setSpacing(12)

        self.result_badge = QLabel("—")
        self.result_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.result_badge.setMinimumHeight(48)
        self.result_badge.setStyleSheet(_ss(
            f"font-size: 12pt; font-weight: bold; padding: 8px; "
            f"border-radius: 8px; background-color: rgba(0,0,0,60); color: white;"
        ))
        right_col.addWidget(self.result_badge)

        sick_lbl = QLabel("Hasta Olasılığı:")
        sick_lbl.setStyleSheet(_ss(
            f"color: #94a3b8; font-size: 9pt;"))
        right_col.addWidget(sick_lbl)

        self.sick_prob_bar = QProgressBar()
        self.sick_prob_bar.setRange(0, 100)
        self.sick_prob_bar.setValue(0)
        self.sick_prob_bar.setStyleSheet(_ss(
            f"QProgressBar {{ border: 1px solid #f97316; border-radius: 4px; "
            f"background: rgba(0,0,0,60); text-align: center; color: white; font-size: 9pt; }}"
            f"QProgressBar::chunk {{ background-color: #ef4444; border-radius: 4px; }}"
        ))
        right_col.addWidget(self.sick_prob_bar)

        right_col.addStretch()
        content_row.addLayout(right_col, stretch=2)
        layout.addLayout(content_row, stretch=1)
        apply_responsive_widget_scaling(self)  # [RESP-PATCHED]

    def _load_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Termal Görüntü Seç", "",
            "Resim Dosyaları (*.png *.jpg *.jpeg *.bmp *.tiff)",
        )
        if not path:
            return
        self.selected_image_path = path
        pix = QPixmap(path)
        self.image_preview.setPixmap(pix)
        self.btn_analyze.setEnabled(True)
        self.result_badge.setText("—")
        self.result_badge.setStyleSheet(_ss(
            f"font-size: 12pt; font-weight: bold; padding: 8px; "
            f"border-radius: 8px; background-color: rgba(0,0,0,60); color: white;"
        ))
        self.sick_prob_bar.setValue(0)

    def _start_inference(self):
        if not self.selected_image_path:
            return
        self.btn_load.setEnabled(False)
        self.btn_analyze.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.result_badge.setText("⏳ Analiz ediliyor…")

        threshold = self.threshold_slider.value() / 100.0
        self._thread = ThermalInferenceThread(self.selected_image_path, threshold=threshold)
        self._thread.progress_update.connect(self.progress_bar.setValue)
        self._thread.inference_finished.connect(self._on_done)
        self._thread.error_occurred.connect(self._on_error)
        self._thread.start()

    def _on_done(self, result: dict):
        label      = result.get("label", "Unknown")
        prob_sick  = float(result.get("probability_sick", 0.0))
        confidence = float(result.get("confidence", 0.0))

        is_sick = label.upper() == "SICK"
        color   = "#ef4444" if is_sick else "#22c55e"
        icon    = "🔴" if is_sick else "🟢"
        label_tr = "HASTA" if is_sick else "SAĞLIKLI"

        self.result_badge.setText(f"{icon} {label_tr}  %{confidence * 100:.1f}")
        self.result_badge.setStyleSheet(_ss(
            f"font-size: 12.5pt; font-weight: bold; "
            f"padding: 8px; border-radius: 8px; "
            f"background-color: {color}22; color: {color};"
        ))
        self.sick_prob_bar.setValue(int(prob_sick * 100))
        self.progress_bar.setVisible(False)
        self.btn_load.setEnabled(True)
        self.btn_analyze.setEnabled(True)

    def _on_error(self, error_msg: str):
        self.result_badge.setText("❌ Hata")
        self.result_badge.setStyleSheet(_ss(
            f"font-size: 11pt; font-weight: bold; "
            f"padding: 8px; border-radius: 8px; "
            f"background-color: rgba(239,68,68,0.15); color: #ef4444;"
        ))
        self.fgs_detail_fallback = error_msg  # log amaçlı
        logger.error("Thermal panel hata: %s", error_msg)
        self.progress_bar.setVisible(False)
        self.btn_load.setEnabled(True)
        self.btn_analyze.setEnabled(True)

    def closeEvent(self, event):
        if getattr(self, '_thread', None) is not None and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(3000)
        super().closeEvent(event)


# ══════════════════════════════════════════════════════════════
# Ana widget — CatVisionTab
# ══════════════════════════════════════════════════════════════
class CatVisionTab(QWidget):
    """
    unified_control_window.py'ye eklenen sekme.

    Dışarıdan erişilen tek method:
        receive_camera_frame(q_img: QImage)
            → AI Pro kamerası açıkken son kareyi LandmarkSegPanel'e iletir.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_frame: QImage | None = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        inner_tabs = QTabWidget(self)
        inner_tabs.setStyleSheet(_ss(
            f"QTabWidget::pane {{ border: 1px solid #4c1d95; border-radius: 4px; }}"
            f"QTabBar::tab {{ background: #1e1b4b; color: #94a3b8;"
            f"  padding: 6px 14px; font-size: 10pt; font-weight: 600; border-radius: 4px; "
            f"  margin: 2px; }}"
            f"QTabBar::tab:selected {{ background: #4c1d95; color: white; font-weight: bold; }}"
            f"QTabBar::tab:hover    {{ background: #312e81; color: #e2e8f0; }}"
        ))

        self.landmark_seg_panel = LandmarkSegPanel()
        self.thermal_panel      = ThermalPanel()

        inner_tabs.addTab(self.landmark_seg_panel, "🐱 Nokta İşareti + Segmentasyon")
        inner_tabs.addTab(self.thermal_panel,      "🌡 Termal Analiz")

        layout.addWidget(inner_tabs)

    # ── AI Pro kamerası entegrasyonu ─────────────────────────────
    def receive_camera_frame(self, q_img: QImage):
        """
        _on_camera_frame_ready tarafından çağrılır.
        Son kareyi saklar, snapshot butonunu aktifleştirir (bir kez bağlar).
        """
        self._last_frame = q_img

        btn = self.landmark_seg_panel.btn_snapshot
        if not btn.isEnabled():
            btn.setEnabled(True)
            # Önceki bağlantıları temizle, ardından bir kez bağla
            try:
                btn.clicked.disconnect()
            except (RuntimeError, TypeError): # <-- HATA BURADA ÇÖZÜLÜYOR
                pass
            btn.clicked.connect(self._take_snapshot)
    def _take_snapshot(self):
        if self._last_frame is not None:
            self.landmark_seg_panel.set_snapshot(self._last_frame)
            # Buton snapshot alındıktan sonra pasif olsun
            self.landmark_seg_panel.btn_snapshot.setEnabled(False)

    def closeEvent(self, event):
        for panel in (getattr(self, 'landmark_seg_panel', None), getattr(self, 'thermal_panel', None)):
            if panel is not None:
                panel.close()
        super().closeEvent(event)