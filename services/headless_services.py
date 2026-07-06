from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from event_bus import EventPriority, get_event_bus


logger = logging.getLogger(__name__)


def _windows_creationflags() -> int:
    if platform.system() == "Windows" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        return subprocess.CREATE_NO_WINDOW
    return 0


def _run_command(args: list[str], timeout: int = 5) -> subprocess.CompletedProcess:
    kwargs: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "timeout": timeout,
        "encoding": "cp857",
        "errors": "replace",
    }
    flags = _windows_creationflags()
    if flags:
        kwargs["creationflags"] = flags
    return subprocess.run(args, **kwargs)


def get_local_ip() -> str:
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        if sock:
            try:
                sock.close()
            except Exception:
                pass


def get_hostname() -> str:
    try:
        return socket.gethostname() or "PEMF-Gateway"
    except Exception:
        return "PEMF-Gateway"


def _is_tcp_port_open(host: str, port: int, timeout: float = 2.0) -> bool:
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        return sock.connect_ex((host, int(port))) == 0
    except Exception:
        return False
    finally:
        if sock:
            try:
                sock.close()
            except Exception:
                pass


class MosquittoSupervisor:
    """Qt-free Mosquitto broker supervisor and status monitor."""

    MOSQUITTO_SERVICE_NAME = "mosquitto"
    MOSQUITTO_EXE_PATHS = [
        r"C:\Program Files\mosquitto\mosquitto.exe",
        r"C:\Program Files (x86)\mosquitto\mosquitto.exe",
        r"C:\mosquitto\mosquitto.exe",
    ]

    def __init__(
        self,
        *,
        port: int = 1883,
        interval_seconds: float = 10.0,
        ensure_running: bool = True,
        start_mdns: bool = True,
        event_bus=None,
    ) -> None:
        self.port = int(port)
        self.interval_seconds = float(interval_seconds)
        self.ensure_running = bool(ensure_running)
        self.start_mdns = bool(start_mdns)
        self.event_bus = event_bus or get_event_bus()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._mdns_service = None
        self._status_lock = threading.RLock()
        self._status: dict[str, Any] = {
            "installed": False,
            "running": False,
            "service_exists": False,
            "version": "",
            "port": self.port,
            "port_open": False,
            "pid": None,
            "exe_path": None,
            "mdns_running": False,
            "mdns_ip": None,
        }

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        if self.start_mdns:
            self._start_mdns()
        self._thread = threading.Thread(
            target=self._monitor_loop,
            name="MosquittoSupervisor",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        self._stop_mdns()

    def get_status(self) -> dict[str, Any]:
        with self._status_lock:
            status = dict(self._status)
        if self._mdns_service:
            try:
                status["mdns_running"] = self._mdns_service.is_running()
                status["mdns_ip"] = self._mdns_service.get_current_ip()
            except Exception:
                pass
        return status

    def check_once(self) -> dict[str, Any]:
        exe_path = self._find_mosquitto_exe()
        service = self._check_service_status()
        port_open = _is_tcp_port_open("127.0.0.1", self.port)
        installed = bool(exe_path or service.get("service_exists"))
        # YANLIS-OK FIX: bir Windows servisi KAYITLIYSA durumu OTORITERdir — yalniz "port acik"
        # (zombi/baska surec 1883'u tutuyor olabilir) "calisiyor" SAYILMASIN; yoksa cokmus broker
        # saglikli gorunup restart edilmez ve health yanlis raporlar. Servis yoksa (native Popen)
        # port_open tek gecerli sinyaldir.
        running = bool(service.get("running")) if service.get("service_exists") else port_open

        status = {
            "installed": installed,
            "running": running,
            "service_exists": bool(service.get("service_exists")),
            "version": self._read_version(exe_path) if exe_path else "",
            "port": self.port,
            "port_open": port_open,
            "pid": service.get("pid"),
            "exe_path": str(exe_path) if exe_path else None,
            "mdns_running": self._mdns_service.is_running() if self._mdns_service else False,
            "mdns_ip": self._mdns_service.get_current_ip() if self._mdns_service else None,
        }

        with self._status_lock:
            previous = dict(self._status)
            self._status.update(status)

        if previous.get("running") != status["running"] or previous.get("port_open") != status["port_open"]:
            self._publish("mqtt.broker.status", status)
        return status

    def start_broker(self) -> bool:
        """Broker'ı başlat: zaten çalışıyorsa çık → (Windows) servisi dene → doğrudan süreç başlat."""
        status = self.check_once()
        if status.get("running"):
            return True
        if self._try_start_windows_service(status):
            return True
        return self._launch_broker_process()

    def _try_start_windows_service(self, status: dict) -> bool:
        """Windows'ta mosquitto bir SERVİS olarak kuruluysa `net start` ile başlatmayı dene.
        Başlatabildiyse True; uygun değil/başarısızsa False (çağıran doğrudan sürece düşer)."""
        if platform.system() != "Windows" or not status.get("service_exists"):
            return False
        try:
            result = _run_command(["net", "start", self.MOSQUITTO_SERVICE_NAME], timeout=15)
            if result.returncode == 0:
                time.sleep(1)
                self.check_once()
                return True
            logger.warning("Mosquitto service start failed: %s", result.stderr.strip())
        except Exception as exc:
            logger.warning("Mosquitto service start failed: %s", exc)
        return False

    def _broker_popen_kwargs(self) -> dict[str, Any]:
        """Broker'ı arkaplanda AYRIK başlatmak için platforma-özgü Popen bayrakları
        (Windows: DETACHED_PROCESS; POSIX: start_new_session)."""
        kwargs: dict[str, Any] = {}
        if platform.system() == "Windows":
            flags = _windows_creationflags()
            if hasattr(subprocess, "DETACHED_PROCESS"):
                flags |= subprocess.DETACHED_PROCESS
            if flags:
                kwargs["creationflags"] = flags
        else:
            kwargs["start_new_session"] = True
        return kwargs

    def _launch_broker_process(self) -> bool:
        """mosquitto.exe'yi doğrudan (varsa yanındaki mosquitto.conf ile) AYRIK süreç olarak başlat."""
        exe_path = self._find_mosquitto_exe()
        if not exe_path:
            self._publish(
                "mqtt.broker.error",
                {"message": "Mosquitto executable or service was not found."},
                priority=EventPriority.HIGH,
            )
            return False

        args = [str(exe_path)]
        config_path = exe_path.parent / "mosquitto.conf"
        if config_path.exists():
            args.extend(["-c", str(config_path)])

        try:
            subprocess.Popen(args, **self._broker_popen_kwargs())
            time.sleep(1)
            self.check_once()
            return True
        except Exception as exc:
            logger.warning("Mosquitto process start failed: %s", exc)
            self._publish(
                "mqtt.broker.error",
                {"message": f"Mosquitto process start failed: {exc}"},
                priority=EventPriority.HIGH,
            )
            return False

    def _monitor_loop(self) -> None:
        fails = 0
        while not self._stop_event.is_set():
            try:
                status = self.check_once()
                if self.ensure_running and not status.get("running"):
                    # start_broker() Popen sonrasi True donebilir ama broker HEMEN olmus olabilir →
                    # check_once ile GERCEK durumu dogrula. Basarisizsa exponential backoff ile bekle
                    # (her interval'da yeni detached mosquitto.exe spawn edip churn/log-spam/proses
                    # yigilmasi YAPMA). Ust sinir ~5 dk; basarida sayac sifirlanir.
                    ok = self.start_broker() and bool(self.check_once().get("running"))
                    if ok:
                        fails = 0
                    else:
                        fails += 1
                        if fails == 1:
                            logger.warning("Mosquitto baslatilamadi; exponential backoff ile yeniden denenecek.")
                        wait = min(self.interval_seconds * (2 ** min(fails, 5)), 300.0)
                        self._stop_event.wait(wait)
                        continue
                else:
                    fails = 0
            except Exception as exc:
                logger.warning("Mosquitto monitor error: %s", exc)
            self._stop_event.wait(self.interval_seconds)

    def _find_mosquitto_exe(self) -> Optional[Path]:
        candidates: list[Path] = []
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidates.append(Path(appdata) / "PEMF_GUI" / "mosquitto" / "mosquitto.exe")

        if getattr(sys, "frozen", False):
            exe_dir = Path(sys.executable).resolve().parent
            candidates.append(exe_dir / "bin" / "mosquitto" / "mosquitto.exe")
            meipass = getattr(sys, "_MEIPASS", None)
            if meipass:
                candidates.append(Path(meipass) / "bin" / "mosquitto" / "mosquitto.exe")
        else:
            candidates.append(Path(__file__).resolve().parents[1] / "bin" / "mosquitto" / "mosquitto.exe")

        candidates.extend(Path(path) for path in self.MOSQUITTO_EXE_PATHS)

        path_in_env = shutil.which("mosquitto")
        if path_in_env:
            candidates.append(Path(path_in_env))

        for candidate in candidates:
            try:
                if candidate.exists():
                    return candidate
            except Exception:
                continue
        return None

    def _read_version(self, exe_path: Optional[Path]) -> str:
        if not exe_path:
            return ""
        try:
            result = _run_command([str(exe_path), "-h"], timeout=5)
            for line in (result.stdout + result.stderr).splitlines():
                if "version" in line.lower():
                    return line.strip()
        except Exception:
            pass
        return ""

    def _check_service_status(self) -> dict[str, Any]:
        data = {"service_exists": False, "running": False, "pid": None}
        if platform.system() == "Windows":
            try:
                result = _run_command(["sc", "query", self.MOSQUITTO_SERVICE_NAME], timeout=5)
                if result.returncode == 0:
                    data["service_exists"] = True
                    data["running"] = "RUNNING" in result.stdout
                    return data
            except Exception:
                pass

        if platform.system() == "Windows":
            try:
                result = _run_command(["tasklist", "/FI", "IMAGENAME eq mosquitto.exe", "/NH"], timeout=5)
                if "mosquitto.exe" in result.stdout:
                    data["running"] = True
                    parts = result.stdout.strip().split()
                    if len(parts) >= 2:
                        try:
                            data["pid"] = int(parts[1])
                        except ValueError:
                            pass
            except Exception:
                pass
        return data

    def _start_mdns(self) -> None:
        try:
            from services.mdns_service import MDNSService

            self._mdns_service = MDNSService(mqtt_port=self.port)
            self._mdns_service.start()
        except Exception as exc:
            logger.warning("MQTT mDNS could not start: %s", exc)

    def _stop_mdns(self) -> None:
        if not self._mdns_service:
            return
        try:
            self._mdns_service.stop()
        except Exception as exc:
            logger.warning("MQTT mDNS stop failed: %s", exc)
        finally:
            self._mdns_service = None

    def _publish(self, event_type: str, data: dict[str, Any], priority: EventPriority = EventPriority.NORMAL) -> None:
        try:
            self.event_bus.publish(event_type, data, priority=priority, source="mosquitto_supervisor")
        except Exception:
            logger.exception("Event publish failed: %s", event_type)


class NetworkStatusService:
    """Qt-free periodic network status monitor."""

    INTERNET_CHECK_HOSTS = [("8.8.8.8", 53), ("1.1.1.1", 53), ("208.67.222.222", 53)]
    HOTSPOT_SUBNET = "192.168.137."

    def __init__(self, *, interval_seconds: float = 5.0, mqtt_port: int = 1883, event_bus=None) -> None:
        self.interval_seconds = float(interval_seconds)
        self.mqtt_port = int(mqtt_port)
        self.event_bus = event_bus or get_event_bus()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._status_lock = threading.RLock()
        self._status: dict[str, Any] = {
            "internet_connected": False,
            "hotspot_active": False,
            "hotspot_ssid": "",
            "hotspot_ip": "192.168.137.1",
            "hotspot_clients": 0,
            "mqtt_broker_reachable": False,
            "mqtt_bridge_connected": False,
            "ethernet_ip": None,
            "wifi_ip": None,
            "gateway_mode": "unknown",
        }

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._monitor_loop, name="NetworkStatusService", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)

    def get_status(self) -> dict[str, Any]:
        with self._status_lock:
            return dict(self._status)

    def check_once(self) -> dict[str, Any]:
        hotspot = self._check_hotspot()
        ips = self._get_network_ips()
        status = {
            "internet_connected": self._check_internet(),
            "hotspot_active": hotspot.get("active", False),
            "hotspot_ssid": hotspot.get("ssid", ""),
            "hotspot_ip": hotspot.get("ip") or "192.168.137.1",
            "hotspot_clients": hotspot.get("clients", 0),
            "mqtt_broker_reachable": _is_tcp_port_open("127.0.0.1", self.mqtt_port),
            "mqtt_bridge_connected": self._status.get("mqtt_bridge_connected", False),
            "ethernet_ip": ips.get("ethernet"),
            "wifi_ip": ips.get("wifi"),
        }
        status["gateway_mode"] = self._determine_gateway_mode(status)

        with self._status_lock:
            previous = dict(self._status)
            self._status.update(status)

        if previous != status:
            self._publish("network.status", dict(self._status))
        return self.get_status()

    def _monitor_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.check_once()
            except Exception as exc:
                logger.warning("Network monitor error: %s", exc)
            self._stop_event.wait(self.interval_seconds)

    def _check_internet(self) -> bool:
        for host, port in self.INTERNET_CHECK_HOSTS:
            if _is_tcp_port_open(host, port, timeout=2.0):
                return True
        return False

    def _check_hotspot(self) -> dict[str, Any]:
        info = {"active": False, "ssid": "", "ip": "", "clients": 0}
        if platform.system() != "Windows":
            return info

        try:
            result = _run_command([
                "powershell",
                "-Command",
                "Get-NetIPAddress -AddressFamily IPv4 | "
                "Where-Object { $_.IPAddress -like '192.168.137.*' } | "
                "Select-Object -ExpandProperty IPAddress",
            ])
            if result.returncode == 0 and result.stdout.strip():
                info["active"] = True
                info["ip"] = result.stdout.strip().splitlines()[0].strip()

            arp_result = _run_command(["arp", "-a"])
            if arp_result.returncode == 0:
                info["clients"] = sum(
                    1
                    for line in arp_result.stdout.splitlines()
                    if self.HOTSPOT_SUBNET in line and "dynamic" in line.lower()
                )
        except Exception:
            pass
        return info

    def _get_network_ips(self) -> dict[str, Optional[str]]:
        ips: dict[str, Optional[str]] = {"ethernet": None, "wifi": None, "hotspot": None}
        if platform.system() != "Windows":
            local_ip = get_local_ip()
            if local_ip != "127.0.0.1":
                ips["wifi"] = local_ip
            return ips

        try:
            result = _run_command([
                "powershell",
                "-Command",
                "Get-NetIPAddress -AddressFamily IPv4 | "
                "Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } | "
                "Select-Object IPAddress, InterfaceAlias | Format-Table -HideTableHeaders",
            ])
            if result.returncode == 0:
                for line in result.stdout.strip().splitlines():
                    parts = line.strip().split(None, 1)
                    if len(parts) < 2:
                        continue
                    ip, iface = parts[0], parts[1].strip().lower()
                    if self.HOTSPOT_SUBNET in ip:
                        ips["hotspot"] = ip
                    elif "ethernet" in iface or "eth" in iface:
                        ips["ethernet"] = ip
                    elif "wi-fi" in iface or "wifi" in iface or "wlan" in iface:
                        ips["wifi"] = ip
        except Exception:
            pass
        return ips

    def _determine_gateway_mode(self, status: dict[str, Any]) -> str:
        if status.get("internet_connected") and status.get("hotspot_active"):
            return "online"
        if status.get("hotspot_active"):
            return "offline"
        if status.get("internet_connected"):
            return "hybrid"
        return "disconnected"

    def _publish(self, event_type: str, data: dict[str, Any]) -> None:
        try:
            self.event_bus.publish(event_type, data, source="network_status_service")
        except Exception:
            logger.exception("Event publish failed: %s", event_type)


