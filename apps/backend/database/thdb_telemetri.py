# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""BOBIN KOSUSU + SENSOR TELEMETRISI — (B4 · 4/N, 2026-09-18).

⚠️ AYRILMA GEREKCESI: bkz. `database/thdb_outbox.py` bas yorumu (B4 · 1/N).
Bu kume `session_coil_runs` · `sensor_samples` · `sensor_run_summary` tablolarina dokunur.

⚠️ SENSOR ORNEKLERI DAKIKA-ORTALAMASIDIR, ham akis DEGIL (denetim karari): `sensor_samples`
satirlari `sample_count` tasir — ortalamaya kac ham ornegin girdigi. Bunu "ham veri" sanip
ortalama mantigini kaldirmayin; klinik basina seans-basi ~bobin x 20 satir hedefi buna dayali.

⚠️ `_seansin_son_kaniti` BURADA ama seans kurtarmasi (`recover_stale_active_sessions`) ANA
SINIFTA kaldi: "bu seans gercekten yasiyor mu" sorusunun kaniti TELEMETRIDEN gelir
(son bobin kosusu / son sensor ornegi). Karisim `self` paylastigi icin cagri degismedi.

⚠️ GOVDELER DEGISTIRILMEDI — bayt bayt tasindi.

`self` uzerinden kullandigi ve ANA SINIFTA kalan uyeler: `_get_connection`, `logger`.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Dict, List, Optional

# SQLCipher + sqlite3 istisna demetleri TEK KAYNAKTAN (bkz. database/db_hatalari.py).
from database.db_hatalari import _DB_ERROR, _DB_INTEGRITY  # noqa: F401


