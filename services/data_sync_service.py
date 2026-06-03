"""
Data Sync Service - Offline veri önbelleği ve bulut senkronizasyon servisi.

LattePanda gateway senaryosunda:
- Internet yokken: MQTT mesajlarını yerel SQLite'a kaydeder
- Internet geldiğinde: Biriken veriyi cloud broker'a (HiveMQ) publish eder
- Senkronizasyon durumunu takip eder

Mesaj tipleri:
- Sensor verileri (pemf/coil/+/sensors)
- Treatment session verileri (pemf/system/session)
- ESP durum verileri (pemf/coil/+/status)
"""

import json
import logging
import sqlite3
import time
import threading
from pathlib import Path
from typing import Optional, Dict

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from database.treatment_history_db import get_treatment_db
from utils.path_utils import get_app_data_directory

logger = logging.getLogger(__name__)

# Default sync config
SYNC_DB_PATH = Path(__file__).parent.parent / "data" / "sync_queue.db"
SYNC_CHECK_INTERVAL_MS = 30_000  # 30 saniyede bir sync dene
MAX_BATCH_SIZE = 100  # Bir seferde max mesaj
MAX_QUEUE_AGE_HOURS = 72  # 72 saatten eski mesajları sil
MAX_RETRY_COUNT = 20
INFLIGHT_STALE_SECONDS = 120
PUBLISH_ACK_TIMEOUT_SECONDS = 3.0


