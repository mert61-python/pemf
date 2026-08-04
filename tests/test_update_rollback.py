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
    r"""DENETIM P1 regresyonu: installer PAYLAŞIMLI temp'e SABİT adla indirilmemeli.

    Hata: `Path(tempfile.gettempdir()) / f"PEMF_Update_{sürüm}.exe"`. Backend LocalSystem olduğu
    için bu C:\Windows\Temp'tir; yetkisiz yerel bir hesap dosyayı ÖNCEDEN oluşturup sahipliğini
    koruyabilir ve SHA256+Authenticode doğrulaması GEÇTİKTEN SONRA içeriği değiştirerek
    LocalSystem'e keyfi EXE çalıştırtabilirdi (doğrulama→çalıştırma penceresi).
    """
    import shutil
    import tempfile
    from pathlib import Path

    from servers import update_manager as um

    # NOT: _private_temp_path GERÇEK bir mkdtemp dizini yaratır. Bu test onu temizlemiyordu →
    # her koşuda %TEMP%'e 2 yetim `pemf_upd_*` dizini bırakıyordu (mutasyon testi takımı
    # onlarca kez koşturunca 228 dizin birikti). Testin kendi çöpünü toplaması şart.
    olusan = []
    try:
        p1 = um._private_temp_path("PEMF_Update_1.2.3.exe")
        p2 = um._private_temp_path("PEMF_Update_1.2.3.exe")
        olusan += [p1.parent, p2.parent]

        assert p1 != p2, "yol tahmin edilebilir/sabit olmamalı"
        assert p1.name == "PEMF_Update_1.2.3.exe"
        # Dosya adı aynı olsa da dizin süreç-özel ve paylaşımlı temp KÖKÜ değil.
        assert p1.parent != Path(tempfile.gettempdir())
        assert p1.parent.is_dir(), "özel dizin oluşturulmuş olmalı"
        assert p1.parent.name.startswith("pemf_upd_")
    finally:
        for d in olusan:
            shutil.rmtree(d, ignore_errors=True)


# ─────────────────────────────────────────────────────────────────────────────
# Denetim 2026-08-04 (P2): sürüm KANALI karışıklığı.
# `check_for_update` sonucu exe kanalının latest.json'ıyla karşılaştırılır, ama kurulu sürüm
# `frontend_version.json`'dan (versions.json → frontendOta, 1.4.x) okunuyordu. İki AYRI yayın
# kanalı aynı isim uzayında kıyaslanınca yayındaki base.zip kendini "1.4.0" sanıyordu.
# ─────────────────────────────────────────────────────────────────────────────


def test_kurulu_surum_backend_kanalindan_okunur(um):
    """VERSION (exe/installer kanalı) frontend_version.json'dan ÖNCE gelmeli."""
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    beklenen = (root / "VERSION").read_text(encoding="utf-8").strip()
    assert um.get_current_version() == beklenen, (
        "kurulu sürüm VERSION (backend kanalı) yerine başka kanaldan okunuyor"
    )

    import json as _json

    frontend_ota = str(_json.loads((root / "frontend_version.json").read_text(encoding="utf-8"))["version"])
    if frontend_ota != beklenen:  # iki kanal ayrıştığında karışıklık görünür olur
        assert um.get_current_version() != frontend_ota, (
            "kurulu sürüm frontendOta kanalından okunuyor — exe latest.json ile kıyaslanamaz"
        )


def test_version_paths_sirasi_once_VERSION(um):
    adlar = [p.name for p in um._version_paths()]
    assert adlar.index("VERSION") < adlar.index("frontend_version.json"), (
        "VERSION, frontend_version.json'dan ÖNCE aranmalı"
    )


def test_version_dosyasi_hem_duz_metin_hem_json_okunur(um, tmp_path):
    """VERSION düz metin, frontend_version.json ise {'version': ...} taşır."""
    duz = tmp_path / "VERSION"
    duz.write_text("1.9.5\n", encoding="utf-8")
    assert um._read_version_file(duz) == "1.9.5"

    js = tmp_path / "frontend_version.json"
    js.write_text('{"version": "1.4.1"}', encoding="utf-8")
    assert um._read_version_file(js) == "1.4.1"

    bos = tmp_path / "VERSION_bos"
    bos.write_text("   \n", encoding="utf-8")
    assert um._read_version_file(bos) == ""


# ─────────────────────────────────────────────────────────────────────────────
# DENETİM 2026-08-04 (P0) — REPO-YOLU PİNİ NOKTA-SEGMENTİYLE ATLATILIYORDU
# `urlparse` nokta-segmentlerini SADELEŞTİRMEZ ama HTTP sunucusu RFC 3986 gereği çözer.
# Bu yüzden `p.path.startswith("/mert61-python/pemf-update/")` HAM metinde geçerken GitHub
# `/saldirgan/kotu/setup.exe` sunuyordu → zehirli manifest kendi deposundaki imzasız EXE'yi
# indirtebiliyordu (sha da aynı manifest'ten geldiği için doğrulama geçer).
# Rust ikizi: launcher/core/src/net.rs::nokta_segmentli_url_pini_atlatamaz
# ─────────────────────────────────────────────────────────────────────────────

