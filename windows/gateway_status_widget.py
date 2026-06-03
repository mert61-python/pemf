"""
Gateway Status Widget — LattePanda Gateway Durum Paneli

PEMF GUI'nin sol kenar çubuğunda gösterilir.
Hotspot, Mosquitto broker, internet ve bridge durumlarını gösterir.
"""

import logging
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PyQt6.QtCore import pyqtSlot, Qt
from PyQt6.QtGui import QFont


logger = logging.getLogger(__name__)


class GatewayStatusWidget(QWidget):
    """
    Gateway durum gösterge paneli.
    
    Gösterir:
    - Hotspot durumu (SSID + bağlı cihaz sayısı)
    - MQTT Broker durumu (Mosquitto çalışıyor mu)
    - Internet bağlantısı
    - Cloud Bridge durumu (HiveMQ bağlı mı)
    - Gateway modu (Online/Offline)
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        
        # Default durumlar
        self._hotspot_active = False
        self._broker_running = False
        self._internet_connected = False
        self._bridge_connected = False
        self._gateway_mode = "unknown"
        self._hotspot_clients = 0
    
    def _setup_ui(self):
        """UI bileşenlerini oluştur"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        
        # Başlık
        title = QLabel("🌐 Gateway Durumu")
        title.setStyleSheet("color: #6cffb0; font-size: 11pt; font-weight: bold; margin-bottom: 4px;")
        layout.addWidget(title)
        
        # Container
        container = QWidget()
        container.setStyleSheet("""
            background: rgba(61, 32, 107, 0.4);
            border: 1px solid #6c2b8f;
            border-radius: 8px;
            padding: 8px;
        """)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(8, 6, 8, 6)
        container_layout.setSpacing(3)
        
        # Durum satırları
        self._hotspot_label = self._create_status_row("WiFi Hotspot", "⏳", container_layout)
        self._broker_label = self._create_status_row("MQTT Broker", "⏳", container_layout)
        self._internet_label = self._create_status_row("Internet", "⏳", container_layout)
        self._bridge_label = self._create_status_row("Cloud Bridge", "⏳", container_layout)
        
        # Mod satırı
        self._mode_label = QLabel("Mod: Başlatılıyor...")
        self._mode_label.setStyleSheet("color: #aaa; font-size: 8pt; margin-top: 4px;")
        container_layout.addWidget(self._mode_label)
        
        layout.addWidget(container)
    
    def _create_status_row(self, name: str, initial_status: str, parent_layout) -> QLabel:
        """Tek bir durum satırı oluştur"""
        row = QHBoxLayout()
        row.setSpacing(6)
        
        name_label = QLabel(name)
        name_label.setStyleSheet("color: #ccc; font-size: 8pt;")
        name_label.setFixedWidth(90)
        
        status_label = QLabel(initial_status)
        status_label.setStyleSheet("color: #aaa; font-size: 8pt;")
        status_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        
        row.addWidget(name_label)
        row.addStretch()
        row.addWidget(status_label)
        
        parent_layout.addLayout(row)
        return status_label
    
    @pyqtSlot(dict)
    def update_network_status(self, status: dict):
        """NetworkMonitor'dan gelen durum güncellemesi"""
        self._hotspot_active = status.get("hotspot_active", False)
        self._internet_connected = status.get("internet_connected", False)
        self._gateway_mode = status.get("gateway_mode", "unknown")
        self._hotspot_clients = status.get("hotspot_clients", 0)
        # NOT: _bridge_connected burada güncellenmez.
        # Bridge durumu MosquittoManager.bridge_status_changed sinyalinden gelir.
        # NetworkMonitor bu bilgiye sahip değildir.
        
        self._refresh_ui()
    
    @pyqtSlot(object)
    def update_broker_status(self, status):
        """MosquittoManager'dan gelen durum güncellemesi.

        'running=False' olsa bile Mosquitto Windows servisi yerine process olarak
        başlatılmış olabilir. Bu durumda port_open veya local_connected True ise
        broker fiilen çalışıyor demektir — bunu da 'Çalışıyor' olarak göster.
        """
        if isinstance(status, dict):
            service_running = status.get("running", False)
            port_open       = status.get("port_open", False)
            local_connected = status.get("local_connected", False)
            # Servis olarak değil process olarak çalışıyor olabilir;
            # porta açıksa veya yerel bağlantı varsa broker ayaktadır.
            self._broker_running   = service_running or port_open or local_connected
            self._broker_as_service = service_running  # detay için sakla
        elif isinstance(status, bool):
            self._broker_running    = status
            self._broker_as_service = status
        else:
            self._broker_running    = False
            self._broker_as_service = False
        self._refresh_ui()
    
    @pyqtSlot(bool)
    def update_bridge_status(self, connected: bool):
        """Bridge bağlantı durumu güncellemesi"""
        self._bridge_connected = connected
        self._refresh_ui()
    
    def _refresh_ui(self):
        """Tüm UI elemanlarını güncelle"""
        # Hotspot
        if self._hotspot_active:
            clients_text = f" ({self._hotspot_clients} cihaz)" if self._hotspot_clients > 0 else ""
            self._hotspot_label.setText(f"✅ Aktif{clients_text}")
            self._hotspot_label.setStyleSheet("color: #6cffb0; font-size: 8pt;")
        else:
            self._hotspot_label.setText("❌ Kapalı")
            self._hotspot_label.setStyleSheet("color: #ff6b6b; font-size: 8pt;")
        
        # Broker
        if self._broker_running:
            # Servis olarak mı yoksa process olarak mı çalıştığını göster
            svc_text = "✅ Çalışıyor" if getattr(self, "_broker_as_service", True) else "✅ Aktif (Process)"
            self._broker_label.setText(svc_text)
            self._broker_label.setStyleSheet("color: #6cffb0; font-size: 8pt;")
        else:
            self._broker_label.setText("❌ Durdu")
            self._broker_label.setStyleSheet("color: #ff6b6b; font-size: 8pt;")
        
        # Internet
        if self._internet_connected:
            self._internet_label.setText("✅ Bağlı")
            self._internet_label.setStyleSheet("color: #6cffb0; font-size: 8pt;")
        else:
            self._internet_label.setText("⚠️ Offline")
            self._internet_label.setStyleSheet("color: #ffa500; font-size: 8pt;")
        
        # Bridge
        if self._bridge_connected:
            self._bridge_label.setText("✅ Senkron")
            self._bridge_label.setStyleSheet("color: #6cffb0; font-size: 8pt;")
        elif self._internet_connected:
            self._bridge_label.setText("⏳ Bağlanıyor")
            self._bridge_label.setStyleSheet("color: #ffa500; font-size: 8pt;")
        else:
            self._bridge_label.setText("⏸️ Offline")
            self._bridge_label.setStyleSheet("color: #888; font-size: 8pt;")
        
        # Mod
        mode_map = {
            "online": ("🟢 Online Gateway", "#6cffb0"),
            "offline": ("🟡 Offline Gateway", "#ffa500"),
            "hybrid": ("🔵 Cloud Only", "#4da6ff"),
            "disconnected": ("🔴 Bağlantı Yok", "#ff6b6b"),
            "unknown": ("⏳ Kontrol Ediliyor...", "#aaa"),
        }
        text, color = mode_map.get(self._gateway_mode, ("❓ Bilinmiyor", "#aaa"))
        self._mode_label.setText(f"Mod: {text}")
        self._mode_label.setStyleSheet(f"color: {color}; font-size: 8pt; margin-top: 4px; font-weight: bold;")