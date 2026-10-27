# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""1-G §8 #11 (1-H) — ağ geçidi kurulumu (`scripts/install_mosquitto.ps1` + `config/mosquitto/mosquitto.conf`) hazırlanmamış
kurulumda broker'ı AÇAR.

ÖLÇÜLEN KUSUR (önceden var; G-3.3 / D1.104'ün ölçtüğü sınıf): `config/mosquitto/mosquitto.conf` SONDA
`include_dir C:/ProgramData/mosquitto/conf.d` içerir; `install_mosquitto.ps1` `conf.d`'yi YALNIZ oluşturur. mosquitto
2.0.18 Windows'ta BOŞ include_dir'de AÇILMAZ ("Error: Unable to open include_dir"). `--mqtt-kimlik hazirla
--broker-dizini C:/ProgramData/mosquitto` kimlik parçasını bu dizine yazana dek broker hiç açılmaz → ESP'ler (bobin 6-8 STOP
yolu) bağlanamaz.

KAPI: deponun GERÇEK `config/mosquitto/mosquitto.conf`'u (listener → 127.0.0.1:rastgele, dosya günlüğü → stderr, include_dir
→ test dizini) + kurulum betiğinin KENDİ yazdığı yer tutucu (adı ve içeriği betikten okunur) ile GERÇEK mosquitto AÇILIR;
yer tutucu, yapılandırma kopyalanmadan ve servis başlatılmadan ÖNCE yazılır. KARŞIT (aparat kanıtı): aynı yapılandırma BOŞ
conf.d ile açılmaz.
"""

from __future__ import annotations

import re
from pathlib import Path

import capraz
import mosquitto_aparat as ma
import pytest

KOK = Path(__file__).resolve().parents[1]
BETIK = KOK / "scripts" / "install_mosquitto.ps1"
CONF = KOK / "config" / "mosquitto" / "mosquitto.conf"
_INCLUDE = "include_dir C:/ProgramData/mosquitto/conf.d"


def _betik() -> str:
    return BETIK.read_text(encoding="utf-8-sig")


def _yapilandirma(port: int, conf_d: Path) -> str:
    conf = CONF.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert "listener 1883 0.0.0.0" in conf, "aparat: listener satırı yok"
    assert conf.count(_INCLUDE) == 1, f"aparat: `{_INCLUDE}` satırı yok/birden çok"
    conf = conf.replace("listener 1883 0.0.0.0", f"listener {port} 127.0.0.1")
    conf = re.sub(r"(?m)^log_dest file .*$", "log_dest stderr", conf)
    return conf.replace(_INCLUDE, f"include_dir {conf_d.as_posix()}")


def _yer_tutucu() -> tuple[str, str] | None:
    """Betiğin conf.d'ye yazdığı yer tutucu (ad, içerik) — yoksa None."""
    t = _betik()
    ad = re.search(r'\$(\w+)\s*=\s*Join-Path\s+\$MOSQUITTO_CONF_DIR\s+"([^"]+\.conf)"', t)
    if not ad:
        return None
    yaz = re.search(r"Set-Content\s+-Path\s+\$" + ad.group(1) + r'\s+-Value\s+"([^"]*)"', t)
    return (ad.group(2), yaz.group(1)) if yaz else None


def _ac(tmp_path: Path, yer_tutucu: tuple[str, str] | None):
    conf_d = tmp_path / "conf.d"
    conf_d.mkdir()
    if yer_tutucu:
        (conf_d / yer_tutucu[0]).write_text(yer_tutucu[1] + "\n", encoding="ascii")
    port = ma.bos_port()
    b = ma.Broker(_yapilandirma(port, conf_d), tmp_path / "b", port)
    try:
        b.basla()
        return True, ""
    except AssertionError as e:
        return False, str(e)
    finally:
        b.dur()


@pytest.fixture(autouse=True)
def _ikili():
    if ma.ikili() is None:
        capraz.atla("mosquitto ikilisi yok (Linux CI) — Windows CI aynı kapıyı paketteki 2.0.18 ile koşar")


def test_KRITIK_G811_ag_gecidi_yapilandirmasi_betigin_YER_TUTUCUSUyla_ACILIR(tmp_path):
    yt = _yer_tutucu()
    assert yt is not None, (
        "install_mosquitto.ps1 conf.d'ye yer tutucu YAZMIYOR — config/mosquitto/mosquitto.conf'un include_dir'i boş kalır, "
        "mosquitto (Windows) AÇILMAZ"
    )
    acildi, hata = _ac(tmp_path, yt)
    assert acildi, f"ağ geçidi yapılandırması + betiğin yer tutucusu ile broker AÇILMADI: {hata[-400:]}"
    t = _betik()
    i_yer = t.index(f'"{yt[0]}"')
    assert t.index("$MOSQUITTO_CONF_DIR, $MOSQUITTO_LOG_DIR") < i_yer, "yer tutucu conf.d oluşturulmadan ÖNCE yazılıyor"
    assert i_yer < t.index('Copy-Item $mainConf'), "yer tutucu yapılandırma kopyalandıktan SONRA yazılıyor"


def test_KARSIT_G811_ayni_yapilandirma_BOS_conf_d_ile_ACILMAZ_aparat_kaniti(tmp_path):
    acildi, hata = _ac(tmp_path, None)
    assert not acildi and "Unable to open include_dir" in hata, (
        f"aparat: boş include_dir sınıfı ölçülemedi: {hata[-300:]}"
    )


def test_KRITIK_G811_conf_d_hazirlama_aracinin_broker_dizini_ile_AYNI():
    """Yapılandırmanın yorumu `--mqtt-kimlik hazirla --broker-dizini C:/ProgramData/mosquitto` der — kimlik parçası tam bu
    include_dir'e yazılmalı; betiğin conf.d'si aynı dizin olmalı (biri kayarsa kimlik sessizce devre dışı kalır)."""
    t = _betik()
    assert re.search(r'\$MOSQUITTO_DATA_DIR\s*=\s*"C:\\ProgramData\\mosquitto"', t), "veri kökü değişti"
    assert re.search(r'\$MOSQUITTO_CONF_DIR\s*=\s*"\$MOSQUITTO_DATA_DIR\\conf\.d"', t), "conf.d veri kökü altında değil"
    assert "--broker-dizini C:/ProgramData/mosquitto" in CONF.read_text(encoding="utf-8")
