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
    # D0Ö.20 ek-2 (tur 5): TR arayüz "BUILTIN\Kullanıcılar" basar — yalnız İngilizce ad aranırsa boşa döner.
    yasak = ("builtin\\users", "s-1-5-32-545", "\\kullan", "authenticated users", "s-1-5-11")
    # D0Ö.20 ek-3 (tur 6): ÖN-KOŞUL — yasak listesi konan Users ACE'sini kilitten ÖNCE GÖRMELİ; başka arayüz
    # dilinde (ör. "VORDEFINIERT\Benutzer") liste boşa döner ve kilit hiç ölçülmeden yeşil kalırdı.
    once = subprocess.run(["icacls", str(hedef)], capture_output=True, text=True).stdout
    once = once.replace(str(hedef), "").lower()
    assert [y for y in yasak if y in once], f"ön-koşul: yasak listesi Users ACE'sini görmüyor (arayüz dili?): {once!r}"
    try:
        assert m.disa_aktar(hedef) == 0
        assert m.dogrula(hedef) == 0
        aceler = subprocess.run(["icacls", str(hedef)], capture_output=True, text=True).stdout
        aceler = aceler.replace(str(hedef), "").lower()
        assert f"\\{getpass.getuser().lower()}:" in aceler, f"çalıştıran hesap ACE'lerde YOK: {aceler!r}"
        assert not [y for y in yasak if y in aceler], f"Users / Authenticated Users okuyabilir: {aceler!r}"
    finally:
        subprocess.run(["icacls", str(hedef), "/reset", "/q"], capture_output=True)


def test_KRITIK_disa_aktar_hedef_KLASORSE_kilide_DOKUNMAZ(tmp_path, monkeypatch, capsys):
    """D0Ö.20 ek-2 (tur 5, ORTA — ek-1'in getirdiği regresyon): hedef var olan bir KLASÖRse yeni sıra
    (touch → kilit → yazım) klasörün ACL'sini yazım düşmeden ÖNCE yeniden yazıyordu (POSIX'te chmod 0600:
    sahip klasörü dolaşamaz). Eski sırada yazım hemen düşer, kilide hiç varılmazdı."""
    m = betik_modulu("hasta_anahtari_emanet")
    monkeypatch.setattr(m, "_sirlari_oku", lambda: {_ALAN: _SAHTE})
    import utils.file_acl as acl

    kilitler: list[str] = []
    monkeypatch.setattr(acl, "lock_down_file", lambda yol, **k: kilitler.append(str(yol)) or True)
    klasor = tmp_path / "kasa"
    klasor.mkdir()
    (klasor / "baska_dosya.txt").write_text("sahibin", encoding="utf-8")
    rc = m.disa_aktar(klasor)
    assert rc != 0, "klasör hedefte emanet başarılı sayıldı"
    assert not kilitler, f"klasör hedefte lock_down_file ÇAĞRILDI (klasörün ACL'si değişir): {kilitler}"
    assert klasor.is_dir() and (klasor / "baska_dosya.txt").read_text(encoding="utf-8") == "sahibin"
    assert "DOSYA yolu" in capsys.readouterr().err, "hata ne yapılacağını söylemiyor"


def test_KRITIK_dosya_sistemi_GERCEK_birimi_OKUR(tmp_path):
    """D0Ö.20 ek-2 (tur 5): `_dosya_sistemi`nin gerçek ctypes yolu hiçbir kolda koşmuyordu (kollar onu yamıyor);
    None'a bozulursa NTFS reddi sessizce kapanır (fail-open), kapılar yeşil kalırdı."""
    m = betik_modulu("hasta_anahtari_emanet")
    fs = m._dosya_sistemi(tmp_path)
    if sys.platform == "win32":
        assert (fs or "").upper() in {"NTFS", "REFS"}, f"tmp_path birimi okunamadı ya da beklenmedik: {fs!r}"
    else:
        assert fs is None


def test_KRITIK_NTFS_te_kilit_TUTMAZSA_ONCEKI_emanet_DEGISMEZ(tmp_path, monkeypatch, capsys):
    """D0Ö.20 ek-2 (tur 5): var olan (önceki) emanette kilit tutmazsa ne silinir ne üzerine yazılır — rc 2.
    `if yeni:` silinse ya da ret yalnız yeni dosyaya uygulansa tek emanet kopyası silinir / kilitsiz
    düz metin yazılırdı; tüm kollar yeni dosya kullandığı için kapısızdı."""
    m = betik_modulu("hasta_anahtari_emanet")
    monkeypatch.setattr(m, "_sirlari_oku", lambda: {_ALAN: _SAHTE})
    monkeypatch.setattr(m, "_dosya_sistemi", lambda yol: "NTFS", raising=False)
    import utils.file_acl as acl

    monkeypatch.setattr(acl, "lock_down_file", lambda *a, **k: False)
    hedef = tmp_path / "kasa" / "emanet.txt"
    hedef.parent.mkdir()
    hedef.write_text("onceki-emanet\n", encoding="utf-8")
    rc = m.disa_aktar(hedef)
    cikti = capsys.readouterr()
    assert rc == 2, f"NTFS'te kilit tutmadığı hâlde rc={rc}"
    assert hedef.read_text(encoding="utf-8") == "onceki-emanet\n", "ÖNCEKİ emanet silindi ya da üzerine yazıldı"
    assert "DEGISTIRILMEDI" in cikti.err, f"önceki dosyanın durumu söylenmedi: {cikti.err!r}"


def test_KRITIK_ikinci_disa_aktar_IZIN_hatasi_ne_yapilacagini_SOYLER(tmp_path, monkeypatch):
    """Eski sürümün yalnız-yönetici kilidindeki hedefe ikinci `--disa-aktar`: ham traceback değil EYLEM."""
    m = betik_modulu("hasta_anahtari_emanet")
    monkeypatch.setattr(m, "_sirlari_oku", lambda: {_ALAN: _SAHTE})
    hedef = tmp_path / "kasa" / "emanet.txt"
    hedef.parent.mkdir()
    hedef.write_text("onceki-emanet\n", encoding="utf-8")
    gercek_touch = Path.touch

    def _kilitli_touch(self, *a, **k):
        if Path(self) == hedef:
            raise PermissionError(13, "Erisim engellendi")
        return gercek_touch(self, *a, **k)

    monkeypatch.setattr(Path, "touch", _kilitli_touch)
    with pytest.raises(SystemExit) as e:
        m.disa_aktar(hedef)
    assert "yonetici" in str(e.value.code).lower(), f"izin hatası eylem söylemiyor: {e.value.code!r}"


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
