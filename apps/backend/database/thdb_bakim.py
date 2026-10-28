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

`self` uzerinden kullandigi ve ANA SINIFTA kalan uyeler: `MIN_FREE_DISK_MB`, `_DOGAL_ANAHTAR`, `_ILISKILER`,
`_TASINAN_TABLOLAR`, `_disk_usage_provider`, `_get_connection`, `_get_sqlcipher_key`, `_import_sqlcipher`, `db_path`,
`logger`.
"""

from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from utils import ceviri

_SAAT_SUPHESI_DESENI = re.compile(r"^(geride|ileri): cihaz saati (\S+ \S+), son gorulen (\S+ \S+)$")


def saat_suphesi_metni(neden, dil=None):
    """`saat_supheli` DEĞERİ (DB'ye yazılan Türkçe VERİ — değişmez) → ekranda gösterilen metin (istek dilinde). TR çıktı BAYT BAYT
    kayıttaki değerdir; tanınmayan / eski biçimli değer aynen döner (kayıt kaybolmaz)."""
    m = _SAAT_SUPHESI_DESENI.match(str(neden or ""))
    if not m:
        return neden
    if m.group(1) == "geride":
        return ceviri.t("sistem.saat.geride", dil=dil, simdi=m.group(2), tavan=m.group(3))
    return ceviri.t("sistem.saat.ileri", dil=dil, simdi=m.group(2), tavan=m.group(3))


class BakimKarisimi:
    # ── ⚠️ F2-1.2 (2-F incelemesi) · A-73: geri dönüşsüz SÜREYE BAĞLI işlemler (anonimleştirme, PII maskeleme, doz/sensör/olay silmesi)
    # yalnız AKLA YATKIN saatle koşar. Ölçüldü: saat +10 yıl sıçrayınca TEK tur tüm hastaları anonimleştiriyor, tüm dozu siliyordu; BIOS
    # 2000'deyken yapılan tedavi saat düzelince anonimleşip dozu siliniyordu. Son görülen saat ("tavan") DB'de tutulur: saat ondan 1 günden
    # fazla GERİDE ya da `SAAT_SICRAMA_GUN`den fazla İLERİDE ise şüphe KALICI işaretlenir; operatör saati onaylayana (`saat_onayla`) dek bu
    # adımlar ATLANIR (veri kaybı yok — yalnız gecikme). Kapı: tests/test_saat_SICRAMASI_geri_donussuz_islem_yapmaz_A73_F2_1_2.py
    SAAT_TAVANI_ANAHTARI = "saat_tavani"
    SAAT_SUPHELI_ANAHTARI = "saat_supheli"
    #: Bir turdan ötekine saatin (cihaz kapalı kalsa da) en çok ilerleyebileceği gün — aşılırsa ileri sıçrama şüphesi (sahip kararı).
    SAAT_SICRAMA_GUN = 45
    SAAT_GERI_TOLERANS = timedelta(days=1)

    def saat_supheli_mi(self) -> Optional[str]:
        """Onaylanmamış saat şüphesinin nedeni ya da None."""
        return self._get_system_setting(self.SAAT_SUPHELI_ANAHTARI) or None

    def saat_akla_yatkin_mi(self) -> bool:
        """Geri dönüşsüz süreye bağlı adım bu turda koşabilir mi? ASLA istisna atmaz; denetlenemezse False (bu tur atlanır)."""
        try:
            neden = self.saat_supheli_mi()
            if not neden:
                simdi = datetime.now()
                ham = self._get_system_setting(self.SAAT_TAVANI_ANAHTARI)
                tavan = datetime.fromisoformat(ham) if ham else None
                if tavan is not None and simdi < tavan - self.SAAT_GERI_TOLERANS:
                    neden = f"geride: cihaz saati {simdi:%Y-%m-%d %H:%M}, son gorulen {tavan:%Y-%m-%d %H:%M}"
                elif tavan is not None and simdi > tavan + timedelta(days=self.SAAT_SICRAMA_GUN):
                    neden = f"ileri: cihaz saati {simdi:%Y-%m-%d %H:%M}, son gorulen {tavan:%Y-%m-%d %H:%M}"
                if neden:
                    self._set_system_setting(
                        self.SAAT_SUPHELI_ANAHTARI, neden, "A-73: saat suphesi (operator onayi bekleniyor)"
                    )
                elif tavan is None or simdi > tavan:
                    self._set_system_setting(
                        self.SAAT_TAVANI_ANAHTARI, simdi.isoformat(timespec="seconds"), "A-73: son gorulen saat"
                    )
                    return True
                else:
                    return True
            self.logger.warning(
                "SAAT SUPHESI (%s) — anonimlestirme / maskeleme / saklama silmesi YAPILMADI; Ayarlar > Veri Saklama'dan cihaz "
                "saatini dogrulayip onaylayin (A-73).",
                neden,
            )
            return False
        except Exception:
            self.logger.warning(
                "Saat denetimi yapilamadi — geri donussuz saklama adimlari bu turda ATLANDI.", exc_info=True
            )
            return False

    def saat_onayla(self) -> None:
        """Operatör cihaz saatinin DOĞRU olduğunu onayladı: şüphe kalkar, tavan = şimdi."""
        self._set_system_setting(
            self.SAAT_TAVANI_ANAHTARI, datetime.now().isoformat(timespec="seconds"), "A-73: son gorulen saat"
        )
        self._set_system_setting(self.SAAT_SUPHELI_ANAHTARI, "", "A-73: saat suphesi (operator onayladi)")

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
        anahtarla ŞİFRELİ olur (plain hedefe yedek hem uyumsuz hem düz-metin PII sızdırır).

        ⚠️ D2.61 (B-3.70) · D2.63 (B-3.20): yedek GEÇİCİ ada yazılır, açılarak doğrulanır, sonra son ada taşınır
        (`database/yedek_dosyasi.yedek_yaz`) — başarısız deneme hedefte 0 baytlık / yarım dosya BIRAKMAZ, son ad yalnız doğrulanmış
        yedekle oluşur. Kapılar: tests/test_at_rest_bayragi_ve_yarim_yedek_D261.py · tests/test_yerel_yedek_penceresi_KORUNUR_D263.py"""
        from database.yedek_dosyasi import yedek_yaz

        try:
            backup_dir = os.path.dirname(backup_path)
            if backup_dir:
                os.makedirs(backup_dir, exist_ok=True)

            with self._get_connection() as src_conn:
                if getattr(self, "at_rest_encrypted", False):
                    # ⚠️ A-13 (sahip kararı): yedek BİRİNCİL anahtarla şifrelenir — DB D-3 legacy anahtarla açılmış olsa da.
                    # Kurtarma zarfı yalnız birincil `sqlcipher_key`i taşır; "açan anahtarla" yazılan yedek makine dışında
                    # açılamazdı (regresyon). SQLCipher yedek API'si farklı anahtarlar arasında çalışır, çıktı hedef anahtarla.
                    # ⚠️ D2.62 (B-3.71): anahtar çözümü bu `try` içinde — düşerse yedek yok, artık yok. BOŞ anahtar REDDEDİLİR,
                    # hedef dosya hiç açılmaz: `PRAGMA key=''` kitaplığa bırakılmaz (boş anahtarı "şifresiz" sayan sürümde
                    # klinik verisinin düz-metin kopyası yazılırdı). Kapı: tests/test_yedek_ANA_anahtarla_bos_anahtar_reddi_D262_A13.py
                    key = self._get_sqlcipher_key()
                    if not key:
                        self.logger.error(
                            "DB yedegi ALINMADI: at-rest sifreli DB icin birincil anahtar BOS dondu (sir kaydi okunamadi/silinmis) "
                            "— bos anahtarla yedek yazilmaz (duz-metin kopya riski). Sir deposunu denetleyin."
                        )
                        return False
                    yedek_yaz(src_conn, backup_path, self._import_sqlcipher(), key, self.logger)
                else:
                    yedek_yaz(src_conn, backup_path, sqlite3, "", self.logger)
            return True
        except Exception as e:
            self.logger.error(f"DB backup hatası: {e}")
            return False

    def yedek_acilir_mi(self, yol, tam: bool = False) -> bool:
        """Bu kurulumun anahtarıyla (birincil — A-13) yedek dosyası açılıyor mu? Rotasyon / tazelik yalnız açılanları sayar
        (D2.63). Düz-metin yedek anahtarsız açılır; şifreli yedek anahtar yoksa AÇILAMAZ sayılır. ASLA istisna atmaz."""
        from database.yedek_dosyasi import yedek_acilir_mi

        mod, key = None, ""
        if getattr(self, "at_rest_encrypted", False):
            try:
                key = self._get_sqlcipher_key() or ""
                mod = self._import_sqlcipher()
            except Exception:
                self.logger.warning(
                    "Yedek dogrulamasi: birincil anahtar cozulemedi — sifreli yedekler ACILAMAZ sayilir.", exc_info=True
                )
                mod, key = None, ""
        return yedek_acilir_mi(yol, mod, key, tam=tam)

    def yedek_sifre_bilgisi(self):
        """⚠️ D2.51 (A-32): bu kurulumun yedek şifrelemesi — `(sqlcipher modülü, BİRİNCİL anahtar)`; düz kurulumda `(None, "")`.

        Ek yedekler (operatör hesapları) klinik DB yedekleriyle AYNI anahtarla şifrelenir: kurtarma zarfı yalnız birincil anahtarı
        taşır (A-13). Şifreli kurulumda anahtar BOŞ dönerse istisna — D2.62 kuralı: boş anahtarla yedek yazılmaz."""
        if not getattr(self, "at_rest_encrypted", False):
            return None, ""
        key = self._get_sqlcipher_key()
        if not key:
            raise RuntimeError(
                "at-rest sifreli kurulumda birincil anahtar BOS dondu — ek yedek yazilmaz (duz-metin kopya riski)"
            )
        return self._import_sqlcipher(), key

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
        # ⚠️ F2-1.2 · A-73: saat akla yatkın değilse HİÇBİR geri dönüşsüz adım koşmaz (bkz. `saat_akla_yatkin_mi`).
        if not self.saat_akla_yatkin_mi():
            report['saat_supheli'] = True
            return report

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
            # D2.55 · A-09: onay BU süreye ve maskeleme kapsamına verilmiş olmalı (süre kısalınca genişleyen kapsam yeni onay ister).
            if not self.pii_onayi_var_mi(pii_retain_days):
                bekleyen = self.redaksiyon_bekleyen_sayisi(pii_retain_days)
                report['pii_pending'] = bekleyen
                if bekleyen is None:
                    # D2.58 (B-3.90): sayılamadı — "0 bekleyen" yazılmaz; ekran da "sayılamadı" der.
                    self.logger.warning(
                        "KVKK: maskelenmeyi bekleyen kayıt sayılamadı — operatöre sorulamıyor; maskeleme YAPILMADI."
                    )
                elif bekleyen:
                    self.logger.warning(
                        "KVKK: %d seans kaydı maskelenmeyi bekliyor ama operatör ONAYI YOK — "
                        "maskeleme YAPILMADI (geri dönüşsüz işlem sessizce uygulanmaz).",
                        bekleyen,
                    )
            else:
                # ⚠️ 2-F incelemesi §10 #18 (D5): izin BİRİMİ — `item_count` seans SÜTUNU maskelenen seans SATIRI, `parametre` parametre SATIRI;
                # operatörün onayladığı / ekranın "N kayıt" dediği ise ETKİLENEN SEANS (`redaksiyon_bekleyen_sayisi`, D2.58 tek ölçütü).
                # Yalnız parametresi maskelenen seans izde hiç görünmüyordu (ölçüldü: onay 2, iz 1 + parametre 1). Maskelemeden HEMEN ÖNCE
                # aynı ölçütle sayılır → iz `etkilenen_seans` (sayılamazsa null); eski anahtarlar eski okuyucular için KALIR.
                # Kapı: tests/test_saklama_izi_SAYAC_birimleri_ACIK_D5E18.py
                etkilenen_seans = self.redaksiyon_bekleyen_sayisi(pii_retain_days)
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
                        detail={
                            "gun": int(pii_retain_days),
                            "parametre": report['parameters_pii_redacted'],
                            "etkilenen_seans": etkilenen_seans,
                        },
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
                # ⚠️ D2-4.3 (2-D incelemesi): tablolar TEK okuma işleminde (WAL anlık görüntüsü) okunur — yazarlar beklemez. Eskiden her
                # SELECT kendi anlık görüntüsüydü: dışa aktarma sürerken commit edilen bir geri yükleme ya da süren tedavinin yeni seansı
                # paketi karıştırıyordu (eski seanslar + yeni bobin koşuları / sensör / olay — seansları pakette YOK); o yedekten geri
                # yüklemede doz kayıtları sessizce düşüyordu (ölçüldü). Kapı: tests/test_disa_aktarma_TUTARLI_anlik_goruntu_D2_4_3.py
                cursor.execute("BEGIN")
                try:
                    mevcut = {
                        r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                    }
                    for tablo in self._TASINAN_TABLOLAR:
                        if tablo not in mevcut:  # çok eski DB — tablo henüz yok
                            continue
                        cursor.execute(f"SELECT * FROM {tablo} ORDER BY id ASC")
                        cols = [c[0] for c in cursor.description]
                        out[tablo] = [dict(zip(cols, r)) for r in cursor.fetchall()]
                finally:
                    conn.rollback()  # salt okuma işlemi kapanır (havuzdaki bağlantı anlık görüntü / kilit tutmaz)
        except Exception:
            self.logger.exception("Dışa aktarma için satırlar okunamadı.")
            raise
        # SGI-1.1 (CH3 · Y152): ÷5 düzeltilmiş satır pakete ÖZGÜN değer + BOŞ işaretle girer. ESKİ sürüm (CH3 öncesi) içe aktarırken
        # işaret / orijinal sütunlarını atar; ÷5'li değer işaretsiz kalır ve o cihaz yükseltilince yeniden bölünürdü (÷25, "orijinal"
        # yanlış — ölçüldü). Böyle her sürüm satırı "eski kayıt" alır: yeni sürüm içe aktarmada bir kez böler (import_rows → göç),
        # eski sürüm kendi eski verisiyle tutarlı saklar ve yükseltmede bir kez bölünür. Yeni → yeni taşımanın sonucu değişmez.
        from utils import mt_duzeltme as _mt

        for _tablo, _alan, _orj in (
            ("sensor_samples", "magnetic_field_mt", "magnetic_field_mt_orijinal"),
            ("sensor_run_summary", "field_avg", "field_avg_orijinal"),
        ):
            for _s in out.get(_tablo) or []:
                if _mt.duzeltildi_mi(_s.get("alan_duzeltme")) and _s.get(_orj) is not None:
                    _s[_alan], _s[_orj], _s["alan_duzeltme"] = _s[_orj], None, _mt.ESKI
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
        # Y131 (S-F2-1.4): REPLACE_ALL'ın korunan / silinen olay sayıları — EKLEMELİ alanlar; uç bunları `data.import` izinin
        # `detail`ine (`**n`) ve yanıtın `counts`una taşır.
        sonuc.update({"kritik_olay_korunan": 0, "kritik_olay_yedekte_vardi": 0, "olay_silinen": 0})
        # tablo -> {eski_id: yeni_id}
        eslem: Dict[str, Dict[Any, int]] = {t: {} for t in self._TASINAN_TABLOLAR}
        from database.db_hatalari import _DB_INTEGRITY

        # ⚠️ D2.52 (B-3.28) + İG-6.5 P2u: işlem BÜTÜNLÜKLÜ — silme ya da ekleme adımlarından biri UNIQUE çakışması DIŞINDA bir
        # hatayla düşerse (kilit, G-Ç, disk dolu) HİÇBİR şey commit edilmez: `_get_connection` geri alır, istisna çağırana yükselir.
        # Eskiden silme hataları `logger.debug` ile YUTULUYORDU (eski + yeni satırlar yan yana, seanslar çiftleniyordu) ve ekleme
        # dalı her istisnayı "zaten var" sayıyordu (DB kilitliyken 0 satır yazılıp "success" dönülüyordu — ölçüldü).
        # Kapı: tests/test_geri_yukleme_BUTUNLUKLU_D252_Y12_Y111.py
        with self._get_connection() as conn:
            cursor = conn.cursor()
            var_olan_tablolar = {
                r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }
            korunacak: List[Dict[str, Any]] = []
            eski_seans_uuid: Dict[Any, Any] = {}
            if replace:
                # ⚠️ Y131 (S-F2-1.4, sahip · A-07): yedekten SONRA kaydedilmiş KRİTİK olaylar (ACİL DURDUR, mandal sıfırlama, hekim
                # onay / ret izi …) SİLİNMEZ — silmeden ÖNCE okunur, yedek yüklendikten sonra yedekte olmayanları aynı işlemde geri yazılır.
                # Eskiden REPLACE_ALL `session_events`in tamamını siliyordu (ölçüldü). Kapı: tests/test_geri_yukleme_KRITIK_olaylari_KORUR_Y131.py
                if "session_events" in var_olan_tablolar:
                    korunacak, eski_seans_uuid = self._kritik_olaylari_oku(cursor)
                    toplam = int(cursor.execute("SELECT COUNT(*) FROM session_events").fetchone()[0])
                    sonuc["olay_silinen"] = toplam - len(korunacak)
                # Çocuktan ebeveyne doğru sil (FK ihlali olmasın). Hata YUTULMAZ (yukarıdaki not); yalnız bu sürümde
                # olmayan tablo atlanır.
                for tablo in reversed(self._TASINAN_TABLOLAR):
                    if tablo in var_olan_tablolar:
                        cursor.execute(f"DELETE FROM {tablo}")

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
                    except _DB_INTEGRITY:
                        # UNIQUE çakışması: bu satır hedefte ZATEN VAR (aynı hasta/olay). ⚠️ P2u: YALNIZ bütünlük hatası
                        # buraya girer; kilit / G-Ç hatası yükselir ve işlem geri alınır.
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
            if korunacak:
                self._kritik_olaylari_geri_yaz(cursor, korunacak, eski_seans_uuid, sonuc)
            conn.commit()
            if replace:
                # F2-2.3 (Y13 · D2.29 ilkesi): REPLACE_ALL'ın sildiği eski kayıtların sayfaları denetim noktasına kadar ana dosyada kalıyordu.
                self._silme_sonrasi_denetim_noktasi(conn, "REPLACE_ALL ice aktarma")
        # CH3 · Y152: CH3 ÖNCESİ bir dışa aktarım dosyasının satırları düzeltme işareti TAŞIMAZ ('' = eski, ~5× ölçek) → aynı göç
        # içe aktarmadan sonra yeniden uygulanır (CH3 sonrası dosyanın 'yok' / 'bolu5' satırlarına dokunmaz). Ayrı işlem: düşerse
        # içe aktarma geri alınmaz; göç ayarı "bekliyor"a çekilir → bir sonraki açılış yeniden dener (günlüğe yazılır).
        _goc = getattr(self, "_mt_bolu5_gocu", None)
        if callable(_goc):
            _goc(zorla=True)
        return sonuc

    def _kritik_olaylari_oku(self, cursor) -> tuple:
        """Y131: REPLACE_ALL silmeden ÖNCE mevcut kritik olaylar (`KRITIK_OLAY_ONEMLERI` / `KRITIK_OLAY_TURLERI` — D2.50 saklama
        kuralıyla AYNI tek kaynak) + bağlı oldukları seansların `session_uuid`'i (yedekte aynı seans varsa yeniden bağlamak için)."""
        on_yer = ",".join("?" for _ in self.KRITIK_OLAY_ONEMLERI)
        tur_yer = ",".join("?" for _ in self.KRITIK_OLAY_TURLERI)
        cursor.execute(
            f"SELECT * FROM session_events WHERE severity IN ({on_yer}) OR event_type IN ({tur_yer})",
            (*self.KRITIK_OLAY_ONEMLERI, *self.KRITIK_OLAY_TURLERI),
        )
        kolonlar = [d[0] for d in cursor.description]
        olaylar = [dict(zip(kolonlar, tuple(r))) for r in cursor.fetchall()]
        seans_uuid: Dict[Any, Any] = {}
        for sid in {o.get("session_id") for o in olaylar if o.get("session_id") is not None}:
            r = cursor.execute("SELECT session_uuid FROM treatment_sessions WHERE id = ?", (sid,)).fetchone()
            if r and r[0]:
                seans_uuid[sid] = r[0]
        return olaylar, seans_uuid

    def _kritik_olaylari_geri_yaz(self, cursor, olaylar, eski_seans_uuid, sonuc) -> None:
        """Y131: yedekte OLMAYAN (event_uuid) korunan kritik olaylar geri yazılır — aynı işlem, hata YUTULMAZ (D2.52). Seansı yedekte aynı
        `session_uuid` ile varsa yeni kimliğine bağlanır; yoksa olay seanssız (NULL) korunur — seans satırı yedeğe göre değişti."""
        gecerli = {r[1] for r in cursor.execute("PRAGMA table_info(session_events)").fetchall()} - {"id"}
        for olay in olaylar:
            if cursor.execute(
                "SELECT 1 FROM session_events WHERE event_uuid = ?", (olay.get("event_uuid"),)
            ).fetchone():
                sonuc["kritik_olay_yedekte_vardi"] += 1
                continue
            alan = {k: v for k, v in olay.items() if k in gecerli}
            yeni_seans = None
            uuid_ = eski_seans_uuid.get(olay.get("session_id"))
            if uuid_:
                r = cursor.execute("SELECT id FROM treatment_sessions WHERE session_uuid = ?", (uuid_,)).fetchone()
                yeni_seans = r[0] if r else None
            alan["session_id"] = yeni_seans
            ph = ", ".join("?" for _ in alan)
            cursor.execute(f"INSERT INTO session_events ({', '.join(alan)}) VALUES ({ph})", list(alan.values()))
            sonuc["kritik_olay_korunan"] += 1
