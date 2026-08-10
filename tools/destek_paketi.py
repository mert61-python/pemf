# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Destek paketi üretici (CLI) — backend çökmüşken de çalışır.

    python tools\\destek_paketi.py                     # Masaüstüne yazar
    python tools\\destek_paketi.py --cikti C:\\yol\\x.zip
    python tools\\destek_paketi.py --veri-dizini "C:\\ProgramData\\PEMF_System\\PEMF_GUI"

Arayüzdeki tek-tık düğmesi aynı işi `POST /api/support/bundle` ile yapar; bu script backend
ayakta DEĞİLKEN (tam da desteğin en çok gerektiği an) alternatiftir.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.support_bundle import dosya_adi, olustur  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="PEMF destek paketi (PII maskelenmiş)")
    ap.add_argument("--veri-dizini", default=None, help="PEMF veri kökü (varsayılan: otomatik)")
    ap.add_argument("--cikti", default=None, help="hedef .zip (varsayılan: Masaüstü)")
    ap.add_argument("--log-tavani", type=int, default=512 * 1024, help="dosya başına son N bayt")
    a = ap.parse_args()

    if a.veri_dizini:
        kok = Path(a.veri_dizini)
    else:
        from utils.path_utils import get_app_data_directory

        kok = Path(get_app_data_directory())

    hedef = Path(a.cikti) if a.cikti else (Path.home() / "Desktop" / dosya_adi())
    hedef.parent.mkdir(parents=True, exist_ok=True)
    _, ozet = olustur(kok, hedef, log_tavani=a.log_tavani)

    print(f"Destek paketi yazildi: {hedef}")
    print(
        json.dumps(
            {
                k: ozet[k]
                for k in ("app_version", "build_id", "alinan_dosyalar", "atlanan_dosyalar", "maskelenen_eslesme")
                if k in ozet
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print("\nGondermeden once icerige bakabilirsiniz — maskeleme EN IYI GAYRETTIR.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
