# -*- coding: utf-8 -*-
"""
GUI EventBus Integration Example
PEMF Medical System GUI bileşenlerinin EventBus ile entegrasyonu

Bu modül, GUI bileşenlerinin EventBus kullanarak nasıl gevşek bağlılık
sağlayabileceğini gösterir.

@author: merta
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime
from PyQt6.QtCore import QObject, pyqtSignal, QTimer
from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QLabel, QPushButton

from event_bus import get_event_bus, EventTypes, EventPriority, Event
from websocket_server_refactored import WebSocketServerRefactored

logger = logging.getLogger(__name__)


class EventDrivenMainWindow(QMainWindow):
    """
    EventBus kullanan ana pencere
    
    Özellikler:
    - WebSocket server ile gevşek bağlılık
    - Event-driven communication
    - Daha temiz separation of concerns
    """
    
    def __init__(self):
        super().__init__()
        
        # EventBus instance
        self.event_bus = get_event_bus()
        
        # Components
        self.websocket_server = None
        self.esp_status_widgets = {}
        
        # UI setup
        self._setup_ui()
        
        # Event subscriptions
        self._setup_event_subscriptions()
        
        # Initialize components
        self._initialize_components()
    
    def _setup_ui(self):
        """UI bileşenlerini ayarla"""
        self.setWindowTitle("PEMF Medical System - Event Driven")
        self.setGeometry(100, 100, 800, 600)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout(central_widget)
        
        # Status label
        self.status_label = QLabel("System Status: Initializing...")
        layout.addWidget(self.status_label)
        
        # ESP status area
        self.esp_status_widget = QWidget()
        self.esp_status_layout = QVBoxLayout(self.esp_status_widget)
        layout.addWidget(self.esp_status_widget)
        
        # Control buttons
        self.start_button = QPushButton("Start System")
        self.start_button.clicked.connect(self._start_system)
        layout.addWidget(self.start_button)
        
        self.stop_button = QPushButton("Stop System")
        self.stop_button.clicked.connect(self._stop_system)
        self.stop_button.setEnabled(False)
        layout.addWidget(self.stop_button)
    
    def _setup_event_subscriptions(self):
        """Event subscriptions'ları ayarla"""
        
        # ESP connection events
        self.event_bus.subscribe(
            EventTypes.ESP_CONNECTED,
            self._handle_esp_connected,
            "main_window",
            priority=EventPriority.HIGH
        )
        
        self.event_bus.subscribe(
            EventTypes.ESP_DISCONNECTED,
            self._handle_esp_disconnected,
            "main_window",
            priority=EventPriority.HIGH
        )
        
        # ESP data events
        self.event_bus.subscribe(
            EventTypes.ESP_DATA_RECEIVED,
            self._handle_esp_data,
            "main_window"
        )
        
        # ESP heartbeat events
        self.event_bus.subscribe(
            EventTypes.ESP_HEARTBEAT,
            self._handle_esp_heartbeat,
            "main_window"
        )
        
        # ESP error events
        self.event_bus.subscribe(
            EventTypes.ESP_ERROR,
            self._handle_esp_error,
            "main_window",
            priority=EventPriority.HIGH
        )
        
        # System events
        self.event_bus.subscribe(
            EventTypes.SYSTEM_STARTUP,
            self._handle_system_startup,
            "main_window"
        )
        
        self.event_bus.subscribe(
            EventTypes.SYSTEM_SHUTDOWN,
            self._handle_system_shutdown,
            "main_window"
        )
    
    def _initialize_components(self):
        """Sistem bileşenlerini başlat"""
        # WebSocket server'ı oluştur (henüz başlatma)
        self.websocket_server = WebSocketServerRefactored()
        
        # System initialization event'i yayınla
        self.event_bus.publish(
            EventTypes.SYSTEM_STARTUP,
            {
                "component": "main_window",
                "timestamp": datetime.now().isoformat()
            },
            source="main_window"
        )
    
    def _start_system(self):
        """Sistemi başlat"""
        if self.websocket_server:
            # Async operation'ı thread'de çalıştır
            import asyncio
            import threading
            
            def start_server():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self.websocket_server.start())
            
            thread = threading.Thread(target=start_server, daemon=True)
            thread.start()
            
            # UI state'i güncelle
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(True)
            self.status_label.setText("System Status: Starting...")
            
            # System start event'i yayınla
            self.event_bus.publish(
                EventTypes.GUI_USER_ACTION,
                {
                    "action": "system_start",
                    "user": "operator",
                    "timestamp": datetime.now().isoformat()
                },
                source="main_window"
            )
    
    def _stop_system(self):
        """Sistemi durdur"""
        if self.websocket_server:
            # Async operation'ı thread'de çalıştır
            import asyncio
            import threading
            
            def stop_server():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self.websocket_server.stop())
            
            thread = threading.Thread(target=stop_server, daemon=True)
            thread.start()
            
            # UI state'i güncelle
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self.status_label.setText("System Status: Stopping...")
            
            # System stop event'i yayınla
            self.event_bus.publish(
                EventTypes.GUI_USER_ACTION,
                {
                    "action": "system_stop",
                    "user": "operator",
                    "timestamp": datetime.now().isoformat()
                },
                source="main_window"
            )
    
    # Event handlers
    def _handle_esp_connected(self, event: Event):
        """ESP bağlantı event'ini işle"""
        data = event.data
        coil_id = data["coil_id"]
        ip = data["ip"]
        
        # UI'da ESP status'unu göster
        if coil_id not in self.esp_status_widgets:
            status_label = QLabel(f"ESP {coil_id} ({ip}): Connected")
            status_label.setStyleSheet("color: green; font-weight: bold;")
            self.esp_status_widgets[coil_id] = status_label
            self.esp_status_layout.addWidget(status_label)
        else:
            self.esp_status_widgets[coil_id].setText(f"ESP {coil_id} ({ip}): Connected")
            self.esp_status_widgets[coil_id].setStyleSheet("color: green; font-weight: bold;")
        
        logger.info(f"GUI: ESP {coil_id} connected from {ip}")
    
    def _handle_esp_disconnected(self, event: Event):
        """ESP bağlantı kopma event'ini işle"""
        data = event.data
        coil_id = data["coil_id"]
        
        # UI'da ESP status'unu güncelle
        if coil_id in self.esp_status_widgets:
            self.esp_status_widgets[coil_id].setText(f"ESP {coil_id}: Disconnected")
            self.esp_status_widgets[coil_id].setStyleSheet("color: red; font-weight: bold;")
        
        logger.info(f"GUI: ESP {coil_id} disconnected")
    
    def _handle_esp_data(self, event: Event):
        """ESP veri event'ini işle"""
        data = event.data
        coil_id = data["coil_id"]
        
        # Sensor data ise
        if "sensor_data" in data:
            sensor_data = data["sensor_data"]
            
            # UI'da veri gösterimi (örnek)
            if coil_id in self.esp_status_widgets:
                temp = sensor_data.get("temperature", "N/A")
                humidity = sensor_data.get("humidity", "N/A")
                status_text = f"ESP {coil_id}: T={temp}°C, H={humidity}%"
                self.esp_status_widgets[coil_id].setText(status_text)
            
            # Data processing event'i yayınla
            self.event_bus.publish(
                EventTypes.DATA_SENSOR_UPDATE,
                {
                    "coil_id": coil_id,
                    "processed_data": sensor_data,
                    "processing_timestamp": datetime.now().isoformat()
                },
                source="main_window"
            )
    
    def _handle_esp_heartbeat(self, event: Event):
        """ESP heartbeat event'ini işle"""
        data = event.data
        coil_id = data["coil_id"]
        
        # UI'da heartbeat indicator'ı güncelle (örnek)
        if coil_id in self.esp_status_widgets:
            current_text = self.esp_status_widgets[coil_id].text()
            if "♥" not in current_text:
                self.esp_status_widgets[coil_id].setText(current_text + " ♥")
            
            # Heartbeat indicator'ı kısa süre sonra kaldır
            QTimer.singleShot(1000, lambda: self._remove_heartbeat_indicator(coil_id))
    
    def _remove_heartbeat_indicator(self, coil_id: str):
        """Heartbeat indicator'ını kaldır"""
        if coil_id in self.esp_status_widgets:
            current_text = self.esp_status_widgets[coil_id].text()
            new_text = current_text.replace(" ♥", "")
            self.esp_status_widgets[coil_id].setText(new_text)
    
    def _handle_esp_error(self, event: Event):
        """ESP error event'ini işle"""
        data = event.data
        coil_id = data["coil_id"]
        error_type = data["error_type"]
        
        # UI'da error gösterimi
        if coil_id in self.esp_status_widgets:
            self.esp_status_widgets[coil_id].setText(f"ESP {coil_id}: ERROR - {error_type}")
            self.esp_status_widgets[coil_id].setStyleSheet("color: red; font-weight: bold;")
        
        logger.error(f"GUI: ESP {coil_id} error - {error_type}")
    
    def _handle_system_startup(self, event: Event):
        """System startup event'ini işle"""
        data = event.data
        component = data.get("component", "unknown")
        
        if component == "websocket_server":
            self.status_label.setText("System Status: WebSocket Server Running")
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
    
    def _handle_system_shutdown(self, event: Event):
        """System shutdown event'ini işle"""
        data = event.data
        component = data.get("component", "unknown")
        
        if component == "websocket_server":
            self.status_label.setText("System Status: WebSocket Server Stopped")
            self.status_label.setStyleSheet("color: red; font-weight: bold;")
    
    def closeEvent(self, event):
        """Pencere kapatılırken cleanup"""
        # System shutdown event'i yayınla
        self.event_bus.publish(
            EventTypes.SYSTEM_SHUTDOWN,
            {
                "component": "main_window",
                "reason": "user_close"
            },
            source="main_window"
        )
        
        # WebSocket server'ı durdur
        if self.websocket_server:
            import asyncio
            import threading
            
            def stop_server():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self.websocket_server.stop())
            
            thread = threading.Thread(target=stop_server, daemon=True)
            thread.start()
            thread.join(timeout=5)  # 5 saniye bekle
        
        # Event subscriptions'ları temizle
        self.event_bus.unsubscribe(EventTypes.ESP_ALL, "main_window")
        self.event_bus.unsubscribe(EventTypes.SYSTEM_ALL, "main_window")
        self.event_bus.unsubscribe(EventTypes.GUI_ALL, "main_window")
        self.event_bus.unsubscribe(EventTypes.DATA_ALL, "main_window")
        
        super().closeEvent(event)


