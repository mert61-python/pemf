# Author: mertaygn, cglrgrkn
"""Cross-platform destek — TEK NOKTA (backend).

OS-özgü farklar (çalıştırılabilir adları, sistem/bundled ikili bulma, yollar) BURADA toplanır;
kod bunları çağırır, dağınık `if sys.platform` YOK. Windows / macOS / Linux üçü de tek kod
tabanından çalışır → platforma göre AYRI kaynak/AYRI build kodu GEREKMEZ (aynı .spec her yerde).

Yeni platform veya yeni OS-farkı = yalnızca bu dosyaya bir dal ekle.
İstemci (Tauri) tarafı ise Rust'ta `#[cfg(target_os = "...")]` ile ayrılır (ayrı katman).
"""

import shutil
import sys
from pathlib import Path
from typing import Iterable, Optional

# ── OS bayrakları (tek kaynak) ────────────────────────────────────────────────
IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")


def exe_suffix() -> str:
    """Çalıştırılabilir uzantı: Windows '.exe', macOS/Linux ''."""
    return ".exe" if IS_WIN else ""


def binary_name(stem: str) -> str:
    """Platforma uygun ikili adı. Örn. binary_name('mosquitto') → Win 'mosquitto.exe', mac/Linux 'mosquitto'."""
    return stem + exe_suffix()


def find_executable(
    stem: str,
    bundle_dirs: Iterable[Path] = (),
    extra: Iterable[Path] = (),
    prefer_system: Optional[bool] = None,
) -> Optional[Path]:
    """Bir ikiliyi bul (bundled dizinler + sistem PATH + ek adaylar).

    prefer_system=None → macOS/Linux'ta SİSTEM önce (bundled genelde Windows-ikilisidir, orada çalışmaz;
    mac/Linux sistem mosquitto'yu apt/brew ile alır), Windows'ta BUNDLED önce (offline saha).
    Döndürür: ilk var-olan Path | None.
    """
    if prefer_system is None:
        prefer_system = not IS_WIN
    name = binary_name(stem)
    sys_which = shutil.which(stem)
    system = [Path(sys_which)] if sys_which else []
    bundled = [Path(d) / name for d in bundle_dirs]
    extra_list = list(extra)
    order = (system + bundled + extra_list) if prefer_system else (bundled + extra_list + system)
    for p in order:
        try:
            if p and p.exists():
                return p
        except Exception:
            continue
    return None


def find_bundled_file(filename: str, bundle_dirs: Iterable[Path] = ()) -> Optional[Path]:
    """Bundled bir yardımcı dosyayı (ör. mosquitto.conf) verilen dizinlerde bul."""
    for d in bundle_dirs:
        cand = Path(d) / filename
        try:
            if cand.exists():
                return cand
        except Exception:
            continue
    return None
