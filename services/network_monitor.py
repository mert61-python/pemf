"""
Network Monitor — Ağ Durumu İzleme Servisi

LattePanda gateway'inin ağ durumunu izler:
- Internet bağlantısı (Ethernet)
- WiFi Hotspot durumu  
- MQTT broker erişilebilirliği
- Bridge bağlantı durumu

Event bus üzerinden status güncellemelerini yayınlar.
"""

import socket
import subprocess
import logging
from typing import Dict, Optional
from PyQt6.QtCore import QObject, QTimer, QThread, pyqtSignal, pyqtSlot


logger = logging.getLogger(__name__)


class NetworkStatus:
    """Ağ durum bilgisi"""
    def __init__(self):
        self.internet_connected: bool = False
        self.hotspot_active: bool = False
        self.hotspot_ssid: str = ""
        self.hotspot_ip: str = "192.168.137.1"
        self.hotspot_clients: int = 0
        self.mqtt_broker_reachable: bool = False
        self.mqtt_bridge_connected: bool = False
        self.ethernet_ip: Optional[str] = None
        self.wifi_ip: Optional[str] = None
        self.gateway_mode: str = "unknown"  # "online", "offline", "hybrid"


class NetworkMonitorWorker(QObject):
    """Ağ kontrollerini arka planda çalıştıran worker."""

    status_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._busy = False

    def _check_internet(self) -> bool:
        for host, port in NetworkMonitor.INTERNET_CHECK_HOSTS:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                result = sock.connect_ex((host, port))
                sock.close()
                if result == 0:
                    return True
            except Exception:
                continue
        return False

    def _check_hotspot(self) -> Dict:
        hotspot_info = {
            "active": False,
            "ssid": "",
            "ip": "",
            "clients": 0
        }

        try:
            result = subprocess.run(
                ["powershell", "-Command",
                 "Get-NetIPAddress -AddressFamily IPv4 | "
                 "Where-Object { $_.IPAddress -like '192.168.137.*' } | "
                 "Select-Object -ExpandProperty IPAddress"],
                capture_output=True, text=True, timeout=5,
                encoding='cp857', errors='replace',
                creationflags=subprocess.CREATE_NO_WINDOW
            )

            if result.returncode == 0 and result.stdout.strip():
                hotspot_ip = result.stdout.strip().split("\n")[0].strip()
                hotspot_info["active"] = True
                hotspot_info["ip"] = hotspot_ip

                arp_result = subprocess.run(
                    ["arp", "-a"],
                    capture_output=True, text=True, timeout=5,
                    encoding='cp857', errors='replace',
                    creationflags=subprocess.CREATE_NO_WINDOW
                )

                if arp_result.returncode == 0:
                    clients = 0
                    for line in arp_result.stdout.split("\n"):
                        if NetworkMonitor.HOTSPOT_SUBNET in line and "dynamic" in line.lower():
                            clients += 1
                    hotspot_info["clients"] = clients

                try:
                    ssid_result = subprocess.run(
                        ["netsh", "wlan", "show", "hostednetwork"],
                        capture_output=True, text=True, timeout=5,
                        encoding='cp857', errors='replace',
                        creationflags=subprocess.CREATE_NO_WINDOW
                    )
                    for line in ssid_result.stdout.split("\n"):
                        if "SSID" in line and "name" in line.lower():
                            hotspot_info["ssid"] = line.split(":")[-1].strip().strip('"')
                            break
                except Exception:
                    pass

        except Exception as e:
            logger.debug(f"Hotspot kontrol hatası: {e}")

        return hotspot_info

    def _check_mqtt_port(self, host: str = "127.0.0.1", port: int = 1883) -> bool:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((host, port))
            sock.close()
            return result == 0
        except Exception:
            return False

    def _get_network_ips(self) -> Dict:
        ips = {"ethernet": None, "wifi": None, "hotspot": None}

        try:
            result = subprocess.run(
                ["powershell", "-Command",
                 "Get-NetIPAddress -AddressFamily IPv4 | "
                 "Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } | "
                 "Select-Object IPAddress, InterfaceAlias | Format-Table -HideTableHeaders"],
                capture_output=True, text=True, timeout=5,
                encoding='cp857', errors='replace',
                creationflags=subprocess.CREATE_NO_WINDOW
            )

            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    parts = line.strip().split(None, 1)
                    if len(parts) >= 2:
                        ip, iface = parts[0], parts[1].strip()

                        if NetworkMonitor.HOTSPOT_SUBNET in ip:
                            ips["hotspot"] = ip
                        elif "ethernet" in iface.lower() or "eth" in iface.lower():
                            ips["ethernet"] = ip
                        elif "wi-fi" in iface.lower() or "wifi" in iface.lower() or "wlan" in iface.lower():
                            ips["wifi"] = ip

        except Exception as e:
            logger.debug(f"IP adresi alınamadı: {e}")

        return ips

    @pyqtSlot()
    def run_check(self):
        if self._busy:
            return
        self._busy = True
        try:
            status = {
                "internet_connected": self._check_internet(),
            }
            hotspot = self._check_hotspot()
            status.update({
                "hotspot_active": hotspot.get("active", False),
                "hotspot_ssid": hotspot.get("ssid", ""),
                "hotspot_ip": hotspot.get("ip", "192.168.137.1"),
                "hotspot_clients": hotspot.get("clients", 0),
            })
            status["mqtt_broker_reachable"] = self._check_mqtt_port()
            ips = self._get_network_ips()
            status["ethernet_ip"] = ips.get("ethernet")
            status["wifi_ip"] = ips.get("wifi")
            self.status_ready.emit(status)
        except Exception as e:
            self.error_occurred.emit(f"Network check hatası: {e}")
        finally:
            self._busy = False


