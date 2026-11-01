"""KP (Y236 · kapsam) — `services/credential_manager.py` DAVRANIŞ sözleşmesi (modül hiçbir testte koşmuyordu: %0).

ESP / MQTT kimlik aracıdır (`python -m services.credential_manager …`; ESP kodu SİLİNMEZ — sahip kararı). Testler GERÇEK kasaya,
veri köküne ya da ağa dokunmaz: kimlik dizini `tmp_path`, SecretsManager okuması en alt katta sahte (`utils.secrets_manager.get_secret`),
ACL kilidi kaydedici. İddialar kapsam için değil sözleşme için: şifre deterministik ve bağlama özgü, roller yalnız kendi konularını
görür, düz-metin dosyaların HEPSİ kilitlenir, `generate` şifreyi STDOUT'a yazmaz (Audit P3), `PEMF_REQUIRE_MASTER_SECRET=1` fail-fast.
"""

import importlib.util
import json
import platform
import runpy
import sys
from pathlib import Path

import pytest
from services import credential_manager as cm

_KAYNAK = Path(cm.__file__)


@pytest.fixture
def ortam(monkeypatch, tmp_path):
    kilitli: list = []
    kok = tmp_path / "config" / "credentials"
    monkeypatch.setattr(cm, "CREDENTIALS_DIR", kok)
    monkeypatch.setattr(cm, "lock_down_file", lambda p: kilitli.append(Path(p)) or True)
    import utils.secrets_manager as sm

    monkeypatch.setattr(sm, "get_secret", lambda *a, **k: None)
    monkeypatch.delenv("PEMF_MASTER_SECRET", raising=False)
    monkeypatch.delenv("PEMF_REQUIRE_MASTER_SECRET", raising=False)
    return kok, kilitli


def test_KRITIK_sifre_DETERMINISTIK_baglama_ve_master_sirra_OZGU(ortam):
    a = cm.CredentialManager(master_secret="s" * 40)
    b = cm.CredentialManager(master_secret="s" * 40)
    c = cm.CredentialManager(master_secret="t" * 40)
    assert a._derive_password("esp:6") == b._derive_password("esp:6"), (
        "aynı sır + bağlam → aynı şifre değil (yeniden flash kırılır)"
    )
    assert a._derive_password("esp:6") != a._derive_password("esp:7"), "bobinler aynı şifreyi paylaşıyor"
    assert a._derive_password("esp:6") != c._derive_password("esp:6"), "master sır şifreye girmiyor"
    sifre = a._derive_password("esp:6")
    assert len(sifre) == 32 and len(a._derive_password("x", length=12)) == 12
    izinli = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*")
    assert set(sifre) <= izinli


def test_KRITIK_roller_YALNIZ_kendi_konularini_gorur(ortam):
    m = cm.CredentialManager(master_secret="s" * 40)
    esp = m.get_or_create_esp_credential(6)
    assert (esp.role, esp.username, esp.coil_id) == ("esp_coil", "esp_coil_6", 6)
    assert all(t.startswith("pemf/coil/6/") for t in esp.allowed_publish), esp.allowed_publish
    assert esp.allowed_subscribe == ["pemf/coil/6/control", "pemf/coil/all/control"]
    ky = m.get_or_create_bridge_credential()
    assert (ky.role, ky.allowed_publish, ky.allowed_subscribe, ky.coil_id) == (
        "gui_bridge",
        ["pemf/#"],
        ["pemf/#"],
        None,
    )
    an = m.get_or_create_android_credential()
    assert an.username == "android_prod" and an.role == "android_app"
    assert "pemf/#" not in an.allowed_publish and all(t.endswith("/control") for t in an.allowed_publish), (
        "android yönetim konusuna yazabiliyor"
    )
    assert m.get_or_create_android_credential("tablet1").username == "android_tablet1"


def test_kayit_DISKE_yazilir_KILITLENIR_ve_yeniden_acilista_AYNI_nesne_doner(ortam):
    kok, kilitli = ortam
    m = cm.CredentialManager(master_secret="s" * 40)
    ilk = m.get_or_create_esp_credential(7)
    dosya = kok / "credentials.json"
    assert dosya in kilitli, "düz-metin kimlik dosyası ACL ile kilitlenmedi (Audit P1)"
    veri = json.loads(dosya.read_text(encoding="utf-8"))
    assert veri["esp_coil_7"]["password"] == ilk.password
    m2 = cm.CredentialManager(master_secret="BASKA-SIR-" * 4)  # diskteki kayıt ESAS (türetim yeniden yapılmaz)
    assert m2.get_or_create_esp_credential(7) == ilk
    assert m2.get_credential("esp_coil_7") == ilk and m2.get_credential("yok") is None
    assert m2.get_or_create_esp_credential(7) is m2.get_or_create_esp_credential(7)
    m2.get_or_create_bridge_credential()
    assert m2.get_or_create_bridge_credential() is m2.get_or_create_bridge_credential()
    m2.get_or_create_android_credential("x")
    assert m2.get_or_create_android_credential("x") is m2.get_or_create_android_credential("x")
    assert {c.username for c in m2.list_credentials()} == {"esp_coil_7", "gui_bridge", "android_x"}


