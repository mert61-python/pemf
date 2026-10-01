# Author: mertaygn, cglrgrkn
"""D1.33 · B-10.158 · B-10.164 — STM ACK ayrıştırma kapıları firmware ACK etiketlerinden TÜRER; düşük-duty
"çalışıyor" telafisi DAVRANIŞLA ölçülür.

ÖLÇÜLEN KÖRLÜK:
  * `test_son16_gaps::test_stm_ok_duty_TAMSAYI_yuzde_kirpmasi_telafi_edilir` yalnız YORUM metnini
    ("TAMSAYI yuzde") ve `callable(_parse_stm_ok)`ı ölçüyordu — telafi satırı `if False:` altına alınsa
    YEŞİL. Firmware ACK'i duty'yi tamsayı yüzde basar (`(long)(duty*100)`): %1'in altındaki duty `D=0`
    gelir; telafi olmazsa SÜRÜLEN bobin arayüzde "durdu" görünür (operatör bobini kapalı sanır).
  * `test_stm_surus_kipi_ucu._ack_satiri` ACK'i testin KENDİ dizesinden kuruyordu — firmware `K=` yerine
    `KIP=`, `D=` yerine `DUTY=` bassa ayrıştırıcı ile firmware ayrışır, test yeşil kalırdı.

Bu kapı ACK satırını `firmware/stm32_pemf/Core/Src/main.c`'nin YORUMU SOYULMUŞ hâlinden (`c_soy`) kurar:
`ack_etiket` dizisi, değer ayracı ve `etkin` maskesini basan çağrıdan HEMEN önceki etiket. Yorumdaki
kopya sayılmaz. Satır GERÇEK `HeadlessCore._parse_stm_ok` ile çözülür.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from c_soyucu import c_soy

KOK = Path(__file__).resolve().parents[1]
MAIN_C = KOK / "firmware" / "stm32_pemf" / "Core" / "Src" / "main.c"
_DIZE = r'"((?:[^"\\]|\\.)*)"'


class _Cekirdek:
    STM_COIL_COUNT = 7


def _parse(satir: str):
    import headless_core

    return headless_core.HeadlessCore._parse_stm_ok(_Cekirdek(), satir)


def ack_bicimi(src: str) -> dict:
    """Yorumu soyulmuş main.c'den ACK biçimi: 4 grup etiketi, değer ayracı, kip etiketi."""
    soy = c_soy(src)
    m = re.search(r"static\s+const\s+char\s*\*\s*const\s+ack_etiket\s*\[\s*4\s*\]\s*=\s*\{(.*?)\}\s*;", soy, re.S)
    assert m, "main.c'de (yorum dışı) `ack_etiket[4]` dizisi yok — ACK biçimi değişmiş"
    etiketler = re.findall(_DIZE, m.group(1))
    assert len(etiketler) == 4, f"ack_etiket 4 öğe değil: {etiketler}"
    ayrac = re.search(
        r"if\s*\(\s*ai\s*>\s*0U\s*\)\s*\{\s*len\s*=\s*Coil_AckMetin\(\s*ack_msg\s*,\s*sizeof\(ack_msg\)\s*,\s*len\s*,\s*"
        + _DIZE,
        soy,
    )
    assert ayrac, "değer ayracı çağrısı (yorum dışı) bulunamadı"
    kip = re.search(
        r"Coil_AckMetin\(\s*ack_msg\s*,\s*sizeof\(ack_msg\)\s*,\s*len\s*,\s*" + _DIZE + r"\s*\)\s*;\s*"
        r"len\s*=\s*Coil_AckSayi\(\s*ack_msg\s*,\s*sizeof\(ack_msg\)\s*,\s*len\s*,\s*\(long\)\s*etkin\s*\)",
        soy,
    )
    assert kip, "etkin kip maskesini basan çağrı (yorum dışı) bulunamadı"
    return {"etiketler": etiketler, "ayrac": ayrac.group(1), "kip": kip.group(1)}


