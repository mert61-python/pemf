# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""SEANS YASAM DONGUSU — `TreatmentHistoryDB`nin cekirdegi (B4 · 7/N, 2026-09-18).

⚠️ AYRILMA GEREKCESI: bkz. `database/thdb_outbox.py` bas yorumu (B4 · 1/N).
Bu kume `treatment_sessions` · `session_parameters` · `session_events` tablolarina dokunur
ve hasta kaydinin (`upsert_patient`) tedavi tarafindaki aynasini tutar.

⚠️ BURASI TIBBI KAYDIN YAZILDIGI YER. `end_session` bir seansi "Tamamlandi" diye muhurler;
o satir sonradan PDF raporuna, KPI'ya ve hasta gecmisine GERCEK DOZ olarak girer. Bu depoda
olculmus ariza: bobinler hic enerjilenmemisken seans "basarili" kapaniyordu
(bellek `pemf-sahte-basarili-seans`). Yani buradaki bir satir, olmamis bir tedaviyi
kayitlara gecirebilir.

⚠️ `recover_stale_active_sessions` ACILISTA kosar ve "yarim kalmis" seanslari kapatir.
Kaniti TELEMETRIDEN alir (`_seansin_son_kaniti`, `thdb_telemetri`) — karisimlar `self`
paylastigi icin cagri degismedi.

⚠️ ARAYUZDE "SEANS", KOD/DB'DE "treatment" (sahip karari, bellek
`pemf-tedavi-seans-terminoloji`): tablo ve alan adlarini Turkcelestirmeyin.

⚠️ GOVDELER DEGISTIRILMEDI — AST ile bayt bayt tasindi.

`self` uzerinden kullandigi ve ANA SINIFTA kalan uyeler: `_get_connection`, `logger`,
`_ensure_write_guardrail`.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# ⚠️ SQLCipher + sqlite3 istisna demetleri TEK KAYNAKTAN. Bu adlar MODUL DUZEYIDIR ve
# tasinan `except` dallarinda kullanilir; goturulmezse `NameError` olur ve TAM SUIT bunu
# GOREMEZ (o dallar yalnizca gercek bir DB hatasinda kosar). Bkz. database/db_hatalari.py.
from database.db_hatalari import _DB_ERROR


