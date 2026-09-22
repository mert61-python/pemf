# -*- coding: utf-8 -*-
# Author: mertaygn
"""STM32 GÜVENLİ REFLASH — ön kontrol → yak → banner doğrula → tutmazsa GERİ DÖN.

===============================================================================
NEDEN VAR (plan: docs/stm32-uzaktan-guncelleme-plani.md · Faz 2)
===============================================================================
Firmware pakete girmiyor; her değişiklikte STM'e elle reflash gerekiyordu. Bu betik o
işi **tek komuta** indirir ve elle yakmada atlanan güvenlik adımlarını zorunlu kılar.

⚠️ **1. ADIM PAZARLIĞA KAPALI.** Yakma MCU'yu resetler; hasta üzerindeyken bobinlerin
   aniden durması kabul edilemez. Aktif seans varsa betik YAKMAZ.
⚠️ **"Komut gönderdim" YETMEZ.** Bobinlerin gerçekten durduğu `/api/dashboard-snapshot`ten
   DOĞRULANIR — bu depoda "komut gitmiyor ama seans başlamış görünüyor" sınıfı yaşandı.
⚠️ **"Yaktım, exit 0 döndü" KANIT DEĞİLDİR.** Bu depoda build betiği başarısızken bile
   exit 0 döndürdü. Tek kanıt kartın KENDİ bastığı `STM_READY` banner'ıdır (adım 4).
⚠️ Banner tutmazsa **otomatik geri dönülür** — yedek yakma ÖNCESİ alınır, alınamazsa
   betik hiç yakmaz (geri dönüşü olmayan işlem yapılmaz).

===============================================================================
KULLANIM
===============================================================================
    python scripts/stm_yak.py --bin firmware_cikti/pemf.bin
    python scripts/stm_yak.py --bin pemf.bin --sha256 <beklenen>   # bütünlük kapısı
    python scripts/stm_yak.py --bin pemf.bin --kuru                # hiçbir şey yakmaz
    python scripts/stm_yak.py --bin pemf.bin --port COM10 --backend http://127.0.0.1:8000

⚠️ **BACKEND'İ KAPATIN** (ya da seri portu bıraktığından emin olun): port tek
   kullanıcılıdır, banner okuması "erişim reddedildi" alır. Betik bunu açıkça söyler.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


# ── DEPO KÖKÜ + BACKEND YOLU ─────────────────────────────────────────────────
# ⚠️ SABİT DERİNLİK YAZILMAZ — kök İŞARET DOSYASIYLA yukarı aranır. Bu depoda
#    `parents[N]` varsayımı 2026-09-18'de kod korumasını sessizce kırdı; ayrıca beş
#    betik F4 taşımasında tam bu yüzden öldü (kapı: tests/test_betikler_ACILIYOR.py).
def _depo_koku(bas: Path) -> Path:
    for aday in (bas, *bas.parents):
        if (aday / "pyproject.toml").is_file() and (aday / "apps" / "backend").is_dir():
            return aday
    raise RuntimeError("depo kökü bulunamadı (işaret: pyproject.toml + apps/backend)")


_KOK = _depo_koku(Path(__file__).resolve())
# ⚠️ BETİĞİN KENDİ DİZİNİ DE EKLENİR: bu depo GÖMÜLÜ Python kullanıyor (`python310._pth`),
#    orada `sys.path[0]` otomatik olarak betiğin dizini OLMAZ. Kardeş modül
#    (`stm_firmware_kimligi`) bu satır olmadan çözülmez — ölçüldü 2026-09-21.
for _yol in (Path(__file__).resolve().parent, _KOK, _KOK / "apps" / "backend"):
    if str(_yol) not in sys.path:
        sys.path.insert(0, str(_yol))

# ⚠️ BANNER AYRIŞTIRMA TEK KAYNAK: `apps/backend/utils/stm32_kimlik.py`. Backend'in uyum
#    kapısı da aynı ayrıştırıcıyı kullanır — bu betikle AYNI şeyi görmeleri ŞART.
# ⚠️ UART dinleme de tek kaynak: `scripts/stm_firmware_kimligi.py::_dinle`. İkinci bir
#    kopya yazmak, bu depoda bedeli ölçülmüş bir sınıf (`_DB_ERROR` demetleri ayrışmıştı).
from stm_firmware_kimligi import _dinle, _portlari_bul  # noqa: E402
from utils.stm32_kimlik import banner_ayristir, uyum_denetle  # noqa: E402
from utils.stm32_transport import STM_PAKET_BOBIN_SAYISI  # noqa: E402

#: Uygulama alanı. Bootloader'a DOKUNULMAZ → yarıda kesilen yakma ST-Link ile kurtarılır.
YAKMA_ADRESI = "0x08000000"
#: CubeIDE sürüm dizini değişir → yakıcı glob ile aranır, yol SABİT YAZILMAZ.
CLI_ARAMA = (Path(r"C:\ST"), Path(r"C:\Program Files\STMicroelectronics"))
BANNER_SURESI = 12.0


# ══════════════════════════════════════════════════════════════════════════════
# ARAÇ + BÜTÜNLÜK
# ══════════════════════════════════════════════════════════════════════════════
def programmer_cli() -> Path | None:
    """`STM32_Programmer_CLI.exe` — PATH'te ya da CubeIDE eklentileri altında."""
    yol = shutil.which("STM32_Programmer_CLI")
    if yol:
        return Path(yol)
    for kok in CLI_ARAMA:
        if not kok.is_dir():
            continue
        for aday in kok.rglob("STM32_Programmer_CLI.exe"):
            return aday
    return None


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for parca in iter(lambda: f.read(1024 * 1024), b""):
            h.update(parca)
    return h.hexdigest()


