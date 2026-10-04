# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.66 · B-1.2 + D1.78 · B-3.26 — gözlem notu ve not ekranındaki doz parametreleri DOĞRU seansın satırına yazılır.

ÖLÇÜLEN KUSURLAR (fb5785e):
  * D1.66: `/api/session/notes` hedefi istemciden değil süreçteki SON `db_session_id`'den alıyordu → A hastasının notu ve
    50 Hz / 2 mT'si, arada başlamış B hastasının satırına düşüyordu (B henüz sürerken `end_session` ile B'yi KAPATIYORDU).
    `/stop`'tan sonra açılan bobin koşusu bitmiş seansa bağlanıyordu (`current_db_session_id` `is_active`e bakmıyordu).
  * D1.78: bellekteki seans kaybolunca (yeniden başlatma) not her çağrıda YENİ bir 'completed' satır açıyordu (istemcinin
    planlanan süresiyle, koşusuz/kanıtsız) — kurtarılmış "Elektrik Kesintisi" satırının yanında ikinci bir tedavi.
GERİYE UYUM (plan "uyandırır"): seans kimliği göndermeyen eski istemci (APK 2.3.34) için güvenli dal — bellekteki seans
bitmişse ve hastası aynıysa o; değilse bu hastanın SON BİTMİŞ seansı (12 sa içinde); o da yoksa 409 (YENİ satır AÇILMAZ).
"""

from __future__ import annotations

import ai_pro_aparati as ap
import pytest


@pytest.fixture
def o(monkeypatch, tmp_path):
    import database.treatment_history_db as thdb
    from kayitci_donanim import gercek_hc

    ns = ap.kur(monkeypatch, tmp_path)
    # Not ucu (bugün) DB'ye `get_treatment_db(_app_data_dir())` ile AYRI yoldan gider — o yol da aynı geçici DB'ye.
    monkeypatch.setattr(thdb, "get_treatment_db", lambda *a, **k: ns.db)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            yield ns
    finally:
        ns.geri()


def _baslat(o, hasta, bobinler=(1,)):
    r = o.c.post(
        "/api/session/start",
        json={
            "mode": "Manuel",
            "frequency": 100,
            "duty": 40,
            "phase": 0,
            "duration_minutes": 20,
            "coil_ids": list(bobinler),
            "patient_name": hasta,
        },
    )
    assert r.status_code == 200 and r.json().get("status") == "success", r.text[:300]
    sid = r.json()["session"]["db_session_id"]
    assert sid, "aparat: başlatma yanıtı seans DB kimliğini taşımıyor"
    return sid


def _durdur(o):
    assert o.c.post("/api/session/stop").status_code == 200


def _not(o, **alanlar):
    govde = {"notes": "", "patient_name": "", "mode": "Manuel", "frequency": 0, "intensity": 0, "duration_minutes": 20}
    govde.update(alanlar)
    return o.c.post("/api/session/notes", json=govde)


def _satirlar(o):
    with o.db._get_connection() as conn:
        rows = conn.execute(
            "SELECT id, patient_name, patient_notes, session_status, frequency_hz FROM treatment_sessions ORDER BY id"
        ).fetchall()
    return [dict(r) for r in rows]


def _satir(o, sid):
    return next(r for r in _satirlar(o) if r["id"] == sid)


def _bellegi_sil(o):
    """Süreç yeniden başlatması: bellekteki seans kaybolur."""
    with o.api._session_lock:
        o.api._active_session.clear()


def _sure(o, sid):
    with o.db._get_connection() as conn:
        return conn.execute("SELECT duration_minutes FROM treatment_sessions WHERE id = ?", (sid,)).fetchone()[0]


def test_KRITIK_D166_not_ISTEMCININ_seans_kimligine_yazilir_SONRAKI_seansa_DUSMEZ(o):
    """AYNI ADLI iki hasta ("Boncuk" — klinikte gerçekçi): yalnız seans kimliği doğru satırı ayırt edebilir."""
    sid_a = _baslat(o, "Boncuk")
    _durdur(o)
    sure_a = _sure(o, sid_a)
    sid_b = _baslat(o, "Boncuk")
    _durdur(o)
    r = _not(o, session_id=sid_a, notes="A notu", patient_name="Boncuk", frequency=50, intensity=2, duration_minutes=20)
    assert r.status_code == 200 and r.json().get("session_id") == sid_a, r.text[:300]
    assert _satir(o, sid_a)["patient_notes"] == "A notu", "A'nın notu A'nın satırına YAZILMADI"
    assert not _satir(o, sid_b)["patient_notes"], "A'nın notu B'nin (yanlış hastanın) satırına düştü"
    assert _sure(o, sid_a) == sure_a, "not, kapanmış seansın GERÇEK süresini planlanan süreyle EZDİ"
    n = len(_satirlar(o))
    _bellegi_sil(o)  # yeniden başlatma sonrası aynı istemci yeniden dener
    r2 = _not(o, session_id=sid_a, notes="A notu", patient_name="Boncuk", frequency=50, intensity=2)
    assert r2.status_code == 200, r2.text[:300]
    assert len(_satirlar(o)) == n, "yeniden denemede YENİ seans satırı açıldı"


def test_KRITIK_D166_ESKI_istemci_notu_SUREN_baska_seansi_KAPATMAZ_kendi_seansina_yazilir(o):
    """Kimliksiz (APK 2.3.34) not, B sürerken gelir: B'nin satırına yazılmamalı ve B'yi DB'de kapatmamalı."""
    sid_a = _baslat(o, "Rex")
    _durdur(o)
    sid_b = _baslat(o, "Boncuk")
    r = _not(o, notes="A notu (eski istemci)", patient_name="Rex", frequency=50, intensity=2)
    assert r.status_code == 200, r.text[:300]
    b = _satir(o, sid_b)
    assert b["session_status"] == "active" and not b["patient_notes"], (
        f"eski istemcinin A notu SÜREN B seansına yazıldı/B'yi kapattı: {b}"
    )
    assert _satir(o, sid_a)["patient_notes"] == "A notu (eski istemci)", (
        "eski istemcinin notu kendi seansına bağlanmadı"
    )


