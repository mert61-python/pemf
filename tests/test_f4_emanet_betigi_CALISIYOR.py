# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D0Ö.20 (B-9.25) — hasta anahtarı emanet betiği GERÇEKTEN çalışıyor ve hataları YUTMUYOR.

Ortak import-çözüm kapısı: `test_betikler_ACILIYOR::test_KRITIK_fonksiyon_ici_ilk_taraf_importlari_COZULUYOR`.
Bu dosya DAVRANIŞI ölçer:

  · `hasta_anahtari_emanet.py --parmak-izi` ALT SÜREÇTE (conftest yolları yok) sahte veri kökü +
    sahte `pemf_secrets.json` ile rc=0 ve parmak izlerini basar (DEĞERLERİ basmaz). F4'ten beri
    `_sirlari_oku` → `from utils import secrets_manager` ölüydü.
  · `disa_aktar`: `utils.file_acl` yüklenemezse düz-metin emanet YAZILMAZ ve hata ne olduğunu söyler;
    ACL uygulanamazsa uyarı basılır. Eskiden ikisi de yazımdan SONRA `except: pass` ile yutuluyordu →
    emanet UYARISIZ ve ACL'SİZ diske düşüyordu (İG-9.16).
  · `_veri_koku_adaylari`: `utils.path_utils` yüklenemezse sessizce devam ETMEZ (PEMF_DATA_DIR kökü
    aday listesinden düşer, YANLIŞ kökün anahtarı okunabilir).

⚠️ Sahte sırlar `secrets.token_*` ile üretilir; gerçek sır dosyasına dokunulmaz (bkz. betik_alt_sureci).
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sys
from pathlib import Path

import pytest
from betik_alt_sureci import BETIKLER, betik_modulu, kostur, yalitik_ortam

#: Süreç-içi kollarda `_sirlari_oku` yerine dönen SAHTE çözülmüş değer (gerçek sır değil).
_ALAN, _SAHTE = "auto.sqlcipher_key", "sahte-d0o20"


def _parmak(deger: str) -> str:
    return hashlib.sha256(deger.encode("utf-8")).hexdigest()[:16]


def test_KRITIK_parmak_izi_ALT_SURECTE_sahte_kokle_CALISIR(tmp_path):
    env = yalitik_ortam(tmp_path / "ortam")
    veri = Path(env["PROGRAMDATA"]) / "PEMF_System" / "PEMF_GUI"
    veri.mkdir(parents=True)
    anahtar, fernet = secrets.token_hex(32), secrets.token_urlsafe(32)  # SAHTE — gerçek sır değil
    (veri / "pemf_secrets.json").write_text(
        json.dumps({"auto": {"sqlcipher_key": anahtar, "patient_fernet_key": fernet}}), encoding="utf-8"
    )
    r = kostur([str(BETIKLER / "hasta_anahtari_emanet.py"), "--parmak-izi"], tmp_path, env, 120)
    cikti = r.stdout + r.stderr
    assert r.returncode == 0, f"--parmak-izi ÖLÜ (rc={r.returncode}) — B-9.25:\n{cikti[-900:]}"
    assert str(veri) in r.stdout, f"sır dosyasının kökü seçilmedi:\n{r.stdout[-600:]}"
    for deger in (anahtar, fernet):
        assert f"parmak={_parmak(deger)}" in r.stdout, f"parmak izi basılmadı:\n{r.stdout[-600:]}"
        assert deger not in cikti, "anahtar DEĞERİ çıktıya düştü"


def test_KRITIK_disa_aktar_file_acl_YUKLENEMEZSE_emanet_YAZILMAZ(tmp_path, monkeypatch):
    m = betik_modulu("hasta_anahtari_emanet")
    monkeypatch.setattr(m, "_sirlari_oku", lambda: {_ALAN: _SAHTE})
    monkeypatch.setitem(sys.modules, "utils.file_acl", None)  # import → ImportError
    hedef = tmp_path / "kasa" / "emanet.txt"
    with pytest.raises(SystemExit) as e:
        m.disa_aktar(hedef)
    assert "file_acl" in str(e.value.code), f"hata iletisi ne olduğunu söylemiyor: {e.value.code!r}"
    assert not hedef.exists(), "ACL modülü yüklenemediği hâlde düz-metin emanet YAZILDI (İG-9.16)"


