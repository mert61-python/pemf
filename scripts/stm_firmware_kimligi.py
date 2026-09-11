# -*- coding: utf-8 -*-
# Author: mertaygn
"""KARTTA HANGİ FIRMWARE YÜKLÜ? — UART'ı dinler ve söyler.

===============================================================================
NEDEN VAR (2026-09-11, saha sorusu)
===============================================================================
Sahip sordu: *"stm uygulamada görünüyor ama pwm alıp başlamıyor, sebebi eski firmware
olabilir mi"*. Evet — ve bu **tam olarak** eski firmware'in belirtisi:

| | eski (5 bobin) | yeni (7 bobin) |
|---|---|---|
| Beklediği paket | **88 bayt** | **120 bayt** |

Backend 120 bayt gönderir. Eski firmware akışın **ilk 88 baytını** paket sanıp çerçeveler,
CRC'yi ilk 84 bayt üzerinden hesaplar — gerçek CRC alanı ise 120 baytlık düzende 116.
ofsettedir. Eşleşmez → `Coil_SendNack("CRC")` → `pkt_ok = 0` → **PWM durumuna HİÇ
dokunulmaz**. Ama `STM_READY` yine basıldığı için uygulama STM'i **BAĞLI GÖRÜR**.
Sonuç: "bağlı ama hiçbir bobin başlamıyor" — bobin 1-5 dahil.

⚠️ Bu belirti sessizdir: bağlantı göstergesi yeşil, hata penceresi yok. Ayırt etmenin
tek yolu UART'taki açılış satırını OKUMAKTIR. Bu betik onu okur.

===============================================================================
KULLANIM
===============================================================================
    python scripts/stm_firmware_kimligi.py            # portu kendi bulur
    python scripts/stm_firmware_kimligi.py --port COM10
    python scripts/stm_firmware_kimligi.py --sure 20  # daha uzun dinle

⚠️ **BACKEND KAPALI OLMALI.** Seri port tek kullanıcılıdır; PEMF_Backend çalışıyorsa
portu tutar ve bu betik "erişim reddedildi" alır. Betik bunu açıkça söyler.

Kart açılış satırını YALNIZ RESET'te basar. Betik bir şey duymazsa karttaki siyah
RESET düğmesine bas — banner o an akar.
"""

from __future__ import annotations

import argparse
import re
import sys
import time

BAUD = 115200

# `-> STM_READY: DDS v2.3 (7-ch UNIPOLAR tek-bacak + HW_SYNC@PB1) ...`
READY_DESENI = re.compile(r"STM_READY:.*?\((?P<kanal>\d+)-ch\s+(?P<kip>[^)+]*)")


def _portlari_bul(istenen: str | None) -> list[str]:
    try:
        from serial.tools import list_ports
    except Exception:
        return [istenen] if istenen else []
    if istenen:
        return [istenen]
    hepsi = list(list_ports.comports())
    # ST-Link VCP'yi öne al (backend de böyle yapıyor: utils/stm32_transport.py)
    oncelikli = [
        p.device
        for p in hepsi
        if any(k in ((p.description or "") + (p.manufacturer or "")).upper() for k in ("ST-LINK", "STLINK", "STM"))
    ]
    digerleri = [p.device for p in hepsi if p.device not in oncelikli]
    if hepsi:
        print("Bulunan portlar:")
        for p in hepsi:
            print(f"  {p.device}  {p.description}")
    return oncelikli + digerleri


def _dinle(port: str, sure: float) -> tuple[int | None, list[str]]:
    """@return (kanal_sayisi | None, toplanan ilgili satirlar)"""
    import serial

    satirlar: list[str] = []
    kanal: int | None = None
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
                if any(k in satir for k in ("STM_READY", "STM_NACK", "STM_SENS", "STM_ERR", "STM_TELE")):
                    satirlar.append(satir)
                m = READY_DESENI.search(satir)
                if m:
                    kanal = int(m.group("kanal"))
                    return kanal, satirlar
    return kanal, satirlar


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default=None, help="orn. COM10 (verilmezse otomatik aranir)")
    ap.add_argument("--sure", type=float, default=12.0, help="her portta dinleme suresi (sn)")
    a = ap.parse_args()

    portlar = _portlari_bul(a.port)
    if not portlar:
        print("[HATA] Hic seri port bulunamadi. Kart USB'ye takili mi?")
        return 2

    for port in portlar:
        print(f"\n=== {port} dinleniyor ({a.sure:.0f} sn) — banner gelmezse karttaki RESET'e bas ===")
        try:
            kanal, satirlar = _dinle(port, a.sure)
        except Exception as e:
            mesaj = str(e)
            if "Access is denied" in mesaj or "erisim" in mesaj.lower() or "PermissionError" in type(e).__name__:
                print(f"[{port}] PORT MESGUL — PEMF_Backend calisiyor olabilir. Once onu KAPAT.")
            else:
                print(f"[{port}] acilamadi: {e}")
            continue

        for s in satirlar:
            print("   " + s)

        if kanal is None:
            print(f"[{port}] STM_READY duyulmadi. RESET'e basip tekrar dene (ya da bu port STM degil).")
            continue

        print()
        print("=" * 72)
        if kanal >= 7:
            print(f"  ✅ YENI FIRMWARE YUKLU  ({kanal}-kanal, 120 baytlik paket)")
            print("     Bobinler baslamiyorsa sebep firmware DEGIL — baska yere bakilmali.")
        else:
            print(f"  ❌ ESKI FIRMWARE YUKLU  ({kanal}-kanal, 88 baytlik paket bekliyor)")
            print("     Yeni client 120 bayt gonderiyor -> CRC uyusmuyor -> STM_NACK ->")
            print("     HICBIR BOBIN BASLAMAZ (1-5 dahil), ama uygulama STM'i BAGLI GORUR.")
            print("     COZUM: masaustundeki PEMF_STM32_workspace_2026-09-11 projesini")
            print("            CubeIDE ile karta yukle (reflash).")
        print("=" * 72)
        if any("STM_NACK" in s for s in satirlar):
            print("  NOT: STM_NACK satiri da goruldu -> paket REDDEDILIYOR (teshis dogrulandi).")
        return 0 if kanal >= 7 else 1

    print("\n[SONUC] Hicbir portta STM_READY duyulmadi — firmware kimligi BELIRLENEMEDI.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
