# -*- coding: utf-8 -*-
"""STM32 UART OKUMA — port seçimi + açılış banner'ını dinleme. TEK KAYNAK.

⚠️ **NEDEN `utils/` ALTINDA, `scripts/` ALTINDA DEĞİL** (ölçüldü 2026-09-22):
sevk edilen pakete `scripts/` altından YALNIZ altı `.ps1` giriyor
(`build_tools/make_base_zip.py::ADD_SCRIPTS`) — `scripts/*.py` **HİÇ gitmiyor**.
Donmuş EXE `utils`'i bundle'lar. Firmware güncellemesi kurulu cihazda banner okumak
zorunda; mantık `scripts/` altında kalsaydı sahada **hiç bulunmazdı**.
Aynı gerekçe `build_tools/source_crypto.py` başlığında da yazılı — bu, deponun yerleşik
deseni: *ilkeler `utils`'de durur, `scripts/` yalnız CLI yüzüdür.*

⚠️ BU MODÜL **YAZDIRMAZ**. Kütüphanedir; `print` çağıran bir kütüphane, arayüzü olmayan
bir serviste (NSSM/pipe) stdout'u doldurup kilitlenmeye yol açabilir — bu depoda
`_configure_logging` notunda ölçülmüş bir sınıf. Port listesi VERİ olarak döner,
yazdırma çağırana aittir.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from utils.stm32_kimlik import banner_ayristir

BAUD = 115200

#: Banner'ın yanı sıra toplanan ilgi çekici satırlar (tanılama için).
ILGI_ANAHTARLARI = ("STM_READY", "STM_NACK", "STM_SENS", "STM_ERR", "STM_TELE")


@dataclass(frozen=True)
class PortBilgisi:
    aygit: str
    aciklama: str


def portlari_listele() -> list[PortBilgisi]:
    """Sistemdeki seri portlar. `pyserial` yoksa boş liste (çağıran karar verir)."""
    try:
        from serial.tools import list_ports
    except Exception:
        return []
    return [PortBilgisi(p.device, p.description or "") for p in list_ports.comports()]


def port_adaylari(istenen: str | None = None) -> list[str]:
    """Denenecek portlar — ST-Link VCP ÖNCE.

    ⚠️ Öncelik ölçütü `utils/stm32_transport` ile aynı olmalı: backend orayı kullanıyor,
    bu modül de tanılama/yakma sonrası doğrulamada kullanıyor. İkisi ayrı port seçerse
    "backend bağlı ama betik başka kartı okuyor" durumu doğar.
    """
    if istenen:
        return [istenen]
    hepsi = portlari_listele()
    oncelikli = [p.aygit for p in hepsi if any(k in p.aciklama.upper() for k in ("ST-LINK", "STLINK", "STM"))]
    return oncelikli + [p.aygit for p in hepsi if p.aygit not in oncelikli]


def banner_dinle(port: str, sure: float = 12.0) -> tuple[int | None, list[str]]:
    """(kanal_sayısı | None, toplanan satırlar).

    Kart açılış banner'ını YALNIZ RESET'te basar; `sure` boyunca dinlenir. Banner
    ayrıştırılır ayrıştırılmaz döner (beklemeye gerek yok).

    ⚠️ Seri port TEK KULLANICILIDIR: backend çalışıyorsa portu tutar ve burada
    `SerialException` yükselir. Çağıran bunu YUTMAMALI, açıkça söylemeli — "hiçbir şey
    duyulmadı" ile "port meşgul" farklı arızalardır.
    """
    import serial  # yerel import: modül, pyserial olmayan ortamda da import edilebilsin

    satirlar: list[str] = []
    with serial.Serial(port, BAUD, timeout=0.3) as s:
        bitis = time.monotonic() + sure
        tampon = b""
        while time.monotonic() < bitis:
            tampon += s.read(4096)
            while b"\n" in tampon:
                ham, tampon = tampon.split(b"\n", 1)
                satir = ham.decode("utf-8", "replace").strip()
                if not satir:
                    continue
                if any(k in satir for k in ILGI_ANAHTARLARI):
                    satirlar.append(satir)
                kimlik = banner_ayristir(satir)
                if kimlik:
                    return kimlik.kanal, satirlar
    return None, satirlar
