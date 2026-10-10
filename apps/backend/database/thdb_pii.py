# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""PII REDAKSIYONU / KVKK — (B4 · 5/N, 2026-09-18).

⚠️ AYRILMA GEREKCESI: bkz. `database/thdb_outbox.py` bas yorumu (B4 · 1/N).
Bu kume hasta kimlik verisinin anonimlestirilmesini ve saklama suresini yonetir.

⚠️ MASKELEME VARSAYILAN KAPALIDIR (sahip karari, bellek `pemf-history-pii-mask-opt-in`):
gecmis ekraninda PII maskesi OPT-IN. Varsayilani "acik" yapmayin — klinik kendi hastasinin
adini goremez hale gelir.

⚠️ `anonymize_patients_by_uuid` GERI DONUSSUZDUR ve KVKK "unutulma hakki"nin karsiligidir.
Kapisi (D2.03 · B-3.92): `tests/test_anonimlestirme_TEDAVI_kopyasi_DAVRANISLA_D203.py` (tedavi-DB'deki hasta
kopyasi, seans satiri ve seans parametrelerinde eski ad/sahip/e-posta HAM SQL ile aranir; baska hasta
DOKUNULMAZ). ⚠️ `tests/test_kvkk_anonymization.py` bu metodu KOSTURMAZ — o, kanonik hasta DB'sinin
(`patient_database.anonymize_inactive_patients`) kapisidir (eskiden burada yanlislikla bu metodun kapisi diye aniliyordu).

⚠️ GOVDELER DEGISTIRILMEDI — bayt bayt tasindi.

`self` uzerinden kullandigi ve ANA SINIFTA kalan uyeler: `_get_connection`, `logger`,
`_get_system_setting` / `_set_system_setting`.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Dict, Optional