def test_bozuk_kayit_dosyasi_ACILISI_durdurmaz_bos_baslar(ortam, caplog):
    kok, _ = ortam
    kok.mkdir(parents=True)
    (kok / "credentials.json").write_text("{bozuk", encoding="utf-8")
    m = cm.CredentialManager(master_secret="s" * 40)
    assert m.list_credentials() == []
    assert any("Credential yükleme hatası" in r.getMessage() for r in caplog.records)


def test_kayit_YAZILAMAZSA_istisna_firlamaz_hata_gunluklenir(ortam, caplog):
    kok, _ = ortam
    (kok / "credentials.json").mkdir(parents=True)  # dosya yerine DİZİN → yazma düşer
    m = cm.CredentialManager(master_secret="s" * 40)
    m.get_or_create_bridge_credential()
    assert any("Credential kaydetme hatası" in r.getMessage() for r in caplog.records)


def test_KRITIK_tum_disa_aktarimlar_dogru_icerik_ve_HEPSI_kilitli(ortam, tmp_path):
    kok, kilitli = ortam
    m = cm.CredentialManager(master_secret="s" * 40)
    esp = m.get_or_create_esp_credential(6)
    ky = m.get_or_create_bridge_credential()
    sifreler = Path(m.export_mosquitto_password_file())
    assert sifreler == kok / "mosquitto_passwords.txt"
    assert sifreler.read_text(encoding="utf-8").splitlines() == [
        f"esp_coil_6:{esp.password}",
        f"gui_bridge:{ky.password}",
    ]
    acl = Path(m.export_acl_file()).read_text(encoding="utf-8").splitlines()
    assert (
        "user esp_coil_6" in acl and "topic write pemf/coil/6/status" in acl and "topic read pemf/coil/6/control" in acl
    )
    assert "topic write pemf/#" in acl and acl[0].startswith("#")
    hm = json.loads(Path(m.export_hivemq_config()).read_text(encoding="utf-8"))["users"]
    assert [u["username"] for u in hm] == ["esp_coil_6", "gui_bridge"] and hm[0][
        "publish_topics"
    ] == esp.allowed_publish
    h = Path(m.export_esp_secrets(6)).read_text(encoding="utf-8")
    # başlık satırı ayrıştırılır (gitleaks `pemf-firmware-secrets-h-gercek-deger` kalıbı test kaynağında yanlış pozitif vermesin)
    sifre_satiri = next(s for s in h.splitlines() if "DEFAULT_CLOUD_MQTT_PASS" in s)
    assert "#define FACTORY_COIL_ID 6" in h
    assert sifre_satiri.split("=", 1)[1].strip().rstrip(";").strip('"') == esp.password, (
        "ESP başlığına bobinin şifresi yazılmadı"
    )
    hedef = tmp_path / "ozel.txt"
    assert m.export_mosquitto_password_file(str(hedef)) == str(hedef)
    for ad in ("mosquitto_passwords.txt", "mosquitto_acl.conf", "hivemq_users.json", "secrets_coil_6.h"):
        assert kok / ad in kilitli, f"{ad} düz-metin şifre taşıyor ama kilitlenmedi"
    assert hedef in kilitli


def test_master_sir_ONCELIGI_arguman_ortam_kasa_dosya(ortam, monkeypatch):
    import utils.secrets_manager as sm

    monkeypatch.setenv("PEMF_MASTER_SECRET", "O" * 40)
    monkeypatch.setattr(sm, "get_secret", lambda *a, **k: "K" * 40)
    assert cm.CredentialManager(master_secret="A" * 40)._master_secret == "A" * 40
    assert cm.CredentialManager()._master_secret == "O" * 40
    monkeypatch.delenv("PEMF_MASTER_SECRET")
    assert cm.CredentialManager()._master_secret == "K" * 40
    monkeypatch.setattr(sm, "get_secret", lambda *a, **k: (_ for _ in ()).throw(OSError("kasa yok")))
    m = cm.CredentialManager()  # kasa istisnası açılışı durdurmaz → dosya sırrına düşer
    assert len(m._master_secret) == 64


def test_KRITIK_REQUIRE_MASTER_SECRET_1_ise_FAIL_FAST(ortam, monkeypatch):
    monkeypatch.setenv("PEMF_REQUIRE_MASTER_SECRET", "1")
    with pytest.raises(RuntimeError, match="fail-fast"):
        cm.CredentialManager()


