# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.108 · B-10.12 · B-10.30 + D1.111 · B-4.9 — STM yakma ön kontrolü ("bobin sürülürken yakma" korkuluğu) DÜRÜST.

ÖLÇÜLEN KUSURLAR:
  * B-10.12 / B-4.9: `stm_yakma._json_al` HER hatayı (5xx, 404, zaman aşımı, JSON-dışı gövde, PEMF olmayan servis) `None`
    sayıyor, `seans_ve_bobin_kontrolu` da `None`'ı "backend kapalı (kimse bobin sürmüyor) — güvenli" diye okuyordu: 5xx
    veren ya da asılı bir backend bobin sürerken yakmaya izin veriliyordu. Yakma MCU'yu resetler — bobinler ANİDEN durur.
  * D1.111 orkestratör notu: backend'in KENDİ açılış yakması `server.run()`'dan ÖNCE koşar; HTTP ön kontrolü port doğru
    olsa bile ANLAMSIZ (kendine bağlanamaz → "kapalı → güvenli"; ya da o portta BAŞKA süreç cevap verir). Kontrol süreç
    içi seans/bobin durumunu okumalı. HTTP ayrımı yalnız AYRI süreçteki CLI (`scripts/stm_yak.py`) içindir ve orada yalnız
    BAĞLANTI REDDİ "kapalı" sayılır.
  * B-10.30: `if not guvenli` (DONANIM_MESGUL) dalı davranış kapısına bağlı değildi.

