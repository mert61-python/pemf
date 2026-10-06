# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.110 · B-4.1 · B-4.5 — oto-firmware indirmesi URL pinini GERÇEKTEN uygular; kaynak pini Rust ikiziyle AYNI; yönlendirme
hedefi de doğrulanır.

ÖLÇÜLEN KUSURLAR:
  * B-4.1: `firmware_manager.firmware_indir` `um._validate_installer_url(url)`'yi İFADE-DEYİMİ olarak çağırıyordu — fonksiyon
    istisna fırlatmaz, `(ok, hata)` DÖNER; dönüş atılıyordu → `http://…`, yabancı host ve `../` atlatması dahil HER URL
    `urlopen`'a ulaşıyordu (özet de aynı manifestten geldiği için eşleşir). Manifest ele geçerse herhangi bir sunucudaki
    ikili, bobinleri süren STM'e yakılırdı.
  * B-4.5: Python pini kaynak olarak `raw.githubusercontent.com/<herhangi-sahip>/…`, `codeload.github.com/<herhangi-sahip>/…`
    ve joker sonekle `gist.`/`user-images.githubusercontent.com`'u kabul ediyordu (ücretsiz bir GitHub hesabı oraya keyfi
    bayt koyar). Rust ikizi (`launcher/core/src/net.rs::validate_download_source`) bunları KAYNAK olarak reddeder: kaynak ya
    beklenen depo yoluna pinli `github.com` ya da açıkça sayılmış OPAK nesne depoları; joker yalnız YÖNLENDİRME hedefinde.
  * Yönlendirme: `urlopen` yönlendirmeleri sessizce izliyordu (`http://` ya da yabancı host dahil) — kaynak pini atlatılabilirdi.

KAPI: (1) GERÇEK `firmware_indir` reddedilen URL'lerde ağa HİÇ çıkmaz (urllib `OpenerDirector.open` kayıtçı) ve
"reddedildi" der; (2) `_validate_installer_url` raw/codeload/gist/user-images kaynaklarını reddeder (beklenen depo + nesne
depoları kabul); (3) yönlendirme hedefi her adımda doğrulanır — GERÇEK urllib + iki loopback sunucu: `http://` hedefe
yönlendirme izlenmez, hedef sunucu istek ALMAZ; (4) `firmware_indir` pinli açıcıyı kullanır (yönlendirme denetimi atlanmaz).
"""

from __future__ import annotations

import hashlib
import http.server
import importlib
import io
import threading
import urllib.error
import urllib.request

import pytest

GECERLI = "https://github.com/mert61-python/pemf-update/releases/download/fw-2.4/pemf_fw.bin"

REDDEDILEN = [
    "http://evil.example/fw.bin",  # HTTPS değil
    "https://evil.example/fw.bin",  # yabancı host
    "https://github.com/mert61-python/pemf-update/../../saldirgan/kotu/fw.bin",  # nokta-segmenti pin atlatma
    "https://github.com/saldirgan/kotu/releases/download/x/fw.bin",  # yabancı depo
    "https://raw.githubusercontent.com/saldirgan/kotu/main/fw.bin",  # raw — herhangi sahip
    "https://raw.githubusercontent.com/mert61-python/pemf-update/main/fw.bin",  # raw — kaynak sürüm varlığı OLMALI (Rust ikizi)
    "https://codeload.github.com/saldirgan/kotu/zip/main",  # codeload — herhangi sahip
    "https://gist.githubusercontent.com/x/y/raw/fw.bin",  # joker sonek
    "https://user-images.githubusercontent.com/1/fw.bin",  # joker sonek
    "https://evil.example@github.com/mert61-python/pemf-update/releases/download/x/fw.bin",  # userinfo
]


@pytest.fixture()
def fm(monkeypatch):
    m = importlib.import_module("servers.firmware_manager")
    importlib.reload(m)
    return m


@pytest.fixture()
def ag_kaydi(monkeypatch):
    """urllib'in TÜM açıcıları `OpenerDirector.open`'dan geçer (`urlopen` dahil) — çağrı = ağa çıkma girişimi."""
    cagri: list[str] = []

    def _kayitci(self, fullurl, *a, **k):
        cagri.append(fullurl if isinstance(fullurl, str) else fullurl.full_url)
        raise urllib.error.URLError("D1.110 kapisi: ag YOK")

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", _kayitci)
    return cagri


@pytest.mark.parametrize("url", REDDEDILEN)
def test_KRITIK_reddedilen_URL_AGA_CIKMAZ_ve_REDDEDILDI_der(fm, ag_kaydi, url):
    yol, hata = fm.firmware_indir(url, "ab" * 32)
    assert yol is None, f"reddedilmesi gereken firmware URL'si için dosya döndü: {url}"
    assert not ag_kaydi, (
        f"firmware URL pini UYGULANMADI — reddedilmesi gereken URL ağa gitti: {ag_kaydi} (B-4.1: doğrulama dönüşü atılıyor)"
    )
    assert "reddedildi" in hata, f"hata nedeni pini söylemiyor: {hata!r}"


@pytest.mark.parametrize("url", REDDEDILEN[4:])
def test_KRITIK_kaynak_pini_RUST_IKIZI_gibi_DAR(url):
    from servers.update_manager import _validate_installer_url

    ok, hata = _validate_installer_url(url)
    assert ok is False, f"kaynak pini GENİŞ — {url} kabul edildi (Rust validate_download_source reddeder)"
    assert "güvenlik" in hata.lower(), hata


@pytest.mark.parametrize(
    "url",
    [
        GECERLI,
        "https://objects.githubusercontent.com/github-production-release-asset/1/2?x=y",
        "https://release-assets.githubusercontent.com/a/b.bin",
    ],
)
def test_KARSIT_mesru_kaynaklar_KABUL(url):
    from servers.update_manager import _validate_installer_url

    ok, hata = _validate_installer_url(url)
    assert ok is True, f"meşru kaynak reddedildi ({hata}): {url}"


class _Sunucu:
    """Loopback'te tek amaçlı HTTP sunucu; gelen yolları kaydeder."""

    def __init__(self, yonlendir: str | None = None):
        self.istekler: list[str] = []
        dis = self

        class _H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                dis.istekler.append(self.path)
                if yonlendir:
                    self.send_response(302)
                    self.send_header("Location", yonlendir)
                    self.end_headers()
                else:
                    self.send_response(200)
                    self.send_header("Content-Length", "4")
                    self.end_headers()
                    self.wfile.write(b"EVIL")

            def log_message(self, *a):
                pass

        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _H)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def kapat(self):
        self.srv.shutdown()
        self.srv.server_close()


