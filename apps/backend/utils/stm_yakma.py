# -*- coding: utf-8 -*-
"""STM32 YAKMA ÇEKİRDEĞİ — ön kontrol → yedek → yak → banner doğrula → gerekirse GERİ DÖN.

⚠️ **NEDEN `utils/` ALTINDA** (ölçüldü 2026-09-22): sevk edilen pakete `scripts/` altından
YALNIZ altı `.ps1` giriyor (`make_base_zip.ADD_SCRIPTS`); `scripts/*.py` **hiç gitmiyor**.
Sahip kararıyla firmware güncellemesi OTOMATİK olacak, yani bu mantık **kurulu cihazda**
koşacak. `scripts/` altında kalsaydı sahada hiç bulunmazdı. `scripts/stm_yak.py` artık
yalnız CLI yüzüdür (`build_tools/source_crypto.py` ile aynı yerleşik desen).

⚠️ BU MODÜL YAZDIRMAZ — durumu `Adim` kayıtları olarak DÖNDÜRÜR. Arayüzsüz serviste
`print`, drenajsız pipe'ı doldurup kilitlenmeye yol açabilir (bu depoda ölçülmüş sınıf).

GÜVENLİK DEĞİŞMEZLERİ — pazarlığa kapalı
  1. Aktif seans varsa YAKMAZ. Yakma MCU'yu resetler; hasta üzerindeyken bobinlerin
     aniden durması kabul edilemez.
  2. Bobin sürülüyorsa YAKMAZ — "seans yok" YETMEZ (manuel kipte tek bobin sürülebilir).
  3. Bobin durumu OKUNAMIYORSA yakmaz (**fail-closed**). Ama backend KAPALIYSA yakar
     (**fail-open, bilerek**): kimse bobin sürmüyordur ve asıl ihtiyaç anı orasıdır.
     Ayrım: backend YOK ≠ backend VAR ama cevap vermiyor.
  4. YEDEK yakmadan ÖNCE alınır; alınamazsa HİÇ yakılmaz (geri dönüşü olmayan işlem YOK).
  5. Banner UYUMSUZ → OTOMATİK GERİ DÖN.
  6. Banner TANINMADI (`None`) → geri DÖNÜLMEZ. Üç-durumlu karar `utils/stm32_kimlik`
     ile aynı: banner biçimi ileride değişip UYUMLU bir firmware de tanınmayabilir.

⚠️ "exit 0 döndü" KANIT DEĞİLDİR — bu depoda build betiği başarısızken bile 0 döndü.
   Tek kabul ölçütü kartın KENDİ bastığı `STM_READY` banner'ıdır.
⚠️ Bootloader'a DOKUNULMAZ (yalnız `0x08000000` uygulama alanı) → yarıda kesilen yakma
   ST-Link ile kurtarılabilir.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from utils.stm32_kimlik import banner_ayristir, uyum_denetle
from utils.stm32_transport import STM_PAKET_BOBIN_SAYISI
from utils.stm32_uart import banner_dinle, port_adaylari

#: Uygulama alanı — bootloader'a dokunulmaz.
YAKMA_ADRESI = "0x08000000"
#: CubeIDE sürüm dizini değişir → yakıcı GLOB ile aranır, yol SABİT YAZILMAZ.
CLI_ARAMA = (Path(r"C:\ST"), Path(r"C:\Program Files\STMicroelectronics"))
BANNER_SURESI = 12.0

# ── SONUÇ KODLARI — CLI çıkışı ve otomasyon dallanması AYNI kaynaktan ────────────
TAMAM = 0
BIN_YOK = 2
BUTUNLUK = 3
DONANIM_MESGUL = 4
YAKICI_YOK = 5
YEDEK_ALINAMADI = 6
YAKMA_HATASI = 7
UYUMSUZ_GERI_DONULDU = 8
BANNER_TANINMADI = 9


@dataclass
class Sonuc:
    kod: int
    ozet: str = ""
    banner: str = ""
    sha256: str = ""
    yedek: str = ""
    adimlar: list[str] = field(default_factory=list)

    @property
    def tamam(self) -> bool:
        return self.kod == TAMAM


# ══════════════════════════════════════════════════════════════════════════════
def programmer_cli() -> Path | None:
    """`STM32_Programmer_CLI.exe` — PATH'te ya da CubeIDE eklentileri altında (glob)."""
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


def _json_al(url: str, timeout: float = 5.0):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace") or "{}")
    except (urllib.error.URLError, OSError, ValueError):
        return None


def seans_ve_bobin_kontrolu(backend: str) -> tuple[bool, str]:
    """(guvenli_mi, açıklama). Bkz. modül başlığındaki 1-3 numaralı değişmezler."""
    saglik = _json_al(f"{backend}/api/health")
    if saglik is None:
        return True, "backend kapalı (kimse bobin sürmüyor) — güvenli"
    if saglik.get("sessionActive"):
        return False, (
            "AKTİF SEANS VAR. Yakma MCU'yu resetler ve bobinler ANİDEN durur; hasta "
            "üzerindeyken bu kabul edilemez. Seansı bitirip tekrar deneyin."
        )
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
    """Karttaki MEVCUT firmware'i oku. ⚠️ Alınamazsa YAKILMAZ."""
    hedef.parent.mkdir(parents=True, exist_ok=True)
    rc, cikti = _kos(cli, ["-c", "port=SWD", "-r", YAKMA_ADRESI, str(boyut), str(hedef)])
    if rc != 0 or not hedef.is_file() or hedef.stat().st_size == 0:
        return False, cikti[-600:]
    return True, str(hedef)


