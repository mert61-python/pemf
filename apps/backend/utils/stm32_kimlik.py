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

Bu modul banner'i ayristirir ve kartin soyledigi kanal sayisini VE banner revizyonundan cikan
PAKET BOYUNU backend'in PAKETLEDIGI genislik/boyla (`utils.stm32_transport.STM_PAKET_BOBIN_SAYISI`,
`STM_PAKET_BOYU`) karsilastirir (D1.103 · B-1.20: yalniz kanal sayisina bakmak 7 kanalli ama 120 baytlik
firmware'i "uyumlu" sayiyordu — o firmware her paketi NACK'ler).

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
#: ⚠️ D1.103 (B-1.20): kip ARTIK yalniz `+`/`)`'dan ONCE eksik olabilir — gercek v2.2 banner'i kipsizdi
#: (`DDS v2.2 (5-ch + HW_SYNC@PB1)`, a0487c3) ve "bilinmiyor"a dusuyordu. TANINMAYAN bir kip kelimesi (gelecekte
#: yeni bir kip) yine eslesmez → "bilinmiyor" (seans ENGELLENMEZ); kipsiz-sayip "eski firmware" diye REDDETMEZ.
BANNER_DESENI = re.compile(
    r"STM_READY:\s*(?P<surum>.+?)\s*\(\s*(?P<kanal>\d+)-ch"
    r"(?:\s+(?P<kip>" + "|".join(re.escape(k) for k in KIPLER) + r")"
    r"(?:\s+uni=0x(?P<maske>[0-9A-Fa-f]+))?"
    r"|(?=\s*[+)]))"
)


@dataclass(frozen=True)
class Stm32Kimlik:
    """Kartin banner'da BEYAN ETTIGI kimlik. `maske` yoksa None (eski banner); `kip` yoksa None (v2.2 banner'i)."""

    surum: str
    kanal: int
    kip: str | None
    maske: int | None
    ham: str


def firmware_paket_boyu(kimlik: Stm32Kimlik) -> int:
    """Banner REVIZYONUNDAN kartin bekledigi paket boyu (bayt; CRC dahil) — D1.103 · B-1.20.

    Git gecmisinden OLCULDU (`tests/test_D1103_firmware_UYUM_karari_REVIZYON_tablosu.py`, iki CubeIDE projesi):
      * 07c2d4c'den (2026-09-10 20:59) once: 5 kanal, kip bayti yok → 16·5 + 8 = 88
      * 07c2d4c … 8aace69 (09-10 20:59 … 09-11 03:04): 7 kanal, kip bayti YOK, banner'da `uni=` YOK → 120
      * e2b63a5 … a280fa4 (09-11 13:53 … 15:21): 7 kanal, kip bayti YOK ama banner `uni=` BASAR → 120.
        ⚠️ Banner'i f367f85+ (121 bayt) ile BAYT BAYT AYNI → banner'dan AYIRT EDILEMEZ (bilinen sinir: ayrim icin
        firmware banner'ina protokol revizyonu eklenip kart yeniden yakilmali — Oturum 13 / sahip Y1-Y2). Burada
        121 sayilir; o kartta tepkisel kapi (sistematik NACK → seans durur, B-1.1) devrededir.
      * f367f85 (09-11 17:38) → HEAD: kip bayti (`unipolar_maskesi`) VAR → 16·7 + 9 = 121
    Kural: duty/faz/frekans float + sure uint32 (bobin basina 16) + baslik 2 + ref_ms 2 + CRC 4; `uni=` alani
    (maske) VARSA sürüş kipi bayti var sayilir."""
    return 16 * kimlik.kanal + 8 + (1 if kimlik.maske is not None else 0)


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
def uyum_denetle(
    kimlik: Stm32Kimlik | None, paket_kanal: int, paket_boyu: int | None = None
) -> tuple[bool | None, str]:
    """Kartin beyan ettigi kanal sayisi VE banner revizyonundan cikan paket boyu, BIZIM paketledigimiz genislik ve
    boyla (`paket_boyu`; verilmezse `utils.stm32_transport.STM_PAKET_BOYU`) uyusuyor mu?

    ⚠️ NEDEN "BILINMIYOR" DIYE UCUNCU BIR DURUM VAR — ve neden o seansi ENGELLEMEZ:
    Banner ayristirilamazsa iki ihtimal var: (a) gercekten eski/yabanci firmware,
    (b) ileride banner bicimi degismis AMA uyumlu bir firmware. (b)'de seansi reddetmek
    CALISAN bir klinigi durdurur. Tedaviyi durdurmak da bir zarardir; bu yuzden yalnizca
    KESIN uyumsuzlukta (banner okundu VE kanal ya da paket boyu farkli) reddediyoruz. "Bilinmiyor" hali
    log'da ve `/api/health`te GORUNUR — destek muhendisi ayirt edebilsin.

    ⚠️ D1.103 (B-1.20): eskiden YALNIZ kanal sayisi karsilastiriliyordu → 7 kanalli ama 120 baytlik (kip baytsiz)
    firmware revizyonlari "uyumlu" sayiliyordu (o kart 121 baytlik her paketi NACK'ler). Paket boyu
    `firmware_paket_boyu` ile banner revizyonundan turer; sahadaki banner (`DDS v2.3 (7-ch KARMA uni=0x60 +
    HW_SYNC@PB1)`, Y7) 121 → UYUMLU kalir.

    ⚠️ Zaten uyumsuz firmware'de bobinler CALISMIYOR; kapinin kazandirdigi sey calisirlik
    degil, TEsHIS: "yesil ama hicbir sey olmuyor" yerine EYLEM soyleyen bir mesaj.
    """
    if kimlik is None:
        return None, (
            "Kartin firmware kimligi OKUNAMADI (STM_READY satiri taninmadi). Eski ya da "
            "yabanci bir firmware olabilir. Dogrulama: python scripts/stm_firmware_kimligi.py"
        )
    if paket_boyu is None:
        from utils.stm32_transport import STM_PAKET_BOYU  # tembel: katman dongusu yok, cagiran boyu verebilir

        paket_boyu = STM_PAKET_BOYU
    fw_boyu = firmware_paket_boyu(kimlik)
    if kimlik.kanal == paket_kanal and fw_boyu == paket_boyu:
        return True, ""
    if kimlik.kanal != paket_kanal:
        return False, (
            f"Kart {kimlik.kanal} kanalli firmware kosuyor ({kimlik.surum}), uygulama "
            f"{paket_kanal} kanalli paket gonderiyor. Paket genisligi birebir olmak ZORUNDA — "
            f"aksi halde firmware her paketi NACK'ler ve HICBIR bobin calismaz. "
            f"Yapilacak: docs/SAHA-ISLERI-REHBERI.md B-2 ile STM'i yeniden yakin."
        )
    return False, (
        f"Kart {kimlik.kanal} kanalli ama {fw_boyu} baytlik paket bekleyen ESKI bir firmware kosuyor "
        f"({kimlik.surum}; banner'da surus kipi alani 'uni=' YOK — 2026-09-10/11 surumu), uygulama {paket_boyu} "
        f"baytlik paket gonderiyor. Paket boyu birebir olmak ZORUNDA — aksi halde firmware her paketi NACK'ler ve "
        f"HICBIR bobin calismaz. Yapilacak: docs/SAHA-ISLERI-REHBERI.md B-2 ile STM'i yeniden yakin."
    )
