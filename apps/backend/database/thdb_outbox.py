# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""OUTBOX KUYRUGU — `TreatmentHistoryDB`nin outbox yarisi (B4 · 1/N, 2026-09-18).

⚠️ NEDEN AYRILDI (denetim B4): `treatment_history_db.py` TEK SINIFTA 93 metot tasiyordu —
seans yasam dongusu + bobin kosusu + sensor telemetrisi + AI gecmisi + denetim izi + outbox
+ sema gocu + PII redaksiyonu. Olcut SATIR SAYISI DEGIL (bu depoda yorumlar ozelliktir);
sorun tek nesnede yedi ayri sorumluluk. Outbox kumesi ILK ayrilan, cunku TEK tabloya
(`outbox_messages`) dokunuyor ve baska hicbir kumeyle kesismiyor.

⚠️ NEDEN KARISIM (mixin), NEDEN ISBIRLIKCI NESNE DEGIL:
`get_treatment_db(...)` urunun her yerinden aliniyor ve metotlar DOGRUDAN cagriliyor.
Isbirlikci nesneye cevirmek (`db.outbox.enqueue(...)`) tum cagri yerlerini degistirirdi —
genis yuzeyli ve davranis-koruyan OLMAYAN bir degisiklik. Karisim GENEL API'yi BIREBIR korur:
ayni nesne, ayni metot adlari, ayni `self`. Bolme mekanik ve geri-alinabilir kalir.

⚠️ GOVDELER DEGISTIRILMEDI. Metotlar bayt bayt tasindi; tek fark hangi sinifta durduklari.
Bu dosya hasta gecmisini bir kez kaybettiren kod yolunda — davranis degisikligi AYRI commit'e.

⚠️ OUTBOX "DRAIN-ONLY"DIR (sahip karari, bellek `pemf-dead-code-2026-07-12`): kuyruk
bosaltilir ama MEKANIZMA SILINMEZ. Bu modulu "kullanilmiyor" diye kaldirmayin.

`self` uzerinden kullandigi ve ANA SINIFTA kalan uyeler: `_get_connection`, `logger`.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from typing import Dict, List, Optional

# SQLCipher + sqlite3 istisna demetleri TEK KAYNAKTAN (bkz. database/db_hatalari.py).
from database.db_hatalari import _DB_ERROR, _DB_INTEGRITY  # noqa: F401


