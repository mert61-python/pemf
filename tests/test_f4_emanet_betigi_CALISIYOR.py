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
    m = betik_modulu("hasta_anahtari_emanet")
    monkeypatch.setattr(m, "_sirlari_oku", lambda: {_ALAN: _SAHTE})
    import utils.file_acl as acl

    monkeypatch.setattr(acl, "lock_down_file", lambda *a, **k: False)
    hedef = tmp_path / "kasa" / "emanet.txt"
    m.disa_aktar(hedef)
    err = capsys.readouterr().err
    assert hedef.exists()
    assert "ACL" in err and "UYGULANAMADI" in err, f"ACL kilidi uygulanamadı ama UYARI yok (İG-9.16): {err!r}"


def test_KRITIK_veri_koku_path_utils_YUKLENEMEZSE_SESSIZ_devam_etmez(monkeypatch):
    m = betik_modulu("hasta_anahtari_emanet")
    monkeypatch.setitem(sys.modules, "utils.path_utils", None)
    with pytest.raises(SystemExit) as e:
        m._veri_koku_adaylari()
    assert "path_utils" in str(e.value.code)