def test_KRITIK_D178_yeniden_baslatma_sonrasi_not_YENI_completed_satir_ACMAZ_kurtarilan_satira_yazilir(o):
    sid = _baslat(o, "Pamuk")
    o.db.recover_stale_active_sessions(max_age_hours=0)  # süreç ölümü → açılış kurtarması
    _bellegi_sil(o)
    assert _satir(o, sid)["session_status"] == "ABORTED_DUE_TO_POWER"
    for _ in range(2):
        r = _not(o, notes="kurtarma sonrası not", patient_name="Pamuk", duration_minutes=20)
        assert r.status_code == 200, r.text[:300]
    pamuk = [s for s in _satirlar(o) if s["patient_name"] == "Pamuk"]
    assert len(pamuk) == 1, f"kimliksiz not YENİ seans satırı açtı (Pamuk satırları: {pamuk})"
    assert pamuk[0]["session_status"] == "ABORTED_DUE_TO_POWER" and pamuk[0]["patient_notes"] == "kurtarma sonrası not"


def test_KRITIK_D178_ayni_hastanin_SUREN_seansi_varken_kimliksiz_not_ONA_yazilmaz(o):
    """Kurtarılmış (bitmiş) Pamuk seansı + başka istemcinin başlattığı YENİ Pamuk seansı sürüyor: eski istemcinin
    kimliksiz notu süren seansa değil, bitmiş seansa gider (eski istemci notu seansı BİTTİKTEN sonra gönderir)."""
    sid_eski = _baslat(o, "Pamuk")
    o.db.recover_stale_active_sessions(max_age_hours=0)
    _bellegi_sil(o)
    sid_yeni = _baslat(o, "Pamuk")
    r = _not(o, notes="eski seansın notu", patient_name="Pamuk")
    assert r.status_code == 200, r.text[:300]
    yeni = _satir(o, sid_yeni)
    assert yeni["session_status"] == "active" and not yeni["patient_notes"], f"not SÜREN seansa yazıldı: {yeni}"
    assert _satir(o, sid_eski)["patient_notes"] == "eski seansın notu"


