# -*- coding: utf-8 -*-
# Author: mertaygn
"""STM32 GÜVENLİ REFLASH — CLI yüzü.

⚠️ **MANTIK BURADA DEĞİL:** `apps/backend/utils/stm_yakma.py`. Sebebi ölçüldü (2026-09-22):
sevk edilen pakete `scripts/` altından YALNIZ altı `.ps1` giriyor
(`build_tools/make_base_zip.ADD_SCRIPTS`) — `scripts/*.py` **hiç gitmiyor**. Sahip kararıyla
firmware güncellemesi OTOMATİK olacak, yani akış **kurulu cihazda** koşacak; mantık burada
kalsaydı sahada hiç bulunmazdı. Bu dosya yalnız argüman ayrıştırır ve YAZDIRIR.
(Aynı desen: `build_tools/source_crypto.py` → `utils/source_crypto.py`.)

KULLANIM
    python scripts/stm_yak.py --bin firmware_cikti/pemf.bin
    python scripts/stm_yak.py --bin pemf.bin --sha256 <beklenen>   # bütünlük kapısı
    python scripts/stm_yak.py --bin pemf.bin --kuru                # hiçbir şey yakmaz
    python scripts/stm_yak.py --bin pemf.bin --port COM10 --backend http://127.0.0.1:8000
    python scripts/stm_yak.py --kurtarma --bin saha_yedek_1.bin --sha256 <tam sha> --port COM10   # ELLE KURTARMA

⚠️ T-a: kart yeni firmware'le kendini DOĞRULAMAZSA (uyumsuz ya da doğrulanamadı) akış önceki firmware'e OTOMATİK döner.
   Bilerek eski bir imaj yazılacaksa (prosedür "Elle kurtarma") `--kurtarma` kullanılır: uyum hükmüyle GERİ ALINMAZ,
   ölçüt SHA-256 (zorunlu) + bağımsız geri okuma + kartın konuşması.

⚠️ **BACKEND'İ KAPATIN** (ya da seri portu bıraktığından emin olun): port tek
   kullanıcılıdır, banner okuması "erişim reddedildi" alır.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


# ── DEPO KÖKÜ + BACKEND YOLU ─────────────────────────────────────────────────
# ⚠️ SABİT DERİNLİK YAZILMAZ — kök İŞARET DOSYASIYLA yukarı aranır.
# ⚠️ Betiğin KENDİ dizini de eklenir: bu depo GÖMÜLÜ Python kullanıyor (`python310._pth`),
#    orada `sys.path[0]` otomatik olarak betiğin dizini OLMAZ.
def _depo_koku(bas: Path) -> Path:
    for aday in (bas, *bas.parents):
        if (aday / "pyproject.toml").is_file() and (aday / "apps" / "backend").is_dir():
            return aday
    raise RuntimeError("depo kökü bulunamadı (işaret: pyproject.toml + apps/backend)")


_KOK = _depo_koku(Path(__file__).resolve())
for _yol in (Path(__file__).resolve().parent, _KOK, _KOK / "apps" / "backend"):
    if str(_yol) not in sys.path:
        sys.path.insert(0, str(_yol))

from utils.stm_yakma import TAMAM, elle_kurtarma, yakma_akisi  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="STM32 güvenli reflash (ön kontrol + geri dönüş)")
    ap.add_argument("--bin", required=True, help="yakılacak .bin (firmware_derle.py --stm --cikti)")
    ap.add_argument("--sha256", default="", help="beklenen SHA256 — verilirse ZORUNLU kapı")
    ap.add_argument("--port", default=None, help="UART portu (varsayılan: otomatik)")
    ap.add_argument("--backend", default="http://127.0.0.1:8000", help="ön kontrol için backend")
    ap.add_argument("--yedek-dizin", default="firmware_yedek", help="geri dönüş .bin dizini")
    ap.add_argument("--kuru", action="store_true", help="hiçbir şey yakma, yalnız kontroller")
    ap.add_argument(
        "--kurtarma",
        action="store_true",
        help="ELLE KURTARMA: bilinen imajı (ör. tam yedek) yaz; uyum hükmüyle geri ALMA (--sha256 zorunlu)",
    )
    a = ap.parse_args(argv)
    if a.kurtarma and a.kuru:
        ap.error("--kurtarma ile --kuru birlikte kullanılmaz")

    print("=" * 70)
    print("STM32 GÜVENLİ REFLASH" + ("  [KURU KOŞUM]" if a.kuru else "") + ("  [ELLE KURTARMA]" if a.kurtarma else ""))
    print("=" * 70)

    if a.kurtarma:
        s = elle_kurtarma(
            Path(a.bin),
            beklenen_sha256=a.sha256,
            port=a.port,
            backend=a.backend,
            yedek_dizin=Path(a.yedek_dizin),
        )
    else:
        s = yakma_akisi(
            Path(a.bin),
            beklenen_sha256=a.sha256,
            port=a.port,
            backend=a.backend,
            yedek_dizin=Path(a.yedek_dizin),
            kuru=a.kuru,
        )
    for i, adim in enumerate(s.adimlar, 1):
        print(f"{i}) {adim}")
    print()
    print(("✓ " if s.tamam else "✗ ") + (s.ozet or "(açıklama yok)"))
    if s.banner:
        print(f"   banner: {s.banner}")
    if s.yedek:
        print(f"   yedek : {s.yedek}")
    return s.kod if s.kod != TAMAM else 0


if __name__ == "__main__":
    raise SystemExit(main())