class OutboxKarisimi:
    def purge_old_dead_outbox(self, retain_days: int = 30) -> int:
        """Uzun süreli dead outbox kayıtlarını temizle."""
        cutoff_ts = datetime.now().timestamp() - (max(1, int(retain_days)) * 86400)
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    '''
                    DELETE FROM outbox_messages
                    WHERE status = 'dead' AND available_at < ?
                ''',
                    (cutoff_ts,),
                )
                removed = int(cursor.rowcount)
                conn.commit()
                return removed
        except Exception as e:
            self.logger.warning(f"Dead outbox retention temizleme uyarısı: {e}")
            return 0

    def enqueue_outbox_message(
        self,
        topic: str,
        payload: str,
        qos: int = 0,
        retain: bool = False,
        source: str = 'gateway',
        correlation_id: Optional[str] = None,
        available_at: Optional[float] = None,
        idempotency_key: Optional[str] = None,
    ) -> Optional[int]:
        """Cloud'a gönderilecek mesajı unified outbox tablosuna ekle."""
        try:
            self._ensure_write_guardrail()
            now_ts = datetime.now().timestamp()
            ready_at = available_at if available_at is not None else now_ts
            derived_key = idempotency_key
            if derived_key:
                digest_src = f"{derived_key}|{topic}|{int(qos)}|{int(bool(retain))}".encode('utf-8')
                derived_key = hashlib.sha256(digest_src).hexdigest()

            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    '''
                    INSERT INTO outbox_messages
                    (message_uuid, idempotency_key, topic, payload, qos, retain, status, retry_count,
                     available_at, source, correlation_id, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, 'pending', 0, ?, ?, ?, ?)
                ''',
                    (
                        str(uuid.uuid4()),
                        derived_key,
                        topic,
                        payload,
                        int(qos),
                        int(bool(retain)),
                        ready_at,
                        source,
                        correlation_id,
                        now_ts,
                    ),
                )
                conn.commit()
                return cursor.lastrowid
        except _DB_INTEGRITY:
            # Idempotency key duplicate -> mevcut kaydı tekrar ekleme
            if not derived_key:
                return None
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT id FROM outbox_messages WHERE idempotency_key = ?', (derived_key,))
                    row = cursor.fetchone()
                    return int(row['id']) if row else None
            except Exception:
                return None
        except Exception as e:
            self.logger.error(f"Outbox enqueue hatası: {e}")
            return None

    def get_pending_outbox_messages(self, limit: int = 100) -> List[Dict]:
        """Gönderime hazır pending outbox mesajlarını getir."""
        try:
            now_ts = datetime.now().timestamp()
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    '''
                    SELECT id, message_uuid, topic, payload, qos, retain, retry_count,
                           available_at, created_at, source, correlation_id
                    FROM outbox_messages
                    WHERE status = 'pending' AND available_at <= ?
                    ORDER BY created_at ASC
                    LIMIT ?
                ''',
                    (now_ts, limit),
                )
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            self.logger.error(f"Pending outbox okuma hatası: {e}")
            return []

    def mark_outbox_sent(self, message_ids: List[int]):
        """Başarıyla gönderilen outbox mesajlarını sent olarak işaretle."""
        if not message_ids:
            return

        try:
            sent_at = datetime.now().timestamp()
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.executemany(
                    '''
                    UPDATE outbox_messages
                    SET status = 'sent', sent_at = ?, last_error = NULL
                    WHERE id = ?
                ''',
                    [(sent_at, int(msg_id)) for msg_id in message_ids],
                )
                conn.commit()
        except Exception as e:
            self.logger.error(f"Outbox sent işaretleme hatası: {e}")

    def mark_outbox_inflight(self, message_ids: List[int]):
        """Gönderim denemesi başlayan mesajları in_flight olarak işaretle."""
        if not message_ids:
            return

        try:
            now_ts = datetime.now().timestamp()
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.executemany(
                    '''
                    UPDATE outbox_messages
                    SET status = 'in_flight', available_at = ?, last_error = NULL
                    WHERE id = ? AND status = 'pending'
                ''',
                    [(now_ts, int(msg_id)) for msg_id in message_ids],
                )
                conn.commit()
        except Exception as e:
            self.logger.error(f"Outbox in_flight işaretleme hatası: {e}")

    def mark_outbox_failed(self, message_id: int, error_text: str, retry_count: int, max_retry_count: int = 20) -> bool:
        """Gönderim hatasında retry sayısını ve tekrar deneme zamanını güncelle."""
        try:
            next_retry_at = datetime.now().timestamp() + self._retry_backoff_seconds(retry_count)
            next_status = 'dead' if retry_count >= max_retry_count else 'pending'
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    '''
                    UPDATE outbox_messages
                    SET status = ?, retry_count = ?, available_at = ?, last_error = ?
                    WHERE id = ?
                ''',
                    (next_status, int(retry_count), next_retry_at, str(error_text), int(message_id)),
                )
                conn.commit()
                return next_status == 'dead'
        except Exception as e:
            self.logger.error(f"Outbox failed işaretleme hatası: {e}")
            return False

    def requeue_stale_inflight(self, stale_seconds: int = 120) -> int:
        """Uzun süre in_flight kalan mesajları tekrar pending yap."""
        try:
            cutoff_ts = datetime.now().timestamp() - max(1, int(stale_seconds))
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    '''
                    UPDATE outbox_messages
                    SET status = 'pending',
                        available_at = ?,
                        last_error = COALESCE(last_error, 'requeued stale in_flight')
                    WHERE status = 'in_flight' AND available_at < ?
                ''',
                    (datetime.now().timestamp(), cutoff_ts),
                )
                affected = int(cursor.rowcount)
                conn.commit()
                return affected
        except Exception as e:
            self.logger.warning(f"Stale in_flight requeue uyarısı: {e}")
            return 0

    def get_pending_outbox_count(self) -> int:
        """Bekleyen outbox mesaj sayısını getir."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM outbox_messages WHERE status IN ('pending', 'in_flight')")
                return int(cursor.fetchone()[0])
        except Exception:
            return 0

    def get_outbox_status_counts(self) -> Dict[str, int]:
        """Outbox durum dağılımını döndür (pending/in_flight/sent/dead)."""
        counts = {'pending': 0, 'in_flight': 0, 'sent': 0, 'dead': 0}
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT status, COUNT(*) as cnt
                    FROM outbox_messages
                    GROUP BY status
                ''')
                for row in cursor.fetchall():
                    status = str(row['status'])
                    if status in counts:
                        counts[status] = int(row['cnt'])
            return counts
        except Exception:
            return counts

    def purge_sent_outbox(self, older_than_hours: int = 72):
        """Belirtilen süreden eski sent kayıtlarını temizle."""
        try:
            cutoff_ts = datetime.now().timestamp() - (older_than_hours * 3600)
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    '''
                    DELETE FROM outbox_messages
                    WHERE status = 'sent' AND sent_at IS NOT NULL AND sent_at < ?
                ''',
                    (cutoff_ts,),
                )
                conn.commit()
        except Exception as e:
            self.logger.warning(f"Outbox temizleme uyarısı: {e}")

    def clear_pending_outbox(self):
        """Bekleyen outbox kayıtlarını temizle (operasyonel bakım)."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM outbox_messages WHERE status IN ('pending', 'in_flight')")
                conn.commit()
        except Exception as e:
            self.logger.warning(f"Pending outbox temizleme uyarısı: {e}")