# ══════════════════════════════════════════════════════════════════════════════
# ÖN KONTROLLER — hepsi geçmezse YAKILMAZ
# ══════════════════════════════════════════════════════════════════════════════
def _json_al(url: str, timeout: float = 5.0):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace") or "{}")
    except (urllib.error.URLError, OSError, ValueError):
        return None


def seans_ve_bobin_kontrolu(backend: str) -> tuple[bool, str]:
    """(guvenli_mi, aciklama). Backend KAPALIYSA da güvenlidir — kimse sürmüyor demektir."""
    saglik = _json_al(f"{backend}/api/health")
    if saglik is None:
        return True, "backend kapalı (kimse bobin sürmüyor) — güvenli"

    if saglik.get("sessionActive"):
        return False, (
            "AKTİF SEANS VAR. Yakma MCU'yu resetler ve bobinler ANİDEN durur; hasta "
            "üzerindeyken bu kabul edilemez. Seansı bitirip tekrar deneyin."
        )

    # ⚠️ "seans yok" YETMEZ: manuel kipte tek bobin seanssız sürülebiliyor.
    anlik = _json_al(f"{backend}/api/dashboard-snapshot", timeout=8.0)
    if anlik is None:
        return False, (
            "Bobin durumu DOĞRULANAMADI (`/api/dashboard-snapshot` okunamadı). "
            "Doğrulanamayan durumda yakılmaz — backend'i kapatıp tekrar deneyin."
        )
    calisan = [
        c.get("id") for c in (anlik.get("coils") or []) if isinstance(c, dict) and (c.get("running") or c.get("active"))
    ]
    if calisan:
        return False, f"BOBİN SÜRÜLÜYOR: {calisan}. Hepsini durdurmadan yakılmaz."
    return True, "seans yok, bobin sürülmüyor"


