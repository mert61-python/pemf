# Author: mertaygn, cglrgrkn
"""D3I-A2.9 (doğrulayıcı F) — Y182 grubu yalnız `PEMF_GUI`ye `Değiştir` alırsa (T-g düzeltmesi), ikinci Windows hesabının backend'i
paylaşılan broker dizinindeki (`%ProgramData%\\PEMF_System\\mosquitto`) İLK hesabın yazdığı `pemf_calisma.conf`'u DEĞİŞTİREMEZ
(ProgramData mirası `Users`a yalnız YENİ dosya yaratma verir). Eskiden yazım hatası yutulup broker ANONİM tabanla açılıyordu →
A-04 (yerel broker kimliği) ikinci hesabın oturumlarında sessizce kayboluyordu. Çalışma kopyası artık HESABA ÖZEL dizinde
(`%LOCALAPPDATA%\\PEMF_System\\mosquitto` — kaldırma / KVKK temizliğinin bildiği kullanıcı kökü, `pemf_footprint.ps1` ve
`install::pemf_kokleri`); paylaşılan kimlik parçası (`conf.d`) yalnız OKUNUR.

Sahte EN ALT katta: ikinci hesabın yazamaması, paylaşılan dosyanın SALT-OKUR özniteliğiyle taklit edilir (gerçek hesap / ACL YOK);
GERÇEK `mqtt_kimlik.hazirla` + GERÇEK `MosquittoSupervisor._kimlik_dahil_conf`.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest


@pytest.fixture
def mk(monkeypatch, tmp_path):
    from utils import mqtt_kimlik

    monkeypatch.setenv("PEMF_DEVICE_IDENTITY_DIR", str(tmp_path / "makine"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "hesapB" / "AppData" / "Local"))
    mqtt_kimlik._onbellek.clear()
    yield mqtt_kimlik
    mqtt_kimlik._onbellek.clear()


def _taban(tmp_path: Path) -> Path:
    t = tmp_path / "taban.conf"
    t.write_text("listener 1883 0.0.0.0\nallow_anonymous true\n", encoding="utf-8")
    return t


def test_KRITIK_ilk_hesabin_calisma_kopyasi_DEGISTIRILEMESE_de_ikinci_hesabin_brokeri_KIMLIKLI(mk, tmp_path):
    from services.headless_services import MosquittoSupervisor

    taban = _taban(tmp_path)
    mk.hazirla()
    bd = mk.varsayilan_broker_dizini()
    ortak = bd / "pemf_calisma.conf"
    ortak.write_text("# ilk hesabin calisma kopyasi\n", encoding="utf-8")
    os.chmod(ortak, stat.S_IREAD)  # ikinci hesap ilk hesabın dosyasını değiştiremez
    try:
        calisma = MosquittoSupervisor.__new__(MosquittoSupervisor)._kimlik_dahil_conf(taban)
        assert calisma != taban, "ikinci hesabın broker'ı ANONİM tabana düştü — A-04 kimliği kayboldu"
        satirlar = calisma.read_text(encoding="utf-8").strip().splitlines()
        assert satirlar[-1] == f"include_dir {(bd / mk.CONF_DIZINI).as_posix()}", satirlar[-3:]
        kullanici_koku = (Path(os.environ["LOCALAPPDATA"]) / "PEMF_System").resolve()
        assert kullanici_koku in calisma.resolve().parents, (
            f"çalışma kopyası hesaba özel (temizlenen) kökte değil: {calisma}"
        )
        assert ortak.read_text(encoding="utf-8") == "# ilk hesabin calisma kopyasi\n", "paylaşılan dosya değişti"
    finally:
        os.chmod(ortak, stat.S_IWRITE | stat.S_IREAD)


def test_KARSIT_hazirlanmamis_kimlikte_taban_AYNEN_ve_paylasilan_dizine_YAZILMAZ(mk, tmp_path):
    from services.headless_services import MosquittoSupervisor

    taban = _taban(tmp_path)
    assert MosquittoSupervisor.__new__(MosquittoSupervisor)._kimlik_dahil_conf(taban) == taban
    assert not (mk.varsayilan_broker_dizini() / "pemf_calisma.conf").exists()
