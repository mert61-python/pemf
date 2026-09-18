# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""BAKIM · DISA-AKTARIM · SAKLAMA POLITIKASI — (B4 · 6/N, 2026-09-18).

⚠️ AYRILMA GEREKCESI: bkz. `database/thdb_outbox.py` bas yorumu (B4 · 1/N).
Bu kume TABLOYA degil, VERITABANININ KENDISINE dokunur: yedek alma, butunluk denetimi,
disk durumu, satir disa/ice aktarma, saklama suresi politikasi ve `system_settings`.

⚠️ `apply_data_retention_policy` GERI DONUSSUZ SILME yapar. Saklama suresi
`_get_system_setting`/`_set_system_setting` uzerinden okunur — yani politika KODDA SABIT
DEGIL, veritabaninda tutulur. Buradaki bir hata "eski kayitlari temizledim" diye TIBBI
KAYIT siler; degisiklik yaparken `tests/test_kvkk_anonymization.py` ve saklama kapilarini
KIRMIZI gormeden birakmayin.

⚠️ `import_rows` / `export_rows` `sqlite_master` uzerinden calisir (sema-bagimsiz kopyalama).
Cihaz tasima yolunun parcasidir (bellek: `pemf-veri-sahipligi-tasima` — kayitlar MAKINEDE
kalir, disa aktarma OPERATORUN acik eylemidir).

⚠️ GOVDELER DEGISTIRILMEDI — AST ile bayt bayt tasindi.

`self` uzerinden kullandigi ve ANA SINIFTA kalan uyeler: `_get_connection`, `logger`,
`db_path`, `app_data_dir`.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Any, Dict, List, Optional