class PWMControlWidget(QWidget):
    """
    EventBus kullanan PWM kontrol widget'ı
    
    Bu widget, WebSocket server'a doğrudan bağlı değil,
    sadece event'ler üzerinden iletişim kurar.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # EventBus instance
        self.event_bus = get_event_bus()
        
        # UI setup
        self._setup_ui()
        
        # Event subscriptions
        self._setup_event_subscriptions()
    
    def _setup_ui(self):
        """UI bileşenlerini ayarla"""
        layout = QVBoxLayout(self)
        
        self.status_label = QLabel("PWM Control Ready")
        layout.addWidget(self.status_label)
        
        # PWM control buttons (örnek)
        self.start_pwm_button = QPushButton("Start PWM")
        self.start_pwm_button.clicked.connect(self._start_pwm)
        layout.addWidget(self.start_pwm_button)
        
        self.stop_pwm_button = QPushButton("Stop PWM")
        self.stop_pwm_button.clicked.connect(self._stop_pwm)
        layout.addWidget(self.stop_pwm_button)
    
    def _setup_event_subscriptions(self):
        """Event subscriptions'ları ayarla"""
        # ESP connection events (PWM sadece bağlı ESP'lere gönderilebilir)
        self.event_bus.subscribe(
            EventTypes.ESP_CONNECTED,
            self._handle_esp_connected,
            "pwm_control"
        )
        
        self.event_bus.subscribe(
            EventTypes.ESP_DISCONNECTED,
            self._handle_esp_disconnected,
            "pwm_control"
        )
    
    def _start_pwm(self):
        """PWM başlat komutu gönder"""
        # PWM command event'i yayınla
        self.event_bus.publish(
            EventTypes.DATA_PWM_UPDATE,
            {
                "action": "start",
                "frequency": 1000,
                "duty_cycle": 50,
                "target": "all_esps"  # veya belirli coil_id
            },
            source="pwm_control",
            priority=EventPriority.HIGH
        )
        
        self.status_label.setText("PWM Start command sent")
    
    def _stop_pwm(self):
        """PWM durdur komutu gönder"""
        # PWM command event'i yayınla
        self.event_bus.publish(
            EventTypes.DATA_PWM_UPDATE,
            {
                "action": "stop",
                "target": "all_esps"
            },
            source="pwm_control",
            priority=EventPriority.HIGH
        )
        
        self.status_label.setText("PWM Stop command sent")
    
    def _handle_esp_connected(self, event: Event):
        """ESP bağlantı event'ini işle"""
        data = event.data
        coil_id = data["coil_id"]
        
        # PWM control'ü aktifleştir
        self.start_pwm_button.setEnabled(True)
        self.stop_pwm_button.setEnabled(True)
        self.status_label.setText(f"PWM Control Ready - ESP {coil_id} connected")
    
    def _handle_esp_disconnected(self, event: Event):
        """ESP bağlantı kopma event'ini işle"""
        # Eğer hiç ESP bağlı değilse PWM control'ü deaktifleştir
        # (Bu kontrol daha karmaşık olabilir, tüm ESP'leri kontrol etmek gerekir)
        pass


