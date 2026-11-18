# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""GA (istem 53) B4 — SAHTE KART (AYRI SÜREÇ): örnek modülün kartını taklit eder; geliştirici kartsız çalışır, kabul testleri gerçek kart
kurallarını bununla ÖLÇER (PLAN §2 A):
  - açılışta bobin KAPALI · kendi sınırları (modul.json ile aynı) — sınır dışı ayar REDDEDİLİR, bobin açılmaz
  - `acil` → bobin HEMEN kapanır (zaman damgası kaydedilir) · kalp atışı `bekci_ms` içinde gelmezse bobin KENDİLİĞİNDEN kapanır
  - bağlantı koparsa bobin kapanır
Bağlantı: işletim sisteminin yerel adlandırılmış borusu (Windows `\\\\.\\pipe\\<ad>`, POSIX: geçici dizinde soket dosyası) — ağ portu
DİNLEMEZ. Kullanım: `python sahte_kart.py --boru <ad> [--bekci-ms 1500]`.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import threading
import time
from multiprocessing.connection import Listener

ANAHTAR = b"pemf-ornek-sahte-kart"
SINIRLAR = {"frekans_hz": (1.0, 500.0), "duty_yuzde": (0.0, 50.0), "sure_dk": (0.0, 60.0)}


def adres(ad: str):
    """Platformun yerel boru adresi + ailesi (bağlantı TCP DEĞİL)."""
    if sys.platform == "win32":
        return "\\\\.\\pipe\\" + ad, "AF_PIPE"
    return os.path.join(tempfile.gettempdir(), f"{ad}.sock"), "AF_UNIX"


class Kart:
    def __init__(self, bekci_ms: int):
        self.bekci_s = bekci_ms / 1000.0
        self.kilit = threading.Lock()
        self.bobin = False  # AÇILIŞTA KAPALI
        self.ayar: dict = {}
        self.son_kalp = time.time()
        self.kapanma: dict | None = None
        self.acilma: float | None = None

    def kapat(self, neden: str) -> None:
        with self.kilit:
            if self.bobin:
                self.bobin = False
                self.kapanma = {"zaman": time.time(), "neden": neden}

    def isle(self, m: dict) -> dict:
        k = m.get("k")
        if k == "kalp":
            self.son_kalp = time.time()
            return {"tamam": True}
        if k == "acil":
            self.kapat("acil")
            return {"tamam": True}
        if k == "ayar":
            ayar = m.get("ayar") or {}
            for a, v in ayar.items():
                if a not in SINIRLAR or not isinstance(v, (int, float)) or not SINIRLAR[a][0] <= v <= SINIRLAR[a][1]:
                    return {"tamam": False, "hata": "kartSinirDisi"}
            self.ayar = dict(ayar)
            return {"tamam": True}
        if k == "baslat":
            if not self.ayar:
                return {"tamam": False, "hata": "ayarYok"}
            with self.kilit:
                self.son_kalp = time.time()
                self.bobin = True
                self.acilma = time.time()
            return {"tamam": True}
        if k == "durdur":
            self.kapat("durdur")
            return {"tamam": True}
        if k == "durum":
            return {
                "tamam": True,
                "bobin": self.bobin,
                "ayar": self.ayar,
                "kapanma": self.kapanma,
                "acilma": self.acilma,
            }
        return {"tamam": False, "hata": "bilinmeyen"}

    def bekci(self, dur: threading.Event) -> None:
        while not dur.wait(0.01):
            if self.bobin and time.time() - self.son_kalp > self.bekci_s:
                self.kapat("bekci")


def calistir(ad: str, bekci_ms: int, hazir: threading.Event | None = None, dur: threading.Event | None = None) -> None:
    kart = Kart(bekci_ms)
    dur = dur or threading.Event()
    threading.Thread(target=kart.bekci, args=(dur,), daemon=True).start()
    adr, aile = adres(ad)
    with Listener(adr, family=aile, authkey=ANAHTAR) as dinleyici:
        if hazir is not None:
            hazir.set()
        print("HAZIR", flush=True)
        while not dur.is_set():
            try:
                baglanti = dinleyici.accept()
            except OSError:
                continue
            # her bağlantı kendi iş parçacığında (sürücünün ayrı ACİL bağlantısı takılı bir komutu beklemez)
            threading.Thread(target=_hizmet, args=(kart, baglanti), daemon=True).start()


def _hizmet(kart: Kart, baglanti) -> None:
    with baglanti:
        try:
            while True:
                baglanti.send(kart.isle(baglanti.recv()))
        except (EOFError, OSError):
            kart.kapat("baglanti")  # bağlantı koptu → bobin kapanır


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--boru", required=True)
    ap.add_argument("--bekci-ms", type=int, default=1500)
    a = ap.parse_args(argv)
    calistir(a.boru, a.bekci_ms)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
