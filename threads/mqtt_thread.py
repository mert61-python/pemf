import paho.mqtt.client as mqtt
import ssl
from PyQt6.QtCore import QThread, pyqtSignal

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
    
    def __init__(self, broker_url, broker_port, broker_user, broker_pass, logger, parent=None):
        super().__init__(parent)
        self.broker_url = broker_url
        self.broker_port = broker_port
        self.broker_user = broker_user
        self.broker_pass = broker_pass
        self.logger = logger
        self._stop_requested = False
    
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
                mqtt_client = mqtt.Client(
                    mqtt.CallbackAPIVersion.VERSION2, 
                    client_id="pemf_gui_client",
                    clean_session=False  # Session persistence: receive retained messages from before connection
                )
                
                # Kullanıcı adı ve şifre ayarla
                mqtt_client.username_pw_set(self.broker_user, self.broker_pass)
                
                # SSL/TLS yapılandırması (HiveMQ Cloud zorunlu TLS kullanır)
                mqtt_client.tls_set(
                    ca_certs=None,  # Sistem varsayılan CA sertifikalarını kullan
                    certfile=None,
                    keyfile=None,
                    cert_reqs=ssl.CERT_REQUIRED,
                    tls_version=ssl.PROTOCOL_TLSv1_2
                )
                
                # Client'ı ana thread'e gönder (callback'ler ana thread'de set edilecek)
                self.client_created.emit(mqtt_client)
                
                # HiveMQ Cloud'a bağlan (bloklayıcı işlem - bu thread'de çalışır)
                if self.logger:
                    self.logger.info(f"HiveMQ Cloud'a bağlanılıyor: {self.broker_url}:{self.broker_port} (deneme {attempt + 1}/{max_retries})")
                
                # Bloklayıcı connect çağrısı (bu thread'de çalıştığı için UI donmaz)
                mqtt_client.connect(self.broker_url, self.broker_port, 60)
                
                # Bağlantı başarılı, loop'u başlat
                mqtt_client.loop_start()
                
                if self.logger:
                    self.logger.info(f"MQTT istemcisi HiveMQ Cloud broker'a bağlanıyor...")
                
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
