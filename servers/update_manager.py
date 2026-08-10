# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""PEMF — GitHub Release tabanlı EXE oto-güncelleme (BİLDİRİM + TEK-TIK ONAY).

Akış: `pemf-update` repo'sunun **exe** branch'indeki `latest.json`'ı okur →
sürümü kurulu sürümle karşılaştırır → yeni varsa UI'ya bildirir. Operatör onaylayınca
(POST /api/update/apply) installer'ı indirir → SHA256 doğrular → AKTİF TEDAVİ YOKKEN
sessiz (`/VERYSILENT`) çalıştırır → installer servisi durdurur+değiştirir+yeniden başlatır.

Repo public → token GEREKMEZ.

Kurulu sürüm = `VERSION` (backend/installer kanalı — latest.json'ın YAYINLADIĞI kanal; spec
bundle'lar). Geriye uyum için `frontend_version.json`'a düşülür ama o AYRI bir kanaldır
(versions.json → `frontendOta`) ve exe sürümüyle kıyaslanmamalıdır — bkz. `_version_paths()`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

# exe branch manifest'i (mobil ayrı branch'te; karışmaz). raw.githubusercontent → API rate-limit yok.
_UPDATE_REPO = "mert61-python/pemf-update"  # host-pin bu repoya daraltilir (bkz. _validate_installer_url)
_MANIFEST_URL = f"https://raw.githubusercontent.com/{_UPDATE_REPO}/exe/latest.json"

# ═══════════════════════════════════════════════════════════════════════════════════════════
# ⚠️ BU KANAL VARSAYILAN OLARAK KAPALIDIR (2026-08-09 denetimi, Tier 3 — "tek güncelleme kanalı")
# ───────────────────────────────────────────────────────────────────────────────────────────
# Güncellemeyi artık LAUNCHER yönetir: katmanlı paketler (base-app/base-deps), atomik takas,
# sağlık kapılı geri alma, `rollout` ve `min_supported_version`. Bu modül ONDAN ÖNCEKİ
# Inno/`exe` kanalıdır ve iki nedenle açık kalmamalı:
#
#   1) ÖLÜ: `exe/latest.json` bugün 404 döner (ölçüldü 2026-08-10). Denetleyici 6 saatte bir
#      boşuna ağa çıkar, `previousStable` hiç dolmaz → `/api/update/rollback` HİÇBİR ZAMAN
#      çalışamaz. RUNBOOK'un "kötü güncelleme" satırı tam da bu ölü komutu gösteriyordu.
#   2) TEHLİKELİ: bir gün o dosya yeniden yayınlanırsa, Inno installer'ı LAUNCHER'IN yönettiği
#      kurulumun YANINA ikinci bir backend + ikinci bir veri kökü kurar. Sonuç SPLIT-BRAIN
#      HASTA VERİTABANI: seanslar iki ayrı DB'ye bölünür, ikisi de "eksiksiz" görünür.
#
# `is_update_in_progress()` bayrağı KAPALIYKEN DE doğru çalışır (hep False) — seans/AI Pro
# başlatmadaki TOCTOU korumaları bozulmaz.
#
# Geri açmak (yalnız launcher'sız bir kurulumda): PEMF_LEGACY_EXE_UPDATE=1
# ═══════════════════════════════════════════════════════════════════════════════════════════
_KANAL_KAPALI_MESAJ = (
    "Bu cihazın güncellemelerini PEMF Vet Client (launcher) yönetiyor. Eski EXE güncelleme "
    "kanalı kapalıdır — iki ayrı kurulum ve ikiye bölünmüş hasta veritabanı riski taşır."
)


def eski_kanal_acik_mi() -> bool:
    """Eski Inno/`exe` OTA kanalı etkin mi? Varsayılan HAYIR."""
    return os.environ.get("PEMF_LEGACY_EXE_UPDATE", "").strip() in ("1", "true", "True")


# K2 (defense-in-depth): OTA installer URL'sini HTTPS + bilinen GitHub-release host'larına pinle.
# Manifest ele geçse bile (repo/hesap) URL'yi keyfi bir sunucuya yönlendirip LocalSystem-EXE indirtme
# engellenir. NOT: Çekirdek koruma installer imza-pinleme / manifest-imzalama'dır (release-süreci +
# özel anahtar gerektirir → operatörle koordineli); bu katman URL-yönlendirme + path-traversal'i kapatır.
_ALLOWED_UPDATE_HOSTS = frozenset(
    {
        "github.com",
        "codeload.github.com",
        "objects.githubusercontent.com",
        "release-assets.githubusercontent.com",
        "raw.githubusercontent.com",
    }
)


def _path_has_traversal(path: str) -> bool:
    """Yol, sunucu-tarafı normalizasyonuyla BİZİM gördüğümüzden AYRIŞACAK bir yazım içeriyor mu?

    ⚠️ DENETİM 2026-08-04 (P0): repo-yolu pini `p.path.startswith(...)` ile HAM metin üzerinde
    çalışıyordu. `urlparse` nokta-segmentlerini SADELEŞTİRMEZ (ampirik olarak doğrulandı), ama
    HTTP sunucusu RFC 3986 gereği çözer. Yani:
        /mert61-python/pemf-update/../../saldirgan/kotu/setup.exe
    pinden GEÇER, GitHub ise `/saldirgan/kotu/setup.exe` sunar → zehirli manifest kendi
    deposundaki imzasız EXE'yi indirtir (sha da aynı manifest'ten gelir).
    Meşru release URL'lerinde bu yazımlar ASLA bulunmaz; varlıkları tek başına şüphelidir.
    Rust ikizi: launcher/core/src/net.rs::path_has_traversal — İKİSİ BİRLİKTE güncellenmeli.
    """
    path = (path or "").split("?")[0].split("#")[0]
    low = path.lower()
    # %2e='.'  %2f='/'  %5c='\'
    if "%2e" in low or "%2f" in low or "%5c" in low or "\\" in path:
        return True
    # Baştaki '/' yüzünden ilk parça daima boştur; onu atla.
    return any(seg in (".", "..", "") for seg in path.split("/")[1:])


def _validate_installer_url(url: str):
    """installerUrl'yi HTTPS + bilinen release host'una pinler. (ok: bool, hata: str) döner."""
    try:
        p = urllib.parse.urlparse(url or "")
    except Exception:
        return False, "Güncelleme URL'si çözümlenemedi (güvenlik)."
    if p.scheme != "https":
        return False, "Güncelleme URL'si HTTPS değil — indirilmedi (güvenlik)."
    host = (p.hostname or "").lower()
    if host not in _ALLOWED_UPDATE_HOSTS and not host.endswith(".githubusercontent.com"):
        return False, f"Güncelleme host'u beklenen release sunucusu değil ({host}) — indirilmedi (güvenlik)."
    # DENETIM P3: host-pin TUM github.com'u (yani HERHANGI bir kullanicinin repo/release'ini) ve
    # TUM *.githubusercontent.com alt alanlarini kabul ediyordu → "pin" pratikte yalnizca
    # "GitHub'da bir yer" demekti. Manifest ele gecerse saldirgan KENDI repo'sundaki bir EXE'yi
    # gosterebilirdi (SHA256 manifest'ten geldigi icin hash de eslesirdi). github.com yolunu
    # BEKLENEN REPO'ya sabitle. Nesne-depolama alan adlarinda (objects/release-assets) yol
    # opak oldugundan orada yol kontrolu yapilamaz — asil koruma yine SHA256 + Authenticode.
    if host == "github.com":
        # P0 (2026-08-04): önce pin-atlatma yazımlarını ele — bkz. _path_has_traversal.
        if _path_has_traversal(p.path):
            return False, (
                "Güncelleme URL'si nokta-segmenti/kodlanmış ayraç içeriyor "
                "(repo pini atlatma) — indirilmedi (güvenlik)."
            )
        if not p.path.startswith(f"/{_UPDATE_REPO}/"):
            return False, (
                f"Güncelleme URL'si beklenen repo dışında ({p.path.split('/releases')[0]}) — indirilmedi (güvenlik)."
            )
    return True, ""


# DENETIM P3: indirmelerde BOYUT SINIRI yoktu — ne Content-Length kontrolu ne toplam-bayt
# sayaci. Bozuk/ele gecmis bir manifest sonsuz (ya da devasa) bir govde gosterirse tibbi
# cihazin sistem diski dolar; disk dolunca SQLite yazimlari ve yedekleme de basarisiz olur
# (tedavi kaydi kaybi). Installer'lar ~100 MB mertebesinde → 512 MB genis ama sonlu bir tavan.
_MAX_INSTALLER_BYTES = 512 * 1024 * 1024
_MAX_MANIFEST_BYTES = 1 * 1024 * 1024


def _download_to(resp, dest_file, limit: int, what: str) -> int:
    """Yanit govdesini SINIRLI sekilde dosyaya yaz; tavan asilirsa hata firlat."""
    total = 0
    while True:
        chunk = resp.read(1 << 20)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise ValueError(f"{what} boyut siniri asildi ({limit} bayt) — indirme IPTAL.")
        dest_file.write(chunk)
    return total


def _private_temp_path(filename: str) -> Path:
    """Installer icin SURECE OZEL, tahmin EDILEMEZ bir gecici dizinde yol uret.

    DENETIM P1 (TOCTOU / yerel yetki yukseltme): installer PAYLASIMLI gecici dizine SABIT bir
    adla (PEMF_Update_<surum>.exe) indiriliyordu. Backend LocalSystem olarak kostugu icin bu
    C:\\Windows\\Temp'tir; yetkisiz bir yerel hesap dosyayi ONCEDEN olusturup sahipligini
    koruyabilir ve SHA256 + Authenticode dogrulamasi GECTIKTEN SONRA icerigi degistirerek
    LocalSystem'e keyfi EXE calistirtabilirdi (dogrulama ile calistirma arasindaki pencere).
    mkdtemp rastgele adli + yalniz olusturan hesaba acik ACL'li bir dizin verir → hem tahmin
    hem onceden-olusturma saldirisi kapanir. Cevredeki OTA sertlestirmesi (host-pin, ZORUNLU
    SHA256, Authenticode, aktif-tedavi yeniden-kontrolu) korunur.
    NOT: installer BASARIYLA BASLATILDIYSA dizin bilerek silinmez — installer surec olarak
    devam eder (ve servisi durdurabilir), dosyayi altindan cekemeyiz. Diger TUM yollarda
    (SHA uyusmadi / imza kurcalanmis / tedavi basladi / indirme hatasi) dizin
    `_discard_temp_dir` ile silinir; aksi halde her basarisiz guncelleme denemesi
    %TEMP%'e yetim bir `pemf_upd_*` dizini birakir.
    """
    return Path(tempfile.mkdtemp(prefix="pemf_upd_")) / filename


def _discard_temp_dir(dest) -> None:
    """`_private_temp_path`'in yarattigi ozel dizini komple sil (installer BASLATILMADIYSA)."""
    if dest is None:
        return
    try:
        parent = Path(dest).parent
        if parent.name.startswith("pemf_upd_"):
            shutil.rmtree(parent, ignore_errors=True)
    except Exception:
        logger.debug("gecici guncelleme dizini silinemedi", exc_info=True)


def sweep_stale_update_temp(max_age_s: float = 6 * 3600) -> int:
    """Eski `pemf_upd_*` dizinlerini topla (kendi kendini onaran temizlik).

    Gecmiste birakilmis yetimler (ve baska bir surecten kalanlar) burada temizlenir.
    Yalnizca YASI buyuk olanlara dokunur → su an indirme yapan baska bir surecin
    dizinini silmez. Guncelleme kontrol dongusunun basinda bir kez cagrilir.
    """
    silinen = 0
    try:
        kok = Path(tempfile.gettempdir())
        simdi = time.time()
        for d in kok.glob("pemf_upd_*"):
            try:
                if d.is_dir() and (simdi - d.stat().st_mtime) > max_age_s:
                    shutil.rmtree(d, ignore_errors=True)
                    if not d.exists():
                        silinen += 1
            except Exception:
                continue
    except Exception:
        logger.debug("gecici dizin suepuermesi basarisiz", exc_info=True)
    if silinen:
        logger.info("Eski guncelleme gecici dizini temizlendi: %d", silinen)
    return silinen


def _safe_ver(v) -> str:
    """Sürüm etiketini dosya-adı-güvenli hale getir (path-traversal engelle)."""
    s = re.sub(r"[^0-9A-Za-z._-]", "", str(v))[:40]
    return s or "x"


_status: dict = {
    "checked": False,
    "available": False,
    "currentVersion": "",
    "latestVersion": "",
    "notes": "",
    "installerUrl": "",
    "sha256": "",
    "mandatory": False,
    "error": "",
}
_status_lock = threading.Lock()
_apply_lock = threading.Lock()
_applying = False
# ⚠️ DENETİM 2026-08-04 (P2): `_applying` installer BAŞLATILDIKTAN sonra BİLEREK açık bırakılır
# (tehlikeli pencere orada başlar). Ama hiçbir yerde KAPANMIYORDU: installer kurulumu
# tamamlamazsa (Inno "another instance is running" ile exit, AV bloğu, kullanıcı iptali)
# backend KALICI olarak "güncelleme sürüyor" durumunda kilitleniyor ve `is_update_in_progress()`
# üzerinden /session/start ile /ai/pro/start SONSUZA KADAR reddediliyordu — tıbbi cihaz hiç
# tedavi başlatamaz hale gelir ve tek çözüm servisi elle yeniden başlatmaktır.
# Çözüm: bayrağa son-kullanma ver. BAŞARILI kurulum zaten backend'i yeniden başlatır (bayrak
# doğal olarak sıfırlanır); yalnızca BAŞARISIZ kurulumun bıraktığı bayat bayrak süresi dolar.
_applying_since: float | None = None
# Inno /VERYSILENT kurulumu ~1-2 dk sürer; 5 dk cömert ama sonsuz değil.
_APPLYING_GRACE_S = 300.0
_check_thread: threading.Thread | None = None
_stop = threading.Event()


def _version_paths():
    """Kurulu BACKEND surumunun arandigi yollar (SIRA ONEMLI).

    DENETIM 2026-08-04 (P2): burada YALNIZ `frontend_version.json` araniyordu. O dosya
    versions.json'daki `frontendOta` KANALINI tasir (1.4.x); oysa `check_for_update` sonucu
    exe kanalinin `latest.json`'iyla (backend/installer surumu, 1.9.x) KARSILASTIRILIYOR.
    Iki AYRI yayin kanali ayni isim uzayinda kiyaslaniyordu → yayindaki base.zip kendini
    "1.4.0" saniyordu; guncelleme karari anlamsiz bir kiyasa dayaniyordu.
    Once `VERSION` (exe/installer kanali = DOGRU kaynak) aranir; bulunamazsa VERSION'i bundle
    ETMEYEN eski build'ler icin eski davranisa dusulur (geriye uyum).
    """
    roots = []

    def _add(name: str):
        if getattr(sys, "frozen", False):
            mp = getattr(sys, "_MEIPASS", "")
            if mp:
                roots.append(Path(mp) / name)
            exe_dir = Path(sys.executable).resolve().parent
            roots.append(exe_dir / name)
            roots.append(exe_dir / "_internal" / name)
        roots.append(Path(__file__).resolve().parent.parent / name)

    _add("VERSION")  # exe/installer kanali (latest.json ile AYNI kanal)
    _add("frontend_version.json")  # geriye uyum: VERSION'i bundle etmeyen eski build'ler
    return roots


def _read_version_file(p: Path) -> str:
    """`VERSION` duz-metin, `frontend_version.json` ise {"version": "..."} tasir — ikisini de oku."""
    txt = p.read_text(encoding="utf-8").strip()
    if not txt:
        return ""
    if p.suffix.lower() == ".json" or txt.lstrip().startswith("{"):
        return str(json.loads(txt).get("version", "")).strip()
    return txt.splitlines()[0].strip()


def get_current_version() -> str:
    for p in _version_paths():
        try:
            if p.exists():
                v = _read_version_file(p)
                if v:
                    return v
        except Exception:
            pass
    return "0.0.0"


def _vtuple(v: str):
    """'1.8.1' / 'v1.8.1-safety' → (1,8,1): her parcanin sayisal on-ekini cikar (Audit P2: eskiden
    '1-safety' int() ValueError → (0,0,0) → etiketli zorunlu guvenlik guncellemesi asla onerilmezdi).
    Hicbir sayisal parca yoksa None → 'bilinmiyor' (guncelleme ONERILMEZ; sonsuz-reinstall onle)."""
    import re

    parts = str(v).strip().lstrip("vV").split(".")
    nums = []
    for p in parts[:3]:
        m = re.match(r"\d+", p.strip())
        if not m:
            break
        nums.append(int(m.group()))
    return tuple(nums) if nums else None


def _is_newer(latest: str, current: str) -> bool:
    lv, cv = _vtuple(latest), _vtuple(current)
    if lv is None or cv is None:
        # Ayristirilamayan surum → guncelleme ONERME (yanlis-pozitif/sonsuz-reinstall onle).
        logger.warning("Surum ayristirilamadi (latest=%r current=%r) → guncelleme onerilmiyor.", latest, current)
        return False
    n = max(len(lv), len(cv))
    lv = lv + (0,) * (n - len(lv))
    cv = cv + (0,) * (n - len(cv))
    return lv > cv


def check_for_update(timeout: float = 15.0) -> dict:
    """exe/latest.json'ı çek + kurulu sürümle karşılaştır. Sonucu cache'ler (get_status okur)."""
    cur = get_current_version()
    try:
        req = urllib.request.Request(
            _MANIFEST_URL + "?t=" + str(int(time.time())),  # cache-bust
            headers={"User-Agent": "pemf-updater", "Cache-Control": "no-cache"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            # DENETIM 2026-08-04: `_MAX_MANIFEST_BYTES` TANIMLI ama HIC UYGULANMIYORDU —
            # `r.read()` govdeyi SINIRSIZ bellege aliyordu. Installer indirmeleri `_download_to`
            # ile 512 MB'a sinirliyken manifest yolu korumasizdi: bozuk/ele gecmis bir sunucu
            # devasa bir govde donerse tibbi cihazin RAM'i tukenir. Tavan+1 oku, asimi YAKALA.
            raw = r.read(_MAX_MANIFEST_BYTES + 1)
        if len(raw) > _MAX_MANIFEST_BYTES:
            raise ValueError(f"manifest boyut tavanini asti (> {_MAX_MANIFEST_BYTES} bayt) — reddedildi")
        m = json.loads(raw.decode("utf-8"))
        latest = str(m.get("version", "")).strip()
        res = {
            "checked": True,
            "available": bool(latest) and _is_newer(latest, cur),
            "currentVersion": cur,
            "latestVersion": latest,
            "notes": str(m.get("notes", "")),
            "installerUrl": str(m.get("installerUrl", "")),
            "sha256": str(m.get("sha256", "")).lower(),
            "mandatory": bool(m.get("mandatory", False)),
            # audit B-9.2: rollback hedefi — {version, installerUrl, sha256} (publish_release.ps1 doldurur).
            "previousStable": (m.get("previousStable") or None),
            "error": "",
        }
    except Exception as e:
        logger.warning("Güncelleme kontrolü hatası: %s", e)
        res = {
            "checked": True,
            "available": False,
            "currentVersion": cur,
            "latestVersion": "",
            "notes": "",
            "installerUrl": "",
            "sha256": "",
            "mandatory": False,
            "previousStable": None,
            "error": "Güncelleme kontrolü başarısız",
        }
    with _status_lock:
        _status.clear()
        _status.update(res)
    return res


def get_status() -> dict:
    with _status_lock:
        s = dict(_status)
    s["applying"] = _applying
    if not s.get("currentVersion"):
        # ilk kontrol öncesi (checker henüz çalışmadı) bile kurulu sürümü ver — setdefault
        # mevcut boş "" değeri ezmediğinden DOĞRUDAN ata.
        s["currentVersion"] = get_current_version()
    if not eski_kanal_acik_mi():
        # Kanal kapalı → "güncelleme yok" DEĞİL, "bu kanal artık yönetmiyor" de. Sözleşme
        # korunur (`available`/`currentVersion` alanları aynı tipte) ki eski mobil istemciler
        # kırılmasın; `channel` alanı yeni istemcilere gerçeği söyler. `error` BOŞ bırakılır:
        # kapalı bir kanal arıza değildir, arıza gibi göstermek yanlış teşhise yol açar.
        s.update(
            {
                "checked": True,
                "available": False,
                "latestVersion": "",
                "notes": "",
                "installerUrl": "",
                "sha256": "",
                "mandatory": False,
                "previousStable": None,
                "error": "",
                "channel": "launcher",
                "legacyChannelEnabled": False,
                "message": _KANAL_KAPALI_MESAJ,
            }
        )
    else:
        s["channel"] = "legacy-exe"
        s["legacyChannelEnabled"] = True
    return s


def is_update_in_progress() -> bool:
    """Güncelleme İNDİRİLİYOR/UYGULANIYOR mu (apply veya rollback). True ise tedavi/seans
    başlatma yolları YENİ seans AÇMAMALI: apply penceresinde (indirme + installer servisi
    durdurma + EXE değişimi) başlayan bir tedavi bobinleri kontrolcüsüz bırakabilir. Bu, TOCTOU
    guard'ının TERS yönüdür (apply, başlamış tedaviyi zaten _has_active_treatment ile reddeder).

    DENETİM 2026-08-04 (P2): bayrak installer başlatıldıktan sonra hiç kapanmıyordu → kurulum
    tamamlanmazsa cihaz KALICI olarak seans açamaz hale geliyordu. Bayat bayrak burada süresi
    dolunca temizlenir (bkz. _APPLYING_GRACE_S)."""
    global _applying, _applying_since
    if not _applying:
        return False
    if _applying_since is not None and (time.monotonic() - _applying_since) > _APPLYING_GRACE_S:
        with _apply_lock:
            # Kilit altında yeniden doğrula (başka bir apply araya girmiş olabilir).
            if _applying_since is not None and (time.monotonic() - _applying_since) > _APPLYING_GRACE_S:
                logger.warning(
                    "Guncelleme guard'i %.0f sn'dir acik ve kurulum tamamlanmadi — bayat bayrak "
                    "temizlendi (seans acma yeniden serbest).",
                    time.monotonic() - _applying_since,
                )
                _applying = False
                _applying_since = None
        return _applying
    return _applying


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _has_active_treatment() -> bool:
    """Aktif tedavi/koşan bobin varsa güncelleme UYGULANMAZ (medikal güvenlik).

    FAIL-CLOSED: durum BELİRLENEMEZSE (snapshot fonksiyonu yok / istisna) 'aktif tedavi VAR'
    kabul edilir → güncelleme REDDEDİLİR. Tedavi sürerken installer'ın servisi durdurup EXE'yi
    değiştirmesi bobinleri kontrolcüsüz bırakabilir; belirsizlikte asla güncelleme."""
    try:
        from servers import api_server as _api

        if not hasattr(_api, "_build_ws_snapshot"):
            logger.warning("_build_ws_snapshot yok → aktif-tedavi belirlenemedi, fail-closed (güncelleme reddedildi).")
            return True
        snap = _api._build_ws_snapshot() or {}
        at = snap.get("activeTreatment") or {}
        if at.get("isActive"):
            return True
        for c in snap.get("coils", []) or []:
            if c.get("running"):
                return True
        return False
    except Exception:
        logger.exception("Aktif-tedavi kontrolü başarısız → fail-closed (güncelleme reddedildi).")
        return True


def _verify_authenticode(path: Path) -> str:
    """Windows Authenticode imza durumu: 'valid' | 'unsigned' | 'tampered' | 'unknown'.

    SHA256 birincil bütünlük kapısıdır (apply_update'te ZORUNLU). Bu EK savunma yalnız açıkça
    KURCALANMIŞ/güvenilmez imzayı (HashMismatch / NotTrusted) reddeder; imzasız installer'ı
    (backward-compat, Inno Setup imzasız üretilebilir) SHA doğrulandığı için geçirir.
    Kontrol hatası → 'unknown' (SHA zaten korur, güncellemeyi bloklamayız)."""
    if os.name != "nt":
        return "unknown"
    try:
        ps = "$s=(Get-AuthenticodeSignature -LiteralPath '%s').Status; Write-Output $s" % str(path).replace("'", "''")
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=20,
        )
        status = (out.stdout or "").strip()
        if status == "Valid":
            return "valid"
        if status in ("HashMismatch", "NotTrusted"):
            logger.error("Installer imzası KURCALANMIŞ/güvenilmez: %s → güncelleme reddedilecek.", status)
            return "tampered"
        logger.warning("Installer imza durumu '%s' (SHA256 doğrulandı, kuruluyor).", status or "bilinmiyor")
        return "unsigned"
    except Exception:
        logger.exception("Authenticode doğrulama başarısız (SHA256 birincil kapı, devam).")
        return "unknown"


def apply_update() -> dict:
    """Operatör onayıyla: installer'ı indir → SHA256 doğrula → aktif tedavi yoksa sessiz kur."""
    global _applying, _applying_since
    if not eski_kanal_acik_mi():
        return {"ok": False, "error": _KANAL_KAPALI_MESAJ}
    st = get_status()
    if not st.get("available") or not st.get("installerUrl"):
        return {"ok": False, "error": "Uygulanacak güncelleme yok."}
    if _has_active_treatment():
        return {"ok": False, "error": "Aktif tedavi sürüyor — güncelleme seans bitince yapılabilir."}
    # K2 (defense-in-depth): installerUrl'yi indirmeden ÖNCE HTTPS + release-host'a pinle (kilit almadan).
    _ok_url, _url_err = _validate_installer_url(st.get("installerUrl", ""))
    if not _ok_url:
        return {"ok": False, "error": _url_err}
    with _apply_lock:
        if _applying:
            return {"ok": False, "error": "Güncelleme zaten sürüyor."}
        _applying = True
        _applying_since = time.monotonic()
    url = st["installerUrl"]
    expected = (st.get("sha256") or "").lower()
    # DENETIM P2: asagidaki `finally` _applying'i installer BASLATILIR BASLATILMAZ False
    # yapiyordu. Oysa tehlikeli pencere tam o noktada BASLIYOR: installer servisi durduracak
    # ve EXE'yi degistirecek. Guard kapaninca /session/start ve /ai/pro/start yeniden serbest
    # kalip o pencerede TEDAVI baslatabiliyor → bobinler kontrolcusuz kalir. Installer basariyla
    # baslatildiysa guard ACIK KALMALI (surec zaten yeniden baslatilacak); yalnizca BASARISIZ
    # yollarda serbest birak.
    _installer_launched = False
    dest = None
    try:
        dest = _private_temp_path(f"PEMF_Update_{_safe_ver(st.get('latestVersion', 'x'))}.exe")
        req = urllib.request.Request(url, headers={"User-Agent": "pemf-updater"})
        with urllib.request.urlopen(req, timeout=180) as r, open(dest, "wb") as f:
            _download_to(r, f, _MAX_INSTALLER_BYTES, "Installer")
        # GÜVENLİK (P0): SHA256 ZORUNLU. Manifest hash vermezse indirilen installer'ı ÇALIŞTIRMA.
        # Aksi halde manifest'i değiştirebilen (repo/hesap ele geçirme, TLS-pinsiz MITM) biri
        # keyfi bir EXE'yi LocalSystem yetkisiyle sessiz kurdurabilir (RCE). Hash boşsa İPTAL.
        if not expected:
            try:
                dest.unlink()
            except Exception:
                pass
            return {
                "ok": False,
                "error": "Güncelleme manifest'inde SHA256 yok — doğrulanamayan installer ÇALIŞTIRILMADI (güvenlik).",
            }
        actual = _sha256(dest)
        if actual != expected:
            try:
                dest.unlink()
            except Exception:
                pass
            return {
                "ok": False,
                "error": f"SHA256 uyuşmadı (beklenen {expected[:12]}… geldi {actual[:12]}…) — güncelleme İPTAL.",
            }
        # EK savunma: Authenticode imzası açıkça kurcalanmışsa reddet (imzasız = SHA ile geçer).
        if _verify_authenticode(dest) == "tampered":
            try:
                dest.unlink()
            except Exception:
                pass
            return {"ok": False, "error": "Installer imzası GEÇERSİZ/kurcalanmış (Authenticode) — güncelleme İPTAL."}
        # TOCTOU (Audit P1): indirme+imza penceresi ~200sn — bu sürede tedavi BAŞLAMIŞ olabilir.
        # Installer'ı ÇALIŞTIRMADAN hemen önce tekrar kontrol et; aktifse kur BAŞLATMA (servis-restart
        # bobinleri kontrolcüsüz bırakır → ESP son komutu sürdürür → aşırı-doz/yanık riski).
        if _has_active_treatment():
            try:
                dest.unlink()
            except Exception:
                pass
            return {
                "ok": False,
                "error": "İndirme sırasında tedavi başladı — güncelleme iptal edildi (seans bitince tekrar deneyin).",
            }
        # Detached: installer servisi (bu süreci) durdursa da hayatta kalır → değiştir → yeniden başlat.
        flags = 0
        if os.name == "nt":
            flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(
            [str(dest), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/NOCANCEL"],
            creationflags=flags,
            close_fds=True,
        )
        _installer_launched = True
        logger.info("Güncelleme kurulumu başlatıldı: %s", dest)
        return {
            "ok": True,
            "message": "Güncelleme indirildi + doğrulandı, kurulum başladı. Servis birazdan yeni sürümle yeniden başlar.",
        }
    except Exception:
        logger.exception("apply_update hatası")
        return {"ok": False, "error": "Güncelleme uygulanamadı"}
    finally:
        if not _installer_launched:
            _applying = False  # basarisiz → normale don
            # Ozel gecici dizin YALNIZ installer basladiysa yasamali; aksi halde her
            # basarisiz deneme %TEMP%'e yetim bir `pemf_upd_*` dizini birakirdi.
            _discard_temp_dir(dest)
            _applying_since = None
        else:
            logger.info(
                "Guncelleme guard'i ACIK birakildi: installer servisi durdurup EXE'yi "
                "degistirene kadar YENI tedavi/seans baslatilamaz."
            )


def rollback() -> dict:
    """Önceki KARARLI sürüme GERİ DÖN (audit B-9.2): latest.json 'previousStable' installer'ını
    indir → SHA256 (ZORUNLU) + Authenticode doğrula → aktif tedavi yoksa sessiz kur. apply_update
    ile AYNI güvenlik zinciri, yön 'geri'. previousStable yoksa/manifest vermezse rollback yapılamaz.
    Kötü bir güncelleme sahada sorun çıkarırsa operatör tek-tıkla son iyi sürüme döner."""
    global _applying, _applying_since
    if not eski_kanal_acik_mi():
        return {"ok": False, "error": _KANAL_KAPALI_MESAJ}
    st = get_status()
    # Audit P3: previousStable dict DEĞİLSE (bozuk manifest: string/liste) `or {}` truthy-non-dict'i
    # geçirir → prev.get() AttributeError → try'dan önce olduğu için generic 500 (operatör dönemez).
    prev = st.get("previousStable")
    if not isinstance(prev, dict):
        prev = {}
    url = str(prev.get("installerUrl") or "")
    expected = str(prev.get("sha256") or "").lower()
    ver = str(prev.get("version") or "prev")
    if not url:
        return {
            "ok": False,
            "error": "Geri dönülecek önceki kararlı sürüm tanımlı değil (manifest 'previousStable' yok).",
        }
    # Öncelik: aktif-tedavi güvenlik-guard'ı URL-doğrulamasından ÖNCE (apply_update ile tutarlı).
    if _has_active_treatment():
        return {"ok": False, "error": "Aktif tedavi sürüyor — rollback seans bitince yapılabilir."}
    _ok_url, _url_err = _validate_installer_url(url)
    if not _ok_url:
        return {"ok": False, "error": _url_err}
    with _apply_lock:
        if _applying:
            return {"ok": False, "error": "Bir güncelleme/rollback zaten sürüyor."}
        _applying = True
    # DENETIM 2026-08-04 (P2): asagidaki `finally` _applying'i KOSULSUZ False yapiyordu — oysa
    # apply_update ayni zincirde (satir ~310) bunu bilerek ACIK BIRAKIYOR. Tehlikeli pencere
    # installer BASLATILDIKTAN sonra baslar: installer servisi durdurup EXE'yi degistirecektir.
    # Guard erken kapaninca /session/start ve /ai/pro/start yeniden serbest kalir ve tam o
    # pencerede TEDAVI baslatilabilir → bobinler kontrolcusuz kalir. apply_update ile AYNI desen:
    # yalnizca BASARISIZ yollarda serbest birak.
    _installer_launched = False
    dest = None
    try:
        if not expected:
            return {
                "ok": False,
                "error": "previousStable SHA256 yok — doğrulanamayan installer ÇALIŞTIRILMADI (güvenlik).",
            }
        dest = _private_temp_path(f"PEMF_Rollback_{_safe_ver(ver)}.exe")
        req = urllib.request.Request(url, headers={"User-Agent": "pemf-updater"})
        with urllib.request.urlopen(req, timeout=180) as r, open(dest, "wb") as f:
            _download_to(r, f, _MAX_INSTALLER_BYTES, "Installer")
        actual = _sha256(dest)
        if actual != expected:
            try:
                dest.unlink()
            except Exception:
                pass
            return {"ok": False, "error": f"SHA256 uyuşmadı (rollback İPTAL): beklenen {expected[:12]}…"}
        if _verify_authenticode(dest) == "tampered":
            try:
                dest.unlink()
            except Exception:
                pass
            return {"ok": False, "error": "Rollback installer imzası GEÇERSİZ/kurcalanmış — İPTAL."}
        # TOCTOU (Audit P1): apply_update ile aynı — Popen'dan hemen önce tedavi re-check.
        if _has_active_treatment():
            try:
                dest.unlink()
            except Exception:
                pass
            return {
                "ok": False,
                "error": "İndirme sırasında tedavi başladı — rollback iptal edildi (seans bitince tekrar deneyin).",
            }
        flags = 0
        if os.name == "nt":
            flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(
            [str(dest), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/NOCANCEL"],
            creationflags=flags,
            close_fds=True,
        )
        _installer_launched = True
        logger.warning("ROLLBACK kurulumu başlatıldı → önceki kararlı sürüm %s (%s)", ver, dest)
        return {"ok": True, "message": f"Önceki kararlı sürüme ({ver}) dönülüyor. Servis birazdan yeniden başlar."}
    except Exception:
        logger.exception("rollback hatası")
        return {"ok": False, "error": "Geri alma başarısız"}
    finally:
        if not _installer_launched:
            _applying = False  # basarisiz → normale don
            _discard_temp_dir(dest)  # apply_update ile AYNI desen (yetim dizin birakma)
            _applying_since = None
        else:
            logger.info(
                "Rollback guard'i ACIK birakildi: installer servisi durdurup EXE'yi "
                "degistirene kadar YENI tedavi/seans baslatilamaz."
            )


def start_update_checker(interval_sec: int = 6 * 3600) -> None:
    """Arka plan: açılışta + her interval'da exe/latest.json kontrol (bildirim için). Uygulamaz — onay ister."""
    global _check_thread
    if not eski_kanal_acik_mi():
        logger.info(
            "Eski EXE guncelleme kanali KAPALI (guncellemeleri launcher yonetir); "
            "denetleyici baslatilmadi. Acmak icin PEMF_LEGACY_EXE_UPDATE=1."
        )
        return
    if _check_thread and _check_thread.is_alive():
        return
    _stop.clear()

    def _loop():
        _stop.wait(20)  # açılışta kısa bekle (ağ hazır olsun)
        # Kendi kendini onarma: gecmiste birakilmis yetim `pemf_upd_*` dizinlerini bir kez topla
        # (bu duzeltmeden ONCEKI surumlerin ve cokmus deneme kalintilarinin izini siler).
        try:
            sweep_stale_update_temp()
        except Exception:
            logger.debug("acilis gecici-dizin suepuermesi hatasi", exc_info=True)
        while not _stop.is_set():
            try:
                r = check_for_update()
                if r.get("available"):
                    logger.info(
                        "Yeni backend sürümü mevcut: %s (kurulu %s)", r.get("latestVersion"), r.get("currentVersion")
                    )
            except Exception:
                logger.exception("update checker döngü hatası")
            _stop.wait(interval_sec)

    _check_thread = threading.Thread(target=_loop, daemon=True, name="PemfUpdateChecker")
    _check_thread.start()
    logger.info("Güncelleme denetleyici başlatıldı (GitHub exe branch, %dsn).", interval_sec)
