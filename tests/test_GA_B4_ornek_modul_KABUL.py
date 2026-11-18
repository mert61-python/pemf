# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""GA (istem 53) B4 — ÖRNEK MODÜL + SAHTE KART uçtan uca KABUL TESTLERİ (PLAN §2 kurallar A + B). GERÇEK süreçler: sahte kart AYRI
süreç (`moduller/ornek/sahte_kart.py`, yerel adlandırılmış boru — ağ portu yok), sürücü `--alt-surec modul-surucu` alt süreci.

  A1 `acil_durdur_hepsi` dönüşü ≤ 50 ms · kart ≤ 100 ms içinde keser (kartın kendi zaman damgası)
  A2 kalp atışı akarken bobin AÇIK kalır; kesilince kart bekçisi bobini KENDİSİ keser (≤ bekçi + pay)
  A3 sınır dışı ayar SUNUCUDA reddedilir — karta HİÇ gitmez
  A4 ebeveyn bağlantıyı keserse (stdin kapanır) sürücü kabuğu ÖNCE acil_durdur → bobin durur
  B6 sürücü çökünce / takılınca sunucu ayakta; takılan sürücüde ACİL DURDUR yine ≤ 50 ms döner ve süreci öldürür; açılış gecikmez
     (yönetici / alt süreç İLK kullanımda)
  E2E HTTP `POST /api/hardware/emergency_stop` çalışan modülün kartını keser
Ölçümler `GA_KABUL_OLCUM` ortam değişkeni verilirse JSON satırı olarak yazılır (rapor için).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
KART = KOK / "moduller" / "ornek" / "sahte_kart.py"


def _olcum(ad: str, deger: float) -> None:
    yol = os.environ.get("GA_KABUL_OLCUM")
    if yol:
        with open(yol, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"olcum": ad, "ms": round(deger * 1000.0, 2)}) + "\n")


def _kart_istemci(ad: str):
    sys.path.insert(0, str(KART.parent))
    try:
        import sahte_kart
    finally:
        sys.path.remove(str(KART.parent))
    from multiprocessing.connection import Client

    adr, aile = sahte_kart.adres(ad)
    return Client(adr, family=aile, authkey=sahte_kart.ANAHTAR)


