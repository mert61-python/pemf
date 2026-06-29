"""
Mosquitto Manager — Mosquitto MQTT Broker + Python Bridge Yönetim Servisi

LattePanda üzerinde YEREL Mosquitto broker'ını yönetir (başlat/durdur/durum).
NOT (2026-06-28): HiveMQ cloud bridge KALDIRILDI — sistem yerel-mosquitto-only (ESP'ler
anon yerel broker'a bağlanır). start_bridge/stop_bridge artık inaktif no-op'tur
(services/mqtt_bridge.py silindi → import hatasını yutar, False döner).

Kullanım:
    manager = MosquittoManager()
    manager.start()  # Broker'ı başlat
    status = manager.get_status()  # Durumu sorgula
"""

import subprocess
import logging
import shutil
import os
import sys
import platform
import socket
import psutil
from pathlib import Path
from typing import Optional, Dict
from PyQt6.QtCore import QObject, QTimer, QThread, pyqtSignal, pyqtSlot


logger = logging.getLogger(__name__)


class MosquittoStatus:
    """Mosquitto broker durum bilgisi"""
    def __init__(self):
        self.installed: bool = False
        self.running: bool = False
        self.service_exists: bool = False
        self.version: str = ""
        self.config_path: str = ""
        self.bridge_connected: bool = False
        self.port: int = 1883
        self.pid: Optional[int] = None


class MosquittoCheckWorker(QObject):
    """Mosquitto durum sorgularını arka planda çalıştırır."""

    status_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, service_name: str, parent=None):
        super().__init__(parent)
        self._service_name = service_name
        self._busy = False

    def _check_process_running(self) -> Dict:
        result_data = {
            "running": False,
            "pid": None,
        }
        try:
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq mosquitto.exe", "/NH"],
                capture_output=True, text=True, timeout=5,
                encoding='cp857', errors='replace',
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            running = "mosquitto.exe" in result.stdout
            result_data["running"] = running

            if running:
                parts = result.stdout.strip().split()
                if len(parts) >= 2:
                    try:
                        result_data["pid"] = int(parts[1])
                    except ValueError:
                        pass
        except Exception:
            pass
        return result_data

    def _check_service_status(self) -> Dict:
        result_data = {
            "service_exists": False,
            "running": False,
            "pid": None,
        }

        if platform.system() != "Windows":
            return self._check_process_running()

        try:
            result = subprocess.run(
                ["sc", "query", self._service_name],
                capture_output=True, text=True, timeout=5,
                encoding='cp857', errors='replace',
                creationflags=subprocess.CREATE_NO_WINDOW
            )

            if result.returncode == 0:
                result_data["service_exists"] = True
                output = result.stdout
                result_data["running"] = "RUNNING" in output
            else:
                process_data = self._check_process_running()
                result_data.update(process_data)
        except Exception:
            process_data = self._check_process_running()
            result_data.update(process_data)

        return result_data

    def _check_port_open(self, port: int) -> bool:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex(('127.0.0.1', port))
            sock.close()
            return result == 0
        except Exception:
            return False

    @pyqtSlot(int)
    def run_check(self, port: int):
        if self._busy:
            return
        self._busy = True
        try:
            status = self._check_service_status()
            status["port_open"] = self._check_port_open(port)
            self.status_ready.emit(status)
        except Exception as e:
            self.error_occurred.emit(f"Mosquitto periodic check hatası: {e}")
        finally:
            self._busy = False


