# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""GA (istem 53) B4 — ÖRNEK MODÜL SÜRÜCÜSÜ (şablon): sahte karta (`sahte_kart.py`, ayrı süreç) yerel adlandırılmış boruyla bağlanır.
Gerçek modülde bağlantı geliştiricinin seçimidir (seri / Wi-Fi / BLE …); arayüz ve kurallar AYNI (`servers/modul_surucu.py`).
Her çağrı zaman aşımlıdır (takılmaz); `acil_durdur` öbür çağrılardan bağımsız, kendi kilidiyle gider."""

from __future__ import annotations

import os
import sys
import tempfile
import threading
from multiprocessing.connection import Client

from servers.modul_surucu import BobinSurucusu, SurucuHatasi

ANAHTAR = b"pemf-ornek-sahte-kart"
ZAMAN_ASIMI_S = 0.5


def _adres(ad: str):
    if sys.platform == "win32":
        return "\\\\.\\pipe\\" + ad, "AF_PIPE"
    return os.path.join(tempfile.gettempdir(), f"{ad}.sock"), "AF_UNIX"


class Surucu(BobinSurucusu):
    def __init__(self, modul: dict, klasor: str):
        super().__init__(modul, klasor)
        self._boru = os.environ.get("PEMF_ORNEK_BORU") or modul.get("baglanti_ayrinti", {}).get(
            "boru", "pemf-ornek-kart"
        )
        self._baglanti = None
        self._kilit = threading.Lock()
        # ACİL DURDUR AYRI bağlantı + kilitle: takılı bir `uygula` onu BEKLETMEZ
        self._acil_baglanti = None
        self._acil_kilit = threading.Lock()

    def _gonder(self, ileti: dict, acil: bool = False) -> dict:
        b = self._acil_baglanti if acil else self._baglanti
        if b is None:
            raise SurucuHatasi("bagliDegil")
        with self._acil_kilit if acil else self._kilit:
            try:
                b.send(ileti)
                if not b.poll(ZAMAN_ASIMI_S):
                    raise SurucuHatasi("kartYanitsiz")
                y = b.recv()
            except (EOFError, OSError):
                raise SurucuHatasi("baglantiKoptu") from None
        if not y.get("tamam"):
            raise SurucuHatasi(str(y.get("hata") or "kartHatasi"))
        return y

    def baglan(self) -> None:
        adr, aile = _adres(self._boru)
        try:
            self._baglanti = Client(adr, family=aile, authkey=ANAHTAR)
            self._acil_baglanti = Client(adr, family=aile, authkey=ANAHTAR)
        except (OSError, EOFError):
            self.kes()
            raise SurucuHatasi("kartBulunamadi") from None

    def kes(self) -> None:
        for ad in ("_baglanti", "_acil_baglanti"):
            b = getattr(self, ad)
            setattr(self, ad, None)
            if b is not None:
                b.close()

    def uygula(self, ayar: dict) -> None:
        self._gonder({"k": "ayar", "ayar": ayar})

    def baslat(self) -> None:
        self._gonder({"k": "baslat"})

    def durdur(self) -> None:
        self._gonder({"k": "durdur"})

    def acil_durdur(self) -> None:
        self._gonder({"k": "acil"}, acil=True)

    def kalp(self) -> None:
        self._gonder({"k": "kalp"})

    def durum(self) -> dict:
        y = self._gonder({"k": "durum"})
        return {"bobin": y["bobin"], "ayar": y["ayar"]}
