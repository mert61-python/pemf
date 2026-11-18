# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""GA (istem 53) B5 — SÜRÜCÜ DENETLEYİCİSİ (AST, statik): `moduller/<kimlik>/surucu.py` PLAN §2 B kurallarına uyuyor mu.

Kurallar (geçmeyen modül birleştirilmez; geliştiricinin CI'ı da aynı denetimi koşar):
  - AĞ yalnız BEYAN EDİLEN bağlantı için: seri → `serial` · wifi → `socket` (+ MQTT: `paho`, YALNIZ `pemf/modul/<kimlik>/…` konuları,
    kalıcı ileti YOK) · ble → `bleak` · usb → `usb` / `hid` · sahte → `multiprocessing.connection` (yerel boru). Başka ağ / HTTP / keşif
    (`zeroconf`, mDNS) modülü YASAK.
  - ALT SÜREÇ yok: `subprocess`, `multiprocessing` (sahte bağlantının `connection`ı dışında), `os.system / popen / spawn* / exec* / fork`.
  - DİSKE yazma yalnız modül klasörüne: yazma kipinde `open(...)` yalnız `self.dosya_yolu(...)` ile; `os` / `shutil` / `pathlib` dosya
    değiştiren çağrıları YASAK.
  - Denetimi aşan dinamik kod YOK: `exec`, `eval`, `compile`, `__import__`, `importlib`, `ctypes`.
  - `class Surucu(BobinSurucusu)` tanımlı olmalı.
Bulgu: `(satır, kod, ayrıntı)`; boş liste = geçti.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

#: bağlantı türü → izinli ağ / donanım modülleri (kök ad)
BAGLANTI_IZNI = {
    "seri": {"serial"},
    "wifi": {"socket", "paho"},
    "ble": {"bleak"},
    "usb": {"usb", "hid"},
    "sahte": {"multiprocessing.connection"},
}
#: hiçbir bağlantıda izin YOK
HER_ZAMAN_YASAK = {
    "subprocess",
    "ctypes",
    "shutil",
    "importlib",
    "zeroconf",
    "http",
    "urllib",
    "requests",
    "httpx",
    "aiohttp",
    "websocket",
    "websockets",
    "ftplib",
    "smtplib",
    "telnetlib",
    "ssl",
    "asyncio",
}
AG_MODULLERI = {"socket", "paho", "serial", "bleak", "usb", "hid", "multiprocessing"}
YASAK_CAGRILAR = {"exec", "eval", "compile", "__import__"}
OS_YASAK = {
    "system",
    "popen",
    "fork",
    "forkpty",
    "remove",
    "unlink",
    "rename",
    "replace",
    "rmdir",
    "removedirs",
    "makedirs",
    "mkdir",
    "chmod",
    "chown",
    "truncate",
    "symlink",
    "link",
    "startfile",
    "kill",
}
YOL_YASAK = {
    "write_text",
    "write_bytes",
    "unlink",
    "rename",
    "replace",
    "mkdir",
    "rmdir",
    "touch",
    "chmod",
    "symlink_to",
    "hardlink_to",
}


def _kok(ad: str) -> str:
    return ad.split(".", 1)[0]


def _ice_aktarma_izinli(ad: str, izinli: set[str]) -> bool:
    return ad in izinli or _kok(ad) in izinli or any(ad.startswith(i + ".") for i in izinli)


def _dosya_yolu_cagrisi(dugum) -> bool:
    return (
        isinstance(dugum, ast.Call)
        and isinstance(dugum.func, ast.Attribute)
        and dugum.func.attr == "dosya_yolu"
        and isinstance(dugum.func.value, ast.Name)
        and dugum.func.value.id == "self"
    )


def _yazma_kipi(cagri: ast.Call) -> bool:
    kip = None
    if len(cagri.args) >= 2 and isinstance(cagri.args[1], ast.Constant):
        kip = cagri.args[1].value
    for k in cagri.keywords:
        if k.arg == "mode" and isinstance(k.value, ast.Constant):
            kip = k.value.value
    if len(cagri.args) >= 2 and not isinstance(cagri.args[1], ast.Constant):
        return True  # kip çalışma anında belirleniyor → yazma say
    return isinstance(kip, str) and any(c in kip for c in "wax+")


def denetle_kaynak(kaynak: str, modul: dict) -> list[tuple[int, str, str]]:
    bulgu: list[tuple[int, str, str]] = []
    baglanti = modul.get("baglanti")
    kimlik = str(modul.get("kimlik", ""))
    izinli = BAGLANTI_IZNI.get(baglanti, set())
    try:
        agac = ast.parse(kaynak)
    except SyntaxError as e:
        return [(e.lineno or 0, "sozdizimi", str(e.msg))]

    def ice_aktarma(ad: str, satir: int) -> None:
        if _kok(ad) in HER_ZAMAN_YASAK:
            bulgu.append((satir, "yasakModul", ad))
        elif _kok(ad) in AG_MODULLERI and not _ice_aktarma_izinli(ad, izinli):
            bulgu.append((satir, "beyansizBaglanti", ad))

    surucu_var = False
    for d in ast.walk(agac):
        if isinstance(d, ast.Import):
            for a in d.names:
                ice_aktarma(a.name, d.lineno)
        elif isinstance(d, ast.ImportFrom):
            taban = d.module or ""
            if d.level == 0:
                if _kok(taban) in AG_MODULLERI and taban and not _ice_aktarma_izinli(taban, izinli):
                    # `from multiprocessing import connection` gibi alt modül içe aktarımı
                    if not all(_ice_aktarma_izinli(f"{taban}.{a.name}", izinli) for a in d.names):
                        bulgu.append((d.lineno, "beyansizBaglanti", taban))
                elif _kok(taban) in HER_ZAMAN_YASAK:
                    bulgu.append((d.lineno, "yasakModul", taban))
        elif isinstance(d, ast.ClassDef) and d.name == "Surucu":
            surucu_var = any(isinstance(b, ast.Name) and b.id == "BobinSurucusu" for b in d.bases)
        elif isinstance(d, ast.Call):
            f = d.func
            if isinstance(f, ast.Name) and f.id in YASAK_CAGRILAR:
                bulgu.append((d.lineno, "dinamikKod", f.id))
            elif (
                isinstance(f, ast.Name)
                and f.id == "open"
                and _yazma_kipi(d)
                and not (d.args and _dosya_yolu_cagrisi(d.args[0]))
            ):
                bulgu.append((d.lineno, "klasorDisiYazma", "open"))
            elif isinstance(f, ast.Attribute):
                sahip = f.value.id if isinstance(f.value, ast.Name) else ""
                if sahip == "os" and (f.attr in OS_YASAK or f.attr.startswith(("spawn", "exec", "posix_spawn"))):
                    bulgu.append((d.lineno, "altSurecVeyaDosya", f"os.{f.attr}"))
                elif f.attr in YOL_YASAK and sahip != "self":
                    bulgu.append((d.lineno, "klasorDisiYazma", f.attr))
                elif f.attr == "publish":
                    bulgu.extend(_mqtt_yayin(d, kimlik))
        elif isinstance(d, ast.Constant) and isinstance(d.value, str) and d.value.startswith("pemf/"):
            if not d.value.startswith(f"pemf/modul/{kimlik}/"):
                bulgu.append((d.lineno, "mqttKonuAlaniDisi", d.value))
    if not surucu_var:
        bulgu.append((0, "surucuSinifiYok", "class Surucu(BobinSurucusu)"))
    return sorted(set(bulgu))


def _mqtt_yayin(d: ast.Call, kimlik: str) -> list[tuple[int, str, str]]:
    out = []
    for k in d.keywords:
        if k.arg == "retain" and not (isinstance(k.value, ast.Constant) and k.value.value is False):
            out.append((d.lineno, "mqttKaliciIleti", "retain"))
    if len(d.args) >= 4:
        out.append((d.lineno, "mqttKaliciIleti", "retain (konumsal)"))
    return out


def denetle(klasor) -> list[tuple[int, str, str]]:
    klasor = Path(klasor)
    try:
        modul = json.loads((klasor / "modul.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        modul = {}
    if not isinstance(modul, dict):
        modul = {}
    try:
        kaynak = (klasor / "surucu.py").read_text(encoding="utf-8")
    except OSError:
        return [(0, "surucuYok", "surucu.py")]
    return denetle_kaynak(kaynak, modul)


def main(argv=None) -> int:
    """Komut satırı: `python -c "from servers.modul_denetleyici import main; raise SystemExit(main([...]))"` — bulgu varsa çıkış 1."""
    argv = list(sys.argv[1:] if argv is None else argv)
    kotu = 0
    for k in argv:
        for satir, kod, ayrinti in denetle(k):
            print(f"{k}:{satir}: {kod} — {ayrinti}")
            kotu += 1
    print(f"{len(argv)} modül · {kotu} bulgu")
    return 1 if kotu else 0