class DataSyncService(QObject):
    """
    Offline-first veri senkronizasyon servisi.
    
    Signals:
        sync_started: Senkronizasyon başladı
        sync_completed(int): Senkronizasyon tamamlandı (senkronize edilen mesaj sayısı)
        sync_failed(str): Senkronizasyon hatası
        queue_size_changed(int): Kuyruk boyutu değişti
    """
    
    sync_started = pyqtSignal()
    sync_completed = pyqtSignal(int)  # synced_count
    sync_failed = pyqtSignal(str)  # error_message
    queue_size_changed = pyqtSignal(int)  # queue_size
    
    def __init__(self, db_path: Optional[Path] = None, app_data_dir: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self._db_path = db_path or SYNC_DB_PATH
        self._db_lock = threading.Lock()
        self._mqtt_client = None  # Cloud MQTT client (set externally)
        self._is_online = False
        self._use_unified_outbox = False
        self._unified_db = None

        # Runtime sync tuning (config/config.json -> performance.sync)
        self._sync_check_interval_ms = SYNC_CHECK_INTERVAL_MS
        self._max_batch_size = MAX_BATCH_SIZE
        self._max_queue_age_hours = MAX_QUEUE_AGE_HOURS
        self._max_retry_count = MAX_RETRY_COUNT
        self._inflight_stale_seconds = INFLIGHT_STALE_SECONDS
        self._publish_ack_timeout_seconds = PUBLISH_ACK_TIMEOUT_SECONDS
        self._batch_pacing_ms = 0
        self._apply_performance_config()
        
        # Sync timer
        self._sync_timer = QTimer(self)
        self._sync_timer.timeout.connect(self._try_sync)

        # Öncelik: unified local DB (pemf_gateway/pemf_treatment_history)
        try:
            resolved_app_data_dir = app_data_dir or get_app_data_directory()
            self._unified_db = get_treatment_db(resolved_app_data_dir)
            self._use_unified_outbox = True
            logger.info("DataSyncService unified outbox mode aktif")
        except Exception as e:
            logger.warning(f"Unified outbox başlatılamadı, legacy sync_queue kullanılacak: {e}")
            self._use_unified_outbox = False

        # Fallback DB başlat
        if not self._use_unified_outbox:
            self._init_db()

    def _apply_performance_config(self):
        """Sync performans ayarlarını merkezi config dosyasından yükle."""
        try:
            config_path = Path(__file__).resolve().parent.parent / "config" / "config.json"
            with open(config_path, 'r', encoding='utf-8') as handle:
                cfg = json.load(handle)

            sync_cfg = cfg.get('performance', {}).get('sync', {})
            self._sync_check_interval_ms = max(1000, int(sync_cfg.get('check_interval_ms', self._sync_check_interval_ms)))
            self._max_batch_size = max(1, int(sync_cfg.get('max_batch_size', self._max_batch_size)))
            self._max_queue_age_hours = max(1, int(sync_cfg.get('max_queue_age_hours', self._max_queue_age_hours)))
            self._max_retry_count = max(1, int(sync_cfg.get('max_retry_count', self._max_retry_count)))
            self._inflight_stale_seconds = max(5, int(sync_cfg.get('inflight_stale_seconds', self._inflight_stale_seconds)))
            self._publish_ack_timeout_seconds = max(0.1, float(sync_cfg.get('publish_ack_timeout_seconds', self._publish_ack_timeout_seconds)))
            self._batch_pacing_ms = max(0, min(200, int(sync_cfg.get('batch_pacing_ms', self._batch_pacing_ms))))

            logger.info(
                "DataSyncService config: interval=%dms, batch=%d, max_retry=%d",
                self._sync_check_interval_ms,
                self._max_batch_size,
                self._max_retry_count,
            )
        except Exception as e:
            logger.warning(f"DataSyncService performance config yüklenemedi, default kullanılacak: {e}")
    
    def _init_db(self):
        """SQLite veritabanını oluştur."""
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            with self._db_lock:
                conn = sqlite3.connect(str(self._db_path))
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS sync_queue (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        topic TEXT NOT NULL,
                        payload TEXT NOT NULL,
                        qos INTEGER DEFAULT 0,
                        retain INTEGER DEFAULT 0,
                        timestamp REAL NOT NULL,
                        synced INTEGER DEFAULT 0,
                        sync_time REAL DEFAULT NULL
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_sync_queue_synced 
                    ON sync_queue(synced, timestamp)
                """)
                conn.commit()
                conn.close()
            logger.info(f"Sync DB initialized: {self._db_path}")
        except Exception as e:
            logger.error(f"Sync DB init error: {e}")
    
    def start(self):
        """Senkronizasyon servisini başlat."""
        self._sync_timer.start(self._sync_check_interval_ms)
        logger.info("DataSyncService started")
    
    def stop(self):
        """Senkronizasyon servisini durdur."""
        self._sync_timer.stop()
        logger.info("DataSyncService stopped")
    
    def set_mqtt_client(self, client):
        """Cloud MQTT client ayarla (senkronizasyon için)."""
        self._mqtt_client = client
    
    def set_online_status(self, is_online: bool):
        """Internet durumunu güncelle."""
        was_offline = not self._is_online
        self._is_online = is_online
        
        # Offline → Online geçiş: Hemen sync dene
        if was_offline and is_online:
            logger.info("Internet geldi, senkronizasyon tetikleniyor...")
            self._try_sync()
    
    def queue_message(self, topic: str, payload: str, qos: int = 0, retain: bool = False,
                     idempotency_key: Optional[str] = None, correlation_id: Optional[str] = None):
        """
        Mesajı senkronizasyon kuyruğuna ekle.
        Unified outbox modunda daima önce DB'ye yazar (outbox-first),
        online ise hemen sync denemesi yapar.
        
        Args:
            topic: MQTT topic
            payload: JSON payload string
            qos: Quality of Service (0, 1, 2)
            retain: Retain flag
        """
        # Unified outbox mode: her durumda önce local DB'ye yaz (durability)
        try:
            if self._use_unified_outbox and self._unified_db is not None:
                self._unified_db.enqueue_outbox_message(
                    topic=topic,
                    payload=payload,
                    qos=qos,
                    retain=retain,
                    source='data_sync_service',
                    correlation_id=correlation_id,
                    idempotency_key=idempotency_key
                )
                self.queue_size_changed.emit(self._unified_db.get_pending_outbox_count())

                # Online ise hemen göndermeyi dene
                if self._is_online and self._mqtt_client:
                    self._sync_unified_outbox()
                return

            # Legacy mode: online ise direkt gönder, olmazsa local queue'ya al
            if self._is_online and self._mqtt_client:
                try:
                    self._publish_with_confirmation(topic, payload, qos=qos, retain=retain)
                    return
                except Exception:
                    pass

            with self._db_lock:
                conn = sqlite3.connect(str(self._db_path))
                conn.execute(
                    "INSERT INTO sync_queue (topic, payload, qos, retain, timestamp) VALUES (?, ?, ?, ?, ?)",
                    (topic, payload, qos, int(retain), time.time())
                )
                conn.commit()
                
                # Queue size güncelle
                cursor = conn.execute("SELECT COUNT(*) FROM sync_queue WHERE synced = 0")
                queue_size = cursor.fetchone()[0]
                conn.close()
                
            self.queue_size_changed.emit(queue_size)
        except Exception as e:
            logger.error(f"Queue message error: {e}")

    def force_sync_now(self) -> bool:
        """Dışarıdan manuel sync tetiklemesi için helper."""
        if not self._mqtt_client:
            return False

        try:
            if self._use_unified_outbox and self._unified_db is not None:
                self._sync_unified_outbox()
            else:
                self._try_sync()
            return True
        except Exception as e:
            logger.error(f"force_sync_now error: {e}")
            return False
    
    def _try_sync(self):
        """Kuyruktaki mesajları cloud broker'a göndermeyi dene."""
        if not self._is_online:
            return
        
        if not self._mqtt_client:
            return
        
        try:
            if self._use_unified_outbox and self._unified_db is not None:
                self._sync_unified_outbox()
                return

            with self._db_lock:
                conn = sqlite3.connect(str(self._db_path))
                
                # Eski mesajları temizle
                cutoff_time = time.time() - (self._max_queue_age_hours * 3600)
                conn.execute("DELETE FROM sync_queue WHERE timestamp < ?", (cutoff_time,))
                
                # Sync edilmemiş mesajları al
                cursor = conn.execute(
                    "SELECT id, topic, payload, qos, retain FROM sync_queue WHERE synced = 0 ORDER BY timestamp ASC LIMIT ?",
                    (self._max_batch_size,)
                )
                messages = cursor.fetchall()
                conn.close()
            
            if not messages:
                return
            
            self.sync_started.emit()
            synced_count = 0
            failed_ids = []
            successful_ids = []
            
            for msg_id, topic, payload, qos, retain in messages:
                try:
                    self._mqtt_client.publish(topic, payload, qos=qos, retain=bool(retain))
                    synced_count += 1
                    successful_ids.append(msg_id)
                except Exception as e:
                    logger.warning(f"Sync message failed (id={msg_id}): {e}")
                    failed_ids.append(msg_id)
                self._apply_sync_pacing()
            
            # Sync edilen mesajları batch olarak işaretle ve temizle
            with self._db_lock:
                conn = sqlite3.connect(str(self._db_path))

                if successful_ids:
                    sync_time = time.time()
                    conn.executemany(
                        "UPDATE sync_queue SET synced = 1, sync_time = ? WHERE id = ?",
                        [(sync_time, msg_id) for msg_id in successful_ids]
                    )

                conn.execute("DELETE FROM sync_queue WHERE synced = 1")
                cursor = conn.execute("SELECT COUNT(*) FROM sync_queue WHERE synced = 0")
                queue_size = cursor.fetchone()[0]
                conn.commit()
                conn.close()
            
            self.queue_size_changed.emit(queue_size)
            
            if synced_count > 0:
                self.sync_completed.emit(synced_count)
                logger.info(f"Sync completed: {synced_count} messages sent to cloud")
            
            if failed_ids:
                self.sync_failed.emit(f"{len(failed_ids)} mesaj gönderilemedi")
                
        except Exception as e:
            self.sync_failed.emit(str(e))
            logger.error(f"Sync error: {e}")

    def _sync_unified_outbox(self):
        """Unified DB outbox tablosundan cloud broker'a senkronizasyon yap."""
        self._unified_db.purge_sent_outbox(older_than_hours=self._max_queue_age_hours)
        requeued_count = self._unified_db.requeue_stale_inflight(stale_seconds=self._inflight_stale_seconds)
        if requeued_count > 0:
            logger.warning(f"Stale in_flight mesajlar pending'e alındı: {requeued_count}")

        messages = self._unified_db.get_pending_outbox_messages(self._max_batch_size)

        if not messages:
            return

        self.sync_started.emit()
        synced_count = 0
        failed_count = 0
        dead_count = 0
        success_ids = []
        inflight_ids = [int(message['id']) for message in messages]
        self._unified_db.mark_outbox_inflight(inflight_ids)

        for message in messages:
            msg_id = int(message['id'])
            topic = message['topic']
            payload = message['payload']
            qos = int(message.get('qos', 0))
            retain = bool(message.get('retain', 0))

            try:
                self._publish_with_confirmation(topic, payload, qos=qos, retain=retain)
                success_ids.append(msg_id)
                synced_count += 1
            except Exception as e:
                failed_count += 1
                retry_count = int(message.get('retry_count', 0)) + 1
                moved_to_dead = self._unified_db.mark_outbox_failed(
                    msg_id,
                    str(e),
                    retry_count,
                    max_retry_count=self._max_retry_count
                )
                if moved_to_dead:
                    dead_count += 1
                logger.warning(f"Unified outbox message failed (id={msg_id}): {e}")
            self._apply_sync_pacing()

        if success_ids:
            self._unified_db.mark_outbox_sent(success_ids)

        queue_size = self._unified_db.get_pending_outbox_count()
        self.queue_size_changed.emit(queue_size)

        if synced_count > 0:
            self.sync_completed.emit(synced_count)
            logger.info(f"Unified sync completed: {synced_count} messages sent to cloud")

        if failed_count > 0:
            status_counts = self._unified_db.get_outbox_status_counts()
            self.sync_failed.emit(
                f"{failed_count} mesaj gönderilemedi (dead={dead_count}, pending={status_counts.get('pending', 0)}, in_flight={status_counts.get('in_flight', 0)})"
            )

    def _apply_sync_pacing(self):
        """Batch içi pacing ile anlık publish burst yükünü düşür."""
        if self._batch_pacing_ms <= 0:
            return
        time.sleep(self._batch_pacing_ms / 1000.0)

    def _publish_with_confirmation(self, topic: str, payload: str, qos: int, retain: bool):
        """MQTT publish sonucunu doğrula; mümkünse ACK/complete bekle."""
        result = self._mqtt_client.publish(topic, payload, qos=qos, retain=retain)

        # paho v1 tuple sonucu desteği
        if isinstance(result, tuple):
            rc = int(result[0])
            if rc != 0:
                raise RuntimeError(f"MQTT publish rc={rc}")
            return

        rc = int(getattr(result, 'rc', 0))
        if rc != 0:
            raise RuntimeError(f"MQTT publish rc={rc}")

        wait_for_publish = getattr(result, 'wait_for_publish', None)
        if callable(wait_for_publish):
            try:
                wait_for_publish(timeout=self._publish_ack_timeout_seconds)
            except TypeError:
                # Eski paho sürümlerinde timeout parametresi olmayabilir
                wait_for_publish()

        is_published = getattr(result, 'is_published', None)
        if callable(is_published) and not is_published():
            raise RuntimeError("MQTT publish ACK timeout")
    
    def get_queue_size(self) -> int:
        """Kuyruktaki bekleyen mesaj sayısını döndür."""
        try:
            if self._use_unified_outbox and self._unified_db is not None:
                return self._unified_db.get_pending_outbox_count()

            with self._db_lock:
                conn = sqlite3.connect(str(self._db_path))
                cursor = conn.execute("SELECT COUNT(*) FROM sync_queue WHERE synced = 0")
                count = cursor.fetchone()[0]
                conn.close()
                return count
        except Exception:
            return 0
    
    def clear_queue(self):
        """Kuyruğu temizle."""
        try:
            if self._use_unified_outbox and self._unified_db is not None:
                self._unified_db.clear_pending_outbox()
                self.queue_size_changed.emit(0)
                logger.info("Unified outbox queue cleared")
                return

            with self._db_lock:
                conn = sqlite3.connect(str(self._db_path))
                conn.execute("DELETE FROM sync_queue")
                conn.commit()
                conn.close()
            self.queue_size_changed.emit(0)
            logger.info("Sync queue cleared")
        except Exception as e:
            logger.error(f"Clear queue error: {e}")

    def get_health_snapshot(self) -> Dict[str, object]:
        """Sync servisinin anlık sağlık durumunu döndür (Phase 3)."""
        snapshot: Dict[str, object] = {
            'online': bool(self._is_online),
            'has_mqtt_client': bool(self._mqtt_client),
            'unified_outbox_mode': bool(self._use_unified_outbox and self._unified_db is not None),
            'queue_size': 0,
        }

        try:
            snapshot['queue_size'] = int(self.get_queue_size())
        except Exception:
            snapshot['queue_size'] = 0

        if snapshot['unified_outbox_mode']:
            try:
                snapshot['outbox_status_counts'] = self._unified_db.get_outbox_status_counts()
                snapshot['db_health'] = self._unified_db.get_database_health_snapshot()
            except Exception as e:
                snapshot['db_health_error'] = str(e)
        else:
            snapshot['legacy_sync_db'] = str(self._db_path)

        return snapshot
