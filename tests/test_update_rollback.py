"""Sürüm rollback güvenliği (audit B-9.2): önceki kararlı sürüme geri dönüş — previousStable
yoksa/aktif-tedavi varsa REDDEDİLİR (fail-closed); /api/update/rollback endpoint kayıtlı."""
import pytest


@pytest.fixture
def um(monkeypatch):
    import servers.update_manager as m
    m._status.clear()
    return m


def test_rollback_refused_without_previous_stable(um):
    um._status.update({"previousStable": None})
    r = um.rollback()
    assert r["ok"] is False
    assert "previousStable" in r["error"] or "önceki" in r["error"].lower()


def test_rollback_fail_closed_on_active_treatment(um, monkeypatch):
    um._status.update({"previousStable": {"version": "1.3.0", "installerUrl": "https://github.com/mert61-python/pemf-update/releases/download/v1.3.0/i.exe", "sha256": "ab" * 32}})
    monkeypatch.setattr(um, "_has_active_treatment", lambda: True)
    r = um.rollback()
    assert r["ok"] is False
    assert "tedavi" in r["error"].lower()  # aktif tedavi sürerken rollback yapılmaz


def test_rollback_refused_without_sha256(um, monkeypatch):
    # previousStable var ama SHA256 yok → doğrulanamayan installer çalıştırılmaz (güvenlik)
    um._status.update({"previousStable": {"version": "1.3.0", "installerUrl": "https://github.com/mert61-python/pemf-update/releases/download/v1.3.0/i.exe", "sha256": ""}})
    monkeypatch.setattr(um, "_has_active_treatment", lambda: False)
    r = um.rollback()
    assert r["ok"] is False
    assert "SHA256" in r["error"]


def test_status_exposes_previous_stable(um):
    um._status.update({"currentVersion": "1.4.0", "previousStable": {"version": "1.3.0"}})
    assert um.get_status()["previousStable"]["version"] == "1.3.0"


def test_rollback_endpoint_registered():
    from servers import api_server
    paths = [r.path for r in api_server.app.routes if hasattr(r, "path")]
    assert "/api/update/rollback" in paths


def test_installer_temp_path_is_private_and_unpredictable():
    """DENETIM P1 regresyonu: installer PAYLAŞIMLI temp'e SABİT adla indirilmemeli.

    Hata: `Path(tempfile.gettempdir()) / f"PEMF_Update_{sürüm}.exe"`. Backend LocalSystem olduğu
    için bu C:\Windows\Temp'tir; yetkisiz yerel bir hesap dosyayı ÖNCEDEN oluşturup sahipliğini
    koruyabilir ve SHA256+Authenticode doğrulaması GEÇTİKTEN SONRA içeriği değiştirerek
    LocalSystem'e keyfi EXE çalıştırtabilirdi (doğrulama→çalıştırma penceresi).
    """
    import tempfile
    from pathlib import Path

    from servers import update_manager as um

    p1 = um._private_temp_path("PEMF_Update_1.2.3.exe")
    p2 = um._private_temp_path("PEMF_Update_1.2.3.exe")

    assert p1 != p2, "yol tahmin edilebilir/sabit olmamalı"
    assert p1.name == "PEMF_Update_1.2.3.exe"
    # Dosya adı aynı olsa da dizin süreç-özel ve paylaşımlı temp KÖKÜ değil.
    assert p1.parent != Path(tempfile.gettempdir())
    assert p1.parent.is_dir(), "özel dizin oluşturulmuş olmalı"
    assert p1.parent.name.startswith("pemf_upd_")
