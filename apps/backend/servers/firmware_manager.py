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
import urllib.error
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
    # D1.119 · Y16 — LAUNCHER'ın okuyacağı durum (`/api/health` → `firmwareGuncelleme`): uyum (True/False/None) ve
    # "client geri alınmalı" sinyali (KESİN uyumsuz + STM bağlı + ileri gidilemiyor). Geri almayı LAUNCHER yapar.
    "uyum": None,
    "istemciGeriAlinmali": False,
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
#: ⚠️ Y17 (sahip) · D1.120: firmware uyum kuralları AYRI bir yayın varlığındadır — `exe/latest.json`'a BAĞLANMAZ (o dosya
#: 2026-07-01'den beri değişmemiş, kapalı eski EXE kanalının 1.4.0 taslağı — B-4.25). Varlığı yayınlamak sahibin "yayınla"
#: kararıdır; yayınlanmamışsa (HTTP 404) "kural yok" → EYLEM_YOK (hata DEĞİL). Biçim `manifest_oku` belgesinde.
UYUM_ETIKETI = "firmware-uyum"
UYUM_VARLIGI = "firmware_uyum.json"
UYUM_URL = f"https://github.com/{um._UPDATE_REPO}/releases/download/{UYUM_ETIKETI}/{UYUM_VARLIGI}"


def manifest_oku(timeout: float = 15.0) -> dict | None:
    """Y17 firmware uyum varlığı (`UYUM_URL`) → `firmware.stm32` + `uyumluluk`. Varlık yayınlanmamışsa (404) `{}` = "kural
    yok"; ağ yok / bozuk / tavan aşımı → None (fail-quiet: BEKLE). İndirme zincirinin AYNISI: kaynak pini
    (`_validate_installer_url`, dönüşü okunur) + her yönlendirmesi doğrulanan açıcı (`_pinli_ac`) + boyut tavanı.

    Beklenen biçim:
        {"firmware": {"stm32": {"version": "2.4", "url": "https://github.com/<depo>/releases/download/…/pemf_fw.bin",
                                "sha256": "...", "previousStable": {"version": "...", "url": "...", "sha256": "..."}}},
         "uyumluluk": [{"clientMin": "...", "clientMax": "", "firmwareMin": "...", "firmwareMax": ""}]}
    """
    ok, hata = um._validate_installer_url(UYUM_URL)
    if not ok:
        logger.error("firmware uyum varlığının adresi pin dışında (%s) — kontrol atlanıyor", hata)
        return None
    try:
        with um._pinli_ac(
            UYUM_URL, timeout=timeout, headers={"User-Agent": "pemf-fw-updater", "Cache-Control": "no-cache"}
        ) as r:
            ham = r.read(um._MAX_MANIFEST_BYTES + 1)
        if len(ham) > um._MAX_MANIFEST_BYTES:
            raise ValueError("manifest boyut tavanını aştı — reddedildi")
        veri = json.loads(ham.decode("utf-8"))
        if not isinstance(veri, dict):
            raise ValueError("firmware uyum varlığı bir JSON nesnesi değil")
        return veri
    except urllib.error.HTTPError as e:
        if e.code == 404:
            logger.info("firmware uyum varlığı YAYINLANMAMIŞ (404, Y17) — uyumluluk kuralı yok")
            return {}
        logger.warning("firmware uyum varlığı okunamadı (HTTP %s) — kontrol atlanıyor", e.code)
        return None
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
        _gecici_sil(hedef)
        return None, f"indirme başarısız: {type(e).__name__}"

    from utils.stm_yakma import sha256 as _ozet

    bulunan = _ozet(hedef)
    if bulunan != beklenen_sha256.lower():
        _gecici_sil(hedef)
        return None, f"SHA256 tutmadı (beklenen {beklenen_sha256.lower()}, bulunan {bulunan})"
    return hedef, ""


