# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""GA (istem 53) — yardımcı alt süreç altyapısı (`servers/alt_surec.py` + `backend_service --alt-surec`).

SÖZLEŞME:
  - Komut: donmuş EXE'de `PEMF_Backend.exe --alt-surec <ad>` (sahada Python yok), kaynakta `python -X utf8 backend_service.py --alt-surec <ad>`.
    `backend_service.main` bu alt komutta sunucu / port / donanım AÇMADAN dağıtıcıya gider.
  - Alt süreç konsol penceresi AÇMAZ (`gizli_surec`), DÜŞÜK öncelikli (BELOW_NORMAL), BLAS tek iş parçacığı; stderr atılır.
  - JSON satırları: bozuk istek / işleyici hatası döngüyü düşürmez; girdi kapanınca çıkar.
  - Ebeveyn: zaman aşımı / ölü süreç / yazma hatası → None (çağıran fail-safe), takılan süreç öldürülür, sonraki istek yeniden başlatır.
  - GERÇEK alt süreç gidiş-dönüşü (kaynak kipinde, kalibrasyonsuz veri kökü → `kalibrasyonYok`).
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import time

import pytest


def test_KRITIK_GA_alt_surec_KOMUT_donmus_ve_kaynak(monkeypatch):
    from servers import alt_surec

    k = alt_surec.komut("canli-alan")
    assert k[:4] == [sys.executable, "-X", "utf8", "-c"] and k[-2:] == ["--alt-surec", "canli-alan"]
    assert os.path.isdir(k[5]) and os.path.isfile(
        os.path.join(k[5], "servers", "alt_surec.py")
    )  # apps/backend → sys.path
    assert os.path.basename(k[6]) == "backend_service.py" and os.path.isfile(k[6])
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\PEMF\PEMF_Backend\PEMF_Backend.exe")
    assert alt_surec.komut("canli-alan", "a") == [
        r"C:\PEMF\PEMF_Backend\PEMF_Backend.exe",
        "--alt-surec",
        "canli-alan",
        "a",
    ]


def test_KRITIK_GA_alt_surec_DAGITICI_ve_backend_service_ALT_KOMUTU(monkeypatch):
    import backend_service
    from servers import alt_surec, canli_alan_hesapci

    gelen = []
    monkeypatch.setattr(canli_alan_hesapci, "main", lambda argv: gelen.append(argv) or 7)
    assert alt_surec.calistir([]) == 2
    assert alt_surec.calistir(["bilinmeyen"]) == 2
    assert alt_surec.calistir(["canli-alan", "x"]) == 7 and gelen == [["x"]]
    assert backend_service._alt_surec_mi(["--port", "8010"]) is None
    assert backend_service._alt_surec_mi(["--port", "8010", "--alt-surec", "x"]) is None  # yalnız İLK argüman
    assert backend_service._alt_surec_mi([]) is None
    assert backend_service._alt_surec_mi(["--alt-surec", "canli-alan"]) == ["canli-alan"]
    monkeypatch.setattr(sys, "argv", ["backend_service.py", "--alt-surec", "canli-alan", "y"])
    assert backend_service._alt_surec_mi(None) == ["canli-alan", "y"]
    # main: alt komut sunucuyu / argparse'ı HİÇ çalıştırmaz
    monkeypatch.setattr(backend_service, "build_arg_parser", lambda: pytest.fail("sunucu ayrıştırıcısı çağrıldı"))
    assert backend_service.main(["--alt-surec", "canli-alan", "z"]) == 7 and gelen[-1] == ["z"]


def test_KRITIK_GA_json_satir_dongusu_BOZUK_ve_HATA_dongu_SURER(monkeypatch):
    from servers.alt_surec import json_satir_dongusu

    def isle(istek):
        if istek.get("patla"):
            raise KeyError("x")
        return {"ok": istek["n"] * 2, "metin": "ğüşİ"}

    girdi = io.StringIO('{"n": 2}\n[1]\nbozuk{\n{"patla": true}\n\n{"n": 5}\n')
    cikti = io.StringIO()
    assert json_satir_dongusu(isle, girdi, cikti) == 0
    assert [json.loads(s) for s in cikti.getvalue().splitlines()] == [
        {"ok": 4, "metin": "ğüşİ"},
        {"hata": "bozukIstek"},
        {"hata": "bozukIstek"},
        {"hata": "KeyError"},
        {"ok": 10, "metin": "ğüşİ"},
    ]
    # varsayılan akışlar: sys.stdin / sys.stdout
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"n": 1}\n'))
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    assert json_satir_dongusu(isle) == 0
    assert json.loads(out.getvalue()) == {"ok": 2, "metin": "ğüşİ"}


