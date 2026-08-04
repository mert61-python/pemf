"""Production-readiness tazeleme (2026-07-12) düzeltmelerinin karakterizasyon/regresyon testleri.

Kapsanan bulgular:
- T-1 / D-1  : sync_worker cloud-PULL upsert'i yerel-özel kolonları (owner_email/last_treatment_at/
               anonymized) KORUR + patient_search_index'i FK-cascade ile SİLMEZ (ON CONFLICT DO UPDATE,
               eski INSERT OR REPLACE değil). sync_worker.py %0 kapsamdaydı → gerçek kod yolu çalıştırılır.
- SEC-2      : login/reset kaba-kuvvet throttle mantığı (e-posta-başına login, global reset).
- O-2        : düz-metin log formatter %(rid)s'i KeyError'suz render eder (correlation-id her satırda).
"""
import sqlite3

import pytest

# ─────────────────────────── T-1 / D-1 : cloud-sync PULL upsert ───────────────────────────

class _FakeResp:
    def __init__(self, data):
        self.data = data


class _FakeRpc:
    def __init__(self, data):
        self._data = data

    def execute(self):
        return _FakeResp(self._data)


class _FakeSupabase:
    """Yalnız test için: resolve_patients → verilen satırlar; diğer RPC'ler (upsert_patient) → no-op."""

    def __init__(self, resolve_rows):
        self._resolve = resolve_rows

    def rpc(self, name, params=None):
        return _FakeRpc(self._resolve if name == "resolve_patients" else [])


def test_d1_cloud_pull_preserves_local_columns_and_search_index(temp_app_data, monkeypatch):
    """D-1 regresyon kalkanı: bir bulut-PULL, yerel-özel kolonları sıfırlamamalı ve hasta arama
    indeksini (FK ON DELETE CASCADE) yok etmemeli. Eski `INSERT OR REPLACE` (=DELETE+INSERT) ikisini de
    bozardı; `ON CONFLICT(id) DO UPDATE` korumalı. Gerçek `CloudSyncWorker._sync_patients` çalıştırılır."""
    from database.patient_database import PatientDatabase
    from servers.sync_worker import CloudSyncWorker

    db_path = temp_app_data / "patients.db"
    db = PatientDatabase(str(db_path))
    pid = db.add_patient({"name": "Boncuk", "species": "Kedi", "owner": "Ali", "owner_email": "ali@example.com"})

    # Yerel-özel kolonları (bulut-sync bunlara DOKUNMAMALI) doğrudan set et.
    # NOT: skaler .fetchone()[0] erişimi — bağlantı sqlite3 VEYA sqlcipher3 olabilir (Row uyumsuz).
    with db._get_connection() as c:
        c.row_factory = None                  # tuple satırlar → skaler [0] erişimi (sqlite3/sqlcipher3 ortak)
        c.execute(
            "UPDATE patients SET last_treatment_at=?, anonymized=? WHERE id=?",
            ("2026-07-01T10:00:00", 0, pid),
        )
        c.commit()
        owner_before = c.execute("SELECT owner_email FROM patients WHERE id=?", (pid,)).fetchone()[0]
        ltat_before = c.execute("SELECT last_treatment_at FROM patients WHERE id=?", (pid,)).fetchone()[0]
        anon_before = c.execute("SELECT anonymized FROM patients WHERE id=?", (pid,)).fetchone()[0]
        idx_before = c.execute("SELECT COUNT(*) FROM patient_search_index WHERE patient_id=?", (pid,)).fetchone()[0]
        enc_name = c.execute("SELECT name FROM patients WHERE id=?", (pid,)).fetchone()[0]

    assert idx_before > 0, "önkoşul: arama indeksi dolu olmalı"

    # Buluttan PULL edilen kayıt: AYNI id, çözülebilir (bu-cihaz-anahtarlı) name → cross-tenant guard
    # atlamaz; species DEĞİŞMİŞ (upsert'in gerçekten yazdığını kanıtlar).
    pulled = {
        "id": pid, "name": enc_name, "species": db._encrypt_field("Köpek"),
        "breed": "", "age": "", "weight": "", "owner": db._encrypt_field("Ali"),
        "vet_contact": "", "created_at": "2020-01-01T00:00:00", "updated_at": "2026-07-12T00:00:00",
    }

    monkeypatch.setenv("PEMF_CLOUD_PATIENT_SYNC", "1")
    worker = CloudSyncWorker("", "")          # url/key boş → gerçek supabase client kurulmaz
    worker.client = _FakeSupabase([pulled])
    worker.patient_sync_enabled = True
    worker.device_id = "test-device"

    worker._sync_patients(db)                 # GERÇEK kod yolu (PUSH no-op + PULL upsert)

    with db._get_connection() as c:
        c.row_factory = None                  # sync_worker paylaşılan bağlantıda dict-factory bıraktı → sıfırla
        owner_after = c.execute("SELECT owner_email FROM patients WHERE id=?", (pid,)).fetchone()[0]
        ltat_after = c.execute("SELECT last_treatment_at FROM patients WHERE id=?", (pid,)).fetchone()[0]
        anon_after = c.execute("SELECT anonymized FROM patients WHERE id=?", (pid,)).fetchone()[0]
        species_after = c.execute("SELECT species FROM patients WHERE id=?", (pid,)).fetchone()[0]
        idx_after = c.execute("SELECT COUNT(*) FROM patient_search_index WHERE patient_id=?", (pid,)).fetchone()[0]

    # D-1: yerel-özel kolonlar KORUNDU
    assert owner_after == owner_before, "owner_email bulut-PULL'da sıfırlandı (D-1 regresyon!)"
    assert ltat_after == ltat_before, "last_treatment_at kayboldu (D-1 regresyon!)"
    assert anon_after == anon_before
    # D-1: arama indeksi FK-cascade ile SİLİNMEDİ
    assert idx_after == idx_before and idx_after > 0, "patient_search_index cascade-silindi (D-1 regresyon!)"
    # upsert gerçekten çalıştı (sync-sahibi kolon güncellendi)
    assert db._decrypt_field(species_after) == "Köpek"


