# Author: mertaygn, cglrgrkn
"""Y48 (sahip, S4) — ESP8266 aynı kimlikli STOP'u ikinci kez alınca yalnız onaylamaz, STOP'u YENİDEN UYGULAR (STOP
idempotent). ESP kodu silinmez (Ö.4-Y7); değişiklik kodda, yakma ESP dönüşünde.

ÖLÇÜLEN KUSUR (bu aparatla, HEAD): tekrar önbelleği (8 girdilik halka) aynı `command_id`'yi görünce STOP için YALNIZ
`ACK(success=true)` yeniden gönderip dönüyordu — STOP UYGULANMIYORDU. Önceki STOP'tan sonra araya bir START girdiyse
(ör. teyitsiz E-stop'un yeniden denemesi, aynı kimlikle yeniden yayınlanan STOP) bobin ENERJİLİ kalır ama firmware
"durdu" ACK'i döner → backend E-stop'u "teyitli" sayar.

ARAÇ: GERÇEK `processControlCommand` + `isCommandProcessed` + `addCommandToCache` + önbellek global'leri `.ino`'dan BAYT
BAYT kesilip ana makinede derlenir (`tests/esp8266_komut_aparat.py`); gerçek `SharedDefs.h` (hız sınırlayıcı),
`SensorManager`, `CoilController.h` bildirimi. Bobin davranışı modeldir (START → etkin, STOP → durgun).
Ö.4-Y8: STOP yalnız ARTAR — bu değişiklik STOP'u hiçbir koşulda kapılamaz/geciktirmez.
"""

from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def exe(tmp_path_factory):
    import esp8266_komut_aparat as ka

    return ka.derle(tmp_path_factory.mktemp("esp8266_komut"))


def _kos(exe, senaryo: str, tmp_path):
    import esp8266_komut_aparat as ka

    return ka.kos(exe, senaryo, tmp_path)


_START = "CMD start {k} freq=100 duty=50 duration=60\n"


def test_KRITIK_Y48_ayni_kimlikli_STOP_arada_START_varken_bobini_DURDURUR(exe, tmp_path):
    o = _kos(exe, "CMD stop s1\n" + _START.format(k="a1") + "DURUM\nCMD stop s1\nDURUM\n", tmp_path)
    durum = [x[1] for x in o if x[0] == "S"]
    assert durum[0] is True, f"aparat: START bobini etkinleştirmedi {o}"
    son_stop = max(i for i, x in enumerate(o) if x[0] == "A" and x[1] == "s1")
    once = o[:son_stop]
    assert ("C", "STOP", 0, 0, 0) in once[once.index(("A", "a1", True)) :], (
        f"aynı kimlikli STOP (s1) UYGULANMADI — bobin enerjili kaldı: {o}"
    )
    assert durum[-1] is False, f"ikinci STOP sonrası bobin hâlâ ETKİN: {o}"
    assert o[son_stop] == ("A", "s1", True), f"ACK gerçek durumu söylemiyor: {o[son_stop]}"


def test_KRITIK_Y48_tekrar_STOP_icin_TEK_ACK_ve_ACK_gercek_durumdan(exe, tmp_path):
    o = _kos(exe, "CMD stop s1\n" + _START.format(k="a1") + "CMD stop s1\nCMD stop s1\nDURUM\n", tmp_path)
    acklar = [x for x in o if x[0] == "A" and x[1] == "s1"]
    assert len(acklar) == 3, f"üç STOP iletisine {len(acklar)} ACK (her ileti TEK ACK): {acklar}"
    assert all(a[2] for a in acklar) and o[-1] == ("S", False), o


def test_KARSIT_Y48_ayni_kimlikli_START_YENIDEN_uygulanmaz(exe, tmp_path):
    """Tekrar önbelleğinin asıl işi (yinelenen START'ı yutmak) korunur: aynı kimlikli START bobini YENİDEN ENERJİLEMEZ."""
    o = _kos(exe, _START.format(k="a1") + "CMD stop s1\n" + _START.format(k="a1") + "DURUM\n", tmp_path)
    assert o[-1] == ("S", False), f"aynı kimlikli START yeniden UYGULANDI (yinelenen yayın bobini enerjiledi): {o}"
    assert sum(1 for x in o if x[:2] == ("C", "START")) == 1, o


def test_KARSIT_Y48_STOP_hiz_sinirina_takilmaz_ve_kimliksiz_STOP_uygulanir(exe, tmp_path):
    sen = (
        _START.format(k="a1")
        + "".join(f"CMD stop s{i}\n" for i in range(8))
        + _START.format(k="a2")
        + "CMD stop -\nDURUM\n"
    )
    o = _kos(exe, sen, tmp_path)
    assert sum(1 for x in o if x[:2] == ("C", "STOP")) == 9, f"STOP'lar hız sınırına takıldı ya da kimliksiz düştü: {o}"
    assert o[-1] == ("S", False), o