class _SahteSurec:
    """`subprocess.Popen` yerine: stdin'e yazılan her istek satırına `yanitla(istek)` ile yanıt üretir."""

    def __init__(self, yanitla, takil=False, yazma_hatasi=False, olmez=False):
        import queue

        self._q = queue.Queue()
        self._yanitla = yanitla
        self._takil = takil
        self._olmez = olmez
        self.oldu = False
        self.donus = None
        self.pid = 4242
        self.kill_sayisi = 0
        sahte = self

        class _Stdin:
            def write(self, veri):
                if yazma_hatasi:
                    raise BrokenPipeError("kapalı")
                for satir in veri.decode("utf-8").splitlines():
                    y = sahte._yanitla(json.loads(satir))
                    if y is not None and not sahte._takil:
                        sahte._q.put(y if isinstance(y, bytes) else (json.dumps(y) + "\n").encode("utf-8"))

            def flush(self):
                pass

            def close(self):
                if not sahte._takil:
                    sahte._bitir()

        class _Stdout:
            def __iter__(self):
                while True:
                    s = sahte._q.get()
                    if s is None:
                        return
                    yield s

        self.stdin, self.stdout = _Stdin(), _Stdout()

    def _bitir(self):
        self.oldu = True
        self.donus = 0
        self._q.put(None)

    def poll(self):
        return self.donus

    def wait(self, timeout=None):
        if not self.oldu:
            raise subprocess.TimeoutExpired("sahte", timeout)
        return 0

    def kill(self):
        self.kill_sayisi += 1
        if not self._olmez:
            self._bitir()


def test_KRITIK_GA_JsonSatirSureci_istek_YANIT_bozuk_yanit_KAPAT():
    from servers.alt_surec import JsonSatirSureci

    surecler = []

    def baslatici(komut):
        assert komut == ["x", "--alt-surec", "y"]
        s = _SahteSurec(lambda i: {"n": i["n"] + 1} if i["n"] != 9 else b"bozuk\n")
        surecler.append(s)
        return s

    j = JsonSatirSureci(["x", "--alt-surec", "y"], ad="dene", baslatici=baslatici)
    assert not j.calisiyor()
    assert j.istek({"n": 1}, 5) == {"n": 2}
    assert j.istek({"n": 2}, 5) == {"n": 3} and len(surecler) == 1  # aynı süreç
    assert j.istek({"n": 9}, 5) == {"hata": "bozukYanit"}
    assert j.calisiyor()
    j.kapat()
    assert not j.calisiyor() and surecler[0].oldu and surecler[0].kill_sayisi == 0  # stdin kapanınca kendisi çıktı
    j.kapat()  # çalışmıyorken zararsız


def test_KRITIK_GA_JsonSatirSureci_ZAMAN_ASIMI_oldurur_SONRAKI_yeniden_baslatir():
    from servers.alt_surec import JsonSatirSureci

    surecler = []

    def baslatici(komut):
        s = _SahteSurec(lambda i: {"ok": True}, takil=not surecler)  # ilk süreç takılır
        surecler.append(s)
        return s

    j = JsonSatirSureci(["x"], baslatici=baslatici)
    t0 = time.monotonic()
    assert j.istek({"n": 1}, 0.2) is None
    assert time.monotonic() - t0 < 10
    assert surecler[0].kill_sayisi == 1 and surecler[0].oldu  # takılan süreç ÖLDÜRÜLDÜ
    assert j.istek({"n": 2}, 5) == {"ok": True} and len(surecler) == 2  # yeniden başladı


