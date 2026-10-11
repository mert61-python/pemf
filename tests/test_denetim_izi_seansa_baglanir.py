# Author: mertaygn, cglrgrkn
"""DENETİM İZİ SEANSA BAĞLANABİLMELİ + AYNI SANİYEDE ÇAKIŞMAMALI.

KAMPANYA BULGUSU S11 (2026-08-14, düşmanca doğrulamadan geçti). İki ayrı kusur:

**(1) ÇAKIŞAN MÜHÜR.** API seans kimliği `react_<epoch SANİYE>` biçimindeydi. Ölçümde AYNI
SANİYE içinde başlatılan iki farklı seans AYNI kimliği aldı. `session_events` kayıtlarındaki
`payload.ref` bu kimliktir; çakışınca "bu denetim kaydı hangi seansa ait?" sorusu CEVAPSIZ
kalır. Bir denetimde/istismar incelemesinde atfedilebilirlik yoksa iz işe yaramaz.

**(2) İZ SEANSA JOIN EDİLEMİYOR.** `session_started` kayıtlarında `session_events.session_id`
NULL'dur — bu KASITLIDIR ve DOĞRUDUR: olay, DB seans satırı OLUŞMADAN ÖNCE yazılır (önce-iz-
sonra-satır sıralaması). Ama bağlantı hiçbir yerde KURULMUYORDU.

⚠️ ÇÖZÜM YÖNÜ (bilerek): `session_events`e sonradan UPDATE ATILMAZ — o tablo append-only'dir
ve sıralama kasıtlıdır. Bağlantı TERS yönde kurulur: `ref`, seans satırına bir
seans-parametresi (`audit_ref`) olarak yazılır. Böylece yeni DB metodu, UPDATE ve silme
semantiği değişikliği GEREKMEZ.

⚠️ DÜRÜST SINIR: bu, silinen bir seansın `session_events` payload'unda kalan `patient_id`/
`operator_email` artığını (KVKK) ÇÖZMEZ. "İz seansla birlikte silinsin mi?" ayrı bir sahip
kararıdır ve bu düzeltme o soruyu cevaplamadan uygulanabilir.
"""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_KRITIK_ayni_saniyede_iki_seans_AYNI_muhru_ALMAZ():
    """Ölçülen arıza: `react_<epoch saniye>` sub-saniye başlat/durdur/başlat dizisinde çakışıyor."""
    from servers.api_server import _yeni_seans_muhru

    muhurler = {_yeni_seans_muhru() for _ in range(50)}
    assert len(muhurler) == 50, f"50 muhurden yalniz {len(muhurler)} tanesi benzersiz — CAKISMA var"


def test_muhur_bicimi_react_onekini_KORUR():
    """Karşı-kanıt: biçim değişikliği mevcut sözleşmeyi kırmamalı — `react_` ön-eki korunur
    (test_session_lifecycle `startswith` ile bakar)."""
    from servers.api_server import _yeni_seans_muhru

    m = _yeni_seans_muhru()
    assert m.startswith("react_"), f"on-ek degisti: {m}"
    assert re.fullmatch(r"react_\d+_\d+", m), f"beklenen bicim react_<ms>_<seq>, gelen: {m}"


def test_muhur_ZAMAN_SIRASINI_korur():
    """Mühür artan olmalı: denetimde olayları sıralamak için kullanılabilsin."""
    from servers.api_server import _yeni_seans_muhru

    a, b = _yeni_seans_muhru(), _yeni_seans_muhru()
    ms_a, seq_a = (int(x) for x in a.split("_")[1:])
    ms_b, seq_b = (int(x) for x in b.split("_")[1:])
    assert (ms_b, seq_b) > (ms_a, seq_a), "muhur artmiyor — kronolojik siralama yapilamaz"


def test_KRITIK_denetim_izi_seansa_JOIN_edilebilir(tmp_path):
    """İz, seans satırına `audit_ref` parametresi üzerinden bağlanabilmeli.

    ⚠️ `session_events`e UPDATE ATILMAZ (append-only). Bağlantı ters yönde kurulur."""
    from database.treatment_history_db import TreatmentHistoryDB

    db = TreatmentHistoryDB(tmp_path)
    sid = db.start_session(treatment_mode="Manuel", target_condition="test", patient_name="Pamuk")
    ref = "react_1786734864491_1"
    db.set_session_parameter(sid, "audit_ref", ref, "")

    with db._get_connection() as conn:
        satir = conn.execute(
            "SELECT parameter_value FROM session_parameters WHERE session_id=? AND parameter_name='audit_ref'",
            (sid,),
        ).fetchone()
    assert satir is not None, "audit_ref yazilmadi → denetim izi seansa baglanamaz"
    assert satir[0] == ref


