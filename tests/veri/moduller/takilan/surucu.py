# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""GA test verisi: TAKILAN sürücü — `uygula` ve `acil_durdur` 30 sn uyur (kabul testi: sunucu ayakta kalır, ACİL DURDUR ≤ 50 ms döner
ve süreci öldürür). Denetleyiciden geçer (yasak çağrı yok)."""

import time

from servers.modul_surucu import BobinSurucusu


class Surucu(BobinSurucusu):
    def baglan(self):
        pass

    def kes(self):
        pass

    def uygula(self, ayar):
        time.sleep(30)

    def baslat(self):
        pass

    def durdur(self):
        pass

    def acil_durdur(self):
        time.sleep(30)

    def kalp(self):
        pass

    def durum(self):
        return {"bobin": False}
