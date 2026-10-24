# Author: mertaygn, cglrgrkn
"""T-b (Y195) — sahte yakıcıların ortak `-l st-link` yanıtı: yakma akışı artık ST-Link'i SERİ NUMARASIYLA seçer (`stm_yakma.stlink_sec`),
yani her yakıcı sahtesi (EN ALT kat, `stm_yakma._kos`) prob listesini de GERÇEK biçimde vermeli. Biçim tezgâh çıktısındaki satır:
`ST-LINK SN  : <SN>` (`DENETIM/t2/kanit/C1_rst_once.txt`)."""

from __future__ import annotations

TEK_SN = "066DFF565251887067064422"


def liste(*sn_ler: str) -> str:
    """`STM32_Programmer_CLI -l st-link` çıktısı (prob başına bir blok)."""
    govde = "".join(
        f"ST-Link Probe {i} :\n   ST-LINK SN  : {sn}\n   ST-LINK FW  : V2J46M31\n   Board Name  : NUCLEO-F429ZI\n"
        for i, sn in enumerate(sn_ler or (TEK_SN,))
    )
    return (
        "-------- Connected ST-LINK Probes List --------\n\n"
        + govde
        + "-----------------------------------------------\n"
    )


def listeli(kos, *sn_ler: str):
    """Bir `_kos` sahtesini sarar: `-l st-link` → prob listesi (varsayılan tek prob `TEK_SN`); diğer komutlar sahteye gider."""

    def _kos(cli, argumanlar, timeout=300.0):
        if list(argumanlar)[:1] == ["-l"]:
            return 0, liste(*sn_ler)
        return kos(cli, argumanlar, timeout)

    return _kos