def test_audit_ref_PII_MASKESINE_takilmaz():
    """`audit_ref` kişisel veri DEĞİLDİR; PII redaksiyon listesine girerse join anahtarı
    maskelenir ve bağlantı yine kopar.

    ⚠️ D4.07 (B-10.2, 2026-10-10): sembol MODÜLDE aranıyordu (`getattr(thd, ...)`) ama `_PII_PARAM_NAMES`
    `TreatmentHistoryDB` SINIFININ özniteliği → test doğduğundan beri HİÇ koşmadı (her ortamda SKIP). Sembol yoksa
    artık SKIP değil FAIL (PII listesi kaybolmuş ya da taşınmış demektir)."""
    from database import treatment_history_db as thd

    pii = getattr(thd.TreatmentHistoryDB, "_PII_PARAM_NAMES", None)
    assert pii is not None, "TreatmentHistoryDB._PII_PARAM_NAMES YOK — PII maskesinin kapsami olculemiyor"
    assert "patient_name" in pii, f"PII listesi beklenen biçimde değil (patient_name yok): {sorted(pii)}"
    assert "audit_ref" not in pii, "audit_ref PII sayilmis → maskelenir, join anahtari kaybolur"


def test_KRITIK_audit_ref_MASKE_ACIKKEN_de_seansa_baglanir(tmp_path, monkeypatch):
    """D4.07 davranış kolu: maske GERÇEKTEN devredeyken (şifresiz DB + `PEMF_MASK_HISTORY_PII=1`) `audit_ref` aynen
    yazılır. JOIN testi şifreli test DB'sinde koştuğu için maske hiç devreye girmiyor ve `audit_ref`i PII listesine
    ekleyen mutant orada YEŞİL kalıyordu (ölçüldü). KARŞIT: aynı koşumda `patient_name` MASKELENİR (maske açık)."""
    from database.treatment_history_db import TreatmentHistoryDB

    monkeypatch.setenv("PEMF_MASK_HISTORY_PII", "1")
    db = TreatmentHistoryDB(tmp_path)
    monkeypatch.setattr(db, "at_rest_encrypted", False)
    sid = db.start_session(treatment_mode="Manuel", target_condition="test", patient_name="Pamuk")
    ref = "react_1786734864491_7"
    assert db.set_session_parameter(sid, "audit_ref", ref, "")
    assert db.set_session_parameter(sid, "patient_name", "Pamuk", "")
    with db._get_connection() as conn:
        degerler = dict(
            conn.execute(
                "SELECT parameter_name, parameter_value FROM session_parameters WHERE session_id=? "
                "AND parameter_name IN ('audit_ref','patient_name')",
                (sid,),
            ).fetchall()
        )
    assert degerler.get("patient_name") == TreatmentHistoryDB._PII_REDACTION, (
        f"maske bu koşumda devrede DEĞİL — kapı ölçemiyor: {degerler}"
    )
    assert degerler.get("audit_ref") == ref, f"audit_ref MASKELENDI → denetim izi seansa baglanamaz: {degerler}"


def test_KRITIK_SIFRELI_DB_de_maske_bayragi_ACIKKEN_PII_ve_audit_ref_AYNEN_yazilir(tmp_path, monkeypatch):
    """4-A inc. 4A-2.13 — maskenin ŞİFRELİ kolu: `at_rest_encrypted=True` iken `_redact_pii` değeri AYNEN yazar
    (`PEMF_MASK_HISTORY_PII=1` olsa bile; whole-DB SQLCipher birincil koruma). Bu kol hiçbir testte ölçülmüyordu: şifre ve
    maske denetiminin sırası değişince (şifreli DB'de de maskele) PII kümesi 308/308 yeşildi — üretimde bayrak açılırsa gerçek
    adlar geri DÖNÜLEMEZ biçimde maskelenirdi."""
    from database.treatment_history_db import TreatmentHistoryDB

    monkeypatch.setenv("PEMF_MASK_HISTORY_PII", "1")
    db = TreatmentHistoryDB(tmp_path)
    monkeypatch.setattr(db, "at_rest_encrypted", True)
    sid = db.start_session(treatment_mode="Manuel", target_condition="test", patient_name="Pamuk")
    ref = "react_1786734864491_7"
    assert db.set_session_parameter(sid, "audit_ref", ref, "")
    assert db.set_session_parameter(sid, "patient_name", "Pamuk", "")
    with db._get_connection() as conn:
        degerler = dict(
            conn.execute(
                "SELECT parameter_name, parameter_value FROM session_parameters WHERE session_id=? "
                "AND parameter_name IN ('audit_ref','patient_name')",
                (sid,),
            ).fetchall()
        )
    assert degerler.get("patient_name") == "Pamuk", f"ŞİFRELİ DB'de PII MASKELENDİ (geri dönülemez kayıp): {degerler}"
    assert degerler.get("audit_ref") == ref, degerler


if __name__ == "__main__":
    import os

    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
