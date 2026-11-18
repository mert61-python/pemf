# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""GA (istem 53) B1 — GELİŞTİRİCİ MODÜLÜ SÜRÜCÜ ARAYÜZÜ (`BobinSurucusu`) + sürücünün koştuğu ALT SÜREÇ KABUĞU.

Modül = kart yazılımı + sürücü (`moduller/<kimlik>/surucu.py`, `Surucu(BobinSurucusu)`) + panel + `modul.json` (PLAN §2, Y298 / Y299).
Kart, kart yazılımı ve bağlantı (seri / Wi-Fi / BLE / …) geliştiricinindir; BİZ KURAL koyarız:
  - Sürücü AYRI SÜREÇTE koşar (`PEMF_Backend.exe --alt-surec modul-surucu <klasör>`): çökse / takılsa ana sunucu donmaz.
  - `acil_durdur` KENDİ iş parçacığında, öbür komutlardan BAĞIMSIZ işlenir (takılı bir `uygula` onu bekletmez).
  - Ebeveyn (ana sunucu) ölürse / bağlantıyı keserse stdin kapanır → kabuk ÖNCE `acil_durdur`, sonra `kes` çağırır (bobin HER
    kapanıştan önce durur — hafıza `pemf-device-safety-shutdown`). Asıl güvence kartın kendi bekçisidir (kalp atışı kesilince bobini keser).
  - Her yöntem TAKILMADAN döner; hata = istisna → yanıt `{"tamam": false, "hata": <kod>}` (süreç çökmez).
  - Sürücü ağa (kendi kartı dışında), diske (kendi klasörü dışında) ve alt süreçlere erişmez (`servers/modul_denetleyici.py`).

