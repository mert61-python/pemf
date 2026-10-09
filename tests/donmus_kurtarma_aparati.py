# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""DONMUŞ EXE BENZETİMİ — `PEMF_Backend.exe --kurtarma` yolunun içe aktarma + çalıştırma kolu (D2.35 · D2.75).

PyInstaller derlemesi YOK. `tools/kurtarma.py` depo DIŞINDAKİ bir paket dizinine (`<tmp>/paket/tools/`) kopyalanır; alt süreçte
`sys.frozen = True`, `sys._MEIPASS = <paket>`. Paketlenmiş modüller (`utils`, `database`) için YALNIZ `apps/backend` sys.path'e
eklenir (PYZ benzetimi); depo kökü sys.path'te YOKTUR — aracın kendisi eklerse ölçülür. Ardından GERÇEK `backend_service._kurtarma_mi`
ile aynı biçimde `tools.kurtarma.main(argv)` çağrılır.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from betik_alt_sureci import kostur, yalitik_ortam

DEPO = Path(__file__).resolve().parents[1]

_SURUCU = r"""
import json, sys
from pathlib import Path
PAKET, BACKEND, DEPO = {paket!r}, {backend!r}, {depo!r}
sys.frozen = True
sys._MEIPASS = PAKET
sys.path.insert(0, PAKET)
sys.path.append(BACKEND)
sonuc = {{}}
try:
    import tools.kurtarma as k
    sonuc["ice_aktarma"] = "tamam"
    sonuc["open_envelope"] = hasattr(k, "open_envelope")
    sonuc["depo_koku_yolda"] = any(p and Path(p).resolve() == Path(DEPO).resolve() for p in sys.path)
    try:
        sonuc["rc"] = k.main({argv!r})
    except SystemExit as e:
        sonuc["rc"] = e.code
except BaseException as e:
    sonuc["kacan"] = type(e).__name__ + ": " + str(e)[:300]
print("SONUC " + json.dumps(sonuc, default=str))
"""


def donmus_kurtarma_kos(tmp_path: Path, argv: list[str]) -> tuple[dict, str]:
    """`argv`i donmuş benzetimde `tools.kurtarma.main`e verir → (SONUC sözlüğü, tüm çıktı)."""
    paket = tmp_path / "paket"
    (paket / "tools").mkdir(parents=True, exist_ok=True)
    shutil.copy2(DEPO / "tools" / "kurtarma.py", paket / "tools" / "kurtarma.py")
    (paket / "tools" / "__init__.py").write_text("", encoding="utf-8")
    surucu = tmp_path / "donmus_surucu.py"
    surucu.write_text(
        _SURUCU.format(paket=str(paket), backend=str(DEPO / "apps" / "backend"), depo=str(DEPO), argv=list(argv)),
        encoding="utf-8",
    )
    p = kostur([str(surucu)], cwd=tmp_path, env=yalitik_ortam(tmp_path / "ev"), sure=120)
    for satir in p.stdout.splitlines():
        if satir.startswith("SONUC "):
            return json.loads(satir[len("SONUC ") :]), p.stdout + p.stderr
    raise AssertionError(f"donmuş sürücü sonuç basmadı (rc={p.returncode}):\n{(p.stdout + p.stderr)[-1500:]}")
