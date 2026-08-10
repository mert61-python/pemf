# Author: mertaygn, cglrgrkn
"""DENETİM (per-call-sqlcipher-connect): ana-thread-DIŞI her DB context'i yeni bağlantı
açıp kapatıyordu. SQLCipher'da bu, her seferinde tam `PRAGMA key` PBKDF2'si demek —
ölçüm: 86,49 ms/çağrı yeni bağlantı, 0,025 ms yeniden kullanım (maliyetin %99,5'i anahtar
türetme). Bu dosya havuzun DAVRANIŞINI kilitler: bağlantı thread'de kalır, ama üç koruma
(kuşak / tavan / açık-işlem) korunur. Korumalar olmadan havuz açmak; bayat dosya
tanıtıcısı, sınırsız bellek ve kalıcı yazma kilidi riski getirirdi."""

import threading

from database.treatment_history_db import TreatmentHistoryDB


def _db(temp_app_data):
    return TreatmentHistoryDB(temp_app_data)


def _run_in_thread(fn, name="worker"):
    """Ayrı bir thread'de çalıştır ve sonucu/hatayı geri taşı."""
    box = {}

    def _t():
        try:
            box["v"] = fn()
        except BaseException as e:  # noqa: BLE001 - testte hatayı görünür kılmak için
            box["e"] = e

    th = threading.Thread(target=_t, name=name)
    th.start()
    th.join(20)
    assert not th.is_alive(), "worker thread takıldı"
    if "e" in box:
        raise box["e"]
    return box["v"], th


def test_worker_threadinde_baglanti_yeniden_kullanilir(temp_app_data, monkeypatch):
    """ESKİ DAVRANIŞ: worker thread'de her context yeni bağlantı → N çağrı = N × PBKDF2.
    Bu test düzeltme olmadan başarısız olur (created == 5)."""
    db = _db(temp_app_data)
    created = []
    real = db._create_connection

    def _spy():
        c = real()
        created.append(c)
        return c

    monkeypatch.setattr(db, "_create_connection", _spy)

    def _work():
        for i in range(5):
            db.start_session("Manuel", patient_name=f"P{i}")

    _run_in_thread(_work)

    assert len(created) == 1, (
        f"worker thread {len(created)} bağlantı açtı; havuzda 1 olmalı (her açılış tam SQLCipher PBKDF2 maliyeti)"
    )


def test_kusak_artinca_bayat_baglanti_yenilenir(temp_app_data, monkeypatch):
    """KORUMA 1: DB dosyası altımızdan değişirse (migration rollback / restore) havuzdaki
    bağlantı bayat dosya tanıtıcısına bakar. Kuşak artışı onu bir sonraki kullanımda
    zorla yeniletmeli."""
    db = _db(temp_app_data)
    created = []
    real = db._create_connection
    monkeypatch.setattr(db, "_create_connection", lambda: created.append(real()) or created[-1])

    def _work():
        db.start_session("Manuel", patient_name="A")
        n_before = len(created)
        db._invalidate_connections("test")
        db.start_session("Manuel", patient_name="B")
        return n_before, len(created)

    (n_before, n_after), _ = _run_in_thread(_work)
    assert n_before == 1
    assert n_after == 2, "kuşak artınca bağlantı YENİDEN açılmalıydı (bayat tanıtıcı riski)"

    # Geçersiz kılma sonrası DB hâlâ tutarlı okunmalı (veri kaybı/bozulma yok)
    assert len(db.get_session_history(limit=10)) == 2


def test_tavan_asilinca_eski_ac_kapa_davranisina_duser(temp_app_data, monkeypatch):
    """KORUMA 2: MAX_POOLED_CONNECTIONS emniyet valfi. Tavan dolunca yeni worker
    bağlantıları havuza GİRMEZ, context sonunda kapanır — yavaş ama doğru ve bellek
    sınırlı kalır (havuzun 'sınırsız birikme' itirazının cevabı)."""
    db = _db(temp_app_data)
    monkeypatch.setattr(db, "MAX_POOLED_CONNECTIONS", 1)

    # 1. worker havuzdaki tek yeri kapsın ve thread'i CANLI kalsın (budanmasın)
    hold_open = threading.Event()
    seated = threading.Event()

    def _holder():
        db.start_session("Manuel", patient_name="tutucu")
        seated.set()
        hold_open.wait(20)

    th1 = threading.Thread(target=_holder, name="holder", daemon=True)
    th1.start()
    assert seated.wait(20), "tutucu thread DB'ye bağlanamadı"
    assert len(db._live_conns) == 1

    # 2. worker: tavan dolu → geçici bağlantı, context sonunda kapanmalı
    def _overflow():
        db.start_session("Manuel", patient_name="tasan")
        return len(db._live_conns), getattr(db._local, "conn", None)

    (n_live, leftover), _ = _run_in_thread(_overflow, name="overflow")
    hold_open.set()
    th1.join(20)

    assert n_live == 1, "tavan aşıldığında havuza YENİ kayıt girmemeliydi"
    assert leftover is None, "geçici bağlantı thread'e yapışmamalı (context sonunda kapanır)"
    assert len(db.get_session_history(limit=10)) == 2, "taşan çağrı yine de yazabilmeliydi"


