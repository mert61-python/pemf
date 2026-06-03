"""
BLE Provision Dialog — ESP32 Cihaz Yapılandırma Penceresi

LattePanda GUI'den ESP32-S3 cihazlarını BLE üzerinden yapılandırır:
- BLE tarama ile PEMF cihazlarını bul
- WiFi SSID/Pass gönder (varsayılan: PEMF-Gateway hotspot)
- MQTT broker bilgisi gönder (varsayılan: 192.168.137.1:1883)
"""

import logging
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QListWidget, QListWidgetItem,
    QProgressBar, QGroupBox, QFormLayout, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QFont

from services.ble_provisioner import BLEProvisionerThread

logger = logging.getLogger(__name__)


class BLEProvisionDialog(QDialog):
    """
    BLE üzerinden ESP32 cihazları yapılandırma dialog penceresi.
    Mevcut BLEProvisionerThread backend'ini kullanır.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔗 Yeni Cihaz Ekle")
        self.setMinimumSize(520, 620)
        self.setModal(True)

        # BLE Thread
        self._ble_thread = BLEProvisionerThread(self)
        self._found_devices: list[tuple[str, str]] = []  # (address, name)

        self._setup_ui()
        self._connect_signals()
        self._apply_styles()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # === Başlık ===
        title = QLabel("📡 Yeni Cihaz Eşleştirme Sistemi")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        desc = QLabel(
            "Çevredeki kurulum bekleyen yeni bobinleri (cihazları) bulun\n"
            "ve otomatik olarak sisteme bağlayın."
        )
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet("color: #aaa; margin-bottom: 8px;")
        layout.addWidget(desc)

        # === Tarama Bölümü ===
        scan_group = QGroupBox("🔍 Yeni Cihaz Arama")
        scan_layout = QVBoxLayout(scan_group)

        self._scan_btn = QPushButton("🔎 Çevredeki Cihazları Ara")
        self._scan_btn.setFixedHeight(40)
        self._scan_btn.clicked.connect(self._on_scan_clicked)
        scan_layout.addWidget(self._scan_btn)

        self._device_list = QListWidget()
        self._device_list.setMinimumHeight(120)
        self._device_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        scan_layout.addWidget(self._device_list)

        self._scan_status = QLabel("Henüz arama yapılmadı.")
        self._scan_status.setStyleSheet("color: #888; font-size: 9pt;")
        scan_layout.addWidget(self._scan_status)

        layout.addWidget(scan_group)

        # === WiFi Ayarları ===
        wifi_group = QGroupBox("📶 Ağ (Wi-Fi) Bağlantı Ayarları")
        wifi_form = QFormLayout(wifi_group)

        self._ssid_input = QLineEdit("PEMF-Gateway")
        self._pass_input = QLineEdit("pemf1234")
        self._pass_input.setEchoMode(QLineEdit.EchoMode.Password)

        wifi_form.addRow("Ağ Adı:", self._ssid_input)
        wifi_form.addRow("Şifre:", self._pass_input)
        layout.addWidget(wifi_group)

        # === MQTT Ayarları ===
        mqtt_group = QGroupBox("🌐 Sistem İletişim Ayarları (Lütfen değiştirmeyin)")
        mqtt_form = QFormLayout(mqtt_group)

        self._mqtt_host_input = QLineEdit("192.168.137.1")
        self._mqtt_port_input = QLineEdit("1883")

        mqtt_form.addRow("Merkez IP:", self._mqtt_host_input)
        mqtt_form.addRow("Port:", self._mqtt_port_input)
        layout.addWidget(mqtt_group)

        # === İlerleme ===
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._progress.setTextVisible(True)
        layout.addWidget(self._progress)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #6cffb0; font-size: 9pt;")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        # === Butonlar ===
        btn_layout = QHBoxLayout()

        self._provision_btn = QPushButton("⚡ Cihazı Kur ve Sisteme Ekle")
        self._provision_btn.setFixedHeight(44)
        self._provision_btn.setEnabled(False)
        self._provision_btn.clicked.connect(self._on_provision_clicked)

        self._close_btn = QPushButton("Kapat")
        self._close_btn.setFixedHeight(44)
        self._close_btn.clicked.connect(self.close)

        btn_layout.addWidget(self._provision_btn)
        btn_layout.addWidget(self._close_btn)
        layout.addLayout(btn_layout)

    def _connect_signals(self):
        """BLE Thread sinyallerini bağla."""
        self._ble_thread.scan_started.connect(self._on_scan_started)
        self._ble_thread.scan_finished.connect(self._on_scan_finished)
        self._ble_thread.device_found.connect(self._on_device_found)
        self._ble_thread.provision_started.connect(self._on_provision_started)
        self._ble_thread.provision_progress.connect(self._on_provision_progress)
        self._ble_thread.provision_success.connect(self._on_provision_success)
        self._ble_thread.provision_failed.connect(self._on_provision_failed)
        self._ble_thread.all_done.connect(self._on_all_done)
        self._ble_thread.error_occurred.connect(self._on_error)

    def _apply_styles(self):
        """Dialog stilini uygula."""
        self.setStyleSheet("""
            QDialog {
                background: #1e1e2e;
                color: #fff;
            }
            QGroupBox {
                background: rgba(61, 32, 107, 0.3);
                border: 1px solid #6c2b8f;
                border-radius: 10px;
                margin-top: 10px;
                padding-top: 16px;
                font-weight: bold;
                color: #6cffb0;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
            }
            QLineEdit {
                background: #3d206b;
                color: #fff;
                border: 1px solid #6c2b8f;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 10pt;
            }
            QLineEdit:focus {
                border: 1px solid #6cffb0;
            }
            QListWidget {
                background: #2a1a4e;
                color: #fff;
                border: 1px solid #6c2b8f;
                border-radius: 6px;
                font-size: 10pt;
            }
            QListWidget::item {
                padding: 6px;
                border-bottom: 1px solid #3d206b;
            }
            QListWidget::item:selected {
                background: rgba(108, 255, 176, 0.2);
                color: #6cffb0;
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #7c3aed, stop:1 #6c2b8f);
                color: #fff;
                border: none;
                border-radius: 10px;
                font-size: 11pt;
                font-weight: bold;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #8b5cf6, stop:1 #7c3aed);
            }
            QPushButton:disabled {
                background: #444;
                color: #888;
            }
            QProgressBar {
                border: 1px solid #6c2b8f;
                border-radius: 6px;
                text-align: center;
                color: #fff;
                background: #2a1a4e;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7c3aed, stop:1 #6cffb0);
                border-radius: 5px;
            }
            QLabel {
                color: #ddd;
            }
        """)

    # ─── Tarama ─────────────────────────────────────────────

    def _on_scan_clicked(self):
        """BLE tarama başlat."""
        if self._ble_thread.isRunning():
            self._status_label.setText("⏳ Zaten bir işlem çalışıyor...")
            return

        self._device_list.clear()
        self._found_devices.clear()
        self._provision_btn.setEnabled(False)
        self._ble_thread.start_scan()

    @pyqtSlot()
    def _on_scan_started(self):
        self._scan_btn.setEnabled(False)
        self._scan_btn.setText("⏳ Aranıyor...")
        self._scan_status.setText("Çevredeki cihazlar aranıyor...")

    @pyqtSlot()
    def _on_scan_finished(self):
        self._scan_btn.setEnabled(True)
        self._scan_btn.setText("🔎 Çevredeki Cihazları Ara")
        count = len(self._found_devices)
        self._scan_status.setText(f"✅ Arama tamamlandı: {count} yeni cihaz bulundu")
        
        if count > 0:
            self._provision_btn.setEnabled(True)
            # Tüm cihazları seç
            for i in range(self._device_list.count()):
                self._device_list.item(i).setSelected(True)

    @pyqtSlot(str, str)
    def _on_device_found(self, address: str, name: str):
        # Mükerrer (çift) cihaz eklemeyi engelle
        for existing_address, _ in self._found_devices:
            if existing_address == address:
                return

        self._found_devices.append((address, name))
        item = QListWidgetItem(f"📱 {name}  —  {address}")
        item.setData(Qt.ItemDataRole.UserRole, address)
        self._device_list.addItem(item)

    # ─── Provisioning ──────────────────────────────────────

    def _on_provision_clicked(self):
        """Seçili cihazlara WiFi + MQTT config gönder."""
        if self._ble_thread.isRunning():
            self._status_label.setText("⏳ Zaten bir işlem çalışıyor...")
            return

        # Seçili cihazları al
        selected_items = self._device_list.selectedItems()
        if not selected_items:
            self._status_label.setText("⚠️ Lütfen en az bir cihaz seçin.")
            return

        selected_addresses = [
            item.data(Qt.ItemDataRole.UserRole) for item in selected_items
        ]

        # WiFi config
        ssid = self._ssid_input.text().strip()
        password = self._pass_input.text().strip()
        if not ssid:
            self._status_label.setText("⚠️ Bağlanılacak ağ adı boş bırakılamaz.")
            return

        # MQTT config
        mqtt_host = self._mqtt_host_input.text().strip()
        try:
            mqtt_port = int(self._mqtt_port_input.text().strip())
        except ValueError:
            mqtt_port = 1883

        # Worker'ı yapılandır
        self._ble_thread.worker.set_wifi_config(ssid, password)
        self._ble_thread.worker.set_mqtt_config(mqtt_host, mqtt_port)
        self._ble_thread.worker.set_target_devices(selected_addresses)

        # İlerleme
        self._progress.setVisible(True)
        self._progress.setRange(0, len(selected_addresses))
        self._progress.setValue(0)
        self._provision_count = 0

        # Başlat
        self._scan_btn.setEnabled(False)
        self._provision_btn.setEnabled(False)
        self._ble_thread.start_provision()

    @pyqtSlot(str)
    def _on_provision_started(self, address: str):
        self._status_label.setText(f"⚡ Eşleştiriliyor: {address}")

    @pyqtSlot(str, str)
    def _on_provision_progress(self, address: str, step: str):
        self._status_label.setText(f"📡 {address}: {step}")

    @pyqtSlot(str)
    def _on_provision_success(self, address: str):
        self._provision_count = getattr(self, '_provision_count', 0) + 1
        self._progress.setValue(self._provision_count)
        self._status_label.setText(f"✅ {address} — Sisteme Eklendi!")
        logger.info(f"BLE Provision başarılı: {address}")

        # Başarılı olan cihazı listeden anında sil
        for i in range(self._device_list.count()):
            item = self._device_list.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == address:
                self._device_list.takeItem(i)
                break

    @pyqtSlot(str, str)
    def _on_provision_failed(self, address: str, error: str):
        self._provision_count = getattr(self, '_provision_count', 0) + 1
        self._progress.setValue(self._provision_count)
        self._status_label.setText(f"❌ {address} — Hata: {error}")
        logger.error(f"BLE Provision başarısız: {address} — {error}")

    @pyqtSlot(int, int)
    def _on_all_done(self, success: int, fail: int):
        self._scan_btn.setEnabled(True)
        self._provision_btn.setEnabled(True)
        self._progress.setVisible(False)
        
        if fail == 0 and success > 0:
            self._status_label.setText(
                f"🎉 Tamamlandı! {success} cihaz başarıyla sisteme bağlandı."
            )
            self._status_label.setStyleSheet("color: #6cffb0; font-size: 10pt; font-weight: bold;")
            
            # Başarılı pop-up mesajı
            QMessageBox.information(
                self, 
                "✅ Bağlantı Başarılı", 
                f"{success} adet yeni cihaz başarıyla klinik sistemine eklendi ve kullanıma hazır!"
            )
        elif success > 0 or fail > 0:
            self._status_label.setText(
                f"⚠️ Tamamlandı: {success} başarılı, {fail} başarısız."
            )
            self._status_label.setStyleSheet("color: #ffa500; font-size: 10pt; font-weight: bold;")

    @pyqtSlot(str)
    def _on_error(self, message: str):
        self._scan_btn.setEnabled(True)
        self._provision_btn.setEnabled(True)
        self._progress.setVisible(False)
        self._status_label.setText(f"❌ Hata: {message}")
        self._status_label.setStyleSheet("color: #ff6b6b; font-size: 10pt;")
        logger.error(f"BLE Provisioner hatası: {message}")