class NetworkMonitor(QObject):
    """
    Ağ durumu izleme servisi.
    
    Periyodik olarak kontrol eder:
    1. Internet erişimi (DNS resolution + HTTP check)
    2. Windows Mobile Hotspot durumu
    3. MQTT broker port erişilebilirliği
    4. Bağlı cihaz sayısı (hotspot)
    
    Signals:
        internet_status_changed(bool): Internet durumu değiştiğinde
        hotspot_status_changed(dict): Hotspot durumu değiştiğinde
        gateway_mode_changed(str): Gateway modu değiştiğinde ("online"/"offline")
        network_status_updated(dict): Tüm durum güncellemesi
    """
    
    internet_status_changed = pyqtSignal(bool)
    hotspot_status_changed = pyqtSignal(dict)
    gateway_mode_changed = pyqtSignal(str)
    network_status_updated = pyqtSignal(dict)
    _request_check = pyqtSignal()
    
    # Internet kontrol hedefleri
    INTERNET_CHECK_HOSTS = [
        ("8.8.8.8", 53),        # Google DNS
        ("1.1.1.1", 53),        # Cloudflare DNS
        ("208.67.222.222", 53), # OpenDNS
    ]
    
    HOTSPOT_SUBNET = "192.168.137."  # Windows Mobile Hotspot varsayılan subnet
    
    def __init__(self, check_interval_ms: int = 5000, parent=None):
        """
        Args:
            check_interval_ms: Kontrol aralığı (ms), varsayılan 5sn
            parent: Parent QObject
        """
        super().__init__(parent)
        
        self._status = NetworkStatus()
        self._check_interval = check_interval_ms
        self._last_internet_state = None
        self._last_gateway_mode = None

        self._worker_thread = QThread(self)
        self._worker = NetworkMonitorWorker()
        self._worker.moveToThread(self._worker_thread)
        self._request_check.connect(self._worker.run_check)
        self._worker.status_ready.connect(self._apply_worker_status)
        self._worker.error_occurred.connect(self._on_worker_error)
        self._worker_thread.start()
        
        # Periyodik kontrol timer
        self._check_timer = QTimer(self)
        self._check_timer.timeout.connect(self._periodic_check)
    
    def start_monitoring(self):
        """Periyodik ağ izlemeyi başlat"""
        self._request_check.emit()
        self._check_timer.start(self._check_interval)
        logger.info(f"Network monitoring başlatıldı ({self._check_interval}ms aralıkla)")
    
    def stop_monitoring(self):
        """Periyodik izlemeyi durdur"""
        self._check_timer.stop()
        
        # QThread Cleanup to prevent "Destroyed while thread is still running"
        if hasattr(self, '_worker_thread') and self._worker_thread.isRunning():
            self._worker_thread.quit()
            self._worker_thread.wait(1000)
            
        logger.info("Network monitoring durduruldu")
    
    def _determine_gateway_mode(self) -> str:
        """Gateway modunu belirle"""
        if self._status.internet_connected and self._status.hotspot_active:
            return "online"  # Hem internet hem hotspot aktif → tam gateway
        elif self._status.hotspot_active:
            return "offline"  # Sadece hotspot → offline gateway
        elif self._status.internet_connected:
            return "hybrid"   # Sadece internet → cloud-only mod
        else:
            return "disconnected"  # Hiçbir bağlantı yok
    
    def _periodic_check(self):
        """Periyodik check isteği gönder."""
        self._request_check.emit()

    @pyqtSlot(dict)
    def _apply_worker_status(self, status: dict):
        """Worker'dan gelen sonucu UI-thread state'ine uygula."""
        try:
            internet = status.get("internet_connected", False)
            self._status.internet_connected = internet
            
            # Internet durum değişikliği
            if self._last_internet_state is not None and internet != self._last_internet_state:
                self.internet_status_changed.emit(internet)
                logger.info(f"Internet durumu: {'Bağlı' if internet else 'Bağlı değil'}")
            self._last_internet_state = internet
            
            self._status.hotspot_active = status.get("hotspot_active", False)
            self._status.hotspot_ssid = status.get("hotspot_ssid", "")
            self._status.hotspot_ip = status.get("hotspot_ip", "192.168.137.1")
            self._status.hotspot_clients = status.get("hotspot_clients", 0)
            
            self._status.mqtt_broker_reachable = status.get("mqtt_broker_reachable", False)
            
            self._status.ethernet_ip = status.get("ethernet_ip")
            self._status.wifi_ip = status.get("wifi_ip")
            
            mode = self._determine_gateway_mode()
            self._status.gateway_mode = mode
            
            if self._last_gateway_mode is not None and mode != self._last_gateway_mode:
                self.gateway_mode_changed.emit(mode)
                logger.info(f"Gateway modu: {mode}")
            self._last_gateway_mode = mode
            
            status_dict = self.get_status()
            self.network_status_updated.emit(status_dict)
            
        except Exception as e:
            logger.error(f"Network check hatası: {e}")

    @pyqtSlot(str)
    def _on_worker_error(self, error_message: str):
        logger.error(error_message)
    
    def get_status(self) -> Dict:
        """Güncel ağ durumunu dictionary olarak döndür"""
        return {
            "internet_connected": self._status.internet_connected,
            "hotspot_active": self._status.hotspot_active,
            "hotspot_ssid": self._status.hotspot_ssid,
            "hotspot_ip": self._status.hotspot_ip,
            "hotspot_clients": self._status.hotspot_clients,
            "mqtt_broker_reachable": self._status.mqtt_broker_reachable,
            "mqtt_bridge_connected": self._status.mqtt_bridge_connected,
            "ethernet_ip": self._status.ethernet_ip,
            "wifi_ip": self._status.wifi_ip,
            "gateway_mode": self._status.gateway_mode,
        }
    
    def update_bridge_status(self, connected: bool):
        """MQTT bridge durumunu güncelle (dışarıdan çağrılır)"""
        self._status.mqtt_bridge_connected = connected
    
    def get_hotspot_ip(self) -> str:
        """Hotspot IP adresini döndür (ESP'ler bu IP'ye bağlanacak)"""
        return self._status.hotspot_ip or "192.168.137.1"
    
    def is_gateway_ready(self) -> bool:
        """Gateway tam hazır mı? (Hotspot + MQTT broker aktif)"""
        return self._status.hotspot_active and self._status.mqtt_broker_reachable