@pytest.fixture
def kart(monkeypatch):
    """Sahte kart AYRI süreçte; sürücü alt süreci boru adını `PEMF_ORNEK_BORU`'dan alır."""
    from utils import gizli_surec

    ad = f"pemf-ga-test-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    p = gizli_surec.baslat(
        [sys.executable, "-X", "utf8", str(KART), "--boru", ad, "--bekci-ms", "1500"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    hazir = threading.Event()
    threading.Thread(target=lambda: (p.stdout.readline(), hazir.set()), daemon=True).start()
    assert hazir.wait(30), "sahte kart açılmadı"
    monkeypatch.setenv("PEMF_ORNEK_BORU", ad)
    monkeypatch.delenv("PEMF_MODULLER_KOKU", raising=False)
    from servers import modul_kayit

    monkeypatch.setattr(modul_kayit, "gorunur_mu", lambda: True)
    baglanti = _kart_istemci(ad)

    def durum():
        baglanti.send({"k": "durum"})
        return baglanti.recv()

    yield durum
    baglanti.close()
    p.kill()
    p.wait(10)


@pytest.fixture
def yonetici():
    from servers.modul_yonetici import ModulYoneticisi

    y = ModulYoneticisi()
    yield y
    y.birak()


def _calistir(y, durum):
    y.sec("ornek")
    y.uygula({"frekans_hz": 100, "duty_yuzde": 25})
    y.baslat()
    assert durum()["bobin"] is True


def _bekle(kosul, sure):
    t0 = time.monotonic()
    while time.monotonic() - t0 < sure:
        if kosul():
            return True
        time.sleep(0.005)
    return False


def test_KRITIK_GA_B4_A1_ACIL_DURDUR_donus_50ms_KART_100ms(kart, yonetici):
    _calistir(yonetici, kart)
    assert yonetici.durum()["surucu"] == {"bobin": True, "ayar": {"frekans_hz": 100, "duty_yuzde": 25}}
    t_duvar = time.time()
    t0 = time.perf_counter()
    sonuc = yonetici.acil_durdur_hepsi()
    donus = time.perf_counter() - t0
    assert sonuc == [{"kimlik": "ornek", "onay": True}]
    assert donus <= 0.05, donus
    d = kart()
    assert d["bobin"] is False and d["kapanma"]["neden"] == "acil"
    kesme = d["kapanma"]["zaman"] - t_duvar
    assert kesme <= 0.1, kesme
    _olcum("acil_donus", donus)
    _olcum("kart_kesme", kesme)


def test_KRITIK_GA_B4_A2_KALP_kesilince_KART_kendisi_keser(kart, yonetici):
    _calistir(yonetici, kart)
    time.sleep(3.2)  # kalp atışı akarken bobin AÇIK kalır (bekçi 1500 ms, kalp 500 ms)
    assert kart()["bobin"] is True
    t0 = time.time()
    yonetici._kalp_dur.set()  # sunucunun kalp atışı kesildi (donma / kablo)
    assert _bekle(lambda: kart()["bobin"] is False, 3.0)
    d = kart()
    assert d["kapanma"]["neden"] == "bekci"
    gecikme = d["kapanma"]["zaman"] - t0
    assert gecikme <= 1.5 + 0.5 + 0.3, gecikme  # bekçi + son kalbin yaşı + pay
    _olcum("bekci_kesme", gecikme)


def test_KRITIK_GA_B4_A3_SINIR_DISI_ayar_karta_GITMEZ(kart, yonetici):
    from servers.modul_kayit import ModulHatasi

    yonetici.sec("ornek")
    for ayar, kod in (
        ({"frekans_hz": 9999}, "ayarSinirDisi"),
        ({"guc_w": 5}, "ayarBilinmeyen"),
        ({"duty_yuzde": "50"}, "ayarSayiDegil"),
    ):
        with pytest.raises(ModulHatasi) as e:
            yonetici.uygula(ayar)
        assert e.value.kod == kod
    assert kart()["ayar"] == {}  # karta HİÇBİRİ gitmedi
    with pytest.raises(ModulHatasi) as e:
        yonetici.baslat()  # ayarsız kart başlamaz (kart kuralı)
    assert (e.value.kod, e.value.alan) == ("surucuHatasi", "ayarYok")
    assert kart()["bobin"] is False


def test_KRITIK_GA_B4_A4_EBEVEYN_gidince_bobin_DURUR(kart, yonetici):
    _calistir(yonetici, kart)
    p = yonetici._etkin[2]._p
    p.stdin.close()  # ana sunucu öldü / bağlantı koptu
    assert _bekle(lambda: kart()["bobin"] is False, 3.0)
    assert kart()["kapanma"]["neden"] == "acil"  # kabuk ÖNCE acil_durdur çağırdı
    assert _bekle(lambda: p.poll() is not None, 5.0)


def test_KRITIK_GA_B4_B6_surucu_COKUNCE_sunucu_AYAKTA_kart_DURUR(kart, yonetici):
    from servers.modul_kayit import ModulHatasi

    _calistir(yonetici, kart)
    yonetici._etkin[2]._p.kill()
    assert _bekle(lambda: kart()["bobin"] is False, 2.0)  # bağlantı koptu → kart keser
    with pytest.raises(ModulHatasi) as e:
        yonetici.durum()
    assert e.value.kod == "surucuOldu"
    t0 = time.perf_counter()
    assert yonetici.acil_durdur_hepsi() == []  # canlı süreç yok → anında
    assert time.perf_counter() - t0 < 0.05


def test_KRITIK_GA_B4_B6_TAKILAN_surucu_ACIL_50ms_ve_OLDURULUR(monkeypatch):
    from servers import modul_kayit
    from servers.modul_kayit import ModulHatasi
    from servers.modul_yonetici import ModulYoneticisi

    monkeypatch.setenv("PEMF_MODULLER_KOKU", str(KOK / "tests" / "veri" / "moduller"))
    monkeypatch.setattr(modul_kayit, "gorunur_mu", lambda: True)
    y = ModulYoneticisi()
    try:
        y.sec("takilan")
        s = y._etkin[2]
        sonuc = {}
        t = threading.Thread(target=lambda: sonuc.update(r=_hata_kodu(y, {"frekans_hz": 100})), daemon=True)
        t.start()
        time.sleep(0.3)  # uygula sürücüde TAKILI
        t0 = time.perf_counter()
        assert y.acil_durdur_hepsi() in (
            [{"kimlik": "takilan", "onay": False}],
            [],
        )  # bütçe dolarsa sonuç eksik, öldürme sürer
        donus = time.perf_counter() - t0
        assert donus <= 0.05, donus
        assert _bekle(lambda: not s.canli(), 2.0)  # takılan süreç ÖLDÜRÜLDÜ
        t.join(5)
        assert sonuc["r"] in ("surucuOldu", "surucuYanitsiz")  # sunucu ayakta, çağrı zaman aşımıyla döndü
        _olcum("takilan_acil_donus", donus)
    finally:
        y.birak()
    with pytest.raises(ModulHatasi):
        y.durum()


def _hata_kodu(y, ayar):
    from servers.modul_kayit import ModulHatasi

    try:
        y.uygula(ayar)
    except ModulHatasi as e:
        return e.kod
    return None


def test_KRITIK_GA_B4_E2E_HTTP_ACIL_DURDUR_modul_kartini_KESER(kart, monkeypatch):
    from ai_pro_aparati import istemci, mandali_sifirla
    from servers import api_server, modul_yonetici

    class _HW:
        def stop_all_coils(self):
            return True

    y = modul_yonetici.ModulYoneticisi()
    monkeypatch.setattr(modul_yonetici, "_yonetici", y)
    monkeypatch.setattr(api_server.state, "hardware", _HW())
    c = istemci(api_server.app)
    try:
        _calistir(y, kart)
        t_duvar = time.time()
        r = c.post("/api/hardware/emergency_stop")
        assert r.status_code == 200
        assert _bekle(lambda: kart()["bobin"] is False, 1.0)
        d = kart()
        assert d["kapanma"]["neden"] == "acil"
        _olcum("http_estop_kart_kesme", d["kapanma"]["zaman"] - t_duvar)
    finally:
        mandali_sifirla(c)
        y.birak()


def test_KRITIK_GA_B4_B6_ACILIS_GECIKMEZ_yonetici_ilk_kullanimda():
    """Sunucu açılışı modül taramaz / süreç açmaz: api_server içe aktarılınca yönetici YOK (taze süreçte ölçülür)."""
    kod = (
        "import sys; sys.path[:0] = [sys.argv[1], sys.argv[2]];"
        "import servers.api_server;"
        "from servers import modul_yonetici;"
        "print('YONETICI', modul_yonetici.varsa())"
    )
    r = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", kod, str(KOK), str(KOK / "apps" / "backend")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert "YONETICI None" in r.stdout, (r.stdout[-500:], r.stderr[-1500:])