class UdpDiscoveryService:
    """UDP broadcast discovery service for mobile clients."""

    def __init__(
        self,
        *,
        api_port: int = 8000,
        discovery_port: int = 5051,
        mqtt_port: int = 1883,
        event_bus=None,
        logger_instance: Optional[logging.Logger] = None,
    ) -> None:
        self.api_port = int(api_port)
        self.discovery_port = int(discovery_port)
        self.mqtt_port = int(mqtt_port)
        self.event_bus = event_bus or get_event_bus()
        self.logger = logger_instance or logger
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._socket: Optional[socket.socket] = None
        self._status_lock = threading.RLock()
        self._requests_handled = 0
        self._last_client_ip: Optional[str] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="UdpDiscoveryService", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)

    def get_status(self) -> dict[str, Any]:
        with self._status_lock:
            return {
                "running": self._thread.is_alive() if self._thread else False,
                "port": self.discovery_port,
                "requestsHandled": self._requests_handled,
                "lastClientIp": self._last_client_ip,
            }

    def _run(self) -> None:
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except Exception:
                pass
            self._socket.bind(("", self.discovery_port))
            self._socket.settimeout(1.0)
            self.logger.info("UDP discovery started on port %s", self.discovery_port)
            self._publish("discovery.started", self.get_status())

            while not self._stop_event.is_set():
                try:
                    data, addr = self._socket.recvfrom(2048)
                except socket.timeout:
                    continue
                except OSError:
                    break

                client_ip = addr[0]
                if not self._is_discovery_request(data):
                    continue

                response = self._create_response()
                self._socket.sendto(json.dumps(response, ensure_ascii=True).encode("utf-8"), addr)
                with self._status_lock:
                    self._requests_handled += 1
                    self._last_client_ip = client_ip
                self._publish("discovery.request", {"clientIp": client_ip, "response": response})
        except Exception as exc:
            self.logger.warning("UDP discovery failed: %s", exc)
            self._publish("discovery.error", {"message": str(exc)}, priority=EventPriority.HIGH)
        finally:
            if self._socket:
                try:
                    self._socket.close()
                except Exception:
                    pass
                self._socket = None
            self._publish("discovery.stopped", self.get_status())
            self.logger.info("UDP discovery stopped")

    def _is_discovery_request(self, data: bytes) -> bool:
        try:
            request = json.loads(data.decode("utf-8", errors="ignore"))
            return request.get("type") in {"discovery", "pemf_discovery"}
        except Exception:
            return False

    def _create_response(self) -> dict[str, Any]:
        local_ip = get_local_ip()
        base_url = f"http://{local_ip}:{self.api_port}"
        return {
            "type": "discovery_response",
            "service": "PEMF-Vet",
            "ip": local_ip,
            "hostname": get_hostname(),
            "timestamp": datetime.now().isoformat(),
            "version": "1.5",
            "api_port": self.api_port,
            "http_port": self.api_port,
            "websocket_port": self.api_port,
            "base_url": base_url,
            "api_url": f"{base_url}/api",
            "websocket_url": f"ws://{local_ip}:{self.api_port}/ws",
            "ports": [self.api_port],
            "mqtt_broker_host": local_ip,
            "mqtt_broker_port": self.mqtt_port,
            "mqtt_broker_tls": False,
            "gateway_mode": True,
        }

    def _publish(self, event_type: str, data: dict[str, Any], priority: EventPriority = EventPriority.NORMAL) -> None:
        try:
            self.event_bus.publish(event_type, data, priority=priority, source="udp_discovery")
        except Exception:
            self.logger.exception("Event publish failed: %s", event_type)
