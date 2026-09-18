# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AI ANALIZ GECMISI — `TreatmentHistoryDB`nin AI yarisi (B4 · 3/N, 2026-09-18).

⚠️ AYRILMA GEREKCESI: bkz. `database/thdb_outbox.py` bas yorumu (B4 · 1/N).
Bu kume `ai_analyses` tablosuna dokunur.

⚠️ AI CIKTISI ONERIDIR, KARAR HEKIMINDIR (sahip karari 2026-08-06): tablo bu yuzden
`review_status` / `review_note` / `reviewed_by` / `reviewed_at` alanlarini tasir ve
`set_ai_review` bunlari yazar. Bu alanlari "kullanilmiyor" diye kaldirmayin.

⚠️ `ai_analiz_kimliklerini_doldur` Turkce katlama kullanir (`utils.turkce_metin.arama_katla`).
Katlamayi KENDINIZ yazmayin — `I/i` cifti Turkce'de `lower()` ile YANLIS eslesir
(bellek: `turkce-collation-lower-tuzagi`). Fonksiyon-ici import govdeyle birlikte tasindi.

⚠️ GOVDELER DEGISTIRILMEDI — bayt bayt tasindi.

`self` uzerinden kullandigi ve ANA SINIFTA kalan uyeler: `_get_connection`, `logger`.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Dict, List, Optional


