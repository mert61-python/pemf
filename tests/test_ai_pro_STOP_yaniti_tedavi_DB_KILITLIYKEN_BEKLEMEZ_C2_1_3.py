# -*- coding: utf-8 -*-
"""C2-1.3 (2-C inceleme, A1) — tedavi DB'si KİLİTLİYKEN `/api/ai/pro/stop` yanıtı satır kapanışını BEKLEMEMELİ.

KUSUR (D2.E07, `047155e`): `stop_ai_pro` bobin STOP'undan SONRA aynı istek içinde `_ai_pro_satirini_kapat` ile tedavi DB'sini
okur/yazar. DB başka bir bağlantı tarafından kilitliyken (yedekleme aracı, ikinci backend, `locking_mode=EXCLUSIVE`) okuma
bağlantı zaman aşımı + `busy_timeout` boyunca bekler → yanıt ~21 sn (ölçüldü). STOP donanıma 15 ms'de gider (Ö.4-Y8 STOP'un
kendisi gecikmez) ama arayüz (`apiPost` 8 sn zaman aşımı) yanıtı alamaz: "Durdurulamadı — … ACİL DURDUR kullanın" der ve
paneli "çalışıyor" bırakır; satır da kapanmaz. E07'den önce bu uç DB'ye dokunmuyordu.
GERÇEK: tedavi DB dosyası İKİNCİ bir SQLite bağlantısıyla kilitlenir; istek TEK paylaşılan olay döngüsünden gider.
KARŞIT: kilit yokken satır yanıt dönmeden `completed` kapanır (E07 davranışı korunur).
OYZ (zincir 56 AŞAMA 3, 19-11): OTB T-10'dan beri AI Pro sürüşü bobin ÇALIŞMA KAYDI (coil run) açar; `_stop_session_coils` onları
STOP iş parçacığında EŞZAMANLI kapatıyordu → kilitli DB'de yanıt 67,5 sn (T-10 öncesi `c3267319` yeşil, T-10 `89713409` kırmızı).
Kapanış artık satırla aynı kayıt kuyruğunda: kilitliyken yanıt beklemez, kilit kalkınca kayıtlar KAYBOLMADAN kapanır; kilitsizken
yanıt dönmeden kapanmış olur.
"""

from __future__ import annotations

import sqlite3
import threading
import time

import pytest
from fastapi.testclient import TestClient

ARAYUZ_ZAMAN_ASIMI_SN = 8.0  # apps/ui/src/services/apiClient.ts REQUEST_TIMEOUT_MS


def _acik_kosu_kayitlari(o, sid) -> tuple[int, int]:
    """(toplam, kapanmamış) bobin çalışma kaydı sayısı — seansın."""
    with o.db._get_connection() as c:
        toplam = c.execute("SELECT COUNT(*) FROM session_coil_runs WHERE session_id=?", (sid,)).fetchone()[0]
        acik = c.execute(
            "SELECT COUNT(*) FROM session_coil_runs WHERE session_id=? AND ended_epoch IS NULL", (sid,)
        ).fetchone()[0]
    return toplam, acik


@pytest.fixture
def o(monkeypatch, tmp_path):
    import ai_pro_aparati as ap
    from kayitci_donanim import gercek_hc
    from servers import operator_tokens

    o = ap.kur(monkeypatch, tmp_path)
    operator_tokens.temizle_hepsi()
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(o.api.state, "hardware", hc)
            o.hc = hc
            yield o
            o.c.post("/api/ai/pro/stop")
    finally:
        o.air._ai_loop_active = False
        o.geri()


def _baslat_ve_sur(o):
    import ai_pro_aparati as ap

    _pid, r = ap.onayli_baslat(o, organ=0)
    assert r.status_code == 200, r.text[:200]
    with o.api._session_lock:
        sid = o.api._active_session.get("db_session_id")
    ap.kare(o)
    assert ap.bekle(lambda: bool(ap.calisan(o)), 3), "aparat: AI Pro bobinleri sürmedi"
    return sid


def _durdur_paylasilan_dongu(o):
    import ai_pro_aparati as ap
    from anyio.from_thread import start_blocking_portal

    durdu: dict = {}
    with start_blocking_portal(backend="asyncio", backend_options=dict(ap.ISTEMCI_SECENEKLERI)) as portal:
        c = TestClient(o.api.app, client=("127.0.0.1", 50131))
        c.portal = portal

        def _izle(t0):
            while time.monotonic() - t0 < 60:
                if not ap.calisan(o):
                    durdu["sn"] = time.monotonic() - t0
                    return
                time.sleep(0.002)

        t0 = time.monotonic()
        ti = threading.Thread(target=_izle, args=(t0,), daemon=True)
        ti.start()
        r = c.post("/api/ai/pro/stop")
        yanit_sn = time.monotonic() - t0
        ti.join(60)
    return r, yanit_sn, durdu.get("sn")