PROTOKOL (JSON satırları): istek `{"id": n, "islem": <ad>, "ayar": {...}?}` · yanıt `{"id": n, "tamam": bool, "durum": {...}?, "hata": <kod>?}`.
İşlemler: baglan · kes · uygula · baslat · durdur · acil_durdur · kalp · durum.
"""

from __future__ import annotations

import importlib.util
import json
import os
import queue
import sys
import threading

ISLEMLER = ("baglan", "kes", "uygula", "baslat", "durdur", "acil_durdur", "kalp", "durum")
#: Ebeveyn kapandığında (stdin EOF) `acil_durdur` için en çok bekleme — sürücü takılsa da kabuk çıkar.
KAPANIS_ACIL_BEKLEME_S = 1.0


class SurucuHatasi(Exception):
    """Sürücünün bildirdiği hata. `kod` → arayüzde eylem söyleyen metin (geliştiricinin panelinde TR + EN)."""

    def __init__(self, kod: str):
        super().__init__(kod)
        self.kod = str(kod)


class BobinSurucusu:
    """Geliştiricinin sürücüsü bunu genişletir (`class Surucu(BobinSurucusu)`). Her yöntem TAKILMADAN dönmelidir."""

    def __init__(self, modul: dict, klasor: str):
        self.modul = modul
        self.klasor = os.path.abspath(klasor)

    def baglan(self) -> None:
        """Kendi kartını BULUP bağlan (ör. seri portu YALNIZ kendi USB VID / PID / seri no'suyla — ana STM kartının portu açılmaz)."""
        raise NotImplementedError

    def kes(self) -> None:
        raise NotImplementedError

    def uygula(self, ayar: dict) -> None:
        """Ayarı karta yaz (sunucu `modul.json` sınırlarını ZATEN zorladı; kart da kendi sınırını uygular)."""
        raise NotImplementedError

    def baslat(self) -> None:
        raise NotImplementedError

    def durdur(self) -> None:
        raise NotImplementedError

    def acil_durdur(self) -> None:
        """Bobini HEMEN kes (öneri: dönüş ≤ 50 ms, kart ≤ 100 ms'de keser). HİÇBİR koşula bağlanmaz."""
        raise NotImplementedError

    def kalp(self) -> None:
        """Kalp atışını karta ilet (sunucu 500 ms'de bir çağırır). Kart belirli süre duymazsa bobini KENDİSİ keser."""
        raise NotImplementedError

    def durum(self) -> dict:
        raise NotImplementedError

    def dosya_yolu(self, ad: str) -> str:
        """Modül klasörü İÇİNDE bir dosya yolu — sürücünün diske yazabileceği TEK yer (denetleyici başka yazımı reddeder)."""
        yol = os.path.abspath(os.path.join(self.klasor, ad))
        if os.path.commonpath([yol, self.klasor]) != self.klasor:
            raise SurucuHatasi("klasorDisi")
        return yol


def surucuyu_yukle(klasor: str):
    """`<klasör>/modul.json` (doğrulanmış) + `<klasör>/surucu.py` `Surucu` sınıfı → sürücü örneği."""
    from servers import modul_kayit

    modul = modul_kayit.oku(klasor)
    spec = importlib.util.spec_from_file_location(
        f"pemf_modul_{modul['kimlik'].replace('-', '_')}", os.path.join(klasor, "surucu.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sinif = getattr(mod, "Surucu", None)
    if not (isinstance(sinif, type) and issubclass(sinif, BobinSurucusu)):
        raise SurucuHatasi("surucuSinifiYok")
    return sinif(modul, klasor)


def _cagir(surucu, islem: str, ayar) -> dict:
    try:
        if islem == "uygula":
            surucu.uygula(dict(ayar or {}))
        elif islem == "durum":
            return {"tamam": True, "durum": dict(surucu.durum() or {})}
        else:
            getattr(surucu, islem)()
        return {"tamam": True}
    except SurucuHatasi as e:
        return {"tamam": False, "hata": e.kod}
    except Exception as e:  # sürücü hatası kabuğu düşürmez
        return {"tamam": False, "hata": type(e).__name__}


def kabuk(surucu, girdi=None, cikti=None) -> int:
    """Sürücü alt süreç döngüsü. Okuyucu (bu iş parçacığı) satırları ayrıştırır: `acil_durdur` HEMEN kendi iş parçacığında, öbürleri
    sıralı çalışana. Girdi kapanınca (ebeveyn gitti): `acil_durdur` (≤ `KAPANIS_ACIL_BEKLEME_S`) + `kes`, çıkış 0."""
    girdi = sys.stdin if girdi is None else girdi
    cikti = sys.stdout if cikti is None else cikti
    yazim = threading.Lock()
    is_kuyrugu: queue.Queue = queue.Queue()

    def yanitla(no, y: dict) -> None:
        with yazim:
            cikti.write(json.dumps({"id": no, **y}, ensure_ascii=False) + "\n")
            cikti.flush()

    def calisan() -> None:
        while True:
            oge = is_kuyrugu.get()
            if oge is None:
                return
            no, islem, ayar = oge
            yanitla(no, _cagir(surucu, islem, ayar))

    threading.Thread(target=calisan, daemon=True, name="modul-calisan").start()
    for satir in girdi:
        satir = satir.strip()
        if not satir:
            continue
        try:
            istek = json.loads(satir)
            no, islem = istek.get("id"), istek.get("islem")
        except (ValueError, AttributeError):
            yanitla(None, {"tamam": False, "hata": "bozukIstek"})
            continue
        if islem not in ISLEMLER:
            yanitla(no, {"tamam": False, "hata": "bilinmeyenIslem"})
        elif islem == "acil_durdur":
            threading.Thread(
                target=lambda n=no: yanitla(n, _cagir(surucu, "acil_durdur", None)), daemon=True, name="modul-acil"
            ).start()
        else:
            is_kuyrugu.put((no, islem, istek.get("ayar")))
    # ebeveyn gitti → bobin önce durur
    acil = threading.Thread(target=_cagir, args=(surucu, "acil_durdur", None), daemon=True, name="modul-kapanis-acil")
    acil.start()
    acil.join(KAPANIS_ACIL_BEKLEME_S)
    is_kuyrugu.put(None)
    _cagir(surucu, "kes", None)
    return 0


def main(argv: list[str]) -> int:
    """`--alt-surec modul-surucu <klasör>`. Kütüphane `print`i protokolü bozmasın: `sys.stdout` stderr'e yönlenir."""
    cikti = sys.stdout
    sys.stdout = sys.stderr
    if len(argv) != 1:
        return 2
    try:
        surucu = surucuyu_yukle(argv[0])
    except Exception as e:
        kod = getattr(e, "kod", type(e).__name__)
        cikti.write(json.dumps({"id": None, "tamam": False, "hata": f"yuklenemedi:{kod}"}) + "\n")
        cikti.flush()
        return 3
    return kabuk(surucu, None, cikti)