def test_KRITIK_GA_JsonSatirSureci_OLU_surec_ve_YAZMA_hatasi_None():
    from servers.alt_surec import JsonSatirSureci

    surecler = []

    def baslatici(komut):
        s = _SahteSurec(lambda i: None)  # yanıt yazmadan
        surecler.append(s)
        return s

    j = JsonSatirSureci(["x"], baslatici=baslatici)
    surec_bitir = []

    def istek_ve_ol():
        r = j.istek({"n": 1}, 5)
        surec_bitir.append(r)

    import threading

    t = threading.Thread(target=istek_ve_ol)
    t.start()
    for _ in range(200):
        if surecler:
            break
        time.sleep(0.01)
    surecler[0]._bitir()  # süreç yanıt vermeden öldü → akış biter
    t.join(5)
    assert surec_bitir == [None] and not j.calisiyor()
    j2 = JsonSatirSureci(["x"], baslatici=lambda k: _SahteSurec(lambda i: {"x": 1}, yazma_hatasi=True))
    assert j2.istek({"n": 1}, 5) is None and not j2.calisiyor()


def test_KRITIK_GA_JsonSatirSureci_OLDURULEMEYEN_surec_GUNLUGE(caplog):
    from servers.alt_surec import JsonSatirSureci

    s = _SahteSurec(lambda i: {"ok": 1}, takil=True, olmez=True)
    j = JsonSatirSureci(["x"], ad="inatci", baslatici=lambda k: s)
    j._baslat()
    with caplog.at_level("WARNING"):
        j._durdur(bekle_s=0.01)
    assert s.kill_sayisi == 1 and "sonlandırılamadı" in caplog.text


def test_KRITIK_GA_JsonSatirSureci_VARSAYILAN_baslatici_GIZLI_DUSUK_oncelik(monkeypatch):
    from servers import alt_surec
    from utils import gizli_surec

    gelen = {}

    def sahte_baslat(args, **kw):
        gelen.update(kw, args=args)
        return _SahteSurec(lambda i: {"ok": 1})

    monkeypatch.setattr(gizli_surec, "baslat", sahte_baslat)
    j = alt_surec.JsonSatirSureci(["a", "b"])
    assert j.istek({}, 5) == {"ok": 1}
    assert gelen["args"] == ["a", "b"]
    assert (
        gelen["stdin"] == subprocess.PIPE
        and gelen["stdout"] == subprocess.PIPE
        and gelen["stderr"] == subprocess.DEVNULL
    )
    if os.name == "nt":
        assert (
            gelen["creationflags"] & gizli_surec.CREATE_NO_WINDOW and gelen["creationflags"] & alt_surec.DUSUK_ONCELIK
        )
    for k, v in alt_surec.TEK_IS_PARCACIGI.items():
        assert gelen["env"][k] == v
    j.kapat()


def test_KRITIK_GA_GERCEK_alt_surec_gidis_donus_KALIBRASYONSUZ(tmp_path, monkeypatch):
    """Kaynak kipinde GERÇEK `python backend_service.py --alt-surec canli-alan`: sunucu açmadan yanıt verir, stdin kapanınca çıkar."""
    from servers.alt_surec import JsonSatirSureci, komut

    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path))
    j = JsonSatirSureci(komut("canli-alan"), ad="canli-alan-test")
    try:
        t0 = time.monotonic()
        y = j.istek({"bobinler": [[1, 100.0, 0.5, 0.0]]}, 120)
        assert y is not None and y["durum"] == "kalibrasyonYok" and y["modelTahmini"] is True, y
        assert time.monotonic() - t0 < 120
        assert j.istek({"bozuk": 1}, 30) == {"hata": "KeyError"}  # alt süreç sürer
        p = j._p
        assert p is not None and p.poll() is None
    finally:
        j.kapat()
    assert p.poll() == 0  # stdin kapanınca kendisi temiz çıktı (öldürülmedi)


def test_KRITIK_GA_JsonSatirSureci_OKUMA_ve_KAPATMA_hatasi_DUSURMEZ():
    import queue

    from servers.alt_surec import JsonSatirSureci

    class _KirikBoru:
        def __iter__(self):
            raise OSError("boru kırık")

    q = queue.Queue()
    JsonSatirSureci._oku(type("P", (), {"stdout": _KirikBoru()})(), q)
    assert q.get_nowait() is None  # okuma hatası = akış bitti

    s = _SahteSurec(lambda i: {"ok": 1})

    def _kapanmaz():
        raise OSError("kapalı")

    s.stdin.close = _kapanmaz
    j = JsonSatirSureci(["x"], baslatici=lambda k: s)
    j._baslat()
    j._durdur(bekle_s=0.01)
    assert s.kill_sayisi == 1 and s.oldu  # stdin kapatılamadı → beklendi → öldürüldü
