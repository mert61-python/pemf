# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""ACK BEKCISI SONRAKI TESTE SIZMAZ (2026-09-15, CI kosusu 35005619586).

OLCULEN ARIZA. `windows-latest` matrisinde su test dustu:

    tests/test_estop_ack_benzersizligi.py::test_KARSIT_KANIT_timeout_metni_DEGISMEDI
    AssertionError: timeout uyarisi bozuldu: [
        ('⚠️ Bobin 8: start onayi gelmedi …', 'warning'),   <- YABANCI
        ('⚠️ Bobin 8: start onayi gelmedi …', 'warning'),   <- YABANCI
        ('⚠️ Bobin 8: acil durdurma ESP onayi GELMEDI …', 'error'),  <- kendi
        …]

Test kendi listesinin ILK ogesine bakiyordu; kendi uyarisi UCUNCU siradaydi.

KOK NEDEN: `api_server._start_ack_izle_arka_planda` DAEMON THREAD acar
(`start-ack-{coil}`) ve o thread `_START_ACK_TIMEOUT = 2.0` sn bekleyip
`_push_notification` cagirir. Testler 2 sn'den kisa surer -> thread SONRAKI testin
icinde atesler ve o an `_push_notification`a takili olan BASKA testin listesine yazar.
E-stop bekcisi (`estop-ack-{coil}`) ayni desende.

⚠️ NEDEN YERELDE GECIP CI'DA DUSTU: tamamen ZAMANLAMA. Tam suit bu makinede iki kez
yesil gecti. "Kararsiz test" denip gecilecek sinif DEGIL — hangi testi vuracagi
rastgele ve vurdugunda YANLIS bir teshis uretir ("timeout metni bozuldu" derken metin
gayet yerinde).

DUZELTME: `tests/conftest.py` icinde autouse teardown fixture'i `_ack_bekcilerini_bosalt`
— bekleyen Event'leri SET eder (thread oldurulemez, ama beklemesi kisaltilabilir), sonra
`start-ack-*` / `estop-ack-*` thread'lerini join eder ve kayit sozlugunu temizler.

BU DOSYA: sizintiyi KASITLI uretir ve fixture'in onu gercekten bogdugunu olcer.
Fixture kaldirilirsa ikinci test KIRMIZI olur (mutasyonla dogrulandi).
"""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

os.environ.setdefault("PEMF_SIMULATE", "1")


def _api():
    from servers import api_server as api

    return api


def _sizinti_uret(coil_id: int = 8) -> str:
    """Gercek uretim yolunu kullanarak, HICBIR ZAMAN resolve edilmeyecek bir bekci acar.

    ⚠️ Taklit degil: `_start_ack_izle_arka_planda` uretimde start akisinin cagirdigi
    fonksiyondur. Sizintiyi ureten kodu birebir kosturuyoruz.
    """
    api = _api()
    kid = f"start_{coil_id}_sizinti_{int(time.time() * 1e6)}"
    api._register_ack(kid)
    api._start_ack_izle_arka_planda(coil_id, kid, publish_ok=True)
    return kid


def test_ON_KOSUL_bekci_GERCEKTEN_aciliyor():
    """Sizinti uretici calismiyorsa asil test hicbir sey olcmez (sessiz yesil)."""
    _sizinti_uret()
    canli = [t for t in threading.enumerate() if (t.name or "").startswith("start-ack-")]
    assert canli, (
        "start-ack bekcisi HIC acilmadi -> bu dosyadaki sizinti testi KOR kalir "
        "(uretim yolu degistiyse bu dosyayi guncelleyin)"
    )


def test_KRITIK_onceki_testin_bekcisi_SONRAKI_teste_yazmaz(monkeypatch):
    """⚠️ ASIL KAPI.

    Bir onceki test (yukaridaki) bir bekci birakti. Fixture calistiysa o bekci bu test
    baslamadan ONCE bitmis olmali; calismadiysa ~2 sn sonra BU testin listesine yazar.

    MUTASYON: `tests/conftest.py`teki `_ack_bekcilerini_bosalt` fixture'ini sil -> KIRMIZI.
    """
    api = _api()
    uyarilar: list = []
    monkeypatch.setattr(api, "_push_notification", lambda msg, sev="info": uyarilar.append((msg, sev)))

    # Onceki testin bekcisi 2 sn icinde atesleyecekti; fixture onu bogduysa hic gelmez.
    # Bekcinin zaman asimindan UZUN bekle ki "henuz atesleyemedi" ile karistirmayalim.
    time.sleep(api._START_ACK_TIMEOUT + 0.6)

    assert not uyarilar, (
        "ONCEKI testin ack bekcisi BU testin bildirim listesine yazdi -> test-izolasyon "
        f"sizintisi. Sizan kayitlar: {uyarilar!r}\n"
        "Bu sinif CI'da rastgele bir testi dusurur ve YANLIS teshis uretir "
        "(kosu 35005619586: 'timeout metni bozuldu' denirken metin gayet yerindeydi)."
    )


def test_KARSIT_KANIT_bogma_GERCEK_bildirimi_susturmaz(monkeypatch):
    """Fixture "bildirimleri yut"a kaymasin: testin KENDI bekcisi normal calismali.

    Bogma yalnizca test SINIRINDA olur; test ICINDE acilan bir bekci kendi uyarisini
    uretmeye devam eder — yoksa e-stop/start onay kapilari sessizce olur.
    """
    api = _api()
    uyarilar: list = []
    monkeypatch.setattr(api, "_push_notification", lambda msg, sev="info": uyarilar.append((msg, sev)))
    # `_wait_ack`i kisalt: 2 sn beklemeye gerek yok, olculen sey uyarinin URETILMESI.
    orij = api._wait_ack
    monkeypatch.setattr(api, "_wait_ack", lambda cid, timeout: orij(cid, 0.15))

    kid = "start_8_kendi_bekcim"
    api._register_ack(kid)
    api._start_ack_watch(8, kid)  # senkron cagri — kendi thread'imiz yok

    assert any("gelmedi" in m.lower() for m, _ in uyarilar), (
        f"kendi bekcisinin uyarisi URETILMEDI -> bogma fazla genis, gercek kapi olmus: {uyarilar!r}"
    )


def test_KARSIT_KANIT_fixture_conftestte_DURUYOR():
    """Yapisal: fixture silinirse yukaridaki davranissal test 2 sn bekleyip kirmizi olur —
    ama birinin fixture'i "yavas" diye kaldirip testi de silmesi mumkun. Bu iddia, korumanin
    VARLIGINI ucuza kilitler."""
    import re

    src = (KOK / "tests" / "conftest.py").read_text(encoding="utf-8")
    kod = "\n".join(re.sub(r"#.*$", "", s) for s in src.splitlines())
    assert "_ack_bekcilerini_bosalt" in kod, (
        "conftest'teki ack bekcisi bosaltma fixture'i KAYBOLMUS -> sizinti geri gelir"
    )
    assert re.search(r'startswith\(\(\s*["\']start-ack-["\']', kod), (
        "bosaltma artik `start-ack-` thread'lerini hedeflemiyor"
    )
