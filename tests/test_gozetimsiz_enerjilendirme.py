# Author: mertaygn, cglrgrkn
"""GÖZETİMSİZ ENERJİLENDİRME SINIRI — süre verilmeyen bobin GÜNLERCE sürmemeli.

KAMPANYA BULGUSU (2026-08-14, S03). `POST /api/coil/1/control {start:true, duration:0}`
seans açmadan 200 döndü ve bobin kendiliğinden durmadı; ölçülen yazılım deadline'ı
**599 940 sn ≈ 6,9 GÜN**. Ayrıca `duration:-60` sessizce KABUL edildi ve `duration:0` ile
aynı davrandı — yani bir yazım hatası bobini günlerce enerjili bırakabiliyordu.

⚠️ AYRIM (bu testlerin varlık sebebi): 9999 dakika bir KLİNİK sınır DEĞİL, **STM32 firmware
protokol sınırıdır** — `utils/stm32_protocol_limits.DURATION_MAX_MINUTES` ve
`test_stm32_source_parity.py` onu firmware kaynağıyla eşleştirir. Kusur, süre verilmediğinde
yazılım deadline'ının PROTOKOL TAVANINA düşmesiydi: "protokol maksimumu" ile "güvenli
gözetimsiz varsayılan" birbirine karışmıştı. Protokol sabiti DEĞİŞMEZ (firmware pariteyi
bozmayız); ayrı ve açıkça adlandırılmış bir klinik varsayılan kullanılır.

⚠️ freq/duty/48°C safety-limit'lerine DOKUNULMAZ — onlar sahip kararıyla kaldırıldı. Buradaki
sınır SÜREdir ve emsali vardır: `ai_router._AI_PRO_MAX_DURATION_MIN = 120` ("Uzaktan
{duration_minutes: 999999} ile günlerce/gözetimsiz PEMF sürüşünü engeller").
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils import stm32_protocol_limits as lim  # noqa: E402


def test_KRITIK_protokol_sabiti_DEGISMEZ_firmware_paritesi(tmp_path):
    """Karşı-kanıt: bu arıza, protokol sabitini küçülterek "düzeltilemez".

    `DURATION_MAX_MINUTES` firmware kaynağıyla eşleşir (bkz. test_stm32_source_parity).
    Küçültmek firmware paritesini bozar ve gerçek uzun tedavileri de keser. Klinik varsayılan
    AYRI bir sabit olmalıdır."""
    assert lim.DURATION_MAX_MINUTES == 9999, (
        "protokol sabiti degistirilmis → firmware paritesi bozulur (yanlis duzeltme yolu)"
    )


def test_KRITIK_sure_verilmeyen_bobin_GUNLERCE_surmez():
    """Süre verilmemişse yazılım deadline'ı klinik bir üst sınıra düşmeli — protokol tavanına DEĞİL."""
    from controllers.hardware_controller import GOZETIMSIZ_VARSAYILAN_DAKIKA

    assert GOZETIMSIZ_VARSAYILAN_DAKIKA <= 120, (
        f"gozetimsiz varsayilan {GOZETIMSIZ_VARSAYILAN_DAKIKA} dk — AI Pro klinik siniri (120 dk) ile "
        "tutarsiz; gunlerce gozetimsiz enerjilendirme kapisi acik kalir"
    )
    assert GOZETIMSIZ_VARSAYILAN_DAKIKA < lim.DURATION_MAX_MINUTES, (
        "gozetimsiz varsayilan hala PROTOKOL TAVANI — asil kusur bu"
    )


def test_KRITIK_NEGATIF_sure_REDDEDILIR():
    """Negatif süre anlamsız bir girdidir; sessizce kabul edilip `0` gibi davranması, bir yazım
    hatasını "günlerce enerjilendirme" komutuna çeviriyordu."""
    from pydantic import ValidationError

    from servers.api_server import CoilControlPayload

    with pytest.raises(ValidationError):
        CoilControlPayload(start=True, freq=20, duty=30, duration=-60)


def test_sifir_sure_hala_KABUL_edilir_karsit_kanit():
    """Karşı-kanıt: `duration=0` ("süre belirtme") GEÇERLİ bir girdidir ve reddedilmemeli —
    yalnızca sonsuz sürmemeli. Bunu da reddetmek Kontrol Paneli'ni bozardı."""
    from servers.api_server import CoilControlPayload

    p = CoilControlPayload(start=True, freq=20, duty=30, duration=0)
    assert p.duration == 0


if __name__ == "__main__":
    import os

    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
