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
     Ayrım: backend YOK ≠ backend VAR ama cevap vermiyor. ⚠️ D1.108/D1.111: "YOK" YALNIZ bağlantı
     reddidir (5xx/4xx/zaman aşımı/JSON-dışı/PEMF olmayan yanıt = "VAR ama doğrulanamıyor"); bu HTTP
     ayrımı yalnız AYRI süreçteki CLI içindir. Backend'in KENDİ yakması süreç içi durumu okur
     (`yakma_akisi(guvenlik_kontrolu=…)` — açılış denetimi `server.run()`'dan önce koşar, kendine soramaz).
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
from collections.abc import Callable
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


#: Ön kontrol HTTP zaman aşımları (sn) — yalnız AYRI süreçteki CLI yolu (`seans_ve_bobin_kontrolu`).
SAGLIK_ZAMAN_ASIMI_S = 5.0
ANLIK_ZAMAN_ASIMI_S = 8.0

#: `_json_al` sınıfları. ⚠️ D1.108 (B-10.12) + D1.111 (B-4.9): YALNIZ bağlantı reddi (portta kimse dinlemiyor) `KAPALI`dır.
HTTP_TAMAM = "tamam"
HTTP_KAPALI = "kapali"
HTTP_BELIRSIZ = "belirsiz"


def _baglanti_reddi_mi(hata: BaseException) -> bool:
    return isinstance(hata, ConnectionRefusedError) or isinstance(getattr(hata, "reason", None), ConnectionRefusedError)


def _json_al(url: str, timeout: float = 5.0) -> tuple[dict | None, str]:
    """(gövde, sınıf). Sınıf: `HTTP_TAMAM` (JSON nesnesi) · `HTTP_KAPALI` (YALNIZ bağlantı reddi) · `HTTP_BELIRSIZ`.

    ⚠️ D1.108 (B-10.12) + D1.111 (B-4.9): eskiden HER hata (5xx, 404, zaman aşımı, JSON-dışı gövde) `None` dönüyor ve
    `None` "backend kapalı — güvenli" okunuyordu: 5xx veren / asılı bir backend ya da o porttaki PEMF olmayan bir süreç
    bobin sürülürken yakmaya izin veriyordu. Artık yalnız bağlantı reddi "kapalı"; geri kalan her yanıt `BELIRSIZ` — o
    portta bir süreç VAR ve bobin durumu doğrulanamaz (fail-closed)."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            ham = r.read()
    except urllib.error.HTTPError:  # URLError'ın alt sınıfı — ÖNCE yakalanır: biri dinliyor ama 4xx/5xx
        return None, HTTP_BELIRSIZ
    except urllib.error.URLError as e:
        return None, (HTTP_KAPALI if _baglanti_reddi_mi(e) else HTTP_BELIRSIZ)
    except OSError as e:  # zaman aşımı (TimeoutError), bağlantı sıfırlandı…
        return None, (HTTP_KAPALI if _baglanti_reddi_mi(e) else HTTP_BELIRSIZ)
    try:
        veri = json.loads(ham.decode("utf-8", "replace"))
    except ValueError:
        return None, HTTP_BELIRSIZ
    return (veri, HTTP_TAMAM) if isinstance(veri, dict) else (None, HTTP_BELIRSIZ)


def seans_ve_bobin_kontrolu(backend: str) -> tuple[bool, str]:
    """(guvenli_mi, açıklama) — HTTP ön kontrolü: YALNIZ AYRI süreçteki CLI içindir (`scripts/stm_yak.py`).

    ⚠️ Backend'in KENDİ yakma kararı bunu KULLANMAZ: açılış denetimi `server.run()`'dan ÖNCE koşar, kendine HTTP soramaz —
    süreç içi seans/bobin durumunu okur (`firmware_manager._surec_ici_guvenlik_kontrolu`, `yakma_akisi(guvenlik_kontrolu=…)`).
    Bkz. modül başlığındaki 1-3 numaralı değişmezler: yalnız bağlantı reddi "backend kapalı" (fail-open, bilerek); 5xx /
    4xx / zaman aşımı / JSON-dışı / PEMF olmayan yanıt "doğrulanamadı" (fail-closed)."""
    saglik, sinif = _json_al(f"{backend}/api/health", timeout=SAGLIK_ZAMAN_ASIMI_S)
    if sinif == HTTP_KAPALI:
        return True, "backend kapalı (bağlantı reddedildi — portta kimse dinlemiyor, kimse bobin sürmüyor) — güvenli"
    if saglik is None:
        return False, (
            "Backend durumu DOĞRULANAMADI (`/api/health` 5xx / 4xx / zaman aşımı / JSON-dışı yanıt): o portta bir süreç "
            "VAR ama seans/bobin durumu okunamıyor. Doğrulanamayan durumda yakılmaz — backend'i kapatıp tekrar deneyin."
        )
    if not isinstance(saglik.get("sessionActive"), bool):
        return False, (
            "`/api/health` yanıtı seans bilgisini (`sessionActive`) vermiyor — o portta PEMF backend'i olmayan bir servis "
            "olabilir ya da istek loopback değil. Doğrulanamayan durumda yakılmaz."
        )
    if saglik["sessionActive"]:
        return False, (
            "AKTİF SEANS VAR. Yakma MCU'yu resetler ve bobinler ANİDEN durur; hasta "
            "üzerindeyken bu kabul edilemez. Seansı bitirip tekrar deneyin."
        )
    anlik, _ = _json_al(f"{backend}/api/dashboard-snapshot", timeout=ANLIK_ZAMAN_ASIMI_S)
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


#: `_kos` istisnayı buraya çevirir. Yakıcının kendi kodlarıyla çakışmayacak kadar yüksek.
KOSUM_ISTISNASI = 90


def _kos(cli: Path, argumanlar: list[str], timeout: float = 300.0) -> tuple[int, str]:
    """Yakıcıyı çalıştır; **hiçbir istisna dışarı sızmaz** — hata KODA çevrilir.

    ⚠️ BU BİR AÇILIŞ YOLUDUR. `backend_service.main()` → `_donanim_guncellemesi_safe`
    → `firmware_manager.acilis_denetimi` → `yakma_akisi` → buraya iner. `subprocess.run`
    zaman aşımında `TimeoutExpired`, yakıcı keşiften sonra silinirse `OSError` fırlatır.
    Bu istisnalar eskiden `yedek_al`/`yak`/`yakma_akisi` boyunca YAKALANMADAN yükseliyordu;
    en üstte `_donanim_guncellemesi_safe` onları yutuyordu — ama ancak yakıcı asılmayı
    BİTİRDİKTEN sonra. O ana kadar açılış BLOKE (yedekte 300 sn, yakmada 600 sn) ve
    günlükte "zaman aşımı" diye bir şey YAZMIYORDU.

    İstisnayı koda çevirmek çağıranları DEĞİŞTİRMEDEN doğru dala düşürür (hepsi `rc != 0`
    denetliyor): `yedek_al` → YEDEK_ALINAMADI, `yak` → YAKMA_HATASI.
    ⚠️ Bu, "yedek alınamazsa YAKMA" değişmezini KORUR — asılan bir yedek alınmış sayılmaz.

    Kapı: `tests/test_stm_yakma_ZAMAN_ASIMI_YUTULUR.py` (çıpa davranışta, kaynakta değil).
    """
    try:
        r = subprocess.run(
            [str(cli), *argumanlar],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return KOSUM_ISTISNASI, f"ZAMAN AŞIMI: yakıcı {timeout:.0f} sn içinde bitmedi ({cli.name})"
    except OSError as e:
        return KOSUM_ISTISNASI, f"YAKICI ÇALIŞTIRILAMADI: {cli} — {e}"
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
    guvenlik_kontrolu: Callable[[], tuple[bool, str]] | None = None,
    yedek_dizin: Path | None = None,
    kuru: bool = False,
) -> Sonuc:
    """Tam akış. Yan etkiler YALNIZ burada; karar mantığı yukarıdaki parçalarda.

    `guvenlik_kontrolu`: verilirse seans/bobin ön kontrolü BUNUNLA yapılır (backend'in kendi yakması — süreç içi durum,
    D1.108 + D1.111); verilmezse `backend` adresine HTTP ön kontrolü (CLI). İstisna fırlatırsa yakılmaz (fail-closed)."""
    adimlar: list[str] = []
    ikili = Path(ikili).resolve()
    if not ikili.is_file():
        return Sonuc(BIN_YOK, f".bin yok: {ikili}", adimlar=adimlar)

    ozet = sha256(ikili)
    adimlar.append(f"ikili {ikili.name} ({ikili.stat().st_size} bayt) sha256={ozet}")
    if beklenen_sha256 and beklenen_sha256.lower() != ozet:
        return Sonuc(BUTUNLUK, f"beklenen {beklenen_sha256.lower()}, bulunan {ozet}", sha256=ozet, adimlar=adimlar)

    if guvenlik_kontrolu is not None:
        try:
            guvenli, aciklama = guvenlik_kontrolu()
        except Exception as e:  # noqa: BLE001 — doğrulanamayan durumda yakılmaz
            guvenli, aciklama = False, f"seans/bobin durumu DOĞRULANAMADI ({type(e).__name__}) — yakılmaz"
    else:
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