import pytest


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/mert61-python/pemf-update/../../saldirgan/kotu/setup.exe",
        "https://github.com/mert61-python/pemf-update/%2e%2e/%2e%2e/saldirgan/setup.exe",
        "https://github.com/mert61-python/pemf-update/%2E%2E/saldirgan/setup.exe",
        "https://github.com/mert61-python/pemf-update/./../saldirgan/setup.exe",
        "https://github.com/mert61-python/pemf-update//../saldirgan/setup.exe",
        "https://github.com/mert61-python/pemf-update/..%2fsaldirgan/setup.exe",
    ],
)
def test_nokta_segmentli_url_repo_pinini_atlatamaz(url):
    from servers.update_manager import _validate_installer_url

    ok, msg = _validate_installer_url(url)
    assert not ok, f"PIN ATLATILDI — indirme saldirganin deposuna gider: {url}"


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/mert61-python/pemf-update/releases/download/exe-v1.9.5/PEMF_Setup.exe",
        "https://objects.githubusercontent.com/github-production-release-asset/1/2?x=y",
    ],
)
def test_mesru_guncelleme_urlleri_hala_kabul_ediliyor(url):
    from servers.update_manager import _validate_installer_url

    ok, msg = _validate_installer_url(url)
    assert ok, f"mesru URL reddedildi ({msg}): {url}"


def test_rust_ve_python_pin_ikizleri_ayni_yazimlari_reddediyor():
    """İki taraf ayrışırsa biri zayıf kalır — Rust tarafında da AYNI yardımcı olmalı."""
    from pathlib import Path

    rs = Path(__file__).resolve().parent.parent / "launcher" / "core" / "src" / "net.rs"
    if not rs.exists():
        pytest.skip("launcher kaynagi yok")
    src = rs.read_text(encoding="utf-8", errors="replace")
    assert "fn path_has_traversal" in src, (
        "Rust tarafinda path_has_traversal YOK — pin atlatma orada hala acik olabilir."
    )
    for tok in ("%2e", "%2f", "%5c"):
        assert tok in src, f"Rust ikizi {tok} yazimini kontrol etmiyor"


# ─────────────────────────────────────────────────────────────────────────────
# DENETİM 2026-08-04 (P2) — GÜNCELLEME GUARD'I KALICI AÇIK KALIYORDU
# `_applying`, installer başlatıldıktan sonra BİLEREK açık bırakılır (tehlikeli pencere orada
# başlar: installer servisi durdurup EXE'yi değiştirecek). Ama hiçbir yerde KAPANMIYORDU:
# installer kurulumu tamamlamazsa (Inno "another instance is running", AV bloğu, iptal) backend
# KALICI olarak "güncelleme sürüyor" durumunda kilitlenir ve is_update_in_progress() üzerinden
# /session/start + /ai/pro/start SONSUZA KADAR reddedilir — cihaz hiç tedavi başlatamaz.
# BAŞARILI kurulum backend'i zaten yeniden başlatır (bayrak doğal sıfırlanır); süresi dolan
# yalnızca BAŞARISIZ kurulumun bıraktığı bayat bayraktır.
# ─────────────────────────────────────────────────────────────────────────────


def _guard_ayarla(active: bool, yas_sn: float | None):
    import time as _t

    from servers import update_manager as um

    um._applying = active
    um._applying_since = None if yas_sn is None else (_t.monotonic() - yas_sn)
    return um


def test_taze_guncelleme_guardi_seans_acmayi_engeller():
    um = _guard_ayarla(True, 5.0)
    try:
        assert um.is_update_in_progress() is True, (
            "taze guard kapandi — installer EXE'yi degistirirken tedavi baslatilabilir"
        )
    finally:
        _guard_ayarla(False, None)


def test_bayat_guncelleme_guardi_SURESI_DOLAR():
    um = _guard_ayarla(True, 1_000_000.0)  # grace'in çok ötesi
    try:
        assert um.is_update_in_progress() is False, (
            "bayat guard temizlenmedi — cihaz KALICI olarak seans acamaz halde kalir"
        )
        assert um._applying is False and um._applying_since is None, "durum sifirlanmadi"
    finally:
        _guard_ayarla(False, None)


def test_zaman_damgasi_yoksa_eski_davranis_korunur():
    """Damgasız (eski akıştan kalan) bayrak sessizce temizlenmemeli — geriye uyum."""
    um = _guard_ayarla(True, None)
    try:
        assert um.is_update_in_progress() is True
    finally:
        _guard_ayarla(False, None)
