# Author: mertaygn, cglrgrkn
"""STM32 <-> PEMF uyumluluk denetimi (2026-09-03) duzeltmeleri icin kapilar.

Kaynak: firmware/backend/frontend katmanlarinin STM seri protokol sozlesmesi karsilastirildi;
onaylanan uyumsuzluklardan M2 ve M6 icin regresyon kapilari (M4 frontend TS -> typecheck;
M7 firmware -> tezgah/reflash; M3 frontend etiket -> jest).

- M2: firmware NTC termal kesme yeniden acilirsa gonderdigi STM_EVT dizesi backend'de
  PARSE EDILMELI (CRITICAL olay + bobinleri sifirla). Dal yoksa satir sessizce yutulur.
- M6: donanim-surumu TEK KAYNAK (utils.path_utils.HARDWARE_VERSION); system_router ve
  live_state ELLE 'HW-...' literali icermemeli (eskiden 2025.1 vs 2026.1 ayrisiyordu).
"""

import logging
import pathlib
import re
import sys

_KOK = pathlib.Path(__file__).resolve().parents[1]
if str(_KOK) not in sys.path:
    sys.path.insert(0, str(_KOK))

from event_bus import EventPriority  # noqa: E402
from headless_core import HeadlessCore  # noqa: E402


class _YakalayanBus:
    """event_bus.publish cagrilarini yakalayan minimal sahte veri yolu."""

    def __init__(self):
        self.olaylar = []  # (event_type, data, priority)

    def publish(self, event_type, data, priority=None, source=None):
        self.olaylar.append((event_type, data, priority))


def _core():
    """__init__'i baypas ederek yalniz _handle_stm_line'in ihtiyaci alanlari kuran core."""
    c = HeadlessCore.__new__(HeadlessCore)
    c.logger = logging.getLogger("test-stm-uyumluluk")
    c.event_bus = _YakalayanBus()
    return c


# --- M2: STM_EVT termal kesme parse ---------------------------------------------------

# Firmware'in PEMF_NTC_TERMAL_ENABLED=1 iken gonderdigi gercek dize (main.c).
_STM_EVT_TERMAL = "-> STM_EVT: TERMAL kesme (>=48C) - bobin(ler) durduruldu, sogumada kilitli."


def test_M2_stm_evt_termal_KRITIK_olay_yayinlar():
    """STM_EVT satiri hardware.stm.thermal_cutoff CRITICAL olayi uretmeli.

    Dal SILINIRSE satir hicbir kosula uymaz (STM_ERR'e de esit degil), jenerik logger'a
    duser -> thermal_cutoff HIC yayinlanmaz -> bu test kirilir (mutasyon-korumali)."""
    c = _core()
    c._handle_stm_line(_STM_EVT_TERMAL)
    termal = [e for e in c.event_bus.olaylar if e[0] == "hardware.stm.thermal_cutoff"]
    assert len(termal) == 1, "STM_EVT icin thermal_cutoff olayi yayinlanmadi (parse dali eksik?)"
    assert termal[0][2] == EventPriority.CRITICAL, "termal kesme CRITICAL oncelikte olmali"


def test_M2_stm_evt_TUM_bobinleri_sifirlar():
    """Termal kesmede 5 bobinin hepsi icin duty=0 / running=False olayi gitmeli."""
    c = _core()
    c._handle_stm_line(_STM_EVT_TERMAL)
    sifirlar = [e for e in c.event_bus.olaylar if e[0] == "hardware.stm.coil_update"]
    assert len(sifirlar) == HeadlessCore.STM_COIL_COUNT, (
        f"beklenen {HeadlessCore.STM_COIL_COUNT} bobin-sifirlama, gelen {len(sifirlar)}"
    )
    for _, data, _p in sifirlar:
        assert data["duty"] == 0.0 and data["running"] is False, "termal kesmede bobin sifirlanmadi (guvenlik)"


def test_M2_stm_evt_STM_ERR_dali_ile_KARISMAZ():
    """STM_EVT, STM_ERR alt-dizesi DEGILDIR; yanlislikla error dalina dusmemeli."""
    c = _core()
    c._handle_stm_line(_STM_EVT_TERMAL)
    hata = [e for e in c.event_bus.olaylar if e[0] == "hardware.stm.error"]
    assert not hata, "STM_EVT yanlislikla hardware.stm.error olarak siniflandirildi"


# --- M6: donanim-surumu tek kaynak --------------------------------------------------


def test_M6_donanim_surumu_TEK_KAYNAK_elle_literal_yok():
    """system_router ve live_state ELLE 'HW-20xx' literali icermemeli.

    Eskiden system_router 'HW-2025.1', live_state 'HW-2026.1' derdi -> ayni /status
    uclari celisen deger donuyordu. Ikisi de utils.path_utils.HARDWARE_VERSION okumali.
    Yeniden bir literal eklenirse bu test kirilir."""
    for rel in ("servers/system_router.py", "servers/live_state.py"):
        src = (_KOK / rel).read_text(encoding="utf-8")
        literaller = re.findall(r'"HW-\d[^"]*"', src)
        assert not literaller, (
            f"{rel} elle donanim-surumu literali iceriyor {literaller}; path_utils.HARDWARE_VERSION kullan (tek kaynak)"
        )


def test_M6_live_state_runtime_degeri_tek_kaynakla_esit():
    import servers.live_state as ls
    from utils.path_utils import HARDWARE_VERSION

    assert ls._live_state["system"]["hardwareVersion"] == HARDWARE_VERSION