class DataVisualizationWidget(QWidget):
    """
    EventBus kullanan veri görselleştirme widget'ı
    
    Bu widget sadece sensor data event'lerini dinler ve
    grafikleri günceller.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # EventBus instance
        self.event_bus = get_event_bus()
        
        # Data storage
        self.sensor_data_history = {}
        
        # UI setup
        self._setup_ui()
        
        # Event subscriptions
        self._setup_event_subscriptions()
    
    def _setup_ui(self):
        """UI bileşenlerini ayarla"""
        layout = QVBoxLayout(self)
        
        self.data_label = QLabel("Waiting for sensor data...")
        layout.addWidget(self.data_label)
        
        # Burada pyqtgraph veya matplotlib widget'ları olabilir
        # Örnek için sadece label kullanıyoruz
    
    def _setup_event_subscriptions(self):
        """Event subscriptions'ları ayarla"""
        # Sensor data events
        self.event_bus.subscribe(
            EventTypes.DATA_SENSOR_UPDATE,
            self._handle_sensor_data,
            "data_visualization"
        )
    
    def _handle_sensor_data(self, event: Event):
        """Sensor data event'ini işle"""
        data = event.data
        coil_id = data["coil_id"]
        sensor_data = data["processed_data"]
        
        # Veriyi history'ye ekle
        if coil_id not in self.sensor_data_history:
            self.sensor_data_history[coil_id] = []
        
        self.sensor_data_history[coil_id].append({
            "timestamp": datetime.now(),
            "data": sensor_data
        })
        
        # Son 100 veriyi tut
        if len(self.sensor_data_history[coil_id]) > 100:
            self.sensor_data_history[coil_id] = self.sensor_data_history[coil_id][-100:]
        
        # UI'ı güncelle
        temp = sensor_data.get("temperature", "N/A")
        humidity = sensor_data.get("humidity", "N/A")
        pressure = sensor_data.get("pressure", "N/A")
        
        self.data_label.setText(
            f"Latest Data - ESP {coil_id}:\n"
            f"Temperature: {temp}°C\n"
            f"Humidity: {humidity}%\n"
            f"Pressure: {pressure} hPa"
        )


