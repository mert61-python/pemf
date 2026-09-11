# -*- coding: utf-8 -*-
# Author: mertaygn
"""BOBİN SAYISI TEK KAYNAK — sessizce bayatlayan sabitlerin kapısı.

===============================================================================
2026-09-11'de README denetiminde BULUNDU
===============================================================================
`utils/stm32_protocol_limits.py` içinde `STM32_NUM_COILS = 5` yazıyordu — 2026-09-10'daki
7-bobin geçişinde (bobin 6-7 ESP8266'dan STM'e taşındı) **güncellenmemişti**.

Bugün hiçbir yerde kullanılmıyordu (grep: yalnız tanımın kendisi), yani zarar vermedi. Ama:
  · dosyanın adı `protocol_limits` — okuyan bunu PROTOKOL GERÇEĞİ sanır,
  · `utils/README.md` de "5 STM / 8 ESP" diye yazıyordu (belge de birlikte bayatlamıştı),
  · bir sonraki geliştirici bu sabiti kullanmaya başlasaydı 6-7 sessizce dışarıda kalırdı.

⚠️ SINIF: "sihirli sayı ikinci bir yere kopyalanmış". Bu depoda tekrar eden arıza —
firmware ACK biçim dizesi, simülatör dilimleri ve banner kanal sayısı da aynı şekilde
bayatlamıştı.

===============================================================================
NEDEN IMPORT DEĞİL DE KAPI
===============================================================================
`utils/` katmanı `servers/`e bağımlı OLMAMALI (katman tersine döner). Bu yüzden sabit
`live_state`ten import EDİLMİYOR; bunun yerine bu kapı ikisinin AYRIŞMASINI kırmızı yapar.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

os.environ.setdefault("PEMF_SIMULATE", "1")


def test_KRITIK_STM_bobin_sayisi_live_state_ile_AYNI():
    """MUTASYON: `STM32_NUM_COILS`i 5'e döndür → KIRMIZI.

    Sahadaki etki (bu sabit kullanılmaya başlarsa): bobin 6-7 sessizce kapsam dışı kalır.
    """
    from servers.live_state import STM_COIL_IDS
    from utils.stm32_protocol_limits import STM32_NUM_COILS

    assert STM32_NUM_COILS == len(STM_COIL_IDS), (
        f"utils/stm32_protocol_limits.STM32_NUM_COILS={STM32_NUM_COILS} ama "
        f"live_state.STM_COIL_IDS {len(STM_COIL_IDS)} bobin ({sorted(STM_COIL_IDS)}) -> "
        "IKI KAYNAK AYRISTI (2026-09-10 gecisinde tam bu oldu)"
    )


def test_KRITIK_ESP_bobin_sayisi_live_state_ile_AYNI():
    """⚠️ `ESP_NUM_COILS` ADETTİR, en büyük kimlik DEĞİL.

    Eski değeri `8` idi ve "8 ESP bobini var" diye de okunabiliyordu; gerçekte ESP olarak
    yalnız SLOT 8 vardı. Ad ile içerik arasındaki bu belirsizlik, yanlış okumanın kendisiydi.
    """
    from servers.live_state import ESP_COIL_IDS
    from utils.stm32_protocol_limits import ESP_NUM_COILS

    assert ESP_NUM_COILS == len(ESP_COIL_IDS), (
        f"ESP_NUM_COILS={ESP_NUM_COILS} ama ESP_COIL_IDS {sorted(ESP_COIL_IDS)} "
        f"({len(ESP_COIL_IDS)} slot) -> ADET mi KIMLIK mi karisikligi geri geldi"
    )


def test_KRITIK_bobin_kimlikleri_CAKISMAZ_ve_BOSLUK_birakmaz():
    """STM ∪ ESP kesintisiz 1..N olmalı; kesişim boş olmalı.

    Çakışma: bir bobin iki taşıma katmanından da sürülmeye çalışılır.
    Boşluk: canlı durumdaki `range(8)` döngüleri var olmayan bir slota yazar.
    """
    from servers.live_state import ESP_COIL_IDS, STM_COIL_IDS

    assert not (STM_COIL_IDS & ESP_COIL_IDS), f"bobin kimlikleri CAKISIYOR: {sorted(STM_COIL_IDS & ESP_COIL_IDS)}"
    birlesim = STM_COIL_IDS | ESP_COIL_IDS
    assert birlesim == set(range(1, max(birlesim) + 1)), f"bobin kimliklerinde BOSLUK var: {sorted(birlesim)}"


def test_utils_README_bobin_sayisini_DOGRU_yaziyor():
    """⚠️ BELGE DE BİRLİKTE BAYATLAMIŞTI — kapı ikisini birden tutar.

    `utils/README.md` "5 STM / 8 ESP bobin" diyordu. Kod düzeltilip belge unutulursa
    bir sonraki okuyan yine yanlış öğrenir.

    MUTASYON: README'deki "7 STM" ifadesini "5 STM" yap → KIRMIZI.
    """
    from servers.live_state import STM_COIL_IDS

    metin = (KOK / "utils" / "README.md").read_text(encoding="utf-8", errors="replace")
    assert f"{len(STM_COIL_IDS)} STM" in metin, (
        f"utils/README.md '{len(STM_COIL_IDS)} STM' demiyor -> belge kodla AYRISMIS"
    )
    assert "5 STM / 8 ESP" not in metin, "utils/README.md hala ESKI (5/8) sayilari tasiyor"