def test_KRITIK_D178_eslesen_seans_YOKSA_409_ve_YENI_satir_ACILMAZ(o):
    n = len(_satirlar(o))
    r = _not(o, notes="sahipsiz not", patient_name="Hayalet")
    assert r.status_code == 409, f"seansı belirlenemeyen not: {r.status_code} {r.text[:200]}"
    assert len(_satirlar(o)) == n, "seansı belirlenemeyen not YENİ 'completed' satır açtı"


def test_KRITIK_D166_bilinmeyen_seans_kimligi_404_satir_ACILMAZ(o):
    n = len(_satirlar(o))
    r = _not(o, session_id=987654, notes="x")
    assert r.status_code == 404, f"{r.status_code} {r.text[:200]}"
    assert len(_satirlar(o)) == n


def test_KRITIK_D166_stop_SONRASI_bobin_kosusu_BITMIS_seansa_BAGLANMAZ(o):
    sid = _baslat(o, "Rex")
    _durdur(o)
    once = len(o.db.get_session_coil_runs(sid))
    r = o.c.post("/api/coil/2/control", json={"start": True, "freq": 100, "duty": 40, "phase": 0, "duration": 60})
    assert r.status_code == 200 and r.json().get("status") == "success", r.text[:200]
    assert len(o.db.get_session_coil_runs(sid)) == once, "seanssız sürüşün koşusu BİTMİŞ seansa bağlandı"


def test_KRITIK_D166_kimliksiz_not_ayni_hastanin_EN_SON_bitmis_seansina_yazilir(o):
    """1-F inceleme (çürütme: 12 sa penceresinde AYNI hastanın iki bitmiş seansı): yeniden başlatma sonrası (bellek boş)
    kimliksiz not hastanın EN SON başlayan bitmiş seansına gider, eskisine DEĞİL. Hepsi tek bitmiş seansla kurulduğu için
    "en ESKİ bitmiş seans" mutantı (`ORDER BY started_epoch ASC`) mevcut 24 kolda YEŞİL kalıyordu."""
    import time

    sid_1 = _baslat(o, "Pamuk")
    _durdur(o)
    sid_2 = _baslat(o, "Pamuk")
    _durdur(o)
    simdi = time.time()
    with o.db._get_connection() as conn:  # gerçekçi başlangıçlar (eşit damga sıralamayı belirsizleştirmesin)
        conn.execute("UPDATE treatment_sessions SET started_epoch = ? WHERE id = ?", (simdi - 3 * 3600, sid_1))
        conn.execute("UPDATE treatment_sessions SET started_epoch = ? WHERE id = ?", (simdi - 600, sid_2))
        conn.commit()
    _bellegi_sil(o)
    r = _not(o, notes="son seansin notu", patient_name="Pamuk")
    assert r.status_code == 200 and r.json().get("session_id") == sid_2, (
        f"kimliksiz not hastanın EN SON bitmiş seansına ({sid_2}) değil {r.json().get('session_id')}'e gitti: {r.text[:200]}"
    )
    assert _satir(o, sid_2)["patient_notes"] == "son seansin notu" and not _satir(o, sid_1)["patient_notes"]


def test_KRITIK_D166_kimliksiz_not_bellekteki_HASTASIZ_seansa_DUSMEZ_kendi_hastasinin_seansina_gider(o):
    """1-F inceleme: eski istemci (kimliksiz) A="Rex" notunu, arada başka bir istemcinin HASTASIZ (anonim) seansı bitmişken
    gönderir. Bellek dalı yalnız aynı hasta için geçerlidir; hastası bilinmeyen bellek seansı Rex'in notunu ALMAMALI —
    Rex'in son bitmiş seansı adla bulunur."""
    sid_rex = _baslat(o, "Rex")
    _durdur(o)
    sid_anonim = _baslat(o, "")
    _durdur(o)
    r = _not(o, notes="Rex notu (eski istemci)", patient_name="Rex", frequency=50, intensity=2)
    assert r.status_code == 200, r.text[:300]
    assert not _satir(o, sid_anonim)["patient_notes"], (
        f"Rex'in notu HASTASIZ (başka istemcinin) seansına yazıldı: {r.json()}"
    )
    assert _satir(o, sid_rex)["patient_notes"] == "Rex notu (eski istemci)", (
        f"not Rex'in seansına yazılmadı: {r.json()}"
    )