def _gecici_sil(yol: Path) -> None:
    """D1.115 (B-4.10): indirilen dosya VE `_private_temp_path`'in açtığı `pemf_upd_*` dizini silinir. Eskiden yalnız dosya
    siliniyordu: her başarısız/başarılı deneme %TEMP%'te yetim bir dizin bırakıyordu (1-H'de ölçüldü: 10 deneme → 10 dizin)."""
    try:
        Path(yol).unlink(missing_ok=True)
    except OSError as e:
        logger.warning("geçici firmware dosyası silinemedi: %s", e)
    um._discard_temp_dir(yol)


#: D1.115 (B-4.10): veri kökündeki kalıcı firmware yedeklerinden en yeni bu kadarı tutulur (elle kurtarma / geri dönüş).
FIRMWARE_YEDEK_TUT = 5


def _yedek_dizini() -> Path | None:
    """D1.115 (B-4.10): eski firmware'in yedeği veri kökündeki KALICI `firmware_yedek` dizinine yazılır. Eskiden
    `yakma_akisi` varsayılanı (`ikili.parent / "firmware_yedek"`) — yani GEÇİCİ indirme dizininin İÇİ — kullanılıyordu:
    elle kurtarmada gereken eski firmware'in yeri yalnız INFO günlüğünde kalıyor, dizinle birlikte kayboluyordu.
    Veri kökü çözülemezse None (varsayılana düşer, uyarı yazılır)."""
    try:
        from utils import path_utils

        return Path(path_utils.get_app_data_directory()) / "firmware_yedek"
    except Exception as e:  # noqa: BLE001
        logger.warning("firmware yedek dizini çözülemedi (%s) — yedek geçici dizine yazılacak", type(e).__name__)
        return None


def _yedekleri_buda(kok: Path | None, tut: int = FIRMWARE_YEDEK_TUT) -> None:
    """En yeni `tut` yedek kalır (ad = zaman damgası → kronolojik). Silinemeyen yedek yalnız günlüğe yazılır."""
    if kok is None or tut < 1 or not kok.is_dir():
        return
    for eski in sorted(kok.glob("pemf_yedek_*.bin"))[:-tut]:
        try:
            eski.unlink()
        except OSError as e:
            logger.warning("eski firmware yedeği silinemedi: %s — %s", eski.name, e)


# ══════════════════════════════════════════════════════════════════════════════
# AÇILIŞ DENETİMİ — sahip: "client kontrolünden SONRA, açılmadan ÖNCE"
# ══════════════════════════════════════════════════════════════════════════════
def _surec_ici_guvenlik_kontrolu() -> tuple[bool, str]:
    """D1.108 + D1.111 (B-10.12 · B-4.9) — backend'in KENDİ yakma kararının ön kontrolü SÜREÇ İÇİ durumu okur.

    ⚠️ HTTP DEĞİL: açılış denetimi `server.run()`'dan ÖNCE koşar; `127.0.0.1:<port>/api/health` ya bağlantı reddi alır
    ("backend kapalı → güvenli" — süreç kendisi bobin sürüyor olsa bile) ya da o portta BAŞKA bir süreç cevap verir. Üç
    kaynaktan biri "aktif" derse ya da okunamazsa YAKILMAZ (fail-closed): resmi seans (`_active_session`), STM
    keep-alive'ının sürdüğü bobinler (`HardwareController.calisan_bobin_durumu`) ve seans dışı sürülen bobinler dahil canlı
    durum (`update_manager._has_active_treatment` — `/api/health` `sessionActive`'in de kaynağı)."""
    try:
        from servers import api_server as api

        if api._active_session.get("is_active"):
            return False, "AKTİF SEANS VAR (süreç içi) — yakma MCU'yu resetler, bobinler ANİDEN durur; yakılmaz"
        hw = getattr(api.state, "hardware", None)
        calisan = hw.calisan_bobin_durumu() if hw is not None else {}
        if calisan:
            return False, f"BOBİN SÜRÜLÜYOR (süreç içi, STM): {sorted(calisan)} — yakılmaz"
        if um._has_active_treatment():
            return False, "AKTİF TEDAVİ / SÜRÜLEN BOBİN VAR (süreç içi canlı durum) — yakılmaz"
    except Exception as e:  # noqa: BLE001 — doğrulanamayan durumda yakılmaz
        return False, f"seans/bobin durumu süreç içinden OKUNAMADI ({type(e).__name__}) — yakılmaz"
    return True, "seans yok, bobin sürülmüyor (süreç içi)"


