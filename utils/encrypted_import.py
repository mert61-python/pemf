# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""ŞİFRELİ KAYNAK YÜKLEYİCİ — sahada `.pyenc` modüllerini BELLEKTE çözer (2026-08-06).

`build_tools/encrypt_sources.py` build çıktısındaki `.py` dosyalarını `.pyenc`'e çevirir ve
düz kaynağı siler. Bu modül, Python'un import mekanizmasına bir bulucu (finder) ekleyerek o
dosyaları çalışma anında çözer ve normal modül gibi yükler.

TASARIM KARARLARI:
  * **Diske YAZMAZ.** Çözülen kaynak yalnız bellekte derlenir. Geçici dosyaya yazmak,
    şifrelemenin tek faydasını (düz kaynağın diskte durmaması) ortadan kaldırırdı.
  * **Standart bulucudan SONRA çalışır** (`sys.path_hooks` yerine `sys.meta_path`'in SONUNA
    eklenir): düz `.py` varsa o kullanılır → geliştirme ortamı ETKİLENMEZ.
  * **Parola yoksa sessizce devre dışı.** Şifreleme uygulanmamış build'lerde (geliştirme,
    testler) bu modül hiçbir şey yapmaz — kurulum akışını bozmaz.
  * **Çözme hatası YUTULMAZ.** Yanlış parola/bozuk dosya net bir ImportError verir; sessizce
    "modül yok" demek, saha teşhisini imkânsız kılardı.

⚠️ Bu katman kopyalamayı zorlaştırır, tersine mühendisliği ENGELLEMEZ (anahtar üründe gider).
Asıl koruma `.py → .pyd` native derlemedir. Bkz. build_tools/source_crypto.py.
"""

from __future__ import annotations

import importlib.abc
import importlib.machinery
import importlib.util
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

ENC_SUFFIX = ".pyenc"
_installed = False


def _password() -> str:
    from utils.source_crypto import read_password

    return read_password()


def _decrypt(blob: bytes, pw: str) -> bytes:
    from utils.source_crypto import decrypt_bytes

    return decrypt_bytes(blob, pw)


class EncryptedLoader(importlib.abc.Loader):
    def __init__(self, fullname: str, path: Path, password: str):
        self.fullname = fullname
        self.path = path
        self.password = password

    def create_module(self, spec):
        return None  # varsayılan modül nesnesi

    def exec_module(self, module):
        try:
            kaynak = _decrypt(self.path.read_bytes(), self.password)
        except Exception as e:
            # SESSİZCE GEÇME: yanlış parola/bozuk dosya sahada teşhis edilebilmeli.
            raise ImportError(
                f"Şifreli modül çözülemedi: {self.fullname} ({self.path.name}). "
                f"Parola yanlış ya da dosya bozuk olabilir. Ayrıntı: {e}"
            ) from e
        kod = compile(kaynak, str(self.path), "exec")
        exec(kod, module.__dict__)


class EncryptedFinder(importlib.abc.MetaPathFinder):
    """`sys.meta_path` SONUNDA durur → düz .py varsa standart bulucu önce davranır."""

    def __init__(self, password: str):
        self.password = password

    def find_spec(self, fullname, path=None, target=None):
        parca = fullname.rsplit(".", 1)[-1]
        aranan = list(path) if path else list(sys.path)
        for kok in aranan:
            try:
                aday = Path(kok) / f"{parca}{ENC_SUFFIX}"
            except Exception:
                continue
            if aday.is_file():
                loader = EncryptedLoader(fullname, aday, self.password)
                return importlib.util.spec_from_loader(fullname, loader, origin=str(aday))
        return None


def install() -> bool:
    """Yükleyiciyi kur. Parola yoksa ya da hiç `.pyenc` yoksa sessizce False döner."""
    global _installed
    if _installed:
        return True
    pw = _password()
    if not pw:
        logger.debug("Şifreli kaynak yükleyici: parola yok → devre dışı (şifresiz build).")
        return False
    sys.meta_path.append(EncryptedFinder(pw))
    _installed = True
    logger.info("Şifreli kaynak yükleyici kuruldu (.pyenc).")
    return True
