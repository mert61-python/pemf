# -*- coding: utf-8 -*-
"""PEMF — GitHub Release tabanlı EXE oto-güncelleme (BİLDİRİM + TEK-TIK ONAY).

Akış: `pemf-update` repo'sunun **exe** branch'indeki `latest.json`'ı okur →
sürümü kurulu sürümle karşılaştırır → yeni varsa UI'ya bildirir. Operatör onaylayınca
(POST /api/update/apply) installer'ı indirir → SHA256 doğrular → AKTİF TEDAVİ YOKKEN
sessiz (`/VERYSILENT`) çalıştırır → installer servisi durdurur+değiştirir+yeniden başlatır.

Repo public → token GEREKMEZ. Kurulu sürüm = frontend_version.json (build sürümü, spec bundle'lar).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

# exe branch manifest'i (mobil ayrı branch'te; karışmaz). raw.githubusercontent → API rate-limit yok.
_MANIFEST_URL = "https://raw.githubusercontent.com/mert61-python/pemf-update/exe/latest.json"

_status: dict = {"checked": False, "available": False, "currentVersion": "", "latestVersion": "",
                 "notes": "", "installerUrl": "", "sha256": "", "mandatory": False, "error": ""}
_status_lock = threading.Lock()
_apply_lock = threading.Lock()
_applying = False
_check_thread: threading.Thread | None = None
_stop = threading.Event()


def _version_paths():
    roots = []
    if getattr(sys, "frozen", False):
        mp = getattr(sys, "_MEIPASS", "")
        if mp:
            roots.append(Path(mp) / "frontend_version.json")
        exe_dir = Path(sys.executable).resolve().parent
        roots.append(exe_dir / "frontend_version.json")
        roots.append(exe_dir / "_internal" / "frontend_version.json")
    roots.append(Path(__file__).resolve().parent.parent / "frontend_version.json")
    return roots


def get_current_version() -> str:
    for p in _version_paths():
        try:
            if p.exists():
                v = str(json.loads(p.read_text(encoding="utf-8")).get("version", "")).strip()
                if v:
                    return v
        except Exception:
            pass
    return "0.0.0"


def _vtuple(v: str):
    try:
        return tuple(int(x) for x in str(v).strip().lstrip("vV").split(".")[:3])
    except Exception:
        return (0, 0, 0)


def _is_newer(latest: str, current: str) -> bool:
    return _vtuple(latest) > _vtuple(current)


def check_for_update(timeout: float = 15.0) -> dict:
    """exe/latest.json'ı çek + kurulu sürümle karşılaştır. Sonucu cache'ler (get_status okur)."""
    cur = get_current_version()
    try:
        req = urllib.request.Request(
            _MANIFEST_URL + "?t=" + str(int(time.time())),  # cache-bust
            headers={"User-Agent": "pemf-updater", "Cache-Control": "no-cache"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            m = json.loads(r.read().decode("utf-8"))
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
            "error": "",
        }
    except Exception as e:
        res = {"checked": True, "available": False, "currentVersion": cur, "latestVersion": "",
               "notes": "", "installerUrl": "", "sha256": "", "mandatory": False, "error": str(e)}
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


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _has_active_treatment() -> bool:
    """Aktif tedavi/koşan bobin varsa güncelleme UYGULANMAZ (medikal güvenlik)."""
    try:
        from servers import api_server as _api
        snap = _api._build_ws_snapshot() if hasattr(_api, "_build_ws_snapshot") else {}
        at = (snap or {}).get("activeTreatment") or {}
        if at.get("isActive"):
            return True
        for c in (snap or {}).get("coils", []) or []:
            if c.get("running"):
                return True
    except Exception:
        pass
    return False


def apply_update() -> dict:
    """Operatör onayıyla: installer'ı indir → SHA256 doğrula → aktif tedavi yoksa sessiz kur."""
    global _applying
    st = get_status()
    if not st.get("available") or not st.get("installerUrl"):
        return {"ok": False, "error": "Uygulanacak güncelleme yok."}
    if _has_active_treatment():
        return {"ok": False, "error": "Aktif tedavi sürüyor — güncelleme seans bitince yapılabilir."}
    with _apply_lock:
        if _applying:
            return {"ok": False, "error": "Güncelleme zaten sürüyor."}
        _applying = True
    url = st["installerUrl"]
    expected = (st.get("sha256") or "").lower()
    try:
        dest = Path(tempfile.gettempdir()) / f"PEMF_Update_{st.get('latestVersion','x')}.exe"
        req = urllib.request.Request(url, headers={"User-Agent": "pemf-updater"})
        with urllib.request.urlopen(req, timeout=180) as r, open(dest, "wb") as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
        if expected:
            actual = _sha256(dest)
            if actual != expected:
                try:
                    dest.unlink()
                except Exception:
                    pass
                return {"ok": False, "error": f"SHA256 uyuşmadı (beklenen {expected[:12]}… geldi {actual[:12]}…) — güncelleme İPTAL."}
        # Detached: installer servisi (bu süreci) durdursa da hayatta kalır → değiştir → yeniden başlat.
        flags = 0
        if os.name == "nt":
            flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(
            [str(dest), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/NOCANCEL"],
            creationflags=flags,
            close_fds=True,
        )
        logger.info("Güncelleme kurulumu başlatıldı: %s", dest)
        return {"ok": True, "message": "Güncelleme indirildi + doğrulandı, kurulum başladı. Servis birazdan yeni sürümle yeniden başlar."}
    except Exception as e:
        logger.exception("apply_update hatası")
        return {"ok": False, "error": str(e)}
    finally:
        _applying = False


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


def stop_update_checker() -> None:
    _stop.set()