def acilis_denetimi(
    *,
    firmware_surum: str,
    stm_bagli: bool,
    uygula: bool = True,
    banner_kaynagi=None,
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
            uyum=None,
            istemciGeriAlinmali=False,
        )

    girdi = _stm32_girdisi(manifest)
    kurallar = _kurallar(manifest)
    uyum, _uyum_gerekcesi = su.uyumlu_mu(client, firmware_surum, kurallar)
    # ⚠️ D1.119 · Y16 (sahip): "client güncellenip STM güncellenmezse client geri döner" kararını LAUNCHER (sağlık kapılı
    # geri alma) uygular — backend client'ı GERİ ALMAZ, eski EXE kanalı (`update_manager.rollback()`, Inno) AÇILMAZ.
    # Eskiden `previousStable` eski kanalın manifestinden okunup `CLIENT_GERI_AL` dalında `um.rollback()` çağrılıyordu:
    # kanal kapalıyken (varsayılan) ölüydü; `PEMF_LEGACY_EXE_UPDATE=1` ile açıkken launcher'ın yönettiği kurulumun YANINA
    # ikinci bir kurulum yapardı (split-brain hasta DB'si). Artık `onceki_client` VERİLMEZ (plan geri almayı önermez);
    # durum `uyum` + `istemciGeriAlinmali` ile launcher'a bildirilir (`/api/health` → `firmwareGuncelleme`, D1.116).
    # Launcher (Rust) tarafı bu sinyali henüz OKUMUYOR — launcher oturumunun açık maddesi (docs/LAUNCHER_SPEC.md).
    plan = su.plan_yap(
        client,
        firmware_surum,
        kurallar,
        yeni_firmware=str(girdi.get("version", "")),
        onceki_client="",
        internet=True,
        stm_bagli=stm_bagli,
    )
    istemci_geri = bool(uyum is False and stm_bagli and plan.eylem == su.BEKLE)
    gerekce = plan.gerekce
    if istemci_geri:
        gerekce += (
            " — client geri alma LAUNCHER'ın işi (Y16): launcher `istemciGeriAlinmali`yı okuyup sağlık kapılı geri alır; "
            "backend client'ı geri ALMAZ (eski EXE kanalı açılmaz)"
        )
    _durum_yaz(
        kontrol_edildi=True,
        eylem=plan.eylem,
        gerekce=gerekce,
        clientSurum=client,
        firmwareSurum=firmware_surum,
        hedefSurum=plan.hedef_surum,
        uygulandi=False,
        hata="",
        uyum=uyum,
        istemciGeriAlinmali=istemci_geri,
    )
    if not uygula or plan.eylem != su.FIRMWARE_GUNCELLE:
        logger.info("donanım güncellemesi: %s — %s", plan.eylem, gerekce)
        return durum()

    return _firmware_uygula(girdi, plan, banner_kaynagi)