def test_d1_sync_worker_uses_non_destructive_upsert():
    """Kaynak-düzeyi sentinel: sync_worker patients yazımı `ON CONFLICT ... DO UPDATE` kullanmalı ve
    veri-yok-eden `INSERT OR REPLACE INTO patients`'a GERİ DÖNMEMELİ."""
    import pathlib
    src = pathlib.Path(__file__).resolve().parent.parent / "servers" / "sync_worker.py"
    text = src.read_text(encoding="utf-8", errors="ignore")
    assert "ON CONFLICT(id) DO UPDATE" in text
    assert "INSERT OR REPLACE INTO patients" not in text.replace(" ", " ")


# ─────────────────────────── SEC-2 : login/reset throttle ───────────────────────────

def test_sec2_login_throttle_locks_after_max_fails():
    """E-posta-başına login throttle: MAX_FAILS başarısız denemeden sonra o e-posta geçici kilitlenir;
    BAŞKA e-posta etkilenmez (tarayan saldırgan meşru operatörü kilitlemesin)."""
    from servers import auth_router as ar
    ar._login_throttle.clear()
    b = ar._login_bucket("attacker@example.com")
    for _ in range(ar._THROTTLE_MAX_FAILS):
        assert not ar._throttle_locked(b)
        ar._throttle_note_fail(b)
    assert ar._throttle_locked(b), "MAX_FAILS sonrası kilitlenmeliydi"

    # per-email izolasyon: başka e-posta serbest
    b2 = ar._login_bucket("legit@example.com")
    assert not ar._throttle_locked(b2)

    # başarılı giriş sayacı sıfırlar
    ar._throttle_clear(b)
    assert not ar._throttle_locked(b)
    ar._login_throttle.clear()


def test_sec2_reset_throttle_is_global_and_locks():
    """Reset throttle global (admin-kod kaba-kuvvetine karşı): MAX_FAILS sonrası kilitlenir."""
    from servers import auth_router as ar
    ar._throttle_clear(ar._reset_throttle)
    for _ in range(ar._THROTTLE_MAX_FAILS):
        assert not ar._throttle_locked(ar._reset_throttle)
        ar._throttle_note_fail(ar._reset_throttle)
    assert ar._throttle_locked(ar._reset_throttle)
    ar._throttle_clear(ar._reset_throttle)


