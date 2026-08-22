# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""DNS-REBINDING KORUMASI FIILEN DEVREDE OLMALI (eksik-taramasi P2, 2026-08-22).

OLCULEN DURUM: `PEMF_ALLOWED_HOSTS` altyapisi vardi (TrustedHost) ama varsayilani "*" ve HICBIR
dagitim profili/launcher onu ayarlamiyordu → koruma hicbir kurulumda aktif degildi. Kotucul bir
sayfa, kurban tarayicisini kendi alan adini klinik IP'sine rebind ederek LAN-muaf API'ye
same-origin gibi ulasabilir.

NEDEN STATIK LISTE COZUM DEGIL: mesru istemciler klinigin O ANKI LAN IP'siyle baglanir
(telefon → http://192.168.1.35:8000); IP kurulumdan kuruluma degisir ve TrustedHost joker-IP
bilmez. Statik liste ya IP'yi disarida birakip MOBILI KIRAR ya da "*" kalir.

COZUM — "auto" MODU: rebinding SALDIRISININ Host basligi HER ZAMAN saldirganin ALAN ADIdir
(tarayici Host'a çözdüğü adı yazar). Mesru istemcilerin Host'lari ise sayilabilir bir sinif:
IP-literal (v4/v6), localhost, *.local (mDNS), makinenin kendi adi, tunel alanlari. "auto" bu
sinifi serbest birakir, YABANCI DNS ADLARINI 400 ile reddeder.

SOZLESME:
  · Varsayilan "*" KALIR (kutuphane davranisi degismez — sessiz davranis degisikligi yok);
    korumayi DAGITIM profilleri + launcher acar (PEMF_ALLOWED_HOSTS=auto).
  · "auto,ek1.example.com" bicimiyle kurulum-ozel ek adlar tanimlanabilir (cikis kapisi:
    kurumsal intranet FQDN'i olan klinik icin).
  · Acik liste verilirse eski TrustedHost davranisi aynen korunur.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_KOK = Path(__file__).resolve().parents[1]


@pytest.fixture()
def api():
    import servers.api_server as api

    return api


# ── 1) Host siniflandirmasi ──────────────────────────────────────────────────────


def test_KRITIK_yabanci_alan_adi_REDDEDILIR(api):
    assert api._host_izinli("attacker.example.com", ()) is False, (
        "rebinding vektoru (yabanci DNS adi) kabul ediliyor — koruma islevsiz"
    )
    assert api._host_izinli("evil-rebind.io", ()) is False


def test_KRITIK_mesru_istemci_hostlari_SERBEST(api, monkeypatch):
    monkeypatch.setattr(api._socket, "gethostname", lambda: "KLINIK-PC")
    for host in (
        "192.168.1.35",  # telefonun LAN erisimi
        "10.0.0.7",
        "192.168.137.1",  # hotspot
        "[::1]",
        "127.0.0.1",
        "localhost",
        "pemf.local",  # mDNS
        "klinik-pc",  # makinenin kendi adi (buyuk/kucuk duyarsiz)
        "abcd-efgh.trycloudflare.com",  # quick tunnel
    ):
        assert api._host_izinli(host, ()) is True, f"mesru host reddedildi: {host} (kurulum kirilir)"


def test_KRITIK_ek_adlar_cikis_kapisi(api):
    assert api._host_izinli("klinik.sirket.com", ("klinik.sirket.com",)) is True
    assert api._host_izinli("baska.sirket.com", ("klinik.sirket.com",)) is False


def test_KARSIT_KANIT_bos_host_fail_open(api):
    """HTTP/1.0 istekleri Host tasimayabilir; tibbi cihazda bos Host yuzunden calismamak yanlis
    yonde hata olur (rebinding bos Host ile YAPILAMAZ — tarayici hep Host yazar)."""
    assert api._host_izinli("", ()) is True


# ── 2) Middleware davranisi (saf ASGI — TestClient'in kendi Host'una bagimli degil) ──


@pytest.mark.anyio
async def test_KRITIK_middleware_yabanci_hostu_400_ile_keser(api):
    async def ic_uygulama(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    mw = api._RebindKorumaMiddleware(ic_uygulama, ekstra=())
    durumlar: list = []

    async def alici():
        return {"type": "http.request"}

    async def gonderici(msg):
        if msg["type"] == "http.response.start":
            durumlar.append(msg["status"])

    scope = {"type": "http", "headers": [(b"host", b"attacker.example.com")]}
    await mw(scope, alici, gonderici)
    assert durumlar == [400], f"yabanci Host kesilmedi: {durumlar}"

    durumlar.clear()
    scope = {"type": "http", "headers": [(b"host", b"192.168.1.35:8000")]}
    await mw(scope, alici, gonderici)
    assert durumlar == [200], f"mesru IP Host'u kesildi: {durumlar}"


# ── 3) Dagitim kablolamasi: profiller korumayi ACAR ──────────────────────────────


def test_KRITIK_dagitim_profilleri_korumayi_ACIYOR():
    """Altyapinin varligi yetmez (2026-08-04'ten beri vardi ve hicbir kurulumda calismiyordu) —
    profiller acmali. Varsayilan '*' kutuphane duzeyinde korunur (dev/testler etkilenmez)."""
    for ad in ("device.env", "server.env", "staging.env"):
        metin = (_KOK / "deploy" / ad).read_text(encoding="utf-8", errors="replace")
        satirlar = [
            s.strip()
            for s in metin.splitlines()
            if s.strip().startswith("PEMF_ALLOWED_HOSTS=") and not s.strip().startswith("#")
        ]
        assert satirlar, f"deploy/{ad} PEMF_ALLOWED_HOSTS ayarlamiyor — koruma o profilde OLU"
        deger = satirlar[-1].split("=", 1)[1].strip()
        assert deger == "auto" or deger.startswith("auto,"), (
            f"deploy/{ad}: beklenen 'auto' modu, bulunan {deger!r} (statik liste LAN IP'yi bilemez)"
        )


def test_KRITIK_launcher_da_korumayi_ACIYOR():
    """Launcher ile kurulan klinikler .env okumaz (bilinen sinif: ENABLE_TUNNEL/STM_PORT/
    DATA_DIR ayni yoldan kacmisti) — backend_env bu anahtari da tasimali."""
    rust = (_KOK / "launcher" / "core" / "src" / "install.rs").read_text(encoding="utf-8", errors="replace")
    assert "PEMF_ALLOWED_HOSTS" in rust, (
        "launcher backend_env PEMF_ALLOWED_HOSTS tasimiyor — launcher kurulumlarinda koruma OLU "
        "(deploy profillerini yalniz Inno/NSSM kurulumu okur)"
    )


def test_KARSIT_KANIT_varsayilan_yildiz_DAVRANISI_KORUR(api):
    """Ortamda deger yokken middleware EKLENMEZ (mevcut testler/dev akisi kirilmasin)."""
    secim = api._allowed_hosts_secimi("*")
    assert secim == ("kapali", ()), f"'*' artik korumayi aciyor: {secim!r} (sessiz davranis degisikligi)"
    assert api._allowed_hosts_secimi("auto")[0] == "auto"
    assert api._allowed_hosts_secimi("auto, klinik.sirket.com") == ("auto", ("klinik.sirket.com",))
    mod, liste = api._allowed_hosts_secimi("a.com,b.com")
    assert mod == "liste" and liste == ("a.com", "b.com")
