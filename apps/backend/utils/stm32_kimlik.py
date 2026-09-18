# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""STM32 FIRMWARE KIMLIGI — banner ayristirma + UYUM DENETIMI (2026-09-18).

⚠️ COZDUGU ARIZA (olculdu, `docs/stm32-uzaktan-guncelleme-plani.md` §1):
Kart acilista KIM OLDUGUNU zaten soyluyor:

    -> STM_READY: DDS v2.3 (7-ch UNIPOLAR tek-bacak uni=0x60 + HW_SYNC@PB1) Waiting for commands...

Backend ise `headless_core.py` icinde yalnizca su kontrolu yapiyordu:

    if "STM_READY" in decoded or "STM_OK:" in decoded:
        self._set_stm_connected(True)          # ⚠️ ICERIGE HIC BAKMIYOR

Sonucu SESSIZ bir ariza sinifi: eski firmware (5 bobin) 88 baytlik paket bekler, backend 120
bayt gonderir → eski firmware ilk 88 bayti paket sanar, CRC'yi YANLIS OFSETTEN okur,
`Coil_SendNack("CRC")` doner ve **PWM durumuna hic dokunmaz**. Ama `STM_READY` basildigi icin
uygulama STM'i **BAGLI** gosterir.

    Belirti: baglanti gostergesi YESIL, hata penceresi YOK, hicbir bobin baslamiyor
             (bobin 1-5 dahil). Bugun bunu ayirt etmenin tek yolu UART'i ELLE dinlemek.

Bu modul banner'i ayristirir ve kartin soyledigi kanal sayisini backend'in PAKETLEDIGI
genislikle (`utils.stm32_protocol_limits` / `utils.stm32_transport.STM_PAKET_BOBIN_SAYISI`)
karsilastirir.

⚠️ TEK KAYNAK: desen eskiden `scripts/stm_firmware_kimligi.py` icindeydi. KOPYALANMADI —
o betik artik BURADAN import eder. (Bu depoda ayni deseni iki yere yazmanin bedeli olculdu:
`_DB_ERROR` demetleri iki DB modulunde sessizce AYRISMISTI.)

⚠️ GUVENLIK DEGISMEZI: bu modul bir KARAR uretir, bir KILIT degildir. Uyumsuzluk seans
baslatmayi reddeder ama ACIL DURDURMAYI **ASLA** engellemez — depo kurali: bobinler her
seyden once durur (bkz. bellek `pemf-device-safety-shutdown`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Firmware'in bastigi kip sozlugu (`firmware/stm32_pemf/Core/Src/main.c:1012`).
#: ⚠️ Kip dizesi MASKEDEN turer; elle yazilan etiket 2026-09-11 karma yapilandirmasinda
#: YALAN soylerdi. Buraya yeni bir kip eklenirse firmware'deki uclu ile birlikte guncellenir.
KIPLER = ("SYM-BIPOLAR", "UNIPOLAR tek-bacak", "KARMA")

#: `-> STM_READY: DDS v2.3 (7-ch UNIPOLAR tek-bacak uni=0x60 + HW_SYNC@PB1) ...`
#: ⚠️ `surum` tembel (`.+?`) ve parantez ONCESINDE biter; kip sozlukten secilir ki
#: "UNIPOLAR tek-bacak" gibi BOSLUKLU etiket ikiye bolunmesin.
BANNER_DESENI = re.compile(
    r"STM_READY:\s*(?P<surum>.+?)\s*\(\s*(?P<kanal>\d+)-ch\s+"
    r"(?P<kip>" + "|".join(re.escape(k) for k in KIPLER) + r")"
    r"(?:\s+uni=0x(?P<maske>[0-9A-Fa-f]+))?"
)


@dataclass(frozen=True)
class Stm32Kimlik:
    """Kartin banner'da BEYAN ETTIGI kimlik. `maske` yoksa None (eski banner)."""

    surum: str
    kanal: int
    kip: str
    maske: int | None
    ham: str


def banner_ayristir(satir: str) -> Stm32Kimlik | None:
    """`STM_READY` satirindan kimligi cikar; taninmazsa None."""
    if not satir:
        return None
    m = BANNER_DESENI.search(satir)
    if not m:
        return None
    ham_maske = m.group("maske")
    return Stm32Kimlik(
        surum=m.group("surum").strip(),
        kanal=int(m.group("kanal")),
        kip=m.group("kip"),
        maske=int(ham_maske, 16) if ham_maske else None,
        ham=satir.strip(),
    )


#: `uyum_denetle` sonucu: (uyumlu, sebep). `uyumlu` UC DURUMLU olabilir —
#: True = eslesti · False = KESIN uyumsuz · None = BILINMIYOR (banner taninmadi).
def uyum_denetle(kimlik: Stm32Kimlik | None, paket_kanal: int) -> tuple[bool | None, str]:
    """Kartin beyan ettigi kanal sayisi ile BIZIM paketledigimiz genislik uyusuyor mu?

    ⚠️ NEDEN "BILINMIYOR" DIYE UCUNCU BIR DURUM VAR — ve neden o seansi ENGELLEMEZ:
    Banner ayristirilamazsa iki ihtimal var: (a) gercekten eski/yabanci firmware,
    (b) ileride banner bicimi degismis AMA uyumlu bir firmware. (b)'de seansi reddetmek
    CALISAN bir klinigi durdurur. Tedaviyi durdurmak da bir zarardir; bu yuzden yalnizca
    KESIN uyumsuzlukta (banner okundu VE kanal farkli) reddediyoruz. "Bilinmiyor" hali
    log'da ve `/api/health`te GORUNUR — destek muhendisi ayirt edebilsin.

    ⚠️ Zaten uyumsuz firmware'de bobinler CALISMIYOR; kapinin kazandirdigi sey calisirlik
    degil, TEsHIS: "yesil ama hicbir sey olmuyor" yerine EYLEM soyleyen bir mesaj.
    """
    if kimlik is None:
        return None, (
            "Kartin firmware kimligi OKUNAMADI (STM_READY satiri taninmadi). Eski ya da "
            "yabanci bir firmware olabilir. Dogrulama: python scripts/stm_firmware_kimligi.py"
        )
    if kimlik.kanal == paket_kanal:
        return True, ""
    return False, (
        f"Kart {kimlik.kanal} kanalli firmware kosuyor ({kimlik.surum}), uygulama "
        f"{paket_kanal} kanalli paket gonderiyor. Paket genisligi birebir olmak ZORUNDA — "
        f"aksi halde firmware her paketi NACK'ler ve HICBIR bobin calismaz. "
        f"Yapilacak: docs/SAHA-ISLERI-REHBERI.md B-2 ile STM'i yeniden yakin."
    )
