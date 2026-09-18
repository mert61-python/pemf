# Author: mertaygn, cglrgrkn
"""Konsol penceresi AÇMADAN alt süreç başlatma — TEK KAYNAK.

SAHA ŞİKÂYETİ (2026-08-11): "client güncellemesi için uygulamayı kapatıp geri açtığımda siyah
konsol penceresi çıktı."

NEDEN OLUYOR. Backend, launcher tarafından `CREATE_NO_WINDOW` ile (yani KONSOLSUZ) başlatılır.
Konsolsuz bir süreçten konsol-altsistem bir program (powershell, ffmpeg, netsh, taskkill…)
çalıştırılınca Windows ona **YENİ BİR KONSOL** açar ve kullanıcı ekranda siyah pencerenin yanıp
söndüğünü görür. Bayrağı bir yerde vermeyi unutmak yeterlidir.

⚠️ `creationflags` değeri EZER, OR'lamaz: iki kez vermek ilkini sessizce iptal eder. Bu yüzden
ek bayrak gerekiyorsa (DETACHED_PROCESS gibi) `bayraklar()`a EKLENİR, ayrıca verilmez.

`tests/test_konsol_penceresi.py` proje kodunda bayraksız spawn kalmadığını denetler.
"""

from __future__ import annotations

import os
import subprocess
from typing import Any

#: Süreç konsol penceresi almaz (Windows).
CREATE_NO_WINDOW = 0x0800_0000
#: Süreç ebeveynin konsolunu DEVRALMAZ (uzun ömürlü/ayrık süreçler için).
DETACHED_PROCESS = 0x0000_0008
CREATE_NEW_PROCESS_GROUP = 0x0000_0200


def bayraklar(ayrik: bool = False) -> int:
    """Windows'ta konsol penceresi açtırmayan `creationflags` değeri.

    `ayrik=True` → süreç ebeveynden BAĞIMSIZ yaşar (kurulum/broker gibi). DETACHED_PROCESS
    zaten konsol devralmaz ve yenisini de açmaz; CREATE_NO_WINDOW ile birlikte verilmesi
    zararsızdır (Windows ikincisini yok sayar) ama niyeti açık bırakır.
    """
    if os.name != "nt":
        return 0
    f = CREATE_NO_WINDOW
    if ayrik:
        f |= DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    return f


def calistir(args, **kwargs: Any) -> subprocess.CompletedProcess:
    """`subprocess.run` — konsol penceresi AÇMADAN."""
    kwargs.setdefault("creationflags", bayraklar())
    return subprocess.run(args, **kwargs)


def baslat(args, *, ayrik: bool = False, **kwargs: Any) -> subprocess.Popen:
    """`subprocess.Popen` — konsol penceresi AÇMADAN."""
    kwargs.setdefault("creationflags", bayraklar(ayrik=ayrik))
    return subprocess.Popen(args, **kwargs)