class BakimKarisimi:
    def get_disk_space_status(self) -> Dict[str, object]:
        """DB volume disk alanı durumunu döndür."""
        usage = self._disk_usage_provider(self.db_path.parent)
        free_mb = int(usage.free / (1024 * 1024))
        return {
            'total_bytes': int(usage.total),
            'used_bytes': int(usage.used),
            'free_bytes': int(usage.free),
            'free_mb': free_mb,
            'critical': free_mb < self.MIN_FREE_DISK_MB,
            'threshold_mb': self.MIN_FREE_DISK_MB,
        }

    def _get_system_setting(self, key: str) -> Optional[str]:
        """System setting değeri oku."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT setting_value FROM system_settings WHERE setting_key = ?', (key,))
                row = cursor.fetchone()
                return str(row['setting_value']) if row else None
        except Exception:
            return None

    def _set_system_setting(self, key: str, value: str, description: str = ''):
        """System setting değeri upsert et."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                '''
                INSERT INTO system_settings (setting_key, setting_value, description, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(setting_key) DO UPDATE SET
                    setting_value = excluded.setting_value,
                    description = excluded.description,
                    updated_at = CURRENT_TIMESTAMP
            ''',
                (key, value, description),
            )
            conn.commit()

    def run_integrity_check(self, quick: bool = True) -> Dict[str, object]:
        """SQLite integrity check çalıştır ve sonucu döndür."""
        pragma_name = 'quick_check' if quick else 'integrity_check'
        result = {'ok': False, 'check': pragma_name, 'details': []}
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f'PRAGMA {pragma_name}')
                rows = cursor.fetchall()
                details = [str(row[0]) for row in rows] if rows else ['unknown']
                result['details'] = details
                result['ok'] = len(details) > 0 and details[0].lower() == 'ok'
        except Exception as e:
            result['details'] = [str(e)]
            result['ok'] = False
        return result

    def get_database_health_snapshot(self) -> Dict[str, object]:
        """DB health snapshot: schema, integrity, session/outbox sayıları."""
        health = {
            'db_path': str(self.db_path),
            'schema_version': self.get_schema_version(),
            'at_rest_encrypted': bool(getattr(self, 'at_rest_encrypted', False)),
            'integrity': self.run_integrity_check(quick=True),
            'disk': self.get_disk_space_status(),
            'sessions': {
                'total': 0,
                'active': 0,
                'completed': 0,
                'aborted_recovered': 0,
            },
            'outbox': self.get_outbox_status_counts(),
        }

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT COUNT(*) FROM treatment_sessions')
                health['sessions']['total'] = int(cursor.fetchone()[0])

                cursor.execute("SELECT COUNT(*) FROM treatment_sessions WHERE session_status = 'active'")
                health['sessions']['active'] = int(cursor.fetchone()[0])

                cursor.execute("SELECT COUNT(*) FROM treatment_sessions WHERE session_status = 'completed'")
                health['sessions']['completed'] = int(cursor.fetchone()[0])

                # Audit P3: recover_stale_active_sessions 'ABORTED_DUE_TO_POWER' yazar; eski sorgu
                # 'aborted_recovered' ile HİÇ eşleşmiyordu → güç-kaybı kurtarma sayacı daima 0 (izleme kör).
                cursor.execute("SELECT COUNT(*) FROM treatment_sessions WHERE session_status = 'ABORTED_DUE_TO_POWER'")
                health['sessions']['aborted_recovered'] = int(cursor.fetchone()[0])
        except Exception as e:
            health['integrity']['ok'] = False
            health['integrity']['details'].append(f'health snapshot error: {e}')

        return health

    def run_maintenance(self) -> Dict[str, object]:
        """Periyodik DB bakım işlemleri: checkpoint + optimize + quick_check."""
        report = {
            'checkpoint': None,
            'optimize': False,
            'integrity': None,
        }
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute('PRAGMA wal_checkpoint(TRUNCATE)')
                    row = cursor.fetchone()
                    report['checkpoint'] = list(row) if row else None
                except Exception:
                    report['checkpoint'] = None

                try:
                    cursor.execute('PRAGMA optimize')
                    report['optimize'] = True
                except Exception:
                    report['optimize'] = False

            report['integrity'] = self.run_integrity_check(quick=True)
        except Exception as e:
            report['integrity'] = {'ok': False, 'check': 'quick_check', 'details': [str(e)]}
        return report

    def create_backup(self, backup_path: str) -> bool:
        """Çalışan DB'den dosya yedeği üret (online backup API). DB ŞİFRELİYSE yedek de aynı
        anahtarla ŞİFRELİ olur (plain hedefe yedek hem uyumsuz hem düz-metin PII sızdırır)."""
        try:
            backup_dir = os.path.dirname(backup_path)
            if backup_dir:
                os.makedirs(backup_dir, exist_ok=True)

            with self._get_connection() as src_conn:
                if getattr(self, "at_rest_encrypted", False):
                    key = self._get_sqlcipher_key()
                    sqlcipher = self._import_sqlcipher()
                    dst_conn = sqlcipher.connect(backup_path)
                    dst_conn.execute("PRAGMA key='{}'".format(key.replace("'", "''")))
                else:
                    dst_conn = sqlite3.connect(backup_path)
                try:
                    src_conn.backup(dst_conn)
                    dst_conn.commit()
                finally:
                    dst_conn.close()
            return True
        except Exception as e:
            self.logger.error(f"DB backup hatası: {e}")
            return False

    def apply_data_retention_policy(
        self,
        sensor_retain_days: int = 90,
        event_retain_days: int = 365,
        dead_outbox_retain_days: int = 30,
        pii_retain_days: int = 365,
        #: ⚠️ DOZ kaydı AYRI saat (denetim 2026-08-17). Eskiden `sensor_retain_days`e bağlıydı;
        #: uygulanan doz 90 günde siliniyordu. `0 = adım kapalı` sözleşmesi burada da geçerli.
        dose_retain_days: int = 3650,
    ) -> Dict[str, int]:
        """Toplu retention policy uygula (ticari operasyon bakımı).

        DENETIM P2: her sure <= 0 ise O ADIM ATLANIR (kapali). Eskiden adimlar kosulsuzdu ve
        cagiran hicbir parametre gecirmedigi icin sabit 90/365/30/365 gun ZORLANIYORDU:
        bobin-calisma kayitlari ve seans olaylari GERI DONUSSUZ siliniyor, hasta/operator
        adlari maskeleniyordu — opt-out YOKTU. Tibbi-hukuki saklama suresi ulkeye/kliniğe gore
        degisir (KVKK silmeyi ister, dava dosyasi saklamayi) → operator karari olmali.
        Yapilandirma: services/headless_db_maintenance.py (PEMF_RETAIN_* env degiskenleri).
        """
        report = {
            'sensor_samples_removed': 0,
            'coil_runs_removed': 0,
            'session_events_removed': 0,
            'dead_outbox_removed': 0,
            'sessions_pii_redacted': 0,
            'parameters_pii_redacted': 0,
        }

        if sensor_retain_days and sensor_retain_days > 0:
            report['sensor_samples_removed'] = self.purge_old_sensor_samples(sensor_retain_days)
        # ⚠️ DOZ adımı SENSÖR bloğundan ÇIKARILDI (denetim 2026-08-17): uygulanan doz, telemetri
        # saklama süresiyle silinemez. Rapor anahtarı `coil_runs_removed` DEĞİŞMEDİ.
        if dose_retain_days and dose_retain_days > 0:
            report['coil_runs_removed'] = self.purge_old_coil_runs(dose_retain_days)
        if event_retain_days and event_retain_days > 0:
            report['session_events_removed'] = self.purge_old_session_events(event_retain_days)
        if dead_outbox_retain_days and dead_outbox_retain_days > 0:
            report['dead_outbox_removed'] = self.purge_old_dead_outbox(dead_outbox_retain_days)

        # ── PII MASKELEME: OPERATÖR ONAYI OLMADAN ÇALIŞMAZ (2026-08-09 denetimi, Tier 1) ──────
        # Maskeleme GERİ DÖNÜŞSÜZDÜR ve tamamen SESSİZ çalışıyordu: klinik 366. günde hasta adı
        # yerine `[REDACTED]` görüyor, sebebini hiçbir yerde bulamıyor, "veritabanım bozuldu"
        # diye destek arıyordu. Süre yalnız bir ortam değişkeniyle (PEMF_RETAIN_PII_DAYS)
        # ayarlanabiliyordu — hiçbir veteriner bunu bilmez.
        #
        # Yeni kural: maskelenecek KAYIT VARSA ve operatör bunu ONAYLAMAMIŞSA, hiçbir şey
        # maskelenmez; rapor `pii_pending` ile kaç kaydın beklediğini söyler ve arayüz sorar.
        # Operatörün seçtiği süre varsa ortam değişkenini EZER (ayar arayüzden yönetilir).
        _secilen = self.pii_suresi_oku()
        if _secilen is not None:
            pii_retain_days = _secilen
        report['pii_pending'] = 0
        if pii_retain_days and pii_retain_days > 0:
            if not self.pii_onayi_var_mi():
                bekleyen = self.redaksiyon_bekleyen_sayisi(pii_retain_days)
                report['pii_pending'] = bekleyen
                if bekleyen:
                    self.logger.warning(
                        "KVKK: %d seans kaydı maskelenmeyi bekliyor ama operatör ONAYI YOK — "
                        "maskeleme YAPILMADI (geri dönüşsüz işlem sessizce uygulanmaz).",
                        bekleyen,
                    )
            else:
                pii_report = self.redact_old_session_pii(pii_retain_days)
                report['sessions_pii_redacted'] = int(pii_report.get('sessions_redacted', 0))
                report['parameters_pii_redacted'] = int(pii_report.get('parameters_redacted', 0))
                # Denetim izi (2026-08-09, Tier 3): maskeleme GERİ DÖNÜŞSÜZ ve arka planda,
                # kimse bakmadan çalışır. Kaç kaydın hangi eşikle maskelendiği yazılmazsa,
                # klinik 366. günde [REDACTED] görüp sebebini hiçbir yerde bulamaz.
                if report['sessions_pii_redacted'] or report['parameters_pii_redacted']:
                    self.denetim_yaz(
                        "retention.pii_maskelendi",
                        scope="otomatik",
                        item_count=report['sessions_pii_redacted'],
                        detail={"gun": int(pii_retain_days), "parametre": report['parameters_pii_redacted']},
                    )

        return report

    def export_rows(self) -> Dict[str, List[Dict]]:
        """Taşınabilir TÜM tabloların satırlarını ham olarak döner (dışa aktarma için).

        `get_session_history`/`get_ai_analyses` limit uyguladığı için taşımada kullanılamaz —
        sessizce kayıp veriye yol açardı.

        ⚠️ `id` kolonları KORUNUR: içe aktarma ilişkileri onlarla yeniden kurar (bkz. üstteki not).
        """
        out: Dict[str, List[Dict]] = {t: [] for t in self._TASINAN_TABLOLAR}
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                mevcut = {r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
                for tablo in self._TASINAN_TABLOLAR:
                    if tablo not in mevcut:  # çok eski DB — tablo henüz yok
                        continue
                    cursor.execute(f"SELECT * FROM {tablo} ORDER BY id ASC")
                    cols = [c[0] for c in cursor.description]
                    out[tablo] = [dict(zip(cols, r)) for r in cursor.fetchall()]
        except Exception:
            self.logger.exception("Dışa aktarma için satırlar okunamadı.")
            raise
        return out

    def import_rows(self, data: Dict[str, List[Dict]], replace: bool = False) -> Dict[str, int]:
        """Dışa aktarılmış satırları geri yükler — İLİŞKİLERİ KORUYARAK.

        ⚠️ `id` DEĞERLERİ korunmaz (AUTOINCREMENT, hedefte çakışabilir) ama İLİŞKİLER korunur:
        her tablo eklenirken ESKİ id → YENİ id eşlemesi tutulur ve çocuk satırların
        `session_id`/`patient_id`/`coil_run_id` kolonları yeniden yazılır. Bu olmadan bir seansın
        bobin-koşuları/telemetrisi hedefte BAŞKA bir seansa bağlanırdı — hastanın verisi başka
        hastanın kaydında görünürdü (bkz. `_ILISKILER` üstündeki denetim notu).

        ⚠️ `replace=True` hedefteki TÜM taşınan tabloları SİLER. Varsayılan `False` EKLER —
        aynı dosyayı iki kez içe aktarmak KAYITLARI ÇOĞALTIR; çağıran (API) bunu boş-hedef
        kuralıyla engeller.

        GERİYE UYUM: v1 yedekleri yalnız `treatment_sessions` + `ai_analyses` içerir; eksik
        tablolar boş geçilir, ilişki eşlemesi yine kurulur (o yedeklerde bağlı satır yoktur).
        """
        sonuc = {t: 0 for t in self._TASINAN_TABLOLAR}
        # tablo -> {eski_id: yeni_id}
        eslem: Dict[str, Dict[Any, int]] = {t: {} for t in self._TASINAN_TABLOLAR}
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if replace:
                # Çocuktan ebeveyne doğru sil (FK ihlali olmasın).
                for tablo in reversed(self._TASINAN_TABLOLAR):
                    try:
                        cursor.execute(f"DELETE FROM {tablo}")
                    except Exception:
                        self.logger.debug("temizlenemedi: %s", tablo, exc_info=True)

            var_olan_tablolar = {
                r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }

            for tablo in self._TASINAN_TABLOLAR:
                satirlar = data.get(tablo) or []
                if not satirlar or tablo not in var_olan_tablolar:
                    continue
                cursor.execute(f"PRAGMA table_info({tablo})")
                gecerli = {r[1] for r in cursor.fetchall()} - {"id"}
                # Bu tablonun hangi kolonları hangi tabloya bakıyor?
                yeniden_bagla = {
                    kol: hedef for (t, kol), hedef in self._ILISKILER.items() if t == tablo and kol in gecerli
                }
                for s in satirlar:
                    # Hedef şemada OLMAYAN kolonları at (eski/yeni sürüm arası uyum).
                    alan = {k: v for k, v in s.items() if k in gecerli}
                    if not alan:
                        continue
                    atla = False
                    for kol, hedef_tablo in yeniden_bagla.items():
                        eski = alan.get(kol)
                        if eski is None:
                            continue  # seansa bağlı olmayan satır (NULL) — normal
                        yeni = eslem[hedef_tablo].get(eski)
                        if yeni is None:
                            # Ebeveyni taşınmamış çocuk satır: SESSİZCE YANLIŞ BAĞLAMAK yerine ATLA.
                            # Yanlış bağlamak, bir hastanın telemetrisini başka bir hastanın
                            # kaydında gösterirdi — sessiz ve teşhis edilemez bir tıbbi hata.
                            self.logger.warning(
                                "İçe aktarma: %s satırı ebeveyni bulunamadığı için atlandı (%s=%r).", tablo, kol, eski
                            )
                            atla = True
                            break
                        alan[kol] = yeni
                    if atla:
                        continue
                    ph = ", ".join("?" for _ in alan)
                    try:
                        cursor.execute(f"INSERT INTO {tablo} ({', '.join(alan)}) VALUES ({ph})", list(alan.values()))
                    except Exception:
                        # UNIQUE çakışması: bu satır hedefte ZATEN VAR (aynı hasta/olay).
                        #
                        # ⚠️ Burada "atla ve devam et" demek YETMEZ: eşlemeye giriş yazılmazsa o
                        # ebeveyne bağlı TÜM çocuk satırlar (seanslar, bobin koşuları, telemetri)
                        # yukarıdaki "ebeveyni bulunamadı" dalına düşüp SESSİZCE ATILIR. Yani tek
                        # bir mükerrer hasta, o hastanın bütün geçmişini yok ederdi.
                        # Doğrusu BİRLEŞTİRMEKtir: mevcut satırın id'sini doğal anahtarla bul ve
                        # eşlemeye yaz → çocuklar mevcut kayda bağlanır.
                        mevcut_id = None
                        dogal = self._DOGAL_ANAHTAR.get(tablo)
                        if dogal and s.get(dogal) is not None:
                            try:
                                r = cursor.execute(f"SELECT id FROM {tablo} WHERE {dogal} = ?", (s[dogal],)).fetchone()
                                mevcut_id = r[0] if r else None
                            except Exception:
                                mevcut_id = None
                        if mevcut_id is not None and s.get("id") is not None:
                            eslem[tablo][s["id"]] = mevcut_id
                            self.logger.info(
                                "İçe aktarma: %s satırı hedefte zaten var, MEVCUT kayda bağlandı (%s=%r).",
                                tablo,
                                dogal,
                                s[dogal],
                            )
                        else:
                            self.logger.warning("İçe aktarma: %s satırı eklenemedi, atlandı.", tablo, exc_info=True)
                        continue
                    if s.get("id") is not None:
                        eslem[tablo][s["id"]] = cursor.lastrowid
                    sonuc[tablo] += 1
            conn.commit()
        return sonuc
