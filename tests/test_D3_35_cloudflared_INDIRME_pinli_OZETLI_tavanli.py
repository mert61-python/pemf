# Author: mertaygn, cglrgrkn
"""D3.35 (B-4.13 · B-4.14) — cloudflared İNDİRME kolu: sürüm-pinli, boyut tavanlı, SHA-256 özetli; önbellek özetle doğrulanır; macOS
arşivi BİR KEZ açılır. (B-4.12 paket önceliği 18K K6'da kapandı: `test_18K_K6_cloudflared_PAKETTEKI_oncelikli.py`.)

ÖLÇÜLEN (HEAD): `releases/latest` URL'si (sürüm belirsiz); `response.read()` boyutsuz; özeti tutmayan ≥ 5 MB gövde `bin_path`'e yerleşip
DÖNÜYOR (start_tunnel onu Popen eder); ≥ 5 MB her önbellek dosyası (eski pinsiz indirme) doğrulamasız kullanılıyor; Darwin + geçerli
.tgz → çıkarılan ikili ikinci kez `tarfile.open` ile açılıyor → None. Özeti bilinmeyen varlık (Linux) yine iniyordu.

Sahte EN ALT katta: `urllib.request.urlopen` (ağ YOK — çağrılan URL kaydedilir) ve `subprocess.Popen` (süreç YOK — komut kaydedilir).
Platform `platform.system` / `platform.machine` ile seçilir; önbellek dizini geçici.
"""

from __future__ import annotations

import hashlib
import io
import os
import platform
import tarfile
import urllib.request

import pytest

MB6 = 6_000_000


class _Yanit:
    def __init__(self, govde: bytes = b"", sonsuz: bool = False):
        self._g = govde
        self._i = 0
        self.sonsuz = sonsuz
        self.boyutlar: list = []

    def read(self, n=None):
        self.boyutlar.append(n)
        if self.sonsuz:
            return b"x" * (n or 1 << 16)
        if n is None:
            r = self._g[self._i :]
        else:
            r = self._g[self._i : self._i + n]
        self._i += len(r)
        return r

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def tm(monkeypatch, tmp_path):
    from servers import tunnel_manager as tm

    tm._urller = []
    tm._popen = []
    tm._yanit = None

    def _urlopen(url, *a, **k):
        tm._urller.append(str(url))
        if tm._yanit is None:
            raise AssertionError("D3.35: beklenmeyen indirme (ağ YOK)")
        return tm._yanit

    def _popen(cmd, *a, **k):
        tm._popen.append([str(x) for x in cmd])
        raise OSError("D3.35 sahte Popen: süreç başlatılmaz")

    monkeypatch.setattr(urllib.request, "urlopen", _urlopen)
    monkeypatch.setattr(tm.subprocess, "Popen", _popen)
    monkeypatch.setattr(tm, "_BIN_DIR", tmp_path / "onbellek")
    monkeypatch.setattr(tm, "_bundled_cloudflared", lambda: None)
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    monkeypatch.setattr(platform, "machine", lambda: "AMD64")
    import utils.secrets_manager as sm

    monkeypatch.setattr(sm, "get_secret", lambda *a, **k: "")
    return tm