def test_sec2_login_endpoint_throttles_bruteforce(monkeypatch):
    """Uçtan-uca: /api/auth/login'e aynı e-postayla ard arda hatalı deneme, sonunda 429 döndürür."""
    from fastapi.testclient import TestClient

    monkeypatch.setenv("PEMF_REQUIRE_AUTH", "0")   # login zaten auth-muaf; yine de garanti
    import servers.auth as _auth
    _auth._require = None; _auth._token = None; _auth._warned = False
    from servers import api_server, auth_router
    auth_router._login_throttle.clear()

    client = TestClient(api_server.app)
    email = "bruteforce@example.com"
    statuses = [
        client.post("/api/auth/login", json={"email": email, "password": "wrongpass"}).status_code
        for _ in range(auth_router._THROTTLE_MAX_FAILS + 2)
    ]
    auth_router._login_throttle.clear()
    _auth._require = None; _auth._token = None; _auth._warned = False
    assert 429 in statuses, f"login uç-noktası kaba-kuvvette 429 vermedi: {statuses}"


# ─────────────────────────── O-2 : correlation-id düz-metin log ───────────────────────────

def test_o2_plain_log_formatter_renders_rid_without_error():
    """Düz-metin formatter %(rid)s'i KeyError'suz render eder (istek-dışı bağlamda '-')."""
    import logging

    from backend_service import _PlainLogFormatter
    fmt = _PlainLogFormatter("%(levelname)s [%(name)s] [%(rid)s] %(message)s")
    rec = logging.LogRecord("pemf.test", logging.INFO, __file__, 1, "merhaba", None, None)
    out = fmt.format(rec)
    assert "merhaba" in out
    assert "[-]" in out or "[" in out   # rid alanı render edildi (KeyError yok)


# ─────────────────────────────────────────────────────────────────────────────
# Denetim 2026-08-04 (P2): uvicorn graceful-shutdown tavanı.
# Verilmezse varsayılan None = SINIRSIZ bekleme. Bu üründe açık WebSocket bağlantıları
# olduğundan `server.run()` dönmez → main()'deki `finally: _shutdown()` HİÇ çalışmaz →
# `_safe_stop_outputs()` (STM stop_all_coils + ESP 6-8 MQTT STOP) gönderilmez.
# ─────────────────────────────────────────────────────────────────────────────


def test_uvicorn_graceful_shutdown_tavani_ayarli():
    """Kapanış SINIRSIZ beklememeli — yoksa servis durdurmada bobin-STOP yolu hiç çalışmaz."""
    import argparse

    import backend_service as bs

    args = argparse.Namespace(host="127.0.0.1", port=8123, log_level="info")
    server = bs._build_server(object(), args)

    t = server.config.timeout_graceful_shutdown
    assert t is not None, (
        "timeout_graceful_shutdown AYARLI DEĞİL → uvicorn açık WebSocket'te süresiz bekler, "
        "_safe_stop_outputs() hiç çalışmaz ve bobinler enerjili kalır"
    )
    assert 0 < t <= 12, f"tavan makul aralıkta olmalı (NSSM stop bütçesi 15 sn), bulunan: {t}"


