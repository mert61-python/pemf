# -*- coding: utf-8 -*-
"""STM32 FIRMWARE OTOMATİK GÜNCELLEME — manifest → plan → indir → yak → doğrula.

SAHİP KARARI (2026-09-22): *"cihaz kendi alcak… pemf uygulaması ilk açılışta client
güncelleme kontrol ediyor zaten, ardından stm için de güncelleme kontrol etcek donanım
güncellemesi ismi altında, varsa güncelleyecek sonra açılacak. bu sırada stm bağlı ya da
bağlı değil, internet var yok ayrımları temiz yapılmalı… bu işlemler tamamen otomatik
olmalı, kullanıcı müdahalesi minimumda."*

═══════════════════════════════════════════════════════════════════════════════
İŞ BÖLÜMÜ — üç modül, üç ayrı sorumluluk
═══════════════════════════════════════════════════════════════════════════════
  · `utils/surum_uyumu`   → **KARAR** (hangi ikili uyumlu, uyumsuzsa ne yapılmalı)
  · `utils/stm_yakma`     → **YAKMA** (ön kontrol, yedek, yak, banner, geri dön)
  · bu modül              → **ORKESTRASYON** (manifest, indirme, sıra, durum)

Ayrı tutulmalarının sebebi ölçülebilirlik: karar donanımsız/ağsız sınanır, yakma
donanımsız sınanır, burası da ikisini yamalayarak sınanır.

═══════════════════════════════════════════════════════════════════════════════
DEĞİŞMEZLER
═══════════════════════════════════════════════════════════════════════════════
⚠️ **ACİL DURDURMA ASLA KAPILANMAZ.** Bu modül seansı/E-stop'u engellemez; yalnız
   güncelleme yapar. (Kayıtlı ilke — `SurumFarkiBanner`: *"bir tıbbi cihazın uzaktan ACİL
   DURDURMASINI sürüm eşleşmesine bağlamak kabul edilemez"*.)
⚠️ **FAIL-QUIET, FAIL-SILENT DEĞİL.** İnternet yoksa / STM bağlı değilse kullanıcı
   rahatsız edilmez ama durum `durum()` ile GÖRÜNÜR kalır — internetsiz klinikte sahte
   uyarı üretilmez, destek mühendisi de neden atlandığını okur.
⚠️ **İNDİRME ZİNCİRİ YENİDEN YAZILMADI.** `update_manager`ın host-pin'i
   (`_validate_installer_url` — DÖNÜŞÜ okunur, D1.110), yönlendirme denetimli açıcısı (`_pinli_ac`),
   boyut tavanı (`_download_to`) ve özel geçici dizini (`_private_temp_path`) AYNEN kullanılır. İkinci
   bir indirici, ikinci bir güvenlik yüzeyi demektir; bu depoda "aynı kural iki yerde" sınıfının bedeli
   ölçülmüştür.
⚠️ **SHA256 ZORUNLU.** Manifest özet vermiyorsa firmware YAKILMAZ. Yakma geri dönüşü
   pahalı bir işlemdir; doğrulanmamış ikili yakılmaz.
"""

from __future__ import annotations

import json
import logging
import threading
import urllib.request
from pathlib import Path

from utils import surum_uyumu as su

from servers import update_manager as um

logger = logging.getLogger("firmware_manager")

#: Firmware ikilisi için boyut tavanı. STM32F429 uygulama alanı ~2 MB; 8 MB bol pay.
#: ⚠️ `update_manager._MAX_INSTALLER_BYTES` (512 MB) BURADA KULLANILMAZ — firmware çok
#: daha küçüktür ve dar tavan, bozuk/ele geçmiş bir sunucuya karşı daha iyi korur.
_MAX_FIRMWARE_BYTES = 8 * 1024 * 1024

_durum_kilidi = threading.Lock()
_durum: dict = {
    "kontrol_edildi": False,
    "eylem": su.EYLEM_YOK,
    "gerekce": "henüz kontrol edilmedi",
    "clientSurum": "",
    "firmwareSurum": "",
    "hedefSurum": "",
    "uygulandi": False,
    "hata": "",
}


def durum() -> dict:
    """`/api/health` ve destek paketi için anlık görüntü. ⚠️ Sır/DEĞER taşımaz."""
    with _durum_kilidi:
        return dict(_durum)


def _durum_yaz(**alanlar) -> dict:
    with _durum_kilidi:
        _durum.update(alanlar)
        return dict(_durum)