def yak(cli: Path, ikili: Path) -> tuple[bool, str]:
    rc, cikti = _kos(cli, ["-c", "port=SWD", "-w", str(ikili), YAKMA_ADRESI, "-v", "-rst"], timeout=600.0)
    return rc == 0, cikti[-1200:]


def banner_dogrula(port: str | None = None) -> tuple[bool | None, str, str]:
    """(uyumlu, sebep, ham_banner). Kart KENDİ kimliğini söylemeden yakma başarılı sayılmaz."""
    portlar = port_adaylari(port)
    if not portlar:
        return None, "seri port bulunamadı — banner okunamadı", ""
    for p in portlar:
        try:
            _kanal, satirlar = banner_dinle(p, BANNER_SURESI)
        except Exception:  # noqa: BLE001 — port meşgul/yok: sonraki adaya geç
            continue
        for satir in satirlar:
            if "STM_READY" not in satir:
                continue
            uyumlu, sebep = uyum_denetle(banner_ayristir(satir), STM_PAKET_BOBIN_SAYISI)
            return uyumlu, sebep or "banner uyumlu", satir
    return None, "STM_READY satırı hiç görülmedi (karta RESET atmayı deneyin)", ""


# ══════════════════════════════════════════════════════════════════════════════
def yakma_akisi(
    ikili: Path,
    *,
    beklenen_sha256: str = "",
    port: str | None = None,
    backend: str = "http://127.0.0.1:8000",
    yedek_dizin: Path | None = None,
    kuru: bool = False,
) -> Sonuc:
    """Tam akış. Yan etkiler YALNIZ burada; karar mantığı yukarıdaki parçalarda."""
    adimlar: list[str] = []
    ikili = Path(ikili).resolve()
    if not ikili.is_file():
        return Sonuc(BIN_YOK, f".bin yok: {ikili}", adimlar=adimlar)

    ozet = sha256(ikili)
    adimlar.append(f"ikili {ikili.name} ({ikili.stat().st_size} bayt) sha256={ozet}")
    if beklenen_sha256 and beklenen_sha256.lower() != ozet:
        return Sonuc(BUTUNLUK, f"beklenen {beklenen_sha256.lower()}, bulunan {ozet}", sha256=ozet, adimlar=adimlar)

    guvenli, aciklama = seans_ve_bobin_kontrolu(backend.rstrip("/"))
    adimlar.append(f"donanım: {aciklama}")
    if not guvenli:
        return Sonuc(DONANIM_MESGUL, aciklama, sha256=ozet, adimlar=adimlar)

    cli = programmer_cli()
    if cli is None:
        return Sonuc(YAKICI_YOK, "STM32_Programmer_CLI bulunamadı (CubeIDE kurulu mu?)", sha256=ozet, adimlar=adimlar)
    adimlar.append(f"yakıcı: {cli}")

    if kuru:
        return Sonuc(TAMAM, "KURU KOŞUM — kontroller geçti, yakma yapılmadı", sha256=ozet, adimlar=adimlar)

    kok = Path(yedek_dizin or (ikili.parent / "firmware_yedek"))
    yedek = kok / f"pemf_yedek_{time.strftime('%Y%m%d_%H%M%S')}.bin"
    tamam, bilgi = yedek_al(cli, yedek, ikili.stat().st_size)
    adimlar.append(f"yedek: {'alındı ' + bilgi if tamam else 'ALINAMADI'}")
    if not tamam:
        return Sonuc(
            YEDEK_ALINAMADI,
            "yedek alınamadı — geri dönüşü olmayan işlem YAPILMAZ: " + bilgi,
            sha256=ozet,
            adimlar=adimlar,
        )

    tamam, cikti = yak(cli, ikili)
    adimlar.append("yakma: " + ("yazıldı + doğrulandı" if tamam else "YAKICI HATA"))
    if not tamam:
        return Sonuc(YAKMA_HATASI, cikti, sha256=ozet, yedek=str(yedek), adimlar=adimlar)

    time.sleep(2.0)  # kart açılış banner'ını bassın
    uyumlu, sebep, ham = banner_dogrula(port)
    adimlar.append(f"banner: {ham or '(okunamadı)'} → uyum={uyumlu} ({sebep})")

    if uyumlu is False:
        geri, _ = yak(cli, yedek)
        adimlar.append("GERİ DÖNÜŞ: " + ("eski firmware yakıldı" if geri else "BAŞARISIZ"))
        return Sonuc(UYUMSUZ_GERI_DONULDU, sebep, banner=ham, sha256=ozet, yedek=str(yedek), adimlar=adimlar)

    if uyumlu is None:
        # ⚠️ Geri dönüş sebebi DEĞİL — üç-durumlu karar (bkz. modül başlığı, 6).
        return Sonuc(BANNER_TANINMADI, sebep, banner=ham, sha256=ozet, yedek=str(yedek), adimlar=adimlar)

    return Sonuc(
        TAMAM, "yakıldı ve kart kendi kimliğiyle doğruladı", banner=ham, sha256=ozet, yedek=str(yedek), adimlar=adimlar
    )
