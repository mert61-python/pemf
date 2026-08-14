# Author: mertaygn, cglrgrkn
"""ACİL DURDURMA GEÇMİŞTE GÖRÜNMELİ — "bu hastada e-stop yaşandı mı?" cevaplanabilmeli.

KAMPANYA BULGUSU (2026-08-14, S09). Aynı ortamda üç seans koşuldu: biri normal `/session/stop`,
biri **ACİL DURDURMA**, biri yine normal. Üçünün de `session_status` değeri `'completed'` çıktı.
Ayrıca KPI `stoppedSessions=0`, `completedSessions=3` gösterdi.

Sonuç: bir denetimde ya da istismar incelemesinde **"bu hastada acil durdurma yaşandı mı?"**
sorusu cevapsız kalıyor; kesintiyle biten tedavi, sorunsuz tamamlanmış gibi görünüyor. Tıbbi
kayıtta bu, olayın kendisini gizlemek demektir.

NEDEN OLUYORDU. Sebep zaten boru hattında TAŞINIYORDU:
`_emergency_stop_all` → `_finalize_session_db(reason="acil-durdurma:...")` → ama `reason`
YALNIZCA LOGLANIYOR, `session_status`'a hiç yazılmıyordu (`end_session` sabit `'completed'`
yazıyor). Yani bilgi vardı, kaydedilmiyordu.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.treatment_history_db import SEANS_DURUMU_ACIL_DURDURMA, TreatmentHistoryDB  # noqa: E402


def _seans_baslat(db, hasta="Pamuk"):
    return db.start_session(
        treatment_mode="Manuel",
        target_condition="test",
        patient_name=hasta,
    )


def test_KRITIK_acil_durdurma_ile_biten_seans_AYIRT_EDILEBILIR(tmp_path):
    """En kritik değişmez: e-stop ile biten seans, normal bitenden ayırt edilebilmeli."""
    db = TreatmentHistoryDB(tmp_path)

    normal = _seans_baslat(db, "Normal")
    db.end_session(normal, duration_minutes=10)

    acil = _seans_baslat(db, "Acil")
    db.end_session(acil, duration_minutes=3, session_status=SEANS_DURUMU_ACIL_DURDURMA)

    with db._get_connection() as conn:
        d_normal = conn.execute("SELECT session_status FROM treatment_sessions WHERE id=?", (normal,)).fetchone()[0]
        d_acil = conn.execute("SELECT session_status FROM treatment_sessions WHERE id=?", (acil,)).fetchone()[0]

    assert d_normal != d_acil, "acil durdurma ile biten seans normal bitmis gibi gorunuyor"
    assert d_acil == SEANS_DURUMU_ACIL_DURDURMA


def test_VARSAYILAN_hala_completed_karsit_kanit(tmp_path):
    """Karşı-kanıt: değişiklik normal akışı bozarak da geçemez — durum verilmezse `completed`."""
    db = TreatmentHistoryDB(tmp_path)
    sid = _seans_baslat(db)
    db.end_session(sid, duration_minutes=10)
    with db._get_connection() as conn:
        durum = conn.execute("SELECT session_status FROM treatment_sessions WHERE id=?", (sid,)).fetchone()[0]
    assert durum == "completed"


def test_KRITIK_KPI_acil_durdurmayi_SAYAR(tmp_path):
    """KPI `stoppedSessions` e-stop'u saymalı; aksi hâlde gösterge tablosu "her şey yolunda" der.

    ⚠️ Bu test, yazan (`end_session`) ile okuyanın (`system_router` KPI sorgusu) AYRI yerlerde
    olmasından doğan ayrışmayı kilitler: durum sabiti değişip sorgu güncellenmezse sayaç sessizce
    sıfırlanır — kimse fark etmez."""
    from servers import api_server as _api
    from servers import system_router

    db = TreatmentHistoryDB(tmp_path)
    for _ in range(2):
        db.end_session(_seans_baslat(db), duration_minutes=10)
    db.end_session(_seans_baslat(db), duration_minutes=2, session_status=SEANS_DURUMU_ACIL_DURDURMA)

    # ⚠️ SQL'i KOPYALAMA — GERÇEK okuyucuyu çağır. İlk yazımda sorguyu teste kopyalamıştım ve
    # mutasyon testi bunu yakaladı: üretimdeki sorgu bozulduğu hâlde test yeşil kalıyordu
    # (kopya kendi kendini doğruluyordu). Kilitlenmesi gereken şey ÜRETİMDEKİ sorgudur.
    _eski = _api._get_treatment_db
    _api._get_treatment_db = lambda: db
    try:
        kpi = system_router.get_kpi_summary()
    finally:
        _api._get_treatment_db = _eski

    assert kpi["stoppedSessions"] == 1, f"KPI acil durdurmayi saymadi: {kpi['stoppedSessions']}"
    assert kpi["completedSessions"] == 2, f"normal seanslar yanlis sayildi: {kpi['completedSessions']}"


def test_KRITIK_KPI_SORGUSU_durum_sabitini_ICERIR():
    """Yazan ile okuyanın ayrışmasını doğrudan kilitler: KPI sorgusu, `end_session`ın yazdığı
    durumu tanımıyorsa sayaç sessizce 0 kalır (bulgunun ta kendisi)."""
    kaynak = (Path(__file__).resolve().parent.parent / "servers" / "system_router.py").read_text(
        encoding="utf-8", errors="replace"
    )
    # ⚠️ Aranan şey, durumun ELLE YAZILMIŞ hâli DEĞİL, SABİTİN KENDİSİdir. Elle yazılmış bir
    # kopya "şu an doğru" olurdu ama sabit değişince sessizce ayrışırdı — kilitlenmesi gereken
    # değişmez tam olarak budur: okuyan, yazanla AYNI kaynağı kullanır.
    assert "SEANS_DURUMU_ACIL_DURDURMA" in kaynak, (
        "KPI sorgusu durum sabitini kullanmiyor → sabit degisince stoppedSessions SESSIZCE 0 kalir"
    )
    assert SEANS_DURUMU_ACIL_DURDURMA == "EMERGENCY_STOPPED", "sabit degistiyse gecmis kayitlar da gozden gecirilmeli"


if __name__ == "__main__":
    import os

    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
