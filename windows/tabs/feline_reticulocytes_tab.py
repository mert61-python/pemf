# -*- coding: utf-8 -*-
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
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QTextEdit, QFileDialog, QProgressBar)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap
from utils.responsive_label import ResponsiveImageLabel

current_dir = os.path.dirname(os.path.abspath(__file__))
ai_hub_dir = os.path.join(current_dir, '..', '..', 'ai_hub')
if ai_hub_dir not in sys.path:
    sys.path.insert(0, ai_hub_dir)

import threading
_retic_model = None
_retic_lock = threading.Lock()

def _get_retic_model():
    global _retic_model
    with _retic_lock:
        if _retic_model is None:
            from ultralytics import YOLO
            from utils.model_downloader import download_model_sync
            repo_path = "ai_hub/feline_reticulocytes/yolov8s.onnx"
            model_path = download_model_sync(repo_path)
            _retic_model = YOLO(model_path, task="detect")
        return _retic_model


class ReticulocytesInferenceThread(QThread):
    inference_finished = pyqtSignal(str, str)
    progress_update = pyqtSignal(int)

    def __init__(self, image_path, parent=None):
        super().__init__(parent)
        self.image_path = image_path

    def run(self):
        self.progress_update.emit(10)
        try:
            model = _get_retic_model()
            self.progress_update.emit(40)

            import tempfile
            # PyInstaller exe'sinde "Program Files" izni (WinError 5) olmaması için sonuçlar APPDATA'ya yazılır.
            temp_project = os.path.join(os.environ.get("APPDATA", tempfile.gettempdir()), "PEMF_GUI", "ai_results")
            
            output_dir = os.path.join(
                temp_project,
                'feline_reticulocytes',
                'results'
            )
            os.makedirs(output_dir, exist_ok=True)
            
            results = model.predict(
                source=self.image_path, conf=0.25, iou=0.7,
                imgsz=640, device='cpu', save=True,
                project=os.path.join(temp_project, 'feline_reticulocytes'),
                name='results', exist_ok=True,
            )
            self.progress_update.emit(80)

            # Sınıf isimleri Türkçe
            CLASS_NAMES_TR = {
                'erythrocyte':             'Eritrosit',
                'punctate reticulocyte':   'Noktalı Retikülosit',
                'aggregate reticulocyte':  'Agrege Retikülosit',
            }
            CLASS_NAMES = list(CLASS_NAMES_TR.keys())
            total_counts = {c: 0 for c in CLASS_NAMES}

            for r in results:
                if r.boxes is not None:
                    for box in r.boxes:
                        cls_id = int(box.cls[0])
                        total_counts[CLASS_NAMES[cls_id]] += 1
            
            result_lines = [
                f'İşlenen Görüntü: {os.path.basename(self.image_path)}',
                '─' * 40,
            ]
            for eng_name, cnt in total_counts.items():
                tr_name = CLASS_NAMES_TR[eng_name]
                result_lines.append(f'• {tr_name}: {cnt}')
            
            result_str = '\n'.join(result_lines)
            saved_image_path = os.path.join(output_dir, os.path.basename(self.image_path))

            self.progress_update.emit(100)
            self.inference_finished.emit(result_str, saved_image_path)
            
        except Exception as e:
            self.progress_update.emit(100)
            self.inference_finished.emit(f'Hata oluştu: {str(e)}', '')


class FelineReticulocytesTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        self.selected_image_path = None

    def _init_ui(self):
        layout = QVBoxLayout(self)
        _m = _sv(20); _spacing = _sv(15)
        layout.setContentsMargins(_m, _m, _m, _m)
        layout.setSpacing(_spacing)

        # Başlık
        title_label = QLabel('Kedi Retikülosit Sayımı (Kan / Mikroskopi) Modülü')
        title_label.setStyleSheet(
            f'font-size: 14pt; font-weight: bold; color: #10b981;')
        layout.addWidget(title_label)

        # ── Görüntü önizleme alanı ──────────────────────────────────────
        # set_constrain_width(True): yüklenen resim ne boyutta olursa olsun,
        # dashed border yalnızca gerçek resim alanını sarar — yanlarda geniş
        # siyah boşluk kalmaz. Widget tam genişlikte kalır; arka plan üst
        # konteynerin rengini gösterir → profesyonel, responsive görünüm.
        self.image_preview = ResponsiveImageLabel('Henüz Görüntü Yüklenmedi')
        self.image_preview.setMinimumHeight(_sv(300))
        self.image_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_preview.setStyleSheet(_ss(
            'background-color: rgba(0, 0, 0, 100); border: 2px dashed #9ca3af; '
            f'border-radius: 10px; color: white;'
        ))
        self.image_preview.set_constrain_width(True)   # ← DÜZELTME: kenara sıkıştır
        layout.addWidget(self.image_preview, stretch=2)

        # Kontrol butonları
        ctrl_layout = QHBoxLayout()
        
        self.btn_load = QPushButton('📂  Görüntü Yükle')
        self.btn_load.setStyleSheet(
            f'padding: 8px 14px; background-color: #334155; '
            f'color: white; border-radius: 5px;'
        )
        self.btn_load.clicked.connect(self.load_image)
        ctrl_layout.addWidget(self.btn_load)

        self.btn_analyze = QPushButton('🔬  Hücreleri Say (Analiz Başlat)')
        self.btn_analyze.setEnabled(False)
        self.btn_analyze.setStyleSheet(
            f'background-color: #10b981; color: white; font-weight: bold; '
            f'border-radius: 5px; padding: 10px;'
        )
        self.btn_analyze.clicked.connect(self.start_analysis)
        ctrl_layout.addWidget(self.btn_analyze)
        
        layout.addLayout(ctrl_layout)

        # İlerleme çubuğu
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # ── Sonuç alanı ─────────────────────────────────────────────────
        # setMaximumHeight kaldırıldı; stretch=1 ile kalan dikey alanı
        # kullanır → kaydırma gerekmeden tüm hücre sayım sonuçları görünür.
        self.result_area = QTextEdit()
        self.result_area.setReadOnly(True)
        self.result_area.setMinimumHeight(_sv(150))
        # ↑ setMaximumHeight kaldırıldı — sonuçlar tam görünsün
        self.result_area.setPlaceholderText('Hücre sayım sonuçları burada görüntülenecek...')
        self.result_area.setStyleSheet(
            f'font-size: 11pt; background-color: rgba(0, 0, 0, 100); color: white; '
            f'border: 1px solid #10b981; border-radius: 5px; padding: 10px;'
        )
        layout.addWidget(self.result_area, stretch=1)
        # ↑ addStretch() kaldırıldı — sonuç alanı boş alanı doldursun

        apply_responsive_widget_scaling(self)  # [RESP-PATCHED]

    def load_image(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self, 'Mikroskop Görüntüsü Seç', '',
            'Resim Dosyaları (*.png *.jpg *.jpeg)'
        )
        if file_name:
            self.selected_image_path = file_name
            pixmap = QPixmap(file_name)
            self.image_preview.setPixmap(pixmap)
            self.btn_analyze.setEnabled(True)
            self.result_area.clear()

    def start_analysis(self):
        if not self.selected_image_path:
            return

        self.btn_load.setEnabled(False)
        self.btn_analyze.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.result_area.clear()

        self.thread = ReticulocytesInferenceThread(self.selected_image_path)
        self.thread.progress_update.connect(self.progress_bar.setValue)
        self.thread.inference_finished.connect(self.on_inference_finished)
        self.thread.start()

    def on_inference_finished(self, result_text, saved_image_path):
        self.result_area.setText(result_text)
        
        if saved_image_path and os.path.exists(saved_image_path):
            pixmap = QPixmap(saved_image_path)
            self.image_preview.setPixmap(pixmap)
            
        self.btn_load.setEnabled(True)
        self.btn_analyze.setEnabled(True)
        self.progress_bar.setVisible(False)

    def closeEvent(self, event):
        if getattr(self, 'thread', None) is not None and self.thread.isRunning():
            self.thread.quit()
            self.thread.wait(3000)
        super().closeEvent(event)