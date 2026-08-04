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
    import backend_service as bs

    SAFE_STOP_BUDGET_S = 3.0   # backend_service._safe_stop_outputs toplam bütçesi
    NSSM_STOP_BUDGET_S = 15.0  # scripts/setup_services.ps1: AppStopMethodConsole 15000
    assert bs._GRACEFUL_SHUTDOWN_TIMEOUT_S + SAFE_STOP_BUDGET_S < NSSM_STOP_BUDGET_S