# ══════════════════════════════════════════════════════════════════════════════
# MANIFEST
# ══════════════════════════════════════════════════════════════════════════════
def manifest_oku(timeout: float = 15.0) -> dict | None:
    """`latest.json`daki `firmware.stm32` + `uyumluluk`. Ağ yoksa None (fail-quiet).

    Beklenen biçim:
        {"firmware": {"stm32": {"version": "2.3", "url": "...", "sha256": "...",
                                "previousStable": {"version": "...", "url": "...", "sha256": "..."}}},
         "uyumluluk": [{"clientMin": "...", "clientMax": "", "firmwareMin": "...", "firmwareMax": ""}]}
    """
    try:
        istek = urllib.request.Request(
            um._MANIFEST_URL, headers={"User-Agent": "pemf-fw-updater", "Cache-Control": "no-cache"}
        )
        with urllib.request.urlopen(istek, timeout=timeout) as r:
            ham = r.read(um._MAX_MANIFEST_BYTES + 1)
        if len(ham) > um._MAX_MANIFEST_BYTES:
            raise ValueError("manifest boyut tavanını aştı — reddedildi")
        return json.loads(ham.decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        # ⚠️ exc_info ŞART: bu depoda `logger.info(..., e)` bir kök nedeni saatlerce gizledi
        # (A9). "İnternet yok" ile "manifest bozuk" farklı arızalardır.
        logger.warning("firmware manifesti okunamadı (%s) — kontrol atlanıyor", type(e).__name__, exc_info=True)
        return None


def _stm32_girdisi(manifest: dict) -> dict:
    fw = manifest.get("firmware")
    if not isinstance(fw, dict):
        return {}
    girdi = fw.get("stm32")
    return girdi if isinstance(girdi, dict) else {}


def _kurallar(manifest: dict) -> list[dict]:
    k = manifest.get("uyumluluk")
    return [x for x in k if isinstance(x, dict)] if isinstance(k, list) else []


# ══════════════════════════════════════════════════════════════════════════════
# İNDİRME — update_manager'ın güvenlik zinciriyle
# ══════════════════════════════════════════════════════════════════════════════
def firmware_indir(url: str, beklenen_sha256: str) -> tuple[Path | None, str]:
    """(yol, hata). ⚠️ SHA256 ZORUNLU — özet yoksa/tutmuyorsa dosya SİLİNİR."""
    if not url:
        return None, "manifest firmware url'i vermiyor"
    if not beklenen_sha256:
        return None, "manifest SHA256 vermiyor — doğrulanmamış firmware YAKILMAZ"
    # ⚠️ D1.110 (B-4.1): `_validate_installer_url` istisna FIRLATMAZ, (ok, hata) DÖNER — eskiden ifade-deyimi olarak
    # çağrılıp dönüşü atılıyordu: `http://…`, yabancı host ve `../` atlatması dahil HER URL indiriliyordu (özet de aynı
    # manifestten geldiği için eşleşir). Reddedilen URL'de ağa ÇIKILMAZ, geçici dizin de AÇILMAZ.
    ok, neden = um._validate_installer_url(url)
    if not ok:
        return None, f"firmware url'i reddedildi: {neden}"

    hedef = um._private_temp_path("pemf_fw.bin")
    try:
        # D1.110: yönlendirme hedefi de her adımda doğrulanır (`urlopen` 302'leri — `http://` dahil — sessizce izliyordu).
        with um._pinli_ac(url, timeout=120, headers={"User-Agent": "pemf-fw-updater"}) as r, open(hedef, "wb") as f:
            um._download_to(r, f, _MAX_FIRMWARE_BYTES, "firmware")
    except Exception as e:  # noqa: BLE001
        logger.warning("firmware indirilemedi (%s)", type(e).__name__, exc_info=True)
        try:
            hedef.unlink(missing_ok=True)
        except OSError as se:
            logger.warning("geçici firmware dosyası silinemedi: %s", se)
        return None, f"indirme başarısız: {type(e).__name__}"

    from utils.stm_yakma import sha256 as _ozet

    bulunan = _ozet(hedef)
    if bulunan != beklenen_sha256.lower():
        try:
            hedef.unlink(missing_ok=True)
        except OSError as se:
            logger.warning("bütünlüğü bozuk firmware silinemedi: %s", se)
        return None, f"SHA256 tutmadı (beklenen {beklenen_sha256.lower()}, bulunan {bulunan})"
    return hedef, ""


# ══════════════════════════════════════════════════════════════════════════════
# AÇILIŞ DENETİMİ — sahip: "client kontrolünden SONRA, açılmadan ÖNCE"
# ══════════════════════════════════════════════════════════════════════════════
def acilis_denetimi(
    *,
    firmware_surum: str,
    stm_bagli: bool,
    backend: str = "http://127.0.0.1:8000",
    uygula: bool = True,
) -> dict:
    """Uyumu ölç, plan yap, gerekirse uygula. Her yol `durum()`a yazar.

    ⚠️ HİÇBİR DALI SESSİZ DEĞİL: internet yok / STM bağlı değil / kural yok / uyumlu —
    hepsi gerekçesiyle kaydedilir. "Atlandı" ile "yapıldı" ayırt edilebilmeli.
    """
    client = um.get_current_version()
    manifest = manifest_oku()
    if manifest is None:
        # 🔴 KAPI BU KUSURU YAKALADI (2026-09-22): önce boş kural listesiyle `plan_yap`
        #    çağırıyordum. Boş kural → karar `None` → plan `EYLEM_YOK` dönüyordu ve rapor
        #    "yok" oluyordu. Yani **"uyumlu, yapacak bir şey yok"** ile **"kontrol
        #    EDEMEDİM"** AYNI görünüyordu — kendi yazdığım "atlandı ile yapıldı ayırt
        #    edilebilmeli" değişmezinin ihlali.
        #    Manifest okunamaması bir UYUM kararı değildir; doğrudan BEKLE'dir.
        return _durum_yaz(
            kontrol_edildi=True,
            eylem=su.BEKLE,
            gerekce="manifest okunamadı (internet yok ya da sunucu erişilemez) — "
            "donanım güncellemesi kontrolü ERTELENDİ",
            clientSurum=client,
            firmwareSurum=firmware_surum,
            hedefSurum="",
            uygulandi=False,
            hata="",
        )

    girdi = _stm32_girdisi(manifest)
    plan = su.plan_yap(
        client,
        firmware_surum,
        _kurallar(manifest),
        yeni_firmware=str(girdi.get("version", "")),
        onceki_client=str((um.get_status().get("previousStable") or {}).get("version", "")),
        internet=True,
        stm_bagli=stm_bagli,
    )
    _durum_yaz(
        kontrol_edildi=True,
        eylem=plan.eylem,
        gerekce=plan.gerekce,
        clientSurum=client,
        firmwareSurum=firmware_surum,
        hedefSurum=plan.hedef_surum,
        uygulandi=False,
        hata="",
    )
    if not uygula or plan.eylem in (su.EYLEM_YOK, su.BEKLE):
        logger.info("donanım güncellemesi: %s — %s", plan.eylem, plan.gerekce)
        return durum()

    if plan.eylem == su.FIRMWARE_GUNCELLE:
        return _firmware_uygula(girdi, plan, backend)

    if plan.eylem == su.CLIENT_GERI_AL:
        # ⚠️ Client'ı geri almak `update_manager.rollback()`un işi — burada YENİDEN YAZILMAZ.
        #    O zincir Authenticode + SHA256 + "aktif tedavi yok" kapılarını zaten uygular.
        sonuc = um.rollback()
        return _durum_yaz(
            uygulandi=bool(sonuc.get("ok")),
            hata="" if sonuc.get("ok") else str(sonuc.get("error", "client geri alınamadı")),
        )

    return durum()


def _firmware_uygula(girdi: dict, plan: su.Plan, backend: str) -> dict:
    yol, hata = firmware_indir(str(girdi.get("url", "")), str(girdi.get("sha256", "")))
    if yol is None:
        logger.warning("firmware indirilemedi: %s", hata)
        return _durum_yaz(uygulandi=False, hata=hata)

    from utils.stm_yakma import TAMAM, yakma_akisi

    sonuc = yakma_akisi(yol, beklenen_sha256=str(girdi.get("sha256", "")), backend=backend)
    for adim in sonuc.adimlar:
        logger.info("firmware: %s", adim)
    try:
        yol.unlink(missing_ok=True)
    except OSError as e:
        logger.warning("geçici firmware dosyası silinemedi: %s", e)

    if sonuc.kod == TAMAM:
        logger.info("donanım güncellemesi TAMAM → %s", plan.hedef_surum)
        return _durum_yaz(uygulandi=True, hata="", firmwareSurum=plan.hedef_surum)
    logger.warning("donanım güncellemesi BAŞARISIZ (kod %s): %s", sonuc.kod, sonuc.ozet)
    return _durum_yaz(uygulandi=False, hata=f"[{sonuc.kod}] {sonuc.ozet}")
