# -*- coding: utf-8 -*-
"""KP-3 C · `utils/mqtt_kimlik.py` + `utils/model_downloader.py` kapsanmayan kolları — her test bir DAVRANIŞ iddiası:

- MQTT kimlik deposu: boş parolalı depo OKUNAMAZ sayılır (uyarı, None — boş parolayla broker kurulmaz).
- Anonim broker sondası: bağlantı reddedilirse "ölçülemedi" (None); CONNACK kabulünden sonra DISCONNECT gönderilemese de "anonim" (True).
- `ozet7_dogrula`: başka şema / bozuk kayıt → False (istisna yok).
- ESP başlığı / kabin kimliği: C dizesini / YAML'ı bozacak karakter → ValueError (dosyaya yazılmaz).
- `parcayi_onar`: parçalar yerindeyse "hazir"; yazılamazsa "yazilamadi" + uyarı (broker anonim kalır, depo EZİLMEZ).
- CLI: hazırlama RuntimeError'ı → "HATA:" + çıkış 2; modül doğrudan koşulunca `main()`in çıkış kodu süreç kodu olur.
- Model manifesti: paket / kaynak kökü çözülemezse ya da manifest bozuksa özet YOK (yan dosyayla denetim), günlüğe yazılır.
- Bütünlük: dosya yok → "dogrulanamadi"; yan özet dosyası okunamazsa → "dogrulanamadi" (fail-closed).
- Kalıcı model dizini: gizleme özniteliği verilemese de dizin döner; kök çözücüleri patlasa da kalıcı dizin aday kalır.
- Yan dosya çözümü: kurulu model araması patlarsa modül yanındaki yol döner (çağıran kendi hatasını üretir).

Sahte EN ALT katta: `socket.create_connection` (modül özniteliği), yol çözücüler, depo yolu, broker dosya yazıcısı, `ctypes.windll`.
Bağlantı reddi GERÇEK: az önce bırakılmış geçici bir loopback portu (yasak portlar değil).
"""

from __future__ import annotations

import importlib.util
import json
import logging
import socket
import sys
import types
from pathlib import Path

import pytest
from utils import model_downloader as md
from utils import mqtt_kimlik as mk

KOK = Path(__file__).resolve().parents[1]


def test_bos_parolali_depo_okunamaz_sayilir(monkeypatch, tmp_path, caplog):
    depo = tmp_path / "mqtt_kimlik.json"
    depo.write_text(json.dumps({mk.BACKEND_KULLANICI: "", mk.ESP_KULLANICI: "esp-parola"}), encoding="utf-8")
    monkeypatch.setattr(mk, "_depo_yolu", lambda: depo)
    monkeypatch.setattr(mk, "_onbellek", {})
    with caplog.at_level(logging.WARNING, logger=mk.logger.name):
        assert mk.kimlikleri_oku() is None
    assert any(
        "MQTT kimlik deposu okunamadı" in r.getMessage() and "ValueError" in r.getMessage() for r in caplog.records
    )


def test_anonim_sonda_ret_none_disconnect_hatasi_yine_true(monkeypatch):
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    bos_port = s.getsockname()[1]
    s.close()
    assert mk.broker_anonim_kabul_ediyor_mu("127.0.0.1", bos_port, zaman_asimi=1.0) is None

    class _Soket:
        def __init__(self):
            self.gonderilen = 0

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def settimeout(self, t):
            pass

        def sendall(self, b):
            self.gonderilen += 1
            if self.gonderilen > 1:
                raise ConnectionResetError("broker bağlantıyı kapattı")

        def recv(self, n):
            return b"\x20\x02\x00\x00"[:n]

    monkeypatch.setattr(mk, "socket", types.SimpleNamespace(create_connection=lambda *a, **k: _Soket()))
    assert mk.broker_anonim_kabul_ediyor_mu("broker.test", 18830) is True


def test_ozet7_dogrulama_bozuk_kayit_false():
    kayit = mk.ozet7("parola-1")
    assert mk.ozet7_dogrula("parola-1", kayit) is True
    assert mk.ozet7_dogrula("parola-1", kayit.replace("$7$", "$6$", 1)) is False
    assert mk.ozet7_dogrula("parola-1", "bozuk-kayit") is False


def test_c_ve_yaml_icin_guvensiz_kimlik_reddedilir():
    with pytest.raises(ValueError, match="C dizesine"):
        mk.firmware_basligi('pemf"esp', "parola")
    with pytest.raises(ValueError, match="YAML"):
        mk.kabin_kimlik_metni("pemf_cv", "par:ola")