def _firmware_uygula(girdi: dict, plan: su.Plan, banner_kaynagi=None) -> dict:
    yol, hata = firmware_indir(str(girdi.get("url", "")), str(girdi.get("sha256", "")))
    if yol is None:
        logger.warning("firmware indirilemedi: %s", hata)
        return _durum_yaz(uygulandi=False, hata=hata)

    from utils import firmware_yakma_penceresi as pencere
    from utils.stm_yakma import TAMAM, yakma_akisi

    # D1.108 + D1.111: ön kontrol SÜREÇ İÇİ — HTTP değil (bkz. `_surec_ici_guvenlik_kontrolu`).
    # D1.114 (B-4.6): port BIRAKILMAZ — yakma sonrası kimlik çekirdeğin KENDİ okuyucusundan (`banner_kaynagi`). Pencere ön
    # kontrolden ÖNCE açılır: içinde bobin başlatma reddedilir (HC kapısı durum kilidi altında — denetle-sonra-yap aralığı
    # kapanır), seans/AI Pro 409, ACİL DURDUR kapılanmaz ama teyidi dürüst (`utils.firmware_yakma_penceresi`).
    # D1.115 (B-4.10): yedek veri kökündeki KALICI `firmware_yedek`e (tutma sınırıyla); indirme dizini HER yolda silinir.
    yedek_kok = _yedek_dizini()
    try:
        with pencere.ac():
            sonuc = yakma_akisi(
                yol,
                beklenen_sha256=str(girdi.get("sha256", "")),
                guvenlik_kontrolu=_surec_ici_guvenlik_kontrolu,
                banner_kaynagi=banner_kaynagi,
                yedek_dizin=yedek_kok,
            )
    finally:
        _gecici_sil(yol)
    _yedekleri_buda(yedek_kok)
    for adim in sonuc.adimlar:
        logger.info("firmware: %s", adim)

    if sonuc.kod == TAMAM:
        # ⚠️ H-1.1 (1-H incelemesi): "uygulandı" ve `firmwareSurum` ÖLÇÜLENİ söyler — kartın yakmadan SONRA kendi bastığı
        # banner'ın sürümü. Eskiden planın HEDEF sürümü yazılıyordu: yakılan ikilinin banner'ı hedefi söylemese de (main.c'deki
        # sürüm dizesi artırılmadan yayınlanan ikili) durum "uygulandı, 2.4" diyordu ve sonraki her açılış AYNI ikiliyi
        # YENİDEN yakıyordu (ölçüldü — inceleme raporu, Kapsam 1).
        kart = _banner_surumu(sonuc.banner)
        if _ayni_surum(kart, plan.hedef_surum):
            logger.info("donanım güncellemesi TAMAM → %s (kart yakmadan sonra %s bildirdi)", plan.hedef_surum, kart)
            return _durum_yaz(uygulandi=True, hata="", firmwareSurum=kart)
        hata = (
            f"yakıldı ama kart hedef sürümü bildirmedi: kart {kart or '(sürüm ayrıştırılamadı)'}, hedef "
            f"{plan.hedef_surum} — yayınlanan ikilinin banner sürümü uyum varlığındaki sürümle UYUŞMUYOR (yayın hatası); "
            "sonraki açılışta yeniden denenir"
        )
        logger.error("donanım güncellemesi DOĞRULANAMADI: %s", hata)
        return _durum_yaz(uygulandi=False, hata=hata, firmwareSurum=kart)
    logger.warning("donanım güncellemesi BAŞARISIZ (kod %s): %s", sonuc.kod, sonuc.ozet)
    return _durum_yaz(uygulandi=False, hata=f"[{sonuc.kod}] {sonuc.ozet}")


def _banner_surumu(banner: str) -> str:
    """H-1.1: banner satırından karşılaştırılabilir firmware sürümü (D1.120 `firmware_surumu`); okunamazsa ""."""
    from utils import stm32_kimlik

    kimlik = stm32_kimlik.banner_ayristir(banner or "")
    return stm32_kimlik.firmware_surumu(kimlik.surum) if kimlik else ""


def _ayni_surum(a: str, b: str) -> bool:
    """`2.4` ≡ `2.4.0` (eksik parçalar 0). Biri ayrıştırılamazsa False — bilinmeyen sürüm "hedefe ulaşıldı" sayılmaz."""
    x, y = su.surum_demeti(a), su.surum_demeti(b)
    if x is None or y is None:
        return False
    n = max(len(x), len(y))
    return x + (0,) * (n - len(x)) == y + (0,) * (n - len(y))