# ══════════════════════════════════════════════════════════════════════════════
# YAKMA + DOĞRULAMA
# ══════════════════════════════════════════════════════════════════════════════
def _kos(cli: Path, argumanlar: list[str], timeout: float = 300.0) -> tuple[int, str]:
    r = subprocess.run(
        [str(cli), *argumanlar],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def yedek_al(cli: Path, hedef: Path, boyut: int) -> tuple[bool, str]:
    """Karttaki MEVCUT firmware'i oku. ⚠️ Alınamazsa YAKILMAZ — geri dönüşü olmayan
    işlem yapmayız."""
    hedef.parent.mkdir(parents=True, exist_ok=True)
    rc, cikti = _kos(cli, ["-c", "port=SWD", "-r", YAKMA_ADRESI, str(boyut), str(hedef)])
    if rc != 0 or not hedef.is_file() or hedef.stat().st_size == 0:
        return False, cikti[-600:]
    return True, str(hedef)


def yak(cli: Path, ikili: Path) -> tuple[bool, str]:
    rc, cikti = _kos(cli, ["-c", "port=SWD", "-w", str(ikili), YAKMA_ADRESI, "-v", "-rst"], timeout=600.0)
    return rc == 0, cikti[-1200:]


def banner_dogrula(port: str | None) -> tuple[bool | None, str, str]:
    """(uyumlu, sebep, ham_banner). Kart KENDİ kimliğini söylemeden yakma başarılı sayılmaz."""
    portlar = _portlari_bul(port)
    if not portlar:
        return None, "seri port bulunamadı — banner okunamadı", ""
    for p in portlar:
        try:
            _kanal, satirlar = _dinle(p, BANNER_SURESI)
        except Exception as e:  # noqa: BLE001 — port meşgul/yok: sonraki adaya geç
            print(f"   [{p}] dinlenemedi: {type(e).__name__}: {str(e)[:80]}")
            continue
        for satir in satirlar:
            if "STM_READY" not in satir:
                continue
            kimlik = banner_ayristir(satir)
            uyumlu, sebep = uyum_denetle(kimlik, STM_PAKET_BOBIN_SAYISI)
            return uyumlu, sebep or "banner uyumlu", satir
    return None, "STM_READY satırı hiç görülmedi (karta RESET atmayı deneyin)", ""


# ══════════════════════════════════════════════════════════════════════════════
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="STM32 güvenli reflash (ön kontrol + geri dönüş)")
    ap.add_argument("--bin", required=True, help="yakılacak .bin (scripts/firmware_derle.py --stm --cikti)")
    ap.add_argument("--sha256", default="", help="beklenen SHA256 — verilirse ZORUNLU kapı")
    ap.add_argument("--port", default=None, help="UART portu (varsayılan: otomatik)")
    ap.add_argument("--backend", default="http://127.0.0.1:8000", help="ön kontrol için backend")
    ap.add_argument("--yedek-dizin", default="firmware_yedek", help="geri dönüş .bin dizini")
    ap.add_argument("--kuru", action="store_true", help="hiçbir şey yakma, yalnız kontrolleri göster")
    a = ap.parse_args(argv)

    ikili = Path(a.bin).resolve()
    if not ikili.is_file():
        print(f"HATA: .bin yok: {ikili}")
        return 2

    print("=" * 70)
    print("STM32 GÜVENLİ REFLASH" + ("  [KURU KOŞUM]" if a.kuru else ""))
    print("=" * 70)

    # 1) ÖN KONTROLLER
    ozet = sha256(ikili)
    print(f"1) ikili   : {ikili}  ({ikili.stat().st_size} bayt)")
    print(f"   sha256  : {ozet}")
    if a.sha256 and a.sha256.lower() != ozet:
        print(f"   ✗ BÜTÜNLÜK: beklenen {a.sha256.lower()} — YAKILMAZ")
        return 3
    if a.sha256:
        print("   ✓ beklenen özetle eşleşti")

    guvenli, aciklama = seans_ve_bobin_kontrolu(a.backend.rstrip("/"))
    print(f"2) donanım : {'✓' if guvenli else '✗'} {aciklama}")
    if not guvenli:
        return 4

    cli = programmer_cli()
    print(f"3) yakıcı  : {cli or '✗ STM32_Programmer_CLI bulunamadı (CubeIDE kurulu mu?)'}")
    if cli is None:
        return 5

    if a.kuru:
        print("\nKURU KOŞUM — yakma yapılmadı. Kontroller geçti.")
        return 0

    # 2) YEDEK (geri dönüşün ön şartı)
    yedek = Path(a.yedek_dizin).resolve() / f"pemf_yedek_{time.strftime('%Y%m%d_%H%M%S')}.bin"
    tamam, bilgi = yedek_al(cli, yedek, ikili.stat().st_size)
    print(f"4) yedek   : {'✓ ' + bilgi if tamam else '✗ ALINAMADI'}")
    if not tamam:
        print("   Geri dönüşü olmayan işlem YAPILMAZ. Çıkılıyor.\n" + bilgi)
        return 6

    # 3) YAK
    print("5) yakılıyor…")
    tamam, cikti = yak(cli, ikili)
    print(f"   {'✓ yazıldı + doğrulandı' if tamam else '✗ yakıcı hata verdi'}")
    if not tamam:
        print(cikti)
        return 7

    # 4) BANNER — ASIL KABUL ÖLÇÜTÜ
    time.sleep(2.0)  # kart açılış banner'ını bassın
    uyumlu, sebep, ham = banner_dogrula(a.port)
    print(f"6) banner  : {ham or '(okunamadı)'}")
    print(f"   uyum    : {uyumlu} — {sebep}")

    if uyumlu is False:
        print("\n✗ UYUMSUZ FIRMWARE — GERİ DÖNÜLÜYOR…")
        geri, geri_cikti = yak(cli, yedek)
        print(f"   geri dönüş: {'✓ eski firmware yakıldı' if geri else '✗ BAŞARISIZ'}")
        if not geri:
            print(geri_cikti)
            print(f"   ⚠️ ELLE KURTARMA GEREKLİ: {yedek}")
        return 8

    if uyumlu is None:
        # ⚠️ "Bilinmiyor" geri dönüş sebebi DEĞİL: banner biçimi ileride değişip UYUMLU bir
        #    firmware de tanınmayabilir. Backend'in uyum kapısı da aynı üç-durumlu kararı verir.
        print("\n⚠️ Banner tanınmadı — yakma yapıldı ama DOĞRULANAMADI.")
        print("   Karta RESET atıp `python scripts/stm_firmware_kimligi.py` ile bakın.")
        return 9

    print("\n✓ TAMAM — yakıldı ve kart kendi kimliğiyle doğruladı.")
    print(f"   sha256 : {ozet}")
    print(f"   zaman  : {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   yedek  : {yedek}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