def test_parca_onarimi_hazir_ve_yazilamadi(monkeypatch, tmp_path, caplog):
    hazir = tmp_path / "hazir"
    (hazir / mk.CONF_DIZINI).mkdir(parents=True)
    for ad in (mk.PASSWD_ADI, mk.ACL_ADI, f"{mk.CONF_DIZINI}/{mk.CONF_ADI}"):
        (hazir / ad).write_text("x")
    assert mk.parcayi_onar(hazir) == "hazir"
    depo = tmp_path / "depo.json"
    depo.write_text("{}")
    monkeypatch.setattr(mk, "_depo_yolu", lambda: depo)
    monkeypatch.setattr(mk, "kimlikleri_oku", lambda: {mk.BACKEND_KULLANICI: "a", mk.ESP_KULLANICI: "b"})

    def _yazma_patla(bd, kimlikler):
        raise PermissionError(13, "Erişim engellendi")

    monkeypatch.setattr(mk, "_broker_dosyalarini_yaz", _yazma_patla)
    with caplog.at_level(logging.WARNING, logger=mk.logger.name):
        assert mk.parcayi_onar(tmp_path / "bos") == "yazilamadi"
    assert any("broker ANONIM kalir" in r.getMessage() for r in caplog.records)
    assert depo.read_text() == "{}", "depo ezildi"


def test_cli_hazirlama_hatasi_cikis_2_ve_dogrudan_kosu(monkeypatch, tmp_path, capsys):
    def _patla(*a, **k):
        raise RuntimeError("kimlik deposu bozuk")

    monkeypatch.setattr(mk, "hazirla", _patla)
    assert mk.main(["hazirla", "--broker-dizini", str(tmp_path)]) == 2
    assert "HATA: kimlik deposu bozuk" in capsys.readouterr().out
    monkeypatch.setattr(sys, "argv", ["mqtt_kimlik", "durum", "--broker-dizini", str(tmp_path)])
    spec = importlib.util.spec_from_file_location("__main__", KOK / "apps/backend/utils/mqtt_kimlik.py")
    kopya = importlib.util.module_from_spec(spec)
    with pytest.raises(SystemExit) as e:
        spec.loader.exec_module(kopya)
    assert e.value.code == 0
    assert "kimlik_parcasi: False" in capsys.readouterr().out


def test_manifest_cozumlenemez_ya_da_bozuksa_ozet_yok(monkeypatch, tmp_path, caplog):
    def _patla(*a):
        raise OSError("kök bulunamadı")

    monkeypatch.setattr(md, "_manifest_onbellegi", {})
    monkeypatch.setattr(md, "resource_path", _patla)
    monkeypatch.setattr(md, "kaynak_kokunu_bul", _patla)
    with caplog.at_level(logging.DEBUG, logger=md.logger.name):
        assert md._manifest_ozetleri() == {}
    mesajlar = [r.getMessage() for r in caplog.records]
    assert (
        "model manifesti: paket yolu çözülemedi" in mesajlar and "model manifesti: kaynak kökü çözülemedi" in mesajlar
    )
    bozuk = tmp_path / md._MANIFEST_ADI
    bozuk.write_text("{bozuk", encoding="utf-8")
    monkeypatch.setattr(md, "resource_path", lambda goreli: str(bozuk))
    with caplog.at_level(logging.ERROR, logger=md.logger.name):
        assert md._manifest_ozetleri() == {}
    assert any("manifesti OKUNAMADI" in r.getMessage() for r in caplog.records)


def test_butunluk_dosya_yok_ve_ozet_okunamaz_fail_closed(tmp_path, caplog):
    assert md.butunluk_sebebi(tmp_path / "yok.bin") == "dogrulanamadi"
    agirlik = tmp_path / "model.npy"  # asgari boyut tablosunda yok → 1 B yeter
    agirlik.write_bytes(b"agirlik")
    (tmp_path / "model.npy.sha256").mkdir()  # yan özet "dosyası" okunamıyor
    with caplog.at_level(logging.ERROR, logger=md.logger.name):
        assert md.butunluk_sebebi(agirlik) == "dogrulanamadi"
    assert any("DOĞRULANAMADI" in r.getMessage() for r in caplog.records)


def test_kalici_dizin_ve_kokler_cozucu_hatasinda_da_doner(monkeypatch):
    import ctypes

    monkeypatch.setattr(ctypes, "windll", types.SimpleNamespace(), raising=False)
    dizin = md.get_persistent_model_dir()
    assert dizin.is_dir()

    def _patla(*a):
        raise OSError("çözülemedi")

    monkeypatch.setattr(md, "kaynak_kokunu_bul", _patla)
    monkeypatch.setattr(md, "resource_path", _patla)
    assert dizin in md._candidate_model_roots()


def test_yan_dosya_aramasi_patlarsa_yerel_yol_doner(monkeypatch, tmp_path):
    def _patla(goreli):
        raise RuntimeError("model kökleri okunamadı")

    monkeypatch.setattr(md, "find_installed_model", _patla)
    yerel = tmp_path / "scaler.pkl"
    assert md.yan_dosya_coz(yerel, "ai_hub/kedi/scaler.pkl") == str(yerel)
