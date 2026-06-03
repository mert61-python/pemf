import os
import sys
import threading
import logging
from queue import Queue, Empty
from PyQt6.QtCore import QObject, pyqtSignal, QSettings
from pathlib import Path

# Imports requested by user
from database.patient_database import get_patient_database
from database.session_manager import get_session_manager
from services.mosquitto_manager import MosquittoManager
from services.network_monitor import NetworkMonitor
from threads.discovery_service_thread import DiscoveryServiceThread

class HeadlessCore(QObject):
    # Signals required by the STM32 worker or related mechanics
    stm_connected_signal = pyqtSignal(bool)

    def __init__(self, app_data_dir: str):
        super().__init__()
        
        self.logger = logging.getLogger(self.__class__.__name__)
        self.app_data_dir = Path(app_data_dir)
        
        # 1. Initialize databases
        self.patient_db = get_patient_database(self.app_data_dir)
        self.session_manager = get_session_manager(self.app_data_dir)
        
        # 2. Services
        try:
            self.mosquitto_manager = MosquittoManager()
            self.mosquitto_manager.start_monitoring()
            self.mosquitto_manager.ensure_running()
            self.mosquitto_manager.start_bridge()
            self.logger.info("MosquittoManager ve MQTT Bridge başarıyla başlatıldı.")
        except Exception as e:
            self.logger.error(f"MosquittoManager başlatılamadı: {e}")

        try:
            self.network_monitor = NetworkMonitor()
            self.network_monitor.start_monitoring()
            self.logger.info("NetworkMonitor başlatıldı.")
        except Exception as e:
            self.logger.error(f"NetworkMonitor başlatılamadı: {e}")

        try:
            self.discovery_thread = DiscoveryServiceThread(logger=self.logger)
            self.discovery_thread.start()
            self.logger.info("DiscoveryServiceThread başlatıldı.")
        except Exception as e:
            self.logger.error(f"DiscoveryServiceThread başlatılamadı: {e}")

        # 3. STM32 worker thread exactly as seen in the snippet
        self.stm_is_connected = False
        self.stm_connected_signal.connect(self._on_stm_connected_slot)
        
        self._hw_send_queue = Queue(maxsize=4)
        self._hw_sender_stop = threading.Event()
        
        def _hw_sender_worker():
            """STM32 serial ve UDP gönderimlerini ana thread'den bağımsız çalıştırır."""
            _serial = None
            _udp_sock = None
            _stm_ready_emitted = [False]  # closure için mutable
            
            # Serial port aç
            try:
                import serial as _serial_lib
                import serial.tools.list_ports as _list_ports
                _settings = QSettings("Mertacor", "PEMF_GUI")
                port_name = _settings.value("stm32_com_port", "AUTO", type=str)
                if port_name in ("AUTO", "COM10"):
                    detected_port = None
                    ports = list(_list_ports.comports())
                    for p in ports:
                        desc = p.description.lower()
                        hwid = p.hwid.lower()
                        if "ch340" in desc or "stlink" in desc or "stm32" in desc \
                                or "vid:pid=0483" in hwid or "vid:pid=1a86" in hwid:
                            detected_port = p.device
                            break
                    if not detected_port:
                        for p in ports:
                            if "usb" in p.hwid.lower() or "serial" in p.description.lower():
                                detected_port = p.device
                                break
                    if detected_port:
                        port_name = detected_port
                        _settings.setValue("stm32_com_port", port_name)
                        self.logger.info(f"🔍 [STM32 OTO-TANIMA] {port_name}")
                    else:
                        port_name = "COM10"

                _serial = _serial_lib.Serial(
                    port_name, 115200, timeout=1, dsrdtr=False, rtscts=False
                )
                self.logger.info(f"🚀 [STM32] {port_name} portu açıldı")

                def _reader():
                    while _serial and _serial.is_open and not self._hw_sender_stop.is_set():
                        try:
                            line = _serial.readline()
                            if line:
                                decoded = line.decode('utf-8', errors='ignore').strip()
                                if decoded:
                                    self.logger.info(f"✅ [STM32] {decoded}")
                                    # STM_READY mesajı ilk kez geldiğinde sinyal emit et
                                    if "STM_READY" in decoded and not _stm_ready_emitted[0]:
                                        _stm_ready_emitted[0] = True
                                        self.stm_connected_signal.emit(True)
                        except Exception as _e:
                            self.logger.warning(f"⚠️ [STM32 READER] {_e}")
                            break

                threading.Thread(target=_reader, daemon=True, name="STM32Reader").start()

            except Exception as e:
                self.logger.warning(f"❌ [STM32] Serial açılamadı: {e}")
                _serial = None

            # UDP soketi aç
            try:
                import socket as _socket_lib
                _udp_sock = _socket_lib.socket(_socket_lib.AF_INET, _socket_lib.SOCK_DGRAM)
                _udp_sock.setsockopt(_socket_lib.SOL_SOCKET, _socket_lib.SO_BROADCAST, 1)
            except Exception as e:
                self.logger.warning(f"❌ [UDP] Soket açılamadı: {e}")
                _udp_sock = None

            # Ana gönderim döngüsü
            while not self._hw_sender_stop.is_set():
                try:
                    payload_tuple = self._hw_send_queue.get(timeout=0.5)
                except Empty:
                    continue
                stm_msg, udp_pkt, esp_ip, esp_port = payload_tuple
                if _serial and _serial.is_open and stm_msg:
                    try:
                        _serial.write(stm_msg.encode('utf-8'))
                    except Exception as e:
                        self.logger.warning(f"❌ [STM32 SEND] {e}")
                if _udp_sock and udp_pkt:
                    try:
                        _udp_sock.sendto(udp_pkt, (esp_ip, esp_port))
                    except Exception as e:
                        self.logger.warning(f"❌ [UDP SEND] {e}")

            # Temizlik
            if _serial and _serial.is_open:
                try: _serial.close()
                except: pass
            if _udp_sock:
                try: _udp_sock.close()
                except: pass

        self._hw_sender_thread = threading.Thread(
            target=_hw_sender_worker, daemon=True, name="HWSender"
        )
        self._hw_sender_thread.start()

    def _on_stm_connected_slot(self, is_connected: bool):
        self.stm_is_connected = is_connected
        self.logger.info(f"STM32 bağlantı durumu güncellendi: {self.stm_is_connected}")

    def quit(self):
        """Clean up threads and services upon exit."""
        self._hw_sender_stop.set()
        if self._hw_sender_thread.is_alive():
            self._hw_sender_thread.join(timeout=2.0)
            
        if hasattr(self, 'discovery_thread') and self.discovery_thread.isRunning():
            self.discovery_thread.stop()
            self.discovery_thread.wait()
