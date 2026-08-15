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
    maskelenir ve bağlantı yine kopar."""
    from database import treatment_history_db as thd

    pii = getattr(thd, "_PII_PARAM_NAMES", None)
    if pii is None:
        pytest.skip("_PII_PARAM_NAMES yok")
    assert "audit_ref" not in pii, "audit_ref PII sayilmis → maskelenir, join anahtari kaybolur"


if __name__ == "__main__":
    import os

    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