# PWM Command Handler (WebSocket server ile entegrasyon için)
class PWMCommandHandler:
    """
    PWM command event'lerini dinleyip WebSocket server'a ileten handler
    
    Bu sınıf, GUI'den gelen PWM command'larını WebSocket server'a iletir.
    """
    
    def __init__(self, websocket_server: WebSocketServerRefactored):
        self.websocket_server = websocket_server
        self.event_bus = get_event_bus()
        
        # PWM command events'ini dinle
        self.event_bus.subscribe(
            EventTypes.DATA_PWM_UPDATE,
            self._handle_pwm_command,
            "pwm_command_handler",
            priority=EventPriority.HIGH
        )
    
    async def _handle_pwm_command(self, event: Event):
        """PWM command event'ini işle ve ESP'lere gönder"""
        data = event.data
        action = data.get("action")
        target = data.get("target", "all_esps")
        
        # PWM command'ını hazırla
        pwm_data = {
            "action": action,
            "frequency": data.get("frequency", 1000),
            "duty_cycle": data.get("duty_cycle", 0),
            "timestamp": datetime.now().isoformat()
        }
        
        if target == "all_esps":
            # Tüm ESP'lere gönder
            success_count = await self.websocket_server.broadcast_config_update(pwm_data)
            logger.info(f"PWM command sent to {success_count} ESPs")
        else:
            # Belirli ESP'ye gönder
            success = await self.websocket_server.send_pwm_command(target, pwm_data)
            if success:
                logger.info(f"PWM command sent to ESP {target}")
            else:
                logger.error(f"Failed to send PWM command to ESP {target}")


if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication
    
    # Logging setup
    logging.basicConfig(level=logging.INFO)
    
    app = QApplication(sys.argv)
    
    # Ana pencereyi oluştur
    main_window = EventDrivenMainWindow()
    main_window.show()
    
    sys.exit(app.exec())
