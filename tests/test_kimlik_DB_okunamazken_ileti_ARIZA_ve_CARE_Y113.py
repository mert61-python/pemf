# -*- coding: utf-8 -*-
"""Y113 (S-B2.5 · 2-B incelemesi) — kimlik veritabanı OKUNAMAZKEN kapılar KAPALI kalır; ileti, günlük ve `/api/operators`
ARIZAYI ve ÇAREYİ söyler, "Operatör seçin" DEMEZ.

ÖLÇÜLEN KUSUR: `be3e6ee` (B2-1.1) kimlik kapılarını auth DB arızasında fail-closed yaptı; ama 428 iletisi "Operatör seçin —
… hangi hekim olduğunuzu seçin" kaldı: operatör listesi de okunamıyor (seçmek imkânsız), operatörsüz klinikte seçilecek kimse
yok — operatör yanlış eyleme yönlendiriliyordu; günlük satırı ("kayitli operator listesi okunamadi …") çare söylemiyordu.
SAHİP KARARI Y113: kapılar KAPALI kalır (değerlendirme ve silme 428; STOP ve ACİL DURDUR etkilenmez); ileti ve günlük
"Cihazın kimlik veritabanı okunamıyor — …" der ve çareyi söyler.

Arıza EN ALT katta, DÖRT gerçek biçimde (2-B incelemesinin ölçtüğü sınıf): GERÇEK SQLite kilidi (ikinci bağlantı
`locking_mode=EXCLUSIVE` + `BEGIN EXCLUSIVE`), var olmayan dizin, SQLite olmayan dosya, Windows ACL reddi (ürünün kendi
`utils.file_acl.lock_down_file` yardımcısı, yalnız SYSTEM + Administrators — yükseltilmemiş süreç OKUYAMAZ). Tekil `AuthDB`
örneğinin `db_path`'i testin tmp'sindeki kopyaya çevrilir; `AuthDB`'nin ve `servers.auth`'un kendi kodu koşar.
Beklenen metin bu dosyada SABİT yazılır (mutasyon hedefi `servers.auth`'tan okunmaz).
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

AYSE = "dr.ayse@klinik.com"
MEHMET = "dr.mehmet@klinik.com"
TEK = "tek@klinik.com"
LAN = ("192.168.1.87", 52335)
ARIZA_BASI = "Cihazın kimlik veritabanı okunamıyor —"
CARE = "uygulamayı kapatıp yeniden açın"
ARIZA_KIPLERI = ["kilit", "yol_yok", "bozuk_dosya", "acl"]


def _operatorleri_sil(c):
    for op in c.get("/api/operators").json().get("data", []):
        c.post("/api/operators/remove", json={"email": op["email"]})


@pytest.fixture
def o(monkeypatch, tmp_path):
    import ai_pro_aparati as apa
    from database.patient_database import PatientDatabase
    from kayitci_donanim import gercek_hc
    from servers import operator_tokens, patient_router
    from servers.history_router import get_db

    o = apa.kur(monkeypatch, tmp_path)
    o.hdb = PatientDatabase(str(tmp_path / "patients.db"))
    monkeypatch.setattr(patient_router, "get_patient_database", lambda: o.hdb)
    o.api.app.dependency_overrides[get_db] = lambda: o.db
    secenek = dict(apa.ISTEMCI_SECENEKLERI)
    o.tmp = tmp_path
    o.yerel = TestClient(o.api.app, client=("127.0.0.1", 52334), backend_options=secenek)
    o.lan = TestClient(o.api.app, client=LAN, backend_options=secenek)
    operator_tokens.temizle_hepsi()
    _operatorleri_sil(o.yerel)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(o.api.state, "hardware", hc)
            yield o
            o.lan.post("/api/session/stop")
    finally:
        o.api.app.dependency_overrides.pop(get_db, None)
        operator_tokens.temizle_hepsi()
        _operatorleri_sil(o.yerel)
        o.geri()


def _iki_hekim_jetonlar(o):
    j = {}
    for e, ad in ((AYSE, "Dr. Ayşe"), (MEHMET, "Dr. Mehmet")):
        r = o.yerel.post("/api/operators/enroll", json={"email": e, "display_name": ad, "pin": "123456"})
        assert r.status_code == 200, r.text[:200]
        j[e] = o.yerel.post("/api/operators/verify", json={"email": e, "pin": "123456"}).json()["operator_token"]
    return j


class _Ariza:
    """auth DB'yi EN ALT katta bozar (tekil `AuthDB`'nin `db_path`'i tmp'deki kopyaya); blok çıkışında geri alır."""

    def __init__(self, monkeypatch, tmp_path, kip):
        self.mp, self.tmp, self.kip, self.kc = monkeypatch, tmp_path, kip, None
        self.kilitli: list = []  # `acl` kipinde ürün kilidi uygulanan kopyalar — çıkışta izin GERİ alınır

    def _acl_geri_al(self):
        """O-B2B2.4: kilitli kopyaların iznini sıfırla (miras geri gelir) — tmp'de okunamayan/silinemeyen artık kalmasın."""
        while self.kilitli:
            g = self.kilitli.pop()
            subprocess.run(["icacls", str(g), "/reset", "/Q"], capture_output=True)

    def _kopya(self, adb, ad):
        d = self.tmp / ad
        d.mkdir()
        for sfx in ("", "-wal", "-shm"):
            f = __import__("pathlib").Path(str(adb.db_path) + sfx)
            if f.exists():
                shutil.copy2(f, d / f.name)
        return d / "auth_users.db"

    def __enter__(self):
        from database.auth_db import get_auth_db

        self.ctx = self.mp.context()
        m = self.ctx.__enter__()
        adb = get_auth_db()
        if self.kip == "yol_yok":
            m.setattr(adb, "db_path", self.tmp / "yok_dizin" / "auth_users.db")
        elif self.kip == "bozuk_dosya":
            f = self.tmp / "bozuk_auth_users.db"
            f.write_bytes(b"BU BIR SQLITE DOSYASI DEGIL " * 400)
            m.setattr(adb, "db_path", f)
        elif self.kip == "kilit":
            f = self._kopya(adb, "kilitli")
            m.setattr(adb, "db_path", f)
            self.kc = sqlite3.connect(str(f), isolation_level=None, timeout=1)
            self.kc.execute("PRAGMA locking_mode=EXCLUSIVE")
            self.kc.execute("BEGIN EXCLUSIVE")
            self.kc.execute("UPDATE device_operators SET last_active = last_active")
        else:  # acl
            if sys.platform != "win32":
                pytest.skip("Windows ACL kipi")
            from utils.file_acl import lock_down_file

            f = self._kopya(adb, "acl")
            try:
                for sfx in ("", "-wal", "-shm"):
                    g = __import__("pathlib").Path(str(f) + sfx)
                    if g.exists():
                        self.kilitli.append(g)
                        assert lock_down_file(g, keep_current_user=False), f"aparat: ACL uygulanamadı ({g.name})"
                m.setattr(adb, "db_path", f)
                with pytest.raises(PermissionError):  # aparat kanıtı: süreç gerçekten okuyamıyor
                    open(f, "rb").close()
            except BaseException:
                # `__enter__` düşerse `with` `__exit__`'i çağırmaz → kilit ve yama burada geri alınır.
                self._acl_geri_al()
                self.ctx.__exit__(None, None, None)
                raise
        return m

    def __exit__(self, *a):
        if self.kc is not None:
            self.kc.execute("ROLLBACK")
            self.kc.close()
        self._acl_geri_al()
        self.ctx.__exit__(*a)
        return False