def test_KRITIK_disa_aktar_ACL_UYGULANAMAZSA_UYARIR(tmp_path, monkeypatch, capsys):
    """ACL'siz birim (FAT/exFAT USB — ana kullanım): yazılır ama UYARI basılır."""
    m = betik_modulu("hasta_anahtari_emanet")
    monkeypatch.setattr(m, "_sirlari_oku", lambda: {_ALAN: _SAHTE})
    monkeypatch.setattr(m, "_dosya_sistemi", lambda yol: "exFAT", raising=False)
    import utils.file_acl as acl

    monkeypatch.setattr(acl, "lock_down_file", lambda *a, **k: False)
    hedef = tmp_path / "kasa" / "emanet.txt"
    assert m.disa_aktar(hedef) == 0
    err = capsys.readouterr().err
    assert hedef.exists()
    assert "ACL" in err and "UYGULANAMADI" in err, f"ACL kilidi uygulanamadı ama UYARI yok (İG-9.16): {err!r}"


def test_KRITIK_disa_aktar_NTFS_te_kilit_TUTMAZSA_YAZMAZ(tmp_path, monkeypatch, capsys):
    """D0Ö.20 ek (tur 4): ACL destekleyen birimde kilit tutmazsa düz-metin emanet YAZILMAZ, rc≠0.

    Eskiden yalnız uyarı + rc=0 idi: icacls NTFS'te başarısız olursa anahtar bu makinedeki başka
    hesaplarca okunabilir hâlde diskte kalıyordu ("ACL'siz yazmaz" yalnız modül yüklenemezken doğruydu).
    """
    m = betik_modulu("hasta_anahtari_emanet")
    monkeypatch.setattr(m, "_sirlari_oku", lambda: {_ALAN: _SAHTE})
    monkeypatch.setattr(m, "_dosya_sistemi", lambda yol: "NTFS", raising=False)
    import utils.file_acl as acl

    monkeypatch.setattr(acl, "lock_down_file", lambda *a, **k: False)
    hedef = tmp_path / "kasa" / "emanet.txt"
    rc = m.disa_aktar(hedef)
    cikti = capsys.readouterr()
    assert rc != 0, "NTFS'te ACL kilidi tutmadı ama emanet BAŞARILI sayıldı"
    assert not hedef.exists(), "NTFS'te ACL kilidi tutmadığı hâlde düz-metin emanet diskte KALDI"
    assert "YAZILMADI" in cikti.err, f"hata ne olduğunu söylemiyor: {cikti.err!r}"
    assert _SAHTE not in cikti.out + cikti.err


def test_KRITIK_disa_aktar_ONCE_kilit_SONRA_icerik_ve_HESAP_disari_atilmaz(tmp_path, monkeypatch, capsys):
    """D0Ö.20 ek (tur 4, ORTA): kilit içerikten ÖNCE ve çalıştıran hesabı KORUYARAK uygulanır.

    `keep_current_user=False` (varsayılan) dosyayı yalnız SYSTEM + Administrators'a açar: UAC'li ya da
    standart hesap KENDİ emanetini `--dogrula` ile okuyamaz (file_acl: "DENETİM P3 — sahada yaşandı").
    Kilit yazımdan SONRA gelirse düz-metin anahtar arada miras ACL'siyle (Users okur) durur.
    """
    m = betik_modulu("hasta_anahtari_emanet")
    monkeypatch.setattr(m, "_sirlari_oku", lambda: {_ALAN: _SAHTE})
    import utils.file_acl as acl

    kilitler = []

    def _kilit(yol, keep_current_user=False):
        kilitler.append((Path(yol).stat().st_size, keep_current_user))
        return True

    monkeypatch.setattr(acl, "lock_down_file", _kilit)
    hedef = tmp_path / "kasa" / "emanet.txt"
    assert m.disa_aktar(hedef) == 0
    assert kilitler == [(0, True)], f"kilit (boyut-anında, hesap-korunur) beklenen [(0, True)] değil: {kilitler}"
    assert f"{_ALAN} = {_SAHTE}" in hedef.read_text(encoding="utf-8"), "içerik kilitten sonra YAZILMADI"
    assert "ACL:" in capsys.readouterr().out, "başarıda kimin okuyabileceği söylenmiyor"


