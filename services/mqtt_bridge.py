"""
Python MQTT Bridge — Local Mosquitto ↔ HiveMQ Cloud Bridge

Mosquitto 2.0.18 bridge TLS'in Windows'ta çalışmaması nedeniyle,
bu servis Python paho-mqtt ile aynı işlevi yerine getirir:

- Local Mosquitto (127.0.0.1:1883) ↔ HiveMQ Cloud (TLS:8883)
- Çift yönlü topic forwarding (pemf/# )
- Döngü önleme (bridged mesajları yeniden bridge etmez)
- Internet bağlantısı kesildiğinde graceful disconnect + retry
- Bridge durumu pemf/bridge/status topic'ine yayınlanır

Kullanım (standalone):
    python -m services.mqtt_bridge

Kullanım (GUI entegrasyon):
    bridge = MQTTBridge(config)
    bridge.start()
    ...
    bridge.stop()
"""

import sys
import ssl
import time
import json
import os
import socket
import logging
import threading
import uuid
import certifi
from typing import Optional, Dict, Set
from pathlib import Path

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)


def _load_bridge_credential() -> dict:
    """
    Bridge kredensiyelını çözümler. Öncelik sırası:
    1. CredentialManager (önerilir — PEMF_MASTER_SECRET varsa otomatik üretir)
    2. Ortam değişkenleri (PEMF_MQTT_USER, PEMF_MQTT_PASS)
    3. Düz metin fallback (üretim için uygun değil, WARN log’lar)
    """
    # 1. CredentialManager (en güvenli)
    try:
        from services.credential_manager import CredentialManager
        mgr = CredentialManager()
        cred = mgr.get_or_create_bridge_credential()
        return {"username": cred.username, "password": cred.password}
    except Exception:
        pass  # CredentialManager yoksa veya başarhanımadsızsa bir sonraki yola geç

    # 2. Ortam değişkenleri
    env_user = os.environ.get("PEMF_MQTT_USER", "").strip()
    env_pass = os.environ.get("PEMF_MQTT_PASS", "").strip()
    if env_user and env_pass:
        return {"username": env_user, "password": env_pass}

    # 3. Fallback — üretim için uygun değil
    logger.warning(
        "[Bridge] Gelişmiş kimlik doğrulama bulunamadı! "
        "Lütfen PEMF_MASTER_SECRET veya PEMF_MQTT_USER/PEMF_MQTT_PASS "
        "ortam değişkenlerini ayarlayın."
    )
    return {"username": "gui_bridge", "password": ""}


_bridge_cred = _load_bridge_credential()

# Varsayılan yapılandırma
# Credentials: CredentialManager veya ortam değişkeni üzerinden yüklenir (yukarıda)
DEFAULT_CONFIG = {
    "local_broker": {
        "host": "127.0.0.1",
        "port": 1883,
        "use_tls": False,
        "username": "",
        "password": "",
    },
    "cloud_broker": {
        "host": "8593bfdb2f324ad88d08b54b5e37c0a9.s1.eu.hivemq.cloud",
        "port": 8883,
        "use_tls": True,
        "username": _bridge_cred["username"],   # CredentialManager üzerinden
        "password": _bridge_cred["password"],   # Hiçbir zaman kaynak kodda sabit değil
    },
    "topics": ["pemf/#"],
    "bridge_qos": 1,
    "bridge_status_topic": "pemf/bridge/status",
    "keepalive": 60,
    "reconnect_min_delay": 5,
    "reconnect_max_delay": 60,
    "internet_check_interval": 30,
}


