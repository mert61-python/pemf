# -*- coding: utf-8 -*-
# Author: mertaygn
"""KARTTA HANGİ FIRMWARE YÜKLÜ? — UART'ı dinler ve söyler.

===============================================================================
NEDEN VAR (2026-09-11, saha sorusu)
===============================================================================
Sahip sordu: *"stm uygulamada görünüyor ama pwm alıp başlamıyor, sebebi eski firmware
olabilir mi"*. Evet — ve bu **tam olarak** eski firmware'in belirtisi:

| | eski (5 bobin) | yeni (7 bobin) |
|---|---|---|
| Beklediği paket | **88 bayt** | **120 bayt** |

Backend 120 bayt gönderir. Eski firmware akışın **ilk 88 baytını** paket sanıp çerçeveler,
CRC'yi ilk 84 bayt üzerinden hesaplar — gerçek CRC alanı ise 120 baytlık düzende 116.
ofsettedir. Eşleşmez → `Coil_SendNack("CRC")` → `pkt_ok = 0` → **PWM durumuna HİÇ
dokunulmaz**. Ama `STM_READY` yine basıldığı için uygulama STM'i **BAĞLI GÖRÜR**.
Sonuç: "bağlı ama hiçbir bobin başlamıyor" — bobin 1-5 dahil.

⚠️ Bu belirti sessizdir: bağlantı göstergesi yeşil, hata penceresi yok. Ayırt etmenin
tek yolu UART'taki açılış satırını OKUMAKTIR. Bu betik onu okur.

===============================================================================
KULLANIM
===============================================================================
    python scripts/stm_firmware_kimligi.py            # portu kendi bulur
    python scripts/stm_firmware_kimligi.py --port COM10
    python scripts/stm_firmware_kimligi.py --sure 20  # daha uzun dinle

⚠️ **BACKEND KAPALI OLMALI.** Seri port tek kullanıcılıdır; PEMF_Backend çalışıyorsa
portu tutar ve bu betik "erişim reddedildi" alır. Betik bunu açıkça söyler.

Kart açılış satırını YALNIZ RESET'te basar. Betik bir şey duymazsa karttaki siyah
RESET düğmesine bas — banner o an akar.
"""

from __future__ import annotations

import argparse
import re
import sys
import time

BAUD = 115200

# ⚠️ DESEN BURADA DEGIL — TEK KAYNAK `apps/backend/utils/stm32_kimlik.py` (2026-09-18).
# Eskiden bu satirda kendi regex'i vardi. Ayni banner'i iki yerde ayristirmak, bu depoda
# bedeli OLCULMUS bir sinif: `_DB_ERROR` demetleri iki DB modulunde sessizce AYRISMISTI.
# Backend'in UYUM KAPISI da ayni ayristiriciyi kullanir; bu betikle aynı seyi gormeleri SART.

from pathlib import Path


# ── DEPO KÖKÜ + BACKEND YOLU ─────────────────────────────────────────────────
# ⚠️ Bu dosya 2026-09-18 klasör taşımasından (F4: `apps/backend/`) beri ÖLÜYDÜ —
#    `utils` artık depo kökünde değil, `apps/backend/` altında. Açılışta
#    `ModuleNotFoundError: No module named 'utils'` atıyordu. Ölçüldü 2026-09-21.
# ⚠️ SABİT DERİNLİK (`parents[1]`) YAZILMAZ: taşımada sessizce kayar ve bu depoda tam
#    o sınıf kod korumasını kırdı. Kök, İŞARET DOSYASIYLA yukarı aranır.
def _depo_koku(bas: Path) -> Path:
    for aday in (bas, *bas.parents):
        if (aday / "pyproject.toml").is_file() and (aday / "apps" / "backend").is_dir():
            return aday
    raise RuntimeError("depo kökü bulunamadı (işaret: pyproject.toml + apps/backend). Betik depo dışına mı taşındı?")


_KOK = _depo_koku(Path(__file__).resolve())
for _yol in (_KOK, _KOK / "apps" / "backend"):
    if str(_yol) not in sys.path:
        sys.path.insert(0, str(_yol))

from utils.stm32_kimlik import banner_ayristir  # noqa: E402

# ⚠️ UART OKUMA ARTIK TEK KAYNAKTAN: `apps/backend/utils/stm32_uart.py`.
#    Sebep (olculdu 2026-09-22): sevk edilen pakete `scripts/*.py` HIC girmiyor; firmware
#    guncellemesi kurulu cihazda banner okumak zorunda. Mantik `utils/` altinda, bu dosya
#    yalniz CLI yuzu. Ikinci bir kopya yazmak bu depoda bedeli olculmus bir siniftir.
from utils.stm32_uart import banner_dinle as _dinle  # noqa: E402
from utils.stm32_uart import port_adaylari  # noqa: E402


def _portlari_bul(istenen: str | None) -> list[str]:
    """CLI yuzu: portlari LISTELER (yazdirma burada, kutuphanede degil)."""
    from utils.stm32_uart import portlari_listele

    hepsi = portlari_listele()
    if hepsi and not istenen:
        print("Bulunan portlar:")
        for p in hepsi:
            print(f"  {p.aygit}  {p.aciklama}")
    return port_adaylari(istenen)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default=None, help="orn. COM10 (verilmezse otomatik aranir)")
    ap.add_argument("--sure", type=float, default=12.0, help="her portta dinleme suresi (sn)")
    a = ap.parse_args()

    portlar = _portlari_bul(a.port)
    if not portlar:
        print("[HATA] Hic seri port bulunamadi. Kart USB'ye takili mi?")
        return 2

    for port in portlar:
        print(f"\n=== {port} dinleniyor ({a.sure:.0f} sn) — banner gelmezse karttaki RESET'e bas ===")
        try:
            kanal, satirlar = _dinle(port, a.sure)
        except Exception as e:
            mesaj = str(e)
            if "Access is denied" in mesaj or "erisim" in mesaj.lower() or "PermissionError" in type(e).__name__:
                print(f"[{port}] PORT MESGUL — PEMF_Backend calisiyor olabilir. Once onu KAPAT.")
            else:
                print(f"[{port}] acilamadi: {e}")
            continue

        for s in satirlar:
            print("   " + s)

        if kanal is None:
            print(f"[{port}] STM_READY duyulmadi. RESET'e basip tekrar dene (ya da bu port STM degil).")
            continue

        print()
        print("=" * 72)
        if kanal >= 7:
            print(f"  ✅ YENI FIRMWARE YUKLU  ({kanal}-kanal, 120 baytlik paket)")
            print("     Bobinler baslamiyorsa sebep firmware DEGIL — baska yere bakilmali.")
        else:
            print(f"  ❌ ESKI FIRMWARE YUKLU  ({kanal}-kanal, 88 baytlik paket bekliyor)")
            print("     Yeni client 120 bayt gonderiyor -> CRC uyusmuyor -> STM_NACK ->")
            print("     HICBIR BOBIN BASLAMAZ (1-5 dahil), ama uygulama STM'i BAGLI GORUR.")
            print("     COZUM: masaustundeki PEMF_STM32_workspace_2026-09-11 projesini")
            print("            CubeIDE ile karta yukle (reflash).")
        print("=" * 72)
        if any("STM_NACK" in s for s in satirlar):
            print("  NOT: STM_NACK satiri da goruldu -> paket REDDEDILIYOR (teshis dogrulandi).")
        return 0 if kanal >= 7 else 1

    print("\n[SONUC] Hicbir portta STM_READY duyulmadi — firmware kimligi BELIRLENEMEDI.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
