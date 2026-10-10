# -*- coding: utf-8 -*-
"""E2-3.6 (2-E incelemesi A3) — yönergedeki kurtarma komutu (`"%LOCALAPPDATA%\\…\\PEMF_Backend.exe" --kurtarma …`, cmd penceresinde)
anahtarları launcher backend'inin OKUDUĞU veri köküne yazar; `--kodu-goster` cihazın kodunu gösterir.

Launcher backend'e `PEMF_DATA_DIR=%PROGRAMDATA%\\PEMF_System` + `PEMF_ENCRYPT_AT_REST=1` verir (launcher/core/src/install.rs:602-665;
`deploy/device.env` de aynı kök) ve kurulum = kur-ve-BAŞLAT (`install_and_launch` → `flow::start_backend`, launcher/app/src/main.rs:619-667):
yeni makinede backend bir kez açılıp o köke YENİ anahtar + kurtarma kodu yazar. Operatörün cmd penceresinde `PEMF_DATA_DIR` YOKTUR →
araç `%APPDATA%\\PEMF_GUI`ye düşer (ölçüldü, 2-E incelemesi E2-3.6): `--kodu-goster` "URETILMEMIS" (rc 1); `--yaz` kurtarılan anahtarları
`%APPDATA%\\PEMF_GUI\\pemf_secrets.json`e yazıp "sır deposuna yazıldı" (rc 0) der; backend yeniden açılınca kendi (ilk açılış) anahtarını
kullanır (göç hedefte anahtar varken dokunmaz) → yedekten kopyalanan DB AÇILMAZ.

Kapı: üç ALT SÜREÇ, aynı sahte kökler (`betik_alt_sureci.yalitik_ortam`, tmp_path): C1 launcher ortamıyla GERÇEK `get_app_data_directory`
+ `get_sqlcipher_key` + `get_or_create_code`; C2 operatör ortamıyla (PEMF_DATA_DIR YOK) GERÇEK `tools.kurtarma.main`; C3 launcher ortamıyla
GERÇEK kök çözümü + `get_sqlcipher_key` → kurtarılan anahtarla şifreli sentetik DB açılır mı. Değerler sentetik, yazdırılmaz.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from betik_alt_sureci import kostur, yalitik_ortam
from cryptography.fernet import Fernet
from sahte_vault_sunucusu import sqlcipher_mod

DEPO = Path(__file__).resolve().parents[1]
SQL = "e236-sql-kurtarilan"
ON = f"import sys, json, io, contextlib\nsys.path[:0] = [{str(DEPO / 'apps' / 'backend')!r}, {str(DEPO)!r}]\n"


def _kos(tmp: Path, ad: str, govde: str, env: dict) -> dict:
    b = tmp / f"{ad}.py"
    b.write_text(ON + govde, encoding="utf-8")
    p = kostur([str(b)], cwd=tmp, env=env, sure=180)
    for s in p.stdout.splitlines():
        if s.startswith("SONUC "):
            return json.loads(s[6:])
    raise AssertionError(f"aparat: {ad} sonuç basmadı (rc={p.returncode}):\n{(p.stdout + p.stderr)[-1200:]}")


@pytest.fixture()
def klinik(tmp_path):
    """Yeni makine: launcher kurdu ve backend'i BİR KEZ açtı (C1). Döner: (operatör ortamı, launcher ortamı, zarf, kod)."""
    from utils import backup_recovery as br

    kod = br.generate_recovery_code()
    zarf = tmp_path / "yedek" / br.ENVELOPE_NAME
    zarf.parent.mkdir()
    zarf.write_bytes(
        br.build_envelope(kod, {"sqlcipher_key": SQL, "patient_fernet_key": Fernet.generate_key().decode()})
    )
    operator = yalitik_ortam(tmp_path / "ev")
    launcher = dict(
        operator, PEMF_DATA_DIR=str(Path(operator["PROGRAMDATA"]) / "PEMF_System"), PEMF_ENCRYPT_AT_REST="1"
    )
    c1 = _kos(
        tmp_path,
        "c1",
        "from utils.path_utils import get_app_data_directory\n"
        "from database.sqlcipher_util import get_sqlcipher_key\n"
        "from utils import backup_recovery as br\n"
        "d = get_app_data_directory(); k = get_sqlcipher_key(d); c = br.get_or_create_code()\n"
        "print('SONUC ' + json.dumps({'anahtar': bool(k), 'kod': bool(c)}))\n",
        launcher,
    )
    assert c1 == {"anahtar": True, "kod": True}, f"aparat: launcher ilk açılışı anahtar/kod üretmedi: {c1}"
    return operator, launcher, zarf, kod


