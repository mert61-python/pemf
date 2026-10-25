# -*- coding: utf-8 -*-
"""18K K6 · D3.35 (B-4.12) — uzaktan erişim tüneli PAKETTEKİ cloudflared ikilisini ÖNCE kullanır.

ÖLÇÜLDÜ (18K, 2026-10-22): yayın derlemesinde `cloudflared.exe` PAKETTE (`_internal/bin/cloudflared/`; son derleme çıktısı ve bu makinenin
kurulu runtime'ı — boyut / SHA-256 raporda). Ama `start_tunnel` önce `%APPDATA%\\PEMF_GUI\\cloudflared\\` önbelleğine bakıyor ve dosya
VARSA (0 bayt / bozuk / eski sürümlerin sürüm-pinsiz, özetsiz indirdiği ikili) doğrulamadan çalıştırıyordu; paketli ikili yalnız önbellek
yokken deneniyordu. Artık tek yol `_download_cloudflared`: paket → boyutu ve SHA-256'sı doğrulanmış önbellek (D3.35) → indirme
(paketli yayında ULAŞILMAZ).

Sahte EN ALT katta: `subprocess.Popen` komutu kaydedip hata fırlatır (süreç başlamaz), `urllib.request.urlopen` çağrılırsa kapı düşer
(ağ YOK). Paket kökü `sys._MEIPASS` (frozen) ile geçici dizinde kurulur.
"""

from __future__ import annotations

import platform
import sys
import urllib.request

import pytest

_AD = (
    "cloudflared.exe"
    if platform.system() == "Windows"
    else ("cloudflared-darwin" if platform.system() == "Darwin" else "cloudflared-linux")
)


@pytest.fixture
def tm(monkeypatch, tmp_path):
    from servers import tunnel_manager as tm

    cagrilar: list[list[str]] = []

    def _popen(cmd, *a, **k):
        cagrilar.append([str(x) for x in cmd])
        raise OSError("18K-K6 sahte Popen: süreç başlatılmaz")

    def _ag(*a, **k):
        raise AssertionError("18K-K6: cloudflared İNDİRİLMEYE çalışıldı (ağ YOK)")

    monkeypatch.setattr(tm.subprocess, "Popen", _popen)
    monkeypatch.setattr(urllib.request, "urlopen", _ag)
    monkeypatch.setattr(tm, "_BIN_DIR", tmp_path / "onbellek")
    import utils.secrets_manager as sm

    monkeypatch.setattr(sm, "get_secret", lambda *a, **k: "")
    tm._cagrilar = cagrilar
    return tm


def _paket(monkeypatch, tmp_path):
    mei = tmp_path / "meipass"
    (mei / "bin" / "cloudflared").mkdir(parents=True)
    paketli = mei / "bin" / "cloudflared" / _AD
    paketli.write_bytes(b"PAKETLI" * 10)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(mei), raising=False)
    return paketli


def _onbellek(tmp_path, boyut: int):
    d = tmp_path / "onbellek"
    d.mkdir(parents=True, exist_ok=True)
    p = d / _AD
    with open(p, "wb") as f:
        f.truncate(boyut)
    return p


@pytest.mark.parametrize("boyut", [0, 5_000_001], ids=["bozuk_0_bayt", "eski_indirilmis"])
def test_KRITIK_18K_K6_onbellek_VARKEN_PAKETTEKI_ikili_calistirilir(tm, monkeypatch, tmp_path, boyut):
    paketli = _paket(monkeypatch, tmp_path)
    _onbellek(tmp_path, boyut)
    assert tm.start_tunnel(port=48999) is False  # sahte Popen düşürdü — süreç YOK
    print("K6OLC|", boyut, tm._cagrilar)
    assert tm._cagrilar and tm._cagrilar[0][0] == str(paketli), (
        f"önbellekteki ({boyut} bayt) ikili paketli ikilinin ÖNÜNE geçti: {tm._cagrilar}"
    )


def test_18K_K6_KARSIT_paket_YOKSA_gecerli_onbellek_indirmeden_kullanilir(tm, monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(tm, "_bundled_cloudflared", lambda: None)
    onbellek = _onbellek(tmp_path, 5_000_001)
    # D3.35 (B-4.13): geçerli önbellek = boyut eşiğini geçen VE pinli özeti tutan dosya (arşiv varlığında doğrulanmış kurulumun eki).
    import hashlib

    varlik, _ = tm._varlik_adi()
    ozet = hashlib.sha256(onbellek.read_bytes()).hexdigest()
    monkeypatch.setattr(tm, "_CLOUDFLARED_OZET", {varlik: ozet})
    if varlik.endswith(".tgz"):
        tm._ozet_eki(onbellek).write_text(ozet, encoding="ascii")
    assert tm.start_tunnel(port=48999) is False
    assert tm._cagrilar and tm._cagrilar[0][0] == str(onbellek), tm._cagrilar


def test_18K_K6_KARSIT_paketli_ikili_ONBELLEKSIZ_de_indirmesiz(tm, monkeypatch, tmp_path):
    paketli = _paket(monkeypatch, tmp_path)
    assert tm.start_tunnel(port=48999) is False
    assert tm._cagrilar and tm._cagrilar[0][0] == str(paketli), tm._cagrilar
