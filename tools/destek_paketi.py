# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Destek paketi üretici (CLI) — backend çökmüşken de çalışır.

SAHADA (Python YOK) launcher'ın kurduğu EXE'nin alt komutudur (D6.47 · Y32; `backend_service._destek_paketi_mi`), cmd:
    "%LOCALAPPDATA%\\PEMF Vet Client\\runtime\\PEMF_Backend\\PEMF_Backend.exe" --destek-paketi   # Masaüstüne
    ... --destek-paketi --cikti C:\\yol\\x.zip
    ... --destek-paketi --veri-dizini "C:\\ProgramData\\PEMF_System\\PEMF_GUI"

Kaynak ağacında (geliştirme) aynı bayraklarla: python tools\\destek_paketi.py ...

Arayüzdeki tek-tık düğmesi aynı işi `POST /api/support/bundle` ile yapar; bu araç backend
ayakta DEĞİLKEN (tam da desteğin en çok gerektiği an) alternatiftir.
"""

import argparse
import json
import sys
from pathlib import Path


# ── DEPO KÖKÜ + BACKEND YOLU ─────────────────────────────────────────────────
# ⚠️ Bu betik 2026-09-18 klasör taşımasından (F4: `apps/backend/`) beri ÖLÜYDÜ: `utils`
#    artık depo kökünde değil. Açılışta `ModuleNotFoundError: No module named 'utils'`.
#    Ölçüldü 2026-09-21; kapı: tests/test_betikler_ACILIYOR.py
# ⚠️ SABİT DERİNLİK YAZILMAZ — kök İŞARET DOSYASIYLA yukarı aranır.
# ⚠️ D6.47 (Y32): DONMUŞ EXE'de (`PEMF_Backend.exe --destek-paketi`) kaynak ağacı YOKTUR — `tools/kurtarma.py`
#    (D2.35) ile AYNI kural: donmuşken ARAMA YAPILMAZ ve yol EKLENMEZ (modüller paketin içinden gelir; yukarı
#    yürümek paketi gölgeleyebilir).
#    Eskiden burada koşulsuz arama + `parents[1]` eklemesi vardı → donmuş EXE'de içe aktarmada RuntimeError.
#    Kapı: tests/test_destek_paketi_EXE_bayragi_SAHADA_D6_47.py
def _depo_koku(bas: Path) -> Path | None:
    if getattr(sys, "frozen", False):
        return None
    for aday in (bas, *bas.parents):
        if (aday / "pyproject.toml").is_file() and (aday / "apps" / "backend").is_dir():
            return aday
    raise RuntimeError("depo kökü bulunamadı (işaret: pyproject.toml + apps/backend)")


_KOK = _depo_koku(Path(__file__).resolve())
for _yol in (_KOK, _KOK / "apps" / "backend") if _KOK is not None else ():
    if str(_yol) not in sys.path:
        sys.path.insert(0, str(_yol))

from utils.support_bundle import dosya_adi, olustur  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="PEMF destek paketi (PII maskelenmiş)")
    ap.add_argument("--veri-dizini", default=None, help="PEMF veri kökü (varsayılan: otomatik)")
    ap.add_argument("--cikti", default=None, help="hedef .zip (varsayılan: Masaüstü)")
    ap.add_argument("--log-tavani", type=int, default=512 * 1024, help="dosya başına son N bayt")
    a = ap.parse_args(argv)

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