def test_KRITIK_yonlendirme_hedefi_DOGRULANIR_http_hedef_IZLENMEZ():
    """GERÇEK urllib: A → 302 → B (`http://`). Pinli açıcı yönlendirmeyi izlememeli; B hiç istek almamalı."""
    from servers import update_manager as um

    b = _Sunucu()
    a = _Sunucu(yonlendir=f"http://127.0.0.1:{b.port}/kotu.bin")
    try:
        with pytest.raises((urllib.error.HTTPError, urllib.error.URLError)):
            with um._pinli_ac(f"http://127.0.0.1:{a.port}/fw.bin", timeout=5) as r:
                r.read()
        assert a.istekler == ["/fw.bin"], a.istekler
        assert b.istekler == [], f"yönlendirme hedefi DOĞRULANMADAN izlendi: {b.istekler}"
    finally:
        a.kapat()
        b.kapat()


@pytest.mark.parametrize(
    "hedef,kabul",
    [
        ("http://objects.githubusercontent.com/x", False),
        ("https://evil.example/x", False),
        ("https://evil.example@objects.githubusercontent.com/x", False),
        ("https://objects.githubusercontent.com/x/y", True),
        ("https://release-assets.githubusercontent.com/a", True),
        ("https://github.com/mert61-python/pemf-update/releases/download/a/b", True),
    ],
)
def test_yonlendirme_kurali_RUST_validate_url_ikizi(hedef, kabul):
    from servers import update_manager as um

    ok, _ = um._yonlendirme_hedefi_dogrula(hedef)
    assert ok is kabul, hedef


@pytest.mark.parametrize("yol", ["apply_update", "rollback"])
def test_KRITIK_eski_kanal_indirmeleri_de_PINLI_acicidan(monkeypatch, yol):
    """Eski EXE kanalının (varsayılan KAPALI; `PEMF_LEGACY_EXE_UPDATE=1` ile açılır) installer indirmeleri de aynı
    yönlendirme denetimli açıcıdan geçer — indirme zinciri TEK (firmware_manager başlığı)."""
    from servers import update_manager as um

    url = "https://github.com/mert61-python/pemf-update/releases/download/exe-v9.9.9/PEMF_Setup.exe"
    monkeypatch.setenv("PEMF_LEGACY_EXE_UPDATE", "1")
    monkeypatch.setattr(um, "_has_active_treatment", lambda: False)
    monkeypatch.setattr(
        um,
        "_status",
        {
            "checked": True,
            "available": True,
            "currentVersion": "1.0.0",
            "latestVersion": "9.9.9",
            "installerUrl": url,
            "sha256": "ab" * 32,
            "previousStable": {"version": "0.9.0", "installerUrl": url, "sha256": "ab" * 32},
            "error": "",
        },
    )
    monkeypatch.setattr(um, "_applying", False)
    monkeypatch.setattr(um, "_applying_since", None)
    kayit: list[str] = []

    def _sahte_pinli(u, timeout, headers=None):
        kayit.append(u)
        raise urllib.error.URLError("D1.110 kapisi: ag YOK")

    monkeypatch.setattr(um, "_pinli_ac", _sahte_pinli)
    monkeypatch.setattr(
        urllib.request.OpenerDirector, "open", lambda self, *a, **k: pytest.fail("pinsiz açıcı kullanıldı")
    )
    sonuc = getattr(um, yol)()
    assert kayit == [url], f"{yol} installer indirmesi pinli açıcıyı KULLANMADI: {kayit} · {sonuc}"
    assert sonuc.get("ok") is False


def test_KRITIK_firmware_indir_PINLI_aciciyi_kullanir(fm, monkeypatch, tmp_path):
    """Geçerli kaynak: indirme `um._pinli_ac` üzerinden (yönlendirme denetimi atlanmaz); özet tutar → dosya döner."""
    govde = b"PEMF-FW-2.4"
    kayit: list[str] = []

    class _Yanit(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            self.close()

    def _sahte_pinli(url, timeout, headers=None):
        kayit.append(url)
        return _Yanit(govde)

    monkeypatch.setattr(fm.um, "_pinli_ac", _sahte_pinli)
    monkeypatch.setattr(fm.um, "_private_temp_path", lambda ad: tmp_path / "pemf_upd_test" / ad)
    (tmp_path / "pemf_upd_test").mkdir()
    yol, hata = fm.firmware_indir(GECERLI, hashlib.sha256(govde).hexdigest())
    assert kayit == [GECERLI], f"firmware indirmesi pinli açıcıyı KULLANMADI (yönlendirme denetimsiz): {kayit}"
    assert yol is not None and hata == "", hata
