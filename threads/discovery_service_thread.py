"""
Discovery Service Thread - Android App için UDP discovery servisi

Android app, UDP port 5051'de broadcast göndererek GUI sunucusunu keşfeder.
Bu thread, discovery request'lerini dinler ve response gönderir.
"""

import socket
import json
import logging
from datetime import datetime
from PyQt6.QtCore import QThread, pyqtSignal


def get_local_ip():
    """
    Yerel IP adresini alır.
    Google DNS'e bağlanarak aktif network interface'in IP'sini bulur.
    
    Returns:
        str: Yerel IP adresi (örn: "192.168.1.100")
    """
    s = None
    try:
        # Google DNS'e bağlanarak yerel IP'yi öğren
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        return local_ip
    except Exception:
        # Fallback: localhost
        return "127.0.0.1"
    finally:
        if s:
            try:
                s.close()
            except Exception:
                pass


def get_hostname():
    """
    Sistem hostname'ini alır.
    
    Returns:
        str: Hostname (örn: "PEMF-GUI" veya sistem hostname'i)
    """
    try:
        import socket as sock
        hostname = sock.gethostname()
        return hostname if hostname else "PEMF-GUI"
    except Exception:
        return "PEMF-GUI"


class DiscoveryServiceThread(QThread):
    """
    UDP discovery servisi thread'i.
    Android app'in discovery request'lerini dinler ve response gönderir.
    
    Port: 5051 (UDP)
    Protocol: UDP Broadcast
    """
    
    # Signal: Discovery servisi başlatıldığında
    service_started = pyqtSignal()
    
    # Signal: Discovery servisi durdurulduğunda
    service_stopped = pyqtSignal()
    
    # Signal: Discovery request alındığında (log için)
    request_received = pyqtSignal(str)  # client_ip
    
    def __init__(self, logger=None, parent=None, mqtt_broker_host=None, mqtt_broker_port=1883, mqtt_broker_tls=False):
        """
        Discovery servisi thread'ini başlatır.
        
        Args:
            logger: Logger instance (opsiyonel)
            parent: Parent widget (opsiyonel)
            mqtt_broker_host: MQTT broker IP adresi (opsiyonel, varsayılan: local IP)
            mqtt_broker_port: MQTT broker portu (varsayılan: 1883)
            mqtt_broker_tls: MQTT TLS aktif mi? (varsayılan: False)
        """
        super().__init__(parent)
        self.logger = logger or logging.getLogger(__name__)
        self._stop_requested = False
        self.discovery_port = 5051
        self.socket = None
        
        # Discovery response bilgileri
        self.local_ip = get_local_ip()
        self.hostname = get_hostname()
        # Note: websocket_port Android app'in beklediği format için gerekli
        # Ancak Android app artık MQTT kullanıyor, WebSocket değil
        self.websocket_port = 8081  # Port bilgisi (Android app discovery format için)
        self.http_port = 8080  # HTTP port (gelecekte kullanılabilir)
        self.version = "1"  # Software version
        
        # MQTT broker bilgileri — Android app bu bilgiyle broker'a bağlanır
        self.mqtt_broker_host = mqtt_broker_host or self.local_ip
        self.mqtt_broker_port = mqtt_broker_port
        self.mqtt_broker_tls = mqtt_broker_tls
        
    def stop(self):
        """Thread'i durdurma isteği gönderir"""
        self._stop_requested = True
        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
    
    def _create_discovery_response(self):
        """
        Discovery response JSON'unu oluşturur.
        Android app'in DiscoveryResponse modeline uygun format.
        MQTT broker bilgileri eklendi — Android bu IP:port ile broker'a bağlanır.
        
        Returns:
            str: JSON string
        """
        response = {
            "type": "discovery_response",
            "ip": self.local_ip,
            "ports": [self.http_port, self.websocket_port],
            "websocket_port": self.websocket_port,
            "http_port": self.http_port,
            "hostname": self.hostname,
            "timestamp": datetime.now().isoformat(),
            "version": self.version,
            # MQTT broker bilgileri — Gateway modu için eklendi
            "mqtt_broker_host": self.mqtt_broker_host,
            "mqtt_broker_port": self.mqtt_broker_port,
            "mqtt_broker_tls": self.mqtt_broker_tls,
            "gateway_mode": True  # Bu GUI, gateway olarak çalışıyor
        }
        return json.dumps(response)
    
    def _is_discovery_request(self, data):
        """
        Gelen data'nın discovery request olup olmadığını kontrol eder.
        
        Args:
            data: Gelen UDP data (bytes)
            
        Returns:
            bool: Discovery request ise True
        """
        try:
            request = json.loads(data.decode('utf-8'))
            return request.get("type") == "discovery"
        except Exception:
            return False
    
    def run(self):
        """
        Thread'in ana çalışma metodu.
        UDP socket ile discovery request'lerini dinler ve response gönderir.
        """
        try:
            # UDP socket oluştur
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # Windows'ta SO_REUSEPORT yok, sadece SO_REUSEADDR kullan
            try:
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except AttributeError:
                # Windows'ta SO_REUSEPORT yok, sadece SO_REUSEADDR yeterli
                pass
            
            # Broadcast'i dinle
            self.socket.bind(('', self.discovery_port))
            self.socket.settimeout(1.0)  # 1 saniye timeout (stop kontrolü için)
            
            if self.logger:
                self.logger.info(f"Discovery servisi başlatıldı (UDP port {self.discovery_port})")
                self.logger.info(f"Local IP: {self.local_ip}, Hostname: {self.hostname}")
            
            self.service_started.emit()
            
            # Ana loop: Discovery request'lerini dinle
            while not self._stop_requested:
                try:
                    # UDP packet al (timeout ile)
                    data, addr = self.socket.recvfrom(1024)
                    client_ip = addr[0]
                    
                    # Discovery request kontrolü
                    if self._is_discovery_request(data):
                        if self.logger:
                            self.logger.debug(f"Discovery request alındı: {client_ip}")
                        
                        self.request_received.emit(client_ip)
                        
                        # Response gönder
                        response = self._create_discovery_response()
                        response_bytes = response.encode('utf-8')
                        
                        self.socket.sendto(response_bytes, addr)
                        
                        if self.logger:
                            self.logger.info(f"Discovery response gönderildi: {client_ip} -> {response}")
                    else:
                        if self.logger:
                            self.logger.debug(f"Geçersiz discovery request: {client_ip}")
                
                except socket.timeout:
                    # Timeout normal (stop kontrolü için)
                    continue
                
                except Exception as e:
                    if not self._stop_requested:
                        if self.logger:
                            self.logger.error(f"Discovery servisi hatası: {e}", exc_info=True)
                    continue
        
        except Exception as e:
            if self.logger:
                self.logger.error(f"Discovery servisi başlatılamadı: {e}", exc_info=True)
        
        finally:
            # Socket'i kapat
            if self.socket:
                try:
                    self.socket.close()
                except Exception:
                    pass
                self.socket = None
            
            if self.logger:
                self.logger.info("Discovery servisi durduruldu")
            
            self.service_stopped.emit()

