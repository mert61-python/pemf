# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""1-G inceleme G-3.3 — A-11 kurulum yolunun broker servisi (`scripts/install_mosquitto_service.ps1`) hazırlanmamış
kurulumda AÇILIR.

ÖLÇÜLEN KUSUR (`b733a79`, önceden var; D1.104'ün ölçtüğü sınıf): betik yapılandırmayı
`include_dir C:/ProgramData/PEMF_System/mosquitto/conf.d` ile bitiriyor ve `conf.d`'yi YALNIZ oluşturuyordu.
mosquitto 2.0.18 Windows'ta BOŞ include_dir'de AÇILMAZ — bu betiğin kendi yapılandırmasıyla ölçüldü:
"Error: Unable to open include_dir …". 1-G (D1.104) aynı sınıfı `setup_services.ps1`'de yer tutucuyla kapattı; A-11'in
desteklenen ikinci kurulum yolu (install_backend_service.ps1 → "önce install_mosquitto_service.ps1") dışarıda kalmıştı —
oysa D1.104 `--mqtt-kimlik hazirla` kimlik parçasını tam bu dizine yazar.

KAPI: betiğin `$conf` bloğu (listener → 127.0.0.1:rastgele, dosya günlüğü → stderr, `$ConfDir` → test dizini) + betiğin
KENDİ yazdığı yer tutucu (adı ve içeriği betikten okunur) ile GERÇEK mosquitto AÇILIR; yer tutucu servis kaydından ÖNCE
yazılır. KARŞIT (aparat kanıtı): aynı yapılandırma BOŞ conf.d ile açılmaz.
"""

from __future__ import annotations

import re
from pathlib import Path

import capraz
import mosquitto_aparat as ma
import pytest

KOK = Path(__file__).resolve().parents[1]
BETIK = KOK / "scripts" / "install_mosquitto_service.ps1"


def _betik() -> str:
    return BETIK.read_text(encoding="utf-8-sig")


def _yapilandirma(port: int, conf_d: Path) -> str:
    m = re.search(r'\$conf = @"\r?\n(.*?)\r?\n"@', _betik(), re.S)
    assert m, "aparat: betikte $conf bloğu yok"
    conf = m.group(1).replace("\r\n", "\n")
    assert "listener 1883 0.0.0.0" in conf, "aparat: listener satırı yok"
    assert "include_dir $($ConfDir -replace '\\\\','/')" in conf, "aparat: include_dir $ConfDir satırı yok"
    conf = conf.replace("listener 1883 0.0.0.0", f"listener {port} 127.0.0.1")
    conf = re.sub(r"(?m)^log_dest file .*$", "log_dest stderr", conf)
    conf = conf.replace("$($ConfDir -replace '\\\\','/')", conf_d.as_posix())
    assert "$" not in conf, f"aparat: çözülmemiş PowerShell ifadesi:\n{conf}"
    return conf


def _yer_tutucu() -> tuple[str, str] | None:
    """Betiğin conf.d'ye yazdığı yer tutucu (ad, içerik) — yoksa None."""
    t = _betik()
    ad = re.search(r'\$(\w+)\s*=\s*Join-Path\s+\$ConfDir\s+"([^"]+\.conf)"', t)
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


def test_KRITIK_G33_servis_yapilandirmasi_betigin_YER_TUTUCUSUyla_ACILIR(tmp_path):
    yt = _yer_tutucu()
    assert yt is not None, (
        "install_mosquitto_service.ps1 conf.d'ye yer tutucu YAZMIYOR — include_dir boş kalır, mosquitto (Windows) AÇILMAZ"
    )
    acildi, hata = _ac(tmp_path, yt)
    assert acildi, f"betiğin yapılandırması + kendi yer tutucusu ile broker AÇILMADI: {hata[-400:]}"
    t = _betik()
    assert t.index(f'"{yt[0]}"') < t.index("& $ExePath install"), "yer tutucu servis KAYDINDAN SONRA yazılıyor"


def test_KARSIT_G33_ayni_yapilandirma_BOS_conf_d_ile_ACILMAZ_aparat_kaniti(tmp_path):
    acildi, hata = _ac(tmp_path, None)
    assert not acildi and "Unable to open include_dir" in hata, (
        f"aparat: boş include_dir sınıfı ölçülemedi: {hata[-300:]}"
    )


def test_KRITIK_G33_servisin_conf_d_si_D1104_kimlik_parcasinin_dizini():
    """`hazirla` (Windows varsayılanı `%ProgramData%\\PEMF_System\\mosquitto`) kimlik parçasını bu betiğin include_dir'ine
    yazar — biri kayarsa A-11 kurulumunda kimlik sessizce devre dışı kalır."""
    m = re.search(r'\$DataRoot\s*=\s*"([^"]+)"', _betik())
    assert m, "aparat: $DataRoot yok"
    assert m.group(1).lower() == r"c:\programdata\pemf_system\mosquitto", m.group(1)
    assert re.search(r'\$ConfDir\s*=\s*"\$DataRoot\\conf\.d"', _betik()), "conf.d $DataRoot altında değil"
