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
| Beklediği paket | **88 bayt** | **121 bayt** |

Backend 121 bayt gönderir. Eski firmware akışın **ilk 88 baytını** paket sanıp çerçeveler,
CRC'yi ilk 84 bayt üzerinden hesaplar — gerçek CRC alanı ise 121 baytlık düzende 117.
ofsettedir. (120 → 121: 2026-09-11'de `unipolar_maskesi` baytı eklendi.) Eşleşmez → `Coil_SendNack("CRC")` → `pkt_ok = 0` → **PWM durumuna HİÇ
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

from utils.stm32_kimlik import firmware_paket_boyu, satirlardan_karar  # noqa: E402

# ⚠️ Paket boyu ELLE YAZILMAZ: 2026-09-11 protokol degisiminde (120 -> 121) betik
#    120'de kaldi ve operatore YANLIS sayi gosterdi. Tek kaynak stm32_transport.
#    Kapi: tests/test_stm_kimlik_betigi_PAKET_BOYU_BAYATLAMAZ.py
from utils.stm32_transport import STM_PAKET_BOBIN_SAYISI, STM_PAKET_BOYU  # noqa: E402


def firmware_karari(satirlar: list[str]):
    """Kart uyumlu mu? → (True | False | None, sebep, kimlik). BACKEND'IN UYUM KAPISININ AYNISI.

    ⚠️ D1.29 (B-10.219, plan C1b-89): betik eskiden kendi `kanal >= 7` esigiyle karar veriyordu; backend
    (`utils.stm32_kimlik.uyum_denetle`) ise `kanal == paket genisligi` der. 8 kanalli bir kart icin betik
    "YENI FIRMWARE YUKLU", HEAD derlemesi ayni karti 409 ile reddederdi — sahip Y7 sorusuna YANLIS cevap alirdi.
    Artik karar TEK yerde: bu fonksiyon yalniz backend kuralini cagirir.

    ⚠️ TD1-d · K10 (tezgâh 2026-10-14): banner'a bakan karar 120 B saha imajli kartta "✅ UYUMLU … sebep firmware DEGIL"
    dedi — 120 ve 121 B firmware AYNI banner'i basar. Karar artik KANITTAN: Y68 kimlik yaniti (pkt=) ya da kartin paketimize
    yaniti (STM_OK = kabul · arada kabul olmadan 3 CRC NACK = red) — backend cekirdeginin AYNI islevi (`satirlardan_karar`).
    Yalniz banner → "DOGRULANAMADI"."""
    uyumlu, sebep, kimlik = satirlardan_karar(satirlar, STM_PAKET_BOBIN_SAYISI)
    return uyumlu, sebep, kimlik


# ⚠️ UART OKUMA ARTIK TEK KAYNAKTAN: `apps/backend/utils/stm32_uart.py`.
#    Sebep (olculdu 2026-09-22): sevk edilen pakete `scripts/*.py` HIC girmiyor; firmware
#    guncellemesi kurulu cihazda banner okumak zorunda. Mantik `utils/` altinda, bu dosya
#    yalniz CLI yuzu. Ikinci bir kopya yazmak bu depoda bedeli olculmus bir siniftir.
#    TD1-d: dinleme + AKTIF dogrulama (kimlik sorgusu + sifir-duty yoklamasi) — backend el sikismasinin AYNISI.
from utils.stm32_uart import kart_dogrula as _kart_dogrula  # noqa: E402
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
        print(
            f"\n=== {port} dinleniyor ({a.sure:.0f} sn) + kart dogrulamasi (kimlik sorgusu + sifir-duty yoklamasi) ==="
        )
        try:
            satirlar, _ozet = _kart_dogrula(port, a.sure)
        except Exception as e:
            mesaj = str(e)
            if "Access is denied" in mesaj or "erisim" in mesaj.lower() or "PermissionError" in type(e).__name__:
                print(f"[{port}] PORT MESGUL — PEMF_Backend calisiyor olabilir. Once onu KAPAT.")
            else:
                print(f"[{port}] acilamadi: {e}")
            continue

        for s in satirlar:
            print("   " + s)

        if not any(("STM_" in s) for s in satirlar):
            print(f"[{port}] kart HIC yanit vermedi. RESET'e basip tekrar dene (ya da bu port STM degil).")
            continue

        uyumlu, sebep, _kimlik = firmware_karari(satirlar)
        kanal = _kimlik.kanal if _kimlik is not None else None
        print()
        print("=" * 72)
        if uyumlu is True:
            print(f"  ✅ UYUMLU — kart bu uygulamanin {STM_PAKET_BOYU} baytlik paketini KABUL ediyor (kanitla olculdu)")
            if _kimlik is not None and _kimlik.paket_boyu is not None:
                print(f"     Kartin beyani: proto={_kimlik.protokol} pkt={_kimlik.paket_boyu} ({_kimlik.surum})")
            print("     Bobinler baslamiyorsa sebep paket uyumsuzlugu DEGIL — baska yere bakilmali.")
        elif uyumlu is False:
            # ⚠️ ESKI (az kanalli) firmware'in teshis satiri KORUNUR: 88 bayt, 5 bobinli eski firmware'in
            # ayirt edici gercegidir (kapi: test_stm_kimlik_betigi_PAKET_BOYU_BAYATLAMAZ). Fazla kanalli kart
            # da artik uyumsuz (D1.29) — o durumda "eski" denmez.
            if kanal is not None and kanal < STM_PAKET_BOBIN_SAYISI:
                print(
                    f"  ❌ ESKI FIRMWARE YUKLU  ({kanal}-kanal, {'88 baytlik' if kanal == 5 else 'eski boyda'} paket bekliyor)"
                )
            elif kanal == STM_PAKET_BOBIN_SAYISI and _kimlik is not None and _kimlik.paket_boyu is not None:
                print(f"  ❌ UYUMSUZ FIRMWARE YUKLU  (kart {firmware_paket_boyu(_kimlik)} B paket bildiriyor)")
            elif kanal is not None and kanal > STM_PAKET_BOBIN_SAYISI:
                print(
                    f"  ❌ UYUMSUZ FIRMWARE YUKLU  ({kanal}-kanal; uygulama {STM_PAKET_BOBIN_SAYISI}-kanal gonderiyor)"
                )
            else:
                # TD1: banner 120 / 121 ayirt edemez; kart paketimizi SISTEMATIK reddediyor (CRC) — eski saha imaji gibi.
                print("  ❌ UYUMSUZ FIRMWARE YUKLU  (kart uygulamanin paketini REDDEDIYOR — eski paket boyu)")
            print(f"     Uygulama {STM_PAKET_BOYU} bayt gonderiyor -> CRC uyusmuyor -> STM_NACK ->")
            print(f"     {sebep}")
            print("     HICBIR BOBIN BASLAMAZ (1-5 dahil), ama uygulama STM'i BAGLI GORUR.")
            # D6.57 (B-10.191): sabit tarihli masaustu klasoru DEGIL — guncel yol: yakma CLI + kaynaktan temiz workspace.
            print("     COZUM: karti bu surumun firmware'i ile yakin: scripts/stm_yak.py (kullanim: scripts/README.md;")
            print("     dogrulama: el sikismada STM_OK). Kaynaktan derlemek icin once scripts/stm_workspace_kopyala.py")
            print(
                "     ile temiz CubeIDE workspace'i cikarin (firmware/stm32_pemf/README.md 'CubeIDE'de acma / derleme')."
            )
        else:
            print(f"  ❓ DOĞRULANAMADI — {sebep or 'kart kimligi ve paket yaniti alinamadi'}")
            print("     Banner tek basina uyumu SOYLEYEMEZ (120 ve 121 B firmware ayni banner'i basar).")
        print("=" * 72)
        if any("STM_NACK" in s for s in satirlar):
            print("  NOT: STM_NACK satiri da goruldu -> paket REDDEDILIYOR.")
        return 0 if uyumlu is True else (1 if uyumlu is False else 2)

    print("\n[SONUC] Hicbir portta kart yanit vermedi — firmware uyumu BELIRLENEMEDI.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