def test_sirsiz_ilk_acilis_GUCLU_sir_uretir_KILITLER_sonra_AYNISINI_okur(ortam, caplog):
    kok, kilitli = ortam
    m1 = cm.CredentialManager()
    dosya = kok.parent / "pemf_secret.key"
    assert dosya.read_text(encoding="utf-8") == m1._master_secret and len(m1._master_secret) == 64
    assert dosya in kilitli, "master KDF sırrı kilitlenmedi → tüm cihaz şifreleri türetilebilir (Audit P1)"
    assert any("PEMF_MASTER_SECRET ortam değişkeni ayarlanmamış" in r.getMessage() for r in caplog.records)
    assert cm.CredentialManager()._master_secret == m1._master_secret
    dosya.write_text("kisa", encoding="utf-8")  # < 32 karakter → güvenilmez, yeniden üretilir
    m3 = cm.CredentialManager()
    assert m3._master_secret != "kisa" and len(m3._master_secret) == 64


def test_sir_dosyasi_OKUNAMAZ_ve_YAZILAMAZSA_oturumluk_sir_ile_calisir(ortam, caplog):
    kok, _ = ortam
    (kok.parent / "pemf_secret.key").mkdir(parents=True)  # dosya yerine DİZİN: okuma da yazma da düşer
    m = cm.CredentialManager()
    assert len(m._master_secret) == 64
    mesajlar = " ".join(r.getMessage() for r in caplog.records)
    assert "Secret dosyası okunamadı" in mesajlar and "oturum için geçici secret" in mesajlar


def _cli(monkeypatch, capsys, *arg):
    monkeypatch.setattr(sys, "argv", ["credential_manager", *arg])
    cm.main()
    return capsys.readouterr().out


def test_KRITIK_CLI_generate_SIFREYI_STDOUTa_YAZMAZ(ortam, monkeypatch, capsys):
    monkeypatch.setenv("PEMF_MASTER_SECRET", "s" * 40)
    cikti = _cli(monkeypatch, capsys, "generate", "--all-coils", "6", "7")
    cikti += _cli(monkeypatch, capsys, "generate", "--coil-id", "8", "--android-uid", "tab")
    m = cm.CredentialManager()
    for c in m.list_credentials():
        assert c.password not in cikti, f"{c.username} şifresi STDOUT'a yazıldı (Audit P3)"
    assert "user=esp_coil_6" in cikti and "user=esp_coil_8" in cikti and "user=android_tab" in cikti


def test_CLI_list_export_provision_ve_yardim(ortam, monkeypatch, capsys):
    kok, _ = ortam
    monkeypatch.setenv("PEMF_MASTER_SECRET", "s" * 40)
    pr = _cli(monkeypatch, capsys, "provision", "--coil-ids", "6", "7")
    assert "Coil 6: esp_coil_6" in pr and str(kok) in pr
    for ad in ("mosquitto_passwords.txt", "mosquitto_acl.conf", "hivemq_users.json"):
        assert (kok / ad).is_file()
    ls = _cli(monkeypatch, capsys, "list")
    assert "esp_coil_7" in ls and "gui_bridge" in ls
    ex = _cli(monkeypatch, capsys, "export", "--mosquitto-pass", "--mosquitto-acl", "--hivemq", "--esp-secrets", "6")
    assert ex.count("[OK]") == 4 and (kok / "secrets_coil_6.h").is_file()
    assert "usage" in _cli(monkeypatch, capsys).lower()


def test_modul_kendi_basina_calistirilinca_main_kosar(monkeypatch, tmp_path, capsys):
    """`python -m services.credential_manager` (yardım metni) — veri kökü `tmp_path` (APPDATA), gerçek köke DOKUNULMAZ."""
    import utils.secrets_manager as sm

    monkeypatch.delenv("PEMF_DATA_DIR", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("PEMF_MASTER_SECRET", "s" * 40)
    monkeypatch.setattr(sm, "get_secret", lambda *a, **k: None)
    monkeypatch.setattr(sys, "argv", ["credential_manager"])
    runpy.run_path(str(_KAYNAK), run_name="__main__")
    assert "usage" in capsys.readouterr().out.lower()
    assert list((tmp_path / "appdata").rglob("credentials")), "kimlik dizini geçici köke açılmadı"


@pytest.mark.parametrize("sistem", ["Windows", "Linux"])
def test_yardimcilar_YOKSA_modul_yine_yuklenir_ve_kilit_sessizce_atlanir(monkeypatch, tmp_path, sistem):
    """`utils.file_acl` / `utils.path_utils` içe aktarılamazsa (eksik paket): kilit no-op, veri kökü platform varsayılanı."""
    monkeypatch.setitem(sys.modules, "utils.file_acl", None)
    monkeypatch.setitem(sys.modules, "utils.path_utils", None)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("HOME", str(tmp_path / "ev"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "ev"))
    monkeypatch.setattr(platform, "system", lambda: sistem)
    spec = importlib.util.spec_from_file_location("kp_credential_manager_kopya", _KAYNAK)
    kopya = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(kopya)
    assert kopya.lock_down_file(tmp_path / "x") is False
    beklenen = tmp_path / ("appdata" if sistem == "Windows" else "ev/.local/share") / "PEMF_GUI"
    assert kopya.CREDENTIALS_DIR == beklenen / "config" / "credentials"
