import paho.mqtt.client as mqtt
import ssl
import uuid
import os
import json
import hashlib
from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal

try:
    from pemf_gui.config import get_config
except Exception:
    get_config = None

class MQTTConnectionThread(QThread):
    """
    MQTT bağlantısını ayrı bir thread'de yapan sınıf.
    Ana thread'i bloklamadan MQTT broker'a bağlanır.
    
    Kritik Düzeltme: Main thread bloklanmasını önlemek için oluşturuldu.
    """
    # Signal: MQTT client başarıyla oluşturulduğunda
    # Parametre: mqtt_client (mqtt.Client) - Oluşturulan MQTT client
    client_created = pyqtSignal(object)
    
    # Signal: Bağlantı başarılı olduğunda
    connection_success = pyqtSignal()
    
    # Signal: Bağlantı başarısız olduğunda
    # Parametre: error_message (str) - Hata mesajı
    connection_failed = pyqtSignal(str)
    
    # Signal: Retry denemesi yapılıyor
    # Parametre: attempt (int), max_retries (int)
    retry_attempt = pyqtSignal(int, int)
    
    def __init__(self, broker_url, broker_port, broker_user, broker_pass, use_tls, logger, parent=None, tls_ca_cert_path=None, tls_cert_sha256=None):
        super().__init__(parent)
        self.broker_url = broker_url
        self.broker_port = broker_port
        self.broker_user = broker_user
        self.broker_pass = broker_pass
        self.use_tls = use_tls  # TLS kullanilacak mi?
        self.logger = logger
        self._stop_requested = False
        self.tls_ca_cert_path = tls_ca_cert_path
        self.tls_cert_sha256 = tls_cert_sha256

    def _resolve_tls_ca_cert_path(self):
        config_ca = ""
        try:
            cfg_path = Path(__file__).resolve().parent.parent / "config" / "config.json"
            if cfg_path.exists():
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                config_ca = str(cfg.get("mqtt", {}).get("cloud_broker", {}).get("ca_cert_path", "") or "").strip()
        except Exception:
            config_ca = ""

        if config_ca:
            path = Path(config_ca)
            if path.exists():
                return str(path)

        if self.tls_ca_cert_path:
            path = Path(self.tls_ca_cert_path)
            if path.exists():
                return str(path)

        env_ca = os.getenv("PEMF_MQTT_CA_CERT", "").strip()
        if env_ca and Path(env_ca).exists():
            return env_ca

        bundled = Path(__file__).resolve().parent.parent / "config" / "certs" / "hivemq_root_ca.pem"
        if bundled.exists():
            return str(bundled)

        default_cafile = ssl.get_default_verify_paths().cafile
        if default_cafile and Path(default_cafile).exists():
            if self.logger:
                self.logger.warning("Gomulu HiveMQ CA bulunamadi, sistem CA bundle kullanilacak")
            return default_cafile

        raise RuntimeError(
            "TLS CA sertifikasi bulunamadi. PEMF_MQTT_CA_CERT ayarlayin veya config/certs/hivemq_root_ca.pem dosyasini ekleyin"
        )

    def _validate_certificate_pin(self, ca_cert_path):
        project_cfg_pin = ""
        try:
            cfg_path = Path(__file__).resolve().parent.parent / "config" / "config.json"
            if cfg_path.exists():
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                project_cfg_pin = str(cfg.get("mqtt", {}).get("cloud_broker", {}).get("tls_cert_sha256", "") or "")
        except Exception:
            project_cfg_pin = ""

        config_pin = ""
        if get_config is not None:
            try:
                config_pin = str(get_config().get("mqtt.cloud_broker.tls_cert_sha256", "") or "")
            except Exception:
                config_pin = ""

        expected_pin = (self.tls_cert_sha256 or config_pin or project_cfg_pin or os.getenv("PEMF_MQTT_CERT_SHA256", "")).strip().lower().replace(":", "")
        if not expected_pin:
            raise RuntimeError("TLS certificate pin eksik. Config'te mqtt.cloud_broker.tls_cert_sha256 veya PEMF_MQTT_CERT_SHA256 ayarlanmalidir")

        peer_pem = ssl.get_server_certificate((self.broker_url, int(self.broker_port)), ca_certs=ca_cert_path)
        peer_der = ssl.PEM_cert_to_DER_cert(peer_pem)
        actual_pin = hashlib.sha256(peer_der).hexdigest()

        if actual_pin != expected_pin:
            raise RuntimeError("TLS certificate pin dogrulamasi basarisiz")
    
    def stop(self):
        """Thread'i durdurma isteği gönderir"""
        self._stop_requested = True
    
    def run(self):
        """
        Thread'in ana çalışma metodu.
        MQTT client'ı oluşturur ve bağlanır (bloklayıcı işlemler burada yapılır).
        """
        max_retries = 3
        retry_delay = 2  # saniye
        
        for attempt in range(max_retries):
            # Durdurma isteği kontrolü
            if self._stop_requested:
                self.logger.info("MQTT bağlantı thread'i durduruldu")
                return
            
            try:
                # MQTT client oluştur
                # clean_session=False: Session persistence enabled (receive retained messages)
                # Android app behavior match: isCleanSession = false
                client_id = f"pemf_gui_{uuid.uuid4().hex[:8]}"
                mqtt_client = mqtt.Client(
                    mqtt.CallbackAPIVersion.VERSION2, 
                    client_id=client_id,
                    clean_session=False  # Session persistence: receive retained messages from before connection
                )
                
                # Kullanıcı adı ve şifre ayarla (varsa)
                if self.broker_user and self.broker_pass:
                    mqtt_client.username_pw_set(self.broker_user, self.broker_pass)
                
                # SSL/TLS yapılandırması (sadece cloud broker için)
                if self.use_tls:
                    ca_cert_path = self._resolve_tls_ca_cert_path()
                    self._validate_certificate_pin(ca_cert_path)
                    mqtt_client.tls_set(
                        ca_certs=ca_cert_path,
                        certfile=None,
                        keyfile=None,
                        cert_reqs=ssl.CERT_REQUIRED,
                        tls_version=ssl.PROTOCOL_TLSv1_2
                    )
                    mqtt_client.tls_insecure_set(False)
                
                # Client'i ana thread'e gonder (callback'ler ana thread'de set edilecek)
                self.client_created.emit(mqtt_client)
                
                # Broker'a baglan (bloklayici islem - bu thread'de calisir)
                broker_type = "Cloud Broker (HiveMQ)"
                if self.logger:
                    self.logger.info(f"{broker_type}'a baglaniliyor: {self.broker_url}:{self.broker_port} (deneme {attempt + 1}/{max_retries}, client_id={client_id})")
                
                # Bloklayici connect cagrisi (bu thread'de calistigi icin UI donmaz)
                mqtt_client.connect(self.broker_url, self.broker_port, 60)
                
                # Baglanti basarili, loop'u baslat
                mqtt_client.loop_start()
                
                if self.logger:
                    self.logger.info(f"MQTT istemcisi broker'a baglaniliyor...")
                
                # Başarılı bağlantı sinyali gönder
                self.connection_success.emit()
                return  # Başarılı, fonksiyondan çık
                
            except Exception as e:
                error_msg = f"MQTT istemci kurulumu başarısız (deneme {attempt + 1}/{max_retries}): {e}"
                if self.logger:
                    self.logger.warning(error_msg)
                
                # Retry denemesi sinyali gönder
                self.retry_attempt.emit(attempt + 1, max_retries)
                
                if attempt < max_retries - 1:
                    # QThread.msleep kullan (time.sleep yerine - thread-safe)
                    self.msleep(retry_delay * 1000)  # ms cinsinden
                else:
                    # Tüm denemeler başarısız
                    final_error = f"MQTT istemci kurulumu {max_retries} denemeden sonra başarısız oldu"
                    if self.logger:
                        self.logger.error(final_error)
                    self.connection_failed.emit(final_error)