def _ariza_iletisi_mi(metin: str) -> bool:
    return metin.startswith(ARIZA_BASI) and CARE in metin and "Operatör seçin" not in metin


def _detay(r) -> str:
    try:
        return r.json().get("detail") or ""
    except Exception:
        return r.text


@pytest.mark.parametrize("kip", ARIZA_KIPLERI)
def test_KRITIK_kimlik_DB_okunamazken_428_ve_503_ARIZA_ve_CAREYI_soyler(o, monkeypatch, kip):
    _iki_hekim_jetonlar(o)
    aid = o.db.add_ai_analysis(module_id="m", patient_name="P", result_summary="ozet")
    pid = o.hdb.add_patient({"name": "Boncuk", "species": "Kedi", "operator_email": MEHMET})
    for _ in range(2):
        o.db.add_ai_analysis(module_id="m", patient_name="Q", result_summary="x", operator_email=AYSE)
    with _Ariza(monkeypatch, o.tmp, kip):
        r_deg = o.lan.post("/api/ai/log/review", json={"analysis_id": aid, "status": "approved", "reviewed_by": AYSE})
        r_sil = o.lan.delete(f"/api/patients/{pid}")
        r_ai = o.yerel.post("/api/ai/log/delete_all", json={"confirm": "DELETE_ALL", "operator_email": AYSE})
        r_op = o.yerel.get("/api/operators")
    with o.hdb._get_connection() as c:
        hasta = c.execute("SELECT COUNT(*) FROM patients WHERE id=?", (pid,)).fetchone()[0]
    kayit = next(a for a in o.db.get_ai_analyses(limit=50) if a["id"] == aid)
    with o.db._get_connection() as c:
        ai_kalan = c.execute("SELECT COUNT(*) FROM ai_analyses WHERE operator_email=?", (AYSE,)).fetchone()[0]
    # kapılar KAPALI kalır (B2-1.1)
    assert (r_deg.status_code, kayit.get("review_status") or "") == (428, ""), (r_deg.status_code, kayit)
    assert (r_sil.status_code, hasta) == (428, 1), (r_sil.status_code, _detay(r_sil))
    assert (r_ai.status_code, ai_kalan) == (428, 2), (r_ai.status_code, _detay(r_ai))
    assert r_op.status_code == 503, r_op.text[:200]
    # ileti arızayı ve çareyi söyler, "Operatör seçin" DEMEZ (Y113)
    for ad, r in (
        ("değerlendirme", r_deg),
        ("hasta silme", r_sil),
        ("AI geçmişi silme", r_ai),
        ("/api/operators", r_op),
    ):
        assert _ariza_iletisi_mi(_detay(r)), (
            f"{ad} iletisi arızayı/çareyi söylemiyor ya da 'Operatör seçin' diyor: {_detay(r)!r}"
        )