def ack_satiri(bicim: dict, gruplar: list[list[int]], maske: int | None) -> str:
    satir = "".join(e + bicim["ayrac"].join(str(v) for v in deg) for e, deg in zip(bicim["etiketler"], gruplar))
    if maske is not None:
        satir += bicim["kip"] + str(maske)
    return satir


@pytest.fixture(scope="module")
def bicim():
    return ack_bicimi(MAIN_C.read_text(encoding="utf-8", errors="replace"))


# ── (b) ACK biçimi firmware'den ─────────────────────────────────────────────


def test_KRITIK_firmware_ACK_satiri_GERCEK_ayristiriciyla_cozulur(bicim):
    duty = [25, 40, 0, 99, 1, 50, 75]
    faz = [0, 90, 180, 270, 45, 10, 5]
    frek = [50, 100, 10, 1000, 7, 25000, 1]
    sure = [10, 20, 5, 1, 30, 60, 2]
    maske = 0x60
    g = _parse(ack_satiri(bicim, [duty, faz, frek, sure], maske))
    assert len(g) == 7, f"firmware biçimli ACK'ten {len(g)} bobin çözüldü (7 bekleniyordu) — biçim ayrışmış"
    for i, u in enumerate(g):
        assert u["coil_id"] == i + 1
        assert (u["duty"], u["phase"], u["freq"], u["duration_min"]) == (duty[i], faz[i], frek[i], sure[i]), u
        assert "unipolar" in u, "firmware'in kip etiketi ayrıştırıcıda tanınmıyor (etkin kip arayüze ulaşmaz)"
        assert u["unipolar"] is bool((maske >> i) & 1), u


def test_KARSIT_kip_etiketsiz_ACK_unipolar_anahtari_KOYMAZ(bicim):
    """Eski firmware (`K=` basmayan) canlı durumu kirletmemeli — ve kapının 'unipolar var' iddiası anlamlı olsun."""
    g = _parse(ack_satiri(bicim, [[25] * 7, [0] * 7, [50] * 7, [10] * 7], None))
    assert len(g) == 7 and all("unipolar" not in u for u in g)


def test_ARAC_ack_bicimi_YORUMDAKI_kopyayi_saymaz():
    """Öz-denetim: gerçek kip etiketi değişip eski hâli yorumda kalırsa okuyucu YORUMU okumamalı."""
    src = MAIN_C.read_text(encoding="utf-8", errors="replace")
    gercek = 'len = Coil_AckMetin(ack_msg, sizeof(ack_msg), len, " K=");'
    assert src.count(gercek) == 1
    mutant = src.replace(
        gercek,
        '/* len = Coil_AckMetin(ack_msg, sizeof(ack_msg), len, " K="); */\n'
        '          len = Coil_AckMetin(ack_msg, sizeof(ack_msg), len, " KIP=");',
    )
    assert ack_bicimi(mutant)["kip"] == " KIP="


# ── (a) düşük-duty "çalışıyor" telafisi ─────────────────────────────────────


def test_KRITIK_dusuk_duty_D0_ama_frekans_ve_sure_VARSA_calisiyor_sayilir(bicim):
    g = _parse(ack_satiri(bicim, [[0] * 7, [0] * 7, [10] * 7, [5] * 7], 0))
    assert len(g) == 7
    durdu = [u["coil_id"] for u in g if not (u["running"] and u["pwm_active"])]
    assert durdu == [], (
        f"%1 altı duty (ACK'te D=0) ama F=10 T=5 sürülen bobinler 'durdu' göründü: {durdu} — operatör bobini kapalı sanar"
    )


@pytest.mark.parametrize("frek,sure", [(0, 5), (10, 0)], ids=["frekans_0", "sure_0"])
def test_KARSIT_gercekten_duran_bobin_calisiyor_SAYILMAZ(bicim, frek, sure):
    g = _parse(ack_satiri(bicim, [[0] * 7, [0] * 7, [frek] * 7, [sure] * 7], 0))
    assert len(g) == 7 and not any(u["running"] or u["pwm_active"] for u in g), g