def _arac(tmp: Path, env: dict, argv: list[str]) -> dict:
    return _kos(
        tmp,
        "c2",
        "import tools.kurtarma as k\n"
        "t = io.StringIO()\n"
        "with contextlib.redirect_stdout(t):\n"
        f"    rc = k.main({argv!r})\n"
        "print('SONUC ' + json.dumps({'rc': rc, 'cikti': t.getvalue()[-600:]}))\n",
        env,
    )


def test_KRITIK_kodu_goster_LAUNCHER_kurulumunda_cihazin_kodunu_gosterir_E236(tmp_path, klinik):
    operator, _launcher, _zarf, _kod = klinik
    c2 = _arac(tmp_path, operator, ["--kodu-goster"])
    assert c2["rc"] == 0 and "KURTARMA KODU" in c2["cikti"], (
        f"cihazda kurtarma kodu VAR ama yönergedeki komut 'üretilmemiş' diyor (yanlış veri kökü):\n{c2['cikti']}"
    )


@pytest.mark.skipif(sqlcipher_mod() is None, reason="sqlcipher3 yok — DB açma zinciri ölçülemez")
def test_KRITIK_yaz_LAUNCHER_backendinin_KULLANDIGI_anahtari_kurtarir_yedek_DB_ACILIR_E236(tmp_path, klinik):
    operator, launcher, zarf, kod = klinik
    zorla = dict(operator, PEMF_KURTARMA_USTUNE_YAZ="1")  # taze makine: belgelenen zorlama (ilk açılışın anahtarı var)
    c2 = _arac(tmp_path, zorla, ["--zarf", str(zarf), "--kod", kod, "--yaz"])
    assert c2["rc"] == 0, f"aparat: --yaz başarısız: {c2}"
    c3 = _kos(
        tmp_path,
        "c3",
        "from utils.path_utils import get_app_data_directory\n"
        "from database.sqlcipher_util import get_sqlcipher_key, import_sqlcipher, open_encrypted_conn\n"
        "d = get_app_data_directory(); k = get_sqlcipher_key(d); mod = import_sqlcipher(); db = d / 'patients.db'\n"
        f"c = open_encrypted_conn(db, {SQL!r}, mod)\n"
        "c.execute('CREATE TABLE IF NOT EXISTS patients (id INTEGER PRIMARY KEY)'); c.execute('INSERT INTO patients DEFAULT VALUES')\n"
        "c.commit(); c.close()\n"
        "try:\n"
        "    c = open_encrypted_conn(db, k, mod); n = c.execute('SELECT COUNT(*) FROM patients').fetchone()[0]; c.close(); s = n\n"
        "except Exception as e:\n"
        "    s = type(e).__name__\n"
        f"print('SONUC ' + json.dumps({{'kurtarilan_anahtar': k == {SQL!r}, 'db': s}}))\n",
        launcher,
    )
    assert c3 == {"kurtarilan_anahtar": True, "db": 1}, (
        f"kurtarma 'yazildi' dedi ama launcher backend'i kurtarılan anahtarı KULLANMIYOR, yedekten kopyalanan DB açılmıyor: {c3}"
    )


def test_KARSIT_acik_PEMF_DATA_DIR_onurlandirilir_E236(tmp_path, klinik):
    operator, _launcher, zarf, kod = klinik
    ozel = tmp_path / "ozel_kok"
    c2 = _arac(tmp_path, dict(operator, PEMF_DATA_DIR=str(ozel)), ["--zarf", str(zarf), "--kod", kod, "--yaz"])
    assert c2["rc"] == 0 and (ozel / "PEMF_GUI" / "pemf_secrets.json").is_file(), c2