class PiiKarisimi:
    def redaksiyon_bekleyen_sayisi(self, retain_days: int = 365) -> int:
        """Bu ayarla KAÇ seans maskelenecek? (kuru çalışma — hiçbir şey değiştirmez)

        ⚠️ DENETİM 2026-08-09 (Tier 1): maskeleme GERİ DÖNÜŞSÜZ ve tamamen SESSİZ çalışıyordu.
        Klinik 366. günde hasta adı yerine `[REDACTED]` görüyor, sebebini hiçbir yerde bulamıyor
        ve "veritabanım bozuldu" diye destek arıyordu. Kararı operatörün ALMASI gerekir; bu
        fonksiyon "ne kaybedeceğini" önceden gösterebilmek için var.
        """
        try:
            cutoff = (datetime.now() - timedelta(days=max(1, int(retain_days)))).strftime('%Y-%m-%d')
            with self._get_connection() as conn:
                r = conn.execute(
                    "SELECT COUNT(*) FROM treatment_sessions WHERE session_date < ? AND "
                    "patient_name IS NOT NULL AND patient_name != '' AND patient_name != '[REDACTED]'",
                    (cutoff,),
                ).fetchone()
                return int(r[0] or 0)
        except Exception:
            self.logger.debug("redaksiyon on-sayimi basarisiz", exc_info=True)
            return 0

    def pii_onayi_var_mi(self) -> bool:
        """Operatör geri dönüşsüz maskelemeyi onayladı mı?"""
        return bool(self._get_system_setting(self.PII_ONAY_ANAHTARI))

    def pii_onayla(self) -> None:
        self._set_system_setting(
            self.PII_ONAY_ANAHTARI,
            datetime.now().isoformat(timespec="seconds"),
            "Operator geri donussuz PII maskelemesini onayladi",
        )

    def pii_suresi_oku(self) -> Optional[int]:
        """Operatörün seçtiği süre (gün) ya da None (ayarlanmamış)."""
        v = self._get_system_setting(self.PII_SURE_ANAHTARI)
        try:
            return int(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    def pii_suresi_yaz(self, gun: int) -> None:
        """Saklama süresini ayarla. 0 → maskeleme KAPALI (tıbbi-hukuki saklama ülkeye göre
        değişir; karar operatöründür)."""
        self._set_system_setting(
            self.PII_SURE_ANAHTARI, str(max(0, int(gun))), "Seans PII maskeleme suresi (gun); 0 = kapali"
        )

    def redact_old_session_pii(self, retain_days: int = 365) -> Dict[str, int]:
        """Eski seans kayıtlarında PII alanlarını maskele."""
        report = {
            'sessions_redacted': 0,
            'parameters_redacted': 0,
        }
        cutoff_date = (datetime.now() - timedelta(days=max(1, int(retain_days)))).strftime('%Y-%m-%d')

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    '''
                    UPDATE treatment_sessions
                    SET patient_name = CASE WHEN patient_name IS NOT NULL AND patient_name != '' THEN '[REDACTED]' ELSE patient_name END,
                        operator_name = CASE WHEN operator_name IS NOT NULL AND operator_name != '' THEN '[REDACTED]' ELSE operator_name END,
                        patient_notes = CASE WHEN patient_notes IS NOT NULL AND patient_notes != '' THEN '[REDACTED]' ELSE patient_notes END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE session_date < ?
                ''',
                    (cutoff_date,),
                )
                report['sessions_redacted'] = int(cursor.rowcount)

                # Audit P2: PII isim listesini TEK-KAYNAK self._PII_PARAM_NAMES'ten al. Gömülü liste
                # sapmıştı — gerçek-yazılan 'patient_owner_email'i ATLIYOR, hiç-yazılmayan 'patient_email'i
                # sayıyordu → owner e-postası retention sonrası süresiz düz-metin kalıyordu (KVKK).
                _pii_names = tuple(self._PII_PARAM_NAMES)
                _pii_ph = ",".join("?" * len(_pii_names))
                cursor.execute(
                    f'''
                    UPDATE session_parameters
                    SET parameter_value = '[REDACTED]'
                    WHERE session_id IN (
                        SELECT id FROM treatment_sessions WHERE session_date < ?
                    )
                    AND parameter_name IN ({_pii_ph})
                ''',
                    (cutoff_date, *_pii_names),
                )
                report['parameters_redacted'] = int(cursor.rowcount)

                conn.commit()
        except Exception as e:
            self.logger.warning(f"PII redaction uyarısı: {e}")

        return report

    def anonymize_patients_by_uuid(self, patient_uuids) -> int:
        """KVKK retention (2026-06-28): patient_database'de anonimlestirilen hastalarin bu DB'deki
        kopyasini da anonimlestir (get_session_history JOIN'i eski ad/sahibi gostermesin). Canonical
        karar patient_database.anonymize_inactive_patients'te; bu yalniz kopyayi senkronlar."""
        uuids = [u for u in (patient_uuids or []) if u]
        if not uuids:
            return 0
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                ph = ",".join("?" * len(uuids))
                # 1) patients kopyasi (get_session_history JOIN ile gösterdiği ad/sahip)
                cursor.execute(
                    f"UPDATE patients SET name='[ANONIM]', owner_name='[ANONIM]', vet_contact='', "
                    f"owner_email='', updated_at=CURRENT_TIMESTAMP WHERE patient_uuid IN ({ph})",
                    uuids,
                )
                n = int(cursor.rowcount)
                # 2) KVKK BÜTÜNLÜK (sağ-unutulma): get_session_history patient_name'i session_parameters ve
                #    ts.patient_name'den de okur (COALESCE). Şifreli-at-rest üretimde bu DENORMALİZE PII de
                #    silinmezse anonimleştirme EKSİK kalırdı → ilgili session'ları patient_id üstünden temizle.
                cursor.execute(f"SELECT id FROM patients WHERE patient_uuid IN ({ph})", uuids)
                pids = [r[0] for r in cursor.fetchall() if r[0] is not None]
                if pids:
                    pph = ",".join("?" * len(pids))
                    cursor.execute(
                        f"UPDATE treatment_sessions SET patient_name='[ANONIM]', operator_name='[ANONIM]', "
                        f"patient_notes='[ANONIM]' WHERE patient_id IN ({pph})",
                        pids,
                    )
                    pn_ph = ",".join("?" * len(self._PII_PARAM_NAMES))
                    cursor.execute(
                        f"UPDATE session_parameters SET parameter_value='[ANONIM]' "
                        f"WHERE parameter_name IN ({pn_ph}) AND session_id IN "
                        f"(SELECT id FROM treatment_sessions WHERE patient_id IN ({pph}))",
                        (*self._PII_PARAM_NAMES, *pids),
                    )
                    # 3) D2.59 (B-3.83): seans olayı ve outbox YÜKLERİNDEKİ hasta adı da (SessionManager yaşam döngüsü yükü) —
                    #    aynı işlemde. Satırlar SİLİNMEZ (olay izi A-07, outbox drain-only #21/#28); yalnız `patient_name` alanı.
                    #    Hekim atfı (`operator_name`) KALIR (A-27).
                    cursor.execute(f"SELECT id FROM treatment_sessions WHERE patient_id IN ({pph})", pids)
                    sids = [r[0] for r in cursor.fetchall()]
                    if sids:
                        self._yuklerden_hasta_adini_anonimlestir(cursor, sids)
                conn.commit()
                return n
        except Exception as e:
            self.logger.warning(f"treatment-history hasta anonimlestirme uyarisi: {e}")
            return 0

    def _yuklerden_hasta_adini_anonimlestir(self, cursor, sids) -> int:
        """`session_events` (seans kimliğiyle) ve `outbox_messages` (`correlation_id` = seans kimliği VE yükün `session_id`'si) JSON
        yüklerindeki `patient_name`'i `[ANONIM]` yapar; ÇAĞIRANIN işleminde koşar (commit yok). Ayrıştırılamayan yük olduğu gibi kalır
        (yalnız JSON sözlük yükü tanınır). @return değişen satır sayısı."""
        import json

        anahtarlar = {str(s) for s in sids}
        sph = ",".join("?" * len(sids))
        degisen = 0
        for tablo, kosul, parametre in (
            ("session_events", f"session_id IN ({sph})", list(sids)),
            ("outbox_messages", f"correlation_id IN ({sph})", sorted(anahtarlar)),
        ):
            for rid, yuk in cursor.execute(f"SELECT id, payload FROM {tablo} WHERE {kosul}", parametre).fetchall():
                try:
                    d = json.loads(yuk or "")
                except (TypeError, ValueError):
                    continue
                if not isinstance(d, dict) or d.get("patient_name") in (None, "", "[ANONIM]"):
                    continue
                if tablo == "outbox_messages" and str(d.get("session_id")) not in anahtarlar:
                    continue
                d["patient_name"] = "[ANONIM]"
                cursor.execute(f"UPDATE {tablo} SET payload=? WHERE id=?", (json.dumps(d, ensure_ascii=True), rid))
                degisen += 1
        return degisen

    def _redact_pii(self, value):
        """at_rest_encrypted=True → değer AYNEN (whole-DB SQLCipher = birincil koruma, şifreli saklanır).

        at_rest_encrypted=False → SAHİP KARARI (2026-07-28): maskeleme VARSAYILAN KAPALI. Tedavi
        geçmişinde hasta/sahip/operatör adları GERÇEK görünür. Gerekçe: AYNI PII zaten patients.db'de
        DÜZ-METİN tutuluyor → yalnız tedavi-geçmişinde maskelemek tutarsız bir yarım-önlemdi (klinik
        kullanılabilirliği bozuyor '[SIFRELENMEMIS-DB]', gerçek gizlilik EKLEMİYOR). Eski maskeleme
        davranışı PEMF_MASK_HISTORY_PII=1 ile geri açılabilir (opt-in). DOĞRU üretim çözümü:
        PEMF_ENCRYPT_AT_REST=1 + sqlcipher → değerler ŞİFRELİ saklanır AMA gerçek görünür.
        NOT: Bu değişiklik İLERİYE dönük — daha önce maskelenmiş kayıtlarda gerçek ad yazıya hiç
        girmediği için geri getirilemez (yeni seanslar gerçek adla yazılır)."""
        if value is None or value == "":
            return value
        if getattr(self, "at_rest_encrypted", False):
            return value
        if os.getenv("PEMF_MASK_HISTORY_PII", "0") == "1":
            return self._PII_REDACTION
        return value