class MQTTBridge:
    """
    Bidirectional MQTT bridge between local Mosquitto and HiveMQ Cloud.

    Thread-safe. Runs background threads for local/cloud connections.
    Publishes bridge status ('1'/'0') to local broker.
    """

    # Özel header: bridged mesajları işaretlemek için
    _BRIDGE_MARKER = "_bridged"

    def __init__(self, config: Optional[Dict] = None):
        self._config = {**DEFAULT_CONFIG, **(config or {})}

        # Client'lar
        self._local_client: Optional[mqtt.Client] = None
        self._cloud_client: Optional[mqtt.Client] = None

        # Durum
        self._running = False
        self._local_connected = False
        self._cloud_connected = False
        self._bridge_active = False
        self._stop_event = threading.Event()

        # Döngü önleme: son bridge edilen mesaj ID'leri
        self._forwarded_messages: Set[str] = set()
        self._forwarded_lock = threading.Lock()
        self._max_forwarded_cache = 500

        # İstatistikler
        self._stats = {
            "local_to_cloud": 0,
            "cloud_to_local": 0,
            "errors": 0,
            "reconnects": 0,
            "last_forward_time": None,
        }

        # Internet durumu kontrolü
        self._internet_available = False
        self._internet_check_thread: Optional[threading.Thread] = None

    # ─── PUBLIC API ───────────────────────────────────────────────

    def start(self):
        """Bridge'i başlat"""
        if self._running:
            logger.warning("MQTT Bridge zaten çalışıyor")
            return

        logger.info("MQTT Bridge başlatılıyor...")
        self._running = True
        self._stop_event.clear()

        # Local client'ı oluştur ve bağlan
        self._setup_local_client()
        self._local_client.loop_start()

        # Cloud bağlantısı internet durumuna bağlı
        self._setup_cloud_client()

        # Internet kontrol thread'i
        self._internet_check_thread = threading.Thread(
            target=self._internet_check_loop,
            name="MQTTBridge-InternetCheck",
            daemon=True,
        )
        self._internet_check_thread.start()

        logger.info("MQTT Bridge başlatıldı")

    def stop(self):
        """Bridge'i durdur"""
        if not self._running:
            return

        logger.info("MQTT Bridge durduruluyor...")
        self._running = False
        self._stop_event.set()

        # Bridge durumunu yayınla
        self._publish_bridge_status(False)

        # Client'ları kapat
        if self._cloud_client:
            try:
                self._cloud_client.loop_stop()
                self._cloud_client.disconnect()
            except Exception:
                pass

        if self._local_client:
            try:
                self._local_client.loop_stop()
                self._local_client.disconnect()
            except Exception:
                pass

        self._local_connected = False
        self._cloud_connected = False
        self._bridge_active = False

        logger.info("MQTT Bridge durduruldu")

    def is_running(self) -> bool:
        return self._running

    def is_bridge_active(self) -> bool:
        """Hem local hem cloud bağlı mı?"""
        return self._bridge_active

    def get_stats(self) -> Dict:
        """Bridge istatistikleri"""
        return {
            **self._stats,
            "running": self._running,
            "local_connected": self._local_connected,
            "cloud_connected": self._cloud_connected,
            "bridge_active": self._bridge_active,
            "internet_available": self._internet_available,
        }

    # ─── LOCAL CLIENT ─────────────────────────────────────────────

    def _setup_local_client(self):
        """Local Mosquitto client'ını yapılandır"""
        cfg = self._config["local_broker"]

        self._local_client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"pymqtt-bridge-local-{uuid.uuid4().hex[:8]}",
            clean_session=True,
            protocol=mqtt.MQTTv311,
        )

        if cfg.get("username"):
            self._local_client.username_pw_set(cfg["username"], cfg.get("password", ""))

        self._local_client.on_connect = self._on_local_connect
        self._local_client.on_disconnect = self._on_local_disconnect
        self._local_client.on_message = self._on_local_message

        self._local_client.reconnect_delay_set(
            min_delay=self._config["reconnect_min_delay"],
            max_delay=self._config["reconnect_max_delay"],
        )

        try:
            self._local_client.connect(
                cfg["host"], cfg["port"],
                keepalive=self._config["keepalive"],
            )
        except Exception as e:
            logger.error(f"Local broker bağlantı hatası: {e}")

    def _on_local_connect(self, client, userdata, flags, reason_code, properties=None):
        """Local broker'a bağlandığında"""
        if reason_code == 0:
            self._local_connected = True
            logger.info(f"Local broker bağlandı: {self._config['local_broker']['host']}:{self._config['local_broker']['port']}")

            # Baslangicta retained stale durumu temizlemek icin bridge'i pasif olarak yayinla.
            # Cloud baglaninca _update_bridge_state() aktif durumu tekrar yayinlar.
            self._publish_bridge_status(False)

            # Topic'lere subscribe ol
            for topic in self._config["topics"]:
                client.subscribe(topic, qos=self._config["bridge_qos"])
                logger.info(f"Local subscribe: {topic}")

            self._update_bridge_state()
        else:
            logger.error(f"Local broker bağlantı hatası: rc={reason_code}")
            self._local_connected = False

    def _on_local_disconnect(self, client, userdata, flags, reason_code, properties=None):
        """Local broker bağlantısı kesildiğinde"""
        self._local_connected = False
        self._update_bridge_state()
        if self._running:
            logger.warning(f"Local broker bağlantısı kesildi (rc={reason_code}), yeniden bağlanıyor...")

    def _on_local_message(self, client, userdata, msg):
        """Local broker'dan mesaj geldiğinde → Cloud'a ilet"""
        try:
            # Bridge status kendi mesajımız, iletme
            if msg.topic == self._config["bridge_status_topic"]:
                return

            # Döngü önleme: zaten cloud'dan gelen mesajı tekrar gönderme
            msg_id = f"c2l:{msg.topic}:{hash(msg.payload)}"
            with self._forwarded_lock:
                if msg_id in self._forwarded_messages:
                    self._forwarded_messages.discard(msg_id)
                    return

            # Cloud'a ilet
            if self._cloud_connected and self._cloud_client:
                # Döngü önleme marker ekle
                fwd_id = f"l2c:{msg.topic}:{hash(msg.payload)}"
                with self._forwarded_lock:
                    self._forwarded_messages.add(fwd_id)
                    # Cache boyutunu sınırla
                    if len(self._forwarded_messages) > self._max_forwarded_cache:
                        # En eski yarısını sil
                        to_remove = list(self._forwarded_messages)[: self._max_forwarded_cache // 2]
                        for item in to_remove:
                            self._forwarded_messages.discard(item)

                result = self._cloud_client.publish(
                    msg.topic, msg.payload,
                    qos=min(msg.qos, self._config["bridge_qos"]),
                    retain=msg.retain,
                )

                if result.rc == mqtt.MQTT_ERR_SUCCESS:
                    self._stats["local_to_cloud"] += 1
                    self._stats["last_forward_time"] = time.time()
                    logger.debug(f"L→C: {msg.topic} ({len(msg.payload)}B)")
                else:
                    self._stats["errors"] += 1
                    logger.warning(f"L→C gönderim hatası: {msg.topic}, rc={result.rc}")

        except Exception as e:
            self._stats["errors"] += 1
            logger.error(f"Local mesaj işleme hatası: {e}")

    # ─── CLOUD CLIENT ─────────────────────────────────────────────

    def _setup_cloud_client(self):
        """HiveMQ Cloud client'ını yapılandır"""
        cfg = self._config["cloud_broker"]

        self._cloud_client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"pymqtt-bridge-cloud-{uuid.uuid4().hex[:8]}",
            clean_session=False,  # Offline mesajları almak için
            protocol=mqtt.MQTTv311,
        )

        # Authentication
        if cfg.get("username"):
            self._cloud_client.username_pw_set(cfg["username"], cfg.get("password", ""))

        # TLS
        if cfg.get("use_tls", True):
            self._cloud_client.tls_set(
                ca_certs=certifi.where(),
                certfile=None,
                keyfile=None,
                cert_reqs=ssl.CERT_REQUIRED,
                tls_version=ssl.PROTOCOL_TLSv1_2,
            )

        self._cloud_client.on_connect = self._on_cloud_connect
        self._cloud_client.on_disconnect = self._on_cloud_disconnect
        self._cloud_client.on_message = self._on_cloud_message

        self._cloud_client.reconnect_delay_set(
            min_delay=self._config["reconnect_min_delay"],
            max_delay=self._config["reconnect_max_delay"],
        )

    def _connect_cloud(self):
        """Cloud broker'a bağlan (internet varsa)"""
        if not self._cloud_client or self._cloud_connected:
            return

        cfg = self._config["cloud_broker"]
        try:
            logger.info(f"Cloud broker'a bağlanılıyor: {cfg['host']}:{cfg['port']}")
            self._cloud_client.connect(
                cfg["host"], cfg["port"],
                keepalive=self._config["keepalive"],
            )
            self._cloud_client.loop_start()
        except Exception as e:
            logger.error(f"Cloud broker bağlantı hatası: {e}")
            self._stats["errors"] += 1

    def _disconnect_cloud(self):
        """Cloud broker'dan bağlantıyı kes"""
        if self._cloud_client:
            try:
                self._cloud_client.loop_stop()
                self._cloud_client.disconnect()
            except Exception:
                pass
        self._cloud_connected = False
        self._update_bridge_state()

    def _on_cloud_connect(self, client, userdata, flags, reason_code, properties=None):
        """Cloud broker'a bağlandığında"""
        if reason_code == 0:
            self._cloud_connected = True
            logger.info(f"Cloud broker bağlandı: {self._config['cloud_broker']['host']}:{self._config['cloud_broker']['port']}")

            # Topic'lere subscribe ol
            for topic in self._config["topics"]:
                client.subscribe(topic, qos=self._config["bridge_qos"])
                logger.info(f"Cloud subscribe: {topic}")

            self._update_bridge_state()
            self._stats["reconnects"] += 1
        else:
            logger.error(f"Cloud broker bağlantı hatası: rc={reason_code}")
            self._cloud_connected = False

    def _on_cloud_disconnect(self, client, userdata, flags, reason_code, properties=None):
        """Cloud broker bağlantısı kesildiğinde"""
        was_connected = self._cloud_connected
        self._cloud_connected = False
        self._update_bridge_state()
        if self._running and was_connected:
            logger.warning(f"Cloud broker bağlantısı kesildi (rc={reason_code})")

    def _on_cloud_message(self, client, userdata, msg):
        """Cloud broker'dan mesaj geldiğinde → Local'e ilet"""
        try:
            # Retained mesajları filtrele (ESP hayalet widget sorunu için)
            # Eğer Cloud'dan gelen mesaj 'retained' ise ve bir bobine aitse, 
            # bunu Local'e iletme çünkü GUI bunu yeni bir mesajmış gibi (retain=0) görüyor.
            is_retained = getattr(msg, 'retain', False)
            if is_retained and msg.topic.startswith('pemf/coil/'):
                logger.debug(f"C->L İptal: Cloud'dan gelen retained mesaj yoksayıldı ({msg.topic})")
                return

            # Döngü önleme: zaten local'den gelen mesajı tekrar gönderme
            msg_id = f"l2c:{msg.topic}:{hash(msg.payload)}"
            with self._forwarded_lock:
                if msg_id in self._forwarded_messages:
                    self._forwarded_messages.discard(msg_id)
                    return

            # Local'e ilet
            if self._local_connected and self._local_client:
                # Döngü önleme marker ekle
                fwd_id = f"c2l:{msg.topic}:{hash(msg.payload)}"
                with self._forwarded_lock:
                    self._forwarded_messages.add(fwd_id)
                    if len(self._forwarded_messages) > self._max_forwarded_cache:
                        to_remove = list(self._forwarded_messages)[: self._max_forwarded_cache // 2]
                        for item in to_remove:
                            self._forwarded_messages.discard(item)

                result = self._local_client.publish(
                    msg.topic, msg.payload,
                    qos=min(msg.qos, self._config["bridge_qos"]),
                    retain=msg.retain,
                )

                if result.rc == mqtt.MQTT_ERR_SUCCESS:
                    self._stats["cloud_to_local"] += 1
                    self._stats["last_forward_time"] = time.time()
                    logger.debug(f"C→L: {msg.topic} ({len(msg.payload)}B)")
                else:
                    self._stats["errors"] += 1
                    logger.warning(f"C→L gönderim hatası: {msg.topic}, rc={result.rc}")

        except Exception as e:
            self._stats["errors"] += 1
            logger.error(f"Cloud mesaj işleme hatası: {e}")

    # ─── BRIDGE STATE ─────────────────────────────────────────────

    def _update_bridge_state(self):
        """Bridge durumunu değerlendir ve yayınla"""
        was_active = self._bridge_active
        self._bridge_active = self._local_connected and self._cloud_connected

        if self._bridge_active != was_active:
            self._publish_bridge_status(self._bridge_active)
            if self._bridge_active:
                logger.info("✓ Bridge AKTIF — Local ↔ Cloud mesaj iletimi başladı")
            else:
                logger.info("✗ Bridge PASIF — " +
                           ("Local bağlı değil" if not self._local_connected else "") +
                           (" | " if not self._local_connected and not self._cloud_connected else "") +
                           ("Cloud bağlı değil" if not self._cloud_connected else ""))

    def _publish_bridge_status(self, connected: bool):
        """Bridge durumunu local broker'a yayınla"""
        if self._local_connected and self._local_client:
            try:
                status_payload = "1" if connected else "0"
                self._local_client.publish(
                    self._config["bridge_status_topic"],
                    status_payload,
                    qos=1,
                    retain=True,
                )
            except Exception as e:
                logger.error(f"Bridge status yayınlama hatası: {e}")

    # ─── INTERNET CHECK ──────────────────────────────────────────

    def _check_internet(self) -> bool:
        """Internet bağlantısını kontrol et (DNS + TCP)"""
        # Hızlı DNS check
        test_hosts = [
            ("8.8.8.8", 53),          # Google DNS
            ("1.1.1.1", 53),          # Cloudflare DNS
        ]
        for host, port in test_hosts:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(3)
                sock.connect((host, port))
                sock.close()
                return True
            except (socket.timeout, OSError):
                continue
        return False

    def _internet_check_loop(self):
        """İnternet durumunu periyodik kontrol et"""
        logger.info("Internet kontrol döngüsü başlatıldı")
        cloud_loop_started = False

        while not self._stop_event.is_set():
            try:
                internet_now = self._check_internet()

                if internet_now and not self._internet_available:
                    # Internet geldi → Cloud'a bağlan
                    logger.info("Internet bağlantısı tespit edildi, Cloud bridge başlatılıyor...")
                    self._internet_available = True
                    if not cloud_loop_started:
                        self._connect_cloud()
                        cloud_loop_started = True
                    else:
                        # Reconnect
                        try:
                            self._cloud_client.reconnect()
                        except Exception:
                            self._disconnect_cloud()
                            self._setup_cloud_client()
                            self._connect_cloud()
                            cloud_loop_started = True

                elif not internet_now and self._internet_available:
                    # Internet gitti → Cloud'u kes
                    logger.warning("Internet bağlantısı kesildi, Cloud bridge durduruluyor...")
                    self._internet_available = False
                    # Cloud reconnect döngüsünü durdur ama tamamen kapatma
                    # paho zaten reconnect deneyecek

                # Cloud bağlı değilse ve internet varsa, tekrar dene
                if (internet_now and not self._cloud_connected
                        and self._running and cloud_loop_started):
                    try:
                        self._cloud_client.reconnect()
                    except Exception as e:
                        logger.debug(f"Cloud reconnect hatası: {e}")
                        # Tam reset
                        try:
                            self._cloud_client.loop_stop()
                        except Exception:
                            pass
                        self._setup_cloud_client()
                        self._connect_cloud()
                        cloud_loop_started = True

            except Exception as e:
                logger.error(f"Internet kontrol hatası: {e}")

            # Bekleme (stop_event ile kesilebilir)
            self._stop_event.wait(self._config["internet_check_interval"])

        logger.info("Internet kontrol döngüsü sonlandı")

    # ─── CONFIG LOADER ────────────────────────────────────────────

    @staticmethod
    def load_config_from_file(config_path: str) -> Dict:
        """config.json dosyasından bridge yapılandırmasını yükle"""
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            mqtt_cfg = data.get("mqtt", {})
            local = mqtt_cfg.get("local_broker", {})
            cloud = mqtt_cfg.get("cloud_broker", {})

            return {
                "local_broker": {
                    "host": local.get("broker_url", "127.0.0.1"),
                    "port": local.get("broker_port", 1883),
                    "use_tls": local.get("use_tls", False),
                    "username": local.get("username", ""),
                    "password": local.get("password", ""),
                },
                "cloud_broker": {
                    "host": cloud.get("broker_url") or DEFAULT_CONFIG["cloud_broker"]["host"],
                    "port": cloud.get("broker_port", 8883),
                    "use_tls": cloud.get("use_tls", True),
                    "username": cloud.get("username") or DEFAULT_CONFIG["cloud_broker"]["username"],
                    "password": cloud.get("password") or DEFAULT_CONFIG["cloud_broker"]["password"],
                },
                "bridge_status_topic": mqtt_cfg.get("bridge_status_topic", "pemf/bridge/status"),
                "topics": ["pemf/#"],
                "bridge_qos": 1,
                "keepalive": 60,
                "reconnect_min_delay": 5,
                "reconnect_max_delay": 60,
                "internet_check_interval": 30,
            }
        except Exception as e:
            logger.error(f"Config yükleme hatası: {e}, varsayılan değerler kullanılacak")
            return dict(DEFAULT_CONFIG)


# ─── STANDALONE ÇALIŞTIRMA ────────────────────────────────────────

def _setup_logging():
    """Servis ve standalone mod için logging ayarla (absolute log path)."""
    import logging.handlers as _lh

    log_dir = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "PEMF_System" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "mqtt_bridge_service.log"

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Dönen dosya (10 MB × 5)
    fh = _lh.RotatingFileHandler(str(log_file), maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # Konsol (servis yoksa terminale)
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    return str(log_file)


def main():
    """Standalone / Windows Servisi olarak çalıştırma."""
    import signal

    # sys.path: servis modunda çalışırken gui root'u ekle
    _gui_root = str(Path(__file__).parent.parent)
    if _gui_root not in sys.path:
        sys.path.insert(0, _gui_root)

    log_file = _setup_logging()

    logger.info("=" * 55)
    logger.info("PEMF MQTT Bridge — Baslatiliyor")
    logger.info(f"Log: {log_file}")
    logger.info("=" * 55)

    # Config yükle (ProductionConfigManager kullan)
    try:
        from utils.production_config_manager import get_production_config
        prod_config = get_production_config()
        config_path = prod_config.get_user_config_path()
        if not config_path.exists():
            # Eğer APPDATA'da config yoksa, template fallback'inden yararlanarak geçici oluştur
            prod_config.save()
            
        if config_path.exists():
            config = MQTTBridge.load_config_from_file(str(config_path))
            logger.info(f"Config yüklendi: {config_path}")
        else:
            config = None
            logger.warning(f"Config oluşturulamadı: {config_path}")
    except Exception as e:
        config = None
        logger.warning(f"Production config yüklenemedi: {e}, varsayılan değerler kullanılıyor")

    # Bridge başlat
    bridge = MQTTBridge(config)
    bridge.start()

    logger.info("Bridge calisiyor. Durdurmak icin Ctrl+C.")

    # Graceful shutdown (SIGTERM: Windows servis durdurma sinyali)
    def _shutdown(signum, frame):
        logger.info(f"Sinyal alindi ({signum}), bridge durduruluyor...")
        bridge.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        while True:
            time.sleep(60)
            stats = bridge.get_stats()
            logger.info(
                f"[Heartbeat] Aktif: {stats['bridge_active']} | "
                f"L->C: {stats['local_to_cloud']} | "
                f"C->L: {stats['cloud_to_local']} | "
                f"Hatalar: {stats['errors']} | "
                f"Reconnect: {stats['reconnects']}"
            )
    except KeyboardInterrupt:
        logger.info("Ctrl+C alindi, bridge durduruluyor...")
        bridge.stop()
        logger.info("Bridge durduruldu.")


if __name__ == "__main__":
    main()