def test_commit_edilmemis_islem_context_sonunda_geri_alinir(temp_app_data):
    """KORUMA 3: HAVUZUN GETİRDİĞİ YENİ TEHLİKE. Eskiden commit'i unutulan bir yazma
    close() ile düşerdi. Bağlantı havuzda kalınca aynı işlem RESERVED kilidini süresiz
    tutar → sonraki TÜM yazarlar 'database is locked' alır. Context çıkışı bunu geri
    almalı."""
    db = _db(temp_app_data)

    def _work():
        # commit YOK — bilerek
        with db._get_connection() as conn:
            conn.execute(
                "INSERT INTO treatment_sessions (session_date, start_time, treatment_mode, session_status) "
                "VALUES (date('now'), datetime('now'), 'Manuel', 'active')"
            )
            assert conn.in_transaction, "test kurulumu: açık bir işlem bekleniyordu"

        pooled = db._local.conn
        assert not pooled.in_transaction, "açık işlem geri alınmadı → kalıcı yazma kilidi"

        # Aynı thread yazmaya devam edebilmeli (kilit yok) ve yarım kayıt görünmemeli
        sid = db.start_session("Manuel", patient_name="sonraki")
        return sid, len(db.get_session_history(limit=50))

    (sid, n), _ = _run_in_thread(_work)
    assert sid
    assert n == 1, f"geri alınmayan yarım kayıt sızdı (beklenen 1, bulunan {n})"


def test_olen_thread_baglantisi_defterden_budanir(temp_app_data):
    """Havuz defteri güçlü referans tutar; thread ölünce bağlantı (ve dosya tanıtıcısı)
    orada takılı kalmamalı — aksi halde uzun çalışan serviste tanıtıcı sızıntısı olur."""
    db = _db(temp_app_data)

    _, th = _run_in_thread(lambda: db.start_session("Manuel", patient_name="gecici"))
    assert th.ident in db._live_conns, "test kurulumu: worker bağlantısı deftere girmeliydi"

    # Arka arkaya 5 kısa-ömürlü worker: defter BÜYÜMEMELİ (her yaratımda ölüler budanır).
    # Ana thread'in kendi bağlantısı defterde kalır → tavan = 1 (ana) + 1 (o anki worker).
    for i in range(5):
        _run_in_thread(lambda i=i: db.start_session("Manuel", patient_name=f"w{i}"), name=f"worker{i}")

    assert th.ident not in db._live_conns, "ölmüş thread'in bağlantısı defterde kaldı (tanıtıcı sızıntısı)"
    assert len(db._live_conns) <= 2, (
        f"defter kısa-ömürlü thread'lerle büyüyor ({len(db._live_conns)}) → tanıtıcı sızıntısı"
    )


def test_close_connections_tum_havuzu_kapatir(temp_app_data):
    """DENETİM: close_connections() eskiden YALNIZ çağıran thread'in bağlantısını
    kapatıyordu. Migration rollback bunu çağırıp hemen ardından db dosyasını siliyor →
    diğer thread'lerin tanıtıcıları açık kalırdı (Windows'ta silme HATASI)."""
    db = _db(temp_app_data)
    _run_in_thread(lambda: db.start_session("Manuel", patient_name="w1"), name="w1")
    db.start_session("Manuel", patient_name="ana")  # ana thread de bir bağlantı açsın

    assert len(db._live_conns) >= 1
    gen_before = db._conn_generation

    db.close_connections()

    assert db._live_conns == {}, "havuz defteri boşaltılmadı"
    assert db._conn_generation > gen_before, "kuşak artmadı → hayatta kalan thread bayat bağlantıyı sürdürür"
    assert getattr(db._local, "conn", None) is None

    # Kapanış sonrası tekrar kullanılabilir olmalı (kapanış kalıcı bozmamalı)
    assert len(db.get_session_history(limit=10)) == 2