@pytest.mark.parametrize("kip", ARIZA_KIPLERI)
def test_KRITIK_kimlik_DB_okunamazken_GUNLUK_ariza_care_ve_dosyayi_soyler(o, monkeypatch, caplog, kip):
    _iki_hekim_jetonlar(o)
    aid = o.db.add_ai_analysis(module_id="m", patient_name="P", result_summary="ozet")
    with _Ariza(monkeypatch, o.tmp, kip):
        with caplog.at_level(logging.ERROR, logger="servers.auth"):
            caplog.clear()
            r = o.lan.post("/api/ai/log/review", json={"analysis_id": aid, "status": "approved", "reviewed_by": ""})
    assert r.status_code == 428
    satirlar = [k.getMessage() for k in caplog.records if k.name == "servers.auth" and k.levelno >= logging.ERROR]
    assert any(s.startswith(ARIZA_BASI) and CARE in s and "auth_users.db" in s for s in satirlar), (
        f"günlük arızayı / çareyi / dosyayı söylemiyor: {satirlar}"
    )


@pytest.mark.parametrize("kip", ARIZA_KIPLERI)
def test_KARSIT_kimlik_DB_okunamazken_ACIL_DURDUR_ve_STOP_kapilanmaz_JETON_sahibi_calisir(o, monkeypatch, kip):
    """Ö.4-Y8: arıza sürerken ACİL DURDUR ve STOP 200; arıza ÖNCESİ alınmış jeton yine sahibine yazar (B2-1.1 karşıtı)."""
    j = _iki_hekim_jetonlar(o)
    aid = o.db.add_ai_analysis(module_id="m", patient_name="P", result_summary="ozet")
    with _Ariza(monkeypatch, o.tmp, kip):
        r = o.lan.post(
            "/api/session/start",
            json={"coil_ids": [1], "frequency": 100, "duty": 40, "phase": 0, "duration_minutes": 5, "mode": "Manuel"},
        )
        assert r.status_code == 200, r.text[:200]
        assert o.lan.post("/api/session/stop", json={}).status_code == 200
        assert o.lan.post("/api/hardware/emergency_stop").status_code == 200
        rj = o.lan.post(
            "/api/ai/log/review",
            json={"analysis_id": aid, "status": "approved", "reviewed_by": ""},
            headers={"X-PEMF-Operator": j[MEHMET]},
        )
    assert rj.status_code == 200, rj.text[:200]
    assert next(a for a in o.db.get_ai_analyses(limit=50) if a["id"] == aid).get("reviewed_by") == MEHMET


def test_KARSIT_SAGLAM_DB_kayitli_cihazda_kimliksiz_ileti_OPERATOR_SECIN_kalir(o):
    """Arıza YOKKEN ileti değişmez: kayıtlı operatörlü cihazda kimliksiz istek "Operatör seçin" der (eylem: operatör seç)."""
    _iki_hekim_jetonlar(o)
    aid = o.db.add_ai_analysis(module_id="m", patient_name="P", result_summary="ozet")
    pid = o.hdb.add_patient({"name": "Boncuk", "species": "Kedi", "operator_email": MEHMET})
    r_deg = o.lan.post("/api/ai/log/review", json={"analysis_id": aid, "status": "approved", "reviewed_by": ""})
    r_sil = o.lan.delete(f"/api/patients/{pid}")
    for r in (r_deg, r_sil):
        assert r.status_code == 428 and _detay(r).startswith("Operatör seçin"), (r.status_code, _detay(r))
        assert ARIZA_BASI not in _detay(r)
    assert o.yerel.get("/api/operators").status_code == 200


def test_KARSIT_KURAL2_saglam_DB_operatorsuz_klinik_kilitlenmez(o):
    aid = o.db.add_ai_analysis(module_id="m", patient_name="P", result_summary="ozet")
    r = o.lan.post("/api/ai/log/review", json={"analysis_id": aid, "status": "approved", "reviewed_by": TEK})
    assert r.status_code == 200, r.text[:200]
    pid = o.hdb.add_patient({"name": "Tekir", "species": "Kedi", "operator_email": TEK})
    assert o.lan.delete(f"/api/patients/{pid}").status_code == 200