KAPI: (a) GERÇEK `seans_ve_bobin_kontrolu` loopback rastgele portlarda sahte sunuculara karşı: 500, 404, HTML-200, zaman
aşımı, PEMF olmayan JSON, `sessionActive` yok/None → GÜVENSİZ; bağlantı reddi → güvenli (karşıt), temiz PEMF → güvenli.
(b) GERÇEK `firmware_manager.acilis_denetimi` → GERÇEK `yakma_akisi` (sahte indirme + SAHTE yakıcı `_kos`): süreç içinde
aktif seans / STM'de sürülen bobin / canlı durumda sürülen bobin (ESP 8) / okunamayan durum → DONANIM_MESGUL, yakıcı 0
çağrı ve HTTP ön kontrolü HİÇ yapılmaz (urllib `OpenerDirector.open` kayıtçı — bağlantı reddi taklidi); temiz durumda
yedek → yak sırası. (c) `yakma_akisi(guvenlik_kontrolu=…)` (False) → DONANIM_MESGUL, yedek/yak 0 çağrı.
⚠️ Gerçek yakıcı / ST-Link / seri port ÇAĞRILMAZ (sahte `_kos`, sahte banner).
"""

from __future__ import annotations

import copy
import hashlib
import http.server
import importlib
import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest


# ──────────────────────────────────────────────────────────────────────────
# (a) CLI HTTP ön kontrolü — yalnız bağlantı reddi "kapalı"
# ──────────────────────────────────────────────────────────────────────────
class _Sunucu:
    def __init__(self, kip: str):
        self.kip = kip
        dis = self

        class _H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                saglik = self.path.startswith("/api/health")
                if dis.kip == "500":
                    self.send_response(500)
                    self.end_headers()
                    return
                if dis.kip == "404":
                    self.send_response(404)
                    self.end_headers()
                    return
                if dis.kip == "gecikme":
                    time.sleep(6.0)
                if dis.kip == "html":
                    govde, tur = b"<html><body>baska servis</body></html>", "text/html"
                elif dis.kip == "yabanci_json":
                    govde, tur = json.dumps({"status": "ok"}).encode(), "application/json"
                elif dis.kip == "oturum_none":
                    govde = json.dumps(
                        {"status": "online", "service": "PEMF-Vet", "sessionActive": None} if saglik else {"coils": []}
                    ).encode()
                    tur = "application/json"
                elif dis.kip == "pemf_bobin":
                    govde = json.dumps(
                        {"status": "online", "service": "PEMF-Vet", "sessionActive": False}
                        if saglik
                        else {"coils": [{"id": 3, "running": True}]}
                    ).encode()
                    tur = "application/json"
                else:  # pemf_temiz / gecikme
                    govde = json.dumps(
                        {"status": "online", "service": "PEMF-Vet", "sessionActive": False}
                        if saglik
                        else {"coils": [{"id": 1, "running": False}]}
                    ).encode()
                    tur = "application/json"
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", tur)
                    self.send_header("Content-Length", str(len(govde)))
                    self.end_headers()
                    self.wfile.write(govde)
                except OSError:
                    pass

            def log_message(self, *a):
                pass

        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _H)
        self.adres = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def kapat(self):
        self.srv.shutdown()
        self.srv.server_close()


#: Windows loopback'te KAPALI porta bağlanma reddi ~2 sn sonra gelir (SYN yeniden denemeleri; 1-H'de ölçüldü: 2,02–2,06 sn,
#: 3/3). Sağlık zaman aşımı bundan KISA olursa "backend kapalı" (bağlantı reddi) zaman aşımına düşer → "doğrulanamadı":
#: CLI backend kapalıyken hiç kullanılamaz (fail-closed ama işlevsiz). Ürün değeri bu asgarinin üstünde PİNLENİR.
SAGLIK_ZAMAN_ASIMI_ASGARI_S = 3.0
_URUN: dict = {}


@pytest.fixture()
def sy(monkeypatch):
    m = importlib.import_module("utils.stm_yakma")
    _URUN["saglik"] = getattr(m, "SAGLIK_ZAMAN_ASIMI_S", 5.0)
    # Zaman aşımı kolunu hızlandır (ürün varsayılanı 5/8 sn); HEAD'de sabit yoksa yine de koşar (yavaş).
    monkeypatch.setattr(m, "SAGLIK_ZAMAN_ASIMI_S", 0.5, raising=False)
    monkeypatch.setattr(m, "ANLIK_ZAMAN_ASIMI_S", 0.5, raising=False)
    return m


@pytest.mark.parametrize("kip", ["500", "404", "html", "gecikme", "yabanci_json", "oturum_none", "pemf_bobin"])
def test_KRITIK_CLI_on_kontrolu_belirsiz_yanit_GUVENLI_SAYILMAZ(sy, kip):
    s = _Sunucu(kip)
    try:
        guvenli, aciklama = sy.seans_ve_bobin_kontrolu(s.adres)
    finally:
        s.kapat()
    assert guvenli is False, (
        f"'{kip}' yanıtı veren bir süreç varken ön kontrol YAKMAYA izin verdi ({aciklama!r}) — yalnız bağlantı reddi "
        "'backend kapalı' sayılabilir (B-10.12 / B-4.9)"
    )


def test_KARSIT_CLI_baglanti_reddi_KAPALI_sayilir_ve_temiz_PEMF_guvenli(sy, monkeypatch):
    assert _URUN["saglik"] >= SAGLIK_ZAMAN_ASIMI_ASGARI_S, (
        f"sağlık zaman aşımı {_URUN['saglik']} sn < {SAGLIK_ZAMAN_ASIMI_ASGARI_S} — Windows bağlantı reddi (~2 sn) zaman "
        "aşımına düşer, 'backend kapalı' ayırt edilemez"
    )
    monkeypatch.setattr(sy, "SAGLIK_ZAMAN_ASIMI_S", _URUN["saglik"])  # bağlantı reddi ÜRÜN zaman aşımıyla ölçülür
    s = socket_bos_port()
    guvenli, aciklama = sy.seans_ve_bobin_kontrolu(f"http://127.0.0.1:{s}")
    assert guvenli is True and "kapal" in aciklama.lower(), aciklama
    t = _Sunucu("pemf_temiz")
    try:
        guvenli, aciklama = sy.seans_ve_bobin_kontrolu(t.adres)
    finally:
        t.kapat()
    assert guvenli is True, aciklama


def socket_bos_port() -> int:
    import socket

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()  # kapalı port → bağlantı reddi
    return p


# ──────────────────────────────────────────────────────────────────────────
# (b) Backend'in KENDİ yakma kararı — süreç içi durum, HTTP YOK
# ──────────────────────────────────────────────────────────────────────────
class _Hc:
    def __init__(self, calisan=None, firlat=False):
        self._c, self._f = calisan or {}, firlat

    def calisan_bobin_durumu(self):
        if self._f:
            raise RuntimeError("durum kilidi okunamadi")
        return dict(self._c)


@pytest.fixture()
def zincir(monkeypatch, tmp_path):
    """GERÇEK acilis_denetimi → GERÇEK _firmware_uygula → GERÇEK yakma_akisi; indirme ve yakıcı SAHTE."""
    from servers import api_server as api
    from servers import live_state as ls

    fm = importlib.import_module("servers.firmware_manager")
    importlib.reload(fm)
    sy = importlib.import_module("utils.stm_yakma")
    ikili = tmp_path / "pemf_fw.bin"
    ikili.write_bytes(b"PEMF-FW-2.4" * 64)
    ozet = hashlib.sha256(ikili.read_bytes()).hexdigest()
    manifest = {
        "firmware": {
            "stm32": {"version": "2.4", "url": "https://github.com/mert61-python/pemf-update/x", "sha256": ozet}
        },
        "uyumluluk": [{"clientMin": "", "firmwareMin": "2.4"}],
    }
    monkeypatch.setattr(fm, "manifest_oku", lambda **_k: manifest)
    monkeypatch.setattr(fm.um, "get_current_version", lambda: "1.9.51")
    monkeypatch.setattr(fm.um, "get_status", lambda: {"previousStable": None})
    monkeypatch.setattr(fm, "firmware_indir", lambda url, sha: (ikili, ""))
    kos: list[list[str]] = []

    def _sahte_kos(cli, argumanlar, timeout=300.0):
        kos.append(list(argumanlar))
        if "-r" in argumanlar:
            Path(argumanlar[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(argumanlar[-1]).write_bytes(b"ESKI-FW")
        return 0, "sahte yakici"

    monkeypatch.setattr(sy, "programmer_cli", lambda: Path("sahte_cli.exe"))
    monkeypatch.setattr(sy, "_kos", _sahte_kos)
    monkeypatch.setattr(sy, "banner_dogrula", lambda *a, **k: (True, "uyumlu", "-> STM_READY: DDS v2.4 (7-ch ...)"))
    monkeypatch.setattr(sy.time, "sleep", lambda _s: None)
    http_cagri: list[str] = []

    def _http(self, fullurl, *a, **k):
        http_cagri.append(fullurl if isinstance(fullurl, str) else fullurl.full_url)
        raise urllib.error.URLError(ConnectionRefusedError(10061, "kimse dinlemiyor (kapı taklidi)"))

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", _http)
    monkeypatch.setitem(api._active_session, "is_active", False)
    monkeypatch.setattr(api.state, "hardware", _Hc())
    with ls._live_state_lock:
        eski_bobin = copy.deepcopy(ls._live_state["coils"])
        eski_tedavi = copy.deepcopy(ls._live_state["activeTreatment"])
        for c in ls._live_state["coils"].values():
            c["running"] = False
        ls._live_state["activeTreatment"]["isActive"] = False
    try:
        yield {"fm": fm, "sy": sy, "api": api, "ls": ls, "kos": kos, "http": http_cagri}
    finally:
        with ls._live_state_lock:
            ls._live_state["coils"].clear()
            ls._live_state["coils"].update(eski_bobin)
            ls._live_state["activeTreatment"].clear()
            ls._live_state["activeTreatment"].update(eski_tedavi)


def _kur_durum(z, monkeypatch, durum: str):
    if durum == "seans":
        monkeypatch.setitem(z["api"]._active_session, "is_active", True)
    elif durum == "stm_bobin":
        monkeypatch.setattr(z["api"].state, "hardware", _Hc({3: {"freq": 100.0, "duty": 0.4, "phase": 0.0}}))
    elif durum == "canli_esp_bobin":
        with z["ls"]._live_state_lock:
            z["ls"]._live_state["coils"][7]["running"] = True
    elif durum == "okunamaz":
        monkeypatch.setattr(z["api"].state, "hardware", _Hc(firlat=True))


@pytest.mark.parametrize("durum", ["seans", "stm_bobin", "canli_esp_bobin", "okunamaz"])
def test_KRITIK_backendin_kendi_yakmasi_SUREC_ICI_durumu_okur_ve_YAKMAZ(zincir, monkeypatch, durum):
    z = zincir
    _kur_durum(z, monkeypatch, durum)
    d = z["fm"].acilis_denetimi(firmware_surum="2.3.0", stm_bagli=True, uygula=True)
    assert d["eylem"] == "firmware_guncelle", f"aparat: plan yakmayı gerektirmedi: {d}"
    assert z["kos"] == [], (
        f"süreç içinde '{durum}' varken yakıcı ÇAĞRILDI: {z['kos']} — HTTP ön kontrolü (bağlantı reddi → 'kapalı') "
        "kendi sürecinin bobinlerini göremez (D1.108 + D1.111)"
    )
    assert d["uygulandi"] is False and f"[{z['sy'].DONANIM_MESGUL}]" in d["hata"], d
    assert z["http"] == [], f"backend'in kendi yakma kararı HTTP sordu: {z['http']} (süreç içi durum okunmalı)"


def test_KARSIT_backendin_kendi_yakmasi_temiz_durumda_YEDEK_sonra_YAK(zincir):
    z = zincir
    d = z["fm"].acilis_denetimi(firmware_surum="2.3.0", stm_bagli=True, uygula=True)
    sira = ["-r" if "-r" in a else "-w" if "-w" in a else "?" for a in z["kos"]]
    assert sira == ["-r", "-w"], f"temiz durumda yedek → yak sırası beklenirdi: {z['kos']}"
    assert d["uygulandi"] is True, d
    assert z["http"] == [], z["http"]


# ──────────────────────────────────────────────────────────────────────────
# (c) DONANIM_MESGUL dalı — davranış
# ──────────────────────────────────────────────────────────────────────────
def test_KRITIK_guvenlik_kontrolu_REDDEDERSE_yedek_ve_yak_YOK(zincir, tmp_path):
    z = zincir
    ikili = tmp_path / "d.bin"
    ikili.write_bytes(b"X" * 32)
    s = z["sy"].yakma_akisi(
        ikili, guvenlik_kontrolu=lambda: (False, "test: bobin suruluyor"), yedek_dizin=tmp_path / "y"
    )
    assert s.kod == z["sy"].DONANIM_MESGUL, s
    assert z["kos"] == [], f"ön kontrol reddederken yakıcı çağrıldı: {z['kos']}"


def test_KRITIK_guvenlik_kontrolu_ISTISNA_firlatirsa_YAKILMAZ(zincir, tmp_path):
    """İkinci katman: kontrolün KENDİSİ fırlatırsa (süreç içi kontrol istisnayı kendi yakalar — bu kol onsuz ölçer)
    doğrulanamayan durumda yakılmaz (fail-closed)."""
    z = zincir
    ikili = tmp_path / "e.bin"
    ikili.write_bytes(b"X" * 32)

    def _firlatan():
        raise RuntimeError("durum okunamadi")

    s = z["sy"].yakma_akisi(ikili, guvenlik_kontrolu=_firlatan, yedek_dizin=tmp_path / "y")
    assert s.kod == z["sy"].DONANIM_MESGUL, s
    assert z["kos"] == [], f"kontrol fırlatırken yakıcı çağrıldı: {z['kos']}"
