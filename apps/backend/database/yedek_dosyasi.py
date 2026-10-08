# -*- coding: utf-8 -*-
"""Yedek DOSYASININ kendisi — tedavi ve hasta DB'sinin `create_backup`ı için TEK kaynak (2-D).

⚠️ D2.61 (B-3.70): başarısız bir yedek denemesi hedefte 0 baytlık (ya da yarım) dosya BIRAKIYORDU — iki DB'de de. SQLite yedek
API'si hata verince yazdığını geri alır ama hedef dosya zaten oluşmuştur [ÖLÇTÜM 2-D sondası: disk dolu → 0 B; şifreli kaynak
→ düz hedef `TypeError` → 0 B]. Bu artık, rotasyonda sağlam bir yedeğin yuvasını alır ve "son yedek ne zaman" denetimini
(`headless_db_maintenance._recent_backup_exists`, dosya mtime'ı) kandırır: yedek sessizce ALINMAMIŞ olur.

Kural: yalnız BU denemenin oluşturduğu dosya silinir (deneme öncesi yoksa). Önceden var olan bir dosyaya dokunulmaz.
Silinen dosya veri taşımaz: kaynak DB yerinde ve sağlamdır; artık yalnız başarısız denemenin boş/yarım çıktısıdır.
Kapı: tests/test_at_rest_bayragi_ve_yarim_yedek_D261.py
"""

from __future__ import annotations

import os


def basarisiz_yedegi_kaldir(yol: str, onceden_vardi: bool, logger) -> None:
    """Başarısız yedek denemesinin hedefte bıraktığı dosyayı (ve `-journal` / `-wal` / `-shm` eşlerini) kaldırır.

    `onceden_vardi` True ise hiçbir şeye dokunmaz. Hata YÜKSELTMEZ (yedek yolu çağıranın akışını bozmamalı); kaldırılamazsa
    WARNING yazar — artığın varlığı operatörden saklanmaz."""
    if onceden_vardi:
        return
    for ek in ("", "-journal", "-wal", "-shm"):
        p = f"{yol}{ek}"
        try:
            if os.path.exists(p):
                os.remove(p)
        except OSError:
            logger.warning(
                "Basarisiz yedek artigi kaldirilamadi: %s — 0 baytlik/yarim dosya rotasyonda saglam yedegin yerini alabilir; "
                "elle silin.",
                p,
                exc_info=True,
            )