class AiGecmisiKarisimi:
    # ---- AI Analiz Geçmişi (profesyonel detaylı kayıt; SQLCipher-şifreli → KVKK-güvenli) ----
    def add_ai_analysis(
        self,
        mode: str = "",
        module_id: str = "",
        module_label: str = "",
        patient_name: str = "",
        input_type: str = "",
        result_summary: str = "",
        result_detail: Optional[Dict] = None,
        confidence: Optional[float] = None,
        operator_email: str = "",
        patient_uuid: str = "",
    ) -> Optional[int]:
        """Bir AI analiz sonucunu şifreli geçmişe ekle. Tüm profillerin tüm modelleri buraya yazar.
        operator_email = analizi yapan hekim (klinik-içi "Benim/Tüm Klinik" filtresi).

        ⚠️ `patient_uuid` = hastanın OPAK KİMLİĞİ (2026-09-12). Ada göre eşleme aynı adlı iki
        hayvanda karışıyor, ad düzeltilince kopuyor ve PII maskelemesi açıkken tümüyle çöküyordu.
        Kimlik PII olmadığı için maskelenmez. BOŞ GEÇİLEBİLİR: kimliği bilinmeyen çağrı (eski
        istemci) kaydı DÜŞÜRMEZ, yalnız ada bağlı kalır.

        ⚠️ Yeni parametreler SONDA → pozisyonel çağrılar bozulmaz."""
        try:
            self._ensure_write_guardrail()
            # B-1.3 deseni (start_session ile tutarlı): at-rest şifreleme KAPALIYSA gerçek isim yerine
            # [SIFRELENMEMIS-DB] yazılır → şifresiz DB'de düz-metin PII sızmaz. Şifreliyse isim korunur.
            patient_name = self._redact_pii(patient_name)
            # operator_email = hekimin KENDİ login e-postası (hasta PII'si değil); filtre için ham saklanır
            # (üretimde DB zaten SQLCipher-şifreli). _redact_pii uygulanırsa "Benim" filtresi maskede bozulurdu.
            operator_email = operator_email or ""
            detail_json = json.dumps(result_detail or {}, ensure_ascii=False)
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    '''
                    INSERT INTO ai_analyses
                    (created_at, mode, module_id, module_label, patient_name, patient_uuid,
                     operator_email, input_type, result_summary, result_detail, confidence)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                    (
                        datetime.now().isoformat(timespec="seconds"),
                        mode,
                        module_id,
                        module_label,
                        patient_name,
                        # ⚠️ MASKELENMEZ: kimlik PII değil, opak bir tanımlayıcıdır.
                        str(patient_uuid or ""),
                        operator_email,
                        input_type,
                        result_summary,
                        detail_json,
                        confidence,
                    ),
                )
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            self.logger.warning(f"AI analiz kaydedilemedi: {e}")
            return None

    def set_ai_review(self, analysis_id: int, status: str, note: str = "", reviewed_by: str = "") -> bool:
        """AI analizine HEKİM DEĞERLENDİRMESİ yaz (2026-08-06, sahip isteği).

        `status`: "approved" | "rejected" | "corrected".
        ⚠️ Kayıt SİLİNMEZ, AI çıktısı DEĞİŞTİRİLMEZ — hekimin kararı YANINA yazılır. AI'ın ne
        dediği ile hekimin ne dediği ayrı ayrı görünür kalmalı (klinik denetlenebilirlik: sonradan
        "model ne demişti?" sorusunun cevabı kaybolmamalı).
        """
        if status not in ("approved", "rejected", "corrected"):
            raise ValueError(f"Geçersiz değerlendirme durumu: {status}")
        try:
            with self._get_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    "UPDATE ai_analyses SET review_status=?, review_note=?, reviewed_by=?, reviewed_at=? WHERE id=?",
                    (
                        status,
                        str(note or ""),
                        str(reviewed_by or ""),
                        datetime.now().isoformat(timespec="seconds"),
                        int(analysis_id),
                    ),
                )
                conn.commit()
                return cur.rowcount > 0
        except Exception as e:
            self.logger.warning(f"AI değerlendirmesi yazılamadı: {e}")
            return False

    def delete_ai_analysis(self, analysis_id: int, operator_email: Optional[str] = None) -> bool:
        """TEK bir AI analiz kaydını siler.

        `operator_email` verilirse yalnız O KİŞİYE ait (veya sahipsiz) kayıt silinir — böylece
        klinik profili olmayan kullanıcı başkasının kaydını silemez. KVKK silme hakkı için gerekli:
        kullanıcı kendi kaydını kaldırabilmeli, başkasınınkini kaldıramamalı.
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if operator_email:
                    cursor.execute(
                        "DELETE FROM ai_analyses WHERE id = ? AND "
                        "(operator_email IS NULL OR operator_email = '' OR LOWER(operator_email) = ?)",
                        (int(analysis_id), operator_email.strip().lower()),
                    )
                else:
                    cursor.execute("DELETE FROM ai_analyses WHERE id = ?", (int(analysis_id),))
                silindi = cursor.rowcount > 0
                conn.commit()
                return silindi
        except Exception:
            self.logger.exception("AI analiz kaydı silinemedi (id=%s).", analysis_id)
            return False

    def clear_ai_analyses(self, operator_email: Optional[str] = None) -> int:
        """AI analiz geçmişini TOPLU siler; silinen kayıt sayısını döner.

        ⚠️ VACUUM ŞART: `DELETE` satırları yalnız serbest listeye bırakır — hasta adı ve analiz
        özeti dosyada OKUNABİLİR kalır. `clear_all_patients` ile aynı kural (audit P3).
        VACUUM tüm dosyayı yeniden yazdığı için silinen kişisel veri gerçekten gider.
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if operator_email:
                    op = operator_email.strip().lower()
                    cursor.execute(
                        "SELECT COUNT(*) FROM ai_analyses WHERE "
                        "(operator_email IS NULL OR operator_email = '' OR LOWER(operator_email) = ?)",
                        (op,),
                    )
                    n = int(cursor.fetchone()[0] or 0)
                    cursor.execute(
                        "DELETE FROM ai_analyses WHERE "
                        "(operator_email IS NULL OR operator_email = '' OR LOWER(operator_email) = ?)",
                        (op,),
                    )
                else:
                    cursor.execute("SELECT COUNT(*) FROM ai_analyses")
                    n = int(cursor.fetchone()[0] or 0)
                    cursor.execute("DELETE FROM ai_analyses")
                conn.commit()
                cursor.execute("VACUUM")
                return n
        except Exception:
            self.logger.exception("AI analiz geçmişi temizlenemedi.")
            return -1

    def ai_analiz_kimliklerini_doldur(self, ad_kimlik: dict) -> dict:
        """ESKİ AI analizlerine hasta KİMLİĞİ yazar (tek seferlik taşıma, idempotent).

        ═══════════════════════════════════════════════════════════════════════════════
        ⚠️ BELİRSİZ ADI TAHMİN ETMEZ — BU FONKSİYONUN ASIL KURALI
        ═══════════════════════════════════════════════════════════════════════════════
        `ad_kimlik`, ÇAĞIRANIN hasta defterinden kurduğu {katlanmış_ad: kimlik} haritasıdır
        ve YALNIZ TEK BİR hastaya çözülen adları içerir. Aynı ada sahip iki hayvan varsa o ad
        haritaya HİÇ KONMAZ; o analizler kimliksiz kalır ve eskisi gibi ada bağlı çalışır.

        Yanlış bir kimlik yazmak, taşımanın çözmeye çalıştığı sorunu KALICI hâle getirirdi:
        bir hayvanın analizi başka bir hayvanın kaydına GÖMÜLÜRDÜ ve ad bazlı belirsizliğin
        aksine bu geri alınamazdı (ad hâlâ orada, kimlik ise artık "kesin" görünür).

        ⚠️ YALNIZ BOŞ KİMLİKLİ SATIRLARA yazar → tekrar çalıştırmak güvenlidir (idempotent)
        ve elle düzeltilmiş bir kimliği EZMEZ.

        Dönen: {"guncellenen": n, "kimliksiz_kalan": m, "atlanmis_ad": k}
        """
        harita = {str(a): str(u) for a, u in (ad_kimlik or {}).items() if a and u}
        sonuc = {"guncellenen": 0, "kimliksiz_kalan": 0, "atlanmis_ad": 0}
        try:
            from utils.turkce_metin import arama_katla
        except Exception:
            self.logger.warning("Turkce katlayici yok -> AI kimlik tasima ATLANDI.")
            return sonuc
        try:
            self._ensure_write_guardrail()
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, patient_name FROM ai_analyses "
                    "WHERE COALESCE(patient_uuid,'') = '' AND COALESCE(patient_name,'') != ''"
                )
                satirlar = cursor.fetchall()
                eslesmeyen_adlar = set()
                for kayit_id, ad in satirlar:
                    kimlik = harita.get(arama_katla(ad))
                    if not kimlik:
                        sonuc["kimliksiz_kalan"] += 1
                        eslesmeyen_adlar.add(str(ad))
                        continue
                    # ⚠️ `AND COALESCE(patient_uuid,'') = ''` İKİNCİ KATMANDIR ve tek başına
                    # ölçülemez: yukarıdaki SELECT zaten yalnız boş kimlikli satırları getiriyor,
                    # dolayısıyla bu koşulu kaldıran bir mutasyon testlerde YEŞİL kalır
                    # (2026-09-12'de ölçüldü, dürüstçe not edildi). Yine de duruyor: iki BACKEND
                    # SÜRECİ aynı DB'yi paylaşırsa (süreç-içi kilit onları kapsamaz) SELECT ile
                    # UPDATE arasında başka bir yazıcı kimliği koymuş olabilir; o kimliği ezmek
                    # elle yapılmış bir düzeltmeyi geri almak olurdu.
                    cursor.execute(
                        "UPDATE ai_analyses SET patient_uuid = ? WHERE id = ? AND COALESCE(patient_uuid,'') = ''",
                        (kimlik, kayit_id),
                    )
                    sonuc["guncellenen"] += cursor.rowcount or 0
                conn.commit()
                sonuc["atlanmis_ad"] = len(eslesmeyen_adlar)
            if sonuc["guncellenen"] or sonuc["kimliksiz_kalan"]:
                self.logger.info(
                    "AI analiz kimlik tasimasi: %d guncellendi, %d kimliksiz kaldi (%d farkli ad).",
                    sonuc["guncellenen"],
                    sonuc["kimliksiz_kalan"],
                    sonuc["atlanmis_ad"],
                )
            return sonuc
        except Exception:
            self.logger.exception("AI analiz kimlik tasimasi basarisiz (kayitlar DEGISMEDI).")
            return sonuc

    def get_ai_analyses(
        self,
        limit: int = 50,
        module_id: Optional[str] = None,
        patient_name: Optional[str] = None,
        before_id: Optional[int] = None,
        patient_uuid: Optional[str] = None,
    ) -> List[Dict]:
        """AI analiz geçmişini getir (id DESC = yeni önce). Filtre: modül / hasta / keyset-pagination.

        ⚠️ `patient_uuid` TERCİH EDİLEN hasta süzgecidir (2026-09-12): ad bazlı süzme aynı adlı
        iki hayvanda karışır, ad düzeltilince kopar ve PII maskelemesi açıkken tümüyle çöker.
        `patient_name` GERİYE UYUMLULUK için kalır (kimliği olmayan ESKİ kayıtlar).
        ⚠️ İkisi birlikte verilirse VEYA ile bağlanır: kimliği yazılmış YENİ kayıtlar ile aynı
        hastaya ait ESKİ (kimliksiz) kayıtlar TEK listede görünsün — aksi hâlde taşıma günü
        geçmiş ikiye bölünmüş gibi görünürdü."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                clauses, params = [], []
                if module_id:
                    clauses.append("module_id = ?")
                    params.append(module_id)
                # ⚠️ HASTA SÜZGECİ: kimlik VE/VEYA ad. İkisi de verilirse VEYA (bkz. docstring).
                _hasta_kosul, _hasta_param = [], []
                if patient_uuid:
                    _hasta_kosul.append("patient_uuid = ?")
                    _hasta_param.append(str(patient_uuid))
                if patient_name:
                    _hasta_kosul.append("patient_name LIKE ?")
                    _hasta_param.append(f"%{patient_name}%")
                if _hasta_kosul:
                    clauses.append("(" + " OR ".join(_hasta_kosul) + ")")
                    params.extend(_hasta_param)
                if before_id:
                    clauses.append("id < ?")
                    params.append(int(before_id))
                where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
                params.append(max(1, min(int(limit), 500)))
                cursor.execute(
                    "SELECT id, created_at, mode, module_id, module_label, patient_name, "
                    "COALESCE(patient_uuid,'') AS patient_uuid, operator_email, "
                    "input_type, result_summary, result_detail, confidence, "
                    # Hekim değerlendirmesi (2026-08-06) — AI çıktısı öneri, karar hekimin.
                    "COALESCE(review_status,'') AS review_status, COALESCE(review_note,'') AS review_note, "
                    "COALESCE(reviewed_by,'') AS reviewed_by, COALESCE(reviewed_at,'') AS reviewed_at "
                    f"FROM ai_analyses{where} ORDER BY id DESC LIMIT ?",
                    params,
                )
                cols = [c[0] for c in cursor.description]
                out = []
                for r in cursor.fetchall():
                    d = dict(zip(cols, r))
                    try:
                        d["result_detail"] = json.loads(d.get("result_detail") or "{}")
                    except Exception:
                        d["result_detail"] = {}
                    out.append(d)
                return out
        except Exception as e:
            self.logger.warning(f"AI analiz geçmişi okunamadı: {e}")
            return []
