# -*- coding: utf-8 -*-
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
_UPDATE_REPO = "mert61-python/pemf-update"   # host-pin bu repoya daraltilir (bkz. _validate_installer_url)
_MANIFEST_URL = f"https://raw.githubusercontent.com/{_UPDATE_REPO}/exe/latest.json"

# K2 (defense-in-depth): OTA installer URL'sini HTTPS + bilinen GitHub-release host'larına pinle.
# Manifest ele geçse bile (repo/hesap) URL'yi keyfi bir sunucuya yönlendirip LocalSystem-EXE indirtme
# engellenir. NOT: Çekirdek koruma installer imza-pinleme / manifest-imzalama'dır (release-süreci +
# özel anahtar gerektirir → operatörle koordineli); bu katman URL-yönlendirme + path-traversal'i kapatır.
_ALLOWED_UPDATE_HOSTS = frozenset({
    "github.com",
    "codeload.github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
    "raw.githubusercontent.com",
})


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
    if host == "github.com" and not p.path.startswith(f"/{_UPDATE_REPO}/"):
        return False, (f"Güncelleme URL'si beklenen repo dışında ({p.path.split('/releases')[0]}) "
                       f"— indirilmedi (güvenlik).")
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
    NOT: dizin bilerek silinmez — installer surec olarak devam eder (ve servisi durdurabilir).
    """
    return Path(tempfile.mkdtemp(prefix="pemf_upd_")) / filename


def _safe_ver(v) -> str:
    """Sürüm etiketini dosya-adı-güvenli hale getir (path-traversal engelle)."""
    s = re.sub(r"[^0-9A-Za-z._-]", "", str(v))[:40]
    return s or "x"


_status: dict = {"checked": False, "available": False, "currentVersion": "", "latestVersion": "",
                 "notes": "", "installerUrl": "", "sha256": "", "mandatory": False, "error": ""}
_status_lock = threading.Lock()
_apply_lock = threading.Lock()
_applying = False
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

    _add("VERSION")                # exe/installer kanali (latest.json ile AYNI kanal)
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
            raise ValueError(
                f"manifest boyut tavanini asti (> {_MAX_MANIFEST_BYTES} bayt) — reddedildi"
            )
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
        res = {"checked": True, "available": False, "currentVersion": cur, "latestVersion": "",
               "notes": "", "installerUrl": "", "sha256": "", "mandatory": False,
               "previousStable": None, "error": "Güncelleme kontrolü başarısız"}
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
    return s


def is_update_in_progress() -> bool:
    """Güncelleme İNDİRİLİYOR/UYGULANIYOR mu (apply veya rollback). True ise tedavi/seans
    başlatma yolları YENİ seans AÇMAMALI: apply penceresinde (indirme + installer servisi
    durdurma + EXE değişimi) başlayan bir tedavi bobinleri kontrolcüsüz bırakabilir. Bu, TOCTOU
    guard'ının TERS yönüdür (apply, başlamış tedaviyi zaten _has_active_treatment ile reddeder)."""
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
            capture_output=True, text=True, timeout=20,
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
    global _applying
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
    url = st["installerUrl"]
    expected = (st.get("sha256") or "").lower()
    # DENETIM P2: asagidaki `finally` _applying'i installer BASLATILIR BASLATILMAZ False
    # yapiyordu. Oysa tehlikeli pencere tam o noktada BASLIYOR: installer servisi durduracak
    # ve EXE'yi degistirecek. Guard kapaninca /session/start ve /ai/pro/start yeniden serbest
    # kalip o pencerede TEDAVI baslatabiliyor → bobinler kontrolcusuz kalir. Installer basariyla
    # baslatildiysa guard ACIK KALMALI (surec zaten yeniden baslatilacak); yalnizca BASARISIZ
    # yollarda serbest birak.
    _installer_launched = False
    try:
        dest = _private_temp_path(f"PEMF_Update_{_safe_ver(st.get('latestVersion','x'))}.exe")
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
            return {"ok": False, "error": "Güncelleme manifest'inde SHA256 yok — doğrulanamayan installer ÇALIŞTIRILMADI (güvenlik)."}
        actual = _sha256(dest)
        if actual != expected:
            try:
                dest.unlink()
            except Exception:
                pass
            return {"ok": False, "error": f"SHA256 uyuşmadı (beklenen {expected[:12]}… geldi {actual[:12]}…) — güncelleme İPTAL."}
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
            return {"ok": False, "error": "İndirme sırasında tedavi başladı — güncelleme iptal edildi (seans bitince tekrar deneyin)."}
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
        return {"ok": True, "message": "Güncelleme indirildi + doğrulandı, kurulum başladı. Servis birazdan yeni sürümle yeniden başlar."}
    except Exception:
        logger.exception("apply_update hatası")
        return {"ok": False, "error": "Güncelleme uygulanamadı"}
    finally:
        if not _installer_launched:
            _applying = False   # basarisiz → normale don
        else:
            logger.info("Guncelleme guard'i ACIK birakildi: installer servisi durdurup EXE'yi "
                        "degistirene kadar YENI tedavi/seans baslatilamaz.")


def rollback() -> dict:
    """Önceki KARARLI sürüme GERİ DÖN (audit B-9.2): latest.json 'previousStable' installer'ını
    indir → SHA256 (ZORUNLU) + Authenticode doğrula → aktif tedavi yoksa sessiz kur. apply_update
    ile AYNI güvenlik zinciri, yön 'geri'. previousStable yoksa/manifest vermezse rollback yapılamaz.
    Kötü bir güncelleme sahada sorun çıkarırsa operatör tek-tıkla son iyi sürüme döner."""
    global _applying
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
        return {"ok": False, "error": "Geri dönülecek önceki kararlı sürüm tanımlı değil (manifest 'previousStable' yok)."}
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
    try:
        if not expected:
            return {"ok": False, "error": "previousStable SHA256 yok — doğrulanamayan installer ÇALIŞTIRILMADI (güvenlik)."}
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
            return {"ok": False, "error": "İndirme sırasında tedavi başladı — rollback iptal edildi (seans bitince tekrar deneyin)."}
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
            _applying = False   # basarisiz → normale don
        else:
            logger.info("Rollback guard'i ACIK birakildi: installer servisi durdurup EXE'yi "
                        "degistirene kadar YENI tedavi/seans baslatilamaz.")


def start_update_checker(interval_sec: int = 6 * 3600) -> None:
    """Arka plan: açılışta + her interval'da exe/latest.json kontrol (bildirim için). Uygulamaz — onay ister."""
    global _check_thread
    if _check_thread and _check_thread.is_alive():
        return
    _stop.clear()

    def _loop():
        _stop.wait(20)  # açılışta kısa bekle (ağ hazır olsun)
        while not _stop.is_set():
            try:
                r = check_for_update()
                if r.get("available"):
                    logger.info("Yeni backend sürümü mevcut: %s (kurulu %s)", r.get("latestVersion"), r.get("currentVersion"))
            except Exception:
                logger.exception("update checker döngü hatası")
            _stop.wait(interval_sec)

    _check_thread = threading.Thread(target=_loop, daemon=True, name="PemfUpdateChecker")
    _check_thread.start()
    logger.info("Güncelleme denetleyici başlatıldı (GitHub exe branch, %dsn).", interval_sec)