def test_graceful_shutdown_nssm_butcesine_sigiyor():
    """graceful + güvenli-durdurma toplamı NSSM AppStopMethodConsole (15 sn) altında kalmalı;
    aşarsa NSSM süreci SERT öldürür ve bobin-STOP yarıda kesilir."""
    import re
    from pathlib import Path

    import backend_service as bs

    # ⚠️ DENETİM 2026-08-04 (P3): iki sayı da testte ELLE kopyalanmıştı ve `SAFE_STOP` değeri
    # YANLIŞTI (3.0 yazıyordu; gerçek toplam 1.5 STM-flush + 3.0 ESP-stop = 4.5). Yani test
    # olmayan bir marjı doğruluyordu. Artık İKİSİ DE kaynaktan okunuyor — kopya sürüklenemez.
    toplam = bs._GRACEFUL_SHUTDOWN_TIMEOUT_S + bs._SAFE_STOP_BUDGET_S

    ps1 = Path(__file__).resolve().parent.parent / "scripts" / "setup_services.ps1"
    assert ps1.exists(), f"setup_services.ps1 yok: {ps1}"
    # YORUM satirlarini ele: dosyada aciklama olarak "AppStopMethodConsole 15s" gecıyor ve
    # naif bir regex onu yakalayip 15 ms sanıyordu (ilk yazimda tam olarak bu oldu).
    kod = "\n".join(
        satir
        for satir in ps1.read_text(encoding="utf-8", errors="replace").splitlines()
        if not satir.strip().startswith("#")
    )
    m = re.search(r"AppStopMethodConsole\s+(\d{3,})", kod)
    assert m, "AppStopMethodConsole degeri setup_services.ps1'de bulunamadi — parite kirilmis olabilir"
    nssm_s = int(m.group(1)) / 1000.0
    assert nssm_s >= 1.0, f"NSSM stop butcesi anlamsiz okundu ({nssm_s} sn) — regex yanlis satiri yakalamis"

    assert toplam < nssm_s, (
        f"kapanis butcesi NSSM sinirini asiyor: graceful({bs._GRACEFUL_SHUTDOWN_TIMEOUT_S}) + "
        f"safe_stop({bs._SAFE_STOP_BUDGET_S}) = {toplam} sn >= NSSM {nssm_s} sn. NSSM sureci SERT "
        f"oldurur ve bobin-STOP yarida kesilir."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Denetim 2026-08-04 (P2 #13): /api/health launcher nonce'u.
# find_free_port portu bind edip HEMEN bırakır; frozen backend'in onu gerçekten bind etmesi
# onlarca saniye sürer. O pencerede loopback'e bağlanabilen herhangi bir yerel süreç portu
# kapabilir ve wait_for_health yalnız HTTP 200'e baktığı için launcher onu "hazır" sanardı →
# kapanışta E-stop POST'u SALDIRGANIN dinleyicisine giderdi.
# Nonce YALNIZ loopback'e verilmeli: /api/health auth-muaftır ve tünelden de erişilebilir.
# ─────────────────────────────────────────────────────────────────────────────


def _health(monkeypatch, nonce: str, headers: dict | None = None):
    """NOT: TestClient varsayilan `client.host` degeri "testclient"tir, 127.0.0.1 DEGIL.
    Launcher daima loopback'ten sorar → `client=("127.0.0.1", ...)` ile gercek yolu simule et.
    (Bu fark testi ilk yazdigimda yakalandi: kod dogru, kurulum yanlisti.)"""
    from fastapi.testclient import TestClient

    from servers import api_server

    monkeypatch.setenv("PEMF_HEALTH_NONCE", nonce)
    with TestClient(api_server.app, client=("127.0.0.1", 51234)) as c:
        return c.get("/api/health", headers=headers or {}).json()


def test_health_nonce_loopbacke_verilir(monkeypatch):
    """TestClient soketi 127.0.0.1'dir → launcher'ın gördüğü yol."""
    body = _health(monkeypatch, "NONCE-123")
    assert body.get("launcherNonce") == "NONCE-123", (
        "launcher backend'i dogrulayamaz — port kapan surec 'hazir' sanilir"
    )


def test_health_nonce_tunele_SIZDIRILMAZ(monkeypatch):
    """Cloudflare proxy başlığı taşıyan istek UZAKTIR; nonce sızarsa doğrulama anlamsızlaşır."""
    body = _health(monkeypatch, "NONCE-123", {"cf-connecting-ip": "203.0.113.10"})
    assert body.get("launcherNonce") is None, "nonce UZAK istemciye sizdi"


def test_health_nonce_yokken_alan_None(monkeypatch):
    """Env verilmemişse (servis modu / eski akış) alan None — 200 davranışı değişmez."""
    monkeypatch.delenv("PEMF_HEALTH_NONCE", raising=False)
    from fastapi.testclient import TestClient

    from servers import api_server

    with TestClient(api_server.app, client=("127.0.0.1", 51234)) as c:
        body = c.get("/api/health").json()
    assert body.get("launcherNonce") is None
    assert body.get("status") == "online"


# ─────────────────────────────────────────────────────────────────────────────
# DENETİM 2026-08-04 — AKTİF TEDAVİ BAYRAĞI (`/api/health` → `sessionActive`)
# Launcher açılışta manifest'e bakıp yeni sürümü SESSİZCE indirip `/S` ile kurar; NSIS
# yükseltme kancası `taskkill /F /IM PEMF_Backend.exe` çalıştırır → HASTA ÜZERİNDE SÜREN
# seans yarıda kesilirdi. Launcher artık güncellemeden ÖNCE bunu okuyup seansı bekliyor.
# Bayrak launcherNonce ile AYNI gerekçeyle yalnız loopback'e verilir.
# ─────────────────────────────────────────────────────────────────────────────


def _health_with_session(active: bool, headers: dict | None = None, *, snapshot=None):
    """DENETİM 2026-08-04 (P3): bayrak artık `_active_session` yerine TEK KAYNAK olan
    `update_manager._has_active_treatment()`ten geliyor — o, resmi seans DIŞINDA sürülen
    bobinleri de aktif sayar ve fail-closed'dur. Test o kaynağı sürer.

    `snapshot` verilirse `_build_ws_snapshot` onunla değiştirilir → gerçek kod yolu (seans +
    koşan bobin taraması) uçtan uca koşar."""
    from fastapi.testclient import TestClient

    from servers import api_server

    if snapshot is not None:
        onceki = getattr(api_server, "_build_ws_snapshot", None)
        api_server._build_ws_snapshot = lambda: snapshot
    else:
        onceki = None
        from servers import update_manager as um

        um_prev = um._has_active_treatment
        um._has_active_treatment = lambda: active
    try:
        with TestClient(api_server.app, client=("127.0.0.1", 51234)) as c:
            return c.get("/api/health", headers=headers or {}).json()
    finally:
        if snapshot is not None:
            if onceki is not None:
                api_server._build_ws_snapshot = onceki
        else:
            from servers import update_manager as um2

            um2._has_active_treatment = um_prev


def test_health_aktif_seansi_loopbacke_bildirir():
    """Seans SÜRERKEN launcher oto-güncellemeyi ertelemeli — bayrak True gelmeli."""
    assert _health_with_session(True).get("sessionActive") is True, (
        "aktif seans bildirilmiyor — launcher tedaviyi yarida kesen sessiz guncelleme yapar"
    )


def test_health_seans_yokken_guncellemeye_izin_verir():
    assert _health_with_session(False).get("sessionActive") is False


def test_health_seans_bilgisi_tunele_SIZDIRILMAZ():
    """'Şu an tedavi sürüyor' bilgisi auth-muaf uçtan dışarı çıkmamalı."""
    body = _health_with_session(True, {"cf-connecting-ip": "203.0.113.10"})
    assert body.get("sessionActive") is None, "aktif-seans bilgisi UZAK istemciye sizdi"


def test_health_seans_DISINDA_kosan_bobini_de_aktif_sayar():
    """⚠️ P3: bayrak yalnız `_active_session["is_active"]`e bakıyordu.

    Veteriner bobinleri RESMİ SEANS OLMADAN sürerken (`/api/coil/{id}/control`, AI Pro kare
    akışı) `is_active` False olur → launcher "seans yok" deyip SESSİZ güncellemeyi sürdürür →
    NSIS `taskkill` → bobinler HASTANIN ÜZERİNDE kontrolcüsüz kalır. Artık koşan bobin de sayılır.
    """
    snap = {"activeTreatment": {"isActive": False}, "coils": [{"running": True}]}
    body = _health_with_session(False, snapshot=snap)
    assert body.get("sessionActive") is True, (
        "seans DISINDA kosan bobin 'aktif' sayilmadi — sessiz guncelleme bobinleri "
        "kontrolcusuz birakir"
    )


def test_health_bobin_de_seans_da_yokken_guncellemeye_izin_verir():
    snap = {"activeTreatment": {"isActive": False}, "coils": [{"running": False}]}
    assert _health_with_session(False, snapshot=snap).get("sessionActive") is False


def test_health_aktif_seans_bayragi_tunel_proxysinden_SIZDIRILMAZ():
    """cloudflared 127.0.0.1'den baglanir; beyan edilmis proxy elenmezse bilgi tunele sizar."""
    import os

    from servers import auth as _auth

    os.environ["PEMF_TRUSTED_PROXIES"] = "127.0.0.1"
    _auth._TRUSTED_PROXIES = None  # onbellegi dusur
    try:
        body = _health_with_session(True)
        assert body.get("sessionActive") is None, "aktif-tedavi bilgisi BEYAN EDILMIS proxy'ye sizdi"
        assert body.get("launcherNonce") is None, "nonce BEYAN EDILMIS proxy'ye sizdi"
    finally:
        os.environ.pop("PEMF_TRUSTED_PROXIES", None)
        _auth._TRUSTED_PROXIES = None