class MosquittoManager(QObject):
    """
    Mosquitto MQTT broker yönetim servisi.
    
    Windows servis olarak çalışan Mosquitto'yu yönetir:
    - Otomatik başlatma/durdurma
    - Durum izleme (QTimer ile periyodik)
    - Bridge bağlantı durumu
    - Config dosya yönetimi
    
    Signals:
        status_changed(dict): Broker durumu değiştiğinde
        bridge_status_changed(bool): Bridge bağlantısı değiştiğinde 
        error_occurred(str): Hata oluştuğunda
    """
    
    status_changed = pyqtSignal(dict)
    bridge_status_changed = pyqtSignal(bool)
    error_occurred = pyqtSignal(str)
    _request_check = pyqtSignal(int)
    
    # Default paths
    MOSQUITTO_EXE_PATHS = [
        # Eğer EXE yapıldıysa MEIPASS içindeki gömülü taşınabilir mosquitto
        os.path.join(getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__))), "bin", "mosquitto", "mosquitto.exe"),
        r"C:\Program Files\mosquitto\mosquitto.exe",
        r"C:\Program Files (x86)\mosquitto\mosquitto.exe",
        r"C:\mosquitto\mosquitto.exe",
    ]
    
    MOSQUITTO_SERVICE_NAME = "mosquitto"
    MOSQUITTO_DATA_DIR = r"C:\ProgramData\mosquitto"
    
    def __init__(self, check_interval_ms: int = 10000, parent=None):
        """
        Args:
            check_interval_ms: Durum kontrol aralığı (ms), varsayılan 10sn
            parent: Parent QObject
        """
        super().__init__(parent)
        
        self._check_interval = check_interval_ms
        self._status = MosquittoStatus()
        self._last_bridge_status = False
        
        # Python MQTT Bridge
        self._mqtt_bridge = None

        # mDNS Servis Yayıncısı (pemf-gateway.local)
        self._mdns_service = None

        self._check_thread = QThread(self)
        self._check_worker = MosquittoCheckWorker(self.MOSQUITTO_SERVICE_NAME)
        self._check_worker.moveToThread(self._check_thread)
        self._request_check.connect(self._check_worker.run_check)
        self._check_worker.status_ready.connect(self._apply_periodic_status)
        self._check_worker.error_occurred.connect(self._on_check_worker_error)
        self._check_thread.start()
        
        # Periyodik durum kontrolü
        self._check_timer = QTimer(self)
        self._check_timer.timeout.connect(self._periodic_check)
        
        # Başlangıçta durumu kontrol et
        self._detect_installation()
    
    def start_monitoring(self):
        """Periyodik durum izlemeyi başlat"""
        self._request_check.emit(self._status.port)
        self._check_timer.start(self._check_interval)
        # mDNS yayıncısını başlat (ESP ve Android pemf-gateway.local ile bulabilsin)
        self._start_mdns()
        logger.info(f"Mosquitto monitoring başlatıldı ({self._check_interval}ms aralıkla)")
        
    def get_bundled_exe_path(self) -> Optional[str]:
        """PyInstaller içindeki veya klasördeki portable mosquitto yolunu döner"""
        appdata_path = os.path.join(os.environ.get('APPDATA', 'C:/'), 'PEMF_GUI', 'mosquitto', 'mosquitto.exe')
        if getattr(sys, 'frozen', False):
            # 1. Öncelik: APPDATA içindeki kalıcı kopya (Firewall sorununu çözer)
            if os.path.exists(appdata_path):
                return appdata_path
                
            base_dir = os.path.dirname(sys.executable)
            # Try app directory first
            path = os.path.join(base_dir, "bin", "mosquitto", "mosquitto.exe")
            if os.path.exists(path):
                return path
            # Try PyInstaller _MEIPASS (Fallback)
            path = os.path.join(sys._MEIPASS, "bin", "mosquitto", "mosquitto.exe")
            if os.path.exists(path):
                return path
        else:
            base_dir = os.path.dirname(os.path.dirname(__file__))
            path = os.path.join(base_dir, "bin", "mosquitto", "mosquitto.exe")
            if os.path.exists(path):
                return path
        return None
    
    def stop_monitoring(self):
        """Periyodik durum izlemeyi durdur"""
        self._check_timer.stop()
        self.stop_bridge()
        self._stop_mdns()
        
        # QThread Cleanup to prevent "Destroyed while thread is still running"
        if hasattr(self, '_check_thread') and self._check_thread.isRunning():
            self._check_thread.quit()
            self._check_thread.wait(1000)
            
        logger.info("Mosquitto monitoring durduruldu")

    # ─── mDNS ─────────────────────────────────────────────────

    def _start_mdns(self):
        """mDNS yayıncısını başlat: pemf-gateway.local → yerel IP"""
        if self._mdns_service and self._mdns_service.is_running():
            return
        try:
            from services.mdns_service import MDNSService
            self._mdns_service = MDNSService(mqtt_port=self._status.port)
            ok = self._mdns_service.start()
            if ok:
                logger.info("mDNS yayıncısı başlatıldı: pemf-gateway.local")
            else:
                logger.warning("mDNS yayıncısı başlatamadı (zeroconf kurulu değil olabilir)")
        except Exception as e:
            logger.warning(f"mDNS başlatma hatası: {e}")

    def _stop_mdns(self):
        """mDNS yayıncısını durdur"""
        if self._mdns_service:
            try:
                self._mdns_service.stop()
                logger.info("mDNS yayıncısı durduruldu")
            except Exception as e:
                logger.warning(f"mDNS durdurma hatası: {e}")
            finally:
                self._mdns_service = None
    
    # ─── PYTHON MQTT BRIDGE ──────────────────────────────────────

    def start_bridge(self, config_path: Optional[str] = None) -> bool:
        """
        Python MQTT bridge'ini başlat.
        
        Mosquitto 2.0.18 native bridge TLS Windows bug'ı nedeniyle,
        Python paho-mqtt ile Local ↔ HiveMQ Cloud bridge yapılır.
        
        Args:
            config_path: config.json dosya yolu (None ise otomatik bulunur)
        """
        if self._mqtt_bridge and self._mqtt_bridge.is_running():
            logger.info("Python MQTT bridge zaten çalışıyor")
            return True
        
        try:
            from services.mqtt_bridge import MQTTBridge
            
            # Config yolu bul (ProductionConfigManager ile güvenli)
            if not config_path:
                try:
                    from utils.production_config_manager import get_production_config
                    prod_config = get_production_config()
                    cfg_p = prod_config.get_user_config_path()
                    if cfg_p.exists():
                        config_path = str(cfg_p)
                except Exception as e:
                    logger.warning(f"Production config path tespit edilemedi: {e}")
                
                # Fallback: Eski olası yollar (eğer APPDATA'da henüz yoksa)
                if not config_path:
                    possible_paths = [
                        os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "config.json"),
                        os.path.join(os.getcwd(), "config", "config.json"),
                    ]
                    for p in possible_paths:
                        if os.path.exists(p):
                            config_path = p
                            break
            
            if config_path and os.path.exists(config_path):
                config = MQTTBridge.load_config_from_file(config_path)
                logger.info(f"Bridge config yüklendi: {config_path}")
            else:
                config = None
                logger.warning("Bridge config bulunamadı, varsayılan değerler kullanılacak")
            
            self._mqtt_bridge = MQTTBridge(config)
            self._mqtt_bridge.start()
            
            logger.info("Python MQTT bridge başlatıldı")
            return True
            
        except Exception as e:
            logger.error(f"Python MQTT bridge başlatma hatası: {e}")
            self._mqtt_bridge = None
            return False
    
    def stop_bridge(self):
        """Python MQTT bridge'ini durdur"""
        if self._mqtt_bridge:
            try:
                self._mqtt_bridge.stop()
                logger.info("Python MQTT bridge durduruldu")
            except Exception as e:
                logger.error(f"Bridge durdurma hatası: {e}")
            finally:
                self._mqtt_bridge = None
    
    def is_bridge_running(self) -> bool:
        """Python bridge çalışıyor mu?"""
        return self._mqtt_bridge is not None and self._mqtt_bridge.is_running()
    
    def get_bridge_stats(self) -> Optional[Dict]:
        """Python bridge istatistikleri"""
        if self._mqtt_bridge:
            return self._mqtt_bridge.get_stats()
        return None
    
    def _detect_installation(self):
        """Mosquitto kurulumunu tespit et (Asenkron)"""
        import threading
        
        def _detect_task():
            # Önce Portable (Bundled) Mosquitto'yu ara
            portable_exe = self.get_bundled_exe_path()
            if portable_exe and os.path.exists(portable_exe):
                self._status.installed = True
                self._status.config_path = os.path.join(
                    os.path.dirname(portable_exe), "mosquitto.conf"
                )
                logger.info(f"Mosquitto Portable Bulundu: {portable_exe}")
                
                # Versiyon Bilgisini Oku
                try:
                    result = subprocess.run(
                        [portable_exe, "-h"],
                        capture_output=True, text=True, timeout=5,
                        encoding='cp857', errors='replace',
                        creationflags=subprocess.CREATE_NO_WINDOW
                    )
                    for line in (result.stdout + result.stderr).split('\n'):
                        if "version" in line.lower():
                            self._status.version = line.strip()
                            break
                except Exception as e:
                    logger.debug(f"Portable versiyon alınamadı: {e}")
                return
            
            # Bulunamazsa Geleneksel Kurulum (EXE'yi bul)
            for exe_path in self.MOSQUITTO_EXE_PATHS:
                if os.path.exists(exe_path):
                    self._status.installed = True
                    self._status.config_path = os.path.join(
                        os.path.dirname(exe_path), "mosquitto.conf"
                    )
                    logger.info(f"Mosquitto bulundu: {exe_path}")
                    
                    # Versiyon al
                    try:
                        result = subprocess.run(
                            [exe_path, "--help"],
                            capture_output=True, text=True, timeout=5,
                            encoding='cp857', errors='replace',
                            creationflags=subprocess.CREATE_NO_WINDOW
                        )
                        output = result.stdout + result.stderr
                        # "mosquitto version X.X.X" satırını bul
                        for line in output.split("\n"):
                            if "version" in line.lower():
                                self._status.version = line.strip()
                                break
                    except Exception as e:
                        logger.debug(f"Versiyon alınamadı: {e}")
                    
                    return
            
            # PATH'te ara
            mosquitto_in_path = shutil.which("mosquitto")
            if mosquitto_in_path:
                self._status.installed = True
                self._status.config_path = os.path.join(
                    os.path.dirname(mosquitto_in_path), "mosquitto.conf"
                )
                logger.info(f"Mosquitto PATH'te bulundu: {mosquitto_in_path}")
                return
            
            self._status.installed = False
            logger.warning("Mosquitto kurulumu bulunamadı")

        threading.Thread(target=_detect_task, daemon=True).start()
    
    def _check_service_status(self) -> bool:
        """Windows servis durumunu kontrol et"""
        if platform.system() != "Windows":
            return self._check_process_running()
        
        try:
            result = subprocess.run(
                ["sc", "query", self.MOSQUITTO_SERVICE_NAME],
                capture_output=True, text=True, timeout=5,
                encoding='cp857', errors='replace',
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            if result.returncode == 0:
                self._status.service_exists = True
                output = result.stdout
                
                if "RUNNING" in output:
                    self._status.running = True
                    return True
                else:
                    self._status.running = False
                    return False
            else:
                self._status.service_exists = False
                # Servis yoksa process olarak çalışıyor olabilir
                return self._check_process_running()
                
        except Exception as e:
            logger.error(f"Servis durumu kontrol hatası: {e}")
            return self._check_process_running()
    
    def _check_process_running(self) -> bool:
        """mosquitto.exe process olarak çalışıyor mu?"""
        try:
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq mosquitto.exe", "/NH"],
                capture_output=True, text=True, timeout=5,
                encoding='cp857', errors='replace',
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            running = "mosquitto.exe" in result.stdout
            self._status.running = running
            
            if running:
                # PID'i al
                parts = result.stdout.strip().split()
                if len(parts) >= 2:
                    try:
                        self._status.pid = int(parts[1])
                    except ValueError:
                        pass
            
            return running
        except Exception as e:
            logger.error(f"Process kontrol hatası: {e}")
            return False
    
    def _check_port_open(self, port: int = 1883) -> bool:
        """MQTT portun açık olduğunu doğrula"""
        import socket
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex(('127.0.0.1', port))
            sock.close()
            return result == 0
        except Exception:
            return False
    
    def _periodic_check(self):
        """Periyodik check isteği gönder."""
        self._request_check.emit(self._status.port)

    @pyqtSlot(dict)
    def _apply_periodic_status(self, check_result: dict):
        """Worker check sonucunu UI-thread state'ine uygular."""
        try:
            was_running = self._status.running

            self._status.running = check_result.get("running", False)
            self._status.service_exists = check_result.get("service_exists", False)
            self._status.pid = check_result.get("pid")
            port_open = check_result.get("port_open", False)
            
            # Python bridge durumunu kontrol et
            if self._mqtt_bridge:
                bridge_active = self._mqtt_bridge.is_bridge_active()
                if bridge_active != self._last_bridge_status:
                    self._status.bridge_connected = bridge_active
                    self._last_bridge_status = bridge_active
                    self.bridge_status_changed.emit(bridge_active)
                    logger.info(f"Bridge durumu: {'Bağlı' if bridge_active else 'Bağlı değil'}")
            
            # Durum değişikliği bildirimi
            status_dict = self.get_status()
            status_dict["port_open"] = port_open
            
            if was_running != self._status.running:
                logger.info(f"Mosquitto durumu değişti: {'Çalışıyor' if self._status.running else 'Durdu'}")
            
            self.status_changed.emit(status_dict)
            
        except Exception as e:
            logger.error(f"Periyodik kontrol hatası: {e}")

    @pyqtSlot(str)
    def _on_check_worker_error(self, error_message: str):
        logger.error(error_message)
    
    def start_broker(self) -> bool:
        """Mosquitto broker'ı başlat (Asenkron)"""
        import threading
        
        if not self._status.installed:
            self.error_occurred.emit("Mosquitto kurulu değil veya portable dosyalar (bin/mosquitto/) bulunamadı.")
            return False
        
        if self._status.running:
            logger.info("Mosquitto zaten çalışıyor")
            return True
        
        def _start_task():
            try:
                # 1. Portable EXE varsa onu tercih et
                portable_exe = self.get_bundled_exe_path()
                if portable_exe and os.path.exists(portable_exe):
                    logger.info("Portable Mosquitto başlatılıyor...")
                    args = [portable_exe]
                    if self._status.config_path and os.path.exists(self._status.config_path):
                        args.extend(["-c", self._status.config_path])
                    
                    subprocess.Popen(
                        args,
                        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
                    )
                    logger.info("Portable Mosquitto başarıyla başlatıldı.")
                    self._status.running = True
                    return

                # 2. Windows servis olarak başlat
                if self._status.service_exists:
                    result = subprocess.run(
                        ["net", "start", self.MOSQUITTO_SERVICE_NAME],
                        capture_output=True, text=True, timeout=15,
                        encoding='cp857', errors='replace',
                        creationflags=subprocess.CREATE_NO_WINDOW
                    )
                    if result.returncode == 0:
                        logger.info("Mosquitto servisi başlatıldı")
                        self._status.running = True
                        return
                    else:
                        logger.warning(f"Servis başlatma hatası: {result.stderr}")
                
                # 3. Process olarak başlat (servis yoksa)
                for exe_path in self.MOSQUITTO_EXE_PATHS:
                    if os.path.exists(exe_path):
                        config_path = os.path.join(os.path.dirname(exe_path), "mosquitto.conf")
                        args = [exe_path]
                        if os.path.exists(config_path):
                            args.extend(["-c", config_path])
                        
                        subprocess.Popen(
                            args,
                            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
                        )
                        logger.info(f"Mosquitto process olarak başlatıldı: {exe_path}")
                        self._status.running = True
                        return
                
                self.error_occurred.emit("Mosquitto çalıştırılamadı")
                
            except Exception as e:
                error_msg = f"Mosquitto başlatma hatası: {e}"
                logger.error(error_msg)
                self.error_occurred.emit(error_msg)

        threading.Thread(target=_start_task, daemon=True).start()
        return True
    
    def stop_broker(self) -> bool:
        """Mosquitto broker'ı durdur (Asenkron)"""
        import threading
        
        def _stop_task():
            try:
                # 1. Portable exe kontrol
                portable_exe = self.get_bundled_exe_path()
                if portable_exe and os.path.exists(portable_exe):
                    logger.info("Portable Mosquitto taskkill ile durduruluyor...")
                    subprocess.run(
                        ["taskkill", "/F", "/IM", "mosquitto.exe"],
                        capture_output=True, text=True, timeout=10,
                        encoding='cp857', errors='replace',
                        creationflags=subprocess.CREATE_NO_WINDOW
                    )
                    self._status.running = False
                    return

                if self._status.service_exists:
                    result = subprocess.run(
                        ["net", "stop", self.MOSQUITTO_SERVICE_NAME],
                        capture_output=True, text=True, timeout=15,
                        encoding='cp857', errors='replace',
                        creationflags=subprocess.CREATE_NO_WINDOW
                    )
                    if result.returncode == 0:
                        logger.info("Mosquitto servisi durduruldu")
                        self._status.running = False
                        return
                
                # Process'i sonlandır
                subprocess.run(
                    ["taskkill", "/F", "/IM", "mosquitto.exe"],
                    capture_output=True, text=True, timeout=10,
                    encoding='cp857', errors='replace',
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                self._status.running = False
                
            except Exception as e:
                logger.error(f"Mosquitto durdurma hatası: {e}")

        threading.Thread(target=_stop_task, daemon=True).start()
        return True
    
    def restart_broker(self) -> bool:
        """Mosquitto broker'ı yeniden başlat (Asenkron)"""
        import threading
        def _restart_task():
            try:
                if self._status.service_exists:
                    subprocess.run(
                        ["net", "stop", self.MOSQUITTO_SERVICE_NAME],
                        capture_output=True, text=True, timeout=15,
                        encoding='cp857', errors='replace',
                        creationflags=subprocess.CREATE_NO_WINDOW
                    )
                subprocess.run(
                    ["taskkill", "/F", "/IM", "mosquitto.exe"],
                    capture_output=True, text=True, timeout=10,
                    encoding='cp857', errors='replace',
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                self._status.running = False
            except Exception as e:
                logger.error(f"Mosquitto durdurma hatası (restart): {e}")

            # Şimdi start (bu sefer direkt senkron çalışabilir çünkü içinde yeni bir thread başlatıyor)
            self.start_broker()

        threading.Thread(target=_restart_task, daemon=True).start()
        return True
    
    def get_status(self) -> Dict:
        """Güncel durum bilgisini döndür"""
        status = {
            "installed": self._status.installed,
            "running": self._status.running,
            "service_exists": self._status.service_exists,
            "version": self._status.version,
            "port": self._status.port,
            "pid": self._status.pid,
            "bridge_connected": self._status.bridge_connected,
            "bridge_running": self.is_bridge_running(),
            "mdns_running": self._mdns_service.is_running() if self._mdns_service else False,
            "mdns_ip": self._mdns_service.get_current_ip() if self._mdns_service else None,
        }
        if self._mqtt_bridge:
            bridge_stats = self._mqtt_bridge.get_stats()
            status["bridge_stats"] = bridge_stats
        return status
    
    def update_bridge_status(self, connected: bool):
        """Bridge durumunu güncelle (MQTT callback'ten çağrılır)"""
        # Manager kendi Python bridge instance'ını yönetiyorsa tek doğruluk kaynağı odur.
        if self._mqtt_bridge and self._mqtt_bridge.is_running():
            connected = bool(self._mqtt_bridge.is_bridge_active())

        if connected != self._last_bridge_status:
            self._status.bridge_connected = connected
            self._last_bridge_status = connected
            self.bridge_status_changed.emit(connected)
            logger.info(f"Bridge durumu: {'Bağlı' if connected else 'Bağlı değil'}")
    
    def ensure_running(self) -> bool:
        """Broker çalışmıyorsa başlat, çalışıyorsa True döndür (Asenkron)"""
        import threading
        
        def _ensure_task():
            self._check_service_status()
            if self._status.running:
                logger.info("Mosquitto zaten çalışıyor")
                return
            
            logger.info("Mosquitto çalışmıyor, başlatılıyor...")
            self.start_broker()
            
        threading.Thread(target=_ensure_task, daemon=True).start()
        return True
    
    def install_config_files(self, project_config_dir: str) -> bool:
        """
        Proje config dosyalarını Mosquitto dizinine kopyala.
        
        Args:
            project_config_dir: config/mosquitto/ dizin yolu
        """
        try:
            dest_conf_d = os.path.join(self.MOSQUITTO_DATA_DIR, "conf.d")
            os.makedirs(dest_conf_d, exist_ok=True)
            
            # Ana config
            src_main = os.path.join(project_config_dir, "mosquitto.conf")
            if os.path.exists(src_main):
                # Mosquitto exe dizinine kopyala
                for exe_path in self.MOSQUITTO_EXE_PATHS:
                    dest_dir = os.path.dirname(exe_path)
                    if os.path.exists(dest_dir):
                        shutil.copy2(src_main, os.path.join(dest_dir, "mosquitto.conf"))
                        logger.info(f"mosquitto.conf kopyalandı: {dest_dir}")
                        break
            
            # Bridge config
            src_bridge = os.path.join(project_config_dir, "bridge_hivemq.conf")
            if os.path.exists(src_bridge):
                shutil.copy2(src_bridge, os.path.join(dest_conf_d, "bridge_hivemq.conf"))
                logger.info("bridge_hivemq.conf kopyalandı")
            
            return True
        except Exception as e:
            logger.error(f"Config kopyalama hatası: {e}")
            return False