class SeansKarisimi:
    def recover_stale_active_sessions(self, max_age_hours: int = 12) -> int:
        """Açık kalmış `active` seansları güvenli şekilde kapat (recovery).

        `max_age_hours <= 0` → YAŞ FİLTRESİ YOK, tüm `active` seanslar kapatılır.

        ⚠️ AÇILIŞTA YAŞ FİLTRESİ UYGULANMAZ (kampanya bulgusu S01, 2026-08-14). Bu metodun
        TEK çağrıldığı yer `__init__`, yani BACKEND AÇILIŞIDIR; açılışta bu cihazın hiçbir
        seansı canlı olamaz — süreç yeni başlamıştır. Eski 12 saatlik eşik, çalıştığı tek
        bağlamda hiçbir şey korumuyor, yalnızca kaydı belirsiz bırakıyordu: seans sürerken
        çöken bir cihaz yeniden açıldığında kayıt `active` / `end_time=NULL` /
        `duration_minutes=NULL` kalıyor, üstelik bobin çalışmaları da kapanmıyordu →
        **hastaya uygulanan doz hiç yazılmıyordu.**
        """
        recovered_count = 0
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, session_date, start_time
                    FROM treatment_sessions
                    WHERE session_status = 'active'
                ''')
                rows = cursor.fetchall()

                now = datetime.now()
                yas_filtresi = int(max_age_hours) > 0
                threshold = now - timedelta(hours=max(1, int(max_age_hours))) if yas_filtresi else None

                for row in rows:
                    session_id = int(row['id'])
                    session_date = str(row['session_date'])
                    start_time = str(row['start_time'])

                    try:
                        started_at = datetime.strptime(f"{session_date} {start_time}", '%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        # Parse edilemeyen kaydı da recovery et
                        started_at = now - timedelta(hours=abs(int(max_age_hours)) + 1)

                    if yas_filtresi and started_at > threshold:
                        continue

                    # Bitiş: KANITTAN (bkz. `_seansin_son_kaniti`); kanıt yoksa başlangıç.
                    baslangic_epoch = started_at.timestamp()
                    son_kanit = self._seansin_son_kaniti(cursor, session_id, baslangic_epoch)
                    bitis_epoch = son_kanit if son_kanit is not None else baslangic_epoch
                    bitis_dt = datetime.fromtimestamp(bitis_epoch)
                    duration_minutes = max(0, int((bitis_epoch - baslangic_epoch) / 60))

                    # ⚠️ DOZ KAYDI seans satırında DEĞİL, bobin çalışmalarında durur. Seansı
                    # kapatıp bunları açık bırakmak "hangi bobin ne kadar sürdü"yü cevapsız
                    # bırakır — kaydın tıbbi değeri kalmaz.
                    try:
                        cursor.execute(
                            '''
                            UPDATE session_coil_runs
                            SET ended_epoch = ?,
                                duration_seconds = MAX(0, ? - started_epoch)
                            WHERE session_id = ? AND ended_epoch IS NULL
                        ''',
                            (bitis_epoch, bitis_epoch, session_id),
                        )
                    except Exception:
                        self.logger.warning("Kurtarma: bobin calismalari kapatilamadi (seans %s)", session_id)

                    cursor.execute(
                        '''
                        UPDATE treatment_sessions
                        SET end_time = ?,
                            duration_minutes = ?,
                            session_status = 'ABORTED_DUE_TO_POWER',
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    ''',
                        (bitis_dt.strftime('%H:%M:%S'), duration_minutes, session_id),
                    )
                    recovered_count += 1

                conn.commit()

            if recovered_count > 0:
                self.logger.warning(
                    f"Recovery: {recovered_count} stale active session kurtarıldı (ABORTED_DUE_TO_POWER)"
                )
        except Exception as e:
            self.logger.warning(f"Stale session recovery uyarısı: {e}")

        return recovered_count

    def purge_old_session_events(self, retain_days: int = 365) -> int:
        """Retention süresini aşan session event kayıtlarını temizle."""
        cutoff_ts = datetime.now().timestamp() - (max(1, int(retain_days)) * 86400)
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM session_events WHERE created_at < ?', (cutoff_ts,))
                removed = int(cursor.rowcount)
                conn.commit()
                return removed
        except Exception as e:
            self.logger.warning(f"Session event retention temizleme uyarısı: {e}")
            return 0

    def start_session(
        self,
        treatment_mode: str,
        target_condition: str = None,
        operator_name: str = None,
        patient_name: str = None,
        operator_email: str = None,
    ) -> int:
        """
        Yeni tedavi seansı başlat

        Args:
            treatment_mode: Tedavi modu (Autonomous, Manual, vb.)
            target_condition: Hedef durum (artrit, yara iyileşmesi, vb.)
            operator_name: Uygulayıcı adı
            patient_name: Hasta adı

        Returns:
            int: Oluşturulan seans ID'si
        """
        try:
            self._ensure_write_guardrail()
            # HIGH FIX: Use connection pool instead of new connection
            with self._get_connection() as conn:
                cursor = conn.cursor()

                now = datetime.now()
                session_date = now.strftime('%Y-%m-%d')
                start_time = now.strftime('%H:%M:%S')
                session_uuid = str(uuid.uuid4())

                cursor.execute(
                    '''
                    INSERT INTO treatment_sessions
                    (session_date, start_time, treatment_mode, target_condition,
                     operator_name, operator_email, patient_name, session_status, session_uuid)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?)
                ''',
                    (
                        session_date,
                        start_time,
                        treatment_mode,
                        target_condition,
                        self._redact_pii(operator_name),
                        (operator_email or None),
                        self._redact_pii(patient_name),
                        session_uuid,
                    ),
                )

                session_id = cursor.lastrowid
                conn.commit()

                self.logger.info(f"Yeni tedavi seansı başlatıldı: ID {session_id}")
                return session_id

        except _DB_ERROR as e:
            self.logger.error(f"Seans başlatma hatası: {e}")
            raise

    def end_session(
        self,
        session_id: int,
        parameters: Dict = None,
        patient_notes: str = None,
        duration_minutes: int = None,
        session_status: str = "completed",
    ):
        """
        Tedavi seansını sonlandır

        Args:
            session_id: Seans ID'si
            parameters: Tedavi parametreleri sözlüğü
            patient_notes: Hasta notları
        """
        try:
            self._ensure_write_guardrail()
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Seans bilgilerini al
                cursor.execute(
                    '''
                    SELECT start_time, session_date FROM treatment_sessions
                    WHERE id = ?
                ''',
                    (session_id,),
                )

                result = cursor.fetchone()
                if not result:
                    raise ValueError(f"Seans bulunamadı: {session_id}")

                start_time_str, session_date = result

                # Süreyi hesapla (opsiyonel override varsa kullan)
                now = datetime.now()
                end_time = now.strftime('%H:%M:%S')

                if duration_minutes is None:
                    # Savunmali: negatif-clamp (saat kaymasi/DST/session_date tutarsizligi) + malformed
                    # tarih guard'i (strptime patlarsa end_session komple basarisiz olmasin, 0 yaz).
                    try:
                        start_datetime = datetime.strptime(f"{session_date} {start_time_str}", '%Y-%m-%d %H:%M:%S')
                        duration_minutes = max(0, int((now - start_datetime).total_seconds() / 60))
                    except Exception:
                        self.logger.warning(
                            "Sure hesaplanamadi (session_date=%s start=%s) → 0 dk.", session_date, start_time_str
                        )
                        duration_minutes = 0

                # Seans bilgilerini güncelle.
                # ⚠️ Durum artık SABİT DEĞİL: acil durdurma ile biten seans normal bitenden ayırt
                # edilebilmeli (bkz. SEANS_DURUMU_ACIL_DURDURMA). Varsayılan 'completed' kalır →
                # normal akış değişmez.
                update_data = [end_time, duration_minutes, session_status or 'completed', session_id]
                # D1 (denetim 2026-08-24): KAPANIŞ senkronlanmayı İŞARETLER (sync_status=0). Seans
                # AKTİFKEN buluta push edilmiş olabilir (worker 60 sn interval → 1 dk'dan uzun her
                # seansta sync_status=1 olur); kapanış bayrağı 0'a çekmezse bir sonraki PUSH
                # ('WHERE sync_status=0') kapanışı HİÇ görmez → bulut kopyası sonsuza dek 'active'
                # kalır (end_time/duration bulutta hiç oluşmaz). Kilit: test_sync_pull_bayat_active.
                update_query = '''
                    UPDATE treatment_sessions
                    SET end_time = ?, duration_minutes = ?, session_status = ?,
                        sync_status = 0,
                        updated_at = CURRENT_TIMESTAMP
                '''

                if parameters:
                    # Ana parametreleri güncelle
                    if 'frequency_hz' in parameters:
                        update_query += ', frequency_hz = ?'
                        update_data.insert(-1, parameters['frequency_hz'])
                    if 'intensity_mt' in parameters:
                        update_query += ', intensity_mt = ?'
                        update_data.insert(-1, parameters['intensity_mt'])
                    if 'pulse_duration_ms' in parameters:
                        update_query += ', pulse_duration_ms = ?'
                        update_data.insert(-1, parameters['pulse_duration_ms'])

                if patient_notes:
                    update_query += ', patient_notes = ?'
                    update_data.insert(-1, self._redact_pii(patient_notes))

                update_query += ' WHERE id = ?'

                cursor.execute(update_query, update_data)

                # Detaylı parametreleri kaydet
                if parameters:
                    for param_name, param_value in parameters.items():
                        if param_name not in ['frequency_hz', 'intensity_mt', 'pulse_duration_ms']:
                            _pv = str(param_value)
                            if param_name in self._PII_PARAM_NAMES:
                                _pv = self._redact_pii(_pv)
                            cursor.execute(
                                '''
                                INSERT INTO session_parameters
                                (session_id, parameter_name, parameter_value)
                                VALUES (?, ?, ?)
                            ''',
                                (session_id, param_name, _pv),
                            )

                conn.commit()
                self.logger.info(f"Tedavi seansı sonlandırıldı: ID {session_id}")

        except _DB_ERROR as e:
            self.logger.error(f"Seans sonlandırma hatası: {e}")
            raise

    def get_session_history(
        self,
        limit: int = 100,
        start_date: str = None,
        end_date: str = None,
        treatment_mode: str = None,
        before_id: int = None,
        internal_full: bool = False,
        session_ids=None,
    ) -> List[Dict]:
        """
        Tedavi geçmişini getir

        Args:
            limit: Maksimum kayıt sayısı
            start_date: Başlangıç tarihi (YYYY-MM-DD)
            end_date: Bitiş tarihi (YYYY-MM-DD)
            treatment_mode: Tedavi modu filtresi
            before_id: audit B-8.2 keyset (cursor) pagination — verilirse yalnız bu id'den ESKİ
                       (daha küçük id) seanslar döner. Bir sonraki sayfa için: son öğenin id'sini geçir.

        Returns:
            List[Dict]: Tedavi seansları listesi (id DESC = kronolojik, yeni önce)
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                query = '''
                    SELECT ts.id, ts.session_date, ts.start_time, ts.end_time, ts.duration_minutes,
                           ts.treatment_mode, ts.target_condition, ts.frequency_hz, ts.intensity_mt,
                           ts.pulse_duration_ms, ts.operator_name, ts.operator_email, ts.patient_notes, ts.session_status,
                           COALESCE(sp_name.parameter_value, ts.patient_name) as patient_name,
                           sp_surname.parameter_value as patient_surname,
                           sp_age.parameter_value as patient_age,
                           sp_species.parameter_value as patient_species,
                           sp_breed.parameter_value as patient_breed,
                           sp_weight.parameter_value as patient_weight,
                           sp_owner.parameter_value as patient_owner,
                           sp_vet.parameter_value as patient_vet_contact,
                           sp_veteriner.parameter_value as patient_veteriner,
                           sp_duration.parameter_value as treatment_duration,
                           COALESCE(NULLIF(sp_owner_email.parameter_value, ''), pt.owner_email) as owner_email
                    FROM treatment_sessions ts
                    LEFT JOIN session_parameters sp_name ON ts.id = sp_name.session_id AND sp_name.parameter_name = 'patient_name'
                    LEFT JOIN session_parameters sp_surname ON ts.id = sp_surname.session_id AND sp_surname.parameter_name = 'patient_surname'
                    LEFT JOIN session_parameters sp_age ON ts.id = sp_age.session_id AND sp_age.parameter_name = 'patient_age'
                    LEFT JOIN session_parameters sp_species ON ts.id = sp_species.session_id AND sp_species.parameter_name = 'patient_species'
                    LEFT JOIN session_parameters sp_breed ON ts.id = sp_breed.session_id AND sp_breed.parameter_name = 'patient_breed'
                    LEFT JOIN session_parameters sp_weight ON ts.id = sp_weight.session_id AND sp_weight.parameter_name = 'patient_weight'
                    LEFT JOIN session_parameters sp_owner ON ts.id = sp_owner.session_id AND sp_owner.parameter_name = 'patient_owner'
                    LEFT JOIN session_parameters sp_vet ON ts.id = sp_vet.session_id AND sp_vet.parameter_name = 'patient_vet_contact'
                    LEFT JOIN session_parameters sp_veteriner ON ts.id = sp_veteriner.session_id AND sp_veteriner.parameter_name = 'patient_veteriner'
                    LEFT JOIN session_parameters sp_duration ON ts.id = sp_duration.session_id AND sp_duration.parameter_name = 'duration'
                    LEFT JOIN session_parameters sp_owner_email ON ts.id = sp_owner_email.session_id AND sp_owner_email.parameter_name = 'patient_owner_email'
                    LEFT JOIN patients pt ON ts.patient_id = pt.id
                    WHERE 1=1
                '''
                params = []

                if start_date:
                    query += ' AND session_date >= ?'
                    params.append(start_date)

                if end_date:
                    query += ' AND session_date <= ?'
                    params.append(end_date)

                if treatment_mode:
                    query += ' AND treatment_mode = ?'
                    params.append(treatment_mode)

                # audit B-8.2: keyset (cursor) pagination — before_id verilirse ondan ESKI (daha kucuk id)
                # satirlar. id PK (monoton+benzersiz, indexli) → buyuk-OFFSET taramasi YOK + araya yeni
                # seans girse de sayfa kaymasi/atlama YOK (offset'in aksine). id DESC = kronolojik (yeni once);
                # pratikte session_date DESC ile ozdes (id insertion-order = tedavi-baslama-order).
                if before_id is not None:
                    query += ' AND ts.id < ?'
                    params.append(int(before_id))

                # DENETIM P3: cagiranlar (CSV export, PDF) istenen id kumesini SQL'e HIC
                # gecirmiyor; 10.000 satirlik tam sonucu 11 LEFT JOIN ile cekip Python'da
                # filtreliyorlardi (olculen tepe ~24 MB + gereksiz JOIN isi). Filtre artik
                # SQL'de: yalnizca istenen satirlar okunur/materyalize edilir.
                # GUVENLIK: id'ler int()'e zorlanir → SQL enjeksiyonu yuzeyi yok.
                # None = filtre YOK (geriye uyumlu). BOS LISTE = "hicbir kayit" demektir:
                # istemci ?session_ids=, gonderdiginde filtreyi yok sayip TUM KLINIGI dokmek
                # KVKK ihlalidir ("Benim Seanslarim" secili iken tum-klinik PII dokumu).
                if session_ids is not None:
                    _ids = [int(x) for x in session_ids]
                    if not _ids:
                        return []
                    query += f" AND ts.id IN ({','.join('?' * len(_ids))})"
                    params.extend(_ids)

                query += ' ORDER BY ts.id DESC LIMIT ?'
                # DoS-clamp: istemci-kontrollü limit'i [1,500]'e sabitle (get_ai_analyses ile tutarlı) →
                # limit=99999999 ile devasa fetch/RAM engellenir. Audit P2: iç export/PDF yolları
                # (internal_full=True) TAM-geçmiş çektiği için daha yüksek kapak — eskiden 500'e sessizce
                # kırpılıyor, >500 seanslı klinikte eski medikal kayıtlar 'tümü indirildi' denip düşüyordu.
                _cap = 100000 if internal_full else 500
                params.append(max(1, min(int(limit), _cap)))

                cursor.execute(query, params)
                rows = cursor.fetchall()

                # Sonuçları sözlük formatına çevir
                columns = [desc[0] for desc in cursor.description]
                sessions = []

                for row in rows:
                    session = dict(zip(columns, row))
                    sessions.append(session)

                return sessions

        except _DB_ERROR as e:
            self.logger.error(f"Geçmiş getirme hatası: {e}")
            raise

    def get_session_details(self, session_id: int) -> Optional[Dict]:
        """
        Belirli bir seansın detaylarını getir

        Args:
            session_id: Seans ID'si

        Returns:
            Dict: Seans detayları ve parametreleri
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Ana seans bilgileri
                cursor.execute(
                    '''
                    SELECT * FROM treatment_sessions WHERE id = ?
                ''',
                    (session_id,),
                )

                session_row = cursor.fetchone()
                if not session_row:
                    return None

                columns = [desc[0] for desc in cursor.description]
                session = dict(zip(columns, session_row))

                # Parametreler
                cursor.execute(
                    '''
                    SELECT parameter_name, parameter_value, parameter_unit
                    FROM session_parameters WHERE session_id = ?
                ''',
                    (session_id,),
                )

                parameters = {}
                for param_row in cursor.fetchall():
                    param_name, param_value, param_unit = param_row
                    parameters[param_name] = {'value': param_value, 'unit': param_unit}

                session['parameters'] = parameters
                return session

        except _DB_ERROR as e:
            self.logger.error(f"Seans detayları getirme hatası: {e}")
            raise

    def get_statistics(self) -> Dict:
        """
        Tedavi istatistiklerini getir

        Returns:
            Dict: İstatistik bilgileri
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                stats = {}

                # Toplam seans sayısı
                cursor.execute('SELECT COUNT(*) FROM treatment_sessions')
                stats['total_sessions'] = cursor.fetchone()[0]

                # Tamamlanan seans (mobil KPI fallback 'completed_sessions' okuyor)
                cursor.execute(
                    "SELECT COUNT(*) FROM treatment_sessions WHERE LOWER(COALESCE(session_status,'')) = 'completed'"
                )
                stats['completed_sessions'] = cursor.fetchone()[0]

                # Bu ay seans sayısı
                current_month = datetime.now().strftime('%Y-%m')
                cursor.execute(
                    '''
                    SELECT COUNT(*) FROM treatment_sessions
                    WHERE session_date LIKE ?
                ''',
                    (f"{current_month}%",),
                )
                stats['monthly_sessions'] = cursor.fetchone()[0]

                # Tedavi modlarına göre dağılım
                cursor.execute('''
                    SELECT treatment_mode, COUNT(*)
                    FROM treatment_sessions
                    GROUP BY treatment_mode
                ''')
                stats['mode_distribution'] = dict(cursor.fetchall())

                # Ortalama seans süresi
                cursor.execute('''
                    SELECT AVG(duration_minutes)
                    FROM treatment_sessions
                    WHERE duration_minutes IS NOT NULL
                ''')
                avg_duration = cursor.fetchone()[0]
                stats['average_duration'] = round(avg_duration, 1) if avg_duration else 0

                return stats

        except _DB_ERROR as e:
            self.logger.error(f"İstatistik getirme hatası: {e}")
            raise

    def update_session_finalized_extras(
        self, session_id: int, notes: str = None, frequency_hz=None, intensity_mt=None
    ) -> None:
        """ZATEN kapatilmis (finalized) bir seansta YALNIZ not/parametre alanlarini gunceller.

        DENETIM P1: gozlem-notu akisi (POST /api/session/notes) eskiden end_session'i TEKRAR
        cagiriyordu; end_session ise end_time / duration_minutes / session_status alanlarini
        KOSULSUZ yeniden yaziyor ve duration_minutes=None gelirse sureyi `now - start` ile
        YENIDEN hesapliyor. Sonuc: /stop'un yazdigi GERCEK tedavi suresi, istemcinin gonderdigi
        PLANLANAN sure ile (4 dk -> 20 dk) ya da notun yazildigi ana kadar gecen sureyle
        (45 dk sonra not -> 65 dk) eziliyordu = tibbi kayit bozulmasi. Bu metod zaman/durum
        alanlarina DOKUNMAZ; yalnizca verilen alanlari gunceller.
        """
        try:
            self._ensure_write_guardrail()
            if not session_id:
                return
            sets, vals = [], []
            if notes is not None:
                sets.append('patient_notes = ?')
                vals.append(self._redact_pii(notes))
            if frequency_hz is not None:
                sets.append('frequency_hz = ?')
                vals.append(frequency_hz)
            if intensity_mt is not None:
                sets.append('intensity_mt = ?')
                vals.append(intensity_mt)
            if not sets:
                return
            sets.append('updated_at = CURRENT_TIMESTAMP')
            vals.append(int(session_id))
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # SET parcalari yalnizca yukaridaki SABIT literallerden gelir (kullanici girdisi
                # DEGIL); tum degerler parametrelidir → enjeksiyon yuzeyi yok.
                cursor.execute('UPDATE treatment_sessions SET ' + ', '.join(sets) + ' WHERE id = ?', vals)
                conn.commit()
            self.logger.info(f"Kapatilmis seansin not/parametreleri guncellendi: ID {session_id}")
        except _DB_ERROR as e:
            self.logger.error(f"update_session_finalized_extras hatasi: {e}")

    def update_session_notes(self, session_id: int, notes: str):
        """
        Tedavi seansının notlarını güncelle

        Args:
            session_id: Güncellenecek seans ID'si
            notes: Yeni notlar
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    '''
                    UPDATE treatment_sessions
                    SET patient_notes = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''',
                    (self._redact_pii(notes), session_id),
                )  # Audit P3: end_session ile tutarlı PII maskesi (şifresiz modda da uygula)

                conn.commit()
                self.logger.info(f"Seans notları güncellendi: ID {session_id}")

        except _DB_ERROR as e:
            self.logger.error(f"Seans notları güncelleme hatası: {e}")
            raise

    def delete_session(self, session_id: int):
        """
        Tedavi seansını sil

        Args:
            session_id: Silinecek seans ID'si
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Önce parametreleri sil
                cursor.execute('DELETE FROM session_parameters WHERE session_id = ?', (session_id,))
                # Çocuk kayıtları sil — FK ON DELETE CASCADE yok; aksi halde veri-içeren seansı
                # silmek FOREIGN KEY hatasıyla 500 döner.
                cursor.execute('DELETE FROM sensor_samples WHERE session_id = ?', (session_id,))
                cursor.execute('DELETE FROM session_events WHERE session_id = ?', (session_id,))
                # P2 audit 2026-06-28: per-bobin run tablolari da silinsin (eskiden orphan kaliyordu).
                cursor.execute(
                    'DELETE FROM sensor_run_summary WHERE coil_run_id IN '
                    '(SELECT id FROM session_coil_runs WHERE session_id = ?)',
                    (session_id,),
                )
                cursor.execute('DELETE FROM session_coil_runs WHERE session_id = ?', (session_id,))

                # Sonra seansı sil
                cursor.execute('DELETE FROM treatment_sessions WHERE id = ?', (session_id,))

                conn.commit()
                self.logger.info(f"Tedavi seansı silindi: ID {session_id}")

        except _DB_ERROR as e:
            self.logger.error(f"Seans silme hatası: {e}")
            raise

    def delete_sessions_bulk(self, session_ids) -> int:
        """Birden çok seansı TEK İŞLEMDE (atomik) siler; silinen seans sayısını döndürür.

        ⚠️ NEDEN AYRI BİR METOT, NEDEN DÖNGÜYLE `delete_session` DEĞİL:
        200 kaydı tek tek silerken 137.'de hata çıkarsa yarısı gitmiş, yarısı durur ve operatör
        HANGİSİNİN gittiğini bilemez. Geri alınamaz bir işlemde "kısmen oldu" en kötü sonuçtur.
        Burada hepsi tek transaction: ya hepsi gider ya hiçbiri. (Hasta tarafındaki
        `clear_all_patients` atomikliği ile aynı gerekçe — audit P3.)

        ⚠️ ÇOCUK TABLOLAR ÖNCE: FK ON DELETE CASCADE YOK. `delete_session` ile AYNI tablo
        listesi kullanılır; ayrışırsa burada orphan satır kalır (P2 denetiminde bir kez oldu).
        """
        kimlikler = []
        for x in session_ids or ():
            try:
                kimlikler.append(int(x))
            except (TypeError, ValueError):
                continue
        kimlikler = sorted(set(kimlikler))
        if not kimlikler:
            return 0
        if len(kimlikler) > self.TOPLU_SILME_AZAMI:
            raise ValueError(f"Tek istekte en fazla {self.TOPLU_SILME_AZAMI} seans silinebilir.")
        try:
            self._ensure_write_guardrail()
            yer = ",".join("?" for _ in kimlikler)
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f'DELETE FROM session_parameters WHERE session_id IN ({yer})', kimlikler)
                cursor.execute(f'DELETE FROM sensor_samples WHERE session_id IN ({yer})', kimlikler)
                cursor.execute(f'DELETE FROM session_events WHERE session_id IN ({yer})', kimlikler)
                cursor.execute(
                    'DELETE FROM sensor_run_summary WHERE coil_run_id IN '
                    f'(SELECT id FROM session_coil_runs WHERE session_id IN ({yer}))',
                    kimlikler,
                )
                cursor.execute(f'DELETE FROM session_coil_runs WHERE session_id IN ({yer})', kimlikler)
                cursor.execute(f'DELETE FROM treatment_sessions WHERE id IN ({yer})', kimlikler)
                silinen = cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
                conn.commit()
                self.logger.info("TOPLU seans silme: %d istendi, %d silindi.", len(kimlikler), silinen)
                return silinen
        except _DB_ERROR as e:
            self.logger.error(f"Toplu seans silme hatası: {e}")
            raise

    def record_session_event(
        self, session_id: Optional[int], event_type: str, payload: Optional[Dict] = None, severity: str = 'info'
    ) -> Optional[int]:
        """Seans olayını local event tablosuna kaydet."""
        try:
            self._ensure_write_guardrail()
            payload_json = json.dumps(payload or {}, ensure_ascii=True)
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    '''
                    INSERT INTO session_events
                    (event_uuid, session_id, event_type, severity, payload, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''',
                    (str(uuid.uuid4()), session_id, event_type, severity, payload_json, datetime.now().timestamp()),
                )
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            self.logger.warning(f"Session event kaydedilemedi: {e}")
            return None

    def upsert_patient(self, patient: Dict) -> Optional[int]:
        """Hasta kaydini ekle/guncelle. patient_uuid varsa ona gore, yoksa
        name (+owner_name) ile eslestir; varsa UPDATE, yoksa INSERT eder.
        Geri donus: patient_id (int) veya hata halinde None."""
        try:
            self._ensure_write_guardrail()
            name = patient.get('name')
            if not name:
                self.logger.warning("upsert_patient: 'name' zorunlu, atlandi")
                return None

            patient_uuid = patient.get('patient_uuid')
            owner_name = patient.get('owner_name')
            now_iso = datetime.now().isoformat(sep=' ', timespec='seconds')

            # B-1.3: at-rest şifreleme YOKken kişi-tanımlayıcı PII'yi maskele (dedup öncesi de →
            # maskeli name/owner tutarlı eşleşir). Üretimde (SQLCipher) değerler AYNEN geçer.
            name = self._redact_pii(name)
            owner_name = self._redact_pii(owner_name)
            _owner_email = self._redact_pii(patient.get('owner_email') or None)
            _vet_contact = self._redact_pii(patient.get('vet_contact'))
            _veteriner = self._redact_pii(patient.get('veteriner'))
            _notes = self._redact_pii(patient.get('notes'))

            with self._get_connection() as conn:
                cursor = conn.cursor()

                existing_id = None
                if patient_uuid:
                    cursor.execute('SELECT id FROM patients WHERE patient_uuid = ?', (patient_uuid,))
                    row = cursor.fetchone()
                    if row:
                        existing_id = int(row['id'])
                else:
                    # name (+ owner_name) ile eslestir
                    if owner_name is not None:
                        cursor.execute(
                            'SELECT id FROM patients WHERE name = ? AND IFNULL(owner_name, "") = ? ORDER BY id LIMIT 1',
                            (name, owner_name),
                        )
                    else:
                        cursor.execute(
                            'SELECT id FROM patients WHERE name = ? AND owner_name IS NULL ORDER BY id LIMIT 1', (name,)
                        )
                    row = cursor.fetchone()
                    if row:
                        existing_id = int(row['id'])

                if existing_id is not None:
                    cursor.execute(
                        '''
                        UPDATE patients SET
                            patient_uuid = COALESCE(?, patient_uuid),
                            name = ?,
                            species = ?,
                            breed = ?,
                            age = ?,
                            weight_kg = ?,
                            owner_name = ?,
                            owner_email = COALESCE(?, owner_email),
                            vet_contact = ?,
                            veteriner = ?,
                            notes = ?,
                            updated_at = ?,
                            sync_status = 0
                        WHERE id = ?
                    ''',
                        (
                            patient_uuid,
                            name,
                            patient.get('species'),
                            patient.get('breed'),
                            patient.get('age'),
                            patient.get('weight_kg'),
                            owner_name,
                            _owner_email,
                            _vet_contact,
                            _veteriner,
                            _notes,
                            now_iso,
                            existing_id,
                        ),
                    )
                    conn.commit()
                    return existing_id

                cursor.execute(
                    '''
                    INSERT INTO patients
                    (patient_uuid, name, species, breed, age, weight_kg, owner_name,
                     owner_email, vet_contact, veteriner, notes, updated_at, sync_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                ''',
                    (
                        patient_uuid,
                        name,
                        patient.get('species'),
                        patient.get('breed'),
                        patient.get('age'),
                        patient.get('weight_kg'),
                        owner_name,
                        _owner_email,
                        _vet_contact,
                        _veteriner,
                        _notes,
                        now_iso,
                    ),
                )
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            self.logger.error(f"Hasta upsert hatası: {e}")
            return None

    def set_session_meta(self, session_id, *, started_epoch=None, ended_epoch=None, patient_id=None) -> None:
        """treatment_sessions satirina yeni kolonlari (gercek wall-clock epoch + patient_id FK)
        baglar. Mevcut start_session/end_session bu Asama-2 kolonlarini bilmedigi icin ayrica cagrilir.
        Yalniz verilen alanlar UPDATE edilir; hepsi best-effort."""
        try:
            self._ensure_write_guardrail()
            sets, params = [], []
            if started_epoch is not None:
                sets.append('started_epoch = ?')
                params.append(float(started_epoch))
            if ended_epoch is not None:
                sets.append('ended_epoch = ?')
                params.append(float(ended_epoch))
            if patient_id is not None:
                sets.append('patient_id = ?')
                params.append(int(patient_id))
            if not sets:
                return
            params.append(int(session_id))
            with self._get_connection() as conn:
                conn.execute('UPDATE treatment_sessions SET ' + ', '.join(sets) + ' WHERE id = ?', params)
                conn.commit()
        except Exception as e:
            self.logger.error(f"set_session_meta hatası: {e}")

    def set_session_parameter(
        self, session_id, parameter_name: str, parameter_value: str, parameter_unit: str = ''
    ) -> None:
        """Seansa tek bir parametre yaz (varsa GUNCELLE, yoksa EKLE) — idempotent.
        React seans-akisinda hasta meta-parametrelerini (orn. patient_owner_email)
        kaydetmek icin. Best-effort: hata seansi/donanimi DURDURMAZ."""
        try:
            self._ensure_write_guardrail()
            if not session_id or not parameter_name:
                return
            _pv = str(parameter_value)
            if parameter_name in self._PII_PARAM_NAMES:
                _pv = self._redact_pii(_pv)  # B-1.3: şifresiz DB'ye gerçek PII yazma
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'UPDATE session_parameters SET parameter_value = ?, parameter_unit = ? '
                    'WHERE session_id = ? AND parameter_name = ?',
                    (_pv, parameter_unit, int(session_id), parameter_name),
                )
                if cursor.rowcount == 0:
                    cursor.execute(
                        'INSERT INTO session_parameters '
                        '(session_id, parameter_name, parameter_value, parameter_unit) '
                        'VALUES (?, ?, ?, ?)',
                        (int(session_id), parameter_name, _pv, parameter_unit),
                    )
                conn.commit()
        except Exception as e:
            self.logger.error(f"set_session_parameter hatası: {e}")