def _ozet(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _pinle(monkeypatch, tm, varlik: str, govde: bytes):
    monkeypatch.setattr(tm, "_CLOUDFLARED_OZET", {varlik: _ozet(govde)}, raising=False)


def test_KRITIK_B_4_13_OZETI_tutmayan_govde_YERLESMEZ_ve_CALISTIRILMAZ(tm, tmp_path):
    tm._yanit = _Yanit(b"A" * MB6)  # boyut eşiğini geçer, özeti pinli Windows özetiyle UYUŞMAZ
    assert tm.start_tunnel(port=48999) is False
    assert tm._popen == [], f"özeti doğrulanmamış ikili Popen edildi: {tm._popen}"
    assert not (tmp_path / "onbellek" / "cloudflared.exe").exists(), "özeti tutmayan gövde önbelleğe yerleşti"
    kalan = list((tmp_path / "onbellek").glob("*")) if (tmp_path / "onbellek").exists() else []
    assert kalan == [], f"geçici dosya kaldı: {kalan}"


def test_KRITIK_B_4_13_indirme_SURUM_PINLI_latest_DEGIL(tm, monkeypatch):
    govde = os.urandom(64) * (MB6 // 64)
    _pinle(monkeypatch, tm, "cloudflared-windows-amd64.exe", govde)
    tm._yanit = _Yanit(govde)
    yol = tm._download_cloudflared()
    assert tm._urller, "indirme denenmedi"
    assert "/releases/latest/" not in tm._urller[0], f"sürüm pinsiz: {tm._urller[0]}"
    assert "/releases/download/2026.6.1/cloudflared-windows-amd64.exe" in tm._urller[0], tm._urller[0]
    assert yol is not None and yol.read_bytes() == govde


def test_KRITIK_B_4_13_okuma_BOYUTLU_ve_TAVANLI(tm, monkeypatch):
    monkeypatch.setattr(tm, "_AZAMI_INDIRME", 64 * 1024, raising=False)
    monkeypatch.setattr(tm, "_PARCA", 4096, raising=False)
    tm._yanit = _Yanit(sonsuz=True)
    assert tm._download_cloudflared() is None
    assert None not in tm._yanit.boyutlar, "response.read() BOYUTSUZ çağrıldı (gövde belleğe sınırsız okunur)"
    assert len(tm._yanit.boyutlar) <= 64 * 1024 // 4096 + 2, (
        f"tavan aşıldıktan sonra okuma sürdü: {len(tm._yanit.boyutlar)}"
    )


def test_KRITIK_B_4_13_eski_PINSIZ_onbellek_KULLANILMAZ_dogrulanmis_indirmeyle_degisir(tm, monkeypatch, tmp_path):
    d = tmp_path / "onbellek"
    d.mkdir()
    (d / "cloudflared.exe").write_bytes(b"E" * MB6)  # eski sürümün pinsiz / özetsiz indirdiği ikili (≥ 5 MB)
    govde = os.urandom(64) * (MB6 // 64)
    _pinle(monkeypatch, tm, "cloudflared-windows-amd64.exe", govde)
    tm._yanit = _Yanit(govde)
    yol = tm._download_cloudflared()
    assert tm._urller, "doğrulanmamış önbellek indirmesiz kullanıldı"
    assert yol is not None and yol.read_bytes() == govde


def test_KRITIK_B_4_13_ozeti_BILINMEYEN_varlik_INDIRILMEZ(tm, monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    tm._yanit = _Yanit(b"L" * MB6)
    assert tm._download_cloudflared() is None
    assert tm._urller == [], f"özeti bilinmeyen varlık indirildi: {tm._urller}"


def _tgz(icerik: bytes) -> bytes:
    tamp = io.BytesIO()
    with tarfile.open(fileobj=tamp, mode="w:gz") as t:
        bilgi = tarfile.TarInfo("cloudflared")
        bilgi.size = len(icerik)
        bilgi.mode = 0o755
        t.addfile(bilgi, io.BytesIO(icerik))
    return tamp.getvalue()


def test_KRITIK_B_4_14_Darwin_gecerli_tgz_CIKARILMIS_ikili_doner_ve_bir_kez_acilir(tm, monkeypatch, tmp_path):
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    monkeypatch.setattr(platform, "machine", lambda: "arm64")
    ikili = os.urandom(MB6)  # sıkışmaz: arşiv de ≥ 5 MB
    arsiv = _tgz(ikili)
    _pinle(monkeypatch, tm, "cloudflared-darwin-arm64.tgz", arsiv)
    tm._yanit = _Yanit(arsiv)
    yol = tm._download_cloudflared()
    assert yol is not None, "geçerli .tgz ile çıkarılmış ikili dönmedi (arşiv ikinci kez açılmaya çalışıldı)"
    assert yol == tmp_path / "onbellek" / "cloudflared-darwin" and yol.read_bytes() == ikili
    assert "/releases/download/2026.6.1/cloudflared-darwin-arm64.tgz" in tm._urller[0], tm._urller
    tm._yanit = None  # ikinci çağrı: önbellek (çıkarılmış ikilinin özeti) → İNDİRME / AÇMA YOK
    assert tm._download_cloudflared() == yol
    assert len(tm._urller) == 1


def test_KARSIT_D3_35_ozeti_DOGRULANMIS_onbellek_indirmesiz_kullanilir(tm, monkeypatch, tmp_path):
    d = tmp_path / "onbellek"
    d.mkdir()
    govde = b"G" * MB6
    (d / "cloudflared.exe").write_bytes(govde)
    _pinle(monkeypatch, tm, "cloudflared-windows-amd64.exe", govde)
    assert tm.start_tunnel(port=48999) is False  # sahte Popen düşürdü
    assert tm._urller == []
    assert tm._popen and tm._popen[0][0] == str(d / "cloudflared.exe"), tm._popen


def test_KARSIT_D3_35_pinli_Windows_ozeti_PAKETLI_ikiliyle_ayni():
    """Pin, 18K K6'nın ölçtüğü paketli ikilinin özeti (54 166 424 B, `main.Version=2026.6.1`)."""
    from servers import tunnel_manager as tm

    assert tm._CLOUDFLARED_SURUM == "2026.6.1"
    assert tm._CLOUDFLARED_OZET["cloudflared-windows-amd64.exe"] == (
        "5253e66f1f493c4e13539749f1aa86fd0c61e3072900fec29a44ba046a6d97e2"
    )
