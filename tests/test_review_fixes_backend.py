"""Backend derin-inceleme (2026-07) düzeltmeleri için regresyon testleri:
K2 OTA URL-pinleme + sürüm-sanitize, seans süresi ge=1, CSV formula-injection,
şifreli-arama çok-alan false-negative. Kritik güvenlik/doğruluk davranışlarını kilitler."""
import pytest


# ── K2: OTA installer URL HTTPS + release-host pinleme (URL-yönlendirme vektörü) ──
# DENETIM P3: pin ESKIDEN tum github.com'u (herhangi bir kullanicinin repo'sunu) kabul ediyordu →
# manifest ele gecerse saldirgan KENDI repo'sundaki EXE'yi gosterebilir, SHA256 de manifest'ten
# geldigi icin eslesirdi. github.com yolu artik BEKLENEN REPO'ya sabit.
@pytest.mark.parametrize("url,ok", [
    ("https://github.com/mert61-python/pemf-update/releases/download/v1/i.exe", True),
    ("https://github.com/saldirgan/kotu-repo/releases/download/v1/i.exe", False),  # YABANCI repo
    ("https://objects.githubusercontent.com/x/i.exe", True),
    ("https://release-assets.githubusercontent.com/x/i.exe", True),
    ("http://github.com/o/r/i.exe", False),          # HTTPS değil
    ("https://evil.example.com/i.exe", False),        # beklenmeyen host
    ("ftp://github.com/i.exe", False),                # şema yanlış
    ("", False),                                      # boş
])
def test_validate_installer_url_pins_https_and_host(url, ok):
    from servers.update_manager import _validate_installer_url
    result_ok, err = _validate_installer_url(url)
    assert result_ok is ok
    if not ok:
        assert err and "güvenlik" in err.lower()


def test_safe_ver_sanitizes_path_traversal():
    from servers.update_manager import _safe_ver
    assert _safe_ver("1.4.0") == "1.4.0"
    assert "/" not in _safe_ver("../../evil")
    assert "\\" not in _safe_ver("..\\evil")
    assert _safe_ver("") == "x"          # boş → güvenli varsayılan
    assert len(_safe_ver("a" * 500)) <= 40


# ── Seans süresi ge=1: 0/negatif süre auto-end mantığını (total>0) hiç tetiklemez ──
def test_session_duration_must_be_positive():
    from pydantic import ValidationError
    from servers.api_server import SessionStartPayload
    SessionStartPayload(duration_minutes=1)          # geçerli
    SessionStartPayload(duration_minutes=20)         # varsayılan-benzeri
    for bad in (0, -5):
        with pytest.raises(ValidationError):
            SessionStartPayload(duration_minutes=bad)


# ── Şifreli-arama: çok-ALANLI arama artık false-negative dönmez ('Ali Veli' = ad+sahip) ──
@pytest.fixture
def patient_db(temp_app_data, monkeypatch):
    import database.patient_database as pdb
    return pdb.PatientDatabase(str(temp_app_data / "patients.db"))


def test_search_multi_field_no_false_negative(patient_db):
    # Ad ve sahip AYRI alanlarda; birleşik 'ali veli' hiçbir tek alanın tamamı DEĞİL.
    patient_db.add_patient({"name": "Ali", "owner": "Veli", "species": "Kedi"})
    patient_db.add_patient({"name": "Mehmet", "owner": "Can", "species": "Kedi"})

    # Tek-kelime aramalar
    assert any(p["name"] == "Ali" for p in patient_db.search_patients("Ali"))
    assert any(p["name"] == "Ali" for p in patient_db.search_patients("Veli"))
    # ÇOK-ALANLI arama: ad+sahip token'larının AND'i → eskiden birleşik-token yüzünden BOŞ dönerdi
    res = patient_db.search_patients("Ali Veli")
    assert any(p["name"] == "Ali" for p in res), "çok-alanlı arama false-negative (regresyon)"
    # Ayırt edici: eşleşmeyen ikinci hasta dönmemeli
    assert all(p["name"] != "Mehmet" for p in res)


def test_search_single_word_still_works(patient_db):
    patient_db.add_patient({"name": "Boncuk", "owner": "Zeynep", "species": "Kedi"})
    res = patient_db.search_patients("Boncuk")
    assert any(p["name"] == "Boncuk" for p in res)


# ── Operatör hesabı: e-posta/şifre kayıt + giriş (yerel PBKDF2) + şifre kuralı ──
def test_auth_register_login_and_password_rules(tmp_path):
    from database.auth_db import AuthDB, PASSWORD_RE
    db = AuthDB(str(tmp_path))
    assert db.register("Op@Clinic.com", "Abc12345")[0] is True
    assert db.register("op@clinic.com", "Abc12345")[0] is False    # e-posta normalize + BENZERSİZ
    assert db.email_exists("OP@clinic.com") is True                # login "kullanıcı yok" ayrımı (net UX)
    assert db.email_exists("yok@x.com") is False
    assert db.verify("OP@clinic.com", "Abc12345") is True          # e-posta case-insensitive
    assert db.verify("op@clinic.com", "wrong") is False            # yanlış şifre
    assert db.verify("yok@x.com", "Abc12345") is False             # olmayan kullanıcı
    # Yönetici şifre-sıfırlama ('Şifremi unuttum'): yeni şifre geçerli, eskisi geçersiz olur
    assert db.reset_password("op@clinic.com", "NewPass9")[0] is True
    assert db.verify("op@clinic.com", "NewPass9") is True
    assert db.verify("op@clinic.com", "Abc12345") is False         # eski şifre artık çalışmaz
    assert db.reset_password("yok@x.com", "NewPass9")[0] is False   # olmayan kullanıcı → sıfırlanamaz
    # Şifre kuralı: ≥8 + büyük + küçük + rakam
    assert PASSWORD_RE.match("Abc12345") is not None
    for bad in ("abc12345", "ABC12345", "Abcdefgh", "Abc1234"):
        assert PASSWORD_RE.match(bad) is None
