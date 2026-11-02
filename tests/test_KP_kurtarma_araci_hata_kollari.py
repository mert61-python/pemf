# -*- coding: utf-8 -*-
"""KP-1 · `tools/kurtarma.py` (`PEMF_Backend.exe --kurtarma`, anakartı ölen kliniğin TEK yolu) · sözleşmeler: kurtarma kodu gösterimi
(okunamaz → rc 2, yok → rc 1, var → biçimli kod rc 0) · zarf yoksa rc 2 · mevcut anahtar (çözülemeyen dahil) varken ÜSTÜNE YAZMAZ rc 3 ·
anahtarlar tek yazımda, düşerse HİÇBİRİ yazılmaz rc 4 · hesap yedeği: yok rc 2, bozuk düz yedek rc 2, doğrulanamayan kopya çıktı BIRAKMAZ rc 4,
şifreli yedekte anahtar okunamaz / yok rc 2, çözülemez rc 4 · operatör ortamında PEMF_DATA_DIR yoksa makine kökü (ProgramData) kullanılır ve
süreç içi çağrıdan sonra ortam GERİ alınır · eksik argüman → kullanım hatası, kod verilmezse gizli sorulur · donmuş EXE'de depo kökü ARANMAZ.

Gerçek kasa / veri kökü YOK: sır deposu (`utils.secrets_manager.get_secret` / `set_secrets`), kopya (`shutil.copy2`) ve gizli giriş (`getpass`)
EN ALT katta sahte; zarf GERÇEK `utils.backup_recovery.build_envelope` ile; dizinler tmp.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

import pytest
import utils.secrets_manager as sm
from utils import backup_recovery as br

from tools import kurtarma as ku

KOD = "ABCDEFGHJKMNPQRSTUVW"


@pytest.fixture
def ortam(monkeypatch, tmp_path):
    monkeypatch.delenv("PEMF_KURTARMA_USTUNE_YAZ", raising=False)
    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path / "veri"))
    durum = {"sirlar": {}, "yazilan": []}
    monkeypatch.setattr(sm, "get_secret", lambda ad, *a, **k: durum["sirlar"].get(ad, ""))
    monkeypatch.setattr(sm, "set_secrets", lambda d: durum["yazilan"].append(dict(d)))
    return durum


def _zarf(tmp_path, anahtarlar):
    z = tmp_path / br.ENVELOPE_NAME
    z.write_bytes(br.build_envelope(KOD, anahtarlar))
    return z


def test_donmus_EXEde_depo_koku_ARANMAZ_kaynak_agacinda_isaret_yoksa_HATA(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert ku._depo_koku(tmp_path) is None
    monkeypatch.setattr(sys, "frozen", False)
    with pytest.raises(RuntimeError, match="depo kökü bulunamadı"):
        ku._depo_koku(tmp_path / "derin" / "yol")


def test_kurtarma_kodu_gosterimi_okunamaz_YOK_ve_VAR(ortam, monkeypatch, capsys):
    monkeypatch.setattr(sm, "get_secret", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("çözülemez")))
    assert ku.main(["--kodu-goster"]) == 2 and "kurtarma kodu okunamadi" in capsys.readouterr().out
    monkeypatch.setattr(sm, "get_secret", lambda *a, **k: "")
    assert ku.main(["--kodu-goster"]) == 1 and "URETILMEMIS" in capsys.readouterr().out
    monkeypatch.setattr(sm, "get_secret", lambda *a, **k: KOD)
    assert ku.main(["--kodu-goster"]) == 0
    assert br.format_code(KOD) in capsys.readouterr().out


def test_zarf_YOKSA_rc2(ortam, tmp_path, capsys):
    assert ku.main(["--zarf", str(tmp_path / "yok.enc"), "--kod", KOD]) == 2
    assert "zarf bulunamadi" in capsys.readouterr().out


def test_KRITIK_cozulemeyen_mevcut_anahtar_da_MEVCUT_sayilir_USTUNE_YAZILMAZ(ortam, monkeypatch, tmp_path, capsys):
    z = _zarf(tmp_path, {"sqlcipher_key": "kurtarilan-sql"})
    monkeypatch.setattr(
        sm, "get_secret", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("başka makinenin DPAPI'si"))
    )
    assert ku.main(["--zarf", str(z), "--kod", KOD, "--yaz"]) == 3
    assert "DURDURULDU" in capsys.readouterr().out and ortam["yazilan"] == [], (
        "çözülemeyen anahtarın üstüne yazıldı (veri kaybı)"
    )


def test_KRITIK_toplu_yazim_DUSERSE_HICBIR_anahtar_yazilmaz_rc4(ortam, monkeypatch, tmp_path, capsys):
    z = _zarf(tmp_path, {"sqlcipher_key": "s", "patient_fernet_key": "p"})
    monkeypatch.setattr(sm, "set_secrets", lambda d: (_ for _ in ()).throw(PermissionError("AV kilidi")))
    assert ku.main(["--zarf", str(z), "--kod", KOD, "--yaz"]) == 4
    cikti = capsys.readouterr().out
    assert "HICBIR anahtar yazilmadi" in cikti and "Servisi BASLATMAYIN" in cikti and "yazildi:" not in cikti


def test_hesap_yedegi_YOK_ve_BOZUK_duz_yedek_rc2_cikti_YOK(ortam, tmp_path, capsys):
    cikti = tmp_path / "auth_users.db"
    assert ku.main(["--hesap-yedegi", str(tmp_path / "yok.db"), "--cikti", str(cikti)]) == 2
    bozuk = tmp_path / "pemf_auth_users_1.db"
    bozuk.write_bytes(b"SQLite format 3\x00" + b"\x00" * 50)  # başlık düz ama sayfa yapısı yok
    assert ku.main(["--hesap-yedegi", str(bozuk), "--cikti", str(cikti)]) == 2
    assert "ACILMIYOR / bozuk" in capsys.readouterr().out and not cikti.exists()


def test_KRITIK_dogrulanamayan_kopya_CIKTI_BIRAKMAZ_rc4(ortam, monkeypatch, tmp_path, capsys):
    import shutil
    import sqlite3

    yedek = tmp_path / "pemf_auth_users_2.db"
    with sqlite3.connect(yedek) as c:
        c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, ad TEXT)")
        c.execute("INSERT INTO users (ad) VALUES ('op')")
    monkeypatch.setattr(
        shutil, "copy2", lambda a, b: Path(b).write_bytes(Path(a).read_bytes()[:100])
    )  # disk dolu: YARIM kopya
    cikti = tmp_path / "auth_users.db"
    assert ku.main(["--hesap-yedegi", str(yedek), "--cikti", str(cikti)]) == 4
    assert "KOPYALANAMADI" in capsys.readouterr().out
    assert not cikti.exists() and not Path(f"{cikti}.yazim.tmp").exists(), "yarım kopya bırakıldı"


def test_sifreli_hesap_yedeginde_anahtar_OKUNAMAZ_YOK_ya_da_COZULEMEZ(ortam, monkeypatch, tmp_path, capsys):
    yedek = tmp_path / "pemf_auth_users_3.db"
    yedek.write_bytes(b"\x8a\x11sifreli-icerik" * 40)
    cikti = tmp_path / "auth_users.db"
    monkeypatch.setattr(sm, "get_secret", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("DPAPI")))
    assert ku.main(["--hesap-yedegi", str(yedek), "--cikti", str(cikti)]) == 2
    out = capsys.readouterr().out
    assert "sqlcipher_key okunamadi" in out and "sqlcipher_key YOK" in out and "--yaz" in out
    monkeypatch.setattr(sm, "get_secret", lambda *a, **k: "yanlis-anahtar")
    assert ku.main(["--hesap-yedegi", str(yedek), "--cikti", str(cikti)]) == 4
    assert "COZULEMEDI" in capsys.readouterr().out and not cikti.exists()


def test_operator_ortaminda_MAKINE_koku_kullanilir_sonra_ortam_GERI_alinir(ortam, monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("PEMF_DATA_DIR", raising=False)
    (tmp_path / "pd" / "PEMF_System").mkdir(parents=True)
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "pd"))
    gorulen: list = []
    monkeypatch.setattr(
        sm, "get_secret", lambda *a, **k: gorulen.append(__import__("os").environ.get("PEMF_DATA_DIR")) or ""
    )
    assert ku.main(["--kodu-goster"]) == 1
    assert gorulen == [str(tmp_path / "pd" / "PEMF_System")], "araç launcher'ın veri kökü yerine kullanıcı köküne baktı"
    assert "PEMF_DATA_DIR" not in __import__("os").environ, "süreç içi çağrı ortamı kalıcı değiştirdi"
    assert str(tmp_path / "pd" / "PEMF_System" / "PEMF_GUI") in capsys.readouterr().out


def test_eksik_argumanlar_KULLANIM_hatasi_kod_verilmezse_GIZLI_sorulur(ortam, monkeypatch, tmp_path):
    with pytest.raises(SystemExit):
        ku.main(["--hesap-yedegi", str(tmp_path / "x.db")])
    with pytest.raises(SystemExit):
        ku.main([])
    import getpass

    sorulan: list = []
    monkeypatch.setattr(getpass, "getpass", lambda istem: sorulan.append(istem) or KOD)
    assert ku.main(["--zarf", str(_zarf(tmp_path, {"sqlcipher_key": "s"}))]) == 0 and sorulan == ["Kurtarma kodu: "]
    monkeypatch.setattr(getpass, "getpass", lambda istem: (_ for _ in ()).throw(EOFError("konsol yok")))
    with pytest.raises(SystemExit):
        ku.main(["--zarf", str(tmp_path / br.ENVELOPE_NAME)])


def test_betik_olarak_calistirilinca_main_cikis_koduyla_biter(ortam, monkeypatch):
    monkeypatch.setattr(sm, "get_secret", lambda *a, **k: "")
    monkeypatch.setattr(sys, "argv", ["kurtarma.py", "--kodu-goster"])
    kok = Path(ku.__file__).resolve().parents[1]
    beklenen = [str(kok), str(kok / "apps" / "backend")]
    monkeypatch.setattr(
        sys, "path", [p for p in sys.path if p not in beklenen]
    )  # operatörün yalın python'u (yollar yok)
    with pytest.raises(SystemExit) as c:
        runpy.run_path(ku.__file__, run_name="__main__")
    assert c.value.code == 1
    assert all(y in sys.path for y in beklenen), (
        "kaynak ağacından koşunca depo kökü / apps/backend yola eklenmedi (utils bulunmaz)"
    )
