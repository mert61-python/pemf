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

    #: ⚠️ D2.54 · A-27: anonimleştirme HASTAYI hedefler — hastanın veteriner HEKİMİ (`patient_veteriner`) seans parametresinde KALIR
    #: (kanonik `patient_database.anonymize_inactive_patients` de `veteriner`i bırakır, `vet_contact`ı siler).
    _ANONIM_KALAN_PARAMETRELER = frozenset({"patient_veteriner"})

    def anonymize_patients_by_uuid(self, patient_uuids, kimlikler=None) -> int:
        """KVKK retention (2026-06-28): patient_database'de anonimlestirilen hastalarin bu DB'deki
        kopyasini da anonimlestir (get_session_history JOIN'i eski ad/sahibi gostermesin). Canonical
        karar patient_database.anonymize_inactive_patients'te; bu yalniz kopyayi senkronlar.

        ⚠️ D2.54 (B-3.33 · B-3.34 · A-27 · Y125):
        - HATADA -1 döner (eskiden sessiz 0 — kanonik taraf anonim olduğu için hasta bir daha seçilmiyor, tedavi geçmişindeki ad SÜRESİZ
          kalıyordu). Çağıran (`services.kvkk_anonimlestirme`) -1'de kalıcı bekleyen listeden düşürmez, sonraki turda yeniden dener.
        - A-27: seansın HEKİM adı (`operator_name`) ve hastanın veteriner hekimi (`patient_veteriner`) KALIR — eskiden `[ANONIM]` oluyordu.
        - Y125: `ai_analyses` da anonimleşir — kimliği bu hastaya ait kayıtlar; `kimlikler[uuid]["ad_ile_kimliksiz"]` doğruysa (ad kanonik
          DB'de başka AKTİF hastaya çözülmüyorsa — çağıran ölçer) aynı adlı KİMLİKSİZ eski kayıtlar da. `patient_name` → `[ANONIM]`; özet,
          ayrıntı, hekim gerekçesi ve değerlendirme geçmişi metinlerinde hasta adı / sahip adı / sahip e-postası → `[ANONIM]` (Türkçe
          i/İ, ı/I duyarsız; klinik içerik kalır). AI kaydının hekim atfı (`operator_email`, `reviewed_by`) KALIR (A-27).
        `kimlikler` = {uuid: {"metinler": [ad, sahip, eposta], "ad_ile_kimliksiz": bool}}; verilmezse yalnız kopyanın kendi metinleri.
        Kapı: tests/test_kvkk_anonimlestirme_ONAYLI_ve_EKSIKSIZ_D254.py"""
        uuids = [u for u in (patient_uuids or []) if u]
        if not uuids:
            return 0
        kimlikler = dict(kimlikler or {})
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                ph = ",".join("?" * len(uuids))
                # 0) Silinecek kimlik metinleri: çağıranın verdikleri + kopyanın KENDİ ad/sahip/e-postası (UPDATE'ten ÖNCE okunur).
                metinler: dict = {u: list((kimlikler.get(u) or {}).get("metinler") or []) for u in uuids}
                for u, ad, sahip, eposta in cursor.execute(
                    f"SELECT patient_uuid, name, owner_name, owner_email FROM patients WHERE patient_uuid IN ({ph})",
                    uuids,
                ).fetchall():
                    metinler.setdefault(u, []).extend([ad, sahip, eposta])
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
                    # ⚠️ A-27: `operator_name` (hekim atfı) DOKUNULMAZ.
                    cursor.execute(
                        f"UPDATE treatment_sessions SET patient_name='[ANONIM]', "
                        f"patient_notes='[ANONIM]' WHERE patient_id IN ({pph})",
                        pids,
                    )
                    _hasta_parametreleri = tuple(sorted(self._PII_PARAM_NAMES - self._ANONIM_KALAN_PARAMETRELER))
                    pn_ph = ",".join("?" * len(_hasta_parametreleri))
                    cursor.execute(
                        f"UPDATE session_parameters SET parameter_value='[ANONIM]' "
                        f"WHERE parameter_name IN ({pn_ph}) AND session_id IN "
                        f"(SELECT id FROM treatment_sessions WHERE patient_id IN ({pph}))",
                        (*_hasta_parametreleri, *pids),
                    )
                    # 3) D2.59 (B-3.83): seans olayı ve outbox YÜKLERİNDEKİ hasta adı da (SessionManager yaşam döngüsü yükü) —
                    #    aynı işlemde. Satırlar SİLİNMEZ (olay izi A-07, outbox drain-only #21/#28); yalnız `patient_name` alanı.
                    #    Hekim atfı (`operator_name`) KALIR (A-27).
                    cursor.execute(f"SELECT id FROM treatment_sessions WHERE patient_id IN ({pph})", pids)
                    sids = [r[0] for r in cursor.fetchall()]
                    if sids:
                        self._yuklerden_hasta_adini_anonimlestir(cursor, sids)
                # 4) Y125 / B-3.33: AI analiz kayıtları (aynı işlem).
                self._ai_kayitlarini_anonimlestir(cursor, uuids, metinler, kimlikler)
                conn.commit()
                return n
        except Exception as e:
            self.logger.warning(
                f"treatment-history hasta anonimlestirme uyarisi (sonraki turda yeniden denenecek): {e}"
            )
            return -1

    @staticmethod
    def _kimlik_deseni(metin: str):
        """Türkçe-duyarsız arama deseni: i/İ (+ birleşik nokta U+0307 — `"İ".lower()`), ı/I sınıf olarak; diğer harfler büyük-küçük
        duyarsız; boşluklar esnek. Aşırı eşleşme (ı↔i) anonimleştirmede GÜVENLİ yöndür."""
        import re

        parca = []
        for ch in str(metin).strip():
            if ch in "iİ":
                parca.append("[iİ]\u0307?")
            elif ch in "ıI":
                parca.append("[ıI]")
            elif ch.isspace():
                parca.append(r"\s+")
            else:
                parca.append(re.escape(ch))
        return re.compile("".join(parca), re.IGNORECASE)

    def _metinden_kimligi_sil(self, deger, desenler):
        if not isinstance(deger, str) or not deger:
            return deger
        for d in desenler:
            deger = d.sub("[ANONIM]", deger)
        return deger

    def _ai_kayitlarini_anonimlestir(self, cursor, uuids, metinler, kimlikler) -> int:
        """D2.54 · Y125: hastanın AI analiz kayıtları — ÇAĞIRANIN işleminde (commit yok). @return değişen satır sayısı."""
        from utils.turkce_metin import arama_katla

        degisen = 0
        for u in uuids:
            desenler = [
                self._kimlik_deseni(m)
                for m in sorted({str(m).strip() for m in (metinler.get(u) or []) if m}, key=len, reverse=True)
                if len(m) >= 3 and m != "[ANONIM]"
            ]
            satirlar = cursor.execute(
                "SELECT id, result_summary, result_detail, review_note, review_history FROM ai_analyses WHERE patient_uuid = ?",
                (u,),
            ).fetchall()
            bilgi = kimlikler.get(u) or {}
            ad = next((m for m in (bilgi.get("metinler") or []) if m), None)
            if bilgi.get("ad_ile_kimliksiz") and ad:
                katli = arama_katla(str(ad))
                satirlar += [
                    r[:5]
                    for r in cursor.execute(
                        "SELECT id, result_summary, result_detail, review_note, review_history, patient_name FROM ai_analyses "
                        "WHERE COALESCE(patient_uuid, '') = ''"
                    ).fetchall()
                    if r[5] and arama_katla(str(r[5])) == katli
                ]
            for aid, ozet, ayrinti, not_, gecmis in satirlar:
                cursor.execute(
                    "UPDATE ai_analyses SET patient_name='[ANONIM]', result_summary=?, result_detail=?, review_note=?, "
                    "review_history=? WHERE id=?",
                    (
                        self._metinden_kimligi_sil(ozet, desenler),
                        self._metinden_kimligi_sil(ayrinti, desenler),
                        self._metinden_kimligi_sil(not_, desenler),
                        self._metinden_kimligi_sil(gecmis, desenler),
                        aid,
                    ),
                )
                degisen += 1
        return degisen

    # ── D2.54 · A-06 / A-09 / B-3.34: anonimleştirme ONAYI ve kalıcı BEKLEYEN listesi (system_settings) ──────────────────────────
    ANONIM_ONAY_ANAHTARI = "kvkk_anonim_onay"
    ANONIM_BEKLEYEN_ANAHTARI = "kvkk_anonim_bekleyen"

    def anonim_onayi_oku(self) -> Optional[dict]:
        """Operatörün anonimleştirme onayı {gun, sayi, zaman, kim} ya da None. Bozuk/okunamaz → None (onay YOK — fail-closed)."""
        import json

        ham = self._get_system_setting(self.ANONIM_ONAY_ANAHTARI)
        try:
            d = json.loads(ham) if ham else None
        except (TypeError, ValueError):
            return None
        return d if isinstance(d, dict) and d.get("gun") else None

    def anonim_onayi_yaz(self, gun: int, sayi: int, kim: str = "") -> None:
        import json

        self._set_system_setting(
            self.ANONIM_ONAY_ANAHTARI,
            json.dumps(
                {
                    "gun": int(gun),
                    "sayi": int(sayi),
                    "zaman": datetime.now().isoformat(timespec="seconds"),
                    "kim": kim or "",
                },
                ensure_ascii=False,
            ),
            "Operator 5 yil inaktif hasta anonimlestirmesini onayladi (A-06); esik degisirse gecersiz (A-09)",
        )

    def anonim_bekleyen_oku(self) -> dict:
        """Tedavi-DB adımı henüz BİTMEMİŞ anonimleştirmeler {uuid: [ad, sahip, eposta]} (B-3.34). Okunamaz → {} (bu tur atlanır)."""
        import json

        ham = self._get_system_setting(self.ANONIM_BEKLEYEN_ANAHTARI)
        try:
            d = json.loads(ham) if ham else {}
        except (TypeError, ValueError):
            self.logger.error(
                "KVKK anonimlestirme bekleyen listesi BOZUK — yeniden yazilana dek yeniden deneme yapilamaz."
            )
            return {}
        return d if isinstance(d, dict) else {}

    def anonim_bekleyen_ekle(self, girdiler: dict) -> None:
        import json

        d = self.anonim_bekleyen_oku()
        d.update({str(k): [str(x) if x else "" for x in (v or [])] for k, v in (girdiler or {}).items() if k})
        self._set_system_setting(
            self.ANONIM_BEKLEYEN_ANAHTARI,
            json.dumps(d, ensure_ascii=False),
            "KVKK: tedavi-DB anonimlestirmesi bekleyenler",
        )

    def anonim_bekleyen_dus(self, uuids) -> None:
        import json

        d = self.anonim_bekleyen_oku()
        for u in uuids or ():
            d.pop(str(u), None)
        self._set_system_setting(
            self.ANONIM_BEKLEYEN_ANAHTARI,
            json.dumps(d, ensure_ascii=False),
            "KVKK: tedavi-DB anonimlestirmesi bekleyenler",
        )

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