class TelemetriKarisimi:
    def _seansin_son_kaniti(self, cursor, session_id: int, baslangic_epoch: float):
        """Seansın DİSKTE İZ BIRAKAN son anı (epoch) — yoksa None.

        ⚠️ Bitişi `datetime.now()` yazmak YANLIŞ TIBBİ KAYIT üretir: cihaz günlerce kapalı
        kalmış olabilir ve kayıt "3 gün süren tedavi" der. Yanlış kayıt, eksik kayıttan daha
        kötüdür — denetimde gerçek sanılır. Bu yüzden bitiş KANITTAN türetilir: son bobin
        çalışması ve son sensör örneği (ikisinin en büyüğü).
        """
        en_son = None
        for sorgu, parametre in (
            (
                "SELECT MAX(COALESCE(ended_epoch, started_epoch)) FROM session_coil_runs WHERE session_id = ?",
                (session_id,),
            ),
            ("SELECT MAX(sample_ts) FROM sensor_samples WHERE session_id = ?", (session_id,)),
        ):
            try:
                deger = cursor.execute(sorgu, parametre).fetchone()[0]
            except Exception:
                deger = None  # tablo/sütun yoksa (eski şema) kanıt aramayı BOZMA
            if deger is not None and (en_son is None or float(deger) > en_son):
                en_son = float(deger)
        # Kanıt seans başlangıcından ÖNCEYSE güvenilmez (saat değişimi / bozuk satır).
        if en_son is not None and en_son < baslangic_epoch:
            return None
        return en_son

    def purge_old_sensor_samples(self, retain_days: int = 90) -> int:
        """Retention süresini aşan sensör örneklerini temizle."""
        cutoff_ts = datetime.now().timestamp() - (max(1, int(retain_days)) * 86400)
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM sensor_samples WHERE sample_ts < ?', (cutoff_ts,))
                removed = int(cursor.rowcount)
                conn.commit()
                return removed
        except Exception as e:
            self.logger.warning(f"Sensor retention temizleme uyarısı: {e}")
            return 0

    def purge_old_coil_runs(self, retain_days: int = 3650) -> int:
        """P2 audit 2026-06-28: retention suresini asan per-bobin run kayitlarini (session_coil_runs
        + sensor_run_summary) temizle — eskiden HIC temizlenmiyordu (sinirsiz buyume).

        ⚠️ DENETİM 2026-08-17 — BU TABLO UYGULANAN DOZDUR, TELEMETRİ DEĞİL. Şeması "hangi bobin,
        hangi frekans/duty/faz ile, kaç saniye çalıştı" tutuyor; büyümeyi sürükleyen telemetri
        AYRI tabloda (`sensor_samples`). Buna rağmen bu adım SENSÖR saklama süresine (90 gün)
        bağlanmıştı ve iki sonucu vardı:
          · `treatment_sessions` HİÇ silinmiyor → 90. günden sonra seans başlığı duruyor ama
            "hangi bobin, hangi duty" cevabı yok oluyor. Yan etki soruşturmasında 4 ay önceki
            seansın PDF'inde "Bobin Çalışmaları" tablosu SESSİZCE kayboluyor (`if not runs: return`).
          · KVKK açısından ters takas: kimliği taşıyan taraf (`patients`/`treatment_sessions`)
            kalıyor, tıbbi kanıt gidiyor — veri minimizasyonuna sıfır katkı.
        Varsayılan 3650 (10 yıl): hasta anonimleştirme eşiği zaten 1825 gün ve ayar ucu 0-36500
        aralığını kabul ediyor. Sahibin GERÇEK kararı ("sınırsız büyüme olmasın") korunuyor —
        değişen tek şey SAAT.

        ⚠️ `0 = adım kapalı` sözleşmesi çağıran tarafta; buraya 0 gelmez.
        """
        cutoff_ts = datetime.now().timestamp() - (max(1, int(retain_days)) * 86400)
        removed = 0
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'DELETE FROM sensor_run_summary WHERE coil_run_id IN '
                    '(SELECT id FROM session_coil_runs WHERE started_epoch < ?)',
                    (cutoff_ts,),
                )
                cursor.execute('DELETE FROM session_coil_runs WHERE started_epoch < ?', (cutoff_ts,))
                removed = int(cursor.rowcount)
                conn.commit()
        except Exception as e:
            self.logger.warning(f"Coil-run retention temizleme uyarisi: {e}")
            return 0
        # ⚠️ İZ, `with` BLOĞUNUN DIŞINDA yazılır: `self._lock` re-entrant DEĞİL ve `denetim_yaz` onu
        # alıyor; ayrıca aynı thread'in açık bağlantı context'i içinde ikinci bir commit açılmaz.
        # ⚠️ Geri dönüşsüz PII maskelemesi denetim izine yazılıyordu, geri dönüşsüz DOZ silmesi
        # yazılmıyordu — asimetri buradan kapanıyor. `denetim_yaz` istisna ATMAZ, günlük bakım
        # bu yüzden kilitlenmez.
        if removed:
            self.denetim_yaz(
                "retention.doz_silindi",
                scope="otomatik",
                item_count=removed,
                detail={"gun": int(retain_days)},
            )
        return removed

    def add_sensor_samples_batch(self, session_id: int, samples: List[Dict]) -> int:
        """Aktif seans için sensör örneklerini batch olarak kaydet.

        Geriye uyumlu genisletme: her ornek dict'i opsiyonel olarak coil_run_id,
        ambient_temp_c, phase, sample_count alanlarini icerebilir; verilmezse NULL
        yazilir. Mevcut cagiranlar (sadece eski alanlari veren) bozulmaz.
        sensor_samples artik dakika-ortalamasi tutabilir; sample_count = ortalamaya
        giren ham okuma sayisi.
        """
        if not samples:
            return 0

        try:
            self._ensure_write_guardrail()
            rows = []
            now_ts = datetime.now().timestamp()
            for sample in samples:
                rows.append(
                    (
                        int(session_id),
                        str(sample.get('coil_id', 'unknown')),
                        float(sample.get('sample_ts', now_ts)),
                        sample.get('temperature_c'),
                        sample.get('magnetic_field_mt'),
                        sample.get('current_a'),
                        sample.get('pwm_frequency_hz'),
                        sample.get('pwm_duty_percent'),
                        json.dumps(sample.get('payload', {}), ensure_ascii=True),
                        now_ts,
                        sample.get('coil_run_id'),
                        sample.get('ambient_temp_c'),
                        sample.get('phase'),
                        sample.get('sample_count'),
                    )
                )

            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.executemany(
                    '''
                    INSERT INTO sensor_samples
                    (session_id, coil_id, sample_ts, temperature_c, magnetic_field_mt,
                     current_a, pwm_frequency_hz, pwm_duty_percent, payload, created_at,
                     coil_run_id, ambient_temp_c, phase, sample_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                    rows,
                )
                conn.commit()
                return len(rows)
        except Exception as e:
            # DENETIM P2: hata SESSIZCE 0 donuyordu ve cagiran bunu "yazacak satir yoktu"dan
            # AYIRT EDEMIYORDU → 'basarisizsa buffer'a geri koy' kurtarma yollari fiilen olu
            # kaliyor, seansin sensor/sicaklik telemetrisi kayboluyordu. Donus sozlesmesi
            # (int) KORUNDU (tum cagiranlar try/except icinde ve int bekliyor); ayirt
            # edilebilirlik cagiran tarafinda "pending vardi ama 0 yazildi" ile saglanir.
            # Kayip miktarini GORUNUR yap: sessiz kayip en kotu turden veri kaybidir.
            self.logger.error(
                "Sensor sample batch kaydetme hatasi (session_id=%s): %s — %d ORNEK YAZILAMADI.",
                session_id,
                e,
                len(samples or []),
            )
            return 0

    def start_coil_run(
        self,
        session_id: Optional[int],
        coil_id: int,
        *,
        frequency_hz: Optional[float] = None,
        duty_percent: Optional[float] = None,
        phase: Optional[float] = None,
        intensity_mt: Optional[float] = None,
        hw_type: Optional[str] = None,
        started_epoch: float,
    ) -> Optional[int]:
        """Bir bobinin calismaya basladigini kaydet. created_at=started_epoch.
        Geri donus: run_id (int) veya hata halinde None."""
        try:
            self._ensure_write_guardrail()
            started = float(started_epoch)
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    '''
                    INSERT INTO session_coil_runs
                    (session_id, coil_id, started_epoch, ended_epoch, duration_seconds,
                     frequency_hz, duty_percent, phase, intensity_mt, hw_type, created_at)
                    VALUES (?, ?, ?, NULL, NULL, ?, ?, ?, ?, ?, ?)
                ''',
                    (
                        session_id,
                        int(coil_id),
                        started,
                        frequency_hz,
                        duty_percent,
                        phase,
                        intensity_mt,
                        hw_type,
                        started,
                    ),
                )
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            self.logger.error(f"Coil run baslatma hatası: {e}")
            return None

    def end_coil_run(self, run_id: int, ended_epoch: float) -> None:
        """Bobin calismasini bitir; duration_seconds = ended_epoch - started_epoch
        (started_epoch satirdan okunur)."""
        try:
            self._ensure_write_guardrail()
            ended = float(ended_epoch)
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT started_epoch FROM session_coil_runs WHERE id = ?', (int(run_id),))
                row = cursor.fetchone()
                if not row or row['started_epoch'] is None:
                    self.logger.warning(f"end_coil_run: run_id {run_id} bulunamadi/started_epoch yok")
                    return
                started = float(row['started_epoch'])
                cursor.execute(
                    '''
                    UPDATE session_coil_runs
                    SET ended_epoch = ?, duration_seconds = ?
                    WHERE id = ?
                ''',
                    (ended, ended - started, int(run_id)),
                )
                conn.commit()
        except Exception as e:
            self.logger.error(f"Coil run bitirme hatası: {e}")

    def add_sensor_run_summary(
        self,
        coil_run_id: int,
        *,
        sample_count=None,
        temp_min=None,
        temp_max=None,
        temp_avg=None,
        current_avg=None,
        field_avg=None,
    ) -> None:
        """Bir bobin calismasinin sensor ozet istatistigini kaydet.
        coil_run_id UNIQUE oldugu icin INSERT OR REPLACE kullanilir (yeniden hesapta uzerine yazar)."""
        try:
            self._ensure_write_guardrail()
            now_ts = datetime.now().timestamp()
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    '''
                    INSERT OR REPLACE INTO sensor_run_summary
                    (coil_run_id, sample_count, temp_min, temp_max, temp_avg,
                     current_avg, field_avg, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                    (int(coil_run_id), sample_count, temp_min, temp_max, temp_avg, current_avg, field_avg, now_ts),
                )
                conn.commit()
        except Exception as e:
            self.logger.error(f"Sensor run summary kaydetme hatası: {e}")

    def get_session_coil_runs(self, session_id: int) -> List[Dict]:
        """Bir seansa ait bobin calismalarini rapor icin getir
        (coil_id, started/ended_epoch, duration, parametreler)."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    '''
                    SELECT id, session_id, coil_id, started_epoch, ended_epoch,
                           duration_seconds, frequency_hz, duty_percent, phase,
                           intensity_mt, hw_type, created_at
                    FROM session_coil_runs
                    WHERE session_id = ?
                    ORDER BY started_epoch ASC
                ''',
                    (session_id,),
                )
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except _DB_ERROR as e:
            self.logger.error(f"Coil run listeleme hatası: {e}")
            return []

    def get_run_summaries(self, session_id: int) -> Dict:
        """Bir seansin tum bobin-calismalarinin sensor ozetlerini getir.
        sensor_run_summary'yi session_coil_runs ile JOIN'leyip o seansa ait
        coil_run_id'leri filtreler.
        Donus: {coil_run_id: {sample_count, temp_min, temp_max, temp_avg,
                              current_avg, field_avg}}.
        Ozet bulunmayan run'lar sozlukte yer almaz (rapor tarafinda null'a duser)."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    '''
                    SELECT s.coil_run_id, s.sample_count, s.temp_min, s.temp_max,
                           s.temp_avg, s.current_avg, s.field_avg
                    FROM sensor_run_summary s
                    JOIN session_coil_runs r ON r.id = s.coil_run_id
                    WHERE r.session_id = ?
                ''',
                    (session_id,),
                )
                rows = cursor.fetchall()
                summaries = {}
                for row in rows:
                    d = dict(row)
                    summaries[d['coil_run_id']] = {
                        'sample_count': d.get('sample_count'),
                        'temp_min': d.get('temp_min'),
                        'temp_max': d.get('temp_max'),
                        'temp_avg': d.get('temp_avg'),
                        'current_avg': d.get('current_avg'),
                        'field_avg': d.get('field_avg'),
                    }
                return summaries
        except _DB_ERROR as e:
            self.logger.error(f"Run summary listeleme hatası: {e}")
            return {}

    def get_sensor_samples(self, session_id: int) -> List[Dict]:
        """Bir seansin sensor orneklerini grafik icin getir (sample_ts ASC).
        Donus alanlari: coil_id, sample_ts, temperature_c, ambient_temp_c,
        current_a, magnetic_field_mt, pwm_frequency_hz, pwm_duty_percent,
        coil_run_id, sample_count."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    '''
                    SELECT coil_id, sample_ts, temperature_c, ambient_temp_c,
                           current_a, magnetic_field_mt, pwm_frequency_hz,
                           pwm_duty_percent, coil_run_id, sample_count
                    FROM sensor_samples
                    WHERE session_id = ?
                    ORDER BY sample_ts ASC
                ''',
                    (session_id,),
                )
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except _DB_ERROR as e:
            self.logger.error(f"Sensor sample listeleme hatası: {e}")
            return []