@pytest.mark.skipif(sys.platform != "win32", reason="NTFS ACL yalnız Windows")
def test_KRITIK_GERCEK_kilit_AYNI_HESABA_acik_Users_grubuna_KAPALI(tmp_path, monkeypatch):
    """Gerçek icacls (tmp_path NTFS): kilitten sonra ACE'lerde çalıştıran hesap VAR, yerel Users YOK
    ve `--dogrula` aynı süreçte emaneti okur. ⚠️ Yükseltilmiş süreçte okuma Administrators'tan da
    geçer; bu yüzden ACE listesi ayrıca ölçülür."""
    import getpass
    import subprocess

    m = betik_modulu("hasta_anahtari_emanet")
    monkeypatch.setattr(m, "_sirlari_oku", lambda: {_ALAN: _SAHTE})
    hedef = tmp_path / "kasa" / "emanet.txt"
    hedef.parent.mkdir()
    hedef.write_text("eski emanet\n", encoding="utf-8")
    # Temp dizini Users'ı zaten miras VERMEZ: açık bir Users ACE'si konur ki kilidin onu kaldırdığı ölçülsün.
    subprocess.run(["icacls", str(hedef), "/grant", "*S-1-5-32-545:(R)"], capture_output=True, check=True)
    try:
        assert m.disa_aktar(hedef) == 0
        assert m.dogrula(hedef) == 0
        aceler = subprocess.run(["icacls", str(hedef)], capture_output=True, text=True).stdout
        aceler = aceler.replace(str(hedef), "").lower()
        assert f"\\{getpass.getuser().lower()}:" in aceler, f"çalıştıran hesap ACE'lerde YOK: {aceler!r}"
        assert "builtin\\users" not in aceler and "s-1-5-32-545" not in aceler, f"Users okuyabilir: {aceler!r}"
    finally:
        subprocess.run(["icacls", str(hedef), "/reset", "/q"], capture_output=True)


def test_KRITIK_dogrula_IZIN_hatasi_ne_yapilacagini_SOYLER(tmp_path, monkeypatch):
    """Eski sürümün yalnız-yönetici kilidi: `--dogrula` ham traceback değil EYLEM söyler."""
    m = betik_modulu("hasta_anahtari_emanet")
    monkeypatch.setattr(m, "_sirlari_oku", lambda: {_ALAN: _SAHTE})
    emanet = tmp_path / "emanet.txt"
    emanet.write_text(f"{_ALAN} = {_SAHTE}\n", encoding="utf-8")

    class _Kilitli(type(emanet)):
        def read_text(self, *a, **k):
            raise PermissionError(13, "Erisim engellendi")

    with pytest.raises(SystemExit) as e:
        m.dogrula(_Kilitli(str(emanet)))
    assert "yonetici" in str(e.value.code).lower(), f"izin hatası eylem söylemiyor: {e.value.code!r}"


def test_KRITIK_veri_koku_path_utils_YUKLENEMEZSE_SESSIZ_devam_etmez(monkeypatch):
    m = betik_modulu("hasta_anahtari_emanet")
    monkeypatch.setitem(sys.modules, "utils.path_utils", None)
    with pytest.raises(SystemExit) as e:
        m._veri_koku_adaylari()
    assert "path_utils" in str(e.value.code)


def test_KRITIK_veri_koku_CALISMA_ANI_hatasi_ne_yapilacagini_SOYLER(monkeypatch):
    """D0Ö.20 ek (tur 4): `get_app_data_directory()` (PEMF_DATA_DIR kökünde mkdir) izin hatası ham
    traceback değil, ne yapılacağını söyleyen bir çıkıştır."""
    m = betik_modulu("hasta_anahtari_emanet")
    import utils.path_utils as pu

    def _izin_yok():
        raise PermissionError(13, "Erisim engellendi")

    monkeypatch.setattr(pu, "get_app_data_directory", _izin_yok)
    with pytest.raises(SystemExit) as e:
        m._veri_koku_adaylari()
    assert "veri koku" in str(e.value.code).lower(), f"hata ne olduğunu söylemiyor: {e.value.code!r}"