def test_KRITIK_C2_1_3_tedavi_DB_KILITLIYKEN_AI_Pro_STOP_yaniti_arayuz_zaman_asimini_ASMAZ(o):
    sid = _baslat_ve_sur(o)
    o.db.close_connections()
    kc = sqlite3.connect(str(o.db.db_path), isolation_level=None, timeout=5)
    try:
        kc.execute("PRAGMA locking_mode=EXCLUSIVE")
        kc.execute("BEGIN EXCLUSIVE")
        kc.execute("UPDATE system_settings SET setting_value = setting_value")
        r, yanit_sn, stop_sn = _durdur_paylasilan_dongu(o)
    finally:
        kc.execute("ROLLBACK")
        kc.close()
    print(f"\nC2-1.3: yanıt {r.status_code} {yanit_sn:.2f} sn · STOP donanıma {stop_sn} sn · satır {sid}")
    assert stop_sn is not None and stop_sn < 0.5, f"STOP donanıma {stop_sn} sn'de gitti"
    assert r.status_code == 200 and yanit_sn < ARAYUZ_ZAMAN_ASIMI_SN, (
        f"tedavi DB kilitliyken /ai/pro/stop yanıtı {yanit_sn:.1f} sn bekledi — arayüz {ARAYUZ_ZAMAN_ASIMI_SN:.0f} sn'de "
        "'Durdurulamadı … ACİL DURDUR kullanın' der (bobinler durmuşken)"
    )
    from utils import dongu_disi_yazim

    assert dongu_disi_yazim.bosalt(60), "kayıt kuyruğu kilit kalktıktan sonra boşalmadı"
    toplam, acik = _acik_kosu_kayitlari(o, sid)
    assert toplam >= 1 and acik == 0, f"kilit kalkınca bobin çalışma kayıtları kapanmadı: {acik} / {toplam} açık"


def test_KARSIT_C2_1_3_kilit_yokken_satir_yanit_donmeden_KAPANIR(o):
    sid = _baslat_ve_sur(o)
    r, yanit_sn, stop_sn = _durdur_paylasilan_dongu(o)
    with o.db._get_connection() as c:
        durum = c.execute("SELECT session_status FROM treatment_sessions WHERE id=?", (sid,)).fetchone()[0]
    assert r.status_code == 200 and stop_sn is not None
    assert durum == "stopped", (
        f"kilitsiz durdurmada satır yanıtla birlikte kapanmadı: {durum!r}"
    )  # ODD B-4: elle durdurma
    toplam, acik = _acik_kosu_kayitlari(o, sid)
    assert toplam >= 1 and acik == 0, (
        f"kilitsiz durdurmada bobin çalışma kayıtları yanıtla kapanmadı: {acik} / {toplam} açık"
    )


def test_KRITIK_OYZ_bir_bobinin_kaydi_KAPANAMAZSA_otekiler_ve_satir_YINE_kapanir(o, monkeypatch):
    """Kayıt kuyruğundaki kapanış best-effort: bir bobinin çalışma kaydı kapanırken hata → kalan bobinlerin kayıtları ve seans
    satırı yine kapanır (STOP'u zaten etkilemez; yanıt 200)."""
    sid = _baslat_ve_sur(o)
    with o.db._get_connection() as c:
        bobinler = [
            r[0] for r in c.execute("SELECT DISTINCT coil_id FROM session_coil_runs WHERE session_id=?", (sid,))
        ]
    assert len(bobinler) >= 2, f"aparat: en az iki bobin kaydı gerekir ({bobinler})"
    bozuk = min(bobinler)
    gercek = o.api._finish_coil_run

    def _kayit_hatasi(cid, *a, **k):
        if int(cid) == bozuk:
            raise RuntimeError("sahte kayıt hatası")
        return gercek(cid, *a, **k)

    monkeypatch.setattr(o.api, "_finish_coil_run", _kayit_hatasi)
    r, _yanit_sn, stop_sn = _durdur_paylasilan_dongu(o)
    assert r.status_code == 200 and stop_sn is not None
    with o.db._get_connection() as c:
        durum = c.execute("SELECT session_status FROM treatment_sessions WHERE id=?", (sid,)).fetchone()[0]
        acik = [
            r[0]
            for r in c.execute(
                "SELECT coil_id FROM session_coil_runs WHERE session_id=? AND ended_epoch IS NULL", (sid,)
            )
        ]
    assert durum == "stopped", f"bir kayıt hatası seans satırının kapanışını engelledi: {durum!r}"
    # OYZ4 (D5 kalıcı kilit düzeltmesi): satır kapanışı seansın AÇIK koşularını da kapatır (açılış kurtarmasıyla aynı kural) →
    # kaydı tek başına yazılamayan bobinin koşusu da kapanır; hiçbir koşu açık kalmaz.
    assert acik == [], f"seans kapandığı hâlde açık bobin kaydı kaldı: {acik}"
