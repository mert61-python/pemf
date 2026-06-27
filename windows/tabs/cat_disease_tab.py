# -*- coding: utf-8 -*-
import os
import sys
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QTextEdit, QGroupBox, QFormLayout,
                             QLineEdit, QProgressBar, QListWidget,
                             QListWidgetItem, QAbstractItemView)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
import logging

from utils.responsive_utils import (
    scale_value,
    get_responsive_pt,
    get_responsive_font_size,
    scale_stylesheet,
    apply_responsive_widget_scaling,
)

def _sv(base: int, mn: float = 0.4, mx: float = 2.0) -> int:
    return scale_value(base, min_ratio=mn, max_ratio=mx)

def _pt(base: int) -> int:
    return get_responsive_pt(base)

def _ss(css: str) -> str:
    return scale_stylesheet(css, scale_padding=True, scale_border_radius=True)

# Loglama ayarları
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('CatDiseaseTab')

# Modül yolunu ekle (ai_hub kullanılıyor)
current_dir = os.path.dirname(os.path.abspath(__file__))
# ai_hub import için sys.path'e eklenebilir veya projenin kökü olduğu için doğrudan import edilebilir.

# Semptom listesi — inference_cat_disease.py ile senkron tutulmalı (1-tabanlı indeks)
SYMPTOM_LIST = [
    "İştah Kaybı",           # 1
    "Kusma",                  # 2
    "İshal",                  # 3
    "Öksürük",                # 4
    "Solunum Güçlüğü",        # 5
    "Topallık",               # 6
    "Deri Lezyonları",        # 7
    "Burun Akıntısı",         # 8
    "Göz Akıntısı",           # 9
    "Halsizlik / Uyuşukluk",  # 10
    "Kilo Kaybı",             # 11
    "Hapşırma",               # 12
    "Dehidrasyon",            # 13
    "Ateş",                   # 14
]

MIN_SYMPTOMS = 2   # Modelin anlamlı tahmin yapması için önerilen minimum semptom sayısı
MAX_SYMPTOMS = 14  # Modelin eğitildiği maksimum semptom sayısı


class DiseaseInferenceThread(QThread):
    inference_finished = pyqtSignal(str)
    progress_update = pyqtSignal(int)

    def __init__(self, patient_data, parent=None):
        super().__init__(parent)
        self.patient_data = patient_data

    def run(self):
        logger.info("DiseaseInferenceThread başlatıldı.")
        self.progress_update.emit(20)
        try:
            logger.info("XGBoost modeli Hugging Face'ten indiriliyor (gerekirse)...")
            from utils.model_downloader import download_model_sync
            download_model_sync("ai_hub/cat_disease/XGBoost.pkl")

            logger.info("CatDiseasePredictor içe aktarılıyor...")
            from ai_hub.cat_disease.inference_cat_disease import CatDiseasePredictor

            logger.info("CatDiseasePredictor başarıyla içe aktarıldı.")
            self.progress_update.emit(40)

            logger.info("CatDiseasePredictor örnekleniyor...")
            predictor = CatDiseasePredictor()
            logger.info("CatDiseasePredictor başarıyla örneklendi.")
            self.progress_update.emit(70)

            # Girdi değerlerini güvenli biçimde ayrıştır
            age      = float(self.patient_data.get('age', 0) or 0)
            weight   = float(self.patient_data.get('weight', 0) or 0)
            hr       = float(self.patient_data.get('hr', 0) or 0)
            temp     = float(self.patient_data.get('temp', 0) or 0)
            duration = float(self.patient_data.get('duration', 0) or 0)

            # symptom_indices: List[int] — 1-tabanlı indeksler
            symptom_indices = self.patient_data.get('symptom_indices', [])

            probs_and_diseases = predictor.predict(age, weight, hr, temp, duration, symptom_indices)
            self.progress_update.emit(90)

            # Seçilen semptomları ismiyle göster
            selected_names = [SYMPTOM_LIST[i - 1] for i in symptom_indices if 1 <= i <= len(SYMPTOM_LIST)]
            selected_text  = ", ".join(selected_names) if selected_names else "—"

            # Sonuçları formatla
            result_lines = [
                "🔍  Teşhis Sonuçları (İlk 3)",
                "─" * 40,
                f"📋  Seçilen Semptomlar ({len(symptom_indices)}): {selected_text}",
                "─" * 40,
            ]
            for rank, (disease, prob) in enumerate(probs_and_diseases, 1):
                bar = "█" * int(prob * 30)
                result_lines.append(f"{rank}. {disease:35s} %{prob * 100:.1f}  {bar}")

            result_str = "\n".join(result_lines)
            logger.info("Çıkarım tamamlandı ve biçimlendirildi.")

        except Exception as e:
            logger.error(f"Çıkarım sırasında hata: {str(e)}", exc_info=True)
            result_str = f"❌ Hata oluştu: {str(e)}"

        logger.info("progress_update sinyaline 100 gönderiliyor.")
        self.progress_update.emit(100)
        self.inference_finished.emit(result_str)


class CatDiseaseTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(_sv(20), _sv(20), _sv(20), _sv(20))
        layout.setSpacing(_sv(15))

        # Başlık
        title_label = QLabel("Kedi Hastalık Tahminleme Modülü (XGBoost ONNX)")
        title_label.setStyleSheet(_ss(f"font-size: 14pt; font-weight: bold; color: #6366f1;"))
        layout.addWidget(title_label)

        # Ana yatay düzen: sol = klinik girdiler, sağ = semptom listesi
        main_row = QHBoxLayout()
        main_row.setSpacing(_sv(15))

        # ── Sol: Klinik Girdiler ──────────────────────────────────────────
        input_group = QGroupBox("🐾 Klinik Girdiler")
        form_layout = QFormLayout(input_group)

        self.age_input = QLineEdit()
        self.age_input.setPlaceholderText("Örn: 2")
        self.weight_input = QLineEdit()
        self.weight_input.setPlaceholderText("Örn: 3.5 (kg)")
        self.hr_input = QLineEdit()
        self.hr_input.setPlaceholderText("Örn: 150 (nabız/dak)")
        self.temp_input = QLineEdit()
        self.temp_input.setPlaceholderText("Örn: 39.5 (°C)")
        self.duration_input = QLineEdit()
        self.duration_input.setPlaceholderText("Örn: 5 (gün)")

        form_layout.addRow("Yaş (Ay/Yıl):", self.age_input)
        form_layout.addRow("Kilo (kg):", self.weight_input)
        form_layout.addRow("Kalp Atış Hızı:", self.hr_input)
        form_layout.addRow("Vücut Sıcaklığı (°C):", self.temp_input)
        form_layout.addRow("Semptom Süresi (Gün):", self.duration_input)

        main_row.addWidget(input_group, stretch=1)

        # ── Sağ: Semptom Seçimi (Kaydırılabilir + Onay Kutusu) ───────────
        symptom_group = QGroupBox(f"🩺 Semptomlar (min {MIN_SYMPTOMS} — maks {MAX_SYMPTOMS})")
        symptom_layout = QVBoxLayout(symptom_group)
        symptom_layout.setSpacing(_sv(6))

        # Minimum uyarısı
        self.symptom_warning = QLabel(f"⚠️  En az {MIN_SYMPTOMS} semptom seçiniz.")
        self.symptom_warning.setStyleSheet(_ss(f"color: #f59e0b; font-size: 8pt;"))
        self.symptom_warning.setVisible(False)
        symptom_layout.addWidget(self.symptom_warning)

        # Maksimum uyarısı
        self.symptom_max_warning = QLabel(f"🚫  Maksimum {MAX_SYMPTOMS} semptoma ulaşıldı.")
        self.symptom_max_warning.setStyleSheet(_ss(f"color: #ef4444; font-size: 8pt;"))
        self.symptom_max_warning.setVisible(False)
        symptom_layout.addWidget(self.symptom_max_warning)

        # Seçim sayacı
        self.symptom_counter = QLabel(f"Seçili: 0 / {MAX_SYMPTOMS} semptom")
        self.symptom_counter.setStyleSheet(_ss(f"color: #94a3b8; font-size: 8pt;"))
        symptom_layout.addWidget(self.symptom_counter)

        # QListWidget — onay kutulu, kaydırılabilir, çoklu seçim
        self.symptom_list = QListWidget()
        self.symptom_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.symptom_list.setStyleSheet(_ss(f"""
            QListWidget {{
                background-color: rgba(0, 0, 0, 80);
                border: 1px solid #6366f1;
                border-radius: 5px;
                color: white;
                font-size: 10pt;
            }}
            QListWidget::item {{
                padding: 4px 8px;
            }}
            QListWidget::item:hover {{
                background-color: rgba(99, 102, 241, 0.25);
            }}
        """))

        for idx, name in enumerate(SYMPTOM_LIST, start=1):
            item = QListWidgetItem(f"  {idx:2d}. {name}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            # 1-tabanlı indeksi UserRole'da sakla
            item.setData(Qt.ItemDataRole.UserRole, idx)
            self.symptom_list.addItem(item)

        self.symptom_list.itemChanged.connect(self._on_symptom_changed)
        symptom_layout.addWidget(self.symptom_list)

        # Tümünü seç / temizle butonları
        sym_btn_row = QHBoxLayout()
        btn_select_all = QPushButton("Tümünü Seç")
        btn_select_all.setStyleSheet(_ss(f"padding: 4px; font-size: 8pt; background-color: #334155; color: white; border-radius: 4px;"))
        btn_select_all.clicked.connect(self._select_all_symptoms)

        btn_clear_all = QPushButton("Temizle")
        btn_clear_all.setStyleSheet(_ss(f"padding: 4px; font-size: 8pt; background-color: #334155; color: white; border-radius: 4px;"))
        btn_clear_all.clicked.connect(self._clear_all_symptoms)

        sym_btn_row.addWidget(btn_select_all)
        sym_btn_row.addWidget(btn_clear_all)
        symptom_layout.addLayout(sym_btn_row)

        main_row.addWidget(symptom_group, stretch=1)
        layout.addLayout(main_row)

        # Analiz butonu
        self.btn_predict = QPushButton("🔍  Hastalık Analizi Başlat")
        self.btn_predict.setStyleSheet(_ss(
            f"padding: 10px; background-color: #6366f1; color: white; "
            f"border-radius: 5px; font-weight: bold; font-size: 11pt;"
        ))
        self.btn_predict.clicked.connect(self.start_inference)
        layout.addWidget(self.btn_predict)

        # İlerleme çubuğu
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Sonuç alanı
        self.result_area = QTextEdit()
        self.result_area.setReadOnly(True)
        self.result_area.setPlaceholderText("Yapay Zeka tahmin sonuçları burada görüntülenecek...")
        self.result_area.setStyleSheet(_ss(
            f"font-size: 11pt; background-color: rgba(0, 0, 0, 100); color: white; "
            f"border: 1px solid #6366f1; border-radius: 5px; padding: 10px;"
        ))
        layout.addWidget(self.result_area)

        apply_responsive_widget_scaling(self)

    # ──────────────────────────────────────────────────────────────────────
    # Semptom yardımcı metodları
    # ──────────────────────────────────────────────────────────────────────

    def _on_symptom_changed(self, item):
        """Onay kutusu değiştiğinde sayacı ve uyarıları güncelle; maksimumu uygula."""
        count = self._checked_symptom_count()

        # Maksimum aşıldıysa son işaretlenen öğeyi geri al
        if item is not None and item.checkState() == Qt.CheckState.Checked and count > MAX_SYMPTOMS:
            self.symptom_list.blockSignals(True)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.symptom_list.blockSignals(False)
            count = MAX_SYMPTOMS

        self.symptom_counter.setText(f"Seçili: {count} / {MAX_SYMPTOMS} semptom")
        self.symptom_warning.setVisible(0 < count < MIN_SYMPTOMS)
        self.symptom_max_warning.setVisible(count >= MAX_SYMPTOMS)

    def _checked_symptom_count(self):
        count = 0
        for i in range(self.symptom_list.count()):
            if self.symptom_list.item(i).checkState() == Qt.CheckState.Checked:
                count += 1
        return count

    def _get_selected_symptom_indices(self):
        """Seçili semptomların 1-tabanlı indekslerini döndür."""
        indices = []
        for i in range(self.symptom_list.count()):
            item = self.symptom_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                indices.append(item.data(Qt.ItemDataRole.UserRole))
        return indices

    def _select_all_symptoms(self):
        self.symptom_list.blockSignals(True)
        for i in range(self.symptom_list.count()):
            self.symptom_list.item(i).setCheckState(Qt.CheckState.Checked)
        self.symptom_list.blockSignals(False)
        self._on_symptom_changed(None)

    def _clear_all_symptoms(self):
        self.symptom_list.blockSignals(True)
        for i in range(self.symptom_list.count()):
            self.symptom_list.item(i).setCheckState(Qt.CheckState.Unchecked)
        self.symptom_list.blockSignals(False)
        self._on_symptom_changed(None)

    # ──────────────────────────────────────────────────────────────────────
    # Çıkarım (Inference)
    # ──────────────────────────────────────────────────────────────────────

    def start_inference(self):
        symptom_indices = self._get_selected_symptom_indices()

        if len(symptom_indices) < MIN_SYMPTOMS:
            self.result_area.setText(
                f"⚠️  Lütfen en az {MIN_SYMPTOMS} semptom seçiniz.\n"
                f"Şu anda {len(symptom_indices)} semptom seçili."
            )
            return

        self.btn_predict.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.result_area.clear()

        patient_data = {
            "age":             self.age_input.text(),
            "weight":          self.weight_input.text(),
            "hr":              self.hr_input.text(),
            "temp":            self.temp_input.text(),
            "duration":        self.duration_input.text(),
            "symptom_indices": symptom_indices,   # List[int], 1-tabanlı
        }

        self.inference_thread = DiseaseInferenceThread(patient_data)
        self.inference_thread.progress_update.connect(self.progress_bar.setValue)
        self.inference_thread.inference_finished.connect(self.on_inference_finished)
        self.inference_thread.start()

    def on_inference_finished(self, result):
        self.result_area.setText(result.replace("\\n", "\n"))
        self.btn_predict.setEnabled(True)
        self.progress_bar.setVisible(False)