# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""GA (istem 53) B1 / B2 — GELİŞTİRİCİ MODÜLÜ YÖNETİCİSİ: sürücüyü AYRI SÜREÇTE koşturur (`servers.alt_surec`, JSON satırları),
bir anda TEK etkin modül (Y299), 500 ms kalp atışı (kart bekçisi), ACİL DURDUR yayılımı.

ACİL DURDUR (GÜVENLİK YOLU, Y257): `acil_durdur_hepsi()` canlı BÜTÜN modül süreçlerine PARALEL `acil_durdur` gönderir ve en çok
`ACIL_DONUS_S` (≤ 50 ms) içinde DÖNER: yanıtlamayan / takılan sürücü süreci ÖLDÜRÜLÜR (kart kalp atışını duymaz → kendi bekçisiyle
keser; sürücü kabuğu da stdin kapanınca acil_durdur çağırır). Seçim kilidi ACİL yolunda ALINMAZ. Ana ACİL DURDUR (STM) bunu BEKLEMEZ
(`api_server._emergency_stop_all` arka planda çağırır). Modüller ACİL DURDUR'a bir KOŞUL eklemez.
"""

from __future__ import annotations

import itertools
import json
import logging
import os
import subprocess
import threading
import time

from servers import modul_kayit
from servers.modul_kayit import ModulHatasi

logger = logging.getLogger(__name__)

#: acil_durdur ONAY penceresi; onaylamayan sürücü süreci öldürülür (güvenli yön: kart bağlantı kopunca / bekçiyle keser). Toplam dönüş
#: ≤ ~40 ms (≤ 50 ms kuralı; yükte payı için 30 ms — ölçüldü 19-11: 40 ms penceresi yükte 50 ms'yi aşabiliyordu).
ACIL_DONUS_S = 0.03
KALP_ARALIK_S = 0.5
KALP_ZAMAN_ASIMI_S = 0.3
ISLEM_ZAMAN_ASIMI_S = 2.0
BAGLAN_ZAMAN_ASIMI_S = 10.0


class ModulSureci:
    """Bir modül sürücüsünün alt süreci. İstekler numaralı; yanıtlar numarayla eşlenir → `acil_durdur` takılı bir isteği BEKLEMEZ."""

    def __init__(self, klasor, baslatici=None):
        self._klasor = str(klasor)
        self._baslatici = baslatici or self._varsayilan_baslatici
        self._no = itertools.count(1)
        self._bekleyen: dict = {}
        self._kilit = threading.Lock()
        self._yazim = threading.Lock()
        self._p = None

    @staticmethod
    def _varsayilan_baslatici(klasor: str):
        from utils import gizli_surec

        from servers.alt_surec import komut

        return gizli_surec.baslat(
            komut("modul-surucu", klasor),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )

    def baslat(self) -> None:
        self._p = self._baslatici(self._klasor)
        threading.Thread(target=self._oku, args=(self._p,), daemon=True, name="modul-oku").start()

    def canli(self) -> bool:
        return self._p is not None and self._p.poll() is None

    def oldu_mu(self, bekle_s: float = 0.3) -> bool:
        """Yanıt gelmediyse: süreç öldü mü (boru EOF'u, işletim sisteminin çıkış işaretinden ÖNCE gelebilir — ölçüldü) yoksa takılı mı."""
        p = self._p
        if p is None:
            return True
        try:
            p.wait(timeout=bekle_s)
        except subprocess.TimeoutExpired:
            return False
        return True

    def _oku(self, p) -> None:
        try:
            for satir in p.stdout:
                try:
                    y = json.loads(satir.decode("utf-8"))
                except ValueError:
                    continue
                with self._kilit:
                    kutu = self._bekleyen.pop(y.get("id"), None) if isinstance(y, dict) else None
                if kutu is not None:
                    kutu["y"] = y
                    kutu["olay"].set()
        except (OSError, ValueError):
            pass
        with self._kilit:  # akış bitti: bekleyen herkes "yanıt yok"
            bekleyen, self._bekleyen = self._bekleyen, {}
        for kutu in bekleyen.values():
            kutu["olay"].set()

    def _gonder(self, islem: str, ayar=None) -> dict:
        no = next(self._no)
        kutu = {"olay": threading.Event(), "y": None}
        with self._kilit:
            self._bekleyen[no] = kutu
        satir = (json.dumps({"id": no, "islem": islem, **({"ayar": ayar} if ayar is not None else {})}) + "\n").encode(
            "utf-8"
        )

        def yaz():
            try:
                with self._yazim:
                    self._p.stdin.write(satir)
                    self._p.stdin.flush()
            except (OSError, ValueError, AttributeError):
                kutu["olay"].set()

        threading.Thread(
            target=yaz, daemon=True, name=f"modul-yaz-{islem}"
        ).start()  # yazım takılsa da çağıran beklemez
        return kutu

    def istek(self, islem: str, ayar=None, zaman_asimi: float = ISLEM_ZAMAN_ASIMI_S) -> dict | None:
        """Yanıt sözlüğü; süreç ölü / zaman aşımı → None."""
        if not self.canli():
            return None
        kutu = self._gonder(islem, ayar)
        kutu["olay"].wait(zaman_asimi)
        return kutu["y"]

    def acil_durdur(self, zaman_asimi: float = ACIL_DONUS_S) -> bool:
        """`acil_durdur` iste; `zaman_asimi` içinde ONAY yoksa süreci ÖLDÜR. Her durumda hızla döner. True = sürücü onayladı."""
        if not self.canli():
            return False
        y = self.istek("acil_durdur", zaman_asimi=zaman_asimi)
        if y is not None and y.get("tamam") is True:
            return True
        self.oldur()
        return False

    def oldur(self) -> None:
        p = self._p
        if p is not None and p.poll() is None:
            try:
                p.kill()
            except OSError:
                pass

    def kapat(self, bekle_s: float = 2.0) -> None:
        """stdin kapanır → kabuk acil_durdur + kes yapıp çıkar; çıkmazsa öldürülür."""
        p, self._p = self._p, None
        if p is None:
            return
        try:
            p.stdin.close()
        except (OSError, ValueError):
            pass
        try:
            p.wait(timeout=bekle_s)
        except subprocess.TimeoutExpired:
            p.kill()


class ModulYoneticisi:
    def __init__(self, surec_sinifi=ModulSureci, kalp_aralik_s: float = KALP_ARALIK_S):
        self._surec_sinifi = surec_sinifi
        self._kalp_aralik = kalp_aralik_s
        self._secim = threading.Lock()  # seçim / bırakma — ACİL yolunda ALINMAZ
        self._etkin: tuple[str, dict, ModulSureci] | None = None
        self._kalp_dur = threading.Event()
        self._kalp_hata = 0
        self._son_hata: str | None = None

    # ── durum ──────────────────────────────────────────────────────────────────────────────────────
    def etkin_kimlik(self) -> str | None:
        e = self._etkin
        return e[0] if e else None

    def ozet(self) -> dict:
        e = self._etkin
        if e is None:
            return {"etkin": None, "canli": False, "hata": self._son_hata}
        return {"etkin": e[0], "canli": e[2].canli(), "hata": self._son_hata, "kalpHata": self._kalp_hata}

    # ── seçim ──────────────────────────────────────────────────────────────────────────────────────
    def sec(self, kimlik: str) -> dict:
        if not modul_kayit.gorunur_mu():
            raise ModulHatasi("gizli")
        klasor, modul = modul_kayit.bul(kimlik)
        with self._secim:
            self._birak_kilitli()
            s = self._surec_sinifi(klasor)
            s.baslat()
            y = s.istek("baglan", zaman_asimi=BAGLAN_ZAMAN_ASIMI_S)
            if not (y and y.get("tamam")):
                s.kapat()
                raise ModulHatasi("baglanamadi", str((y or {}).get("hata") or "yanitYok"))
            self._etkin = (kimlik, modul, s)
            self._son_hata = None
            self._kalp_hata = 0
            self._kalp_dur = threading.Event()
            threading.Thread(
                target=self._kalp, args=(s, self._kalp_dur), daemon=True, name=f"modul-kalp-{kimlik}"
            ).start()
        return self.ozet()

    def birak(self) -> dict:
        with self._secim:
            self._birak_kilitli()
        return self.ozet()

    def _birak_kilitli(self) -> None:
        e, self._etkin = self._etkin, None
        self._kalp_dur.set()
        if e is None:
            return
        s = e[2]
        s.istek("durdur")
        s.istek("kes")
        s.kapat()

    def _kalp(self, s: ModulSureci, dur: threading.Event) -> None:
        while not dur.wait(self._kalp_aralik):
            y = s.istek("kalp", zaman_asimi=KALP_ZAMAN_ASIMI_S)
            if y is not None and y.get("tamam"):
                self._kalp_hata = 0
                continue
            self._kalp_hata += 1
            self._son_hata = "surucuOldu" if not s.canli() else "kalpYanitsiz"
            if not s.canli():
                return

    # ── komutlar ───────────────────────────────────────────────────────────────────────────────────
    def _etkin_al(self):
        e = self._etkin
        if e is None:
            raise ModulHatasi("etkinModulYok")
        return e

    def _komut(self, islem: str, ayar=None) -> dict:
        _, _, s = self._etkin_al()
        y = s.istek(islem, ayar)
        if y is None:
            self._son_hata = "surucuOldu" if s.oldu_mu() else "surucuYanitsiz"
            raise ModulHatasi(self._son_hata)
        if not y.get("tamam"):
            raise ModulHatasi("surucuHatasi", str(y.get("hata") or ""))
        return y

    def uygula(self, ayar) -> dict:
        _, modul, _ = self._etkin_al()
        temiz = modul_kayit.ayar_dogrula(modul, ayar)  # sınır dışı → karta HİÇ gitmez
        self._komut("uygula", temiz)
        return {"uygulandi": temiz}

    def baslat(self) -> dict:
        self._komut("baslat")
        return self.ozet()

    def durdur(self) -> dict:
        self._komut("durdur")
        return self.ozet()

    def durum(self) -> dict:
        return {**self.ozet(), "surucu": self._komut("durum").get("durum", {})}

    # ── ACİL DURDUR ────────────────────────────────────────────────────────────────────────────────
    def acil_durdur_hepsi(self) -> list[dict]:
        """Canlı BÜTÜN modül süreçlerine PARALEL acil_durdur; ≤ ~50 ms döner (takılan öldürülür). Seçim kilidi ALINMAZ."""
        e = self._etkin
        surecler = [(e[0], e[2])] if e is not None else []
        sonuc: list[dict] = []
        t0 = time.monotonic()

        def bir(kimlik, s):
            sonuc.append({"kimlik": kimlik, "onay": s.acil_durdur()})

        isler = [
            threading.Thread(target=bir, args=(k, s), daemon=True, name=f"modul-acil-{k}")
            for k, s in surecler
            if s.canli()
        ]
        for t in isler:
            t.start()
        for t in isler:
            t.join(max(0.0, ACIL_DONUS_S + 0.008 - (time.monotonic() - t0)))
        if surecler:
            logger.warning("ACİL DURDUR modüllere iletildi: %s (%.1f ms)", sonuc, (time.monotonic() - t0) * 1000.0)
        return sonuc


_yonetici: ModulYoneticisi | None = None
_yonetici_kilidi = threading.Lock()


def yonetici() -> ModulYoneticisi:
    global _yonetici
    with _yonetici_kilidi:
        if _yonetici is None:
            _yonetici = ModulYoneticisi()
        return _yonetici


def varsa() -> ModulYoneticisi | None:
    """ACİL yolu için: yönetici HİÇ kurulmadıysa (modül kullanılmadı) None — kurmaz, içe aktarma dışında iş yapmaz."""
    return _yonetici
